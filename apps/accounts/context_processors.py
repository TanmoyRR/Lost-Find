from django.conf import settings
from django.core.cache import cache
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
        'site_name': settings.SITE_NAME,
        'site_description': 'Campus Lost and Found Management System',
    }
    if hasattr(request, 'user') and request.user.is_authenticated:
        user = request.user
        membership = getattr(user, 'membership', None)
        if membership is None:
            key = f'site_membership_{user.pk}'
            cached = cache.get(key)
            if cached is None:
                membership = Membership.objects.filter(user=user).first()
                cache.set(key, membership or 'none', 10)
            elif cached != 'none':
                membership = cached
            if membership is not None:
                user.membership = membership
        context['membership'] = membership
    else:
        context['membership'] = None
    return context
