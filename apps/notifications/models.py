from django.db import models
from django.conf import settings


class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('match_found', 'Match Found'),
        ('membership_expiring', 'Membership Expiring'),
        ('post_claimed', 'Post Claimed'),
        ('post_resolved', 'Post Resolved'),
        ('message', 'Message'),
        ('system', 'System'),
    )

    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.title}"
