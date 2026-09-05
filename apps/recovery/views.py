import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from django.db import transaction
from django.core.paginator import Paginator
from .models import RecoverySession, RecoveryVerificationLog, generate_short_code
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
    Token is generated right away. No claimant yet (finder is assigned later via accept_match).
    """
    session = RecoverySession.objects.create(
        post=post,
        owner=post.user,
        claimant=None,
        status='token_generated',
    )
    RecoveryVerificationLog.objects.create(
        session=session, action='session_created',
        performed_by=post.user,
        details={'post_id': post.id, 'post_title': post.title},
    )
    logger.info('Recovery session %s created for lost post %s', session.short_code, post.pk)
    return session


def create_finder_recovery_session(post):
    """
    Create a RecoverySession when a Found Post is created.
    The finder (post creator) is set as claimant, ready to enter the owner's token.
    """
    session = RecoverySession.objects.create(
        post=post,
        owner=post.user,
        claimant=post.user,
        status='token_generated',
    )
    RecoveryVerificationLog.objects.create(
        session=session, action='session_created',
        performed_by=post.user,
        details={'post_id': post.id, 'post_title': post.title, 'role': 'finder'},
    )
    logger.info('Finder recovery session %s created for found post %s', session.short_code, post.pk)
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

    step_order = ['pending', 'token_generated', 'token_entered', 'completed']
    try:
        idx = step_order.index(session.status)
    except ValueError:
        idx = 0
    steps = [
        {'label': 'Token Ready', 'icon': 'bi-key', 'done': idx >= 1 or session.status == 'completed'},
        {'label': 'Token Entered', 'icon': 'bi-check2-square', 'done': idx >= 2 or session.status == 'completed'},
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
def regenerate_token(request, short_code):
    if request.method != 'POST':
        return redirect('recovery:detail', short_code=short_code)
    session = get_object_or_404(RecoverySession, short_code=short_code, owner=request.user)
    if session.status not in ('pending', 'token_generated'):
        messages.error(request, 'Token can only be regenerated while the session is active.')
        return redirect('recovery:detail', short_code=short_code)
    new_code = generate_short_code()
    while RecoverySession.objects.filter(short_code=new_code).exists():
        new_code = generate_short_code()
    session.short_code = new_code
    session.status = 'token_generated'
    session.save(update_fields=['short_code', 'status'])
    RecoveryVerificationLog.objects.create(
        session=session, action='token_regenerated',
        performed_by=request.user,
        ip_address=request.META.get('REMOTE_ADDR'),
    )
    messages.success(request, 'Recovery token regenerated successfully.')
    return redirect('recovery:detail', short_code=short_code)


@login_required
def enter_token(request, short_code):
    session = get_object_or_404(
        RecoverySession.objects.select_related('post', 'claimant', 'owner'),
        short_code=short_code,
    )
    if request.user != session.claimant:
        messages.error(request, 'Only the authorized finder can complete this recovery.')
        return redirect('recovery:list')
    if session.status != 'token_generated':
        messages.error(request, 'This recovery session is no longer active.')
        return redirect('recovery:detail', short_code=short_code)

    if request.method == 'POST':
        token = (request.POST.get('short_code', '') or '').strip().upper()

        if not token:
            messages.error(request, 'Please enter the owner\'s recovery token.')
            return render(request, 'recovery/enter_token.html', {'session': session, 'sidebar_items': _get_sidebar(request.user)})

        owner_session = RecoverySession.objects.filter(
            short_code=token, status='token_generated',
        ).exclude(pk=session.pk).select_related('post', 'owner').first()

        if not owner_session:
            messages.error(request, 'Invalid or inactive token. Please check the code and try again.')
            return render(request, 'recovery/enter_token.html', {'session': session, 'sidebar_items': _get_sidebar(request.user)})

        with transaction.atomic():
            session.claimant = request.user
            session.status = 'completed'
            session.token_verified_at = timezone.now()
            session.completed_at = timezone.now()
            session.save(update_fields=['claimant', 'status', 'token_verified_at', 'completed_at'])

            owner_session.claimant = request.user
            owner_session.status = 'completed'
            owner_session.token_verified_at = timezone.now()
            owner_session.completed_at = timezone.now()
            owner_session.save(update_fields=['claimant', 'status', 'token_verified_at', 'completed_at'])

            for p in [session.post, owner_session.post]:
                p.status = 'resolved'
                p.is_resolved = True
                p.save(update_fields=['status', 'is_resolved'])

            RecoveryVerificationLog.objects.create(
                session=session, action='recovery_completed',
                performed_by=request.user,
                details={'matched_with': owner_session.short_code},
            )
            RecoveryVerificationLog.objects.create(
                session=owner_session, action='recovery_completed',
                performed_by=request.user,
                details={'matched_with': session.short_code},
            )

            if owner_session.owner != request.user:
                Notification.objects.create(
                    user=owner_session.owner,
                    notification_type='post_resolved',
                    title='Item Successfully Recovered',
                    message=f'Your item "{owner_session.post.title}" has been successfully recovered.',
                    link='/recovery/',
                )
            if session.owner != request.user:
                Notification.objects.create(
                    user=session.owner,
                    notification_type='post_resolved',
                    title='Item Successfully Recovered',
                    message=f'Your found item "{session.post.title}" has been matched and recovered.',
                    link='/recovery/',
                )

        messages.success(request, 'Recovery completed successfully! Both items marked as resolved.')
        return redirect('recovery:detail', short_code=short_code)

    return render(request, 'recovery/enter_token.html', {
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
    other_user = session.owner if request.user == session.claimant else session.claimant
    if other_user:
        Notification.objects.create(
            user=other_user,
            notification_type='recovery_update',
            title='Recovery Session Cancelled',
            message=f'The recovery session for "{session.post.title}" has been cancelled.',
            link='/recovery/',
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
