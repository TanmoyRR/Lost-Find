import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator

from .models import Notification

logger = logging.getLogger(__name__)


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    paginator = Paginator(notifications, 20)
    page = request.GET.get('page', 1)
    notifications_page = paginator.get_page(page)
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    return render(request, 'notifications/list.html', {
        'notifications': notifications_page,
        'unread_count': unread_count,
    })


@login_required
def mark_read(request, pk):
    if request.method != 'POST':
        return redirect('notifications:list')
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save(update_fields=['is_read'])
    if notification.link:
        return redirect(notification.link)
    return redirect('notifications:list')


@login_required
def mark_all_read(request):
    if request.method != 'POST':
        return redirect('notifications:list')
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    messages.success(request, 'All notifications marked as read.')
    return redirect('notifications:list')
