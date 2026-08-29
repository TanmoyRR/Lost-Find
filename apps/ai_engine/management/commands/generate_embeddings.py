import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from apps.ai_engine import jina_client
from apps.ai_engine.models import PostEmbedding
from apps.ai_engine.utils import (
    build_text_for_post,
    generate_embedding,
    reset_vector_backend_cache,
    store_post_embedding,
    vector_backend_available,
)
from apps.posts.models import Post


class Command(BaseCommand):
    help = (
        'Ensure pgvector is set up and backfill/generate embeddings for all posts '
        'via the Jina API. Safe to run multiple times - only posts with missing or '
        'outdated embeddings are processed.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--only-missing',
            action='store_true',
            help='Only generate embeddings for posts that do not have one yet.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Maximum number of posts to process (0 = all).',
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=0.0,
            help='Seconds to sleep between API calls (default 0.3, set 0 for tests).',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Regenerate embeddings for all posts, even if they already exist.',
        )

    def handle(self, *args, **options):
        self.setup_pgvector()

        reset_vector_backend_cache()
        if not vector_backend_available():
            if connection.vendor != 'postgresql':
                self.stderr.write(
                    self.style.WARNING(
                        'Current database is not PostgreSQL with pgvector. '
                        'Embeddings cannot be stored. Switching to the Supabase '
                        'PostgreSQL database (DB_* env vars) fixes this.'
                    )
                )
            else:
                self.stderr.write(
                    self.style.ERROR(
                        'pgvector extension is not available on this database. '
                        'Run: CREATE EXTENSION IF NOT EXISTS vector;  (or run '
                        'this command as the postgres role)'
                    )
                )
            return

        if not jina_client.is_configured():
            self.stderr.write(
                self.style.ERROR('JINA_API_KEY is not set. Add it to .env / environment.')
            )
            return

        model_name = settings.JINA_EMBEDDING_MODEL
        self.stdout.write(
            self.style.SUCCESS(
                f'Using Jina model "{model_name}" '
                f'(dimensions={settings.JINA_EMBEDDING_DIMENSIONS})'
            )
        )

        posts = Post.objects.all().order_by('created_at')
        if options['only_missing'] or not options['force']:
            existing = set(
                PostEmbedding.objects.all().values_list('post_id', flat=True)
            )
            if options['force']:
                existing = set()
            posts = [p for p in posts if p.pk not in existing]

        if options['limit']:
            posts = posts[: options['limit']]

        total = len(posts)
        self.stdout.write(f'Processing {total} post(s)...')

        generated, skipped, failed = 0, 0, 0
        for index, post in enumerate(posts, start=1):
            text = build_text_for_post(post)
            vector = generate_embedding(text)
            if vector is None:
                failed += 1
                self.stderr.write(f'  [{index}/{total}] FAILED (no embedding): {post.title}')
            else:
                stored = store_post_embedding(post, vector)
                if stored:
                    generated += 1
                    self.stdout.write(f'  [{index}/{total}] OK: {post.title}')
                else:
                    skipped += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f'  [{index}/{total}] SKIPPED store (vector backend?): {post.title}'
                        )
                    )
            # Rate-limit: sleep between API calls to avoid 429s
            if options['delay'] and index < total:
                time.sleep(options['delay'])

        self.stdout.write(
            self.style.SUCCESS(
                f'Done. Generated: {generated}, skipped: {skipped}, failed: {failed}'
            )
        )

    def setup_pgvector(self):
        """Idempotent pgvector setup: extension + HNSW index."""
        if connection.vendor != 'postgresql':
            return
        with connection.cursor() as cursor:
            try:
                cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')
                self.stdout.write(
                    self.style.SUCCESS('pgvector extension ready.')
                )
            except Exception as exc:
                self.stderr.write(
                    self.style.WARNING(
                        f'Could not create pgvector extension: {exc}. '
                        'Run manually in Supabase SQL Editor: CREATE EXTENSION IF NOT EXISTS vector;'
                    )
                )
                return
            try:
                cursor.execute(
                    'CREATE INDEX IF NOT EXISTS ai_engine_postembedding_embedding_hnsw '
                    'ON ai_engine_postembedding USING hnsw (embedding vector_cosine_ops)'
                )
                self.stdout.write(
                    self.style.SUCCESS('HNSW vector index ready.')
                )
            except Exception as exc:
                self.stderr.write(
                    self.style.WARNING(
                        f'Could not create HNSW index: {exc}. '
                        'The app still works, searches will be a bit slower.'
                    )
                )