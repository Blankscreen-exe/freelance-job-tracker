from fastapi import APIRouter, Depends, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from decimal import Decimal
from datetime import date
from typing import Optional
from app.database import get_db
from app.models import Payment, Worker, Job, User
from app.dependencies import get_db_session
from app.utils import generate_payment_code
from app.config import BASE_DIR
from app.auth import get_current_user, get_active_role, UserRole as AuthUserRole

router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "templates")

@router.get("/payments", response_class=HTMLResponse)
async def list_payments(
    request: Request,
    worker_id: Optional[str] = Query(None),
    job_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user)
):
    # Get active role for filtering
    active_role = get_active_role(request)
    
    # Build query with role-based filtering
    query = db.query(Payment)
    
    # Apply role-based base filter
    if active_role == AuthUserRole.ADMIN:
        # Admin sees all payments
        pass
    elif active_role == AuthUserRole.WORKER:
        # Worker sees only payments related to their jobs
        if user.worker:
            query = query.filter(Payment.worker_id == user.worker.id)
        else:
            query = query.filter(Payment.id == -1)  # No results
    elif active_role == AuthUserRole.MIDDLEMAN:
        # Middleman sees only payments related to jobs they created
        query = query.join(Job).filter(Job.created_by_user_id == user.id)
    else:
        query = query.filter(Payment.id == -1)  # No results
    
    # Filter by worker
    if worker_id and worker_id.strip():
        try:
            worker_id_int = int(worker_id)
            query = query.filter(Payment.worker_id == worker_id_int)
        except ValueError:
            pass  # Invalid worker_id, ignore
    
    # Filter by job
    if job_id and job_id.strip():
        try:
            job_id_int = int(job_id)
            query = query.filter(Payment.job_id == job_id_int)
        except ValueError:
            pass  # Invalid job_id, ignore
    
    # Filter by date range
    if date_from:
        try:
            date_from_obj = date.fromisoformat(date_from)
            query = query.filter(Payment.paid_date >= date_from_obj)
        except ValueError:
            pass  # Invalid date format, ignore
    
    if date_to:
        try:
            date_to_obj = date.fromisoformat(date_to)
            query = query.filter(Payment.paid_date <= date_to_obj)
        except ValueError:
            pass  # Invalid date format, ignore
    
    payments = query.order_by(desc(Payment.paid_date)).all()
    
    # Get workers and jobs for filter dropdowns
    workers = db.query(Worker).filter(Worker.is_archived == False).order_by(Worker.name).all()
    jobs = db.query(Job).filter(Job.status != "archived").order_by(Job.title).all()
    
    # Convert filter IDs to integers for template comparison
    filter_worker_id_int = None
    filter_job_id_int = None
    if worker_id and worker_id.strip():
        try:
            filter_worker_id_int = int(worker_id)
        except ValueError:
            pass
    
    if job_id and job_id.strip():
        try:
            filter_job_id_int = int(job_id)
        except ValueError:
            pass
    
    return templates.TemplateResponse("payments/list.html", {
        "request": request,
        "payments": payments,
        "workers": workers,
        "jobs": jobs,
        "filter_worker_id": filter_worker_id_int,
        "filter_job_id": filter_job_id_int,
        "filter_date_from": date_from,
        "filter_date_to": date_to
    })

@router.get("/payments/new", response_class=HTMLResponse)
async def new_payment_form(request: Request, db: Session = Depends(get_db_session), job_id: int = None):
    workers = db.query(Worker).filter(Worker.is_archived == False).order_by(Worker.name).all()
    jobs = db.query(Job).filter(Job.status != "archived").order_by(Job.title).all()
    next_code = generate_payment_code(db)
    
    return templates.TemplateResponse("payments/form.html", {
        "request": request,
        "payment": None,
        "workers": workers,
        "jobs": jobs,
        "default_job_id": job_id,
        "suggested_code": next_code
    })

