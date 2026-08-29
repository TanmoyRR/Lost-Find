# Generated manually: migrates PostEmbedding.embedding from JSON (old local
# SentenceTransformer vectors) to a pgvector column (Jina API embeddings).
#
# 1. Enables the pgvector extension on PostgreSQL (no-op elsewhere / if present)
# 2. Deletes old embedding rows - their 384-dim local-model vectors are
#    incompatible with the new model; they are regenerated via the Jina API
#    by `python manage.py generate_embeddings`
# 3. Converts the column to vector(256)
# 4. Creates an HNSW index for fast cosine similarity search

from django.db import migrations, models
from pgvector.django import VectorField


def create_extension(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        with schema_editor.connection.cursor() as cursor:
            cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')


def drop_extension(apps, schema_editor):
    pass


def delete_old_embeddings(apps, schema_editor):
    PostEmbedding = apps.get_model('ai_engine', 'PostEmbedding')
    PostEmbedding.objects.all().delete()


def reverse_delete(apps, schema_editor):
    pass


def create_hnsw_index(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS ai_engine_postembedding_embedding_hnsw '
                'ON ai_engine_postembedding USING hnsw (embedding vector_cosine_ops)'
            )


def drop_hnsw_index(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        with schema_editor.connection.cursor() as cursor:
            cursor.execute('DROP INDEX IF EXISTS ai_engine_postembedding_embedding_hnsw')


def alter_embedding_column_forward(apps, schema_editor):
    """ALTER COLUMN only on PostgreSQL; skip on SQLite/other backends."""
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            'ALTER TABLE ai_engine_postembedding '
            'ALTER COLUMN embedding TYPE vector(256) '
            'USING embedding::text::vector(256)'
        )


def alter_embedding_column_reverse(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            'ALTER TABLE ai_engine_postembedding '
            'ALTER COLUMN embedding TYPE jsonb '
            'USING embedding::text::jsonb'
        )


class Migration(migrations.Migration):

    dependencies = [
        ('ai_engine', '0002_matchsuggestion_status_matchsuggestion_updated_at_and_more'),
    ]

    operations = [
        migrations.RunPython(create_extension, drop_extension),
        migrations.RunPython(delete_old_embeddings, reverse_delete),
        migrations.RunPython(alter_embedding_column_forward, alter_embedding_column_reverse),
        migrations.AlterField(
            model_name='postembedding',
            name='embedding',
            field=VectorField(dimensions=256),
        ),
        migrations.RunPython(create_hnsw_index, drop_hnsw_index),
    ]