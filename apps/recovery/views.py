import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from django.core.paginator import Paginator
from .models import RecoverySession, RecoveryVerificationLog
from apps.posts.models import Post
from apps.notifications.models import Notification

logger = logging.getLogger(__name__)

ADMIN_SIDEBAR = [
    {'url_name': 'dashboard:admin_home', 'label': 'Dashboard', 'icon': 'bi-speedometer2'},
    {'url_name': 'dashboard:admin_users', 'label': 'Users', 'icon': 'bi-people'},
    {'url_name': 'dashboard:admin_posts', 'label': 'Posts', 'icon': 'bi-file-text'},
    {'url_name': 'dashboard:admin_categories', 'label': 'Categories', 'icon': 'bi-tags'},
    {'url_name': 'dashboard:admin_locations', 'label': 'Locations', 'icon': 'bi-geo-alt'},
    {'url_name': 'dashboard:admin_revenue', 'label': 'Revenue', 'icon': 'bi-currency-dollar'},
    {'url_name': 'dashboard:admin_reports', 'label': 'Reports', 'icon': 'bi-bar-chart'},
    {'url_name': 'dashboard:admin_analytics', 'label': 'Analytics', 'icon': 'bi-graph-up'},
    {'url_name': 'recovery:admin_list', 'label': 'Recovery Sessions', 'icon': 'bi-shield-check'},
    {'url_name': 'dashboard:admin_settings', 'label': 'Settings', 'icon': 'bi-gear'},
]

MEMBER_SIDEBAR = [
    {'url_name': 'dashboard:home', 'label': 'Dashboard', 'icon': 'bi-grid'},
    {'url_name': 'posts:my_posts', 'label': 'My Posts', 'icon': 'bi-file-text'},
    {'url_name': 'recovery:list', 'label': 'Recovery Sessions', 'icon': 'bi-shield-check'},
    {'url_name': 'notifications:list', 'label': 'Notifications', 'icon': 'bi-bell'},
    {'url_name': 'accounts:profile', 'label': 'Profile', 'icon': 'bi-person'},
    {'url_name': 'accounts:settings', 'label': 'Settings', 'icon': 'bi-gear'},
]


def _get_sidebar(user):
    if user.role == 'admin' or user.is_staff or user.is_superuser:
        return ADMIN_SIDEBAR
    return MEMBER_SIDEBAR


def create_recovery_session_for_post(post):
    """
    Create a RecoverySession immediately when a Lost Post is created.
    QR is generated right away. No claimant yet (finder is assigned later via accept_match).
    """
    session = RecoverySession.objects.create(
        post=post,
        owner=post.user,
        claimant=None,
        status='qr_generated',
    )
    session.generate_qr_image()
    session.save(update_fields=['qr_code'])
    RecoveryVerificationLog.objects.create(
        session=session, action='session_created',
        performed_by=post.user,
        details={'post_id': post.id, 'post_title': post.title},
    )
    logger.info('Recovery session %s created for lost post %s', session.short_code, post.pk)
    return session


@login_required
def recovery_list(request):
    sessions = RecoverySession.objects.filter(
        Q(claimant=request.user) | Q(owner=request.user)
    ).select_related('post', 'post__category', 'claimant', 'owner').order_by('-created_at')
    return render(request, 'recovery/recovery_list.html', {
        'sessions': sessions,
        'sidebar_items': _get_sidebar(request.user),
    })


