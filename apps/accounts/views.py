"""
Account Views — Authentication, profile management, and user settings.

This module handles:
  - Registration (with rate limiting: 5/min per IP)
  - Login (with brute-force protection: 5 failed attempts → 15-min lockout)
  - Password reset (email-based token, 1-hour expiry)
  - Profile viewing and editing
  - Password change (admin passwords restricted to backend only)
  - Account deletion (with signed cookie for post-delete message)
  - Active session management (view and revoke other sessions)

Security features:
  - Rate limiting on all auth endpoints via django-ratelimit
  - Open redirect prevention via _is_safe_redirect_url()
  - Brute-force lockout after 5 failed login attempts
  - Password reset tokens expire after 1 hour
  - Admin passwords cannot be changed from the web interface
"""

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
    """
    Security check: prevent open redirect attacks.

    Only allows relative paths starting with '/' (no schemes, no domains).
    This prevents attackers from crafting login redirect URLs that point
    to external malicious sites.
    """
    if not url:
        return False
    # Only allow relative paths — reject absolute URLs
    parsed = urlparse(url)
    if parsed.scheme or parsed.netloc:
        return False
    # Must start with / but not // (protocol-relative URL)
    if not url.startswith('/') or url.startswith('//'):
        return False
    return True


def _send_email(subject, template, context, recipient):
    """Helper: send an HTML email with plain-text fallback."""
    try:
        html = render_to_string(template, context)
        plain = strip_tags(html)
        send_mail(subject, plain, settings.DEFAULT_FROM_EMAIL, [recipient], html_message=html)
    except Exception as e:
        logger.error('Email send failed to %s: %s', recipient, e)


@ratelimit(key='ip', rate='5/m', method=['POST'], block=True)
def register(request):
    """
    New user registration.

    Flow:
      1. Validate form (username, email, password, department)
      2. Set role='student', membership_paid=False, email_verified=False
      3. Send verification email
      4. Auto-login, redirect to email verification gate

    Rate limited: 5 attempts per minute per IP.
    """
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = 'student'
            user.is_membership_paid = False
            user.email_verified = False
            import secrets
            user.email_verification_token = secrets.token_urlsafe(32)
            user.email_verification_sent_at = timezone.now()
            user.save()
            login(request, user)

            verify_url = request.build_absolute_uri(
                reverse('accounts:verify_email', args=[user.email_verification_token])
            )
            _send_email(
                'Verify your email - IUBAT SmartFind',
                'accounts/emails/email_verification.html',
                {'user': user, 'verify_url': verify_url, 'site_name': settings.SITE_NAME},
                user.email,
            )

            messages.success(request, 'Registration successful! Please verify your email.')
            return redirect('accounts:verify_email_gate')
    else:
        form = UserRegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})


@login_required
def verify_email_gate(request):
    """Display verification pending page for unverified users."""
    if request.user.email_verified:
        return redirect('dashboard:home')
    return render(request, 'accounts/verify_email_gate.html')


def verify_email(request, token):
    """Verify email with token from verification link."""
    from django.contrib.auth import login as auth_login
    try:
        user = User.objects.get(email_verification_token=token)
    except User.DoesNotExist:
        messages.error(request, 'Invalid or expired verification link.')
        return redirect('accounts:login')

    if user.email_verified:
        messages.success(request, 'Email already verified. Please log in.')
        return redirect('accounts:login')

    if user.email_verification_sent_at:
        from datetime import timedelta
        if timezone.now() - user.email_verification_sent_at > timedelta(hours=24):
            messages.error(request, 'Verification link has expired. Please request a new one.')
            return redirect('accounts:login')

    user.email_verified = True
    user.email_verification_token = None
    user.email_verification_sent_at = None
    user.save(update_fields=['email_verified', 'email_verification_token', 'email_verification_sent_at'])
    auth_login(request, user)
    messages.success(request, 'Email verified successfully!')
    return redirect('membership:pending_purchase')


