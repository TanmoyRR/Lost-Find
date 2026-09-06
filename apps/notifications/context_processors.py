from django.core.cache import cache
from .models import Notification


def unread_notifications(request):
    if request.user.is_authenticated:
        key = f'notif_{request.user.pk}'
        data = cache.get(key)
        if data is None:
            unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
            unread = list(
                Notification.objects.filter(user=request.user, is_read=False)
                .select_related()
                .order_by('-created_at')[:5]
            )
            if len(unread) < 5:
                read = list(
                    Notification.objects.filter(user=request.user, is_read=True)
                    .select_related()
                    .order_by('-created_at')[:5 - len(unread)]
                )
                notifications = unread + read
            else:
                notifications = unread
            data = (unread_count, notifications)
            cache.set(key, data, 5)
        unread_count, notifications = data
        return {
            'unread_count': unread_count,
            'recent_notifications': notifications,
        }
    return {'unread_count': 0, 'recent_notifications': []}
