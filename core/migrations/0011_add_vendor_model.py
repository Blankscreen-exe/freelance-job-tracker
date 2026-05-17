import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_add_job_note'),
    ]

    operations = [
        migrations.CreateModel(
            name='Vendor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('is_archived', models.BooleanField(default=False)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.RemoveField(
            model_name='expense',
            name='vendor',
        ),
        migrations.AddField(
            model_name='expense',
            name='vendor',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='expenses', to='core.vendor'),
        ),
    ]
