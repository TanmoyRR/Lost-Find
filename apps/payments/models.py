from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


class Payment(models.Model):
    PAYMENT_STATUS = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    )

    PAYMENT_TYPES = (
        ('membership', 'Membership'),
        ('reward', 'Reward'),
    )

    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='payments')
    transaction_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPES, default='membership')
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    sslcommerz_session = models.TextField(blank=True, null=True)
    sslcommerz_tran_id = models.CharField(max_length=100, null=True, blank=True)
    reference_id = models.CharField(max_length=100, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.amount} BDT - {self.status}"
