# Task 2: Middleman Management System

## Overview

Implement a comprehensive middleman (work bringer) management system that allows tracking middlemen who bring in projects, linking them to projects, and viewing their commission-related information. This is the foundation for commission tracking and payment features.

**Priority:** Critical (Phase 1)  
**Estimated Time:** 4-6 hours  
**Dependencies:** None (foundational task, but works alongside Task 1)

---

## Requirements (from goals.md)

According to `docs/goals.md`:

- Middleman role (can see their projects + commissions) - Section 1
- Projects should have a middleman assigned - Section 3
- Middleman commission tracking - Section 4
- Middleman dashboard showing:
  - Projects they brought
  - Commission earned
  - Commission paid vs pending - Section 7

---

## Database Changes

### 1. Create Middleman Model

Add to `app/models.py`:

```python
class Middleman(Base):
    __tablename__ = "middlemen"

    id = Column(Integer, primary_key=True, index=True)
    middleman_code = Column(String, unique=True, index=True, nullable=False)  # M01, M02, etc.
    name = Column(String, nullable=False)
    
    # Contact Information
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    contact = Column(String, nullable=True)  # Alternative contact method
    
    # Additional Info
    notes = Column(Text, nullable=True)
    
    # Status
    is_archived = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    jobs = relationship("Job", back_populates="middleman")
    # Commission payments will be added in Task 10
```

### 2. Update Job Model

Modify `app/models.py` - Update the `Job` class:

```python
class Job(Base):
    # ... existing fields ...
    
    # Add middleman relationship
    middleman_id = Column(Integer, ForeignKey("middlemen.id"), nullable=True)  # NEW: Link to Middleman
    
    # ... rest of existing fields ...
    
    # Add relationship
    middleman = relationship("Middleman", back_populates="jobs")
```

**Note:** Commission fields (type, value) will be added in Task 4, but we're setting up the relationship now.

### 3. Create Alembic Migration

Create migration file: `alembic/versions/XXXX_add_middlemen_table.py`

```python
"""Add middlemen table and link to jobs

Revision ID: add_middlemen
Revises: <previous_revision>  # Should be after clients migration
Create Date: <date>
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

def upgrade():
    # Create middlemen table
    op.create_table(
        'middlemen',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('middleman_code', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('contact', sa.String(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_archived', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_middlemen_id'), 'middlemen', ['id'], unique=False)
    op.create_index(op.f('ix_middlemen_middleman_code'), 'middlemen', ['middleman_code'], unique=True)
    
    # Add middleman_id to jobs table
    op.add_column('jobs', sa.Column('middleman_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_jobs_middleman_id', 'jobs', 'middlemen', ['middleman_id'], ['id'])
    op.create_index(op.f('ix_jobs_middleman_id'), 'jobs', ['middleman_id'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_jobs_middleman_id'), table_name='jobs')
    op.drop_constraint('fk_jobs_middleman_id', 'jobs', type_='foreignkey')
    op.drop_column('jobs', 'middleman_id')
    op.drop_index(op.f('ix_middlemen_middleman_code'), table_name='middlemen')
    op.drop_index(op.f('ix_middlemen_id'), table_name='middlemen')
    op.drop_table('middlemen')
```

---

## Implementation Steps

### Step 1: Update Models

1. Add `Middleman` model to `app/models.py`
2. Update `Job` model to include `middleman_id` foreign key
3. Add relationship definitions

### Step 2: Create Utility Function

Add to `app/utils.py`:

```python
def generate_middleman_code(db: Session) -> str:
    """Generate next middleman code (M01, M02, etc.)"""
    from app.models import Middleman
    
    # Get all middlemen
    middlemen = db.query(Middleman).all()
    
    if not middlemen:
        return "M01"
    
    # Extract numbers from existing codes
    import re
    max_num = 0
    for middleman in middlemen:
        match = re.match(r'M(\d+)', middleman.middleman_code)
        if match:
            num = int(match.group(1))
            max_num = max(max_num, num)
    
    return f"M{max_num + 1:02d}"
```

### Step 3: Create Middleman Router

Create `app/routers/middlemen.py`:

```python
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models import Middleman, Job
from app.dependencies import get_db_session
from app.utils import generate_middleman_code
from app.config import BASE_DIR

router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "templates")

@router.get("/middlemen", response_class=HTMLResponse)
async def list_middlemen(request: Request, db: Session = Depends(get_db_session)):
    """List all active middlemen"""
    middlemen = db.query(Middleman).filter(Middleman.is_archived == False).order_by(Middleman.name).all()
    return templates.TemplateResponse("middlemen/list.html", {
        "request": request,
        "middlemen": middlemen
    })

@router.get("/middlemen/new", response_class=HTMLResponse)
async def new_middleman_form(request: Request, db: Session = Depends(get_db_session)):
    """Show form to create new middleman"""
    next_code = generate_middleman_code(db)
    return templates.TemplateResponse("middlemen/form.html", {
        "request": request,
        "middleman": None,
        "suggested_code": next_code
    })

@router.post("/middlemen/new")
async def create_middleman(
    request: Request,
    middleman_code: str = Form(None),
    name: str = Form(...),
    email: str = Form(None),
    phone: str = Form(None),
    contact: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db_session)
):
    """Create new middleman"""
    # Generate code if not provided
    if not middleman_code:
        middleman_code = generate_middleman_code(db)
    
    # Check if code already exists
    existing = db.query(Middleman).filter(Middleman.middleman_code == middleman_code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Middleman code {middleman_code} already exists")
    
    middleman = Middleman(
        middleman_code=middleman_code,
        name=name,
        email=email or None,
        phone=phone or None,
        contact=contact or None,
        notes=notes or None
    )
    
    db.add(middleman)
    db.commit()
    db.refresh(middleman)
    
    return RedirectResponse(url=f"/middlemen/{middleman.id}", status_code=303)

@router.get("/middlemen/{middleman_id}", response_class=HTMLResponse)
async def middleman_detail(request: Request, middleman_id: int, db: Session = Depends(get_db_session)):
    """Show middleman detail page"""
    middleman = db.query(Middleman).filter(Middleman.id == middleman_id).first()
    if not middleman:
        raise HTTPException(status_code=404, detail="Middleman not found")
    
    # Get linked projects
    jobs = db.query(Job).filter(Job.middleman_id == middleman_id).order_by(desc(Job.created_at)).all()
    
    # Calculate summary (will be enhanced in Task 18)
    project_count = len(jobs)
    
    return templates.TemplateResponse("middlemen/detail.html", {
        "request": request,
        "middleman": middleman,
        "jobs": jobs,
        "project_count": project_count
    })

@router.get("/middlemen/{middleman_id}/edit", response_class=HTMLResponse)
async def edit_middleman_form(request: Request, middleman_id: int, db: Session = Depends(get_db_session)):
    """Show form to edit middleman"""
    middleman = db.query(Middleman).filter(Middleman.id == middleman_id).first()
    if not middleman:
        raise HTTPException(status_code=404, detail="Middleman not found")
    
    return templates.TemplateResponse("middlemen/form.html", {
        "request": request,
        "middleman": middleman,
        "suggested_code": middleman.middleman_code
    })

@router.post("/middlemen/{middleman_id}/edit")
async def update_middleman(
    request: Request,
    middleman_id: int,
    name: str = Form(...),
    email: str = Form(None),
    phone: str = Form(None),
    contact: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db_session)
):
    """Update middleman"""
    middleman = db.query(Middleman).filter(Middleman.id == middleman_id).first()
    if not middleman:
        raise HTTPException(status_code=404, detail="Middleman not found")
    
    middleman.name = name
    middleman.email = email or None
    middleman.phone = phone or None
    middleman.contact = contact or None
    middleman.notes = notes or None
    
    db.commit()
    
    return RedirectResponse(url=f"/middlemen/{middleman_id}", status_code=303)

@router.post("/middlemen/{middleman_id}/archive")
async def archive_middleman(middleman_id: int, db: Session = Depends(get_db_session)):
    """Archive (soft delete) middleman"""
    middleman = db.query(Middleman).filter(Middleman.id == middleman_id).first()
    if not middleman:
        raise HTTPException(status_code=404, detail="Middleman not found")
    
    middleman.is_archived = True
    db.commit()
    
    return RedirectResponse(url="/middlemen", status_code=303)
```

### Step 4: Register Router

Update `main.py`:

```python
from app.routers import dashboard, workers, jobs, payments, settings, expenses, clients, middlemen

# ... existing code ...

app.include_router(middlemen.router)
```

### Step 5: Create Templates

#### `templates/middlemen/list.html`

