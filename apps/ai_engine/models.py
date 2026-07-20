from django.db import models
from django.conf import settings


class PostEmbedding(models.Model):
    post = models.OneToOneField('posts.Post', on_delete=models.CASCADE, related_name='embedding')
    embedding = models.JSONField()
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

    post = models.ForeignKey('posts.Post', on_delete=models.CASCADE, related_name='match_suggestions')
    matched_post = models.ForeignKey('posts.Post', on_delete=models.CASCADE, related_name='incoming_matches')
    similarity_score = models.FloatField(default=0.0)
    status = models.CharField(max_length=20, choices=MATCH_STATUS, default='pending')
    is_viewed = models.BooleanField(default=False)
    is_accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Match Suggestion'
        verbose_name_plural = 'Match Suggestions'
        unique_together = ['post', 'matched_post']
        ordering = ['-similarity_score']

    def __str__(self):
        return f"Match: {self.post.title[:30]} <-> {self.matched_post.title[:30]} ({self.similarity_score:.0%})"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            from apps.notifications.models import Notification
            Notification.objects.create(
                user=self.post.user,
                notification_type='match_found',
                title='Potential Match Found!',
                message=f'Your "{self.post.title}" may match "{self.matched_post.title}" (confidence: {self.similarity_score:.0%})',
                link=self.matched_post.get_absolute_url() if hasattr(self.matched_post, 'get_absolute_url') else f'/post/{self.matched_post.pk}/',
            )