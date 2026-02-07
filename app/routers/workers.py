from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import date
import os
import sys
from io import StringIO, BytesIO

# Configure GTK path for WeasyPrint on Windows
if sys.platform == "win32":
    # Common GTK installation paths
    gtk_paths = [
        r"C:\Program Files\GTK3-Runtime Win64\bin",
        r"C:\Program Files (x86)\GTK3-Runtime Win64\bin",
        r"C:\gtk3-runtime-3.24.31-2022-01-04-ts-win64\bin",
        r"C:\gtk3-runtime\bin",
        r"C:\GTK\bin",
        r"C:\GTK3\bin",
        os.path.join(os.environ.get("ProgramFiles", ""), "GTK3-Runtime Win64", "bin"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "GTK3-Runtime Win64", "bin"),
        # Check in common installation locations
        os.path.join(os.path.expanduser("~"), "gtk3-runtime", "bin"),
        os.path.join(os.path.expanduser("~"), "GTK3", "bin"),
    ]
    
    # Also check PATH for existing GTK installations
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    for path_dir in path_dirs:
        if "gtk" in path_dir.lower() and os.path.exists(path_dir):
            if path_dir not in gtk_paths:
                gtk_paths.insert(0, path_dir)  # Prioritize existing PATH entries
    
    # Try to find and configure GTK
    gtk_found = False
    for gtk_path in gtk_paths:
        if os.path.exists(gtk_path):
            try:
                # Python 3.8+ supports os.add_dll_directory
                if sys.version_info >= (3, 8):
                    os.add_dll_directory(gtk_path)
                # Also add to PATH for this process
                current_path = os.environ.get("PATH", "")
                if gtk_path not in current_path:
                    os.environ["PATH"] = f"{gtk_path};{current_path}"
                gtk_found = True
                break
            except (AttributeError, OSError):
                # Fallback for older Python versions or if add_dll_directory fails
                current_path = os.environ.get("PATH", "")
                if gtk_path not in current_path:
                    os.environ["PATH"] = f"{gtk_path};{current_path}"
                gtk_found = True
                break

# Make WeasyPrint import optional to prevent startup errors
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError) as e:
    WEASYPRINT_AVAILABLE = False
    WEASYPRINT_ERROR = str(e)
    HTML = None  # Placeholder to avoid NameError

from app.database import get_db
from app.models import Worker, Payment
from app.schemas import WorkerCreate, WorkerUpdate
from app.services.calculations import compute_worker_totals
from app.dependencies import get_db_session
from app.utils import generate_worker_code
from app.config import BASE_DIR

router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "templates")

@router.get("/workers", response_class=HTMLResponse)
async def list_workers(request: Request, db: Session = Depends(get_db_session)):
    workers = db.query(Worker).filter(Worker.is_archived == False).order_by(Worker.name).all()
    return templates.TemplateResponse("workers/list.html", {
        "request": request,
        "workers": workers
    })

@router.get("/workers/new", response_class=HTMLResponse)
async def new_worker_form(request: Request, db: Session = Depends(get_db_session)):
    next_code = generate_worker_code(db)
    return templates.TemplateResponse("workers/form.html", {
        "request": request,
        "worker": None,
        "suggested_code": next_code
    })

@router.post("/workers/new")
async def create_worker(
    request: Request,
    worker_code: str = Form(None),
    name: str = Form(...),
    contact: str = Form(None),
    notes: str = Form(None),
    is_owner: str = Form(None),
    db: Session = Depends(get_db_session)
):
    # Auto-generate code if not provided
    if not worker_code or worker_code.strip() == "":
        worker_code = generate_worker_code(db)
    
    # Check if worker_code already exists
    existing = db.query(Worker).filter(Worker.worker_code == worker_code).first()
    if existing:
        next_code = generate_worker_code(db)
        return templates.TemplateResponse("workers/form.html", {
            "request": request,
            "worker": None,
            "suggested_code": next_code,
            "error": f"Worker code {worker_code} already exists"
        }, status_code=400)
    
    # If another worker is already marked as owner, unmark them
    is_owner_bool = is_owner == "1"
    if is_owner_bool:
        existing_owner = db.query(Worker).filter(Worker.is_owner == True, Worker.is_archived == False).first()
        if existing_owner:
            existing_owner.is_owner = False
    
    worker = Worker(
        worker_code=worker_code,
        name=name,
        contact=contact if contact else None,
        notes=notes if notes else None,
        is_owner=is_owner_bool
    )
    db.add(worker)
    db.commit()
    db.refresh(worker)
    
    return RedirectResponse(url=f"/workers/{worker.id}", status_code=303)

