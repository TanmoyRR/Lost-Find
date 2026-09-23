"""
Recovery Views — Token-based item recovery verification system.

This module implements the core recovery workflow that proves item ownership:

  Recovery Flow (SINGLE session per match):
    1. Lost post created (NO auto-session) / Found post created
    2. First person to message creates ONE RecoverySession with a unique
       short code (token), e.g. "LF-T2FJBL"
    3. Second person messaging reuses the same session (never creates a second)
    4. Owner (lost-item person) shares their token with the finder
    5. Finder enters the token on the "Enter Token" page
    6. Token verified (entered == session.short_code) → session completed,
       both posts resolved → recovery complete

  Roles:
    - owner: The person who lost the item (session.owner, shares the token)
    - claimant: The person who found it (session.claimant, enters the token)

  Session statuses:
    - pending: Session created, no token generated yet
    - token_generated: Token ready to be shared (default for new sessions)
    - token_entered: Finder has entered a token (intermediate state)
    - completed: Token verified, item recovered
    - expired: Session older than 30 days, auto-expired
    - cancelled: Cancelled by user or admin

  Admin capabilities:
    - View all recovery sessions
    - Force-complete or force-cancel any session
    - Reassign the claimant (finder) to a different user
"""

import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from django.db import transaction
from django.core.paginator import Paginator
from django_ratelimit.decorators import ratelimit
from .models import RecoverySession, RecoveryVerificationLog, generate_short_code
from apps.posts.models import Post
from apps.notifications.models import Notification
from apps.accounts.decorators import is_admin

logger = logging.getLogger(__name__)

# Sidebar navigation items for admin and member views
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
    """Return the appropriate sidebar navigation based on user role."""
    if is_admin(user):
        return ADMIN_SIDEBAR
    return MEMBER_SIDEBAR


def _resolve_counterpart_post(session):
    """
    Find the counterpart (opposite-type) post for a single-session recovery.

    For a lost-post session: counterpart is the claimant's (finder's) found post.
    For a found-post session: counterpart is the owner's (lost-item person's) lost post.
    Returns None if no counterpart found.
    """
    if session.post.post_type == 'lost':
        other_user = session.claimant
        opposite_type = 'found'
    else:
        other_user = session.owner
        opposite_type = 'lost'

    if not other_user:
        return None

    return Post.objects.filter(
        user=other_user,
        post_type=opposite_type,
        status__in=['open', 'claimed'],
    ).order_by('-created_at').first()


@login_required
def recovery_list(request):
    """
    Display all recovery sessions where the user is either the owner or the claimant.
    Shows sessions from both sides of the recovery process.
    """
    sessions = RecoverySession.objects.filter(
        Q(claimant=request.user) | Q(owner=request.user)
    ).select_related('post', 'post__category', 'claimant', 'owner').order_by('-created_at')
    return render(request, 'recovery/recovery_list.html', {
        'sessions': sessions,
        'sidebar_items': _get_sidebar(request.user),
    })


@login_required
def recovery_detail(request, pk):
    """
    Display detailed view of a single recovery session.

    Role resolution (single session):
      - owner: session.owner (lost-item person, shares the token)
      - claimant: session.claimant (finder, enters the token)
      - is_owner: True if viewer is the owner
      - is_finder: True if viewer is the claimant

    Also builds a progress stepper (Token Ready → Token Entered → Completed).
    """
    session = get_object_or_404(
        RecoverySession.objects.select_related('post', 'post__category', 'claimant', 'owner'),
        pk=pk,
    )

    # Access control: only owner or claimant can view
    if request.user not in [session.claimant, session.owner]:
        messages.error(request, 'You do not have access to this recovery session.')
        return redirect('recovery:list')

    actual_owner = session.owner
    actual_finder = session.claimant
    is_owner = request.user == session.owner
    is_finder = request.user == session.claimant

    # Build progress stepper based on session status
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
        'actual_owner': actual_owner,
        'actual_finder': actual_finder,
        'sidebar_items': _get_sidebar(request.user),
    })


