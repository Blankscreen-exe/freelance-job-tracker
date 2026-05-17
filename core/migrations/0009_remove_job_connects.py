from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_remove_job_upwork_ids'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='job',
            name='connects_used',
        ),
        migrations.RemoveField(
            model_name='job',
            name='connect_override_mode',
        ),
        migrations.RemoveField(
            model_name='job',
            name='connect_override_value',
        ),
    ]
