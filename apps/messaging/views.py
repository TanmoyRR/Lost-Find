"""
Messaging Views — Real-time chat system for post owners and finders.

This module handles:
  - Inbox: list all conversations with unread counts and last message preview
  - Conversation detail: view message history, send/edit/delete messages
  - Starting conversations: links to a post and auto-initiates recovery sessions

Recovery Integration:
  When a conversation is started about a post, this module automatically
  creates or links RecoverySessions. This is the bridge between messaging
  and the recovery verification system.

  For lost posts: _initiate_recovery() creates/links a session with the
    viewer as claimant (finder) and the post owner as owner.
  For found posts: _link_found_recovery() creates/links a session with
    the viewer as owner (the person who lost the item) and the post
    creator as claimant (the finder).
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
      2. For lost posts: trigger _initiate_recovery() to create/link recovery session
      3. For found posts: trigger _link_found_recovery() to create/link recovery session
      4. Redirect to the conversation

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

    # Auto-initiate recovery session based on post type
    if post.post_type == 'lost' and post.status != 'resolved':
        _initiate_recovery(post, request.user, other)
    elif post.post_type == 'found' and post.status != 'resolved':
        _link_found_recovery(post, request.user, other)

    return redirect('messaging:detail', pk=conv.pk)


def _initiate_recovery(post, viewer, post_owner):
    """
    Create or link a recovery session for a LOST post when a conversation starts.

    Roles:
      - post_owner: The person who lost the item (session.owner, has the token)
      - viewer: The person who found it (session.claimant, will enter the token)

    If a session already exists for this post:
      - Assign the viewer as claimant if no claimant is set yet
      - Update status from 'pending' to 'token_generated' if needed
    """
    from apps.recovery.models import RecoverySession, RecoveryVerificationLog

    if post.status == 'resolved':
        return

    session = RecoverySession.objects.filter(
        post=post, status__in=('pending', 'token_generated'),
    ).first()

    if not session:
        # No session exists yet — create one
        session = RecoverySession.objects.create(
            post=post, owner=post_owner, claimant=viewer, status='token_generated',
        )
        RecoveryVerificationLog.objects.create(
            session=session, action='session_created',
            performed_by=post_owner,
            details={'post_id': post.id, 'initiated_by': 'messaging'},
        )
    elif not session.claimant or session.claimant == viewer:
        # Session exists but claimant not set yet, or same viewer — update it
        session.claimant = viewer
        if session.status == 'pending':
            session.status = 'token_generated'
            session.save(update_fields=['claimant', 'status'])
        else:
            session.save(update_fields=['claimant'])

        RecoveryVerificationLog.objects.create(
            session=session, action='finder_assigned',
            performed_by=viewer,
            details={'source': 'messaging'},
        )


def _link_found_recovery(post, viewer, post_owner):
    """
    Create or link a recovery session for a FOUND post when a conversation starts.

    For found posts, the roles are reversed:
      - viewer: The person who lost the item (session.owner, will enter the token)
      - post_owner: The person who found it (session.claimant, has the token)

    This is the inverse of _initiate_recovery() because found posts flip the
    owner/finder relationship.
    """
    from apps.recovery.models import RecoverySession, RecoveryVerificationLog

    if post.status == 'resolved':
        return

    session = RecoverySession.objects.filter(
        post=post, status__in=('pending', 'token_generated'),
    ).first()

    if not session:
        # Create session: viewer = owner (lost item), post_owner = claimant (finder)
        session = RecoverySession.objects.create(
            post=post, owner=viewer, claimant=post_owner, status='token_generated',
        )
        RecoveryVerificationLog.objects.create(
            session=session, action='session_created',
            performed_by=viewer,
            details={
                'post_id': post.id, 'post_title': post.title,
                'initiated_by': 'messaging', 'found_post': True,
            },
        )
    elif not session.claimant or session.claimant == post_owner:
        # Update existing session with the post creator as claimant
        session.claimant = post_owner
        if session.status == 'pending':
            session.status = 'token_generated'
            session.save(update_fields=['claimant', 'status'])
        else:
            session.save(update_fields=['claimant'])

        RecoveryVerificationLog.objects.create(
            session=session, action='finder_assigned',
            performed_by=post_owner,
            details={'source': 'messaging', 'found_post': True},
        )
