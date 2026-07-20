from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator

from .models import Post, Category, CampusLocation
from .forms import PostForm
from apps.accounts.models import UserActivity
from apps.ai_engine.utils import find_matches_for_post


def browse_posts(request):
    query = request.GET.get('q', '')
    post_type = request.GET.get('type', '')
    category = request.GET.get('category', '')
    location = request.GET.get('location', '')
    status = request.GET.get('status', '')

    posts = Post.objects.all()

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


def post_detail(request, pk):
    post = get_object_or_404(Post, pk=pk)
    post.views_count += 1
    post.save()
    related_posts = Post.objects.filter(category=post.category).exclude(pk=post.pk)[:4]
    from apps.ai_engine.models import MatchSuggestion
    ai_matches_qs = MatchSuggestion.objects.filter(
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
    })


@login_required
def create_post(request):
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.user = request.user
            post.save()
            messages.success(request, 'Post created successfully!')
            try:
                find_matches_for_post(post)
            except Exception:
                pass
            return redirect('posts:detail', pk=post.pk)
    else:
        form = PostForm()
    return render(request, 'posts/create.html', {'form': form, 'is_edit': False})


@login_required
def edit_post(request, pk):
    post = get_object_or_404(Post, pk=pk, user=request.user)
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            form.save()
            UserActivity.objects.create(user=request.user, activity_type='post_updated', description=f'Updated post: {post.title}')
            messages.success(request, 'Post updated successfully!')
            return redirect('posts:detail', pk=post.pk)
    else:
        form = PostForm(instance=post)
    return render(request, 'posts/create.html', {'form': form, 'is_edit': True, 'post': post})


@login_required
def delete_post(request, pk):
    post = get_object_or_404(Post, pk=pk, user=request.user)
    if request.method == 'POST':
        UserActivity.objects.create(user=request.user, activity_type='post_deleted', description=f'Deleted post: {post.title}')
        post.delete()
        messages.success(request, 'Post deleted successfully!')
        return redirect('dashboard:home')
    return render(request, 'posts/confirm_delete.html', {'post': post})


@login_required
def mark_resolved(request, pk):
    post = get_object_or_404(Post, pk=pk, user=request.user)
    post.status = 'resolved'
    post.is_resolved = True
    post.save()
    UserActivity.objects.create(user=request.user, activity_type='post_resolved', description=f'Resolved post: {post.title}')
    messages.success(request, 'Post marked as resolved!')
    return redirect('posts:detail', pk=post.pk)


@login_required
def my_posts(request):
    posts = Post.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'posts/my_posts.html', {'posts': posts})
