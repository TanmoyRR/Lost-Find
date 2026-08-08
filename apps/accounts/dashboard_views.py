from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.db import connection
from django.utils import timezone
from django.http import JsonResponse
from datetime import timedelta

from .models import User, UserActivity
from apps.posts.models import Post, Category, CampusLocation
from apps.membership.models import Membership, MembershipPlan
from apps.payments.models import Payment
from apps.ai_engine.models import PostEmbedding, MatchSuggestion
from apps.notifications.models import Notification


def is_admin(user):
    return user.is_authenticated and user.role == 'admin'


@login_required
def user_dashboard(request):
    user = request.user
    posts = Post.objects.filter(user=user).order_by('-created_at')
    recent_activities = UserActivity.objects.filter(user=user)[:10]
    membership = getattr(user, 'membership', None)
    matches = MatchSuggestion.objects.filter(post__user=user)[:5]
    from apps.notifications.models import Notification
    unread_notifications = Notification.objects.filter(user=user, is_read=False).count()
    from apps.recovery.models import RecoverySession
    active_recoveries = RecoverySession.objects.filter(Q(claimant=user)|Q(owner=user), status__in=['pending','otp_sent','otp_verified','qr_generated','qr_scanned','handover_verified']).count()
    recovery_rate = round((user.resolved_posts() / user.total_posts() * 100) if user.total_posts() > 0 else 0, 1)

    context = {
        'total_posts': user.total_posts(),
        'open_posts': user.open_posts(),
        'resolved_posts': user.resolved_posts(),
        'lost_posts': user.lost_posts(),
        'found_posts': user.found_posts(),
        'recovery_rate': recovery_rate,
        'unread_notifications': unread_notifications,
        'active_recoveries': active_recoveries,
        'posts': posts,
        'recent_activities': recent_activities,
        'membership': membership,
        'matches': matches,
        'sidebar_items': [
            {'url': '/dashboard/', 'label': 'Dashboard', 'icon': 'bi bi-grid-1x2', 'active': True},
            {'url': '/my-posts/', 'label': 'My Posts', 'icon': 'bi bi-file-earmark-text'},
            {'url': '/post/create/', 'label': 'Create Post', 'icon': 'bi bi-plus-circle'},
            {'url': '/ai/matches/', 'label': 'AI Matches', 'icon': 'bi bi-robot'},
            {'url': '/membership/manage/', 'label': 'Membership', 'icon': 'bi bi-gem'},
            {'url': '/notifications/', 'label': 'Notifications', 'icon': 'bi bi-bell'},
            {'url': '/profile/', 'label': 'Profile', 'icon': 'bi bi-person'},
            {'url': '/settings/', 'label': 'Settings', 'icon': 'bi bi-gear'},
        ],
    }
    return render(request, 'dashboard/user_dashboard.html', context)


