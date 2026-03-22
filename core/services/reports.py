"""
Report services for P&L and accounting ledger.
Reuses get_visible_jobs, get_job_totals, and other calculation functions.
"""
from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum, Q

from core.models import (
    Job, Receipt, Payment, Expense, ReceiptDistribution,
)
from core.services.calculations import get_job_totals, quantize_decimal


def get_pnl_data(user, date_from, date_to, visible_jobs):
    """Build a P&L report dict scoped to user's role.

    Args:
        user: current User
        date_from, date_to: date range
        visible_jobs: pre-filtered Job queryset from get_visible_jobs()

    Returns dict with revenue, deductions, payouts, expenses, profit, margin.
    """
    is_admin = user.is_admin_user()
    job_ids = list(visible_jobs.values_list('id', flat=True))

    # Revenue: receipts in period for visible jobs
    revenue = Receipt.objects.filter(
        job_id__in=job_ids,
        received_date__gte=date_from,
        received_date__lte=date_to,
    ).aggregate(total=Sum('amount_received'))['total'] or Decimal(0)
    revenue = quantize_decimal(revenue)

    # Connect deductions and platform fees — proportional to period receipts
    connect_deductions = Decimal(0)
    platform_fees = Decimal(0)

    jobs_with_receipts = visible_jobs.filter(
        receipts__received_date__gte=date_from,
        receipts__received_date__lte=date_to,
    ).distinct().select_related('settings_version')

    for job in jobs_with_receipts:
        job_totals = get_job_totals(job)

        # Total receipts for this job (all time)
        total_job_receipts = job.receipts.aggregate(
            t=Sum('amount_received')
        )['t'] or Decimal(0)

        # Receipts in period for this job
        period_receipts = job.receipts.filter(
            received_date__gte=date_from,
            received_date__lte=date_to,
        ).aggregate(t=Sum('amount_received'))['t'] or Decimal(0)

        if total_job_receipts > 0:
            ratio = Decimal(str(period_receipts)) / Decimal(str(total_job_receipts))
            connect_deductions += job_totals['connect_deduction'] * ratio
            platform_fees += job_totals['platform_fee'] * ratio

    connect_deductions = quantize_decimal(connect_deductions)
    platform_fees = quantize_decimal(platform_fees)
    gross_profit = quantize_decimal(revenue - connect_deductions - platform_fees)

    # Worker payouts (paid) in period for visible jobs
    worker_payouts = Payment.objects.filter(
        job_id__in=job_ids,
        is_paid=True,
        paid_date__gte=date_from,
        paid_date__lte=date_to,
    ).aggregate(total=Sum('amount_paid'))['total'] or Decimal(0)
    worker_payouts = quantize_decimal(worker_payouts)

    # Expenses — admin only
    expenses_by_category = OrderedDict()
    total_expenses = Decimal(0)

    if is_admin:
        expense_qs = Expense.objects.filter(
            expense_date__gte=date_from,
            expense_date__lte=date_to,
        ).values('category').annotate(total=Sum('amount')).order_by('category')

        category_labels = dict(Expense.Category.choices)

        for row in expense_qs:
            label = category_labels.get(row['category'], row['category'])
            amount = quantize_decimal(row['total'] or 0)
            expenses_by_category[label] = amount
            total_expenses += amount

        total_expenses = quantize_decimal(total_expenses)

    # Net profit
    if is_admin:
        net_profit = quantize_decimal(gross_profit - worker_payouts - total_expenses)
    else:
        net_profit = quantize_decimal(gross_profit - worker_payouts)

    margin = quantize_decimal(
        (net_profit / revenue * 100) if revenue > 0 else Decimal(0)
    )

    return {
        'is_admin': is_admin,
        'date_from': date_from,
        'date_to': date_to,
        'revenue': revenue,
        'connect_deductions': connect_deductions,
        'platform_fees': platform_fees,
        'gross_profit': gross_profit,
        'worker_payouts': worker_payouts,
        'expenses_by_category': expenses_by_category,
        'total_expenses': total_expenses,
        'net_profit': net_profit,
        'margin': margin,
    }


