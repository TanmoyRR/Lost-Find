from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.membership.models import Membership
from apps.accounts.models import UserActivity


class Command(BaseCommand):
    help = 'Deactivate expired memberships and sync User.is_membership_paid'

    def handle(self, *args, **options):
        now = timezone.now()
        expired = Membership.objects.filter(
            is_active=True,
            expires_at__lt=now,
        )
        count = 0
        for membership in expired:
            membership.is_active = False
            membership.save(update_fields=['is_active'])
            if membership.user.is_membership_paid:
                membership.user.is_membership_paid = False
                membership.user.save(update_fields=['is_membership_paid'])
            UserActivity.objects.create(
                user=membership.user,
                activity_type='membership_expired',
                description='Membership has expired (auto-cleanup)',
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f'Deactivated {count} expired memberships.'))
