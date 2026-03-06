# Role-Based Authentication System Implementation

## Overview

Implement a role-based authentication system where:

- **Public pages**: Home page (`/`) and Login page (`/login`)
- **Protected pages**: All other routes require authentication
- **Roles**: 
  - **Admin**: Full control, separate role (cannot be Worker/Middleman)
  - **Worker**: Can switch to Middleman if they have both roles
  - **Middleman**: Can switch to Worker if they have both roles
- **Account creation**: Only Admin can create accounts (no registration page)
- **Multi-role support**: Users can have both Worker and Middleman roles and switch between them
- **Role switching**: Only Worker ↔ Middleman can be switched (Admin is separate)
- **Password management**: Admin sets initial username and password; users can change password later (not username)
- **User profile**: Separate profile page for users to view their info and change password

## Database Schema Changes

### 1. User Model (`app/models.py`)

Create a new `User` model:

```python
class UserRole(str, enum.Enum):
    ADMIN = "admin"
    WORKER = "worker"
    MIDDLEMAN = "middleman"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)  # bcrypt hashed password
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    roles = relationship("UserRoleAssignment", back_populates="user", cascade="all, delete-orphan")
    worker = relationship("Worker", back_populates="user", uselist=False)
    middleman = relationship("Middleman", back_populates="user", uselist=False)

class UserRoleAssignment(Base):
    __tablename__ = "user_role_assignments"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="roles")
    
    # Unique constraint: one role per user
    __table_args__ = (UniqueConstraint('user_id', 'role', name='uq_user_role'),)
```

### 2. Update Worker Model (`app/models.py`)

Add `user_id` foreign key to link Worker to User:

```python
class Worker(Base):
    # ... existing fields ...
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, unique=True)
    user = relationship("User", back_populates="worker")
```

### 3. Update Middleman Model (`app/models.py`)

Add `user_id` foreign key when Middleman model is created (Task 2):

```python
class Middleman(Base):
    # ... existing fields ...
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, unique=True)
    user = relationship("User", back_populates="middleman")
```

## Authentication System

### 1. Session Management (`app/auth.py`)

Create authentication utilities:

```python
from fastapi import Request, HTTPException, status
from sqlalchemy.orm import Session
from app.models import User, UserRole, UserRoleAssignment
import bcrypt

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

def get_current_user(request: Request, db: Session) -> User:
    """Get current user from session"""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    
    return user

def get_active_role(request: Request) -> UserRole:
    """Get active role from session"""
    role_str = request.session.get("active_role")
    if not role_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No active role")
    return UserRole(role_str)

def require_role(allowed_roles: list[UserRole]):
    """Decorator to require specific role(s)"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            request = kwargs.get('request') or args[0]
            db = kwargs.get('db') or args[1]
            user = get_current_user(request, db)
            active_role = get_active_role(request)
            
            # Admin has access to everything
            if active_role == UserRole.ADMIN:
                return await func(*args, **kwargs)
            
            # Check if user has the required role
            if active_role not in allowed_roles:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator
```

### 2. Login/Logout Routes (`app/routers/auth.py`)

Create authentication router:

```python
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Show login page"""
    # Redirect if already logged in
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=303)
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
    return RedirectResponse(url="/", status_code=303)

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
    return RedirectResponse(url="/", status_code=303)
```

### 3. User Profile Page (`app/routers/auth.py`)

```python
@router.get("/profile", response_class=HTMLResponse)
async def user_profile(request: Request, db: Session = Depends(get_db_session)):
    """Show user profile page"""
    user = get_current_user(request, db)
    active_role = get_active_role(request)
    user_roles = [assignment.role for assignment in user.roles]
    
    # Get linked entities
    worker = user.worker if hasattr(user, 'worker') else None
    middleman = user.middleman if hasattr(user, 'middleman') else None
    
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
    user_roles = [assignment.role for assignment in user.roles]
    worker = user.worker if hasattr(user, 'worker') else None
    middleman = user.middleman if hasattr(user, 'middleman') else None
    
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
```

## User Management (Admin Only)

### 1. User Management Router (`app/routers/users.py`)

