from decimal import Decimal
from typing import List
import json
from sqlalchemy.orm import Session
from app.models import Receipt, Job, JobAllocation, Payment, SettingsVersion
from app.services.calculations import get_settings_rules, quantize_decimal
from app.utils import generate_payment_code

def generate_payments_from_receipt(receipt: Receipt, job: Job, db: Session) -> List[Payment]:
    """
    Generate payment entries for selected worker allocations when a receipt is added.
    Returns list of created Payment records.
    
    Important: Payment records are independent of JobAllocation records. They reference
    worker_id and job_id directly, not allocation_id. This means:
    - Payments remain in the database even if allocations are deleted
    - Payment history is preserved when workers are removed and re-added to jobs
    - Payments can be viewed regardless of current allocation status
    """
    # Check if using custom allocations
    if receipt.use_custom_allocations and receipt.custom_allocations:
        try:
            custom_allocs = json.loads(receipt.custom_allocations)
            # Validate structure
            for alloc in custom_allocs:
                if "worker_id" not in alloc or "share_type" not in alloc or "share_value" not in alloc:
                    raise ValueError("Invalid custom allocation structure")
            
            # Use custom allocations - skip the rest of the predefined logic
            return _generate_payments_from_custom_allocations(receipt, job, db, custom_allocs)
        except (json.JSONDecodeError, ValueError, TypeError):
            # Fall back to predefined if custom is invalid
            pass
    
    # Get all allocations for this job (predefined path)
    all_allocations = db.query(JobAllocation).filter(JobAllocation.job_id == job.id).all()
    
    if not all_allocations:
        return []  # No allocations, no payments to generate
    
    # Parse selected allocation IDs from receipt
    selected_allocation_ids = []
    if receipt.selected_allocation_ids:
        try:
            selected_allocation_ids = json.loads(receipt.selected_allocation_ids)
        except (json.JSONDecodeError, TypeError):
            selected_allocation_ids = []
    
    # Filter allocations: use selected ones, or all if none selected (backward compatibility)
    if selected_allocation_ids:
        allocations = [a for a in all_allocations if a.id in selected_allocation_ids]
    else:
        # If no selections, use all allocations (default behavior)
        allocations = all_allocations
    
    # Get settings rules
    rules = get_settings_rules(job.settings_version)
    
    # Calculate deductions for this single receipt
    # Connect deduction - based on connects used (distributed per receipt)
    # If multiple receipts, we need to calculate connect cost per receipt
    # For now, we'll calculate total connects cost and distribute evenly, or use connects per receipt
    # Since connects are per job, we'll calculate the total connect cost for the job
    # and distribute it proportionally across receipts based on amount
    connects_used = job.connects_used or 0
    connect_cost_per_unit = Decimal(str(rules.get("connect_cost_per_unit", 0)))
    total_connect_cost = Decimal(connects_used) * connect_cost_per_unit
    
    # Get all receipts for this job to calculate proportional share
    all_receipts = db.query(Receipt).filter(Receipt.job_id == job.id).all()
    total_received_all = sum((Decimal(str(r.amount_received)) for r in all_receipts), Decimal(0))
    
    if total_received_all > 0:
        # Distribute connect cost proportionally based on receipt amount
        receipt_share = receipt.amount_received / total_received_all
        connect_deduction = total_connect_cost * receipt_share
    else:
        # If no other receipts, this receipt gets the full connect cost
        connect_deduction = total_connect_cost
    
    connect_deduction = quantize_decimal(connect_deduction)
    
    # Platform fee
    platform_fee = Decimal(0)
    platform_fee_enabled = job.platform_fee_override_enabled
    if platform_fee_enabled is None:
        platform_fee_enabled = rules.get("platform_fee", {}).get("enabled", False)
    
    if platform_fee_enabled:
        platform_fee_mode = job.platform_fee_override_mode or rules.get("platform_fee", {}).get("mode", "percent")
        platform_fee_value = job.platform_fee_override_value or Decimal(str(rules.get("platform_fee", {}).get("value", 0)))
        platform_fee_apply_on = job.platform_fee_override_apply_on or rules.get("platform_fee", {}).get("apply_on", "net")
        
        if platform_fee_apply_on == "gross":
            base_amount = receipt.amount_received
        else:  # net
            base_amount = receipt.amount_received - connect_deduction
        
        if platform_fee_mode == "percent":
            platform_fee = base_amount * platform_fee_value
        else:  # fixed
            platform_fee = platform_fee_value
        
        platform_fee = quantize_decimal(platform_fee)
    
    # Net distributable from this receipt
    net_distributable = receipt.amount_received - connect_deduction - platform_fee
    net_distributable = quantize_decimal(net_distributable)
    
    # Generate payments for each worker allocation
    created_payments = []
    
    # Filter allocations to only those with workers
    worker_allocations = [a for a in allocations if a.worker_id]
    
    if not worker_allocations:
        return []  # No worker allocations, no payments to generate
    
    # Calculate total allocation percentage/amount for selected workers
    # This is used to redistribute funds proportionally among selected workers
    total_selected_share = Decimal(0)
    allocation_shares = {}
    
    for alloc in worker_allocations:
        if alloc.share_type == "percent":
            share_value = Decimal(str(alloc.share_value))
        else:  # fixed_amount
            # For fixed amounts, we'll use them as-is for proportional redistribution
            share_value = Decimal(str(alloc.share_value))
        
        allocation_shares[alloc.id] = share_value
        total_selected_share += share_value
    
    # First pass: calculate which allocations will create payments and their shares
    payment_data = []
    for alloc in worker_allocations:
        share_value = allocation_shares[alloc.id]
        
        # Calculate worker's share from this receipt
        # If allocations were selected, redistribute proportionally among selected workers
        if alloc.share_type == "percent":
            if total_selected_share > 0:
                # Redistribute: calculate what percentage this worker represents of selected workers
                # Then apply that percentage to the net distributable
                worker_percentage = share_value / total_selected_share
                worker_share = net_distributable * worker_percentage
            else:
                worker_share = Decimal(0)
        else:  # fixed_amount
            # For fixed amounts, redistribute proportionally based on their relative fixed amounts
            if total_selected_share > 0:
                worker_percentage = share_value / total_selected_share
                # Apply percentage to net distributable
                worker_share = net_distributable * worker_percentage
            else:
                worker_share = Decimal(0)
        
        worker_share = quantize_decimal(worker_share)
        
        # Only create payment if share is positive
        if worker_share > 0:
            payment_data.append({
                "allocation": alloc,
                "share": worker_share
            })
    
    # Generate all payment codes upfront to avoid duplicates
    import re
    max_num = 0
    # Check existing payments in database
    existing_payments = db.query(Payment).all()
    for payment in existing_payments:
        match = re.match(r'P(\d+)', payment.payment_code)
        if match:
            num = int(match.group(1))
            max_num = max(max_num, num)
    
    # Check pending payments in session (newly added but not committed)
    # SQLAlchemy session.new contains objects to be inserted
    for obj in list(db.new):  # Convert to list to avoid modification during iteration
        if isinstance(obj, Payment):
            match = re.match(r'P(\d+)', obj.payment_code)
            if match:
                num = int(match.group(1))
                max_num = max(max_num, num)
    
    # Generate codes for all payments we'll create
    generated_codes = []
    for i in range(len(payment_data)):
        next_code = f"P{max_num + 1 + i:04d}"
        generated_codes.append(next_code)
    
    # Now create payments using the pre-generated codes
    for i, data in enumerate(payment_data):
        alloc = data["allocation"]
        worker_share = data["share"]
        
        # Use pre-generated payment code
        payment_code = generated_codes[i]
        
        # Create payment entry
        payment = Payment(
            payment_code=payment_code,
            worker_id=alloc.worker_id,
            job_id=job.id,
            amount_paid=worker_share,
            paid_date=receipt.received_date,
            method="Auto-generated",
            reference=f"Receipt #{receipt.id}",
            notes=f"Auto-generated from receipt: {receipt.source}",
            is_auto_generated=True,
            is_paid=False  # Not paid yet, just calculated
        )
        db.add(payment)
        created_payments.append(payment)
    
    return created_payments

