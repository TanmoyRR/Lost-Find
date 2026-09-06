from django.db import models
from django.conf import settings
from django.core.cache import cache


def invalidate_notification_cache(user_id):
    """Invalidate the notification cache for a user."""
    cache.delete(f'notif_{user_id}')


class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('match_found', 'Match Found'),
        ('membership_expiring', 'Membership Expiring'),
        ('post_claimed', 'Post Claimed'),
        ('post_resolved', 'Post Resolved'),
        ('message', 'Message'),
        ('system', 'System'),
        ('recovery_update', 'Recovery Update'),
    )

    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read'], name='notif_user_read_idx'),
            models.Index(fields=['user', '-created_at'], name='notif_user_created_idx'),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.title}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        invalidate_notification_cache(self.user_id)

    def mark_as_read(self):
        if not self.is_read:
            from django.utils import timezone as tz
            self.is_read = True
            self.read_at = tz.now()
            self.save(update_fields=['is_read', 'read_at'])
