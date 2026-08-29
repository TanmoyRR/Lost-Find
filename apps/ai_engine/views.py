import logging

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

logger = logging.getLogger('apps.ai_engine')


@login_required
def ai_search(request):
    query = request.GET.get('q', '').strip()
    filters = {
        'post_type': request.GET.get('type', ''),
        'category_slug': request.GET.get('category', ''),
        'location_slug': request.GET.get('location', ''),
        'status': request.GET.get('status', 'open'),
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
            if not vector_backend_available():
                logger.info('AI search fallback: vector backend unavailable')
            else:
                logger.info('AI search fallback: embedding generation failed')
            results = [(post, 0.0) for post in keyword_search_posts(query, **filters)]

    return render(request, 'ai_engine/search_results.html', {
        'results': results,
        'query': query,
        'used_fallback': used_fallback,
        'result_count': len(results),
    })


@login_required
def my_matches(request):
    matches_qs = MatchSuggestion.objects.filter(
        Q(post__user=request.user) | Q(matched_post__user=request.user),
        status='pending',
    ).select_related(
        'post', 'matched_post',
        'post__category', 'matched_post__category',
        'post__location', 'matched_post__location',
    ).order_by('-similarity_score')[:50]

    MatchSuggestion.objects.filter(
        Q(post__user=request.user) | Q(matched_post__user=request.user),
        status='pending',
        is_viewed=False,
    ).update(is_viewed=True)

    matches = list(matches_qs)

    return render(request, 'ai_engine/matches.html', {
        'matches': matches,
    })


@login_required
def dismiss_match(request, match_id):
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('ai:matches')
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
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('ai:matches')
    match = get_object_or_404(MatchSuggestion, pk=match_id)
    if request.user not in [match.post.user, match.matched_post.user]:
        messages.error(request, 'You are not part of this match.')
        return redirect('ai:matches')

    lost_post = match.post if match.post.post_type == 'lost' else match.matched_post
    found_post = match.matched_post if match.post.post_type == 'lost' else match.post
    finder = found_post.user

    match.status = 'accepted'
    match.is_accepted = True
    match.save(update_fields=['status', 'is_accepted'])

    try:
        from apps.recovery.models import RecoverySession, RecoveryVerificationLog
        from apps.notifications.models import Notification
        session = RecoverySession.objects.filter(post=lost_post, status__in=('pending', 'qr_generated')).first()
        if session and not session.claimant:
            session.claimant = finder
            session.save(update_fields=['claimant'])
            RecoveryVerificationLog.objects.create(
                session=session, action='finder_assigned',
                performed_by=finder,
                details={'match_id': match.id},
            )
            Notification.objects.create(
                user=lost_post.user,
                notification_type='recovery_update',
                title='Finder Claimed Your Item',
                message=f'{finder.get_full_name() or finder.username} has been assigned as the finder for "{lost_post.title}". They can now scan the QR code to complete recovery.',
                link=f'/recovery/{session.short_code}/',
            )
            Notification.objects.create(
                user=finder,
                notification_type='recovery_update',
                title='You Are Now the Finder',
                message=f'You have been assigned as the finder for "{lost_post.title}". Go to the recovery session to scan the QR code.',
                link=f'/recovery/{session.short_code}/',
            )
    except Exception:
        pass

    messages.success(request, 'Match accepted! You can now view the matched item details and start a conversation.')
    return redirect('ai:matches')


@login_required
def contact_match_user(request, match_id):
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('ai:matches')
    match = get_object_or_404(MatchSuggestion, pk=match_id)
    if request.user not in [match.post.user, match.matched_post.user]:
        messages.error(request, 'You are not part of this match.')
        return redirect('ai:matches')

    other_post = match.matched_post if match.post.user == request.user else match.post

    messages.success(
        request,
        f'View the matched item details and use the "Start Conversation" button to reach the other user: {other_post.title}'
    )
    return redirect('posts:detail', pk=other_post.pk)


@login_required
def api_matches_count(request):
    count = MatchSuggestion.objects.filter(
        Q(post__user=request.user) | Q(matched_post__user=request.user),
        status='pending', is_viewed=False,
    ).count()
    return JsonResponse({'count': count})
