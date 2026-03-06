from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.services.calculations import get_dashboard_totals, compute_worker_totals
from app.models import Worker, Job, User, UserRole, JobAllocation
from app.dependencies import get_db_session
from app.auth import get_current_user, get_active_role
from app.config import BASE_DIR

router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "templates")

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user)
):
    # Get dashboard totals (all time)
    totals = get_dashboard_totals(db)
    
    # Get active role for filtering
    active_role = get_active_role(request)
    
    # Role-based filtering
    if active_role == UserRole.ADMIN:
        # Admin sees all data
        workers = db.query(Worker).filter(Worker.is_archived == False).all()
        recent_jobs = db.query(Job).filter(Job.status != "archived").order_by(desc(Job.created_at)).limit(10).all()
    elif active_role == UserRole.WORKER:
        # Worker sees only their own data
        if not user.worker:
            workers = []
            recent_jobs = []
        else:
            workers = [user.worker] if not user.worker.is_archived else []
            # Get jobs assigned to this worker
            recent_jobs = db.query(Job).join(JobAllocation).filter(
                JobAllocation.worker_id == user.worker.id,
                Job.status != "archived"
            ).distinct().order_by(desc(Job.created_at)).limit(10).all()
    elif active_role == UserRole.MIDDLEMAN:
        # Middleman sees jobs they created
        workers = db.query(Worker).filter(Worker.is_archived == False).all()  # Middlemen can see all workers
        recent_jobs = db.query(Job).filter(
            Job.created_by_user_id == user.id,
            Job.status != "archived"
        ).order_by(desc(Job.created_at)).limit(10).all()
    else:
        workers = []
        recent_jobs = []
    
    # Get top due workers
    worker_dues = []
    for worker in workers:
        worker_totals = compute_worker_totals(worker.id, db)
        if worker_totals["due"] > 0:
            worker_dues.append({
                "worker": worker,
                "due": worker_totals["due"]
            })
    
    # Sort by due amount descending
    worker_dues.sort(key=lambda x: x["due"], reverse=True)
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "totals": totals,
        "worker_dues": worker_dues[:10],  # Top 10
        "recent_jobs": recent_jobs
    })