@login_required
def recovery_detail(request, short_code):
    session = get_object_or_404(
        RecoverySession.objects.select_related('post', 'post__category', 'claimant', 'owner'),
        short_code=short_code,
    )
    if request.user not in [session.claimant, session.owner]:
        messages.error(request, 'You do not have access to this recovery session.')
        return redirect('recovery:list')

    is_owner = request.user == session.owner
    is_finder = request.user == session.claimant

    step_order = ['pending', 'qr_generated', 'qr_scanned', 'completed']
    try:
        idx = step_order.index(session.status)
    except ValueError:
        idx = 0
    steps = [
        {'label': 'QR Generated', 'icon': 'bi-qr-code', 'done': idx >= 1 or session.status == 'completed'},
        {'label': 'QR Scanned', 'icon': 'bi-qr-code-scan', 'done': idx >= 2 or session.status == 'completed'},
        {'label': 'Completed', 'icon': 'bi-flag', 'done': session.status == 'completed'},
    ]

    return render(request, 'recovery/recovery_detail.html', {
        'session': session,
        'steps': steps,
        'is_owner': is_owner,
        'is_finder': is_finder,
        'sidebar_items': _get_sidebar(request.user),
    })


@login_required
def generate_qr(request, short_code):
    if request.method != 'POST':
        return redirect('recovery:detail', short_code=short_code)
    session = get_object_or_404(RecoverySession, short_code=short_code, owner=request.user)
    if session.status not in ('pending', 'qr_generated'):
        messages.error(request, 'QR code can only be generated while the session is active.')
        return redirect('recovery:detail', short_code=short_code)
    session.generate_qr_image()
    session.status = 'qr_generated'
    session.save(update_fields=['qr_code', 'status'])
    RecoveryVerificationLog.objects.create(
        session=session, action='qr_generated',
        performed_by=request.user,
        ip_address=request.META.get('REMOTE_ADDR'),
    )
    messages.success(request, 'QR code generated successfully.')
    return redirect('recovery:detail', short_code=short_code)


@login_required
def scan_qr(request, short_code):
    session = get_object_or_404(
        RecoverySession.objects.select_related('post', 'claimant', 'owner'),
        short_code=short_code,
    )
    if request.user != session.claimant:
        messages.error(request, 'Only the authorized finder can scan this QR code.')
        return redirect('recovery:list')
    if session.status != 'qr_generated':
        messages.error(request, 'This QR code is no longer active.')
        return redirect('recovery:detail', short_code=short_code)

    if request.method == 'POST':
        token = request.POST.get('short_code', '').strip()
        success, msg = session.verify_and_complete(token, request.user)
        if success:
            messages.success(request, msg)
        else:
            messages.error(request, msg)
        return redirect('recovery:detail', short_code=short_code)

    return render(request, 'recovery/scan_qr.html', {
        'session': session,
        'sidebar_items': _get_sidebar(request.user),
    })


@login_required
def cancel_recovery(request, short_code):
    if request.method != 'POST':
        return redirect('recovery:detail', short_code=short_code)
    session = get_object_or_404(RecoverySession, short_code=short_code)
    if request.user not in [session.claimant, session.owner]:
        messages.error(request, 'Access denied.')
        return redirect('recovery:list')
    if session.status in ('completed', 'expired', 'cancelled'):
        messages.error(request, 'Session cannot be cancelled.')
        return redirect('recovery:detail', short_code=short_code)
    session.status = 'cancelled'
    session.save(update_fields=['status'])
    RecoveryVerificationLog.objects.create(
        session=session, action='cancelled',
        performed_by=request.user,
        details={'reason': request.POST.get('reason', '')},
        ip_address=request.META.get('REMOTE_ADDR'),
    )
    messages.success(request, 'Recovery session cancelled.')
    return redirect('recovery:list')


@login_required
def recovery_admin_list(request):
    if not (request.user.role == 'admin' or request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'Access denied.')
        return redirect('dashboard:home')
    sessions = RecoverySession.objects.all().select_related(
        'post', 'claimant', 'owner'
    ).order_by('-created_at')
    paginator = Paginator(sessions, 20)
    page = request.GET.get('page', 1)
    sessions_page = paginator.get_page(page)
    return render(request, 'recovery/admin_list.html', {
        'sessions': sessions_page,
        'sidebar_items': ADMIN_SIDEBAR,
    })