def _generate_payments_from_custom_allocations(receipt: Receipt, job: Job, db: Session, custom_allocs: List[dict]) -> List[Payment]:
    """
    Generate payment entries from custom allocations.
    Returns list of created Payment records.
    """
    from app.models import Worker
    
    # Get settings rules
    rules = get_settings_rules(job.settings_version)
    
    # Calculate deductions for this single receipt
    connects_used = job.connects_used or 0
    connect_cost_per_unit = Decimal(str(rules.get("connect_cost_per_unit", 0)))
    total_connect_cost = Decimal(connects_used) * connect_cost_per_unit
    
    # Get all receipts for this job to calculate proportional share
    all_receipts = db.query(Receipt).filter(Receipt.job_id == job.id).all()
    total_received_all = sum((Decimal(str(r.amount_received)) for r in all_receipts), Decimal(0))
    
    if total_received_all > 0:
        receipt_share = receipt.amount_received / total_received_all
        connect_deduction = total_connect_cost * receipt_share
    else:
        connect_deduction = total_connect_cost
    
    connect_deduction = quantize_decimal(connect_deduction)
    
    # Platform fee
    platform_fee = Decimal(0)
    platform_fee_enabled = job.platform_fee_override_enabled
    if platform_fee_enabled is None:
        platform_fee_enabled = rules.get("platform_fee", {}).get("enabled", False)
    
    if platform_fee_enabled:
        platform_fee_mode = job.platform_fee_override_mode or rules.get("platform_fee", {}).get("mode", "percent")
        platform_fee_value = job.platform_fee_override_value or Decimal(str(rules.get("platform_fee", {}).get("value", 0)))
        platform_fee_apply_on = job.platform_fee_override_apply_on or rules.get("platform_fee", {}).get("apply_on", "net")
        
        if platform_fee_apply_on == "gross":
            base_amount = receipt.amount_received
        else:  # net
            base_amount = receipt.amount_received - connect_deduction
        
        if platform_fee_mode == "percent":
            platform_fee = base_amount * platform_fee_value
        else:  # fixed
            platform_fee = platform_fee_value
        
        platform_fee = quantize_decimal(platform_fee)
    
    # Net distributable from this receipt
    net_distributable = receipt.amount_received - connect_deduction - platform_fee
    net_distributable = quantize_decimal(net_distributable)
    
    # Filter custom allocations to only those with workers
    worker_allocations = [a for a in custom_allocs if a.get("worker_id")]
    
    if not worker_allocations:
        return []  # No worker allocations, no payments to generate
    
    # Calculate total share for proportional distribution
    total_share = Decimal(0)
    allocation_shares = {}
    
    for alloc in worker_allocations:
        share_type = alloc["share_type"]
        share_value = Decimal(str(alloc["share_value"]))
        allocation_shares[alloc["worker_id"]] = {
            "share_type": share_type,
            "share_value": share_value
        }
        total_share += share_value
    
    # Calculate payment amounts
    payment_data = []
    for alloc in worker_allocations:
        worker_id = alloc["worker_id"]
        share_info = allocation_shares[worker_id]
        share_value = share_info["share_value"]
        share_type = share_info["share_type"]
        
        # Calculate worker's share
        if share_type == "percent":
            if total_share > 0:
                worker_percentage = share_value / total_share
                worker_share = net_distributable * worker_percentage
            else:
                worker_share = Decimal(0)
        else:  # fixed_amount
            if total_share > 0:
                worker_percentage = share_value / total_share
                worker_share = net_distributable * worker_percentage
            else:
                worker_share = Decimal(0)
        
        worker_share = quantize_decimal(worker_share)
        
        if worker_share > 0:
            payment_data.append({
                "worker_id": worker_id,
                "share": worker_share
            })
    
    # Generate payment codes
    import re
    max_num = 0
    existing_payments = db.query(Payment).all()
    for payment in existing_payments:
        match = re.match(r'P(\d+)', payment.payment_code)
        if match:
            num = int(match.group(1))
            max_num = max(max_num, num)
    
    for obj in list(db.new):
        if isinstance(obj, Payment):
            match = re.match(r'P(\d+)', obj.payment_code)
            if match:
                num = int(match.group(1))
                max_num = max(max_num, num)
    
    generated_codes = []
    for i in range(len(payment_data)):
        next_code = f"P{max_num + 1 + i:04d}"
        generated_codes.append(next_code)
    
    # Create payments
    created_payments = []
    for i, data in enumerate(payment_data):
        worker_id = data["worker_id"]
        worker_share = data["share"]
        payment_code = generated_codes[i]
        
        payment = Payment(
            payment_code=payment_code,
            worker_id=worker_id,
            job_id=job.id,
            amount_paid=worker_share,
            paid_date=receipt.received_date,
            method="Auto-generated",
            reference=f"Receipt #{receipt.id}",
            notes=f"Auto-generated from receipt: {receipt.source} (Custom Allocation)",
            is_auto_generated=True,
            is_paid=False
        )
        db.add(payment)
        created_payments.append(payment)
    
    return created_payments
