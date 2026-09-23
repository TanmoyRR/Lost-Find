"""
Post Views — Handles all post-related operations for the Lost & Found system.

This module manages:
  - Browsing and searching posts (with filters for type, category, location)
  - Viewing individual post details (with membership-gated contact info)
  - Creating, editing, and deleting posts (with role-based permissions)
  - Marking posts as resolved (closes recovery sessions)
  - Viewing the user's own posts

Permission rules:
  - Anyone with a membership can create/edit/delete their own posts.
  - Admins can edit/delete any post but cannot create new posts.
  - Post detail viewing is open to all authenticated users.
"""

import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, F
from django.db import transaction
from django.core.paginator import Paginator

from .models import Post, Category, CampusLocation
from .forms import PostForm
from apps.accounts.models import UserActivity
from apps.accounts.decorators import is_admin
from apps.accounts.decorators import membership_required
from apps.ai_engine.utils import find_matches_for_post, refresh_post_embedding, build_text_for_post

logger = logging.getLogger(__name__)


@login_required
def browse_posts(request):
    """
    Browse and search all posts with filtering.

    Supports filtering by:
      - post_type: 'lost', 'found', or 'resolved'
      - category: filter by category slug
      - location: filter by campus location slug
      - query (q): free-text search across title, description, and category name

    By default, only shows 'open' and 'claimed' posts (resolved posts are hidden
    unless explicitly filtered). Results are paginated (12 per page).
    """
    query = request.GET.get('q', '')
    post_type = request.GET.get('type', '')
    category = request.GET.get('category', '')
    location = request.GET.get('location', '')

    posts = Post.objects.select_related('category', 'location', 'user')

    # Filter by post type — resolved posts hidden by default
    if post_type:
        if post_type == 'resolved':
            posts = posts.filter(status='resolved')
        elif post_type == 'lost':
            posts = posts.filter(post_type='lost', status__in=['open', 'claimed'])
        elif post_type == 'found':
            posts = posts.filter(post_type='found', status__in=['open', 'claimed'])
    else:
        posts = posts.filter(status__in=['open', 'claimed'])

    # Free-text search across title, description, and category name
    if query:
        posts = posts.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query)
        )
    if category:
        posts = posts.filter(category__slug=category)
    if location:
        posts = posts.filter(location__slug=location)

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
        'current_status': post_type,
    })


@login_required
def post_detail(request, pk):
    """
    Display full details of a single post.

    Access control for contact info (can_view_full):
      - Post owner: always sees full details
      - Admin: always sees full details
      - Member with active membership: sees full details
      - Others: sees restricted view (contact info hidden)

    Also fetches:
      - AI match suggestions from the matching engine (top 5 by similarity)
      - Related posts from the same category (up to 4)
      - Whether the viewer has an active lost post (for recovery flow)
    """
    post = get_object_or_404(Post.objects.select_related('category', 'location', 'user').prefetch_related('recovery_sessions'), pk=pk)

    # Increment view count for non-owner visitors
    if post.user != request.user:
        Post.objects.filter(pk=pk).update(views_count=F('views_count') + 1)

    # Determine if viewer can see full contact details (membership gate)
    can_view_full = False
    has_active_lost_post = False
    if request.user.is_authenticated:
        if request.user == post.user:
            can_view_full = True
        elif is_admin(request.user):
            can_view_full = True
        else:
            membership = getattr(request.user, 'membership', None)
            if membership and membership.is_active:
                can_view_full = True
        # Check if viewer has an active lost post (used for recovery link)
        has_active_lost_post = Post.objects.filter(
            user=request.user, post_type='lost', status__in=['open', 'claimed']
        ).exists()

    # Related posts from same category
    related_posts = Post.objects.select_related('location', 'category').filter(
        category=post.category
    ).exclude(pk=post.pk)[:4]

    # Fetch AI match suggestions where this post is involved
    from apps.ai_engine.models import MatchSuggestion
    ai_matches_qs = MatchSuggestion.objects.select_related(
        'post', 'matched_post', 'post__category', 'matched_post__category'
    ).filter(
        Q(post=post) | Q(matched_post=post),
        post__status__in=['open', 'claimed'],
        matched_post__status__in=['open', 'claimed'],
    ).order_by('-similarity_score')[:5]

    ai_matches = []
    for m in ai_matches_qs:
        # Show the "other" post in the pair (not the current one)
        other = m.matched_post if m.post == post else m.post
        ai_matches.append({'other': other, 'score': m.similarity_score})

    return render(request, 'posts/detail.html', {
        'post': post,
        'related_posts': related_posts,
        'ai_matches': ai_matches,
        'can_view_full': can_view_full,
        'has_active_lost_post': has_active_lost_post,
    })