@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True, is_suspended=False).count()
    inactive_users = total_users - active_users
    total_posts = Post.objects.count()
    open_posts = Post.objects.filter(status='open').count()
    resolved_posts = Post.objects.filter(status='resolved').count()
    total_revenue = Payment.objects.filter(status='completed').aggregate(Sum('amount'))['amount__sum'] or 0
    pending_payments = Payment.objects.filter(status='pending').count()

    posts_by_category = list(Post.objects.values('category__name').annotate(count=Count('id')))
    posts_by_location = list(Post.objects.values('location__name').annotate(count=Count('id')))
    try:
        monthly_registrations = list(User.objects.annotate(month=TruncMonth('date_joined')).values('month').annotate(count=Count('id')).order_by('-month')[:12])
    except Exception:
        monthly_registrations = []
    try:
        monthly_revenue = list(Payment.objects.filter(status='completed').annotate(month=TruncMonth('created_at')).values('month').annotate(total=Sum('amount')).order_by('-month')[:12])
    except Exception:
        monthly_revenue = []
    from apps.recovery.models import RecoverySession
    from apps.recovery.models import RecoverySession
    recovery_sessions = RecoverySession.objects.count()
    completed_recoveries = RecoverySession.objects.filter(status='completed').count()
    pending_recoveries = RecoverySession.objects.filter(status__in=['pending', 'otp_sent', 'otp_verified', 'qr_generated', 'qr_scanned', 'handover_verified']).count()
    recent_activities = UserActivity.objects.all()[:20]
    users = User.objects.all().order_by('-date_joined')[:10]
    posts = Post.objects.all().order_by('-created_at')[:10]
    payments = Payment.objects.all().order_by('-created_at')[:10]

    context = {
        'total_users': total_users,
        'active_users': active_users,
        'inactive_users': inactive_users,
        'total_posts': total_posts,
        'open_posts': open_posts,
        'resolved_posts': resolved_posts,
        'total_revenue': total_revenue,
        'pending_payments': pending_payments,
        'recovery_sessions': recovery_sessions,
        'completed_recoveries': completed_recoveries,
        'pending_recoveries': pending_recoveries,
        'posts_by_category': posts_by_category,
        'posts_by_location': posts_by_location,
        'monthly_registrations': monthly_registrations,
        'monthly_revenue': monthly_revenue,
        'recent_activities': recent_activities,
        'users': users,
        'posts': posts,
        'payments': payments,
        'sidebar_items': ADMIN_SIDEBAR,
    }
    return render(request, 'admin_dashboard/dashboard.html', context)


ADMIN_SIDEBAR = [
    {'url': '/dashboard/admin/', 'label': 'Dashboard', 'icon': 'bi bi-grid-1x2'},
    {'url': '/dashboard/admin/users/', 'label': 'Users', 'icon': 'bi bi-people'},
    {'url': '/dashboard/admin/posts/', 'label': 'Posts', 'icon': 'bi bi-file-earmark-text'},
    {'url': '/dashboard/admin/categories/', 'label': 'Categories', 'icon': 'bi bi-tags'},
    {'url': '/dashboard/admin/locations/', 'label': 'Locations', 'icon': 'bi bi-geo-alt'},
    {'url': '/dashboard/admin/memberships/', 'label': 'Memberships', 'icon': 'bi bi-gem'},
    {'url': '/dashboard/admin/payments/', 'label': 'Payments', 'icon': 'bi bi-credit-card'},
    {'url': '/dashboard/admin/reports/', 'label': 'Reports', 'icon': 'bi bi-bar-chart'},
    {'url': '/dashboard/admin/analytics/', 'label': 'Analytics', 'icon': 'bi bi-graph-up'},
    {'url': '/dashboard/admin/settings/', 'label': 'Settings', 'icon': 'bi bi-gear'},
    {'url': '/profile/', 'label': 'Profile', 'icon': 'bi bi-person'},
]

USER_SIDEBAR = [
    {'url': '/dashboard/', 'label': 'Dashboard', 'icon': 'bi bi-grid-1x2'},
    {'url': '/my-posts/', 'label': 'My Posts', 'icon': 'bi bi-file-earmark-text'},
    {'url': '/post/create/', 'label': 'Create Post', 'icon': 'bi bi-plus-circle'},
    {'url': '/ai/matches/', 'label': 'AI Matches', 'icon': 'bi bi-robot'},
    {'url': '/membership/', 'label': 'Membership', 'icon': 'bi bi-gem'},
    {'url': '/notifications/', 'label': 'Notifications', 'icon': 'bi bi-bell'},
    {'url': '/profile/', 'label': 'Profile', 'icon': 'bi bi-person'},
    {'url': '/settings/', 'label': 'Settings', 'icon': 'bi bi-gear'},
]


@login_required
@user_passes_test(is_admin)
def admin_users(request):
    users = User.objects.all().order_by('-date_joined')
    return render(request, 'admin_dashboard/users.html', {'users': users, 'sidebar_items': ADMIN_SIDEBAR})