```html
{% extends "base.html" %}

{% block title %}Middlemen{% endblock %}

{% block content %}
<div class="container mt-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h1>Middlemen</h1>
        <a href="/middlemen/new" class="btn btn-primary">
            <i class="bi bi-plus-circle"></i> New Middleman
        </a>
    </div>

    <div class="alert alert-info">
        <i class="bi bi-info-circle"></i> 
        <strong>Middlemen</strong> are work bringers who bring in projects and earn commissions.
    </div>

    {% if middlemen %}
    <div class="table-responsive">
        <table class="table table-striped table-hover">
            <thead>
                <tr>
                    <th>Code</th>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Phone</th>
                    <th>Projects</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {% for middleman in middlemen %}
                <tr>
                    <td><strong>{{ middleman.middleman_code }}</strong></td>
                    <td>
                        <a href="/middlemen/{{ middleman.id }}">{{ middleman.name }}</a>
                    </td>
                    <td>{{ middleman.email or '-' }}</td>
                    <td>{{ middleman.phone or '-' }}</td>
                    <td>
                        <span class="badge bg-secondary">
                            {{ middleman.jobs|length if middleman.jobs else 0 }}
                        </span>
                    </td>
                    <td>
                        <a href="/middlemen/{{ middleman.id }}" class="btn btn-sm btn-outline-primary">
                            <i class="bi bi-eye"></i> View
                        </a>
                        <a href="/middlemen/{{ middleman.id }}/edit" class="btn btn-sm btn-outline-secondary">
                            <i class="bi bi-pencil"></i> Edit
                        </a>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% else %}
    <div class="alert alert-info">
        <i class="bi bi-info-circle"></i> No middlemen found. 
        <a href="/middlemen/new">Create your first middleman</a>
    </div>
    {% endif %}
</div>
{% endblock %}
```

#### `templates/middlemen/form.html`

```html
{% extends "base.html" %}

{% block title %}{{ 'Edit' if middleman else 'New' }} Middleman{% endblock %}

{% block content %}
<div class="container mt-4">
    <h1>{{ 'Edit' if middleman else 'New' }} Middleman</h1>
    
    <form method="POST" action="{{ '/middlemen/' + middleman.id|string + '/edit' if middleman else '/middlemen/new' }}">
        <div class="row">
            <div class="col-md-6">
                <div class="mb-3">
                    <label for="middleman_code" class="form-label">Middleman Code</label>
                    <input type="text" class="form-control" id="middleman_code" name="middleman_code" 
                           value="{{ middleman.middleman_code if middleman else suggested_code }}" 
                           {{ 'readonly' if middleman else '' }} required>
                    <small class="form-text text-muted">Auto-generated if left empty</small>
                </div>
                
                <div class="mb-3">
                    <label for="name" class="form-label">Name <span class="text-danger">*</span></label>
                    <input type="text" class="form-control" id="name" name="name" 
                           value="{{ middleman.name if middleman else '' }}" required>
                </div>
                
                <div class="mb-3">
                    <label for="email" class="form-label">Email</label>
                    <input type="email" class="form-control" id="email" name="email" 
                           value="{{ middleman.email if middleman else '' }}">
                </div>
                
                <div class="mb-3">
                    <label for="phone" class="form-label">Phone</label>
                    <input type="tel" class="form-control" id="phone" name="phone" 
                           value="{{ middleman.phone if middleman else '' }}">
                </div>
            </div>
            
            <div class="col-md-6">
                <div class="mb-3">
                    <label for="contact" class="form-label">Alternative Contact</label>
                    <input type="text" class="form-control" id="contact" name="contact" 
                           value="{{ middleman.contact if middleman else '' }}"
                           placeholder="e.g., Telegram, WhatsApp, etc.">
                    <small class="form-text text-muted">Additional contact method</small>
                </div>
                
                <div class="mb-3">
                    <label for="notes" class="form-label">Notes</label>
                    <textarea class="form-control" id="notes" name="notes" rows="6">{{ middleman.notes if middleman else '' }}</textarea>
                    <small class="form-text text-muted">Internal notes about this middleman</small>
                </div>
            </div>
        </div>
        
        <div class="d-flex gap-2">
            <button type="submit" class="btn btn-primary">
                <i class="bi bi-save"></i> {{ 'Update' if middleman else 'Create' }} Middleman
            </button>
            <a href="{{ '/middlemen/' + middleman.id|string if middleman else '/middlemen' }}" class="btn btn-secondary">
                Cancel
            </a>
        </div>
    </form>
</div>
{% endblock %}
```

#### `templates/middlemen/detail.html`

