import logging
from urllib.parse import urlparse
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django_ratelimit.decorators import ratelimit
import hashlib
import secrets

from .models import User, UserActivity
from .forms import (
    UserRegistrationForm, LoginForm, PasswordResetRequestForm,
    SetNewPasswordForm, UserProfileForm, UserSettingsForm
)
from apps.posts.models import Post
from apps.membership.models import Membership
from apps.notifications.models import Notification

logger = logging.getLogger(__name__)


def _is_safe_redirect_url(url, request=None):
    """Check if a URL is safe for redirect (same host, no external domains)."""
    if not url:
        return False
    # Only allow relative paths
    parsed = urlparse(url)
    if parsed.scheme or parsed.netloc:
        return False
    # Must start with /
    if not url.startswith('/') or url.startswith('//'):
        return False
    return True


def _send_email(subject, template, context, recipient):
    html = render_to_string(template, context)
    plain = strip_tags(html)
    send_mail(subject, plain, settings.DEFAULT_FROM_EMAIL, [recipient], html_message=html)


@ratelimit(key='ip', rate='5/m', method=['POST'], block=True)
def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = 'student'
            user.is_membership_paid = False
            user.email_verified = True
            user.save()
            login(request, user)
            messages.success(request, 'Registration successful!')
            return redirect('membership:pending_purchase')
    else:
        form = UserRegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})


@ratelimit(key='ip', rate='10/m', method=['POST'], block=True)
def user_login(request):
    if request.user.is_authenticated:
        if request.user.role == 'admin':
            return redirect('dashboard:admin_home')
        if not request.user.is_membership_paid:
            return redirect('membership:pending_purchase')
        return redirect('dashboard:home')
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if user.is_suspended:
                messages.error(request, 'Your account has been suspended.')
                return render(request, 'accounts/login.html', {'form': form})
            if user.locked_until and user.locked_until > timezone.now():
                messages.error(request, 'Account is temporarily locked due to too many failed login attempts. Please try again later.')
                return render(request, 'accounts/login.html', {'form': form})
            login(request, user)
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save(update_fields=['failed_login_attempts', 'locked_until'])
            UserActivity.objects.create(user=user, activity_type='login', description='User logged in')
            if user.role == 'admin':
                return redirect('dashboard:admin_home')
            if not user.is_membership_paid:
                messages.info(request, 'Please complete your membership payment to activate your account.')
                return redirect('membership:pending_purchase')
            next_url = request.GET.get('next', '')
            if next_url and _is_safe_redirect_url(next_url):
                return redirect(next_url)
            return redirect('dashboard:home')
        else:
            username = request.POST.get('username', '')
            if username:
                from .models import User as UserModel
                try:
                    failed_user = UserModel.objects.get(username=username)
                    failed_user.failed_login_attempts += 1
                    if failed_user.failed_login_attempts >= 5:
                        failed_user.locked_until = timezone.now() + timedelta(minutes=15)
                    failed_user.save(update_fields=['failed_login_attempts', 'locked_until'])
                except UserModel.DoesNotExist:
                    pass
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})


@ratelimit(key='ip', rate='5/m', method=['POST'], block=True)
def forgot_password(request):
    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                user = User.objects.get(email=email)
                token = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
                user.reset_password_token = token
                user.reset_password_sent_at = timezone.now()
                user.save()
                reset_url = request.build_absolute_uri(reverse('accounts:reset_password', args=[token]))
                _send_email(
                    f'Password Reset - {settings.SITE_NAME}',
                    'accounts/emails/password_reset.html',
                    {'user': user, 'reset_url': reset_url},
                    user.email
                )
                messages.success(request, 'Password reset link sent to your email.')
                if settings.DEBUG:
                    messages.info(request, f'Dev reset link: {reset_url}')
            except User.DoesNotExist:
                messages.success(request, 'If an account exists with this email, a reset link has been sent.')
            return redirect('accounts:login')
    else:
        form = PasswordResetRequestForm()
    return render(request, 'accounts/forgot_password.html', {'form': form})


@ratelimit(key='ip', rate='10/m', method=['POST'], block=True)
def reset_password(request, token):
    user = get_object_or_404(User, reset_password_token=token)
    if user.reset_password_sent_at and (timezone.now() - user.reset_password_sent_at).total_seconds() > 3600:
        messages.error(request, 'Reset link has expired. Please request a new one.')
        return redirect('accounts:forgot_password')
    if request.method == 'POST':
        form = SetNewPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            user.reset_password_token = None
            user.reset_password_sent_at = None
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save()
            messages.success(request, 'Password reset successful! Please login.')
            return redirect('accounts:login')
    else:
        form = SetNewPasswordForm(user)
    return render(request, 'accounts/reset_password.html', {'form': form})