```python
@router.get("/users", response_class=HTMLResponse)
@require_role([UserRole.ADMIN])
async def list_users(request: Request, db: Session = Depends(get_db_session)):
    """List all users (Admin only)"""
    users = db.query(User).order_by(User.username).all()
    return templates.TemplateResponse("users/list.html", {
        "request": request,
        "users": users
    })

@router.get("/users/new", response_class=HTMLResponse)
@require_role([UserRole.ADMIN])
async def new_user_form(request: Request, db: Session = Depends(get_db_session)):
    """Show form to create new user"""
    workers = db.query(Worker).filter(Worker.user_id == None, Worker.is_archived == False).all()
    middlemen = db.query(Middleman).filter(Middleman.user_id == None, Middleman.is_archived == False).all()
    return templates.TemplateResponse("users/form.html", {
        "request": request,
        "user": None,
        "workers": workers,
        "middlemen": middlemen
    })

@router.post("/users/new")
@require_role([UserRole.ADMIN])
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    is_admin: bool = Form(False),
    is_worker: bool = Form(False),
    is_middleman: bool = Form(False),
    worker_id: int = Form(None),
    middleman_id: int = Form(None),
    db: Session = Depends(get_db_session)
):
    """Create new user"""
    # Check if username exists
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        workers = db.query(Worker).filter(Worker.user_id == None, Worker.is_archived == False).all()
        middlemen = db.query(Middleman).filter(Middleman.user_id == None, Middleman.is_archived == False).all()
        return templates.TemplateResponse("users/form.html", {
            "request": request,
            "user": None,
            "workers": workers,
            "middlemen": middlemen,
            "error": "Username already exists"
        })
    
    # Validate: Admin cannot have Worker/Middleman roles
    if is_admin and (is_worker or is_middleman):
        workers = db.query(Worker).filter(Worker.user_id == None, Worker.is_archived == False).all()
        middlemen = db.query(Middleman).filter(Middleman.user_id == None, Middleman.is_archived == False).all()
        return templates.TemplateResponse("users/form.html", {
            "request": request,
            "user": None,
            "workers": workers,
            "middlemen": middlemen,
            "error": "Admin cannot have Worker or Middleman roles"
        })
    
    # At least one role must be selected
    if not (is_admin or is_worker or is_middleman):
        workers = db.query(Worker).filter(Worker.user_id == None, Worker.is_archived == False).all()
        middlemen = db.query(Middleman).filter(Middleman.user_id == None, Middleman.is_archived == False).all()
        return templates.TemplateResponse("users/form.html", {
            "request": request,
            "user": None,
            "workers": workers,
            "middlemen": middlemen,
            "error": "At least one role must be selected"
        })
    
    # Create user
    user = User(
        username=username,
        password_hash=hash_password(password),
        is_active=True
    )
    db.add(user)
    db.flush()
    
    # Assign roles
    if is_admin:
        assignment = UserRoleAssignment(user_id=user.id, role=UserRole.ADMIN)
        db.add(assignment)
    
    if is_worker:
        assignment = UserRoleAssignment(user_id=user.id, role=UserRole.WORKER)
        db.add(assignment)
        
        # Link to Worker entity if provided
        if worker_id:
            worker = db.query(Worker).filter(Worker.id == worker_id).first()
            if worker and worker.user_id is None:
                worker.user_id = user.id
    
    if is_middleman:
        assignment = UserRoleAssignment(user_id=user.id, role=UserRole.MIDDLEMAN)
        db.add(assignment)
        
        # Link to Middleman entity if provided
        if middleman_id:
            middleman = db.query(Middleman).filter(Middleman.id == middleman_id).first()
            if middleman and middleman.user_id is None:
                middleman.user_id = user.id
    
    db.commit()
    return RedirectResponse(url=f"/users/{user.id}", status_code=303)

@router.get("/users/{user_id}", response_class=HTMLResponse)
@require_role([UserRole.ADMIN])
async def user_detail(request: Request, user_id: int, db: Session = Depends(get_db_session)):
    """View user details (Admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_roles = [assignment.role for assignment in user.roles]
    worker = user.worker if hasattr(user, 'worker') else None
    middleman = user.middleman if hasattr(user, 'middleman') else None
    
    return templates.TemplateResponse("users/detail.html", {
        "request": request,
        "user": user,
        "user_roles": user_roles,
        "worker": worker,
        "middleman": middleman
    })

@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
@require_role([UserRole.ADMIN])
async def edit_user_form(request: Request, user_id: int, db: Session = Depends(get_db_session)):
    """Show form to edit user roles (Admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_roles = [assignment.role for assignment in user.roles]
    workers = db.query(Worker).filter(Worker.is_archived == False).all()
    middlemen = db.query(Middleman).filter(Middleman.is_archived == False).all()
    
    return templates.TemplateResponse("users/form.html", {
        "request": request,
        "user": user,
        "user_roles": user_roles,
        "workers": workers,
        "middlemen": middlemen
    })

@router.post("/users/{user_id}/edit")
@require_role([UserRole.ADMIN])
async def update_user(
    request: Request,
    user_id: int,
    is_admin: bool = Form(False),
    is_worker: bool = Form(False),
    is_middleman: bool = Form(False),
    worker_id: int = Form(None),
    middleman_id: int = Form(None),
    is_active: bool = Form(True),
    db: Session = Depends(get_db_session)
):
    """Update user roles (Admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Validate: Admin cannot have Worker/Middleman roles
    if is_admin and (is_worker or is_middleman):
        user_roles = [assignment.role for assignment in user.roles]
        workers = db.query(Worker).filter(Worker.is_archived == False).all()
        middlemen = db.query(Middleman).filter(Middleman.is_archived == False).all()
        return templates.TemplateResponse("users/form.html", {
            "request": request,
            "user": user,
            "user_roles": user_roles,
            "workers": workers,
            "middlemen": middlemen,
            "error": "Admin cannot have Worker or Middleman roles"
        })
    
    # At least one role must be selected
    if not (is_admin or is_worker or is_middleman):
        user_roles = [assignment.role for assignment in user.roles]
        workers = db.query(Worker).filter(Worker.is_archived == False).all()
        middlemen = db.query(Middleman).filter(Middleman.is_archived == False).all()
        return templates.TemplateResponse("users/form.html", {
            "request": request,
            "user": user,
            "user_roles": user_roles,
            "workers": workers,
            "middlemen": middlemen,
            "error": "At least one role must be selected"
        })
    
    # Update active status
    user.is_active = is_active
    
    # Remove all existing role assignments
    db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user.id).delete()
    
    # Add new role assignments
    if is_admin:
        assignment = UserRoleAssignment(user_id=user.id, role=UserRole.ADMIN)
        db.add(assignment)
    
    if is_worker:
        assignment = UserRoleAssignment(user_id=user.id, role=UserRole.WORKER)
        db.add(assignment)
        if worker_id:
            worker = db.query(Worker).filter(Worker.id == worker_id).first()
            if worker:
                # Unlink previous user if exists
                if worker.user_id and worker.user_id != user.id:
                    prev_user = db.query(User).filter(User.id == worker.user_id).first()
                    if prev_user:
                        db.query(UserRoleAssignment).filter(
                            UserRoleAssignment.user_id == prev_user.id,
                            UserRoleAssignment.role == UserRole.WORKER
                        ).delete()
                worker.user_id = user.id
    else:
        # Unlink worker if user no longer has worker role
        if user.worker:
            user.worker.user_id = None
    
    if is_middleman:
        assignment = UserRoleAssignment(user_id=user.id, role=UserRole.MIDDLEMAN)
        db.add(assignment)
        if middleman_id:
            middleman = db.query(Middleman).filter(Middleman.id == middleman_id).first()
            if middleman:
                # Unlink previous user if exists
                if middleman.user_id and middleman.user_id != user.id:
                    prev_user = db.query(User).filter(User.id == middleman.user_id).first()
                    if prev_user:
                        db.query(UserRoleAssignment).filter(
                            UserRoleAssignment.user_id == prev_user.id,
                            UserRoleAssignment.role == UserRole.MIDDLEMAN
                        ).delete()
                middleman.user_id = user.id
    else:
        # Unlink middleman if user no longer has middleman role
        if user.middleman:
            user.middleman.user_id = None
    
    db.commit()
    return RedirectResponse(url=f"/users/{user.id}", status_code=303)
```

