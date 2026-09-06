from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.payments.models import Payment
from apps.accounts.models import UserActivity
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Mark stale pending payments as failed (older than 24 hours)'

    def add_arguments(self, parser):
        parser.add_argument('--hours', type=int, default=24, help='Hours after which a pending payment is considered stale (default: 24)')

    def handle(self, *args, **options):
        hours = options['hours']
        cutoff = timezone.now() - timedelta(hours=hours)
        stale = Payment.objects.filter(
            status='pending',
            created_at__lt=cutoff,
        )
        count = stale.count()
        for payment in stale:
            payment.status = 'failed'
            payment.save(update_fields=['status'])
        if count:
            logger.info('Marked %d stale pending payments as failed (older than %dh)', count, hours)
        self.stdout.write(self.style.SUCCESS(f'Marked {count} stale pending payments as failed'))
