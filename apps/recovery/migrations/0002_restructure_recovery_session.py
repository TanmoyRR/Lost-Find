import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.recovery.models


class Migration(migrations.Migration):

    dependencies = [
        ('posts', '0004_add_location_name_remove_reward'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('recovery', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='recoverysession',
            name='uid',
        ),
        migrations.RemoveField(
            model_name='recoverysession',
            name='qr_token',
        ),
        migrations.RemoveField(
            model_name='recoverysession',
            name='qr_expires_at',
        ),
        migrations.RemoveField(
            model_name='recoverysession',
            name='handover_verified_at',
        ),
        migrations.AddField(
            model_name='recoverysession',
            name='short_code',
            field=models.CharField(
                db_index=True, default=apps.recovery.models.generate_short_code,
                max_length=10, unique=True,
            ),
        ),
        migrations.AlterField(
            model_name='recoverysession',
            name='claimant',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='recovery_sessions',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='recoverysession',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('qr_generated', 'QR Generated'),
                    ('qr_scanned', 'QR Scanned'),
                    ('completed', 'Completed'),
                    ('expired', 'Expired'),
                    ('cancelled', 'Cancelled'),
                ],
                default='pending', max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='recoveryverificationlog',
            name='session',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='verification_logs',
                to='recovery.recoverysession',
            ),
        ),
        migrations.AddIndex(
            model_name='recoverysession',
            index=models.Index(
                fields=['post', 'status'],
                name='recovery_post_status_idx',
            ),
        ),

    ]