@login_required
@user_passes_test(is_admin)
def admin_user_detail(request, pk):
    from apps.payments.models import Payment
    from apps.membership.models import MembershipPlan
    user = get_object_or_404(User, pk=pk)
    user_posts = Post.objects.filter(user=user)
    user_payments = Payment.objects.filter(user=user)
    user_activities = UserActivity.objects.filter(user=user)[:20]
    open_posts = user_posts.filter(status='open').count()
    resolved_posts = user_posts.filter(status='resolved').count()
    payment_count = user_payments.count()
    return render(request, 'admin_dashboard/user_detail.html', {
        'profile_user': user,
        'user_posts': user_posts,
        'user_payments': user_payments,
        'user_activities': user_activities,
        'posts': user_posts,
        'activities': user_activities,
        'open_posts': open_posts,
        'resolved_posts': resolved_posts,
        'payment_count': payment_count,
        'total_posts': user_posts.count(),
        'plans': MembershipPlan.objects.filter(is_active=True),
        'sidebar_items': ADMIN_SIDEBAR,
    })


@login_required
@user_passes_test(is_admin)
def admin_suspend_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    user.is_suspended = True
    user.is_active = False
    user.save()
    messages.success(request, f'User {user.username} has been suspended.')
    return redirect('dashboard:admin_users')


@login_required
@user_passes_test(is_admin)
def admin_activate_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    user.is_suspended = False
    user.is_active = True
    user.save()
    messages.success(request, f'User {user.username} has been activated.')
    return redirect('dashboard:admin_users')


@login_required
@user_passes_test(is_admin)
def admin_posts(request):
    posts = Post.objects.all().order_by('-created_at')
    pending_posts = posts.filter(status='open')
    total_posts_count = posts.count()
    pending_count = pending_posts.count()
    resolved_count = posts.filter(status='resolved').count()
    return render(request, 'admin_dashboard/posts.html', {
        'posts': posts,
        'pending_posts': posts,
        'total_posts_count': total_posts_count,
        'pending_count': pending_count,
        'resolved_count': resolved_count,
        'sidebar_items': ADMIN_SIDEBAR,
    })


@login_required
@user_passes_test(is_admin)
def admin_post_approve(request, pk):
    post = get_object_or_404(Post, pk=pk)
    post.status = 'open'
    post.save(update_fields=['status'])
    messages.success(request, f'Post "{post.title}" approved.')
    return redirect('dashboard:admin_posts')


@login_required
@user_passes_test(is_admin)
def admin_post_reject(request, pk):
    post = get_object_or_404(Post, pk=pk)
    post.status = 'claimed'
    post.save(update_fields=['status'])
    messages.success(request, f'Post "{post.title}" rejected.')
    return redirect('dashboard:admin_posts')


@login_required
@user_passes_test(is_admin)
def admin_post_soft_delete(request, pk):
    post = get_object_or_404(Post, pk=pk)
    post.is_active = False
    post.save(update_fields=['is_active'])
    messages.success(request, f'Post "{post.title}" soft deleted.')
    return redirect('dashboard:admin_posts')


@login_required
@user_passes_test(is_admin)
def admin_post_restore(request, pk):
    post = get_object_or_404(Post, pk=pk)
    post.is_active = True
    post.save(update_fields=['is_active'])
    messages.success(request, f'Post "{post.title}" restored.')
    return redirect('dashboard:admin_posts')


@login_required
@user_passes_test(is_admin)
def admin_post_permanent_delete(request, pk):
    post = get_object_or_404(Post, pk=pk)
    title = post.title
    post.delete()
    messages.success(request, f'Post "{title}" permanently deleted.')
    return redirect('dashboard:admin_posts')


@login_required
@user_passes_test(is_admin)
def admin_categories(request):
    from django.db.models import Count
    categories = Category.objects.annotate(post_count=Count('posts'))
    total_categories = categories.count()
    active_categories = categories.count()
    total_posts_in_categories = Post.objects.filter(category__isnull=False).count()
    return render(request, 'admin_dashboard/categories.html', {
        'categories': categories,
        'total_categories': total_categories,
        'active_categories': active_categories,
        'total_posts_in_categories': total_posts_in_categories,
        'sidebar_items': ADMIN_SIDEBAR,
    })


