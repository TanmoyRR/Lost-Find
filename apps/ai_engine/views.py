from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
from .models import PostEmbedding, MatchSuggestion
from .utils import generate_embedding, compute_cosine_similarity, build_text_for_post
from apps.posts.models import Post
from apps.notifications.models import Notification


def ai_search(request):
    query = request.GET.get('q', '').strip()
    post_type = request.GET.get('type', '')
    category_slug = request.GET.get('category', '')
    location_slug = request.GET.get('location', '')
    status = request.GET.get('status', '')

    results = []
    if query:
        query_embedding = generate_embedding(query)
        if query_embedding:
            all_embeddings = PostEmbedding.objects.select_related('post', 'post__category', 'post__location').all()
            scored = []
            for pe in all_embeddings:
                score = compute_cosine_similarity(query_embedding, pe.embedding)
                if score > 0.3:
                    scored.append((pe.post, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            results = scored[:20]

    posts_list = []
    seen = set()
    for post_obj, score in results:
        if post_obj.pk in seen:
            continue
        seen.add(post_obj.pk)
        if post_type and post_obj.post_type != post_type:
            continue
        if category_slug and (not post_obj.category or post_obj.category.slug != category_slug):
            continue
        if location_slug and (not post_obj.location or post_obj.location.slug != location_slug):
            continue
        if status and post_obj.status != status:
            continue
        posts_list.append(post_obj)

    return render(request, 'ai_engine/search_results.html', {
        'results': posts_list,
        'query': query,
        'result_count': len(posts_list),
    })


@login_required
def my_matches(request):
    matches = MatchSuggestion.objects.filter(
        Q(post__user=request.user) | Q(matched_post__user=request.user),
        status='pending',
    ).select_related('post', 'matched_post', 'post__category', 'matched_post__category').order_by('-similarity_score')[:50]

    for match in matches:
        if match.post.user == request.user and not match.is_viewed:
            match.is_viewed = True
            match.save(update_fields=['is_viewed'])

    return render(request, 'ai_engine/matches.html', {
        'matches': matches,
    })


@login_required
def dismiss_match(request, match_id):
    match = get_object_or_404(MatchSuggestion, pk=match_id)
    if request.user not in [match.post.user, match.matched_post.user]:
        messages.error(request, 'You are not part of this match.')
        return redirect('ai:matches')
    match.status = 'dismissed'
    match.save(update_fields=['status'])
    messages.success(request, 'Match suggestion dismissed.')
    return redirect('ai:matches')


@login_required
def accept_match(request, match_id):
    match = get_object_or_404(MatchSuggestion, pk=match_id)
    if request.user not in [match.post.user, match.matched_post.user]:
        messages.error(request, 'You are not part of this match.')
        return redirect('ai:matches')
    match.status = 'accepted'
    match.is_accepted = True
    match.save(update_fields=['status', 'is_accepted'])
    messages.success(request, 'Match accepted! You can now view the matched item details.')
    return redirect('ai:matches')


@login_required
def contact_match_user(request, match_id):
    match = get_object_or_404(MatchSuggestion, pk=match_id)
    if request.user not in [match.post.user, match.matched_post.user]:
        messages.error(request, 'You are not part of this match.')
        return redirect('ai:matches')

    other_user = match.matched_post.user if match.post.user == request.user else match.post.user
    other_post = match.matched_post if match.post.user == request.user else match.post

    messages.success(
        request,
        f'Contact {other_user.get_full_name()|default:other_user.username} '
        f'via email: {other_user.email} or '
        f'view the matched item: {other_post.title}'
    )
    return redirect('posts:detail', pk=other_post.pk)


@login_required
def api_matches_count(request):
    count = MatchSuggestion.objects.filter(
        Q(post__user=request.user) | Q(matched_post__user=request.user),
        status='pending', is_viewed=False,
    ).count()
    return JsonResponse({'count': count})