@login_required
def user_logout(request):
    logout(request)
    messages.success(request, 'Logged out successfully.')
    return redirect('pages:home')


@login_required
def profile_view(request):
    user = request.user
    user_posts = Post.objects.filter(user=user).select_related('category', 'location').order_by('-created_at')
    total_posts = user_posts.count()
    open_posts = user_posts.filter(status='open').count()
    resolved_posts = user_posts.filter(status='resolved').count()
    membership = getattr(user, 'membership', None)
    membership_days = membership.days_remaining() if membership and membership.is_active else 0
    recent_activities = UserActivity.objects.filter(user=user)[:10]
    all_activities = UserActivity.objects.filter(user=user).order_by('-created_at')[:50]
    from apps.recovery.models import RecoverySession
    recovery_sessions = RecoverySession.objects.filter(Q(claimant=user)|Q(owner=user)).count()
    recovery_rate = round((resolved_posts / total_posts * 100) if total_posts > 0 else 0, 1)
    return render(request, 'profile/overview.html', {
        'user': user,
        'user_posts': user_posts[:10],
        'total_posts': total_posts,
        'open_posts': open_posts,
        'resolved_posts': resolved_posts,
        'recovery_rate': recovery_rate,
        'recovery_sessions': recovery_sessions,
        'membership_days': membership_days,
        'recent_activities': recent_activities,
        'all_activities': all_activities,
        'membership': membership,
    })


@login_required
def profile_edit(request):
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            UserActivity.objects.create(user=request.user, activity_type='profile_updated', description='Profile updated')
            messages.success(request, 'Profile updated successfully!')
            return redirect('accounts:profile')
    else:
        form = UserProfileForm(instance=request.user)
    return render(request, 'profile/edit.html', {'form': form, 'departments': User.DEPARTMENTS})


@login_required
def change_password(request):
    if request.user.role == 'admin':
        messages.error(request, 'Admin passwords can only be changed through the backend.')
        return redirect('accounts:profile')
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, form.user)
            request.user.reset_password_token = None
            request.user.save(update_fields=['reset_password_token'])
            UserActivity.objects.create(user=request.user, activity_type='password_changed', description='Password changed')
            messages.success(request, 'Password changed successfully!')
            return redirect('accounts:profile')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'profile/change_password.html', {'form': form})


@login_required
def settings_view(request):
    if request.method == 'POST':
        form = UserSettingsForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Settings updated successfully!')
            return redirect('accounts:settings')
    else:
        form = UserSettingsForm(instance=request.user)
    return render(request, 'profile/settings.html', {'form': form})


@login_required
def delete_account(request):
    if request.method != 'POST':
        return redirect('accounts:settings')
    user = request.user
    username = user.username
    logout(request)
    user.delete()
    response = redirect('pages:home')
    from django.core.signing import Signer
    signer = Signer()
    response.set_cookie('account_deleted_msg', signer.sign(username), max_age=10)
    return response


@login_required
def active_sessions(request):
    from django.contrib.sessions.models import Session
    from django.utils import timezone
    sessions = Session.objects.filter(expire_date__gte=timezone.now()).order_by('-expire_date')
    user_sessions = []
    current_session_key = request.session.session_key
    for s in sessions:
        data = s.get_decoded()
        if data.get('_auth_user_id') == str(request.user.pk):
            user_sessions.append({
                'session_key': s.session_key,
                'expire_date': s.expire_date,
                'is_current': s.session_key == current_session_key,
                'ip': data.get('ip_address', 'Unknown'),
                'user_agent': data.get('user_agent', 'Unknown'),
            })
    return render(request, 'accounts/sessions.html', {'sessions': user_sessions})


@login_required
def revoke_session(request, session_key):
    from django.contrib.sessions.models import Session
    if request.method != 'POST':
        return redirect('accounts:sessions')
    if session_key == request.session.session_key:
        messages.error(request, 'You cannot revoke your current session.')
        return redirect('accounts:sessions')
    try:
        Session.objects.get(session_key=session_key).delete()
        messages.success(request, 'Session revoked successfully.')
    except Session.DoesNotExist:
        messages.error(request, 'Session not found.')
    return redirect('accounts:sessions')
