from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone


class MembershipPendingMiddleware:
    ALLOWED_PATH_PREFIXES = [
        '/membership/',
        '/payments/',
        '/accounts/logout/',
        '/admin/',
        '/static/',
        '/media/',
        '/favicon.ico',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            if request.user.role != 'admin' and not request.user.is_membership_paid:
                path = request.path
                if not any(path.startswith(prefix) for prefix in self.ALLOWED_PATH_PREFIXES):
                    return redirect('membership:pending_purchase')
        response = self.get_response(request)
        return response


class MembershipMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and hasattr(request.user, 'membership'):
            membership = request.user.membership
            if membership.is_active and membership.expires_at and membership.expires_at < timezone.now():
                membership.is_active = False
                membership.save()
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
