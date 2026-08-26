from django.core.cache import cache
from .models import Notification


def unread_notifications(request):
    if request.user.is_authenticated:
        key = f'notif_{request.user.pk}'
        data = cache.get(key)
        if data is None:
            data = (
                Notification.objects.filter(user=request.user, is_read=False).count(),
                list(Notification.objects.filter(user=request.user)[:5]),
            )
            cache.set(key, data, 5)
        unread_count, notifications = data
        return {
            'unread_count': unread_count,
            'recent_notifications': notifications,
        }
    return {'unread_count': 0, 'recent_notifications': []}
