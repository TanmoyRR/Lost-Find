from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


class MembershipPlan(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.PositiveIntegerField(default=365)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Membership Plan'
        verbose_name_plural = 'Membership Plans'

    def __str__(self):
        return f"{self.name} - {self.price} BDT"


class Membership(models.Model):
    user = models.OneToOneField('accounts.User', on_delete=models.CASCADE, related_name='membership')
    plan = models.ForeignKey(MembershipPlan, on_delete=models.SET_NULL, null=True)
    is_active = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    auto_renew = models.BooleanField(default=False)
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

    def check_expiry(self):
        if self.is_active and self.expires_at and self.expires_at < timezone.now():
            self.is_active = False
            self.save()
            from apps.accounts.models import UserActivity
            UserActivity.objects.create(
                user=self.user,
                activity_type='membership_expired',
                description='Membership has expired'
            )