## Route Protection

### 1. Update All Routers

Add authentication dependency to all protected routes and implement role-based filtering:

```python
from app.auth import get_current_user, get_active_role, require_role, UserRole
from app.models import User

@router.get("/jobs")
async def list_jobs(
    request: Request,
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user)
):
    active_role = get_active_role(request)
    
    # Admin sees all jobs
    if active_role == UserRole.ADMIN:
        jobs = db.query(Job).filter(Job.is_archived == False).all()
    # Worker sees only jobs they're assigned to
    elif active_role == UserRole.WORKER:
        if not user.worker:
            jobs = []
        else:
            jobs = db.query(Job).join(JobAllocation).filter(
                JobAllocation.worker_id == user.worker.id,
                Job.is_archived == False
            ).distinct().all()
    # Middleman sees only jobs they brought
    elif active_role == UserRole.MIDDLEMAN:
        if not user.middleman:
            jobs = []
        else:
            jobs = db.query(Job).filter(
                Job.middleman_id == user.middleman.id,
                Job.is_archived == False
            ).all()
    else:
        jobs = []
    
    return templates.TemplateResponse("jobs/list.html", {
        "request": request,
        "jobs": jobs
    })
```

**Note**: Similar filtering logic needs to be applied to:
- `/workers` - Workers see only themselves, Middlemen see all workers
- `/payments` - Workers see only their payments, Middlemen see commission-related payments
- `/dashboard` - Role-specific dashboards (see Dashboard section)

