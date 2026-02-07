from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc
from decimal import Decimal
import json
from datetime import date
from app.database import get_db
from app.models import Job, Receipt, JobAllocation, SettingsVersion, JobCalculationSnapshot, Worker, Payment, JobSource
from app.schemas import JobCreate
from app.services.calculations import get_job_totals, compute_allocations, get_settings_rules
from app.dependencies import get_db_session
from app.utils import generate_job_code
from app.services.payment_generator import generate_payments_from_receipt
from app.config import BASE_DIR

router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "templates")

def get_active_settings_version(db: Session) -> SettingsVersion:
    """Get the currently active settings version"""
    version = db.query(SettingsVersion).filter(SettingsVersion.is_active == True).first()
    if not version:
        raise HTTPException(status_code=500, detail="No active settings version found. Please create one in Settings.")
    return version

@router.get("/jobs", response_class=HTMLResponse)
async def list_jobs(request: Request, db: Session = Depends(get_db_session)):
    jobs = db.query(Job).filter(Job.status != "archived").order_by(desc(Job.created_at)).all()
    return templates.TemplateResponse("jobs/list.html", {
        "request": request,
        "jobs": jobs
    })

@router.get("/jobs/new", response_class=HTMLResponse)
async def new_job_form(request: Request, db: Session = Depends(get_db_session)):
    active_version = get_active_settings_version(db)
    workers = db.query(Worker).filter(Worker.is_archived == False).all()
    next_code = generate_job_code(db)
    return templates.TemplateResponse("jobs/form.html", {
        "request": request,
        "job": None,
        "active_settings_version": active_version,
        "workers": workers,
        "suggested_code": next_code
    })

