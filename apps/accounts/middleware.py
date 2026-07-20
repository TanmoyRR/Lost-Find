from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone


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
