"""
Messaging Views — Real-time chat system for post owners and finders.

This module handles:
  - Inbox: list all conversations with unread counts and last message preview
  - Conversation detail: view message history, send/edit/delete messages
  - Starting conversations: links to a post and auto-initiates recovery sessions

Recovery Integration:
  When a conversation is started about a post, this module ensures a SINGLE
  RecoverySession exists for the match. This is the bridge between messaging
  and the recovery verification system.

  Whoever messages first creates the session. A second message (either direction)
  reuses the same session — one session per match, never two.
"""

import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Max, Prefetch
from django.db import transaction
from django.core.paginator import Paginator

from .models import Conversation, Message
from apps.accounts.decorators import membership_required
from apps.accounts.models import User
from apps.posts.models import Post

logger = logging.getLogger(__name__)


@login_required
def inbox(request):
    """
    Display all conversations for the current user.

    Optimizations:
      - Uses Prefetch to fetch only the last message per conversation
      - Annotates unread count (messages from others that haven't been read)
      - Prefetches participants to avoid N+1 queries
    """
    last_msg_qs = Message.objects.order_by('-created_at')
    conversations = Conversation.objects.filter(
        participants=request.user
    ).order_by('-updated_at').prefetch_related(
        'participants',
        Prefetch('messages', queryset=last_msg_qs, to_attr='_last_msgs'),
    ).annotate(
        last_msg_time=Max('messages__created_at'),
        unread_count=Count(
            'messages',
            filter=Q(messages__is_read=False) & ~Q(messages__sender=request.user)
        )
    )

    for conv in conversations:
        conv.last_message = conv._last_msgs[0] if conv._last_msgs else None
        conv.other_users = conv.participants.exclude(pk=request.user.pk)

    return render(request, 'messaging/inbox.html', {
        'conversations': conversations,
    })


@login_required
def conversation_detail(request, pk):
    """
    Display a single conversation with all messages.

    Handles three POST actions:
      - 'send' (default): Create a new message, notify the other participant
      - 'edit': Edit an existing message (sender only)
      - 'delete': Soft-delete a message (sender only, marks as deleted)

    Also marks all unread messages from the other party as read.
    Messages are paginated (50 per page, oldest first in chat view).
    """
    conv = get_object_or_404(Conversation, pk=pk, participants=request.user)
    all_messages = conv.messages.all().select_related('sender')
    other = conv.other_participants(request.user).first()

    paginator = Paginator(all_messages, 50)
    page = request.GET.get('page', 1)
    messages_page = paginator.get_page(page)

    if request.method == 'POST':
        action = request.POST.get('action', 'send')

        if action == 'edit':
            # Edit a message — only the sender can edit their own
            msg_id = request.POST.get('message_id')
            new_body = (request.POST.get('body', '') or '').strip()
            if msg_id and new_body:
                msg = get_object_or_404(Message, pk=msg_id, sender=request.user, conversation=conv)
                msg.edit_message(new_body)
                messages.success(request, 'Message edited.')
            return redirect('messaging:detail', pk=pk)

        elif action == 'delete':
            # Soft-delete a message — marks as deleted, keeps in DB
            msg_id = request.POST.get('message_id')
            if msg_id:
                msg = get_object_or_404(Message, pk=msg_id, sender=request.user, conversation=conv)
                msg.mark_as_deleted()
                messages.success(request, 'Message deleted.')
            return redirect('messaging:detail', pk=pk)

        else:
            # Send a new message
            body = (request.POST.get('body', '') or '').strip()
            if body:
                if len(body) > 5000:
                    messages.error(request, 'Message is too long (max 5000 characters).')
                    return redirect('messaging:detail', pk=pk)

                Message.objects.create(
                    conversation=conv,
                    sender=request.user,
                    body=body,
                )
                conv.save()  # Updates the updated_at timestamp

                # Send notification to the other participant
                if other:
                    from django.urls import reverse
                    from apps.notifications.models import Notification
                    Notification.objects.create(
                        user=other,
                        notification_type='message',
                        title=f'New message from {request.user.get_full_name() or request.user.username}',
                        message=body[:200],
                        link=reverse('messaging:detail', args=[conv.pk]),
                    )
            return redirect('messaging:detail', pk=pk)

    # Mark unread messages from the other party as read
    Message.objects.filter(conversation=conv, is_read=False).exclude(sender=request.user).update(is_read=True)

    return render(request, 'messaging/conversation.html', {
        'conversation': conv,
        'messages': messages_page,
        'other': other,
    })


