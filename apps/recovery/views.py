"""
Recovery Views — Token-based item recovery verification system.

This module implements the core recovery workflow that proves item ownership:

  Recovery Flow (for a Lost post):
    1. Owner creates a lost post → a RecoverySession is auto-created with a
       unique short code (token), e.g. "LF-T2FJBL"
    2. Finder finds the item → starts a conversation → recovery session is linked
    3. Owner shares their token with the finder (in person or via chat)
    4. Finder enters the token on the "Enter Token" page
    5. Token is verified → both posts marked as 'resolved' → recovery complete

  For Found posts:
    - The roles are reversed: the found-post creator is the "finder" and the
      person who lost the item is the "owner"
    - The owner enters the finder's token to prove ownership

  Session statuses:
    - pending: Session created, no token generated yet
    - token_generated: Token ready to be shared (default for new lost posts)
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


def create_recovery_session_for_post(post):
    """
    Create a RecoverySession immediately when a Lost Post is created.

    Called from posts/views.py create_post(). The token (short_code) is generated
    right away so the owner can share it with the finder. No claimant is assigned
    yet — that happens later when the finder starts a conversation or AI matching
    assigns them.
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
def recovery_detail(request, short_code):
    """
    Display detailed view of a single recovery session.

    Role resolution (critical for found posts):
      For lost posts: owner = session.owner, finder = session.claimant (straightforward)
      For found posts: the roles need dynamic resolution because the session owner
        might not be the actual item owner. We determine:
        - actual_finder: the found-post creator (post.user)
        - actual_owner: the person who lost the item (determined from session relationships)

    Also builds a progress stepper (Token Ready → Token Entered → Completed)
    and checks if the owner has a matching lost post (for the found-post recovery flow).
    """
    session = get_object_or_404(
        RecoverySession.objects.select_related('post', 'post__category', 'claimant', 'owner'),
        short_code=short_code,
    )

    # Access control: only owner or claimant can view
    if request.user not in [session.claimant, session.owner]:
        messages.error(request, 'You do not have access to this recovery session.')
        return redirect('recovery:list')

    # Dynamic role resolution — especially important for found posts
    if session.post.post_type == 'found':
        # For found posts: the finder is the post creator
        actual_finder = session.post.user
        # The owner is the person who lost the item (may differ from session.owner)
        if session.owner != session.post.user:
            actual_owner = session.owner
        elif session.claimant and session.claimant != session.post.user:
            actual_owner = session.claimant
        else:
            actual_owner = session.owner
        is_owner = request.user == actual_owner
        is_finder = request.user == actual_finder
    else:
        # For lost posts: straightforward from session fields
        actual_finder = session.claimant
        actual_owner = session.owner
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

    # For found-post owners: check if they have a matching lost post with a token
    owner_lost_session = None
    if session.post.post_type == 'found' and is_owner:
        owner_lost_session = RecoverySession.objects.filter(
            post__user=actual_owner,
            post__post_type='lost',
            post__status='open',
            status='token_generated',
        ).exclude(pk=session.pk).select_related('post').first()

    return render(request, 'recovery/recovery_detail.html', {
        'session': session,
        'steps': steps,
        'is_owner': is_owner,
        'is_finder': is_finder,
        'actual_owner': actual_owner,
        'actual_finder': actual_finder,
        'owner_lost_session': owner_lost_session,
        'sidebar_items': _get_sidebar(request.user),
    })


@login_required
def regenerate_token(request, short_code):
    """
    Generate a new recovery token for an active session.

    Only the session owner can do this. Useful if the old token was
    compromised or shared with the wrong person. The old token is
    immediately invalidated.
    """
    if request.method != 'POST':
        return redirect('recovery:detail', short_code=short_code)

    session = get_object_or_404(RecoverySession, short_code=short_code, owner=request.user)

    if session.status not in ('pending', 'token_generated'):
        messages.error(request, 'Token can only be regenerated while the session is active.')
        return redirect('recovery:detail', short_code=short_code)

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
    return redirect('recovery:detail', short_code=session.short_code)


