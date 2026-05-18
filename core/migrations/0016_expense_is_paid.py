from decimal import Decimal
from django.db import migrations, models
from django.db.models import Sum


def seed_expense_coverage(apps, schema_editor):
    Worker = apps.get_model('core', 'Worker')
    Payment = apps.get_model('core', 'Payment')
    Expense = apps.get_model('core', 'Expense')

    for worker in Worker.objects.filter(user__isnull=False).select_related('user'):
        cash_received = Payment.objects.filter(
            worker=worker, is_paid=True,
        ).aggregate(t=Sum('amount'))['t'] or Decimal(0)

        expenses = list(
            Expense.objects.filter(created_by=worker.user).order_by('expense_date', 'id')
        )
        running = Decimal(0)
        to_update = []
        for expense in expenses:
            running += expense.amount
            expense.is_paid = running <= cash_received
            to_update.append(expense)

        if to_update:
            Expense.objects.bulk_update(to_update, ['is_paid'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_rename_payment_amount'),
    ]

    operations = [
        migrations.AddField(
            model_name='expense',
            name='is_paid',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(seed_expense_coverage, migrations.RunPython.noop),
    ]