@router.post("/jobs/new")
async def create_job(
    request: Request,
    job_code: str = Form(None),
    title: str = Form(...),
    client_name: str = Form(None),
    job_post_url: str = Form(...),
    source: str = Form(None),
    description: str = Form(None),
    cover_letter: str = Form(None),
    company_name: str = Form(None),
    company_website: str = Form(None),
    company_email: str = Form(None),
    company_phone: str = Form(None),
    company_address: str = Form(None),
    client_notes: str = Form(None),
    upwork_job_id: str = Form(None),
    upwork_contract_id: str = Form(None),
    upwork_offer_id: str = Form(None),
    job_type: str = Form(...),
    status: str = Form(...),
    start_date: str = Form(None),
    end_date: str = Form(None),
    connects_used: str = Form(None),
    db: Session = Depends(get_db_session)
):
    # Auto-generate code if not provided
    if not job_code or job_code.strip() == "":
        job_code = generate_job_code(db)
    
    # Check if job_code already exists
    existing = db.query(Job).filter(Job.job_code == job_code).first()
    if existing:
        active_version = get_active_settings_version(db)
        workers = db.query(Worker).filter(Worker.is_archived == False).all()
        next_code = generate_job_code(db)
        return templates.TemplateResponse("jobs/form.html", {
            "request": request,
            "job": None,
            "active_settings_version": active_version,
            "workers": workers,
            "suggested_code": next_code,
            "error": f"Job code {job_code} already exists"
        }, status_code=400)
    
    active_version = get_active_settings_version(db)
    
    connects_used_int = int(connects_used) if connects_used and connects_used.strip() else None
    
    # Convert source string to enum if provided
    source_enum = None
    if source and source.strip():
        try:
            source_enum = JobSource(source.strip().lower())
        except ValueError:
            source_enum = None
    
    job = Job(
        job_code=job_code,
        title=title,
        client_name=client_name if client_name else None,
        job_post_url=job_post_url,
        source=source_enum,
        description=description if description and description.strip() else None,
        cover_letter=cover_letter if cover_letter and cover_letter.strip() else None,
        company_name=company_name.strip() if company_name and company_name.strip() else None,
        company_website=company_website.strip() if company_website and company_website.strip() else None,
        company_email=company_email.strip() if company_email and company_email.strip() else None,
        company_phone=company_phone.strip() if company_phone and company_phone.strip() else None,
        company_address=company_address.strip() if company_address and company_address.strip() else None,
        client_notes=client_notes.strip() if client_notes and client_notes.strip() else None,
        upwork_job_id=upwork_job_id if upwork_job_id else None,
        upwork_contract_id=upwork_contract_id if upwork_contract_id else None,
        upwork_offer_id=upwork_offer_id if upwork_offer_id else None,
        job_type=job_type,
        status=status,
        start_date=date.fromisoformat(start_date) if start_date else None,
        end_date=date.fromisoformat(end_date) if end_date else None,
        connects_used=connects_used_int,
        settings_version_id=active_version.id
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    return RedirectResponse(url=f"/jobs/{job.id}", status_code=303)

@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: int, db: Session = Depends(get_db_session)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    receipts = db.query(Receipt).filter(Receipt.job_id == job_id).order_by(Receipt.received_date).all()
    allocations = db.query(JobAllocation).filter(JobAllocation.job_id == job_id).all()
    payments = db.query(Payment).filter(Payment.job_id == job_id).all()
    
    # Get set of currently allocated worker IDs for visual indicators
    # Payments are independent of allocations and remain visible even when workers are removed
    current_worker_ids = {a.worker_id for a in allocations if a.worker_id}
    
    # Get calculations
    if job.is_finalized and job.snapshot:
        # Use snapshot
        snapshot_data = json.loads(job.snapshot.snapshot_json)
        totals = {
            "total_received": Decimal(str(snapshot_data.get("totals", {}).get("total_received", 0))),
            "connect_deduction": Decimal(str(snapshot_data.get("totals", {}).get("connect_deduction", 0))),
            "platform_fee": Decimal(str(snapshot_data.get("totals", {}).get("platform_fee", 0))),
            "net_distributable": Decimal(str(snapshot_data.get("totals", {}).get("net_distributable", 0)))
        }
        # Reconstruct allocation results from snapshot
        snapshot_allocations = snapshot_data.get("allocations", [])
        allocation_results = []
        for snap_alloc in snapshot_allocations:
            alloc_id = snap_alloc.get("allocation_id")
            alloc = next((a for a in allocations if a.id == alloc_id), None)
            if alloc:
                allocation_results.append({
                    "allocation": alloc,
                    "earned": Decimal(str(snap_alloc.get("earned", 0)))
                })
    else:
        # Compute from current data
        totals = get_job_totals(job, receipts, job.settings_version)
        allocation_results = compute_allocations(job, allocations, totals, job.settings_version)
        # Convert to dict format for template
        allocation_results = [
            {
                "allocation": r["allocation"],
                "earned": r["earned"]
            }
            for r in allocation_results
        ]
    
    # Get settings rules
    rules = get_settings_rules(job.settings_version)
    
    # Calculate connect deduction details for display
    connects_used = job.connects_used or 0
    connect_cost_per_unit = Decimal(str(rules.get("connect_cost_per_unit", 0)))
    
    workers = db.query(Worker).filter(Worker.is_archived == False).all()
    # Convert workers to dictionaries for JSON serialization
    workers_dict = [
        {
            "id": w.id,
            "name": w.name,
            "worker_code": w.worker_code
        }
        for w in workers
    ]
    
    return templates.TemplateResponse("jobs/detail.html", {
        "request": request,
        "job": job,
        "receipts": receipts,
        "allocations": allocations,
        "allocation_results": allocation_results,
        "payments": payments,
        "totals": totals,
        "settings_rules": rules,
        "workers": workers,  # Keep original for template iteration
        "workers_json": workers_dict,  # Use this for JSON serialization
        "current_worker_ids": current_worker_ids,  # For showing inactive worker indicators
        "connects_used": connects_used,
        "connect_cost_per_unit": connect_cost_per_unit
    })

@router.get("/jobs/{job_id}/edit", response_class=HTMLResponse)
async def edit_job_form(request: Request, job_id: int, db: Session = Depends(get_db_session)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.is_finalized:
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)
    
    active_version = get_active_settings_version(db)
    workers = db.query(Worker).filter(Worker.is_archived == False).all()
    
    return templates.TemplateResponse("jobs/form.html", {
        "request": request,
        "job": job,
        "active_settings_version": active_version,
        "workers": workers
    })

@router.post("/jobs/{job_id}/edit")
async def update_job(
    request: Request,
    job_id: int,
    job_code: str = Form(...),
    title: str = Form(...),
    client_name: str = Form(None),
    job_post_url: str = Form(...),
    source: str = Form(None),
    description: str = Form(None),
    cover_letter: str = Form(None),
    company_name: str = Form(None),
    company_website: str = Form(None),
    company_email: str = Form(None),
    company_phone: str = Form(None),
    company_address: str = Form(None),
    client_notes: str = Form(None),
    upwork_job_id: str = Form(None),
    upwork_contract_id: str = Form(None),
    upwork_offer_id: str = Form(None),
    job_type: str = Form(...),
    status: str = Form(...),
    start_date: str = Form(None),
    end_date: str = Form(None),
    connects_used: str = Form(None),
    db: Session = Depends(get_db_session)
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.is_finalized:
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)
    
    # Check if job_code already exists (for other jobs)
    existing = db.query(Job).filter(Job.job_code == job_code, Job.id != job_id).first()
    if existing:
        active_version = get_active_settings_version(db)
        workers = db.query(Worker).filter(Worker.is_archived == False).all()
        return templates.TemplateResponse("jobs/form.html", {
            "request": request,
            "job": job,
            "active_settings_version": active_version,
            "workers": workers,
            "error": f"Job code {job_code} already exists"
        }, status_code=400)
    
    # Convert source string to enum if provided
    source_enum = None
    if source and source.strip():
        try:
            source_enum = JobSource(source.strip().lower())
        except ValueError:
            source_enum = None
    
    job.job_code = job_code
    job.title = title
    job.client_name = client_name if client_name else None
    job.job_post_url = job_post_url
    job.source = source_enum
    job.description = description if description and description.strip() else None
    job.cover_letter = cover_letter if cover_letter and cover_letter.strip() else None
    job.company_name = company_name.strip() if company_name and company_name.strip() else None
    job.company_website = company_website.strip() if company_website and company_website.strip() else None
    job.company_email = company_email.strip() if company_email and company_email.strip() else None
    job.company_phone = company_phone.strip() if company_phone and company_phone.strip() else None
    job.company_address = company_address.strip() if company_address and company_address.strip() else None
    job.client_notes = client_notes.strip() if client_notes and client_notes.strip() else None
    job.upwork_job_id = upwork_job_id if upwork_job_id else None
    job.upwork_contract_id = upwork_contract_id if upwork_contract_id else None
    job.upwork_offer_id = upwork_offer_id if upwork_offer_id else None
    job.job_type = job_type
    job.status = status
    job.start_date = date.fromisoformat(start_date) if start_date else None
    job.end_date = date.fromisoformat(end_date) if end_date else None
    job.connects_used = int(connects_used) if connects_used and connects_used.strip() else None
    db.commit()
    
    return RedirectResponse(url=f"/jobs/{job.id}", status_code=303)

@router.post("/jobs/{job_id}/archive")
async def archive_job(job_id: int, db: Session = Depends(get_db_session)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job.status = "archived"
    db.commit()
    
    return RedirectResponse(url="/jobs", status_code=303)

# Receipt routes
@router.post("/jobs/{job_id}/receipts/new")
async def create_receipt(
    job_id: int,
    received_date: str = Form(...),
    amount_received: str = Form(...),
    source: str = Form(...),
    upwork_transaction_id: str = Form(None),
    notes: str = Form(None),
    selected_allocations: list = Form(None),
    allocation_mode: str = Form("predefined"),
    custom_allocations_json: str = Form(None),
    use_custom_allocations: str = Form("false"),
    db: Session = Depends(get_db_session)
):
    import json
    
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.is_finalized:
        raise HTTPException(status_code=400, detail="Cannot add receipts to finalized job")
    
    # Handle allocation mode
    use_custom = use_custom_allocations.lower() == "true" or allocation_mode == "custom"
    
    selected_allocation_ids_json = None
    custom_allocations_json_stored = None
    
    if use_custom:
        # Use custom allocations
        if custom_allocations_json:
            try:
                # Validate JSON
                custom_allocs = json.loads(custom_allocations_json)
                # Validate structure
                for alloc in custom_allocs:
                    if "worker_id" not in alloc or "share_type" not in alloc or "share_value" not in alloc:
                        raise ValueError("Invalid custom allocation structure")
                custom_allocations_json_stored = custom_allocations_json
            except (json.JSONDecodeError, ValueError) as e:
                raise HTTPException(status_code=400, detail=f"Invalid custom allocations: {str(e)}")
    else:
        # Use predefined allocations
        if selected_allocations:
            try:
                allocation_ids = [int(aid) for aid in selected_allocations]
                selected_allocation_ids_json = json.dumps(allocation_ids)
            except (ValueError, TypeError):
                selected_allocation_ids_json = None
    
    receipt = Receipt(
        job_id=job_id,
        received_date=date.fromisoformat(received_date),
        amount_received=Decimal(amount_received),
        source=source,
        upwork_transaction_id=upwork_transaction_id if upwork_transaction_id else None,
        notes=notes if notes else None,
        selected_allocation_ids=selected_allocation_ids_json,
        use_custom_allocations=use_custom,
        custom_allocations=custom_allocations_json_stored
    )
    db.add(receipt)
    db.flush()  # Flush to get receipt ID, but don't commit yet
    
    # Generate payments automatically if job has allocations
    try:
        generate_payments_from_receipt(receipt, job, db)
    except Exception as e:
        # If payment generation fails, rollback the receipt
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error generating payments: {str(e)}")
    
    db.commit()
    
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)

@router.get("/receipts/{receipt_id}/edit", response_class=HTMLResponse)
async def edit_receipt_form(request: Request, receipt_id: int, db: Session = Depends(get_db_session)):
    import json
    
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    
    job = receipt.job
    if job.is_finalized:
        raise HTTPException(status_code=400, detail="Cannot edit receipts in finalized job")
    
    # Get allocations for this job
    allocations = db.query(JobAllocation).filter(JobAllocation.job_id == job.id).all()
    
    # Get workers for custom allocations
    workers = db.query(Worker).filter(Worker.is_archived == False).all()
    # Convert workers to dictionaries for JSON serialization
    workers_dict = [
        {
            "id": w.id,
            "name": w.name,
            "worker_code": w.worker_code
        }
        for w in workers
    ]
    
    # Parse selected allocation IDs
    selected_allocation_ids = []
    if receipt.selected_allocation_ids:
        try:
            selected_allocation_ids = json.loads(receipt.selected_allocation_ids)
        except (json.JSONDecodeError, TypeError):
            selected_allocation_ids = []
    
    # Parse custom allocations
    custom_allocations = []
    if receipt.custom_allocations:
        try:
            custom_allocations = json.loads(receipt.custom_allocations)
        except (json.JSONDecodeError, TypeError):
            custom_allocations = []
    
    return templates.TemplateResponse("receipts/form.html", {
        "request": request,
        "receipt": receipt,
        "job": job,
        "allocations": allocations,  # Pass allocations to template
        "selected_allocation_ids": selected_allocation_ids,  # Pass parsed IDs
        "workers": workers,  # Pass workers for template iteration
        "workers_json": workers_dict,  # Use this for JSON serialization
        "custom_allocations": custom_allocations  # Pass custom allocations
    })

@router.post("/receipts/{receipt_id}/edit")
async def update_receipt(
    receipt_id: int,
    received_date: str = Form(...),
    amount_received: str = Form(...),
    source: str = Form(...),
    upwork_transaction_id: str = Form(None),
    notes: str = Form(None),
    selected_allocations: list = Form(None),
    allocation_mode: str = Form("predefined"),
    custom_allocations_json: str = Form(None),
    use_custom_allocations: str = Form("false"),
    db: Session = Depends(get_db_session)
):
    import json
    
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    
    job = receipt.job
    if job.is_finalized:
        raise HTTPException(status_code=400, detail="Cannot edit receipts in finalized job")
    
    # Handle allocation mode
    use_custom = use_custom_allocations.lower() == "true" or allocation_mode == "custom"
    
    selected_allocation_ids_json = None
    custom_allocations_json_stored = None
    
    if use_custom:
        # Use custom allocations
        if custom_allocations_json:
            try:
                # Validate JSON
                custom_allocs = json.loads(custom_allocations_json)
                # Validate structure
                for alloc in custom_allocs:
                    if "worker_id" not in alloc or "share_type" not in alloc or "share_value" not in alloc:
                        raise ValueError("Invalid custom allocation structure")
                custom_allocations_json_stored = custom_allocations_json
            except (json.JSONDecodeError, ValueError) as e:
                raise HTTPException(status_code=400, detail=f"Invalid custom allocations: {str(e)}")
    else:
        # Use predefined allocations
        if selected_allocations:
            try:
                allocation_ids = [int(aid) for aid in selected_allocations]
                selected_allocation_ids_json = json.dumps(allocation_ids)
            except (ValueError, TypeError):
                selected_allocation_ids_json = None
    
    receipt.received_date = date.fromisoformat(received_date)
    receipt.amount_received = Decimal(amount_received)
    receipt.source = source
    receipt.upwork_transaction_id = upwork_transaction_id if upwork_transaction_id else None
    receipt.notes = notes if notes else None
    receipt.selected_allocation_ids = selected_allocation_ids_json
    receipt.use_custom_allocations = use_custom
    receipt.custom_allocations = custom_allocations_json_stored
    
    # Note: We don't regenerate payments when editing receipts
    # Existing payments remain, but new calculations will use the updated allocation selection
    db.commit()
    
    return RedirectResponse(url=f"/jobs/{job.id}", status_code=303)

@router.post("/receipts/{receipt_id}/delete")
async def delete_receipt(receipt_id: int, db: Session = Depends(get_db_session)):
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    
    job_id = receipt.job_id
    if receipt.job.is_finalized:
        raise HTTPException(status_code=400, detail="Cannot delete receipts from finalized job")
    
    db.delete(receipt)
    db.commit()
    
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)