@login_required
@ratelimit(key='ip', rate='10/m', method='POST', block=True)
def enter_token(request, short_code):
    """
    Finder enters the owner's recovery token to complete recovery.

    This is the critical verification step. The flow:
      1. Only the claimant (finder) can access this page
      2. The finder enters the owner's recovery token (short_code)
      3. The system validates:
         - Token exists and belongs to an active session
         - The token's post is not already resolved
         - The involved users match (prevents unrelated sessions from being linked)
      4. On success (inside an atomic transaction):
         - Both sessions marked as 'completed'
         - Both posts marked as 'resolved'
         - Posts linked via matched_post field
         - Notifications sent to both parties

    Rate limited: 10 attempts per minute per IP (brute-force protection).
    """
    session = get_object_or_404(
        RecoverySession.objects.select_related('post', 'claimant', 'owner'),
        short_code=short_code,
    )

    # Only the assigned finder (claimant) can enter the token
    if request.user != session.claimant:
        messages.error(request, 'Only the authorized finder can complete this recovery.')
        return redirect('recovery:list')

    # Session must be in 'token_generated' state
    if session.status != 'token_generated':
        messages.error(request, 'This recovery session is no longer active.')
        return redirect('recovery:detail', short_code=short_code)

    if request.method == 'POST':
        token = (request.POST.get('short_code', '') or '').strip().upper()

        if not token:
            messages.error(request, 'Please enter the owner\'s recovery token.')
            return render(request, 'recovery/enter_token.html', {
                'session': session, 'sidebar_items': _get_sidebar(request.user)
            })

        # Look up the token — must belong to a different active session
        owner_session = RecoverySession.objects.filter(
            short_code=token, status='token_generated',
        ).exclude(pk=session.pk).select_related('post', 'owner').first()

        if not owner_session:
            messages.error(request, 'Invalid or inactive token. Please check the code and try again.')
            return render(request, 'recovery/enter_token.html', {
                'session': session, 'sidebar_items': _get_sidebar(request.user)
            })

        # Reject if the token's post is already resolved
        if owner_session.post.status == 'resolved':
            messages.error(request, 'This recovery token has already been used for a resolved case.')
            return render(request, 'recovery/enter_token.html', {
                'session': session, 'sidebar_items': _get_sidebar(request.user)
            })

        # Security: ensure the token belongs to related users only
        # (prevents connecting unrelated recovery sessions)
        involved_users = {session.owner_id, session.claimant_id, owner_session.owner_id, owner_session.claimant_id}
        involved_users.discard(None)
        if len(involved_users) > 2:
            messages.error(request, 'This token does not match your recovery session. Please check the code and try again.')
            return render(request, 'recovery/enter_token.html', {
                'session': session, 'sidebar_items': _get_sidebar(request.user)
            })

        # Atomically complete both recovery sessions and resolve both posts
        with transaction.atomic():
            # Complete this session (finder's side)
            session.claimant = request.user
            session.status = 'completed'
            session.token_verified_at = timezone.now()
            session.completed_at = timezone.now()
            session.save(update_fields=['claimant', 'status', 'token_verified_at', 'completed_at'])

            # Complete the owner's session too
            owner_session.claimant = request.user
            owner_session.status = 'completed'
            owner_session.token_verified_at = timezone.now()
            owner_session.completed_at = timezone.now()
            owner_session.save(update_fields=['claimant', 'status', 'token_verified_at', 'completed_at'])

            # Mark both posts as resolved and link them to each other
            session.post.status = 'resolved'
            session.post.matched_post = owner_session.post
            session.post.save(update_fields=['status', 'matched_post'])

            owner_session.post.status = 'resolved'
            owner_session.post.matched_post = session.post
            owner_session.post.save(update_fields=['status', 'matched_post'])

            # Log the completion for both sessions
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

            # Notify both parties about the successful recovery
            if owner_session.owner != request.user:
                Notification.objects.create(
                    user=owner_session.owner,
                    notification_type='post_resolved',
                    title='Item Successfully Recovered',
                    message=f'Your item "{owner_session.post.title}" has been successfully recovered.',
                    link=reverse('recovery:list'),
                )
            if session.owner != request.user:
                Notification.objects.create(
                    user=session.owner,
                    notification_type='post_resolved',
                    title='Item Successfully Recovered',
                    message=f'Your found item "{session.post.title}" has been matched and recovered.',
                    link=reverse('recovery:list'),
                )

        messages.success(request, 'Recovery completed successfully! Both items marked as resolved.')
        return redirect('recovery:detail', short_code=short_code)

    return render(request, 'recovery/enter_token.html', {
        'session': session,
        'sidebar_items': _get_sidebar(request.user),
    })


@login_required
def cancel_recovery(request, short_code):
    """
    Cancel an active recovery session. Either party (owner or claimant) can cancel.
    Sends a notification to the other party about the cancellation.
    """
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

    # Notify the other party
    other_user = session.owner if request.user == session.claimant else session.claimant
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

    # Find and complete the paired session if it exists
    paired_session = RecoverySession.objects.filter(
        post__matched_post=session.post,
        status__in=['pending', 'token_generated', 'token_entered'],
    ).exclude(pk=session.pk).first()

    if paired_session and paired_session.post_id:
        paired_session.status = 'completed'
        paired_session.completed_at = tz.now()
        paired_session.save(update_fields=['status', 'completed_at'])
        paired_session.post.status = 'resolved'
        paired_session.post.save(update_fields=['status'])

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