@membership_required
@transaction.atomic
def start_conversation(request, post_id, user_id):
    """
    Start or resume a conversation about a specific post with a specific user.

    Flow:
      1. Find or create a Conversation between the two users about this post
      2. Ensure a single recovery session exists for this match (_ensure_recovery_session)
      3. Redirect to the conversation

    This is the entry point that connects the messaging system to the recovery system.
    """
    post = get_object_or_404(Post, pk=post_id)
    other = get_object_or_404(User, pk=user_id)

    if other == request.user:
        messages.error(request, 'You cannot start a conversation with yourself.')
        return redirect('posts:detail', pk=post_id)

    # Find existing conversation or create a new one
    conv = Conversation.objects.filter(
        participants=request.user
    ).filter(
        participants=other
    ).filter(
        post=post
    ).first()

    if not conv:
        conv = Conversation.objects.create(post=post, subject=f'Regarding: {post.title}')
        conv.participants.add(request.user, other)

    # Auto-initiate single recovery session based on post type
    if post.status != 'resolved':
        _ensure_recovery_session(post, request.user, other)

    return redirect('messaging:detail', pk=conv.pk)


def _ensure_recovery_session(post, viewer, other):
    """
    Ensure a SINGLE recovery session exists for this match (post + two users).

    Rules:
      - Single session per match: whoever messages first creates it.
      - No auto-create at lost post creation — only here.
      - If an active session already exists linking these two users (either direction),
        reuse it and do NOT create a second one.

    Role assignment by post type:
      - Lost post:  owner = post.user (lost item, has token), claimant = viewer (finder)
      - Found post: owner = viewer (lost item), claimant = post.user (finder)
    """
    from apps.recovery.models import RecoverySession, RecoveryVerificationLog
    from django.db.models import Q

    if post.status == 'resolved':
        return None

    # 1. Reuse existing active session between these two users (single session per match)
    existing = RecoverySession.objects.filter(
        Q(owner=viewer, claimant=other) | Q(owner=other, claimant=viewer),
        status__in=('pending', 'token_generated', 'token_entered'),
    ).first()
    if existing:
        # Ensure claimant is set
        if not existing.claimant:
            existing.claimant = viewer if existing.owner == other else other
            if existing.status == 'pending':
                existing.status = 'token_generated'
            existing.save(update_fields=['claimant', 'status'])
        return existing

    # 2. Also check for an existing session on THIS post (for claimant=None edge cases)
    existing_on_post = RecoverySession.objects.filter(
        post=post, status__in=('pending', 'token_generated', 'token_entered'),
    ).first()
    if existing_on_post:
        return existing_on_post

    # 3. Determine roles based on post type
    if post.post_type == 'lost':
        owner_user = post.user       # lost item person
        claimant_user = viewer       # finder messaging about the lost post
    else:  # found
        owner_user = viewer          # lost item person messaging about found post
        claimant_user = post.user    # finder (found post creator)

    # Guard: owner and claimant must differ
    if owner_user == claimant_user:
        # Viewer is messaging about their own post — swap to use 'other'
        if post.post_type == 'lost':
            claimant_user = other
        else:
            owner_user = other
        if owner_user == claimant_user:
            return None

    session = RecoverySession.objects.create(
        post=post, owner=owner_user, claimant=claimant_user, status='token_generated',
    )
    RecoveryVerificationLog.objects.create(
        session=session, action='session_created',
        performed_by=viewer,
        details={'post_id': post.id, 'post_title': post.title, 'initiated_by': 'messaging'},
    )
    logger.info('Recovery session %s created via messaging for post %s', session.short_code, post.pk)
    return session
