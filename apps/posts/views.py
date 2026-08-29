import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, F
from django.core.paginator import Paginator

from .models import Post, Category, CampusLocation
from .forms import PostForm
from apps.accounts.models import UserActivity
from apps.accounts.decorators import membership_required
from apps.ai_engine.utils import find_matches_for_post, refresh_post_embedding, build_text_for_post

logger = logging.getLogger(__name__)


@login_required
def browse_posts(request):
    query = request.GET.get('q', '')
    post_type = request.GET.get('type', '')
    category = request.GET.get('category', '')
    location = request.GET.get('location', '')
    status = request.GET.get('status', '')

    posts = Post.objects.select_related('category', 'location', 'user')

    if query:
        posts = posts.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query)
        )
    if post_type:
        posts = posts.filter(post_type=post_type)
    if category:
        posts = posts.filter(category__slug=category)
    if location:
        posts = posts.filter(location__slug=location)
    if status:
        posts = posts.filter(status=status)

    paginator = Paginator(posts, 12)
    page = request.GET.get('page', 1)
    posts_page = paginator.get_page(page)

    categories = Category.objects.all()
    locations = CampusLocation.objects.all()

    return render(request, 'posts/browse.html', {
        'posts': posts_page,
        'categories': categories,
        'locations': locations,
        'current_query': query,
        'current_type': post_type,
        'current_category': category,
        'current_location': location,
        'current_status': status,
    })


@login_required
def post_detail(request, pk):
    post = get_object_or_404(Post.objects.select_related('category', 'location', 'user'), pk=pk)
    Post.objects.filter(pk=pk).update(views_count=F('views_count') + 1)

    if post.post_type == 'lost' and post.status != 'resolved':
        try:
            from apps.recovery.models import RecoverySession
            if not RecoverySession.objects.filter(post=post).exists():
                from apps.recovery.views import create_recovery_session_for_post
                create_recovery_session_for_post(post)
        except Exception:
            pass
    elif post.post_type == 'found' and post.status != 'resolved':
        try:
            from apps.recovery.models import RecoverySession
            if not RecoverySession.objects.filter(post=post).exists():
                from apps.recovery.views import create_finder_recovery_session
                create_finder_recovery_session(post)
        except Exception:
            pass

    can_view_full = False
    if request.user.is_authenticated:
        if request.user == post.user:
            can_view_full = True
        elif request.user.is_superuser or request.user.is_staff:
            can_view_full = True
        else:
            membership = getattr(request.user, 'membership', None)
            if membership and membership.is_active:
                can_view_full = True
    related_posts = Post.objects.select_related('location', 'category').filter(category=post.category).exclude(pk=post.pk)[:4]
    from apps.ai_engine.models import MatchSuggestion
    ai_matches_qs = MatchSuggestion.objects.select_related(
        'post', 'matched_post', 'post__category', 'matched_post__category'
    ).filter(
        Q(post=post) | Q(matched_post=post)
    ).order_by('-similarity_score')[:5]
    ai_matches = []
    for m in ai_matches_qs:
        other = m.matched_post if m.post == post else m.post
        ai_matches.append({'other': other, 'score': m.similarity_score})
    return render(request, 'posts/detail.html', {
        'post': post,
        'related_posts': related_posts,
        'ai_matches': ai_matches,
        'can_view_full': can_view_full,
    })


@membership_required
def create_post(request):
    if request.user.is_staff or request.user.is_superuser:
        messages.error(request, 'Admins manage posts; they cannot create new posts.')
        return redirect('dashboard:admin_home')
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.user = request.user
            post.save()
            messages.success(request, 'Post created successfully!')
            if post.post_type == 'lost':
                try:
                    from apps.recovery.views import create_recovery_session_for_post
                    session = create_recovery_session_for_post(post)
                    messages.info(request, f'Recovery QR code generated: {session.short_code}')
                except Exception:
                    pass
            elif post.post_type == 'found':
                try:
                    from apps.recovery.views import create_finder_recovery_session
                    session = create_finder_recovery_session(post)
                    messages.info(request, f'Recovery scan ready: {session.short_code}')
                except Exception:
                    pass
            try:
                find_matches_for_post(post)
            except Exception:
                pass
            return redirect('posts:detail', pk=post.pk)
    else:
        form = PostForm()
    return render(request, 'posts/create.html', {'form': form, 'is_edit': False})


@membership_required
def edit_post(request, pk):
    if request.user.is_staff or request.user.is_superuser:
        post = get_object_or_404(Post, pk=pk)
    else:
        post = get_object_or_404(Post, pk=pk, user=request.user)
    old_searchable_text = build_text_for_post(post)
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            form.save()
            UserActivity.objects.create(user=request.user, activity_type='post_updated', description=f'Updated post: {post.title}')
            new_searchable_text = build_text_for_post(post)
            if new_searchable_text != old_searchable_text:
                try:
                    find_matches_for_post(post)
                except Exception:
                    pass
            messages.success(request, 'Post updated successfully!')
            return redirect('posts:detail', pk=post.pk)
    else:
        form = PostForm(instance=post)
    return render(request, 'posts/create.html', {'form': form, 'is_edit': True, 'post': post})


@membership_required
def delete_post(request, pk):
    post = get_object_or_404(Post, pk=pk, user=request.user)
    if request.method == 'POST':
        UserActivity.objects.create(user=request.user, activity_type='post_deleted', description=f'Deleted post: {post.title}')
        post.delete()
        messages.success(request, 'Post deleted successfully!')
        return redirect('dashboard:home')
    return render(request, 'posts/confirm_delete.html', {'post': post})


@membership_required
def mark_resolved(request, pk):
    post = get_object_or_404(Post, pk=pk, user=request.user)
    if request.method == 'POST':
        post.status = 'resolved'
        post.is_resolved = True
        post.save()
        UserActivity.objects.create(user=request.user, activity_type='post_resolved', description=f'Resolved post: {post.title}')
        messages.success(request, 'Post marked as resolved!')
    return redirect('posts:detail', pk=pk)


@login_required
def my_posts(request):
    posts = Post.objects.filter(user=request.user).select_related('category', 'location').order_by('-created_at')
    paginator = Paginator(posts, 20)
    page = request.GET.get('page', 1)
    posts_page = paginator.get_page(page)
    return render(request, 'posts/my_posts.html', {'posts': posts_page})