```html
{% extends "base.html" %}

{% block title %}{{ middleman.name }}{% endblock %}

{% block content %}
<div class="container mt-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
            <h1>{{ middleman.name }}</h1>
            <p class="text-muted mb-0">Code: <strong>{{ middleman.middleman_code }}</strong></p>
        </div>
        <div>
            <a href="/middlemen/{{ middleman.id }}/edit" class="btn btn-outline-primary">
                <i class="bi bi-pencil"></i> Edit
            </a>
            <a href="/middlemen" class="btn btn-secondary">
                <i class="bi bi-arrow-left"></i> Back to Middlemen
            </a>
        </div>
    </div>

    <div class="row">
        <div class="col-md-6">
            <div class="card mb-4">
                <div class="card-header">
                    <h5 class="mb-0">Contact Information</h5>
                </div>
                <div class="card-body">
                    <dl class="row mb-0">
                        {% if middleman.email %}
                        <dt class="col-sm-4">Email:</dt>
                        <dd class="col-sm-8">
                            <a href="mailto:{{ middleman.email }}">{{ middleman.email }}</a>
                        </dd>
                        {% endif %}
                        
                        {% if middleman.phone %}
                        <dt class="col-sm-4">Phone:</dt>
                        <dd class="col-sm-8">
                            <a href="tel:{{ middleman.phone }}">{{ middleman.phone }}</a>
                        </dd>
                        {% endif %}
                        
                        {% if middleman.contact %}
                        <dt class="col-sm-4">Alternative Contact:</dt>
                        <dd class="col-sm-8">{{ middleman.contact }}</dd>
                        {% endif %}
                    </dl>
                </div>
            </div>
        </div>
        
        <div class="col-md-6">
            <div class="card mb-4">
                <div class="card-header">
                    <h5 class="mb-0">Summary</h5>
                </div>
                <div class="card-body">
                    <dl class="row mb-0">
                        <dt class="col-sm-6">Projects Brought:</dt>
                        <dd class="col-sm-6"><strong>{{ project_count }}</strong></dd>
                        
                        <!-- Will be enhanced in Task 18 -->
                        <dt class="col-sm-6">Commission Earned:</dt>
                        <dd class="col-sm-6"><strong class="text-info">$0.00</strong> <small class="text-muted">(Coming in Task 18)</small></dd>
                        
                        <dt class="col-sm-6">Commission Paid:</dt>
                        <dd class="col-sm-6"><strong class="text-success">$0.00</strong> <small class="text-muted">(Coming in Task 18)</small></dd>
                        
                        <dt class="col-sm-6">Commission Pending:</dt>
                        <dd class="col-sm-6"><strong class="text-warning">$0.00</strong> <small class="text-muted">(Coming in Task 18)</small></dd>
                    </dl>
                </div>
            </div>
        </div>
    </div>

    {% if middleman.notes %}
    <div class="card mb-4">
        <div class="card-header">
            <h5 class="mb-0">Notes</h5>
        </div>
        <div class="card-body">
            <p class="mb-0">{{ middleman.notes|nl2br }}</p>
        </div>
    </div>
    {% endif %}

    <div class="card">
        <div class="card-header">
            <h5 class="mb-0">Projects Brought</h5>
        </div>
        <div class="card-body">
            {% if jobs %}
            <div class="table-responsive">
                <table class="table table-sm">
                    <thead>
                        <tr>
                            <th>Code</th>
                            <th>Title</th>
                            <th>Client</th>
                            <th>Status</th>
                            <th>Created</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for job in jobs %}
                        <tr>
                            <td><strong>{{ job.job_code }}</strong></td>
                            <td>
                                <a href="/jobs/{{ job.id }}">{{ job.title }}</a>
                            </td>
                            <td>
                                {% if job.client %}
                                    <a href="/clients/{{ job.client.id }}">{{ job.client.name }}</a>
                                {% else %}
                                    <span class="text-muted">-</span>
                                {% endif %}
                            </td>
                            <td>
                                <span class="badge bg-{{ 'success' if job.status == 'completed' else 'primary' if job.status == 'active' else 'secondary' }}">
                                    {{ job.status }}
                                </span>
                            </td>
                            <td>{{ job.created_at.strftime('%Y-%m-%d') }}</td>
                            <td>
                                <a href="/jobs/{{ job.id }}" class="btn btn-sm btn-outline-primary">
                                    <i class="bi bi-eye"></i> View
                                </a>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <p class="text-muted mb-0">No projects linked to this middleman yet.</p>
            {% endif %}
        </div>
    </div>
</div>
{% endblock %}
```