def get_ledger_entries(user, date_from, date_to, visible_jobs, entry_type=None):
    """Build chronological list of financial transactions.

    Returns list of dicts: [{date, type, description, amount, reference, job_code}, ...]
    Sorted by date descending.
    """
    is_admin = user.is_admin_user()
    job_ids = list(visible_jobs.values_list('id', flat=True))
    entries = []

    # Receipts (positive)
    if entry_type in (None, 'receipt'):
        receipts = Receipt.objects.filter(
            job_id__in=job_ids,
            received_date__gte=date_from,
            received_date__lte=date_to,
        ).select_related('job')
        for r in receipts:
            entries.append({
                'date': r.received_date,
                'type': 'receipt',
                'description': f'{r.get_source_display()} payment' if hasattr(r, 'get_source_display') else 'Payment received',
                'amount': r.amount_received,
                'reference': r.upwork_transaction_id or '',
                'job_code': r.job.job_code if r.job else '',
            })

    # Payments (negative)
    if entry_type in (None, 'payment'):
        payments = Payment.objects.filter(
            job_id__in=job_ids,
            is_paid=True,
            paid_date__gte=date_from,
            paid_date__lte=date_to,
        ).select_related('worker', 'job')
        for p in payments:
            entries.append({
                'date': p.paid_date,
                'type': 'payment',
                'description': f'Payment to {p.worker.name}' if p.worker else 'Worker payment',
                'amount': -p.amount_paid,
                'reference': p.reference or '',
                'job_code': p.job.job_code if p.job else '',
            })

    # Expenses (admin only, negative)
    if is_admin and entry_type in (None, 'expense'):
        expenses = Expense.objects.filter(
            expense_date__gte=date_from,
            expense_date__lte=date_to,
        )
        for e in expenses:
            entries.append({
                'date': e.expense_date,
                'type': 'expense',
                'description': f'{e.get_category_display()}: {e.description}',
                'amount': -e.amount,
                'reference': e.reference or '',
                'job_code': '',
            })

    entries.sort(key=lambda x: x['date'], reverse=True)
    return entries


def pnl_to_csv_rows(pnl_data):
    """Convert P&L data to list of CSV rows (each row is a list of strings)."""
    rows = [
        ['P&L Report'],
        ['Period', str(pnl_data['date_from']), 'to', str(pnl_data['date_to'])],
        [],
        ['Line Item', 'Amount'],
        ['Revenue', str(pnl_data['revenue'])],
        ['Connect Deductions', str(-pnl_data['connect_deductions'])],
        ['Platform Fees', str(-pnl_data['platform_fees'])],
        ['Gross Profit', str(pnl_data['gross_profit'])],
        [],
        ['Worker Payouts', str(-pnl_data['worker_payouts'])],
    ]

    if pnl_data['is_admin'] and pnl_data['expenses_by_category']:
        rows.append([])
        rows.append(['Expenses by Category', ''])
        for cat, amount in pnl_data['expenses_by_category'].items():
            rows.append([f'  {cat}', str(-amount)])
        rows.append(['Total Expenses', str(-pnl_data['total_expenses'])])

    rows.append([])
    label = 'Net Profit' if pnl_data['is_admin'] else 'Project Profit'
    rows.append([label, str(pnl_data['net_profit'])])
    rows.append(['Margin', f"{pnl_data['margin']}%"])

    return rows


def ledger_to_csv_rows(entries):
    """Convert ledger entries to CSV rows with header."""
    rows = [['Date', 'Type', 'Description', 'Job', 'Amount', 'Reference']]
    for e in entries:
        rows.append([
            str(e['date']),
            e['type'].title(),
            e['description'],
            e['job_code'],
            str(e['amount']),
            e['reference'],
        ])
    return rows