@router.get("/workers/{worker_id}", response_class=HTMLResponse)
async def worker_detail(request: Request, worker_id: int, db: Session = Depends(get_db_session)):
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    # Get worker totals
    totals = compute_worker_totals(worker_id, db)
    
    # Get allocations grouped by job
    allocations_by_job = {}
    current_job_ids = set()
    for alloc in worker.allocations:
        if alloc.job.status != "archived":
            current_job_ids.add(alloc.job_id)
            if alloc.job_id not in allocations_by_job:
                allocations_by_job[alloc.job_id] = {
                    "job": alloc.job,
                    "allocations": []
                }
            allocations_by_job[alloc.job_id]["allocations"].append(alloc)
    
    # Get payments
    payments = sorted(worker.payments, key=lambda p: p.paid_date, reverse=True)
    
    # Separate payments into current allocations and historical (no current allocation)
    payments_with_allocation = []
    payments_without_allocation = []
    for payment in payments:
        if payment.job_id and payment.job_id in current_job_ids:
            payments_with_allocation.append(payment)
        else:
            payments_without_allocation.append(payment)
    
    return templates.TemplateResponse("workers/detail.html", {
        "request": request,
        "worker": worker,
        "totals": totals,
        "allocations_by_job": allocations_by_job.values(),
        "payments": payments,  # All payments for backward compatibility
        "payments_with_allocation": payments_with_allocation,
        "payments_without_allocation": payments_without_allocation
    })

@router.get("/workers/{worker_id}/edit", response_class=HTMLResponse)
async def edit_worker_form(request: Request, worker_id: int, db: Session = Depends(get_db_session)):
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    return templates.TemplateResponse("workers/form.html", {
        "request": request,
        "worker": worker
    })

@router.post("/workers/{worker_id}/edit")
async def update_worker(
    request: Request,
    worker_id: int,
    worker_code: str = Form(...),
    name: str = Form(...),
    contact: str = Form(None),
    notes: str = Form(None),
    is_owner: str = Form(None),
    db: Session = Depends(get_db_session)
):
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    # Check if worker_code already exists (for other workers)
    existing = db.query(Worker).filter(Worker.worker_code == worker_code, Worker.id != worker_id).first()
    if existing:
        return templates.TemplateResponse("workers/form.html", {
            "request": request,
            "worker": worker,
            "error": f"Worker code {worker_code} already exists"
        }, status_code=400)
    
    # If this worker is being marked as owner, unmark any other owner
    is_owner_bool = is_owner == "1"
    if is_owner_bool and not worker.is_owner:
        existing_owner = db.query(Worker).filter(Worker.is_owner == True, Worker.is_archived == False, Worker.id != worker_id).first()
        if existing_owner:
            existing_owner.is_owner = False
    
    worker.worker_code = worker_code
    worker.name = name
    worker.contact = contact if contact else None
    worker.notes = notes if notes else None
    worker.is_owner = is_owner_bool
    db.commit()
    
    return RedirectResponse(url=f"/workers/{worker.id}", status_code=303)

@router.post("/workers/{worker_id}/archive")
async def archive_worker(worker_id: int, db: Session = Depends(get_db_session)):
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    worker.is_archived = True
    db.commit()
    
    return RedirectResponse(url="/workers", status_code=303)

@router.get("/workers/{worker_id}/invoice")
async def worker_invoice_pdf(worker_id: int, db: Session = Depends(get_db_session)):
    # Check if WeasyPrint is available
    if not WEASYPRINT_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=f"PDF generation is not available. WeasyPrint dependencies are missing. "
                   f"Error: {WEASYPRINT_ERROR}. Please install GTK+ runtime libraries for Windows "
                   f"or use an alternative PDF generation method."
        )
    
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    # Get worker totals
    totals = compute_worker_totals(worker_id, db)
    
    # Get all paid payments, ordered by date
    paid_payments = db.query(Payment).filter(
        Payment.worker_id == worker_id,
        Payment.is_paid == True
    ).order_by(Payment.paid_date).all()
    
    # Get current date for invoice
    invoice_date = date.today()
    
    # try:
    # Render template to HTML string
    template = templates.get_template("workers/invoice.html")
    html_content = template.render(
        worker=worker,
        totals=totals,
        payments=paid_payments,
        invoice_date=invoice_date
    )
    
    # Convert HTML to PDF using WeasyPrint
    # Create HTML document from string
    html_doc = HTML(string=html_content)
    
    # Write PDF to BytesIO buffer
    pdf_buffer = BytesIO()
    html_doc.write_pdf(target=pdf_buffer)
    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()
    
    # Generate filename
    filename = f"invoice_{worker.worker_code}_{invoice_date.strftime('%Y%m%d')}.pdf"
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
    # except HTTPException:
    #     raise
    # except Exception as e:
    #     raise HTTPException(status_code=500, detail=f"Error generating PDF: {str(e)}")