# Allocation routes
@router.post("/jobs/{job_id}/allocations/new")
async def create_allocation(
    job_id: int,
    worker_id: str = Form(None),
    label: str = Form(...),
    role: str = Form(None),
    share_type: str = Form(...),
    share_value: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db_session)
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.is_finalized:
        raise HTTPException(status_code=400, detail="Cannot add allocations to finalized job")
    
    worker_id_int = int(worker_id) if worker_id and worker_id != "None" else None
    
    allocation = JobAllocation(
        job_id=job_id,
        worker_id=worker_id_int,
        label=label,
        role=role if role else None,
        share_type=share_type,
        share_value=Decimal(share_value),
        notes=notes if notes else None
    )
    db.add(allocation)
    db.flush()  # Flush to ensure the new allocation is available for query
    
    # Validate allocations
    # Query all allocations for this job, which should include the flushed one
    allocations = db.query(JobAllocation).filter(JobAllocation.job_id == job_id).all()
    
    # If the new allocation isn't in the query results (shouldn't happen, but just in case),
    # manually add it
    if allocation not in allocations:
        allocations.append(allocation)
    
    rules = get_settings_rules(job.settings_version)
    
    if rules.get("require_percent_allocations_sum_to_1", False):
        percent_allocations = [a for a in allocations if a.share_type == "percent"]
        if percent_allocations:
            total_percent = sum((Decimal(str(a.share_value)) for a in percent_allocations), Decimal(0))
            # Only error if sum exceeds 1.0 (allow partial sums during creation)
            if total_percent > Decimal("1.01"):  # Allow small epsilon, but error if exceeds 1.0
                db.rollback()
                raise HTTPException(
                    status_code=400,
                    detail=f"Percent allocations cannot exceed 1.0 (current: {total_percent})"
                )
            # Warn if sum is less than 1.0 but don't block (user might add more allocations)
            # The validation will be enforced when finalizing the job
    
    db.commit()
    
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)