@router.post("/payments/new")
async def create_payment(
    request: Request,
    payment_code: str = Form(None),
    worker_id: str = Form(...),
    job_id: str = Form(None),
    amount_paid: str = Form(...),
    paid_date: str = Form(...),
    method: str = Form(None),
    reference: str = Form(None),
    notes: str = Form(None),
    is_paid: str = Form(None),
    db: Session = Depends(get_db_session)
):
    # Auto-generate code if not provided
    if not payment_code or payment_code.strip() == "":
        payment_code = generate_payment_code(db)
    
    # Check if payment_code already exists
    existing = db.query(Payment).filter(Payment.payment_code == payment_code).first()
    if existing:
        workers = db.query(Worker).filter(Worker.is_archived == False).order_by(Worker.name).all()
        jobs = db.query(Job).filter(Job.status != "archived").order_by(Job.title).all()
        next_code = generate_payment_code(db)
        return templates.TemplateResponse("payments/form.html", {
            "request": request,
            "payment": None,
            "workers": workers,
            "jobs": jobs,
            "suggested_code": next_code,
            "error": f"Payment code {payment_code} already exists"
        }, status_code=400)
    
    job_id_int = int(job_id) if job_id and job_id != "None" else None
    
    payment = Payment(
        payment_code=payment_code,
        worker_id=int(worker_id),
        job_id=job_id_int,
        amount_paid=Decimal(amount_paid),
        paid_date=date.fromisoformat(paid_date),
        method=method if method else None,
        reference=reference if reference else None,
        notes=notes if notes else None,
        is_paid=(is_paid == "on") if is_paid else True  # Default to True for manual payments, but allow override
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    
    return RedirectResponse(url="/payments", status_code=303)

@router.post("/payments/{payment_id}/delete")
async def delete_payment(payment_id: int, db: Session = Depends(get_db_session)):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    db.delete(payment)
    db.commit()
    
    return RedirectResponse(url="/payments", status_code=303)

@router.post("/payments/{payment_id}/mark-paid")
async def mark_payment_paid(payment_id: int, db: Session = Depends(get_db_session)):
    """Mark a payment as paid"""
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    payment.is_paid = True
    db.commit()
    
    # Redirect back to where we came from, or payments list
    return RedirectResponse(url="/payments", status_code=303)

@router.post("/payments/{payment_id}/mark-unpaid")
async def mark_payment_unpaid(payment_id: int, db: Session = Depends(get_db_session)):
    """Mark a payment as unpaid"""
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    payment.is_paid = False
    db.commit()
    
    # Redirect back to where we came from, or payments list
    return RedirectResponse(url="/payments", status_code=303)

@router.get("/payments/{payment_id}/edit", response_class=HTMLResponse)
async def edit_payment_form(request: Request, payment_id: int, db: Session = Depends(get_db_session)):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    workers = db.query(Worker).filter(Worker.is_archived == False).order_by(Worker.name).all()
    jobs = db.query(Job).filter(Job.status != "archived").order_by(Job.title).all()
    
    return templates.TemplateResponse("payments/form.html", {
        "request": request,
        "payment": payment,
        "workers": workers,
        "jobs": jobs,
        "suggested_code": payment.payment_code
    })

@router.post("/payments/{payment_id}/edit")
async def update_payment(
    request: Request,
    payment_id: int,
    payment_code: str = Form(None),
    worker_id: str = Form(...),
    job_id: str = Form(None),
    amount_paid: str = Form(...),
    paid_date: str = Form(...),
    method: str = Form(None),
    reference: str = Form(None),
    notes: str = Form(None),
    is_paid: str = Form(None),
    db: Session = Depends(get_db_session)
):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    # Check if payment_code already exists (for other payments)
    if payment_code and payment_code != payment.payment_code:
        existing = db.query(Payment).filter(Payment.payment_code == payment_code, Payment.id != payment_id).first()
        if existing:
            workers = db.query(Worker).filter(Worker.is_archived == False).order_by(Worker.name).all()
            jobs = db.query(Job).filter(Job.status != "archived").order_by(Job.title).all()
            return templates.TemplateResponse("payments/form.html", {
                "request": request,
                "payment": payment,
                "workers": workers,
                "jobs": jobs,
                "suggested_code": payment_code,
                "error": f"Payment code {payment_code} already exists"
            }, status_code=400)
    
    job_id_int = int(job_id) if job_id and job_id != "None" else None
    
    payment.payment_code = payment_code if payment_code else payment.payment_code
    payment.worker_id = int(worker_id)
    payment.job_id = job_id_int
    payment.amount_paid = Decimal(amount_paid)
    payment.paid_date = date.fromisoformat(paid_date)
    payment.method = method if method else None
    payment.reference = reference if reference else None
    payment.notes = notes if notes else None
    payment.is_paid = (is_paid == "on") if is_paid else payment.is_paid
    
    db.commit()
    db.refresh(payment)
    
    return RedirectResponse(url="/payments", status_code=303)