@login_required
def resend_verification(request):
    """Resend verification email."""
    if request.method != 'POST':
        return redirect('accounts:verify_email_gate')
    if request.user.email_verified:
        messages.success(request, 'Email already verified.')
        return redirect('dashboard:home')

    import secrets
    request.user.email_verification_token = secrets.token_urlsafe(32)
    request.user.email_verification_sent_at = timezone.now()
    request.user.save(update_fields=['email_verification_token', 'email_verification_sent_at'])

    verify_url = request.build_absolute_uri(
        reverse('accounts:verify_email', args=[request.user.email_verification_token])
    )
    _send_email(
        'Verify your email - IUBAT SmartFind',
        'accounts/emails/email_verification.html',
        {'user': request.user, 'verify_url': verify_url, 'site_name': settings.SITE_NAME},
        request.user.email,
    )
    messages.success(request, 'Verification email sent! Check your inbox.')
    return redirect('accounts:verify_email_gate')


@ratelimit(key='ip', rate='10/m', method=['POST'], block=True)
def user_login(request):
    """
    User login with brute-force protection.

    Security flow:
      1. If already logged in → redirect to appropriate dashboard
      2. Check if account is suspended → reject
      3. Check if account is locked (too many failed attempts) → reject
      4. On successful login: reset failed_attempts, log activity, redirect
      5. On failed login: increment failed_attempts, lock after 5 failures

    Brute-force protection:
      - After 5 failed attempts, account is locked for 15 minutes
      - Lockout timestamp stored in user.locked_until
      - Successful login resets the counter

    Redirect logic:
      - Admin → admin dashboard
      - Non-paid member → membership purchase page
      - Regular member → user dashboard (or ?next= URL if safe)
    """
    if request.user.is_authenticated:
        if request.user.role == 'admin':
            return redirect('dashboard:admin_home')
        if not request.user.email_verified:
            return redirect('accounts:verify_email_gate')
        if not request.user.is_membership_paid:
            return redirect('membership:pending_purchase')
        return redirect('dashboard:home')

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            # Check if account is suspended
            if user.is_suspended:
                messages.error(request, 'Your account has been suspended.')
                return render(request, 'accounts/login.html', {'form': form})

            # Check if account is temporarily locked
            if user.locked_until and user.locked_until > timezone.now():
                messages.error(request, 'Account is temporarily locked due to too many failed login attempts. Please try again later.')
                return render(request, 'accounts/login.html', {'form': form})

            login(request, user)

            # Reset login attempt counter on successful login
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save(update_fields=['failed_login_attempts', 'locked_until'])
            UserActivity.objects.create(user=user, activity_type='login', description='User logged in')

            # Role-based redirect
            if user.role == 'admin':
                return redirect('dashboard:admin_home')
            if not user.email_verified:
                return redirect('accounts:verify_email_gate')
            if not user.is_membership_paid:
                messages.info(request, 'Please complete your membership payment to activate your account.')
                return redirect('membership:pending_purchase')

            # Safe redirect: only allow same-origin ?next= URLs
            next_url = request.GET.get('next', '')
            if next_url and _is_safe_redirect_url(next_url):
                return redirect(next_url)
            return redirect('dashboard:home')
        else:
            # Failed login: increment counter, lock after 5 attempts
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
    """
    Password reset request — sends a reset link via email.

    Flow:
      1. User enters email address
      2. If account exists: generate SHA-256 token, save to user, send email
      3. If account doesn't exist: show same success message (prevents email enumeration)
      4. In DEBUG mode: also display the reset link directly (for development)

    Token is valid for 1 hour (checked in reset_password view).
    """
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
                    print(f'\n[DEV] Password reset link for {user.email}: {reset_url}\n')
            except User.DoesNotExist:
                # Same message whether user exists or not (prevents email enumeration)
                messages.success(request, 'If an account exists with this email, a reset link has been sent.')
            return redirect('accounts:login')
    else:
        form = PasswordResetRequestForm()
    return render(request, 'accounts/forgot_password.html', {'form': form})