@router.post("/allocations/{alloc_id}/edit")
async def update_allocation(
    alloc_id: int,
    worker_id: str = Form(None),
    label: str = Form(...),
    role: str = Form(None),
    share_type: str = Form(...),
    share_value: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db_session)
):
    allocation = db.query(JobAllocation).filter(JobAllocation.id == alloc_id).first()
    if not allocation:
        raise HTTPException(status_code=404, detail="Allocation not found")
    
    job = allocation.job
    if job.is_finalized:
        raise HTTPException(status_code=400, detail="Cannot edit allocations in finalized job")
    
    worker_id_int = int(worker_id) if worker_id and worker_id != "None" else None
    
    allocation.worker_id = worker_id_int
    allocation.label = label
    allocation.role = role if role else None
    allocation.share_type = share_type
    allocation.share_value = Decimal(share_value)
    allocation.notes = notes if notes else None
    
    db.flush()  # Flush to ensure changes are available for query
    
    # Validate allocations
    allocations = db.query(JobAllocation).filter(JobAllocation.job_id == job.id).all()
    rules = get_settings_rules(job.settings_version)
    
    if rules.get("require_percent_allocations_sum_to_1", False):
        percent_allocations = [a for a in allocations if a.share_type == "percent"]
        if percent_allocations:
            total_percent = sum(Decimal(str(a.share_value)) for a in percent_allocations)
            if abs(total_percent - Decimal("1.0")) > Decimal("0.01"):
                db.rollback()
                raise HTTPException(
                    status_code=400,
                    detail=f"Percent allocations must sum to 1.0 (current: {total_percent})"
                )
    
    db.commit()
    
    return RedirectResponse(url=f"/jobs/{job.id}", status_code=303)

