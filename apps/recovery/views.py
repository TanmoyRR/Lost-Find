from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.accounts.decorators import membership_required
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.db.models import Q
from .models import RecoverySession, RecoveryVerificationLog, RecoveryConfirmation
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
    order = ['pending', 'qr_generated', 'qr_scanned', 'handover_verified', 'completed']
    idx = order.index(session.status) if session.status in order else 0
    flow = [
        ('Claimed', 'bi-person-check'),
        ('QR Generated', 'bi-qr-code'),
        ('QR Scanned', 'bi-qr-code-scan'),
        ('Handover Verified', 'bi-check2-circle'),
        ('Completed', 'bi-flag'),
    ]
    steps = [{'label': label, 'icon': icon, 'done': i < idx or session.status == 'completed'} for i, (label, icon) in enumerate(flow)]
    return render(request, 'recovery/recovery_detail.html', {
        'session': session,
        'steps': steps,
        'sidebar_items': get_sidebar(request.user),
    })

@membership_required
def initiate_recovery(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    if post.user == request.user:
        messages.error(request, 'You cannot claim your own post.')
        return redirect('posts:detail', pk=post_id)
    if RecoverySession.objects.filter(post=post, claimant=request.user, status__in=['pending', 'qr_generated']).exists():
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
    messages.success(request, 'Recovery session initiated. The owner will generate a QR code for verification.')
    return redirect('recovery:detail', uid=session.uid)

@login_required
def generate_qr(request, uid):
    session = get_object_or_404(RecoverySession, uid=uid, owner=request.user)
    if session.status not in ['pending', 'qr_generated']:
        messages.error(request, 'QR code can only be generated while the session is active.')
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