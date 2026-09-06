from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


class MembershipPlan(models.Model):
    name = models.CharField(max_length=100, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.PositiveIntegerField(default=365)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Membership Plan'
        verbose_name_plural = 'Membership Plans'
        ordering = ['price']

    def __str__(self):
        return f"{self.name} - {self.price} BDT"


class Membership(models.Model):
    user = models.OneToOneField('accounts.User', on_delete=models.CASCADE, related_name='membership')
    plan = models.ForeignKey(MembershipPlan, on_delete=models.SET_NULL, null=True)
    is_active = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Membership'
        verbose_name_plural = 'Memberships'

    def __str__(self):
        return f"{self.user.username} - {'Active' if self.is_active else 'Inactive'}"

    def days_remaining(self):
        if self.expires_at and self.is_active:
            remaining = (self.expires_at - timezone.now()).days
            return max(0, remaining)
        return 0

    def days_remaining_pct(self):
        if self.plan and self.plan.duration_days and self.plan.duration_days > 0:
            return min(100, round(self.days_remaining() / self.plan.duration_days * 100))
        return min(100, self.days_remaining())
