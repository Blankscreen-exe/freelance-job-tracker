from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_split_theme_colors'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='job',
            name='upwork_job_id',
        ),
        migrations.RemoveField(
            model_name='job',
            name='upwork_contract_id',
        ),
        migrations.RemoveField(
            model_name='job',
            name='upwork_offer_id',
        ),
    ]
