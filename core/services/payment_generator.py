"""
Payment generator — auto-creates Payment records from ReceiptDistribution.

Dramatically simplified vs FastAPI version: no dual path, no JSON parsing.
ReceiptDistribution already has computed_amount.
"""
import re
from core.models import Payment, ReceiptDistribution


def _next_payment_code():
    """Generate next sequential payment code P0001, P0002, etc."""
    last = Payment.objects.order_by('-id').first()
    num = 1
    if last:
        m = re.match(r'P(\d+)', last.payment_code)
        if m:
            num = int(m.group(1)) + 1
    return f"P{num:04d}"


def generate_payments_from_receipt(receipt):
    """Create Payment records from ReceiptDistribution rows for this receipt.

    Only creates payments for worker distributions (not owner/null worker).
    Returns list of created Payment objects.
    """
    distributions = receipt.distributions.filter(worker__isnull=False)
    created = []

    for dist in distributions:
        if dist.computed_amount <= 0:
            continue

        payment = Payment(
            payment_code=_next_payment_code(),
            worker=dist.worker,
            job=receipt.job,
            amount_paid=dist.computed_amount,
            paid_date=receipt.received_date,
            method='Auto-generated',
            reference=f'Receipt #{receipt.id}',
            notes=f'Auto-generated from {receipt.get_source_display()} receipt',
            is_auto_generated=True,
            is_paid=False,
        )
        payment.save()
        created.append(payment)

    return created
