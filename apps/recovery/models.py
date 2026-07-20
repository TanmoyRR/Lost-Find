from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid
import hashlib
import hmac
import json
import time

class RecoverySession(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('otp_sent', 'OTP Sent'),
        ('otp_verified', 'OTP Verified'),
        ('qr_generated', 'QR Generated'),
        ('qr_scanned', 'QR Scanned'),
        ('handover_verified', 'Handover Verified'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    )

    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    post = models.ForeignKey('posts.Post', on_delete=models.CASCADE, related_name='recovery_sessions')
    claimant = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='recovery_sessions')
    owner = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='owner_recovery_sessions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    qr_token = models.CharField(max_length=255, null=True, blank=True)
    qr_code = models.ImageField(upload_to='recovery_qr/', null=True, blank=True)
    qr_expires_at = models.DateTimeField(null=True, blank=True)
    qr_scanned_at = models.DateTimeField(null=True, blank=True)
    handover_verified_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Recovery Session'
        verbose_name_plural = 'Recovery Sessions'
        ordering = ['-created_at']

    def __str__(self):
        return f"Recovery {self.uid} - {self.post.title[:50]}"

    def generate_qr_token(self):
        import hashlib, hmac, json, time
        timestamp = int(time.time())
        payload = json.dumps({'session_uid': str(self.uid), 'timestamp': timestamp})
        secret = settings.SECRET_KEY.encode()
        signature = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
        self.qr_token = f"{str(self.uid)}.{timestamp}.{signature}"
        self.qr_expires_at = timezone.now() + timezone.timedelta(minutes=30)
        self.save(update_fields=['qr_token', 'qr_expires_at'])
        return self.qr_token

    def verify_qr_token(self, token):
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return False
            uid_str, timestamp, signature = parts
            if uid_str != str(self.uid):
                return False
            if timezone.now() > self.qr_expires_at:
                return False
            expected = hmac.new(settings.SECRET_KEY.encode(),
                json.dumps({'session_uid': uid_str, 'timestamp': int(timestamp)}).encode(),
                hashlib.sha256).hexdigest()
            return hmac.compare_digest(signature, expected)
        except Exception:
            return False

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
        return f"OTP for {self.session.uid}"

    def is_valid(self):
        return (not self.is_used and
                self.attempts < self.max_attempts and
                timezone.now() <= self.expires_at)

    def verify(self, code):
        if not self.is_valid():
            return False, 'OTP expired or already used'
        self.attempts += 1
        if self.attempts >= self.max_attempts:
            self.save(update_fields=['attempts'])
            return False, 'Maximum attempts exceeded'
        if self.otp_code == code:
            self.is_used = True
            self.verified_at = timezone.now()
            self.save(update_fields=['is_used', 'verified_at', 'attempts'])
            self.session.status = 'otp_verified'
            self.session.save(update_fields=['status'])
            return True, 'OTP verified successfully'
        self.save(update_fields=['attempts'])
        return False, 'Invalid OTP code'

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
        return f"{self.session.uid} - {self.action}"

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
        return f"Confirmation for {self.session.uid}"

    def is_complete(self):
        return self.confirmed_by_owner and self.confirmed_by_claimant