@membership_required
def create_post(request):
    """
    Create a new lost or found item post.

    Flow:
      1. Admins are redirected — they manage posts, not create them.
      2. On POST: validate form → save post → trigger AI matching → redirect to post detail.
      3. On GET: render empty PostForm.

    Recovery sessions are created ONLY when messaging starts (apps/messaging/views.py),
    not at post creation. Whoever messages first creates the single session for the match.

    AI matching: find_matches_for_post() generates an embedding via Jina API,
    searches for opposite-type posts (lost↔found), and stores MatchSuggestions.
    """
    if is_admin(request.user):
        messages.error(request, 'Admins manage posts; they cannot create new posts.')
        return redirect('dashboard:admin_home')

    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.user = request.user
            post.save()
            messages.success(request, 'Post created successfully!')

            # Trigger AI matching (generates embedding + finds matches)
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
    """
    Edit an existing post. Admins can edit any post; regular users only their own.

    AI data refresh: Before saving, we capture the searchable text (title, category,
    location, description, tags). After saving, if the text changed, we re-run
    AI matching to update the embedding and match suggestions. This ensures the
    post stays searchable/matchable after edits.
    """
    # Permission: admin can edit any post, regular user only their own
    if is_admin(request.user):
        post = get_object_or_404(Post, pk=pk)
    else:
        post = get_object_or_404(Post, pk=pk, user=request.user)

    # Capture searchable text BEFORE edit for AI refresh comparison
    old_searchable_text = build_text_for_post(post)

    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            form.save()
            UserActivity.objects.create(
                user=request.user, activity_type='post_updated',
                description=f'Updated post: {post.title}'
            )

            # Only refresh AI data if the searchable content actually changed
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
    """
    Delete a post. Requires POST confirmation. Admins can delete any post.
    Shows a confirmation page on GET; actually deletes on POST.
    """
    if is_admin(request.user):
        post = get_object_or_404(Post, pk=pk)
    else:
        post = get_object_or_404(Post, pk=pk, user=request.user)

    if request.method == 'POST':
        UserActivity.objects.create(
            user=request.user, activity_type='post_deleted',
            description=f'Deleted post: {post.title}'
        )
        post.delete()
        messages.success(request, 'Post deleted successfully!')
        return redirect('dashboard:home')

    return render(request, 'posts/confirm_delete.html', {'post': post})


@membership_required
def mark_resolved(request, pk):
    """
    Mark a post as resolved. Only the post owner can do this.

    When resolved:
      - Post status → 'resolved' (is_resolved auto-set in model.save())
      - Any active RecoverySessions for this post → 'completed'
      - This hides the post from browse and stops AI matching
    """
    post = get_object_or_404(Post, pk=pk, user=request.user)

    if request.method == 'POST':
        post.status = 'resolved'
        post.save()

        # Close any active recovery sessions for this post
        from apps.recovery.models import RecoverySession
        RecoverySession.objects.filter(
            post=post, status__in=['pending', 'token_generated', 'token_entered']
        ).update(status='completed')

        UserActivity.objects.create(
            user=request.user, activity_type='post_resolved',
            description=f'Resolved post: {post.title}'
        )
        messages.success(request, 'Post marked as resolved!')

    return redirect('posts:detail', pk=pk)


@login_required
def my_posts(request):
    """Display all posts created by the current user, paginated (20 per page)."""
    posts = Post.objects.filter(user=request.user).select_related(
        'category', 'location'
    ).order_by('-created_at')

    paginator = Paginator(posts, 20)
    page = request.GET.get('page', 1)
    posts_page = paginator.get_page(page)

    return render(request, 'posts/my_posts.html', {'posts': posts_page})
