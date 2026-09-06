import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.posts.models import Post

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Auto-close open posts older than a specified number of days'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=90, help='Days after which open posts are auto-closed (default: 90)')

    def handle(self, *args, **options):
        days = options['days']
        cutoff = timezone.now() - timedelta(days=days)
        posts = Post.objects.filter(status='open', created_at__lt=cutoff)
        count = posts.count()
        posts.update(status='closed')
        if count:
            logger.info('Auto-closed %d open posts older than %d days', count, days)
        self.stdout.write(self.style.SUCCESS(f'Auto-closed {count} posts older than {days} days'))
