from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
from .models import MatchSuggestion
from .utils import (
    generate_embedding,
    semantic_search_posts,
    keyword_search_posts,
    vector_backend_available,
)
from apps.notifications.models import Notification


@login_required
def ai_search(request):
    query = request.GET.get('q', '').strip()
    filters = {
        'post_type': request.GET.get('type', ''),
        'category_slug': request.GET.get('category', ''),
        'location_slug': request.GET.get('location', ''),
        'status': request.GET.get('status', ''),
    }

    results = []
    used_fallback = False

    if query:
        query_vector = generate_embedding(query) if vector_backend_available() else None
        if query_vector:
            scored = semantic_search_posts(query_vector, **filters)
            results = [(post, score) for post, score in scored][:20]
        else:
            used_fallback = True
            results = [(post, 0.0) for post in keyword_search_posts(query, **filters)]

    return render(request, 'ai_engine/search_results.html', {
        'results': results,
        'query': query,
        'used_fallback': used_fallback,
        'result_count': len(results),
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