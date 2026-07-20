from .models import Notification


def unread_notifications(request):
    if request.user.is_authenticated:
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        notifications = Notification.objects.filter(user=request.user)[:5]
        return {
            'unread_count': count,
            'recent_notifications': notifications,
        }
    return {'unread_count': 0, 'recent_notifications': []}
