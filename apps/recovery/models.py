import logging
import secrets
import string

from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator

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

    def save(self, *args, **kwargs):
        if not self.short_code:
            self.short_code = generate_short_code()
            while RecoverySession.objects.filter(short_code=self.short_code).exists():
                self.short_code = generate_short_code()
        super().save(*args, **kwargs)

    def verify_and_complete(self, token, scanned_by):
        """
        Validate the recovery token and atomically complete the recovery.

        Returns (success: bool, message: str).
        """
        from apps.notifications.models import Notification
        from apps.recovery.models import RecoveryVerificationLog

        if self.status not in ('token_generated',):
            return False, 'This recovery session is no longer active.'

        if not self.claimant:
            return False, 'No authorized finder has been assigned to this session.'

        if scanned_by != self.claimant:
            return False, 'Only the authorized finder can complete this recovery.'

        cleaned = (token or '').strip().upper()
        if cleaned != self.short_code:
            return False, 'Invalid recovery token.'

        with transaction.atomic():
            self.status = 'completed'
            self.token_verified_at = timezone.now()
            self.completed_at = timezone.now()
            self.save(update_fields=['status', 'token_verified_at', 'completed_at'])

            self.post.status = 'resolved'
            self.post.is_resolved = True
            self.post.save(update_fields=['status', 'is_resolved'])

            RecoveryVerificationLog.objects.create(
                session=self, action='token_entered',
                performed_by=scanned_by,
                ip_address=None,
            )
            RecoveryVerificationLog.objects.create(
                session=self, action='recovery_completed',
                performed_by=scanned_by,
                ip_address=None,
            )

            Notification.objects.create(
                user=self.owner,
                notification_type='post_resolved',
                title='Item Successfully Recovered',
                message=f'Your item "{self.post.title}" has been successfully recovered.',
                link=f'/recovery/',
            )
            Notification.objects.create(
                user=self.claimant,
                notification_type='post_resolved',
                title='Recovery Completed',
                message=f'You have successfully completed the recovery of "{self.post.title}".',
                link=f'/recovery/',
            )

        logger.info('Recovery %s completed by finder %s', self.short_code, scanned_by.pk)
        return True, 'Recovery completed successfully!'


class RecoveryOTP(models.Model):
    session = models.ForeignKey(RecoverySession, on_delete=models.CASCADE, related_name='otps')
    otp_code = models.CharField(max_length=6)
    is_used = models.BooleanField(default=False)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Recovery OTP'
        verbose_name_plural = 'Recovery OTPs'
        ordering = ['-created_at']

    def __str__(self):
        return f"OTP for {self.session.short_code}"


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


class RecoveryConfirmation(models.Model):
    session = models.OneToOneField(RecoverySession, on_delete=models.CASCADE, related_name='confirmation')
    confirmed_by_owner = models.BooleanField(default=False)
    confirmed_by_claimant = models.BooleanField(default=False)
    owner_confirmed_at = models.DateTimeField(null=True, blank=True)
    claimant_confirmed_at = models.DateTimeField(null=True, blank=True)
    owner_signature = models.TextField(blank=True, null=True)
    claimant_signature = models.TextField(blank=True, null=True)
    feedback = models.TextField(blank=True, null=True)
    rating = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Recovery Confirmation'
        verbose_name_plural = 'Recovery Confirmations'

    def __str__(self):
        return f"Confirmation for {self.session.short_code}"
