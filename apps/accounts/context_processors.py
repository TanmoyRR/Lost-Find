from apps.notifications.models import Notification
from apps.membership.models import Membership

def notification_processor(request):
    context = {}
    if request.user.is_authenticated:
        notifications = Notification.objects.filter(user=request.user)[:5]
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
        context['recent_notifications'] = notifications
        context['unread_count'] = unread_count
    return context


def site_settings(request):
    context = {
        'site_name': 'Lost & Found',
        'site_description': 'Campus Lost and Found Management System',
    }
    if hasattr(request, 'user') and request.user.is_authenticated:
        try:
            context['membership'] = Membership.objects.get(user=request.user)
        except Membership.DoesNotExist:
            context['membership'] = None
    else:
        context['membership'] = None
    return context