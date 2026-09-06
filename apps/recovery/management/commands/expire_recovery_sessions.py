import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.recovery.models import RecoverySession, RecoveryVerificationLog

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Expire recovery sessions that have passed their TTL'

    def handle(self, *args, **options):
        expired = RecoverySession.objects.filter(
            status__in=('pending', 'token_generated'),
            expires_at__lte=timezone.now(),
        )
        count = 0
        for session in expired:
            session.status = 'expired'
            session.save(update_fields=['status'])
            RecoveryVerificationLog.objects.create(
                session=session,
                action='session_expired',
                details={'reason': 'TTL exceeded'},
            )
            count += 1
        if count:
            logger.info('Expired %d recovery sessions', count)
        self.stdout.write(self.style.SUCCESS(f'Expired {count} recovery sessions'))
