from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.dependencies import get_db_session
from app.models import User, UserRole, UserRoleAssignment, Worker, Middleman
from app.auth import get_current_user, get_active_role, require_role, hash_password, UserRole as AuthUserRole
from app.utils import generate_worker_code, generate_middleman_code
from app.config import BASE_DIR

router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "templates")

@router.get("/users", response_class=HTMLResponse)
async def list_users(
    request: Request, 
    db: Session = Depends(get_db_session),
    _: User = Depends(require_role([AuthUserRole.ADMIN]))
):
    """List all users (Admin only)"""
    users = db.query(User).order_by(User.username).all()
    return templates.TemplateResponse("users/list.html", {
        "request": request,
        "users": users
    })

@router.get("/users/new", response_class=HTMLResponse)
async def new_user_form(
    request: Request, 
    db: Session = Depends(get_db_session),
    _: User = Depends(require_role([AuthUserRole.ADMIN]))
):
    """Show form to create new user"""
    return templates.TemplateResponse("users/form.html", {
        "request": request,
        "user": None,
        "user_role_values": []
    })

@router.post("/users/new")
async def create_user(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    is_admin: bool = Form(False),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_role([AuthUserRole.ADMIN]))
):
    """Create new user"""
    # Check if username exists
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return templates.TemplateResponse("users/form.html", {
            "request": request,
            "user": None,
            "user_role_values": [],
            "error": "Username already exists"
        })
    
    # Create user
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        is_active=True
    )
    db.add(user)
    db.flush()
    
    # Auto-assign roles and create entities
    if is_admin:
        # Admin gets ADMIN role
        admin_role = UserRoleAssignment(user_id=user.id, role=UserRole.ADMIN)
        db.add(admin_role)
        
        # Admin also gets Worker and Middleman entities (for full access)
        worker = Worker(
            worker_code=generate_worker_code(db),
            name=username,  # Use username as name
            contact=email,  # Use email as contact
            user_id=user.id
        )
        db.add(worker)
        
        middleman = Middleman(
            middleman_code=generate_middleman_code(db),
            name=username,  # Use username as name
            user_id=user.id
        )
        db.add(middleman)
    else:
        # Normal users automatically get both Worker and Middleman roles
        worker_role = UserRoleAssignment(user_id=user.id, role=UserRole.WORKER)
        db.add(worker_role)
        
        middleman_role = UserRoleAssignment(user_id=user.id, role=UserRole.MIDDLEMAN)
        db.add(middleman_role)
        
        # Auto-create Worker entity
        worker = Worker(
            worker_code=generate_worker_code(db),
            name=username,  # Use username as name
            contact=email,  # Use email as contact
            user_id=user.id
        )
        db.add(worker)
        
        # Auto-create Middleman entity
        middleman = Middleman(
            middleman_code=generate_middleman_code(db),
            name=username,  # Use username as name
            user_id=user.id
        )
        db.add(middleman)
    
    db.commit()
    return RedirectResponse(url=f"/users/{user.id}", status_code=303)

@router.get("/users/{user_id}", response_class=HTMLResponse)
async def user_detail(
    request: Request, 
    user_id: int, 
    db: Session = Depends(get_db_session),
    _: User = Depends(require_role([AuthUserRole.ADMIN]))
):
    """View user details (Admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_roles = [assignment.role for assignment in user.roles]
    worker = user.worker if user.worker else None
    middleman = None
    try:
        middleman = user.middleman if hasattr(user, 'middleman') and user.middleman else None
    except:
        pass
    
    return templates.TemplateResponse("users/detail.html", {
        "request": request,
        "user": user,
        "user_roles": user_roles,
        "worker": worker,
        "middleman": middleman
    })

@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
async def edit_user_form(
    request: Request, 
    user_id: int, 
    db: Session = Depends(get_db_session),
    _: User = Depends(require_role([AuthUserRole.ADMIN]))
):
    """Show form to edit user (Admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_roles = [assignment.role for assignment in user.roles]
    user_role_values = [r.value for r in user_roles]
    
    return templates.TemplateResponse("users/form.html", {
        "request": request,
        "user": user,
        "user_roles": user_roles,
        "user_role_values": user_role_values
    })

@router.post("/users/{user_id}/edit")
async def update_user(
    request: Request,
    user_id: int,
    email: str = Form(...),
    is_admin: bool = Form(False),
    is_worker: bool = Form(False),
    is_middleman: bool = Form(False),
    is_active: bool = Form(True),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_role([AuthUserRole.ADMIN]))
):
    """Update user (Admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update email
    user.email = email
    user.is_active = is_active
    
    # Update Worker contact if worker entity exists
    if user.worker:
        user.worker.contact = email
    
    # Remove all existing role assignments
    db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user.id).delete()
    
    # Assign roles based on selection
    if is_admin:
        # Admin gets ADMIN role
        admin_role = UserRoleAssignment(user_id=user.id, role=UserRole.ADMIN)
        db.add(admin_role)
        
        # Ensure Worker and Middleman entities exist for admin
        if not user.worker:
            worker = Worker(
                worker_code=generate_worker_code(db),
                name=user.username,
                contact=email,
                user_id=user.id
            )
            db.add(worker)
        else:
            # Update existing worker
            user.worker.contact = email
        
        if not user.middleman:
            middleman = Middleman(
                middleman_code=generate_middleman_code(db),
                name=user.username,
                user_id=user.id
            )
            db.add(middleman)
    else:
        # Normal users get both Worker and Middleman roles
        worker_role = UserRoleAssignment(user_id=user.id, role=UserRole.WORKER)
        db.add(worker_role)
        
        middleman_role = UserRoleAssignment(user_id=user.id, role=UserRole.MIDDLEMAN)
        db.add(middleman_role)
        
        # Ensure Worker and Middleman entities exist
        if not user.worker:
            worker = Worker(
                worker_code=generate_worker_code(db),
                name=user.username,
                contact=email,
                user_id=user.id
            )
            db.add(worker)
        else:
            # Update existing worker
            user.worker.contact = email
        
        if not user.middleman:
            middleman = Middleman(
                middleman_code=generate_middleman_code(db),
                name=user.username,
                user_id=user.id
            )
            db.add(middleman)
    
    db.commit()
    return RedirectResponse(url=f"/users/{user.id}", status_code=303)
