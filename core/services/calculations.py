"""
Calculation engine for job financials, worker totals, and dashboard aggregates.
Ported from FastAPI app/services/calculations.py with improvements:
- Worker totals use ReceiptDistribution aggregates instead of re-computing from allocations
- Dashboard totals accept a queryset (for role-based filtering)
- Owner earnings use ReceiptDistribution (single query)
"""
import json
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum, Q
from core.models import (
    Job, Receipt, JobAllocation, Payment, SettingsVersion,
    Worker, ReceiptDistribution, JobCalculationSnapshot, Expense,
)


def quantize_decimal(value, places=2):
    """Round decimal to specified places using ROUND_HALF_UP."""
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    fmt = Decimal('0.01') if places == 2 else Decimal(10) ** -places
    return value.quantize(fmt, rounding=ROUND_HALF_UP)


def get_settings_rules(settings_version):
    """Parse and return settings rules dict from a SettingsVersion."""
    if not settings_version:
        return {}
    return settings_version.rules


def get_job_totals(job):
    """Calculate job totals: received, platform fee, net distributable.

    Uses the job's own settings_version (or overrides) for calculation rules.
    Returns dict with keys: total_received, platform_fee, net_distributable.
    """
    rules = get_settings_rules(job.settings_version)

    # Total received from all receipts
    agg = job.receipts.aggregate(total=Sum('amount_received'))
    total_received = Decimal(str(agg['total'] or 0))

    # Platform fee
    platform_fee_enabled = job.platform_fee_override_enabled
    if platform_fee_enabled is None:
        platform_fee_enabled = rules.get('platform_fee', {}).get('enabled', False)

    platform_fee = Decimal(0)
    if platform_fee_enabled:
        pf_rules = rules.get('platform_fee', {})
        pf_mode = job.platform_fee_override_mode or pf_rules.get('mode', 'percent')
        pf_value = (
            Decimal(str(job.platform_fee_override_value))
            if job.platform_fee_override_value is not None
            else Decimal(str(pf_rules.get('value', 0)))
        )

        if pf_mode == 'percent':
            platform_fee = total_received * pf_value
        else:  # fixed
            platform_fee = pf_value

        platform_fee = quantize_decimal(platform_fee)

    net_distributable = quantize_decimal(total_received - platform_fee)

    return {
        'total_received': total_received,
        'platform_fee': platform_fee,
        'net_distributable': net_distributable,
    }


def compute_allocations(job, net_distributable=None):
    """Compute earned amounts for each JobAllocation on a job.

    Returns list of dicts: [{allocation, earned}, ...]
    """
    if net_distributable is None:
        totals = get_job_totals(job)
        net_distributable = totals['net_distributable']

    if not isinstance(net_distributable, Decimal):
        net_distributable = Decimal(str(net_distributable))

    results = []
    for alloc in job.allocations.all():
        if alloc.share_type == 'percent':
            earned = net_distributable * Decimal(str(alloc.share_value))
        else:  # fixed_amount
            earned = Decimal(str(alloc.share_value))

        results.append({
            'allocation': alloc,
            'earned': quantize_decimal(earned),
        })

    return results


def compute_receipt_distributions(receipt, allocations, platform_fee):
    """Compute the distribution amounts for a single receipt given specific allocations.

    This is called when creating a receipt to calculate what each worker gets.
    It handles proportional platform fee distribution per receipt.

    Args:
        receipt: Receipt instance
        allocations: list of dicts with keys: worker, label, share_type, share_value
                     (can come from JobAllocation or custom overrides)
        platform_fee: Decimal platform fee for this receipt

    Returns:
        list of dicts: [{worker, label, share_type, share_value, computed_amount}, ...]
    """
    amount = Decimal(str(receipt.amount_received))
    net = quantize_decimal(amount - platform_fee)

    # Calculate total share for proportional distribution
    total_share = Decimal(0)
    for alloc in allocations:
        total_share += Decimal(str(alloc['share_value']))

    results = []
    for alloc in allocations:
        share_value = Decimal(str(alloc['share_value']))

        if alloc['share_type'] == 'percent':
            if total_share > 0:
                proportion = share_value / total_share
                computed = net * proportion
            else:
                computed = Decimal(0)
        else:  # fixed_amount
            # For fixed amounts, distribute proportionally based on relative fixed amounts
            if total_share > 0:
                proportion = share_value / total_share
                computed = net * proportion
            else:
                computed = Decimal(0)

        results.append({
            'worker': alloc.get('worker'),
            'label': alloc.get('label', ''),
            'share_type': alloc['share_type'],
            'share_value': share_value,
            'computed_amount': quantize_decimal(computed),
        })

    return results


def get_receipt_deductions(job, receipt):
    """Calculate platform fee for a single receipt."""
    rules = get_settings_rules(job.settings_version)
    receipt_amount = Decimal(str(receipt.amount_received))

    platform_fee_enabled = job.platform_fee_override_enabled
    if platform_fee_enabled is None:
        platform_fee_enabled = rules.get('platform_fee', {}).get('enabled', False)

    platform_fee = Decimal(0)
    if platform_fee_enabled:
        pf_rules = rules.get('platform_fee', {})
        pf_mode = job.platform_fee_override_mode or pf_rules.get('mode', 'percent')
        pf_value = (
            Decimal(str(job.platform_fee_override_value))
            if job.platform_fee_override_value is not None
            else Decimal(str(pf_rules.get('value', 0)))
        )

        if pf_mode == 'percent':
            platform_fee = receipt_amount * pf_value
        else:
            platform_fee = pf_value

        platform_fee = quantize_decimal(platform_fee)

    return platform_fee


