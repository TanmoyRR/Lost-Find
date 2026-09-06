from datetime import timedelta
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q
from apps.accounts.decorators import is_admin


class MembershipPendingMiddleware:
    ALLOWED_PATH_PREFIXES = [
        '/membership/',
        '/payments/',
        '/logout/',
        '/login/',

        '/static/',
        '/media/',
        '/favicon.ico',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            if request.user.role != 'admin':
                membership_active = False
                if hasattr(request.user, 'membership'):
                    membership_active = request.user.membership.is_active

                if not membership_active and not request.user.is_membership_paid:
                    from apps.payments.models import Payment
                    completed_payment = Payment.objects.filter(
                        user=request.user, payment_type='membership', status='completed'
                    ).order_by('-created_at').first()
                    if completed_payment:
                        request.user.is_membership_paid = True
                        request.user.save(update_fields=['is_membership_paid'])
                        if not membership_active:
                            if hasattr(request.user, 'membership'):
                                m = request.user.membership
                                if not m.is_active:
                                    m.is_active = True
                                    m.started_at = m.started_at or timezone.now()
                                    if not m.expires_at or m.expires_at <= timezone.now():
                                        m.expires_at = timezone.now() + timedelta(days=30)
                                    m.save(update_fields=['is_active', 'started_at', 'expires_at'])
                            else:
                                from apps.membership.models import Membership
                                Membership.objects.create(
                                    user=request.user, is_active=True,
                                    started_at=timezone.now(),
                                    expires_at=timezone.now() + timedelta(days=30),
                                )
                        membership_active = True

                if not membership_active and not request.user.is_membership_paid:
                    path = request.path
                    if not any(path.startswith(prefix) for prefix in self.ALLOWED_PATH_PREFIXES):
                        return redirect('membership:pending_purchase')
        response = self.get_response(request)
        return response


class MembershipMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not is_admin(request.user) and hasattr(request.user, 'membership'):
            membership = request.user.membership
            if membership.is_active and membership.expires_at:
                days_left = (membership.expires_at.date() - timezone.now().date()).days
                if days_left <= 0:
                    membership.is_active = False
                    membership.save(update_fields=['is_active'])
                    if request.user.is_membership_paid:
                        request.user.is_membership_paid = False
                        request.user.save(update_fields=['is_membership_paid'])
                elif days_left <= 7:
                    from django.core.cache import cache
                    notif_key = f'membership_expiring_notif_{request.user.pk}'
                    if not cache.get(notif_key):
                        from apps.notifications.models import Notification
                        from django.urls import reverse
                        Notification.objects.create(
                            user=request.user,
                            notification_type='membership_expiring',
                            title='Membership Expiring Soon',
                            message=f'Your membership expires in {days_left} day{"s" if days_left != 1 else ""}. Renew to keep premium features.',
                            link=reverse('membership:manage'),
                        )
                        cache.set(notif_key, True, 86400)
        response = self.get_response(request)
        return response


class ActiveUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.user.is_suspended:
            from django.contrib.auth import logout
            logout(request)
            from django.contrib import messages
            messages.error(request, 'Your account has been suspended. Please contact the administrator.')
            from django.shortcuts import redirect
            return redirect('accounts:login')
        response = self.get_response(request)
        return response


class EmailVerificationMiddleware:
    ALLOWED_PATH_PREFIXES = [
        '/verify-email/',
        '/resend-verification/',
        '/logout/',
        '/login/',
        '/forgot-password/',
        '/reset-password/',
        '/payments/',
        '/membership/',

        '/static/',
        '/media/',
        '/favicon.ico',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.email_verified:
            if is_admin(request.user):
                response = self.get_response(request)
                return response
            path = request.path
            if not any(path.startswith(prefix) for prefix in self.ALLOWED_PATH_PREFIXES):
                from django.shortcuts import redirect
                return redirect('accounts:verify_email_gate')
        response = self.get_response(request)
        return response
