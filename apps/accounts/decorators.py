from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps


def membership_required(view_func=None, redirect_to='membership:index'):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_superuser or request.user.is_staff:
                return view_func(request, *args, **kwargs)
            membership = getattr(request.user, 'membership', None)
            if membership and membership.is_active:
                return view_func(request, *args, **kwargs)
            messages.warning(request, 'You need an active membership to perform this action.')
            return redirect(redirect_to)
        return _wrapped_view

    if view_func:
        return decorator(view_func)
    return decorator
