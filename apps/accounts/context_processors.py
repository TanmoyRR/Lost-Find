from django.conf import settings
from django.core.cache import cache
from apps.membership.models import Membership


def site_settings(request):
    context = {
        'site_name': settings.SITE_NAME,
        'site_description': 'IUBAT Lost and Found Management System',
    }
    if hasattr(request, 'user') and request.user.is_authenticated:
        membership = getattr(request, '_membership', None)
        if membership is None:
            membership = getattr(request.user, 'membership', None)
        if membership is None:
            key = f'site_membership_{request.user.pk}'
            cached = cache.get(key)
            if cached is None:
                membership = Membership.objects.filter(user=request.user).first()
                cache.set(key, membership or 'none', 60)
            elif cached != 'none':
                membership = cached
        context['membership'] = membership
    else:
        context['membership'] = None
    return context
