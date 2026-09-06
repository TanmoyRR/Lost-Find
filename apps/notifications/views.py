import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator

from .models import Notification, invalidate_notification_cache

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
    next_url = request.POST.get('next', '')
    notification.mark_as_read()
    if next_url and next_url.startswith('/') and not next_url.startswith('//'):
        return redirect(next_url)
    if notification.link and notification.link.startswith('/') and not notification.link.startswith('//'):
        return redirect(notification.link)
    return redirect('notifications:list')


@login_required
def mark_all_read(request):
    if request.method != 'POST':
        return redirect('notifications:list')
    from django.utils import timezone
    Notification.objects.filter(user=request.user, is_read=False).update(
        is_read=True, read_at=timezone.now()
    )
    invalidate_notification_cache(request.user.pk)
    messages.success(request, 'All notifications marked as read.')
    return redirect('notifications:list')


@login_required
def delete_notification(request, pk):
    if request.method != 'POST':
        return redirect('notifications:list')
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.delete()
    invalidate_notification_cache(request.user.pk)
    messages.success(request, 'Notification deleted.')
    return redirect('notifications:list')


@login_required
def delete_all_read(request):
    if request.method != 'POST':
        return redirect('notifications:list')
    count = Notification.objects.filter(user=request.user, is_read=True).delete()[0]
    invalidate_notification_cache(request.user.pk)
    messages.success(request, f'Deleted {count} read notification(s).')
    return redirect('notifications:list')
