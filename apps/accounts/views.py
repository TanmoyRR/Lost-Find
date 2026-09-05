import logging
from urllib.parse import urlparse

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


def _send_verification_email(user):
    token = user.email_verification_token
    verify_url = f'{settings.SITE_URL}/verify-email/{token}/'
    context = {'user': user, 'verify_url': verify_url, 'site_name': settings.SITE_NAME}
    _send_email(
        subject=f'Verify your email - {settings.SITE_NAME}',
        template='accounts/emails/email_verification.html',
        context=context,
        recipient=user.email,
    )


@ratelimit(key='ip', rate='5/m', method=['POST'], block=True)
def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = 'student'
            user.is_membership_paid = False
            user.email_verification_token = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
            user.email_verification_sent_at = timezone.now()
            user.save()
            try:
                _send_verification_email(user)
            except Exception:
                logger.warning('Failed to send verification email for user %s', user.pk, exc_info=True)
            login(request, user)
            messages.success(request, 'Registration successful! Please check your email to verify your account.')
            return redirect('accounts:verify_email_gate')
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
            login(request, user)
            UserActivity.objects.create(user=user, activity_type='login', description='User logged in')
            if user.role == 'admin':
                return redirect('dashboard:admin_home')
            if not user.email_verified:
                messages.info(request, 'Please verify your email to continue.')
                return redirect('accounts:verify_email_gate')
            if not user.is_membership_paid:
                messages.info(request, 'Please complete your membership payment to activate your account.')
                return redirect('membership:pending_purchase')
            next_url = request.GET.get('next', '')
            if next_url and _is_safe_redirect_url(next_url):
                return redirect(next_url)
            return redirect('dashboard:home')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})


def verify_email(request, token):
    user = get_object_or_404(User, email_verification_token=token)
    if user.email_verification_sent_at and (timezone.now() - user.email_verification_sent_at).total_seconds() > 86400:
        messages.error(request, 'Verification link has expired. Please sign in and request a new one.')
        return redirect('accounts:login')
    user.email_verified = True
    user.is_verified = True
    user.email_verification_token = None
    user.email_verification_sent_at = None
    user.save()
    messages.success(request, 'Email verified successfully! You can now login.')
    return redirect('accounts:login')


@login_required
def verify_email_gate(request):
    if request.user.email_verified or request.user.role == 'admin':
        return redirect('dashboard:home')
    return render(request, 'accounts/verify_email_gate.html')


@login_required
@ratelimit(key='ip', rate='3/m', method=['POST'], block=True)
def resend_verification(request):
    if request.user.email_verified or request.user.role == 'admin':
        return redirect('dashboard:home')
    if request.method == 'POST':
        user = request.user
        user.email_verification_token = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
        user.email_verification_sent_at = timezone.now()
        user.save()
        try:
            _send_verification_email(user)
            messages.success(request, 'Verification email sent! Check your inbox.')
        except Exception:
            logger.warning('Failed to resend verification email for user %s', user.pk, exc_info=True)
            messages.error(request, 'Failed to send email. Please try again later.')
        return redirect('accounts:verify_email_gate')
    return redirect('accounts:verify_email_gate')


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
            except User.DoesNotExist:
                messages.success(request, 'If an account exists with this email, a reset link has been sent.')
            return redirect('accounts:login')
    else:
        form = PasswordResetRequestForm()
    return render(request, 'accounts/forgot_password.html', {'form': form})


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
    all_activities = UserActivity.objects.filter(user=user).order_by('-created_at')
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
    messages.success(request, f'Account "{username}" has been permanently deleted.')
    return redirect('pages:home')
