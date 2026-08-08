import random
import io
import base64
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.accounts.decorators import membership_required
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from .models import RecoverySession, RecoveryOTP, RecoveryVerificationLog, RecoveryConfirmation
from apps.posts.models import Post
from apps.accounts.models import User, UserActivity
from apps.notifications.models import Notification

SIDEBAR_ITEMS = [
    {'name': 'Dashboard', 'url': 'dashboard:home', 'icon': 'bi-grid'},
    {'name': 'My Posts', 'url': 'dashboard:my_posts', 'icon': 'bi-file-text'},
    {'name': 'Recovery Sessions', 'url': 'recovery:list', 'icon': 'bi-shield-check'},
    {'name': 'Notifications', 'url': 'dashboard:notifications', 'icon': 'bi-bell'},
    {'name': 'Profile', 'url': 'dashboard:profile', 'icon': 'bi-person'},
    {'name': 'Settings', 'url': 'dashboard:settings', 'icon': 'bi-gear'},
]

ADMIN_SIDEBAR = [
    {'name': 'Dashboard', 'url': 'dashboard:admin_home', 'icon': 'bi-speedometer2'},
    {'name': 'Users', 'url': 'dashboard:admin_users', 'icon': 'bi-people'},
    {'name': 'Posts', 'url': 'dashboard:admin_posts', 'icon': 'bi-file-text'},
    {'name': 'Categories', 'url': 'dashboard:admin_categories', 'icon': 'bi-tags'},
    {'name': 'Locations', 'url': 'dashboard:admin_locations', 'icon': 'bi-geo-alt'},
    {'name': 'Payments', 'url': 'dashboard:admin_payments', 'icon': 'bi-credit-card'},
    {'name': 'Reports', 'url': 'dashboard:admin_reports', 'icon': 'bi-bar-chart'},
    {'name': 'Analytics', 'url': 'dashboard:admin_analytics', 'icon': 'bi-graph-up'},
    {'name': 'Recovery Sessions', 'url': 'recovery:admin_list', 'icon': 'bi-shield-check'},
    {'name': 'Settings', 'url': 'dashboard:admin_settings', 'icon': 'bi-gear'},
]

def get_sidebar(user):
    if user.role == 'admin':
        return ADMIN_SIDEBAR
    return [
        {'name': 'Dashboard', 'url': 'dashboard:home', 'icon': 'bi-grid'},
        {'name': 'My Posts', 'url': 'dashboard:my_posts', 'icon': 'bi-file-text'},
        {'name': 'Recovery Sessions', 'url': 'recovery:list', 'icon': 'bi-shield-check'},
        {'name': 'Notifications', 'url': 'dashboard:notifications', 'icon': 'bi-bell'},
        {'name': 'Profile', 'url': 'dashboard:profile', 'icon': 'bi-person'},
        {'name': 'Settings', 'url': 'dashboard:settings', 'icon': 'bi-gear'},
]

@login_required
def recovery_list(request):
    sessions = RecoverySession.objects.filter(
        Q(claimant=request.user) | Q(owner=request.user)
    ).select_related('post', 'claimant', 'owner').order_by('-created_at')
    return render(request, 'recovery/recovery_list.html', {
        'sessions': sessions,
        'sidebar_items': get_sidebar(request.user),
    })

@login_required
def recovery_detail(request, uid):
    session = get_object_or_404(RecoverySession, uid=uid)
    if request.user not in [session.claimant, session.owner]:
        messages.error(request, 'You do not have access to this recovery session.')
        return redirect('recovery:list')
    return render(request, 'recovery/recovery_detail.html', {
        'session': session,
        'sidebar_items': get_sidebar(request.user),
    })

