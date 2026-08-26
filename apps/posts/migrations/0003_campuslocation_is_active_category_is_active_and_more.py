from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('posts', '0002_postimage_successstory_trustreport_posttag'),
    ]

    operations = [
        migrations.AddField(
            model_name='campuslocation',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='category',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='post',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
