import numpy as np
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from sklearn.metrics.pairwise import cosine_similarity
import os
import pickle
import hashlib

from .models import PostEmbedding, MatchSuggestion
from apps.posts.models import Post

_model = None


def get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            model_name = settings.AI_MODEL_NAME
            cache_dir = settings.AI_MODEL_CACHE_DIR
            _model = SentenceTransformer(model_name, cache_folder=cache_dir)
        except Exception as e:
            print(f"AI Model load error: {e}")
            _model = None
    return _model


def generate_embedding(text):
    model = get_model()
    if model is None:
        return None
    try:
        embedding = model.encode(text).tolist()
        return embedding
    except Exception as e:
        print(f"Embedding error: {e}")
        return None


def compute_similarity(embedding1, embedding2):
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity
    if embedding1 is None or embedding2 is None:
        return 0.0
    vec1 = np.array(embedding1).reshape(1, -1)
    vec2 = np.array(embedding2).reshape(1, -1)
    return float(cosine_similarity(vec1, vec2)[0][0])


def build_text_for_post(post):
    parts = [post.title, post.description]
    if post.category:
        parts.append(post.category.name)
    if post.location:
        parts.append(post.location.name)
    return " ".join(parts)


def compute_date_proximity(post_a, post_b):
    if post_a.date_lost_found and post_b.date_lost_found:
        days_diff = abs((post_a.date_lost_found - post_b.date_lost_found).days)
        if days_diff <= 1:
            return 0.2
        elif days_diff <= 3:
            return 0.15
        elif days_diff <= 7:
            return 0.1
        elif days_diff <= 14:
            return 0.05
    return 0.0


def find_matches_for_post(post):
    from .models import PostEmbedding, MatchSuggestion
    from apps.posts.models import Post
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity

    post_text = build_text_for_post(post)
    post_embedding = generate_embedding(post_text)
    if post_embedding is None:
        return []

    PostEmbedding.objects.update_or_create(post=post, defaults={'embedding': post_embedding})

    opposite_type = 'found' if post.post_type == 'lost' else 'lost'
    candidates = Post.objects.filter(post_type=opposite_type, status='open').exclude(pk=post.pk)

    matches = []
    for candidate in candidates:
        try:
            candidate_embedding = PostEmbedding.objects.get(post=candidate)
            semantic_score = compute_cosine_similarity(post_embedding, candidate_embedding.embedding)
            date_bonus = compute_date_proximity(post, candidate)
            final_score = min(semantic_score + date_bonus, 1.0)
            if final_score > 0.4:
                match, created = MatchSuggestion.objects.update_or_create(
                    post=post,
                    matched_post=candidate,
                    defaults={'similarity_score': final_score}
                )
                matches.append(match)
        except PostEmbedding.DoesNotExist:
            candidate_text = build_text_for_post(candidate)
            candidate_embedding = generate_embedding(candidate_text)
            if candidate_embedding:
                PostEmbedding.objects.create(post=candidate, embedding=candidate_embedding)
                semantic_score = compute_cosine_similarity(post_embedding, candidate_embedding)
                date_bonus = compute_date_proximity(post, candidate)
                final_score = min(semantic_score + date_bonus, 1.0)
                if final_score > 0.4:
                    match, created = MatchSuggestion.objects.update_or_create(
                        post=post,
                        matched_post=candidate,
                        defaults={'similarity_score': final_score}
                    )
                    matches.append(match)

    return matches


def compute_cosine_similarity(emb1, emb2):
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity
    vec1 = np.array(emb1).reshape(1, -1)
    vec2 = np.array(emb2).reshape(1, -1)
    return float(cosine_similarity(vec1, vec2)[0][0])