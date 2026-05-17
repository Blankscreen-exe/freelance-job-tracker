from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_add_vendor_model'),
    ]

    operations = [
        migrations.CreateModel(
            name='SmtpSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_enabled', models.BooleanField(default=False)),
                ('host', models.CharField(blank=True, default='', max_length=200)),
                ('port', models.PositiveIntegerField(default=587)),
                ('username', models.CharField(blank=True, default='', max_length=200)),
                ('password', models.CharField(blank=True, default='', max_length=200)),
                ('use_tls', models.BooleanField(default=True)),
                ('use_ssl', models.BooleanField(default=False)),
                ('from_email', models.EmailField(blank=True, default='')),
                ('from_name', models.CharField(blank=True, default='', max_length=100)),
            ],
            options={
                'verbose_name': 'SMTP Settings',
                'verbose_name_plural': 'SMTP Settings',
            },
        ),
    ]