@membership_required
def initiate_recovery(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    if post.user == request.user:
        messages.error(request, 'You cannot claim your own post.')
        return redirect('posts:detail', pk=post_id)
    if RecoverySession.objects.filter(post=post, claimant=request.user, status__in=['pending', 'otp_sent', 'otp_verified', 'qr_generated']).exists():
        messages.warning(request, 'You already have an active recovery session for this item.')
        return redirect('recovery:list')
    session = RecoverySession.objects.create(
        post=post,
        claimant=request.user,
        owner=post.user,
        status='pending'
    )
    RecoveryVerificationLog.objects.create(
        session=session, action='initiated',
        performed_by=request.user,
        details={'post_id': post.id, 'post_title': post.title}
    )
    Notification.objects.create(
        user=post.user,
        notification_type='post_claimed',
        title='Recovery Session Initiated',
        message=f'{request.user.get_full_name() or request.user.username} has initiated a recovery session for your item: {post.title}',
        link=f'/recovery/{session.uid}/',
    )
    messages.success(request, 'Recovery session initiated. Please verify your identity.')
    return redirect('recovery:detail', uid=session.uid)

@login_required
def send_otp(request, uid):
    session = get_object_or_404(RecoverySession, uid=uid, claimant=request.user)
    if session.status not in ['pending', 'otp_sent']:
        messages.error(request, 'Invalid session state for OTP request.')
        return redirect('recovery:detail', uid=uid)
    otp_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    otp = RecoveryOTP.objects.create(
        session=session,
        otp_code=otp_code,
        expires_at=timezone.now() + timezone.timedelta(minutes=10)
    )
    session.status = 'otp_sent'
    session.save(update_fields=['status'])
    RecoveryVerificationLog.objects.create(
        session=session, action='otp_sent',
        performed_by=request.user,
        details={'otp_id': otp.id},
        ip_address=request.META.get('REMOTE_ADDR')
    )
    try:
        send_mail(
            subject='Your Lost & Found Recovery OTP',
            message=f'Your OTP for item recovery is: {otp_code}\n\nThis code expires in 10 minutes.\n\nIf you did not request this, please ignore this email.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[request.user.email],
            fail_silently=False,
        )
    except Exception:
        pass
    messages.success(request, 'OTP sent to your email.')
    return redirect('recovery:detail', uid=uid)

@login_required
@require_POST
def verify_otp(request, uid):
    session = get_object_or_404(RecoverySession, uid=uid, claimant=request.user)
    otp_code = request.POST.get('otp_code', '').strip()
    if not otp_code:
        messages.error(request, 'Please enter the OTP code.')
        return redirect('recovery:detail', uid=uid)
    otp = RecoveryOTP.objects.filter(session=session, is_used=False).order_by('-created_at').first()
    if not otp:
        messages.error(request, 'No valid OTP found. Please request a new one.')
        return redirect('recovery:detail', uid=uid)
    success, message = otp.verify(otp_code)
    if success:
        RecoveryVerificationLog.objects.create(
            session=session, action='otp_verified',
            performed_by=request.user,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        messages.success(request, message)
    else:
        messages.error(request, message)
    return redirect('recovery:detail', uid=uid)

@login_required
def generate_qr(request, uid):
    session = get_object_or_404(RecoverySession, uid=uid, owner=request.user)
    if session.status != 'otp_verified':
        messages.error(request, 'OTP must be verified before generating QR code.')
        return redirect('recovery:detail', uid=uid)
    token = session.generate_qr_token()
    import qrcode
    from io import BytesIO
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(token)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    from django.core.files.base import ContentFile
    session.qr_code.save(f'qr_{session.uid}.png', ContentFile(buffer.getvalue()), save=False)
    session.status = 'qr_generated'
    session.save(update_fields=['qr_code', 'status'])
    RecoveryVerificationLog.objects.create(
        session=session, action='qr_generated',
        performed_by=request.user,
        ip_address=request.META.get('REMOTE_ADDR')
    )
    messages.success(request, 'QR code generated successfully.')
    return redirect('recovery:detail', uid=uid)

@login_required
def scan_qr(request, uid):
    session = get_object_or_404(RecoverySession, uid=uid)
    if request.user not in [session.claimant, session.owner]:
        messages.error(request, 'Access denied.')
        return redirect('recovery:list')
    if request.method == 'POST':
        token = request.POST.get('qr_token', '')
        if session.verify_qr_token(token):
            session.status = 'qr_scanned'
            session.qr_scanned_at = timezone.now()
            session.save(update_fields=['status', 'qr_scanned_at'])
            RecoveryVerificationLog.objects.create(
                session=session, action='qr_scanned',
                performed_by=request.user,
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, 'QR code verified successfully.')
        else:
            messages.error(request, 'Invalid or expired QR code.')
        return redirect('recovery:detail', uid=uid)
    return render(request, 'recovery/scan_qr.html', {'session': session, 'sidebar_items': get_sidebar(request.user)})

@login_required
def verify_handover(request, uid):
    session = get_object_or_404(RecoverySession, uid=uid, owner=request.user)
    if session.status != 'qr_scanned':
        messages.error(request, 'QR code must be scanned before handover verification.')
        return redirect('recovery:detail', uid=uid)
    session.status = 'handover_verified'
    session.handover_verified_at = timezone.now()
    session.save(update_fields=['status', 'handover_verified_at'])
    RecoveryVerificationLog.objects.create(
        session=session, action='handover_verified',
        performed_by=request.user,
        ip_address=request.META.get('REMOTE_ADDR')
    )
    messages.success(request, 'Handover verified successfully.')
    return redirect('recovery:detail', uid=uid)

@login_required
def confirm_recovery(request, uid):
    session = get_object_or_404(RecoverySession, uid=uid)
    if request.user not in [session.claimant, session.owner]:
        messages.error(request, 'Access denied.')
        return redirect('recovery:list')
    if session.status != 'handover_verified':
        messages.error(request, 'Handover must be verified before confirmation.')
        return redirect('recovery:detail', uid=uid)
    confirmation, created = RecoveryConfirmation.objects.get_or_create(session=session)
    if request.user == session.owner:
        confirmation.confirmed_by_owner = True
        confirmation.owner_confirmed_at = timezone.now()
    elif request.user == session.claimant:
        confirmation.confirmed_by_claimant = True
        confirmation.claimant_confirmed_at = timezone.now()
    confirmation.save()
    if confirmation.is_complete():
        session.status = 'completed'
        session.completed_at = timezone.now()
        session.save(update_fields=['status', 'completed_at'])
        session.post.status = 'resolved'
        session.post.is_resolved = True
        session.post.save(update_fields=['status', 'is_resolved'])
        RecoveryVerificationLog.objects.create(
            session=session, action='recovery_completed',
            performed_by=request.user,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        Notification.objects.create(
            user=session.owner,
            notification_type='post_resolved',
            title='Item Successfully Recovered',
            message=f'Your item "{session.post.title}" has been successfully recovered and handed over.',
            link=f'/recovery/{session.uid}/',
        )
        Notification.objects.create(
            user=session.claimant,
            notification_type='post_resolved',
            title='Recovery Completed',
            message=f'You have successfully completed the recovery of "{session.post.title}".',
            link=f'/recovery/{session.uid}/',
        )
        messages.success(request, 'Recovery completed successfully!')
    else:
        messages.success(request, 'Confirmation recorded. Waiting for the other party.')
    return redirect('recovery:detail', uid=uid)

@login_required
def cancel_recovery(request, uid):
    session = get_object_or_404(RecoverySession, uid=uid)
    if request.user not in [session.claimant, session.owner]:
        messages.error(request, 'Access denied.')
        return redirect('recovery:list')
    if session.status in ['completed', 'expired', 'cancelled']:
        messages.error(request, 'Session cannot be cancelled.')
        return redirect('recovery:detail', uid=uid)
    session.status = 'cancelled'
    session.save(update_fields=['status'])
    RecoveryVerificationLog.objects.create(
        session=session, action='cancelled',
        performed_by=request.user,
        details={'reason': request.POST.get('reason', '')},
        ip_address=request.META.get('REMOTE_ADDR')
    )
    messages.success(request, 'Recovery session cancelled.')
    return redirect('recovery:list')

@login_required
def recovery_admin_list(request):
    if not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    sessions = RecoverySession.objects.all().select_related('post', 'claimant', 'owner').order_by('-created_at')
    return render(request, 'recovery/admin_list.html', {
        'sessions': sessions,
        'sidebar_items': ADMIN_SIDEBAR,
    })