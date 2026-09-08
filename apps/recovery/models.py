import hmac
import logging
import secrets
import string

from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


def generate_short_code():
    """Generate a short random code like LF-7K29QX."""
    alphabet = string.ascii_uppercase + string.digits
    code = ''.join(secrets.choice(alphabet) for _ in range(6))
    return f'LF-{code}'


class RecoverySession(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('token_generated', 'Token Generated'),
        ('token_entered', 'Token Entered'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    )

    post = models.ForeignKey('posts.Post', on_delete=models.CASCADE, related_name='recovery_sessions')
    owner = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='owner_recovery_sessions')
    claimant = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE,
        related_name='recovery_sessions', null=True, blank=True,
    )
    short_code = models.CharField(max_length=10, unique=True, db_index=True, default=generate_short_code)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    token_verified_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Recovery Session'
        verbose_name_plural = 'Recovery Sessions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status'], name='recovery_status_idx'),
            models.Index(fields=['owner', 'status'], name='recovery_owner_status_idx'),
            models.Index(fields=['post', 'status'], name='recovery_post_status_idx'),
        ]

    def __str__(self):
        return f"Recovery {self.short_code} - {self.post.title[:50]}"

    def is_expired(self):
        if self.expires_at and timezone.now() > self.expires_at:
            return True
        return False

    def save(self, *args, **kwargs):
        if not self.short_code:
            self.short_code = generate_short_code()
            while RecoverySession.objects.filter(short_code=self.short_code).exists():
                self.short_code = generate_short_code()
        super().save(*args, **kwargs)


class RecoveryVerificationLog(models.Model):
    session = models.ForeignKey(RecoverySession, on_delete=models.CASCADE, related_name='verification_logs')
    action = models.CharField(max_length=50)
    performed_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Recovery Verification Log'
        verbose_name_plural = 'Recovery Verification Logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.session.short_code} - {self.action}"
