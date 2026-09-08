import logging
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Recovery tokens have no expiration. This command is kept for compatibility but does nothing.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Recovery tokens do not expire. No sessions were expired.'))
