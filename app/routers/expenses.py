from fastapi import APIRouter, Depends, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from decimal import Decimal
from datetime import date
from calendar import monthrange
import json
from app.database import get_db
from app.models import Expense, ExpenseCategory, User
from app.dependencies import get_db_session
from app.utils import generate_expense_code
from app.config import BASE_DIR
from app.auth import get_current_user
from app.services.expense_calculations import (
    get_expense_totals,
    get_expense_chart_data,
    calculate_profit,
    calculate_margin
)
from app.services.calculations import get_earnings_for_period, get_owner_earnings_for_period

router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "templates")

@router.get("/expenses", response_class=HTMLResponse)
async def list_expenses(
    request: Request,
    date_from: str = Query(None),
    date_to: str = Query(None),
    category: str = Query(None),
    db: Session = Depends(get_db_session)
):
    """List expenses with optional filters"""
    query = db.query(Expense)
    
    # Apply date filters
    if date_from:
        try:
            date_from_obj = date.fromisoformat(date_from)
            query = query.filter(Expense.expense_date >= date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = date.fromisoformat(date_to)
            query = query.filter(Expense.expense_date <= date_to_obj)
        except ValueError:
            pass
    
    # Apply category filter
    if category and category.strip():
        try:
            category_enum = ExpenseCategory(category.strip().lower())
            query = query.filter(Expense.category == category_enum)
        except ValueError:
            pass
    
    expenses = query.order_by(desc(Expense.expense_date)).all()
    
    return templates.TemplateResponse("expenses/list.html", {
        "request": request,
        "expenses": expenses,
        "date_from": date_from,
        "date_to": date_to,
        "category": category,
        "categories": ExpenseCategory
    })

@router.get("/expenses/new", response_class=HTMLResponse)
async def new_expense_form(request: Request, db: Session = Depends(get_db_session)):
    """New expense form"""
    next_code = generate_expense_code(db)
    return templates.TemplateResponse("expenses/form.html", {
        "request": request,
        "expense": None,
        "suggested_code": next_code,
        "categories": ExpenseCategory
    })

@router.post("/expenses/new")
async def create_expense(
    request: Request,
    expense_date: str = Form(...),
    amount: str = Form(...),
    category: str = Form(...),
    description: str = Form(...),
    vendor: str = Form(None),
    reference: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db_session)
):
    """Create new expense"""
    # Auto-generate code
    expense_code = generate_expense_code(db)
    
    # Check if code already exists
    existing = db.query(Expense).filter(Expense.expense_code == expense_code).first()
    if existing:
        next_code = generate_expense_code(db)
        return templates.TemplateResponse("expenses/form.html", {
            "request": request,
            "expense": None,
            "suggested_code": next_code,
            "categories": ExpenseCategory,
            "error": f"Expense code {expense_code} already exists"
        }, status_code=400)
    
    # Validate amount
    try:
        amount_decimal = Decimal(amount)
        if amount_decimal <= 0:
            raise ValueError("Amount must be greater than 0")
    except (ValueError, TypeError):
        next_code = generate_expense_code(db)
        return templates.TemplateResponse("expenses/form.html", {
            "request": request,
            "expense": None,
            "suggested_code": next_code,
            "categories": ExpenseCategory,
            "error": "Invalid amount"
        }, status_code=400)
    
    # Validate date
    try:
        expense_date_obj = date.fromisoformat(expense_date)
    except ValueError:
        next_code = generate_expense_code(db)
        return templates.TemplateResponse("expenses/form.html", {
            "request": request,
            "expense": None,
            "suggested_code": next_code,
            "categories": ExpenseCategory,
            "error": "Invalid date format"
        }, status_code=400)
    
    # Validate category
    try:
        category_enum = ExpenseCategory(category.strip().lower())
    except ValueError:
        next_code = generate_expense_code(db)
        return templates.TemplateResponse("expenses/form.html", {
            "request": request,
            "expense": None,
            "suggested_code": next_code,
            "categories": ExpenseCategory,
            "error": "Invalid category"
        }, status_code=400)
    
    # Create expense
    expense = Expense(
        expense_code=expense_code,
        expense_date=expense_date_obj,
        amount=amount_decimal,
        category=category_enum,
        description=description.strip(),
        vendor=vendor.strip() if vendor and vendor.strip() else None,
        reference=reference.strip() if reference and reference.strip() else None,
        notes=notes.strip() if notes and notes.strip() else None
    )
    
    db.add(expense)
    db.commit()
    db.refresh(expense)
    
    return RedirectResponse(url=f"/expenses/{expense.id}", status_code=303)