@login_required
@user_passes_test(is_admin)
def admin_locations(request):
    from django.db.models import Count
    locations = CampusLocation.objects.annotate(post_count=Count('posts'))
    total_locations = locations.count()
    active_locations = locations.count()
    total_posts_in_locations = Post.objects.filter(location__isnull=False).count()
    return render(request, 'admin_dashboard/locations.html', {
        'locations': locations,
        'total_locations': total_locations,
        'active_locations': active_locations,
        'total_posts_in_locations': total_posts_in_locations,
        'sidebar_items': ADMIN_SIDEBAR,
    })


@login_required
@user_passes_test(is_admin)
def admin_payments(request):
    from django.db.models import Sum, Count
    payments = Payment.objects.all().order_by('-created_at')
    total_revenue = Payment.objects.filter(status='completed').aggregate(Sum('amount'))['amount__sum'] or 0
    pending_payments = Payment.objects.filter(status='pending').count()
    completed_payments = Payment.objects.filter(status='completed').count()
    failed_payments = Payment.objects.filter(status='failed').count()
    monthly_revenue = list(Payment.objects.filter(status='completed')
        .annotate(month=TruncMonth('created_at'))
        .values('month').annotate(total=Sum('amount')).order_by('-month')[:12])
    return render(request, 'admin_dashboard/payments.html', {
        'payments': payments,
        'total_revenue': total_revenue,
        'pending_payments': pending_payments,
        'completed_payments': completed_payments,
        'failed_payments': failed_payments,
        'monthly_revenue': monthly_revenue,
        'sidebar_items': ADMIN_SIDEBAR,
    })


@login_required
@user_passes_test(is_admin)
def admin_reports(request):
    from django.db.models import Count, Sum
    total_users = User.objects.count()
    total_posts = Post.objects.count()
    resolved_posts = Post.objects.filter(status='resolved').count()
    recovery_rate = round((resolved_posts / total_posts * 100) if total_posts > 0 else 0, 1)
    posts_by_category = list(Post.objects.values('category__name').annotate(count=Count('id')))
    posts_by_location = list(Post.objects.values('location__name').annotate(count=Count('id')))
    total_revenue = Payment.objects.filter(status='completed').aggregate(Sum('amount'))['amount__sum'] or 0
    return render(request, 'admin_dashboard/reports.html', {
        'total_users': total_users,
        'total_posts': total_posts,
        'resolved_posts': resolved_posts,
        'recovery_rate': recovery_rate,
        'posts_by_category': posts_by_category,
        'posts_by_location': posts_by_location,
        'total_revenue': total_revenue,
        'sidebar_items': ADMIN_SIDEBAR,
    })


@login_required
@user_passes_test(is_admin)
def admin_analytics(request):
    from django.db.models import Count, Sum
    total_users = User.objects.count()
    total_posts = Post.objects.count()
    resolved_posts = Post.objects.filter(status='resolved').count()
    recovery_rate = round((resolved_posts / total_posts * 100) if total_posts > 0 else 0, 1)
    posts_by_category = list(Post.objects.values('category__name').annotate(count=Count('id')))
    posts_by_location = list(Post.objects.values('location__name').annotate(count=Count('id')))
    monthly_registrations = list(User.objects.annotate(month=TruncMonth('date_joined'))
        .values('month').annotate(count=Count('id')).order_by('-month')[:12])
    monthly_revenue = list(Payment.objects.filter(status='completed')
        .annotate(month=TruncMonth('created_at'))
        .values('month').annotate(total=Sum('amount')).order_by('-month')[:12])
    recovery_success_rate = list(Post.objects.filter(status='resolved')
        .annotate(month=TruncMonth('updated_at'))
        .values('month').annotate(count=Count('id')).order_by('-month')[:12])
    return render(request, 'admin_dashboard/analytics.html', {
        'total_users': total_users,
        'total_posts': total_posts,
        'resolved_posts': resolved_posts,
        'recovery_rate': recovery_rate,
        'posts_by_category': posts_by_category,
        'posts_by_location': posts_by_location,
        'monthly_registrations': monthly_registrations,
        'monthly_revenue': monthly_revenue,
        'recovery_success_rate': recovery_success_rate,
        'sidebar_items': ADMIN_SIDEBAR,
    })