### Step 6: Update Navigation

Update `templates/base.html` to include Middlemen link in navigation:

```html
<!-- Add to navigation menu -->
<li class="nav-item">
    <a class="nav-link" href="/middlemen">
        <i class="bi bi-person-badge"></i> Middlemen
    </a>
</li>
```

### Step 7: Update Job Forms (Preview for Task 3)

Update `templates/jobs/form.html` to include middleman selection dropdown (will be fully implemented in Task 3):

```html
<!-- Add middleman selection field -->
<div class="mb-3">
    <label for="middleman_id" class="form-label">Middleman (Work Bringer)</label>
    <select class="form-select" id="middleman_id" name="middleman_id">
        <option value="">-- Select Middleman --</option>
        {% for middleman in middlemen %}
        <option value="{{ middleman.id }}" {{ 'selected' if job and job.middleman_id == middleman.id else '' }}>
            {{ middleman.middleman_code }} - {{ middleman.name }}
        </option>
        {% endfor %}
    </select>
    <small class="form-text text-muted">The person who brought in this project</small>
</div>
```

---

## Testing Checklist

### Database
- [ ] Migration runs successfully
- [ ] Middleman table created with correct schema
- [ ] Foreign key relationship works between jobs and middlemen
- [ ] Middleman codes are unique

### CRUD Operations
- [ ] Create new middleman with auto-generated code
- [ ] Create new middleman with custom code
- [ ] View middleman list (shows only active middlemen)
- [ ] View middleman detail page
- [ ] Edit middleman information
- [ ] Archive middleman (soft delete)
- [ ] Archived middlemen don't appear in list

### Middleman Code Generation
- [ ] First middleman gets M01
- [ ] Subsequent middlemen get M02, M03, etc.
- [ ] Handles gaps in numbering correctly

### Job Linking
- [ ] Can link job to middleman (via middleman_id)
- [ ] Middleman detail page shows linked projects
- [ ] Job detail page shows middleman information (if linked)

### UI/UX
- [ ] Navigation includes Middlemen link
- [ ] Forms validate required fields
- [ ] Error handling for duplicate codes
- [ ] Responsive design works on mobile
- [ ] Empty states show helpful messages
- [ ] Info alert explains what middlemen are

### Edge Cases
- [ ] Handle middleman with no projects
- [ ] Handle middleman with no contact info
- [ ] Handle archived middleman (shouldn't appear in dropdowns)
- [ ] Handle middleman deletion attempt when linked to jobs (should prevent or warn)

---

## Dependencies

**This task has no dependencies** - it's a foundational task.

**Works alongside:**
- Task 1: Client Management System (similar structure, can be done in parallel)

**Future tasks that depend on this:**
- Task 3: Project-Middleman-Client Relationships (will enhance middleman linking)
- Task 4: Commission System Foundation (commissions are for middlemen)
- Task 10: Commission Payment Tracking (will track commission payments)
- Task 18: Middleman Dashboard & Reports (will add commission calculations)

---

## Notes

1. **Naming Convention:** Using "Middleman" (singular) and "Middlemen" (plural) to match the goals.md terminology. The code uses `middleman_code` and `middlemen` table name.

2. **Code Format:** Using M01, M02 format to match existing pattern (C01 for clients, W01 for workers, J01 for jobs).

3. **Soft Delete:** Using `is_archived` flag instead of hard delete to preserve data integrity and commission history.

4. **Commission Calculations:** Commission earned, paid, and pending will be implemented in Task 18 (Middleman Dashboard & Reports). For now, just show placeholders.

5. **Contact Fields:** All contact fields are optional. The `contact` field is for alternative contact methods (Telegram, WhatsApp, etc.) beyond email/phone.

6. **Relationship to Workers:** Middlemen are different from workers:
   - **Middlemen**: Bring in projects, earn commissions
   - **Workers**: Do the work, earn payouts from allocations
   - A person could theoretically be both, but they're tracked separately

7. **Commission Fields:** Commission type and value will be added to Job model in Task 4. This task just sets up the relationship.

---

## Next Steps

After completing this task:
1. Test thoroughly using the checklist above
2. Update job creation/edit forms to include middleman selection (Task 3)
3. Proceed to Task 3: Project-Middleman-Client Relationships (to link everything together)
4. Then Task 4: Commission System Foundation (to add commission logic)
