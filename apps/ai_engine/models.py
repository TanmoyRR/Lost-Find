from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError

try:
    from pgvector.django import VectorField
except ImportError:
    from django.db.models import JSONField as VectorField


class PostEmbedding(models.Model):
    post = models.OneToOneField('posts.Post', on_delete=models.CASCADE, related_name='embedding')
    embedding = VectorField(dimensions=settings.AI_EMBEDDING_DIMENSIONS)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Post Embedding'
        verbose_name_plural = 'Post Embeddings'

    def __str__(self):
        return f"Embedding for {self.post.title[:50]}"


class MatchSuggestion(models.Model):
    MATCH_STATUS = (
        ('pending', 'Pending Review'),
        ('accepted', 'Accepted'),
        ('dismissed', 'Dismissed'),
    )
    MATCH_STRENGTH = (
        ('strong', 'Strong Match'),
        ('possible', 'Possible Match'),
    )

    post = models.ForeignKey('posts.Post', on_delete=models.CASCADE, related_name='match_suggestions')
    matched_post = models.ForeignKey('posts.Post', on_delete=models.CASCADE, related_name='incoming_matches')
    similarity_score = models.FloatField(default=0.0)
    semantic_score = models.FloatField(default=0.0)
    metadata_score = models.FloatField(default=0.0)
    match_strength = models.CharField(max_length=10, choices=MATCH_STRENGTH, default='possible')
    status = models.CharField(max_length=20, choices=MATCH_STATUS, default='pending')
    is_viewed = models.BooleanField(default=False)
    is_accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Match Suggestion'
        verbose_name_plural = 'Match Suggestions'
        constraints = [
            models.UniqueConstraint(fields=['post', 'matched_post'], name='unique_match_suggestion'),
        ]
        ordering = ['-similarity_score']
        indexes = [
            models.Index(fields=['status', '-similarity_score'], name='match_status_score_idx'),
        ]

    def save(self, *args, **kwargs):
        if self.post_id and self.matched_post_id and self.post_id == self.matched_post_id:
            raise ValidationError('A post cannot match itself.')
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            try:
                from apps.notifications.models import Notification
                from django.urls import reverse
                strength_label = self.get_match_strength_display()
                pct = int(round(self.similarity_score * 100))
                msg = (
                    f'AI {strength_label}: "{self.post.title}" may match '
                    f'"{self.matched_post.title}" ({pct}% similarity)'
                )

                Notification.objects.create(
                    user=self.post.user,
                    notification_type='match_found',
                    title='Potential Match Found!',
                    message=msg,
                    link=reverse('posts:detail', args=[self.matched_post.pk]),
                )
                if self.matched_post.user_id and self.matched_post.user_id != self.post.user_id:
                    Notification.objects.create(
                        user=self.matched_post.user,
                        notification_type='match_found',
                        title='Potential Match Found!',
                        message=(
                            f'AI {strength_label}: "{self.matched_post.title}" may match '
                            f'"{self.post.title}" ({pct}% similarity)'
                        ),
                        link=reverse('posts:detail', args=[self.post.pk]),
                    )
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Failed to create match notification')

    def __str__(self):
        return f"Match: {self.post.title[:30]} <-> {self.matched_post.title[:30]} ({self.similarity_score:.0%})"
