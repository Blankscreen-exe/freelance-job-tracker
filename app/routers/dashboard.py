from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import date, datetime
from calendar import monthrange
from decimal import Decimal
import json
from app.database import get_db
from app.services.calculations import get_dashboard_totals, compute_worker_totals, get_earnings_for_period, get_owner_earnings_for_period
from app.services.expense_calculations import (
    get_expense_totals,
    get_expense_chart_data,
    calculate_profit,
    calculate_margin
)
from app.models import Worker, Job, User, UserRole, JobAllocation
from app.dependencies import get_db_session
from app.auth import get_current_user, get_active_role
from app.config import BASE_DIR

router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "templates")

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    date_from: str = Query(None),
    date_to: str = Query(None),
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user)
):
    # Parse date filters or default to current month
    today = date.today()
    if date_from:
        try:
            date_from_obj = date.fromisoformat(date_from)
        except ValueError:
            date_from_obj = date(today.year, today.month, 1)
    else:
        date_from_obj = date(today.year, today.month, 1)
    
    if date_to:
        try:
            date_to_obj = date.fromisoformat(date_to)
        except ValueError:
            date_to_obj = date(today.year, today.month, monthrange(today.year, today.month)[1])
    else:
        date_to_obj = date(today.year, today.month, monthrange(today.year, today.month)[1])
    
    # Get dashboard totals (all time)
    totals = get_dashboard_totals(db)
    
    # Get expense totals for period
    expense_totals = get_expense_totals(db, date_from_obj, date_to_obj)
    
    # Get earnings for period (total)
    earnings_total = get_earnings_for_period(db, date_from_obj, date_to_obj)
    
    # Get owner earnings for period
    owner_earnings_total = Decimal(0)  # Initialize to 0
    try:
        owner_earnings_total = get_owner_earnings_for_period(db, date_from_obj, date_to_obj)
    except Exception as e:
        # If there's an error, keep it as 0
        import logging
        logging.error(f"Error calculating owner earnings: {e}")
        import traceback
        logging.error(traceback.format_exc())
    
    # Calculate profit and margin (using owner earnings)
    profit = calculate_profit(owner_earnings_total, expense_totals)
    margin = calculate_margin(profit, owner_earnings_total)
    
    # Get chart data
    chart_data = get_expense_chart_data(db, date_from_obj, date_to_obj)
    
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
        "recent_jobs": recent_jobs,
        "expense_totals": expense_totals,
        "earnings_total": earnings_total,
        "owner_earnings_total": owner_earnings_total,
        "profit": profit,
        "margin": margin,
        "chart_data": json.dumps(chart_data),  # Convert to JSON string for template
        "date_from": date_from_obj.isoformat(),
        "date_to": date_to_obj.isoformat()
    })
