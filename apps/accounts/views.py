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
import uuid
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


def _send_email(subject, template, context, recipient):
    html = render_to_string(template, context)
    plain = strip_tags(html)
    from django.core.mail import send_mail
    from django.conf import settings
    send_mail(subject, plain, settings.DEFAULT_FROM_EMAIL, [recipient], html_message=html)


def _send_verification_email(user):
    token = user.email_verification_token
    verify_url = f'{settings.SITE_URL}/accounts/verify-email/{token}/'
    context = {'user': user, 'verify_url': verify_url, 'site_name': settings.SITE_NAME}
    _send_email(
        subject='Verify your email - IUBAT SmartFind',
        template='accounts/emails/email_verification.html',
        context=context,
        recipient=user.email,
    )


def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = 'student'
            user.email_verification_token = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
            user.save()
            _send_verification_email(user)
            messages.success(request, 'Registration successful! Please check your email to verify your account.')
            return redirect('accounts:login')
    else:
        form = UserRegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})


def user_login(request):
    if request.user.is_authenticated:
        if request.user.role == 'admin':
            return redirect('dashboard:admin_home')
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
            next_url = request.GET.get('next', None)
            if next_url:
                return redirect(next_url)
            if user.role == 'admin':
                return redirect('dashboard:admin_home')
            return redirect('dashboard:home')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})


def verify_email(request, token):
    user = get_object_or_404(User, email_verification_token=token)
    user.email_verified = True
    user.is_verified = True
    user.email_verification_token = None
    user.save()
    messages.success(request, 'Email verified successfully! You can now login.')
    return redirect('accounts:login')


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
                    'Password Reset - IUBAT SmartFind',
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
    user_posts = Post.objects.filter(user=user).order_by('-created_at')
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



