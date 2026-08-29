"""
AI engine utilities: Jina API embeddings + Supabase PostgreSQL pgvector.

Replaces the old local SentenceTransformer implementation with an
API-based flow:

    text -> Jina Embeddings API -> vector -> pgvector (cosine search)

All AI calls fail soft: if Jina or pgvector is unavailable, functions
return empty results and callers fall back to keyword search.
"""
import logging
import math

from django.conf import settings
from django.db import connection
from django.db.models import Q

from apps.posts.models import Post
from . import jina_client
from .models import PostEmbedding, MatchSuggestion

logger = logging.getLogger('apps.ai_engine')

_vector_backend_state = None


def generate_embedding(text, **kwargs):
    """Generate an embedding via the Jina API. Returns a list or None."""
    result = jina_client.generate_embedding(text, **kwargs)
    if result:
        logger.debug('Embedding generated (%d dims)', len(result))
    else:
        logger.warning('Embedding generation returned None')
    return result


def vector_backend_available():
    """
    True when the active database is PostgreSQL with the pgvector
    extension enabled. Cached per process; reset_vector_backend_cache()
    clears it (used by tests).
    """
    global _vector_backend_state
    if _vector_backend_state is None:
        try:
            if connection.vendor != 'postgresql':
                _vector_backend_state = False
            else:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                    _vector_backend_state = cursor.fetchone() is not None
        except Exception as exc:
            logger.error('pgvector check failed: %s', exc)
            _vector_backend_state = False
    return _vector_backend_state


def reset_vector_backend_cache():
    global _vector_backend_state
    _vector_backend_state = None


def compute_cosine_similarity(embedding1, embedding2):
    """Pure-Python cosine similarity (0..1). Used when pgvector is unavailable."""
    if not embedding1 or not embedding2 or len(embedding1) != len(embedding2):
        return 0.0
    dot = sum(a * b for a, b in zip(embedding1, embedding2))
    norm1 = math.sqrt(sum(a * a for a in embedding1))
    norm2 = math.sqrt(sum(b * b for b in embedding2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def build_text_for_post(post):
    """
    Build the searchable text representation used for embeddings.

    Includes item-type, title, category, location, description, and tags.
    Excludes contact_info and other personally identifiable data for privacy.
    """
    parts = []
    parts.append('{}: {}'.format(post.get_post_type_display(), post.title))
    if post.category_id:
        parts.append('Category: {}'.format(post.category.name))
    location_display = post.display_location if hasattr(post, 'display_location') else ''
    if location_display and location_display != 'N/A':
        parts.append('Location: {}'.format(location_display))
    if post.description:
        parts.append(post.description)
    try:
        tags = list(post.tags.values_list('name', flat=True))
        if tags:
            parts.append('Tags: {}'.format(', '.join(tags)))
    except Exception:
        pass
    return ' '.join(part for part in parts if part)


def store_post_embedding(post, vector):
    """Persist an embedding row for a post (idempotent)."""
    if not vector_backend_available():
        return None
    try:
        return PostEmbedding.objects.update_or_create(
            post=post, defaults={'embedding': vector}
        )
    except Exception as exc:
        logger.error('Failed to store embedding for post %s: %s', post.pk, exc)
        return None


def refresh_post_embedding(post):
    """Regenerate and store the embedding for a single post. Safe to retry."""
    try:
        text = build_text_for_post(post)
        vector = generate_embedding(text)
    except Exception as exc:
        logger.error('refresh_post_embedding error for post %s: %s', post.pk, exc)
        return None
    if not vector:
        logger.warning('refresh_post_embedding: no vector for post %s', post.pk)
        return None
    return store_post_embedding(post, vector)


def semantic_search_posts(query_vector, limit=None, min_score=None, **filters):
    """
    pgvector cosine similarity search.

    Returns a list of (post, similarity_score) tuples ordered by
    relevance. Empty list when pgvector is unavailable.
    """
    if not vector_backend_available() or not query_vector:
        return []

    from pgvector.django import CosineDistance

    limit = limit or settings.AI_SEARCH_RESULTS
    min_score = settings.AI_SEARCH_MIN_SCORE if min_score is None else min_score

    qs = (
        PostEmbedding.objects
        .select_related('post', 'post__category', 'post__location')
        .annotate(distance=CosineDistance('embedding', query_vector))
        .order_by('distance')
    )
    post_type = filters.get('post_type')
    if post_type:
        qs = qs.filter(post__post_type=post_type)
    status = filters.get('status')
    if status:
        qs = qs.filter(post__status=status)
    category_slug = filters.get('category_slug')
    if category_slug:
        qs = qs.filter(post__category__slug=category_slug)
    location_slug = filters.get('location_slug')
    if location_slug:
        qs = qs.filter(post__location__slug=location_slug)

    results = []
    for pe in qs[:limit]:
        similarity = max(0.0, 1.0 - (pe.distance / 2.0))
        if similarity >= min_score:
            results.append((pe.post, round(similarity, 4)))
    return results


def keyword_search_posts(query, **filters):
    """Keyword fallback search (mandatory when AI is unavailable)."""
    qs = Post.objects.select_related('category', 'location')
    query = (query or '').strip()
    if query:
        qs = qs.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query) |
            Q(location_name__icontains=query)
        )
    post_type = filters.get('post_type')
    if post_type:
        qs = qs.filter(post_type=post_type)
    status = filters.get('status')
    if status:
        qs = qs.filter(status=status)
    category_slug = filters.get('category_slug')
    if category_slug:
        qs = qs.filter(category__slug=category_slug)
    location_slug = filters.get('location_slug')
    if location_slug:
        qs = qs.filter(location__slug=location_slug)
    return list(qs[:settings.AI_SEARCH_RESULTS])


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def compute_date_proximity(post_a, post_b):
    """0..1 factor: 1.0 same day, decaying to 0 after 14 days."""
    if not post_a.date_lost_found or not post_b.date_lost_found:
        return 0.0
    days_diff = abs((post_a.date_lost_found - post_b.date_lost_found).days)
    if days_diff <= 1:
        return 1.0
    if days_diff <= 3:
        return 0.75
    if days_diff <= 7:
        return 0.5
    if days_diff <= 14:
        return 0.25
    return 0.0