@login_required
def regenerate_token(request, pk):
    """
    Generate a new recovery token for an active session.

    Only the session owner can do this. Useful if the old token was
    compromised or shared with the wrong person. The old token is
    immediately invalidated.
    """
    if request.method != 'POST':
        return redirect('recovery:detail', pk=pk)

    session = get_object_or_404(RecoverySession, pk=pk, owner=request.user)

    if session.status not in ('pending', 'token_generated'):
        messages.error(request, 'Token can only be regenerated while the session is active.')
        return redirect('recovery:detail', pk=pk)

    # Generate a unique new token
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
    return redirect('recovery:detail', pk=session.pk)


@login_required
@ratelimit(key='ip', rate='10/m', method='POST', block=True)
def enter_token(request, pk):
    """
    Finder enters the owner's recovery token to complete recovery.

    SINGLE-SESSION verification:
      1. Only the claimant (finder) can access this page
      2. The finder enters the owner's recovery token
      3. The system validates entered token == session.short_code (this session's own token)
      4. On success (inside an atomic transaction):
         - Session marked as 'completed'
         - This session's post marked as 'resolved'
         - Counterpart post (other user's opposite-type post) resolved and linked
         - Notifications sent to both parties

    Rate limited: 10 attempts per minute per IP (brute-force protection).
    """
    session = get_object_or_404(
        RecoverySession.objects.select_related('post', 'claimant', 'owner'),
        pk=pk,
    )

    # Only the assigned finder (claimant) can enter the token
    if request.user != session.claimant:
        messages.error(request, 'Only the authorized finder can complete this recovery.')
        return redirect('recovery:list')

    # Session must be in 'token_generated' state
    if session.status != 'token_generated':
        messages.error(request, 'This recovery session is no longer active.')
        return redirect('recovery:detail', pk=pk)

    if request.method == 'POST':
        token = (request.POST.get('short_code', '') or '').strip().upper()

        if not token:
            messages.error(request, 'Please enter the owner\'s recovery token.')
            return render(request, 'recovery/enter_token.html', {
                'session': session, 'sidebar_items': _get_sidebar(request.user)
            })

        # SINGLE-SESSION verification: entered token must match THIS session's short_code
        if token != session.short_code:
            messages.error(request, 'Invalid token. Please check the code and try again.')
            return render(request, 'recovery/enter_token.html', {
                'session': session, 'sidebar_items': _get_sidebar(request.user)
            })

        # Atomically complete session and resolve posts
        with transaction.atomic():
            # Complete this session
            session.status = 'completed'
            session.token_verified_at = timezone.now()
            session.completed_at = timezone.now()
            session.save(update_fields=['status', 'token_verified_at', 'completed_at'])

            # Resolve this session's post
            session.post.status = 'resolved'
            session.post.save(update_fields=['status'])

            # Find and resolve counterpart post (other user's opposite-type post)
            counterpart = _resolve_counterpart_post(session)
            if counterpart and counterpart.status != 'resolved':
                counterpart.status = 'resolved'
                counterpart.matched_post = session.post
                counterpart.save(update_fields=['status', 'matched_post'])
                # Link session's post to counterpart
                session.post.matched_post = counterpart
                session.post.save(update_fields=['matched_post'])

            # Log the completion
            RecoveryVerificationLog.objects.create(
                session=session, action='recovery_completed',
                performed_by=request.user,
                details={'counterpart_post_id': counterpart.pk if counterpart else None},
            )

            # Notify both parties
            if session.owner != request.user:
                Notification.objects.create(
                    user=session.owner,
                    notification_type='post_resolved',
                    title='Item Successfully Recovered',
                    message=f'Your item "{session.post.title}" has been successfully recovered.',
                    link=reverse('recovery:list'),
                )
            if counterpart and counterpart.user != request.user:
                Notification.objects.create(
                    user=counterpart.user,
                    notification_type='post_resolved',
                    title='Item Successfully Recovered',
                    message=f'Your item "{counterpart.title}" has been matched and recovered.',
                    link=reverse('recovery:list'),
                )

        messages.success(request, 'Recovery completed successfully! Items marked as resolved.')
        return redirect('recovery:detail', pk=pk)

    return render(request, 'recovery/enter_token.html', {
        'session': session,
        'sidebar_items': _get_sidebar(request.user),
    })