### 2. Middleware for Route Protection (`main.py`)

```python
from starlette.middleware.sessions import SessionMiddleware
from app.config import settings

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Allow public routes
    public_routes = ["/", "/login", "/static"]
    if any(request.url.path.startswith(route) for route in public_routes):
        return await call_next(request)
    
    # Check authentication for all other routes
    if not request.session.get("user_id"):
        if request.url.path.startswith("/api"):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        return RedirectResponse(url="/login", status_code=303)
    
    return await call_next(request)
```

## UI Components

### 1. Role Switcher in Navbar (`templates/base.html`)

Add role switcher dropdown for users with multiple roles:

```html
{% if user_roles|length > 1 and 'admin' not in user_roles %}
<div class="dropdown">
    <button class="btn btn-outline-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown">
        Role: {{ active_role|title }}
    </button>
    <ul class="dropdown-menu">
        {% for role in user_roles %}
        {% if role in ['worker', 'middleman'] %}
        <li>
            <form method="POST" action="/auth/switch-role" style="display: inline;">
                <input type="hidden" name="role" value="{{ role }}">
                <button type="submit" class="dropdown-item">
                    {{ role|title }}
                </button>
            </form>
        </li>
        {% endif %}
        {% endfor %}
    </ul>
</div>
{% endif %}
```

### 2. Home Page (`app/routers/auth.py` or `app/routers/dashboard.py`)

```python
@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db_session)):
    """Public home page - redirects to dashboard if logged in"""
    if request.session.get("user_id"):
        return RedirectResponse(url="/dashboard", status_code=303)
    
    return templates.TemplateResponse("home.html", {"request": request})
```

### 3. Login Page (`templates/auth/login.html`)

Create login form with username/password fields. Simple, clean design with:
- Username input
- Password input
- Submit button
- Error message display area
- Link to home page

### 4. User Profile Page (`templates/auth/profile.html`)

Create user profile page showing:
- Username (read-only, cannot be changed)
- Active role
- Assigned roles (if multiple)
- Linked Worker entity (if applicable)
- Linked Middleman entity (if applicable)
- Password change form
- Success/error messages

### 5. User Management Pages (Admin Only)

Create templates for:

- `templates/users/list.html` - List all users with their roles, status, linked entities
- `templates/users/form.html` - Create/edit user form with:
  - Username input (disabled for edit)
  - Password input (only for new users)
  - Role checkboxes (Admin, Worker, Middleman) with validation
  - Worker dropdown (if Worker role selected)
  - Middleman dropdown (if Middleman role selected)
  - Active/Inactive toggle
