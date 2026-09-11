import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.recovery.models import RecoverySession

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Expire recovery sessions that are older than 30 days and still pending/token_generated.'

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=30)
        expired = RecoverySession.objects.filter(
            status__in=('pending', 'token_generated'),
            created_at__lt=cutoff,
        )
        count = expired.count()
        if count:
            expired.update(status='expired')
            logger.info('Expired %d recovery sessions older than 30 days', count)
        self.stdout.write(self.style.SUCCESS(f'{count} recovery session(s) expired.'))
