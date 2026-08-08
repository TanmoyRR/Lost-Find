from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.db import transaction

from .models import Conversation, Message
from apps.accounts.decorators import membership_required
from apps.accounts.models import User
from apps.posts.models import Post
from apps.notifications.models import Notification


@login_required
def inbox(request):
    conversations = Conversation.objects.filter(participants=request.user).order_by('-updated_at')
    unread_counts = {}
    for conv in conversations:
        unread_counts[conv.id] = conv.messages.filter(is_read=False).exclude(sender=request.user).count()
    return render(request, 'messaging/inbox.html', {
        'conversations': conversations,
        'unread_counts': unread_counts,
    })


@login_required
def conversation_detail(request, pk):
    conv = get_object_or_404(Conversation, pk=pk, participants=request.user)
    messages_qs = conv.messages.all().select_related('sender')
    Message.objects.filter(conversation=conv, is_read=False).exclude(sender=request.user).update(is_read=True)
    other = conv.other_participants(request.user).first()
    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        if body:
            Message.objects.create(conversation=conv, sender=request.user, body=body)
            Notification.objects.create(
                user=other,
                notification_type='message',
                title=f'New message from {request.user.get_full_name() or request.user.username}',
                message=body[:200],
                link=f'/messages/{conv.pk}/',
            )
            return redirect('messaging:detail', pk=conv.pk)
    return render(request, 'messaging/conversation.html', {
        'conversation': conv,
        'messages': messages_qs,
        'other': other,
    })


@membership_required
@transaction.atomic
def start_conversation(request, post_id, user_id):
    post = get_object_or_404(Post, pk=post_id)
    other = get_object_or_404(User, pk=user_id)
    if other == request.user:
        messages.error(request, 'You cannot start a conversation with yourself.')
        return redirect('posts:detail', pk=post_id)
    conv = Conversation.objects.filter(participants=request.user).filter(participants=other).filter(post=post).first()
    if not conv:
        conv = Conversation.objects.create(post=post, subject=f'Regarding: {post.title}')
        conv.participants.add(request.user, other)
    return redirect('messaging:detail', pk=conv.pk)