- `templates/users/detail.html` - User detail page showing:
  - User information
  - Assigned roles
  - Linked Worker/Middleman entities
  - Edit button
  - Activity history (optional)

## Database Migration

### 1. Alembic Migration (`alembic/versions/add_user_auth.py`)

Create migration to:

1. Create `users` table
2. Create `user_role_assignments` table
3. Add `user_id` to `workers` table
4. Add `user_id` to `middlemen` table (when Task 2 is implemented)
5. Create first admin user (username: "admin", password: "admin123" - should be changed on first login)

## Role-Based Dashboard Views

### 1. Admin Dashboard (`app/routers/dashboard.py`)

Admin sees full dashboard with all data:
- Total receivable
- Total received
- Total payable to workers
- Net retained earnings
- Top paying clients
- Projects at risk (unpaid)
- All expenses
- All jobs

### 2. Worker Dashboard (`app/routers/dashboard.py`)

Worker sees their own data:
- Projects assigned to them
- Earnings (total earned)
- Paid vs pending payouts
- Payment history

### 3. Middleman Dashboard (`app/routers/dashboard.py`)

Middleman sees their own data:
- Projects they brought
- Commission earned
- Commission paid vs pending
- Commission payment history

**Implementation Note**: The existing dashboard route needs to be updated to check active role and filter data accordingly.

## Database Migration

### 1. Alembic Migration (`alembic/versions/add_user_auth.py`)

Create migration file with revision ID. The migration should:

1. Create `users` table with all fields
2. Create `user_role_assignments` table with unique constraint
3. Add `user_id` column to `workers` table (nullable, unique)
4. Add `user_id` column to `middlemen` table (nullable, unique) - when Middleman model exists
5. Create indexes on `users.username` and `user_role_assignments.user_id`
6. Create first admin user

**Migration Code**:

```python
"""Add user authentication and role system

Revision ID: add_user_auth
Revises: <previous_revision>
Create Date: <date>
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite
from sqlalchemy import text

def upgrade():
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    
    # Create user_role_assignments table
    op.create_table(
        'user_role_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.Enum('ADMIN', 'WORKER', 'MIDDLEMAN', name='userrole'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'role', name='uq_user_role')
    )
    op.create_index(op.f('ix_user_role_assignments_id'), 'user_role_assignments', ['id'], unique=False)
    op.create_index(op.f('ix_user_role_assignments_user_id'), 'user_role_assignments', ['user_id'], unique=False)
    
    # Add user_id to workers table
    with op.batch_alter_table('workers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_workers_user_id', 'users', ['user_id'], ['id'])
        batch_op.create_index(batch_op.f('ix_workers_user_id'), ['user_id'], unique=True)
    
    # Add user_id to middlemen table (when it exists)
    # This will be added in a later migration when Middleman model is created
    # For now, we'll skip it or add a check:
    try:
        with op.batch_alter_table('middlemen', schema=None) as batch_op:
            batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_middlemen_user_id', 'users', ['user_id'], ['id'])
            batch_op.create_index(batch_op.f('ix_middlemen_user_id'), ['user_id'], unique=True)
    except:
        # Table doesn't exist yet, will be added in Task 2 migration
        pass
    
    # Create first admin user
    # Note: Import hash_password function or inline bcrypt
    import bcrypt
    password_hash = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    op.execute(text("""
        INSERT INTO users (username, password_hash, is_active, created_at, updated_at)
        VALUES ('admin', :password_hash, 1, datetime('now'), datetime('now'))
    """).bindparams(password_hash=password_hash))
    
    # Get the admin user ID and assign ADMIN role
    connection = op.get_bind()
    result = connection.execute(text("SELECT id FROM users WHERE username = 'admin'"))
    admin_id = result.fetchone()[0]
    
    op.execute(text("""
        INSERT INTO user_role_assignments (user_id, role, created_at)
        VALUES (:user_id, 'ADMIN', datetime('now'))
    """).bindparams(user_id=admin_id))

def downgrade():
    # Remove user_id from middlemen table
    try:
        with op.batch_alter_table('middlemen', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_middlemen_user_id'))
            batch_op.drop_constraint('fk_middlemen_user_id', type_='foreignkey')
            batch_op.drop_column('user_id')
    except:
        pass
    
    # Remove user_id from workers table
    with op.batch_alter_table('workers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_workers_user_id'))
        batch_op.drop_constraint('fk_workers_user_id', type_='foreignkey')
        batch_op.drop_column('user_id')
    
    # Drop user_role_assignments table
    op.drop_index(op.f('ix_user_role_assignments_user_id'), table_name='user_role_assignments')
    op.drop_index(op.f('ix_user_role_assignments_id'), table_name='user_role_assignments')
    op.drop_table('user_role_assignments')
    
    # Drop users table
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_table('users')
```