@login_required
@user_passes_test(is_admin)
def admin_settings(request):
    return render(request, 'admin_dashboard/settings.html', {'sidebar_items': ADMIN_SIDEBAR})


@login_required
@user_passes_test(is_admin)
def admin_memberships(request):
    from django.db.models import Count
    memberships = Membership.objects.select_related('user', 'plan').order_by('-created_at')
    total_members = memberships.count()
    active_members = memberships.filter(is_active=True).count()
    expired_members = total_members - active_members
    return render(request, 'admin_dashboard/memberships.html', {
        'memberships': memberships,
        'total_members': total_members,
        'active_members': active_members,
        'expired_members': expired_members,
        'sidebar_items': ADMIN_SIDEBAR,
    })


@login_required
@user_passes_test(is_admin)
def admin_update_membership(request, pk):
    user = get_object_or_404(User, pk=pk)
    membership = getattr(user, 'membership', None)
    from apps.membership.models import MembershipPlan

    if request.method == 'POST':
        is_active = request.POST.get('is_active') == 'on'
        plan_id = request.POST.get('plan')
        started_at_str = request.POST.get('started_at')
        expires_at_str = request.POST.get('expires_at')

        plan = MembershipPlan.objects.filter(pk=plan_id).first() if plan_id else None
        if is_active and not plan:
            messages.error(request, 'Please select a plan for active membership.')
            return redirect('dashboard:admin_user_detail', pk=pk)

        started_at = timezone.datetime.strptime(started_at_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone()) if started_at_str else None
        expires_at = timezone.datetime.strptime(expires_at_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone()) if expires_at_str else None

        if is_active and (not started_at or not expires_at):
            messages.error(request, 'Start and expiry dates are required for active membership.')
            return redirect('dashboard:admin_user_detail', pk=pk)

        if membership:
            membership.plan = plan
            membership.is_active = is_active
            membership.started_at = started_at
            membership.expires_at = expires_at
            membership.save()
        else:
            Membership.objects.create(
                user=user, plan=plan, is_active=is_active,
                started_at=started_at, expires_at=expires_at
            )
        messages.success(request, f'Membership updated for {user.username}.')
    return redirect('dashboard:admin_user_detail', pk=pk)


@login_required
@user_passes_test(is_admin)
def admin_toggle_membership(request, pk):
    user = get_object_or_404(User, pk=pk)
    membership = getattr(user, 'membership', None)
    if membership and membership.is_active:
        membership.is_active = False
        membership.expires_at = timezone.now()
        membership.save()
        messages.success(request, f'Membership revoked for {user.username}.')
    else:
        from apps.membership.models import MembershipPlan
        plan = MembershipPlan.objects.filter(is_active=True).first()
        if not plan:
            messages.error(request, 'No active membership plan found. Create one first.')
            return redirect('dashboard:admin_user_detail', pk=pk)
        if membership:
            membership.plan = plan
            membership.is_active = True
            membership.started_at = timezone.now()
            membership.expires_at = timezone.now() + timedelta(days=plan.duration_days)
            membership.save()
        else:
            Membership.objects.create(
                user=user, plan=plan, is_active=True,
                started_at=timezone.now(),
                expires_at=timezone.now() + timedelta(days=plan.duration_days)
            )
        messages.success(request, f'Membership granted to {user.username}.')
    return redirect('dashboard:admin_user_detail', pk=pk)