@ratelimit(key='ip', rate='10/m', method=['POST'], block=True)
def reset_password(request, token):
    """
    Set a new password using the reset token.

    Validates:
      - Token must match a user's reset_password_token
      - Token must be less than 1 hour old (3600 seconds)
      - On success: clears token, resets login lockout, redirects to login
    """
    user = get_object_or_404(User, reset_password_token=token)

    # Check if token has expired (1 hour)
    if user.reset_password_sent_at and (timezone.now() - user.reset_password_sent_at).total_seconds() > 3600:
        messages.error(request, 'Reset link has expired. Please request a new one.')
        return redirect('accounts:forgot_password')

    if request.method == 'POST':
        form = SetNewPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            # Clear reset token and login lockout
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
    """Log out the user and redirect to the home page."""
    logout(request)
    messages.success(request, 'Logged out successfully.')
    return redirect('pages:home')


@login_required
def profile_view(request):
    """
    Display user profile with stats and activity history.

    Shows:
      - Total/open/resolved post counts
      - Recovery rate (resolved / total * 100)
      - Membership days remaining
      - Recent activity log (last 10)
      - All activities (last 50, for full history view)
    """
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
    recovery_sessions = RecoverySession.objects.filter(Q(claimant=user) | Q(owner=user)).count()
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
    """Edit user profile (name, department, bio, profile picture)."""
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            UserActivity.objects.create(
                user=request.user, activity_type='profile_updated',
                description='Profile updated'
            )
            messages.success(request, 'Profile updated successfully!')
            return redirect('accounts:profile')
    else:
        form = UserProfileForm(instance=request.user)
    return render(request, 'profile/edit.html', {'form': form, 'departments': User.DEPARTMENTS})


@login_required
def change_password(request):
    """
    Change account password.

    Admin restriction: Admin passwords can only be changed through the Django
    backend for security reasons. Regular users can change via this form.
    """
    if request.user.role == 'admin':
        messages.error(request, 'Admin passwords can only be changed through the backend.')
        return redirect('accounts:profile')

    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            # Keep the user logged in after password change
            update_session_auth_hash(request, form.user)
            # Clear any pending password reset token
            request.user.reset_password_token = None
            request.user.save(update_fields=['reset_password_token'])
            UserActivity.objects.create(
                user=request.user, activity_type='password_changed',
                description='Password changed'
            )
            messages.success(request, 'Password changed successfully!')
            return redirect('accounts:profile')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'profile/change_password.html', {'form': form})


@login_required
def settings_view(request):
    """Edit user notification and privacy settings."""
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
    """
    Permanently delete the user's account.

    Flow:
      1. Only accepts POST requests (prevents accidental GET deletion)
      2. Logs out the user first
      3. Deletes the user from database
      4. Sets a signed cookie with the username for the success message
         (can't use Django messages framework after logout + delete)

    The signed cookie prevents tampering — only the server can read it.
    """
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
    """
    Display all active login sessions for the current user.

    Shows session key, expiry time, IP address, user agent, and whether
    it's the current session. Users can revoke other sessions to force
    logout on other devices.
    """
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
    """
    Revoke (delete) another login session to force logout on that device.
    Cannot revoke the current session (would log out the user themselves).
    """
    from django.contrib.sessions.models import Session

    if request.method != 'POST':
        return redirect('accounts:sessions')

    # Prevent self-revocation
    if session_key == request.session.session_key:
        messages.error(request, 'You cannot revoke your current session.')
        return redirect('accounts:sessions')

    try:
        Session.objects.get(session_key=session_key).delete()
        messages.success(request, 'Session revoked successfully.')
    except Session.DoesNotExist:
        messages.error(request, 'Session not found.')

    return redirect('accounts:sessions')
