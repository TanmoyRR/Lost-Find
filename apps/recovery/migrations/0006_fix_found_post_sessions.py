from django.db import migrations


def fix_found_post_sessions(apps, schema_editor):
    Post = apps.get_model('posts', 'Post')
    RecoverySession = apps.get_model('recovery', 'RecoverySession')
    for session in RecoverySession.objects.select_related('post', 'owner', 'claimant').filter(
        post__post_type='found',
    ):
        if session.owner_id == session.post.user_id:
            old_owner = session.owner_id
            old_claimant = session.claimant_id
            session.owner_id = old_claimant
            session.claimant_id = old_owner
            session.save(update_fields=['owner', 'claimant'])


def reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('recovery', '0005_recoverysession_expires_at'),
        ('posts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(fix_found_post_sessions, reverse),
    ]