def tag_overlap(post_a, post_b):
    """Jaccard similarity of post tag names (0..1)."""
    try:
        tags_a = set(post_a.tags.values_list('name', flat=True))
        tags_b = set(post_b.tags.values_list('name', flat=True))
    except Exception:
        return 0.0
    if not tags_a or not tags_b:
        return 0.0
    union = tags_a | tags_b
    if not union:
        return 0.0
    return len(tags_a & tags_b) / len(union)


def hybrid_match_score(post_a, post_b, semantic_similarity):
    """
    Weighted blend of semantic similarity + structured attributes.

    Returns (final_score, metadata_score) tuple.

    Default weights (configurable via settings.AI_MATCH_WEIGHTS):
        semantic 60%, category 15%, location 10%, date 10%, tags 5%
    """
    weights = settings.AI_MATCH_WEIGHTS

    semantic_component = weights.get('semantic', 0.60) * max(0.0, min(1.0, semantic_similarity))
    metadata_component = 0.0
    if post_a.category_id and post_a.category_id == post_b.category_id:
        metadata_component += weights.get('category', 0.15)
    if post_a.location_id and post_a.location_id == post_b.location_id:
        metadata_component += weights.get('location', 0.10)
    metadata_component += weights.get('date', 0.10) * compute_date_proximity(post_a, post_b)
    metadata_component += weights.get('tags', 0.05) * tag_overlap(post_a, post_b)

    final_score = round(min(semantic_component + metadata_component, 1.0), 4)
    metadata_score = round(min(metadata_component, 1.0), 4)
    return final_score, metadata_score


def _ranked_candidates(post, query_vector):
    """
    Top-N opposite-type candidates with (post, semantic) tuples.
    Uses pgvector when available; falls back to in-Python scoring.
    """
    opposite_type = 'found' if post.post_type == 'lost' else 'lost'
    limit = settings.AI_MATCH_CANDIDATES

    if vector_backend_available():
        from pgvector.django import CosineDistance
        qs = (
            PostEmbedding.objects
            .filter(post__post_type=opposite_type, post__status='open')
            .exclude(post__pk=post.pk)
            .select_related('post', 'post__category', 'post__location')
            .annotate(distance=CosineDistance('embedding', query_vector))
            .order_by('distance')[:limit]
        )
        return [
            (pe.post, max(0.0, 1.0 - (pe.distance / 2.0)))
            for pe in qs
        ]

    candidates = (
        Post.objects
        .filter(post_type=opposite_type, status='open')
        .exclude(pk=post.pk)
        .select_related('category', 'location')
        .prefetch_related('tags')[:limit]
    )
    results = []
    for candidate in candidates:
        try:
            pe = PostEmbedding.objects.get(post=candidate)
            semantic = compute_cosine_similarity(query_vector, pe.embedding)
        except PostEmbedding.DoesNotExist:
            candidate_vector = generate_embedding(build_text_for_post(candidate))
            semantic = (
                compute_cosine_similarity(query_vector, candidate_vector)
                if candidate_vector else 0.0
            )
        results.append((candidate, semantic))
    return results


def _get_match_strength(score):
    """Classify a final hybrid score into match strength."""
    if score >= settings.AI_STRONG_MATCH_THRESHOLD:
        return 'strong'
    return 'possible'


def find_matches_for_post(post):
    """
    Find potential matches for a post after creation/update.

    Stores the post's embedding, searches the opposite post type via
    pgvector (top-N candidates), applies hybrid scoring, and upserts
    MatchSuggestion rows. Never raises - AI failure must not break
    post creation.
    """
    if not getattr(post, 'pk', None):
        return []

    post_text = build_text_for_post(post)
    try:
        post_vector = generate_embedding(post_text)
    except Exception as exc:
        logger.error('find_matches_for_post embedding error for post %s: %s', post.pk, exc)
        return []

    if not post_vector:
        logger.warning('AI matching skipped for post %s (embedding unavailable)', post.pk)
        return []

    store_post_embedding(post, post_vector)

    matches = []
    try:
        candidates = _ranked_candidates(post, post_vector)
    except Exception as exc:
        logger.error('find_matches_for_post candidate search error for post %s: %s', post.pk, exc)
        return []

    if hasattr(post, '_prefetched_objects_cache') is False:
        try:
            _ = list(post.tags.all())
        except Exception:
            pass

    for candidate, semantic in candidates:
        score, meta = hybrid_match_score(post, candidate, semantic)
        if score < settings.AI_MATCH_THRESHOLD:
            continue
        try:
            match, _created = MatchSuggestion.objects.update_or_create(
                post=post,
                matched_post=candidate,
                defaults={
                    'similarity_score': score,
                    'semantic_score': round(semantic, 4),
                    'metadata_score': meta,
                    'match_strength': _get_match_strength(score),
                },
            )
            matches.append(match)
        except Exception as exc:
            logger.error('match upsert failed (post %s <-> %s): %s',
                         post.pk, candidate.pk, exc)

    matches.sort(key=lambda m: m.similarity_score, reverse=True)
    logger.info(
        'Matching completed for post %s: %d candidates evaluated, %d matches created',
        post.pk, len(candidates), len(matches),
    )
    return matches[:settings.AI_MATCH_RESULTS]