def compute_worker_totals(worker):
    """Compute total earned, paid, and due for a worker.

    IMPROVEMENT over FastAPI: Uses ReceiptDistribution aggregates instead of
    re-computing from allocations per job. Single query for earned.
    """
    # Earned = receipt-chain distributions + manual payments (non-auto have no RD, so no double-count)
    rd_agg = ReceiptDistribution.objects.filter(
        worker=worker
    ).aggregate(total=Sum('computed_amount'))
    earned_from_receipts = Decimal(str(rd_agg['total'] or 0))

    manual_agg = Payment.objects.filter(
        worker=worker,
        is_auto_generated=False,
    ).aggregate(total=Sum('amount'))
    earned_from_manual = Decimal(str(manual_agg['total'] or 0))

    earned = earned_from_receipts + earned_from_manual

    # Paid = all payments actually marked as paid (auto + manual)
    paid_agg = Payment.objects.filter(
        worker=worker,
        is_paid=True,
    ).aggregate(total=Sum('amount'))
    paid = Decimal(str(paid_agg['total'] or 0))

    due = earned - paid

    return {
        'earned': quantize_decimal(earned),
        'paid': quantize_decimal(paid),
        'due': quantize_decimal(due),
    }


def get_dashboard_totals(jobs_queryset=None):
    """Get dashboard totals, optionally scoped to a queryset of jobs.

    Args:
        jobs_queryset: QuerySet of Job objects (for role-based filtering).
                       If None, uses all non-archived jobs.
    """
    if jobs_queryset is None:
        jobs_queryset = Job.objects.exclude(status='archived')

    job_ids = list(jobs_queryset.values_list('id', flat=True))

    # Total received
    agg = Receipt.objects.filter(job_id__in=job_ids).aggregate(total=Sum('amount_received'))
    total_received = Decimal(str(agg['total'] or 0))

    # Calculate platform fee per job
    total_platform_fee = Decimal(0)

    for job in jobs_queryset.select_related('settings_version').iterator():
        if job.is_finalized and hasattr(job, 'snapshot'):
            try:
                snapshot_data = job.snapshot.data
                totals = snapshot_data.get('totals', {})
                total_platform_fee += Decimal(str(totals.get('platform_fee', 0)))
                continue
            except JobCalculationSnapshot.DoesNotExist:
                pass

        totals = get_job_totals(job)
        total_platform_fee += totals['platform_fee']

    # Total paid (only actually paid payments for these jobs)
    agg = Payment.objects.filter(
        job_id__in=job_ids,
        is_paid=True
    ).aggregate(total=Sum('amount'))
    total_paid = Decimal(str(agg['total'] or 0))

    # Total due: total from ReceiptDistribution for workers on these jobs minus paid
    agg_earned = ReceiptDistribution.objects.filter(
        receipt__job_id__in=job_ids,
        worker__isnull=False
    ).aggregate(total=Sum('computed_amount'))
    total_earned = Decimal(str(agg_earned['total'] or 0))
    total_due = total_earned - total_paid

    return {
        'total_received': quantize_decimal(total_received),
        'total_platform_fee': quantize_decimal(total_platform_fee),
        'total_paid': quantize_decimal(total_paid),
        'total_due': quantize_decimal(total_due),
    }


def recompute_expense_coverage(worker):
    """Mark a worker's submitted expenses as paid based on cumulative cash actually received.

    Uses only is_paid=True payments (real cash in hand, not just amounts owed).
    Walks expenses oldest-first: once running total exceeds cash received, remaining
    expenses are marked unpaid. Saves only rows whose flag actually changed.
    """
    if not worker.user_id:
        return

    cash_received = Payment.objects.filter(
        worker=worker,
        is_paid=True,
    ).aggregate(t=Sum('amount'))['t'] or Decimal(0)

    expenses = list(
        Expense.objects.filter(created_by_id=worker.user_id).order_by('expense_date', 'id')
    )

    running = Decimal(0)
    to_update = []
    for expense in expenses:
        running += expense.amount
        should_be_paid = running <= cash_received
        if expense.is_paid != should_be_paid:
            expense.is_paid = should_be_paid
            to_update.append(expense)

    if to_update:
        Expense.objects.bulk_update(to_update, ['is_paid'])


def get_earnings_for_period(date_from=None, date_to=None, jobs_queryset=None):
    """Get total earnings (receipts) for a specific date period."""
    if jobs_queryset is None:
        jobs_queryset = Job.objects.exclude(status='archived')

    filters = Q(job__in=jobs_queryset)
    if date_from:
        filters &= Q(received_date__gte=date_from)
    if date_to:
        filters &= Q(received_date__lte=date_to)

    agg = Receipt.objects.filter(filters).aggregate(total=Sum('amount_received'))
    return quantize_decimal(Decimal(str(agg['total'] or 0)))


def get_owner_earnings_for_period(date_from=None, date_to=None):
    """Get owner earnings for a specific date period.

    Owner earnings = ReceiptDistribution where worker is null (owner share)
    OR worker.is_owner=True.

    IMPROVEMENT over FastAPI: Single ORM query instead of looping per job.
    """
    filters = Q(receipt__job__status__in=['active', 'completed'])
    filters &= (Q(worker__isnull=True) | Q(worker__is_owner=True))

    if date_from:
        filters &= Q(receipt__received_date__gte=date_from)
    if date_to:
        filters &= Q(receipt__received_date__lte=date_to)

    agg = ReceiptDistribution.objects.filter(filters).aggregate(total=Sum('computed_amount'))
    return quantize_decimal(Decimal(str(agg['total'] or 0)))
