from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_add_expense_category'),
    ]

    operations = [
        migrations.RenameField(
            model_name='payment',
            old_name='amount_paid',
            new_name='amount',
        ),
    ]