## Additional Requirements

### 1. Update `main.py`

Add session middleware and authentication router:

```python
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from app.config import settings
from app.routers import auth

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.include_router(auth.router)

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Allow public routes
    public_routes = ["/", "/login", "/static"]
    if any(request.url.path.startswith(route) for route in public_routes):
        return await call_next(request)
    
    # Check authentication for all other routes
    if not request.session.get("user_id"):
        if request.url.path.startswith("/api"):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        return RedirectResponse(url="/login", status_code=303)
    
    return await call_next(request)
```

### 2. Update `requirements.txt`

Add bcrypt dependency:

```
bcrypt>=4.0.0
```

### 3. Update Base Template (`templates/base.html`)

Add to navbar:
- User profile link (for all authenticated users)
- Role switcher dropdown (for users with Worker + Middleman roles)
- Logout button
- "Users" link (Admin only)

### 4. Role-Based Navigation

Update navigation to show/hide items based on role:
- Admin: All navigation items visible
- Worker: Dashboard, Jobs (filtered), Payments (filtered), Profile
- Middleman: Dashboard, Jobs (filtered), Payments (filtered), Profile

## Testing Checklist

1. **Authentication**:
   - [ ] Login with valid credentials
   - [ ] Login with invalid credentials (error shown)
   - [ ] Login with inactive user (error shown)
   - [ ] Logout clears session
   - [ ] Accessing protected route without login redirects to login

2. **Role Management**:
   - [ ] Admin can create users
   - [ ] Admin can assign roles
   - [ ] Admin cannot assign Worker/Middleman to Admin user
   - [ ] Admin can edit user roles
   - [ ] Admin can activate/deactivate users

3. **Role Switching**:
   - [ ] User with Worker + Middleman can switch roles
   - [ ] Role switcher only shows Worker/Middleman (not Admin)
   - [ ] Dashboard updates based on active role
   - [ ] Data filtering works correctly after role switch

4. **Password Management**:
   - [ ] User can change password from profile page
   - [ ] Current password must be correct
   - [ ] New password must match confirmation
   - [ ] Password minimum length enforced
   - [ ] Username cannot be changed

5. **Data Filtering**:
   - [ ] Admin sees all data
   - [ ] Worker sees only their assigned jobs/payments
   - [ ] Middleman sees only their projects/commissions
   - [ ] Filtering persists across role switches

6. **User Profile**:
   - [ ] Profile page shows user info
   - [ ] Profile page shows linked Worker/Middleman entities
   - [ ] Profile page shows assigned roles
   - [ ] Password change works from profile

## Implementation Order

1. Create `app/auth.py` with authentication utilities
2. Create `app/models.py` updates (User, UserRoleAssignment)
3. Create Alembic migration
4. Create `app/routers/auth.py` with login/logout/profile routes
5. Create `app/routers/users.py` with user management (Admin only)
6. Update `main.py` with middleware and router registration
7. Update all existing routers with authentication dependencies
8. Create templates (login, profile, user management)
9. Update `templates/base.html` with navigation and role switcher
10. Update dashboard and other routes with role-based filtering
11. Test thoroughly

## Notes

- **Client Entity Exception**: Client login/authentication will be handled separately in a future task
- **Middleman Model**: The `user_id` foreign key will be added to the Middleman model when Task 2 (Middleman Management) is implemented
- **Session Security**: Ensure `SECRET_KEY` in `.env` is strong and unique for production
- **Password Policy**: Currently minimum 6 characters; can be enhanced later
- **Username Uniqueness**: Enforced at database level with unique index