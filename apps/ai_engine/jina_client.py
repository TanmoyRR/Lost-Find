"""
Jina AI Embeddings API client.

Reusable backend service that talks to the Jina Embeddings API.
The API key lives only on the backend - it is never exposed to the
browser, never logged, and never committed to the repository.
"""
import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# None = not checked yet, True/False = known state (cached for the process)
_availability = None


def is_configured():
    """True if a Jina API key is present in the environment."""
    return bool(getattr(settings, 'JINA_API_KEY', '').strip())


def is_available():
    """Cache-friendly availability flag (used to short-circuit UI calls)."""
    global _availability
    if _availability is None:
        _availability = is_configured()
    return _availability


def mark_unavailable():
    global _availability
    _availability = False


def get_embedding_model():
    return getattr(settings, 'JINA_EMBEDDING_MODEL', 'jina-embeddings-v5-text-nano')


def generate_embedding(text, model=None, max_chars=None):
    """
    Send `text` to the Jina Embeddings API and return the embedding as a
    Python list of floats.

    Returns None on any failure (missing key, network error, rate limit,
    invalid key, unexpected response). Never raises.
    """
    text = (text or '').strip()
    if not text:
        logger.warning('Jina: empty text, skipping embedding')
        return None

    api_key = getattr(settings, 'JINA_API_KEY', '').strip()
    if not api_key:
        logger.warning('Jina: JINA_API_KEY is not set, AI features disabled')
        mark_unavailable()
        return None

    url = getattr(settings, 'JINA_API_BASE_URL', 'https://api.jina.ai/v1/embeddings')
    timeout = getattr(settings, 'JINA_TIMEOUT', 30)
    max_retries = getattr(settings, 'JINA_MAX_RETRIES', 2)
    max_chars = max_chars or getattr(settings, 'JINA_MAX_INPUT_CHARS', 4000)

    payload = {
        'model': model or get_embedding_model(),
        'input': text[:max_chars],
        'dimensions': getattr(settings, 'JINA_EMBEDDING_DIMENSIONS', 256),
    }
    headers = {
        'Authorization': 'Bearer {}'.format(api_key),
        'Content-Type': 'application/json',
    }

    last_error = None
    for attempt in range(max_retries + 1):
        if attempt > 0:
            time.sleep(getattr(settings, 'JINA_RATE_LIMIT_DELAY', 0.3) * (attempt + 1))
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        except requests.Timeout:
            last_error = 'timeout after {}s'.format(timeout)
            logger.error('Jina: request timed out (attempt %s)', attempt + 1)
            continue
        except requests.ConnectionError as exc:
            last_error = 'connection error'
            logger.error('Jina: connection error (attempt %s): %s', attempt + 1, exc)
            continue
        except requests.RequestException as exc:
            last_error = 'request error'
            logger.error('Jina: request error (attempt %s): %s', attempt + 1, exc)
            continue

        if response.status_code == 200:
            try:
                data = response.json()
                embedding = data['data'][0]['embedding']
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                logger.error('Jina: unexpected response payload: %s', exc)
                return None
            if not isinstance(embedding, list) or not embedding:
                logger.error('Jina: empty embedding in response')
                return None
            _availability = True
            return embedding

        if response.status_code == 401:
            logger.error('Jina: invalid API key (401). Check JINA_API_KEY.')
            mark_unavailable()
            return None

        if response.status_code == 429:
            retry_after = response.headers.get('Retry-After')
            try:
                wait = float(retry_after)
            except (TypeError, ValueError):
                wait = 2.0
            last_error = 'rate limited (429)'
            logger.warning('Jina: rate limited, waiting %.1fs (attempt %s)', wait, attempt + 1)
            time.sleep(min(wait, 10))
            continue

        last_error = 'HTTP {}'.format(response.status_code)
        logger.error('Jina: API error HTTP %s (attempt %s): %s',
                     response.status_code, attempt + 1, response.text[:200])

    logger.error('Jina: embedding failed after retries (%s)', last_error)
    return None