@router.post("/allocations/{alloc_id}/delete")
async def delete_allocation(alloc_id: int, db: Session = Depends(get_db_session)):
    """
    Delete a job allocation.
    
    Note: Payments are independent of allocations and will remain in the database
    even after an allocation is deleted. This preserves payment history and allows
    workers to be reallocated without losing historical payment records.
    """
    allocation = db.query(JobAllocation).filter(JobAllocation.id == alloc_id).first()
    if not allocation:
        raise HTTPException(status_code=404, detail="Allocation not found")
    
    job_id = allocation.job_id
    if allocation.job.is_finalized:
        raise HTTPException(status_code=400, detail="Cannot delete allocations from finalized job")
    
    db.delete(allocation)
    db.commit()
    
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)

# Finalize routes
@router.post("/jobs/{job_id}/finalize")
async def finalize_job(job_id: int, db: Session = Depends(get_db_session)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.is_finalized:
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)
    
    # Compute current totals
    receipts = db.query(Receipt).filter(Receipt.job_id == job_id).all()
    allocations = db.query(JobAllocation).filter(JobAllocation.job_id == job_id).all()
    
    totals = get_job_totals(job, receipts, job.settings_version)
    allocation_results = compute_allocations(job, allocations, totals, job.settings_version)
    
    # Create snapshot
    snapshot_data = {
        "totals": {
            "total_received": str(totals["total_received"]),
            "connect_deduction": str(totals["connect_deduction"]),
            "platform_fee": str(totals["platform_fee"]),
            "net_distributable": str(totals["net_distributable"])
        },
        "allocations": [
            {
                "allocation_id": r["allocation"].id,
                "worker_id": r["allocation"].worker_id,
                "label": r["allocation"].label,
                "earned": str(r["earned"])
            }
            for r in allocation_results
        ]
    }
    
    snapshot = JobCalculationSnapshot(
        job_id=job_id,
        settings_version_id=job.settings_version_id,
        snapshot_json=json.dumps(snapshot_data)
    )
    db.add(snapshot)
    job.is_finalized = True
    db.commit()
    
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)

@router.post("/jobs/{job_id}/unfinalize")
async def unfinalize_job(job_id: int, db: Session = Depends(get_db_session)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.snapshot:
        db.delete(job.snapshot)
    job.is_finalized = False
    db.commit()
    
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)