@router.get("/expenses/{expense_id}", response_class=HTMLResponse)
async def expense_detail(request: Request, expense_id: int, db: Session = Depends(get_db_session)):
    """Expense detail page"""
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    return templates.TemplateResponse("expenses/detail.html", {
        "request": request,
        "expense": expense
    })

@router.get("/expenses/{expense_id}/edit", response_class=HTMLResponse)
async def edit_expense_form(request: Request, expense_id: int, db: Session = Depends(get_db_session)):
    """Edit expense form"""
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    return templates.TemplateResponse("expenses/form.html", {
        "request": request,
        "expense": expense,
        "categories": ExpenseCategory
    })

@router.post("/expenses/{expense_id}/edit")
async def update_expense(
    request: Request,
    expense_id: int,
    expense_date: str = Form(...),
    amount: str = Form(...),
    category: str = Form(...),
    description: str = Form(...),
    vendor: str = Form(None),
    reference: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db_session)
):
    """Update expense"""
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    # Validate amount
    try:
        amount_decimal = Decimal(amount)
        if amount_decimal <= 0:
            raise ValueError("Amount must be greater than 0")
    except (ValueError, TypeError):
        return templates.TemplateResponse("expenses/form.html", {
            "request": request,
            "expense": expense,
            "categories": ExpenseCategory,
            "error": "Invalid amount"
        }, status_code=400)
    
    # Validate date
    try:
        expense_date_obj = date.fromisoformat(expense_date)
    except ValueError:
        return templates.TemplateResponse("expenses/form.html", {
            "request": request,
            "expense": expense,
            "categories": ExpenseCategory,
            "error": "Invalid date format"
        }, status_code=400)
    
    # Validate category
    try:
        category_enum = ExpenseCategory(category.strip().lower())
    except ValueError:
        return templates.TemplateResponse("expenses/form.html", {
            "request": request,
            "expense": expense,
            "categories": ExpenseCategory,
            "error": "Invalid category"
        }, status_code=400)
    
    # Update expense
    expense.expense_date = expense_date_obj
    expense.amount = amount_decimal
    expense.category = category_enum
    expense.description = description.strip()
    expense.vendor = vendor.strip() if vendor and vendor.strip() else None
    expense.reference = reference.strip() if reference and reference.strip() else None
    expense.notes = notes.strip() if notes and notes.strip() else None
    
    db.commit()
    db.refresh(expense)
    
    return RedirectResponse(url=f"/expenses/{expense.id}", status_code=303)

@router.post("/expenses/{expense_id}/delete")
async def delete_expense(request: Request, expense_id: int, db: Session = Depends(get_db_session)):
    """Delete expense"""
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    db.delete(expense)
    db.commit()
    
    return RedirectResponse(url="/expenses", status_code=303)

@router.get("/expenses/tracking", response_class=HTMLResponse)
async def expense_tracking(
    request: Request,
    date_from: str = Query(None),
    date_to: str = Query(None),
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user)
):
    """Expense tracking and analytics page"""
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
    
    # Get expense totals for period
    expense_totals = get_expense_totals(db, date_from_obj, date_to_obj)
    
    # Get earnings for period (total)
    earnings_total = get_earnings_for_period(db, date_from_obj, date_to_obj)
    
    # Get owner earnings for period
    owner_earnings_total = Decimal(0)
    try:
        owner_earnings_total = get_owner_earnings_for_period(db, date_from_obj, date_to_obj)
    except Exception as e:
        import logging
        logging.error(f"Error calculating owner earnings: {e}")
        import traceback
        logging.error(traceback.format_exc())
    
    # Calculate profit and margin (using owner earnings)
    profit = calculate_profit(owner_earnings_total, expense_totals)
    margin = calculate_margin(profit, owner_earnings_total)
    
    # Get chart data
    chart_data = get_expense_chart_data(db, date_from_obj, date_to_obj)
    
    return templates.TemplateResponse("expenses/tracking.html", {
        "request": request,
        "expense_totals": expense_totals,
        "earnings_total": earnings_total,
        "owner_earnings_total": owner_earnings_total,
        "profit": profit,
        "margin": margin,
        "chart_data": json.dumps(chart_data),
        "date_from": date_from_obj.isoformat(),
        "date_to": date_to_obj.isoformat()
    })