@login_required
def cancel_recovery(request, pk):
    """
    Cancel an active recovery session. Only the owner (lost-item person) can cancel.
    Sends a notification to the claimant about the cancellation.
    """
    if request.method != 'POST':
        return redirect('recovery:detail', pk=pk)

    session = get_object_or_404(RecoverySession, pk=pk)

    if request.user != session.owner:
        messages.error(request, 'Only the session owner can cancel this recovery.')
        return redirect('recovery:list')

    if session.status in ('completed', 'expired', 'cancelled'):
        messages.error(request, 'Session cannot be cancelled.')
        return redirect('recovery:detail', pk=pk)

    session.status = 'cancelled'
    session.save(update_fields=['status'])

    RecoveryVerificationLog.objects.create(
        session=session, action='cancelled',
        performed_by=request.user,
        details={'reason': request.POST.get('reason', '')},
        ip_address=request.META.get('REMOTE_ADDR'),
    )

    # Notify the claimant
    other_user = session.claimant
    if other_user:
        Notification.objects.create(
            user=other_user,
            notification_type='recovery_update',
            title='Recovery Session Cancelled',
            message=f'The recovery session for "{session.post.title}" has been cancelled.',
            link=reverse('recovery:list'),
        )

    messages.success(request, 'Recovery session cancelled.')
    return redirect('recovery:list')


# ──────────────────────────────────────────────
# Admin-only recovery management views
# ──────────────────────────────────────────────

@user_passes_test(is_admin)
def recovery_admin_list(request):
    """Admin view: list all recovery sessions with pagination."""
    sessions = RecoverySession.objects.all().select_related(
        'post', 'claimant', 'owner'
    ).order_by('-created_at')

    paginator = Paginator(sessions, 20)
    page = request.GET.get('page', 1)
    sessions_page = paginator.get_page(page)

    return render(request, 'recovery/admin_list.html', {
        'sessions': sessions_page,
    })


@login_required
@user_passes_test(is_admin)
def admin_force_complete(request, short_code):
    """
    Admin action: force-complete a recovery session.

    Used when the normal token verification flow is stuck or the parties
    have resolved the issue offline. Also resolves the paired session
    if one exists.
    """
    session = get_object_or_404(RecoverySession, short_code=short_code)

    if request.method != 'POST':
        return redirect('recovery:admin_list')

    session.status = 'completed'
    from django.utils import timezone as tz
    session.completed_at = tz.now()
    session.save(update_fields=['status', 'completed_at'])

    RecoveryVerificationLog.objects.create(
        session=session, action='admin_force_completed',
        performed_by=request.user,
        details={'reason': 'Admin intervention'},
    )

    # Also resolve the post
    session.post.status = 'resolved'
    session.post.save(update_fields=['status'])

    messages.success(request, f'Recovery session {session.short_code} force-completed.')
    return redirect('recovery:admin_list')


@login_required
@user_passes_test(is_admin)
def admin_force_cancel(request, short_code):
    """Admin action: force-cancel a recovery session."""
    session = get_object_or_404(RecoverySession, short_code=short_code)

    if request.method != 'POST':
        return redirect('recovery:admin_list')

    session.status = 'cancelled'
    session.save(update_fields=['status'])

    RecoveryVerificationLog.objects.create(
        session=session, action='admin_force_cancelled',
        performed_by=request.user,
        details={'reason': 'Admin intervention'},
    )

    messages.success(request, f'Recovery session {session.short_code} cancelled.')
    return redirect('recovery:admin_list')


@login_required
@user_passes_test(is_admin)
def admin_reassign_claimant(request, short_code):
    """
    Admin action: reassign the claimant (finder) of a recovery session.

    Used when the wrong person was assigned as finder, or when the
    finder's account is inactive/deleted.
    """
    session = get_object_or_404(RecoverySession, short_code=short_code)

    if request.method != 'POST':
        return redirect('recovery:admin_list')

    new_claimant_id = request.POST.get('claimant_id')
    if new_claimant_id:
        from apps.accounts.models import User
        new_claimant = get_object_or_404(User, pk=new_claimant_id)
        session.claimant = new_claimant
        session.save(update_fields=['claimant'])

        RecoveryVerificationLog.objects.create(
            session=session, action='admin_claimant_reassigned',
            performed_by=request.user,
            details={'new_claimant_id': new_claimant.pk},
        )
        messages.success(request, f'Claimant reassigned to {new_claimant.username}.')
    else:
        messages.error(request, 'No claimant specified.')

    return redirect('recovery:admin_list')
