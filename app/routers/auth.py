from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.dependencies import get_db_session
from app.models import User, UserRole
from app.auth import get_current_user, get_active_role, hash_password, verify_password
from app.config import BASE_DIR

router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "templates")

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db_session)):
    """Public home page - redirects to dashboard if logged in"""
    if request.session.get("user_id"):
        return RedirectResponse(url="/dashboard", status_code=303)
    
    return templates.TemplateResponse("home.html", {"request": request})

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Show login page"""
    # Redirect if already logged in
    if request.session.get("user_id"):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("auth/login.html", {"request": request})

@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db_session)
):
    """Handle login"""
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "error": "Invalid username or password"
        })
    
    if not user.is_active:
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "error": "Account is inactive"
        })
    
    # Get user roles
    roles = [assignment.role for assignment in user.roles]
    
    if not roles:
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "error": "User has no assigned roles"
        })
    
    # Set session
    request.session["user_id"] = user.id
    request.session["user_roles"] = [r.value for r in roles]
    
    # Set active role (Admin is separate, cannot have Worker/Middleman)
    # Priority: Admin > Worker > Middleman
    # If user has both Worker and Middleman, default to Worker
    if UserRole.ADMIN in roles:
        request.session["active_role"] = UserRole.ADMIN.value
    elif UserRole.WORKER in roles:
        request.session["active_role"] = UserRole.WORKER.value
    elif UserRole.MIDDLEMAN in roles:
        request.session["active_role"] = UserRole.MIDDLEMAN.value
    
    # Redirect to dashboard (no role selection page - admin manages roles)
    return RedirectResponse(url="/dashboard", status_code=303)

@router.post("/logout")
async def logout(request: Request):
    """Handle logout"""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

@router.post("/auth/switch-role")
async def switch_role(
    request: Request,
    role: str = Form(...),
    db: Session = Depends(get_db_session)
):
    """Switch active role"""
    user = get_current_user(request, db)
    user_roles = [assignment.role for assignment in user.roles]
    
    try:
        new_role = UserRole(role)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role")
    
    # Only allow switching between Worker and Middleman
    if new_role not in [UserRole.WORKER, UserRole.MIDDLEMAN]:
        raise HTTPException(status_code=403, detail="Cannot switch to this role")
    
    if new_role not in user_roles:
        raise HTTPException(status_code=403, detail="User does not have this role")
    
    request.session["active_role"] = new_role.value
    # Update user_roles in session
    request.session["user_roles"] = [r.value for r in user_roles]
    return RedirectResponse(url="/dashboard", status_code=303)

@router.get("/profile", response_class=HTMLResponse)
async def user_profile(request: Request, db: Session = Depends(get_db_session)):
    """Show user profile page"""
    user = get_current_user(request, db)
    active_role = get_active_role(request)
    user_roles = [assignment.role.value for assignment in user.roles]
    
    # Get linked entities
    worker = user.worker if user.worker else None
    middleman = user.middleman if hasattr(user, 'middleman') and user.middleman else None
    
    return templates.TemplateResponse("auth/profile.html", {
        "request": request,
        "user": user,
        "active_role": active_role,
        "user_roles": user_roles,
        "worker": worker,
        "middleman": middleman
    })

@router.post("/profile/change-password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db_session)
):
    """Handle password change from profile page"""
    user = get_current_user(request, db)
    active_role = get_active_role(request)
    user_roles = [assignment.role.value for assignment in user.roles]
    worker = user.worker if user.worker else None
    middleman = user.middleman if hasattr(user, 'middleman') and user.middleman else None
    
    # Verify current password
    if not verify_password(current_password, user.password_hash):
        return templates.TemplateResponse("auth/profile.html", {
            "request": request,
            "user": user,
            "active_role": active_role,
            "user_roles": user_roles,
            "worker": worker,
            "middleman": middleman,
            "error": "Current password is incorrect"
        })
    
    # Validate new password
    if new_password != confirm_password:
        return templates.TemplateResponse("auth/profile.html", {
            "request": request,
            "user": user,
            "active_role": active_role,
            "user_roles": user_roles,
            "worker": worker,
            "middleman": middleman,
            "error": "New passwords do not match"
        })
    
    if len(new_password) < 6:
        return templates.TemplateResponse("auth/profile.html", {
            "request": request,
            "user": user,
            "active_role": active_role,
            "user_roles": user_roles,
            "worker": worker,
            "middleman": middleman,
            "error": "Password must be at least 6 characters"
        })
    
    # Update password
    user.password_hash = hash_password(new_password)
    db.commit()
    
    return RedirectResponse(url="/profile?success=password_changed", status_code=303)
