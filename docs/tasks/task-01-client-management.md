# Task 1: Client Management System

## Overview

Implement a comprehensive client management system with **separate CRUD pages** for clients (similar to the jobs CRUD interface). Clients can be created, edited, and managed independently. When creating or editing a job, users will select a client from a dropdown (clients must be created first in the separate clients section).

**Priority:** Critical (Phase 1)  
**Estimated Time:** 4-6 hours  
**Dependencies:** None (foundational task)

**Key Design Decision:**
- Clients have their own dedicated CRUD interface (`/clients`, `/clients/new`, `/clients/{id}`, `/clients/{id}/edit`)
- Job forms include a **dropdown only** to select an existing client
- No client creation fields in job forms - users must create clients separately first

---

## Requirements (from goals.md)

According to `docs/goals.md` Section 2, each client should have:

- Client name
- Contact info
- Linked projects
- Total invoiced
- Total received
- Outstanding balance
- Payment history log

Dashboard view should show:
- Total receivables
- Overdue clients

---

## Database Changes

### 1. Create Client Model

Add to `app/models.py`:

```python
class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    client_code = Column(String, unique=True, index=True, nullable=False)  # C01, C02, etc.
    name = Column(String, nullable=False)
    
    # Source Information (where client was found)
    source = Column(SQLEnum(JobSource), nullable=True)  # Reuse JobSource enum: upwork, linkedin, direct, etc.
    source_url = Column(String, nullable=True)  # URL where client was found (e.g., Upwork profile, LinkedIn profile)
    source_notes = Column(Text, nullable=True)  # Additional notes about how client was found
    
    # Primary Contact Information
    contact_person = Column(String, nullable=True)  # Primary contact name
    email = Column(String, nullable=True)  # Primary email
    phone = Column(String, nullable=True)  # Primary phone
    mobile = Column(String, nullable=True)  # Mobile phone (alternative)
    
    # Additional Contact Methods
    alternative_email = Column(String, nullable=True)  # Secondary email
    alternative_phone = Column(String, nullable=True)  # Secondary phone
    telegram = Column(String, nullable=True)  # Telegram username/ID
    whatsapp = Column(String, nullable=True)  # WhatsApp number
    skype = Column(String, nullable=True)  # Skype username
    linkedin = Column(String, nullable=True)  # LinkedIn profile URL
    other_contact = Column(String, nullable=True)  # Other contact method
    
    # Company/Organization Information
    company_name = Column(String, nullable=True)  # Company name (if different from client name)
    company_registration = Column(String, nullable=True)  # Registration number/tax ID
    company_website = Column(String, nullable=True)  # Company website
    company_email = Column(String, nullable=True)  # Company email (info@company.com)
    
    # Address Information
    address_line1 = Column(String, nullable=True)  # Street address
    address_line2 = Column(String, nullable=True)  # Apartment, suite, etc.
    city = Column(String, nullable=True)
    state_province = Column(String, nullable=True)  # State or Province
    postal_code = Column(String, nullable=True)  # ZIP/Postal code
    country = Column(String, nullable=True)
    timezone = Column(String, nullable=True)  # Timezone (e.g., "America/New_York", "UTC")
    
    # Legacy address field (for backward compatibility, can be populated from address fields)
    address = Column(Text, nullable=True)  # Full address as text (legacy)
    
    # Additional Information
    industry = Column(String, nullable=True)  # Industry sector
    company_size = Column(String, nullable=True)  # e.g., "1-10", "11-50", "51-200", etc.
    preferred_communication = Column(String, nullable=True)  # Preferred contact method
    working_hours = Column(String, nullable=True)  # Working hours/timezone notes
    
    # Notes and Internal Information
    notes = Column(Text, nullable=True)  # General notes
    internal_notes = Column(Text, nullable=True)  # Internal-only notes (not shared with client)
    tags = Column(String, nullable=True)  # Comma-separated tags for categorization
    
    # Status
    is_archived = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)  # Active client (vs archived)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_contacted = Column(DateTime, nullable=True)  # Last time client was contacted

    # Relationships
    jobs = relationship("Job", back_populates="client")
```

### 2. Update Job Model

Modify `app/models.py` - Update the `Job` class:

```python
class Job(Base):
    # ... existing fields ...
    
    # Replace or supplement existing client fields:
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)  # NEW: Link to Client
    # Keep client_name for backward compatibility (nullable=True)
    # Keep company_name, company_email, etc. for backward compatibility
    
    # ... rest of existing fields ...
    
    # Add relationship
    client = relationship("Client", back_populates="jobs")
```

**Migration Strategy:**
- Add `client_id` as nullable initially
- Migrate existing `client_name` data to Client records (optional, can be done manually)
- Keep old fields for backward compatibility

### 3. Create Alembic Migration

Create migration file: `alembic/versions/XXXX_add_clients_table.py`

```python
"""Add clients table and link to jobs

Revision ID: add_clients
Revises: <previous_revision>
Create Date: <date>
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

def upgrade():
    # Create clients table with extensive fields
    op.create_table(
        'clients',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_code', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        
        # Source Information
        sa.Column('source', sa.String(), nullable=True),  # Will use JobSource enum values
        sa.Column('source_url', sa.String(), nullable=True),
        sa.Column('source_notes', sa.Text(), nullable=True),
        
        # Primary Contact
        sa.Column('contact_person', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('mobile', sa.String(), nullable=True),
        
        # Additional Contact Methods
        sa.Column('alternative_email', sa.String(), nullable=True),
        sa.Column('alternative_phone', sa.String(), nullable=True),
        sa.Column('telegram', sa.String(), nullable=True),
        sa.Column('whatsapp', sa.String(), nullable=True),
        sa.Column('skype', sa.String(), nullable=True),
        sa.Column('linkedin', sa.String(), nullable=True),
        sa.Column('other_contact', sa.String(), nullable=True),
        
        # Company Information
        sa.Column('company_name', sa.String(), nullable=True),
        sa.Column('company_registration', sa.String(), nullable=True),
        sa.Column('company_website', sa.String(), nullable=True),
        sa.Column('company_email', sa.String(), nullable=True),
        
        # Address Information
        sa.Column('address_line1', sa.String(), nullable=True),
        sa.Column('address_line2', sa.String(), nullable=True),
        sa.Column('city', sa.String(), nullable=True),
        sa.Column('state_province', sa.String(), nullable=True),
        sa.Column('postal_code', sa.String(), nullable=True),
        sa.Column('country', sa.String(), nullable=True),
        sa.Column('timezone', sa.String(), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),  # Legacy field
        
        # Additional Information
        sa.Column('industry', sa.String(), nullable=True),
        sa.Column('company_size', sa.String(), nullable=True),
        sa.Column('preferred_communication', sa.String(), nullable=True),
        sa.Column('working_hours', sa.String(), nullable=True),
        
        # Notes
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('internal_notes', sa.Text(), nullable=True),
        sa.Column('tags', sa.String(), nullable=True),
        
        # Status
        sa.Column('is_archived', sa.Boolean(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('last_contacted', sa.DateTime(), nullable=True),
        
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_clients_id'), 'clients', ['id'], unique=False)
    op.create_index(op.f('ix_clients_client_code'), 'clients', ['client_code'], unique=True)
    op.create_index(op.f('ix_clients_source'), 'clients', ['source'], unique=False)  # For filtering by source
    
    # Add client_id to jobs table
    op.add_column('jobs', sa.Column('client_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_jobs_client_id', 'jobs', 'clients', ['client_id'], ['id'])
    op.create_index(op.f('ix_jobs_client_id'), 'jobs', ['client_id'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_jobs_client_id'), table_name='jobs')
    op.drop_constraint('fk_jobs_client_id', 'jobs', type_='foreignkey')
    op.drop_column('jobs', 'client_id')
    op.drop_index(op.f('ix_clients_client_code'), table_name='clients')
    op.drop_index(op.f('ix_clients_id'), table_name='clients')
    op.drop_table('clients')
```

---

## Implementation Steps

### Step 1: Update Models

1. Add `Client` model to `app/models.py`
2. Update `Job` model to include `client_id` foreign key
3. Add relationship definitions

### Step 2: Create Utility Function

Add to `app/utils.py`:

```python
def generate_client_code(db: Session) -> str:
    """Generate next client code (C01, C02, etc.)"""
    # Get all clients
    clients = db.query(Client).all()
    
    if not clients:
        return "C01"
    
    # Extract numbers from existing codes
    import re
    max_num = 0
    for client in clients:
        match = re.match(r'C(\d+)', client.client_code)
        if match:
            num = int(match.group(1))
            max_num = max(max_num, num)
    
    return f"C{max_num + 1:02d}"
```

### Step 3: Create Client Router

**Important:** This creates a **separate CRUD interface** for clients, just like the jobs CRUD interface. Clients are managed independently from jobs.

Create `app/routers/clients.py`:

```python
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models import Client, Job
from app.dependencies import get_db_session
from app.utils import generate_client_code
from app.config import BASE_DIR

router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "templates")

@router.get("/clients", response_class=HTMLResponse)
async def list_clients(request: Request, db: Session = Depends(get_db_session)):
    """List all active clients"""
    clients = db.query(Client).filter(Client.is_archived == False).order_by(Client.name).all()
    return templates.TemplateResponse("clients/list.html", {
        "request": request,
        "clients": clients
    })

@router.get("/clients/new", response_class=HTMLResponse)
async def new_client_form(request: Request, db: Session = Depends(get_db_session)):
    """Show form to create new client"""
    from app.models import JobSource
    
    next_code = generate_client_code(db)
    return templates.TemplateResponse("clients/form.html", {
        "request": request,
        "client": None,
        "suggested_code": next_code,
        "source_options": [s.value for s in JobSource]
    })

@router.post("/clients/new")
async def create_client(
    request: Request,
    client_code: str = Form(None),
    name: str = Form(...),
    # Source Information
    source: str = Form(None),
    source_url: str = Form(None),
    source_notes: str = Form(None),
    # Primary Contact
    contact_person: str = Form(None),
    email: str = Form(None),
    phone: str = Form(None),
    mobile: str = Form(None),
    # Additional Contact
    alternative_email: str = Form(None),
    alternative_phone: str = Form(None),
    telegram: str = Form(None),
    whatsapp: str = Form(None),
    skype: str = Form(None),
    linkedin: str = Form(None),
    other_contact: str = Form(None),
    # Company Information
    company_name: str = Form(None),
    company_registration: str = Form(None),
    company_website: str = Form(None),
    company_email: str = Form(None),
    # Address
    address_line1: str = Form(None),
    address_line2: str = Form(None),
    city: str = Form(None),
    state_province: str = Form(None),
    postal_code: str = Form(None),
    country: str = Form(None),
    timezone: str = Form(None),
    address: str = Form(None),  # Legacy field
    # Additional Info
    industry: str = Form(None),
    company_size: str = Form(None),
    preferred_communication: str = Form(None),
    working_hours: str = Form(None),
    # Notes
    notes: str = Form(None),
    internal_notes: str = Form(None),
    tags: str = Form(None),
    # Status
    is_active: str = Form("true"),
    db: Session = Depends(get_db_session)
):
    """Create new client"""
    from app.models import JobSource
    
    # Generate code if not provided
    if not client_code:
        client_code = generate_client_code(db)
    
    # Check if code already exists
    existing = db.query(Client).filter(Client.client_code == client_code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Client code {client_code} already exists")
    
    # Validate source enum if provided
    source_enum = None
    if source:
        try:
            source_enum = JobSource(source.lower())
        except ValueError:
            source_enum = None  # Invalid source, will be stored as None
    
    # Build address from components if legacy address not provided
    full_address = address
    if not full_address and (address_line1 or city or country):
        address_parts = []
        if address_line1:
            address_parts.append(address_line1)
        if address_line2:
            address_parts.append(address_line2)
        if city:
            address_parts.append(city)
        if state_province:
            address_parts.append(state_province)
        if postal_code:
            address_parts.append(postal_code)
        if country:
            address_parts.append(country)
        full_address = ", ".join(address_parts) if address_parts else None
    
    client = Client(
        client_code=client_code,
        name=name,
        # Source
        source=source_enum,
        source_url=source_url or None,
        source_notes=source_notes or None,
        # Primary Contact
        contact_person=contact_person or None,
        email=email or None,
        phone=phone or None,
        mobile=mobile or None,
        # Additional Contact
        alternative_email=alternative_email or None,
        alternative_phone=alternative_phone or None,
        telegram=telegram or None,
        whatsapp=whatsapp or None,
        skype=skype or None,
        linkedin=linkedin or None,
        other_contact=other_contact or None,
        # Company
        company_name=company_name or None,
        company_registration=company_registration or None,
        company_website=company_website or None,
        company_email=company_email or None,
        # Address
        address_line1=address_line1 or None,
        address_line2=address_line2 or None,
        city=city or None,
        state_province=state_province or None,
        postal_code=postal_code or None,
        country=country or None,
        timezone=timezone or None,
        address=full_address,
        # Additional Info
        industry=industry or None,
        company_size=company_size or None,
        preferred_communication=preferred_communication or None,
        working_hours=working_hours or None,
        # Notes
        notes=notes or None,
        internal_notes=internal_notes or None,
        tags=tags or None,
        # Status
        is_active=is_active.lower() == "true" if is_active else True
    )
    
    db.add(client)
    db.commit()
    db.refresh(client)
    
    return RedirectResponse(url=f"/clients/{client.id}", status_code=303)

@router.get("/clients/{client_id}", response_class=HTMLResponse)
async def client_detail(request: Request, client_id: int, db: Session = Depends(get_db_session)):
    """Show client detail page"""
    from app.models import JobSource
    
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Get linked projects
    jobs = db.query(Job).filter(Job.client_id == client_id).order_by(desc(Job.created_at)).all()
    
    # Calculate totals (will be enhanced in Task 17)
    # For now, just count projects
    project_count = len(jobs)
    
    # Get all source options for display
    source_options = [s.value for s in JobSource]
    
    return templates.TemplateResponse("clients/detail.html", {
        "request": request,
        "client": client,
        "jobs": jobs,
        "project_count": project_count,
        "source_options": source_options
    })

@router.get("/clients/{client_id}/edit", response_class=HTMLResponse)
async def edit_client_form(request: Request, client_id: int, db: Session = Depends(get_db_session)):
    """Show form to edit client"""
    from app.models import JobSource
    
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    return templates.TemplateResponse("clients/form.html", {
        "request": request,
        "client": client,
        "suggested_code": client.client_code,
        "source_options": [s.value for s in JobSource]
    })

@router.post("/clients/{client_id}/edit")
async def update_client(
    request: Request,
    client_id: int,
    name: str = Form(...),
    # Source Information
    source: str = Form(None),
    source_url: str = Form(None),
    source_notes: str = Form(None),
    # Primary Contact
    contact_person: str = Form(None),
    email: str = Form(None),
    phone: str = Form(None),
    mobile: str = Form(None),
    # Additional Contact
    alternative_email: str = Form(None),
    alternative_phone: str = Form(None),
    telegram: str = Form(None),
    whatsapp: str = Form(None),
    skype: str = Form(None),
    linkedin: str = Form(None),
    other_contact: str = Form(None),
    # Company Information
    company_name: str = Form(None),
    company_registration: str = Form(None),
    company_website: str = Form(None),
    company_email: str = Form(None),
    # Address
    address_line1: str = Form(None),
    address_line2: str = Form(None),
    city: str = Form(None),
    state_province: str = Form(None),
    postal_code: str = Form(None),
    country: str = Form(None),
    timezone: str = Form(None),
    address: str = Form(None),
    # Additional Info
    industry: str = Form(None),
    company_size: str = Form(None),
    preferred_communication: str = Form(None),
    working_hours: str = Form(None),
    # Notes
    notes: str = Form(None),
    internal_notes: str = Form(None),
    tags: str = Form(None),
    # Status
    is_active: str = Form("true"),
    db: Session = Depends(get_db_session)
):
    """Update client"""
    from app.models import JobSource
    
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Validate source enum if provided
    source_enum = None
    if source:
        try:
            source_enum = JobSource(source.lower())
        except ValueError:
            source_enum = None
    
    # Build address from components if legacy address not provided
    full_address = address
    if not full_address and (address_line1 or city or country):
        address_parts = []
        if address_line1:
            address_parts.append(address_line1)
        if address_line2:
            address_parts.append(address_line2)
        if city:
            address_parts.append(city)
        if state_province:
            address_parts.append(state_province)
        if postal_code:
            address_parts.append(postal_code)
        if country:
            address_parts.append(country)
        full_address = ", ".join(address_parts) if address_parts else None
    
    # Update all fields
    client.name = name
    client.source = source_enum
    client.source_url = source_url or None
    client.source_notes = source_notes or None
    client.contact_person = contact_person or None
    client.email = email or None
    client.phone = phone or None
    client.mobile = mobile or None
    client.alternative_email = alternative_email or None
    client.alternative_phone = alternative_phone or None
    client.telegram = telegram or None
    client.whatsapp = whatsapp or None
    client.skype = skype or None
    client.linkedin = linkedin or None
    client.other_contact = other_contact or None
    client.company_name = company_name or None
    client.company_registration = company_registration or None
    client.company_website = company_website or None
    client.company_email = company_email or None
    client.address_line1 = address_line1 or None
    client.address_line2 = address_line2 or None
    client.city = city or None
    client.state_province = state_province or None
    client.postal_code = postal_code or None
    client.country = country or None
    client.timezone = timezone or None
    client.address = full_address
    client.industry = industry or None
    client.company_size = company_size or None
    client.preferred_communication = preferred_communication or None
    client.working_hours = working_hours or None
    client.notes = notes or None
    client.internal_notes = internal_notes or None
    client.tags = tags or None
    client.is_active = is_active.lower() == "true" if is_active else True
    
    db.commit()
    
    return RedirectResponse(url=f"/clients/{client_id}", status_code=303)

@router.post("/clients/{client_id}/archive")
async def archive_client(client_id: int, db: Session = Depends(get_db_session)):
    """Archive (soft delete) client"""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    client.is_archived = True
    db.commit()
    
    return RedirectResponse(url="/clients", status_code=303)
```

### Step 4: Register Router

Update `main.py` to include the clients router:

```python
from app.routers import dashboard, workers, jobs, payments, settings, expenses, clients

# ... existing code ...

# Include all routers
app.include_router(dashboard.router)
app.include_router(jobs.router)
app.include_router(clients.router)  # ADD THIS - Separate CRUD for clients
app.include_router(workers.router)
app.include_router(payments.router)
app.include_router(expenses.router)
app.include_router(settings.router)
```

**Routes Created:**
- `GET /clients` - List all clients
- `GET /clients/new` - Form to create new client
- `POST /clients/new` - Create new client
- `GET /clients/{id}` - View client details
- `GET /clients/{id}/edit` - Form to edit client
- `POST /clients/{id}/edit` - Update client
- `POST /clients/{id}/archive` - Archive client

This creates a **complete separate CRUD interface** for clients, accessible via the "Clients" link in the top navbar.

### Step 5: Create Templates

#### `templates/clients/list.html`

```html
{% extends "base.html" %}

{% block title %}Clients{% endblock %}

{% block content %}
<div class="container mt-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h1>Clients</h1>
        <a href="/clients/new" class="btn btn-primary">
            <i class="bi bi-plus-circle"></i> New Client
        </a>
    </div>

    {% if clients %}
    <div class="table-responsive">
        <table class="table table-striped table-hover">
            <thead>
                <tr>
                    <th>Code</th>
                    <th>Name</th>
                    <th>Source</th>
                    <th>Contact Person</th>
                    <th>Email</th>
                    <th>Phone</th>
                    <th>Projects</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {% for client in clients %}
                <tr>
                    <td><strong>{{ client.client_code }}</strong></td>
                    <td>
                        <a href="/clients/{{ client.id }}">{{ client.name }}</a>
                        {% if client.company_name and client.company_name != client.name %}
                            <br><small class="text-muted">{{ client.company_name }}</small>
                        {% endif %}
                    </td>
                    <td>
                        {% if client.source %}
                            <span class="badge bg-info">{{ client.source.value|title }}</span>
                        {% else %}
                            <span class="text-muted">-</span>
                        {% endif %}
                    </td>
                    <td>{{ client.contact_person or '-' }}</td>
                    <td>{{ client.email or '-' }}</td>
                    <td>{{ client.phone or client.mobile or '-' }}</td>
                    <td>
                        <span class="badge bg-secondary">
                            {{ client.jobs|length if client.jobs else 0 }}
                        </span>
                    </td>
                    <td>
                        <a href="/clients/{{ client.id }}" class="btn btn-sm btn-outline-primary">
                            <i class="bi bi-eye"></i> View
                        </a>
                        <a href="/clients/{{ client.id }}/edit" class="btn btn-sm btn-outline-secondary">
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
        <i class="bi bi-info-circle"></i> No clients found. 
        <a href="/clients/new">Create your first client</a>
    </div>
    {% endif %}
</div>
{% endblock %}
```

#### `templates/clients/form.html`

```html
{% extends "base.html" %}

{% block title %}{{ 'Edit' if client else 'New' }} Client{% endblock %}

{% block content %}
<div class="container mt-4">
    <h1>{{ 'Edit' if client else 'New' }} Client</h1>
    
    <form method="POST" action="{{ '/clients/' + client.id|string + '/edit' if client else '/clients/new' }}">
        <!-- Basic Information Tab -->
        <div class="card mb-3">
            <div class="card-header">
                <h5 class="mb-0">Basic Information</h5>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label for="client_code" class="form-label">Client Code</label>
                            <input type="text" class="form-control" id="client_code" name="client_code" 
                                   value="{{ client.client_code if client else suggested_code }}" 
                                   {{ 'readonly' if client else '' }} required>
                            <small class="form-text text-muted">Auto-generated if left empty</small>
                        </div>
                        
                        <div class="mb-3">
                            <label for="name" class="form-label">Client Name <span class="text-danger">*</span></label>
                            <input type="text" class="form-control" id="name" name="name" 
                                   value="{{ client.name if client else '' }}" required>
                        </div>
                    </div>
                    
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label for="source" class="form-label">Source (Where Found)</label>
                            <select class="form-select" id="source" name="source">
                                <option value="">-- Select Source --</option>
                                <option value="upwork" {{ 'selected' if client and client.source and client.source.value == 'upwork' else '' }}>Upwork</option>
                                <option value="freelancer" {{ 'selected' if client and client.source and client.source.value == 'freelancer' else '' }}>Freelancer</option>
                                <option value="linkedin" {{ 'selected' if client and client.source and client.source.value == 'linkedin' else '' }}>LinkedIn</option>
                                <option value="fiverr" {{ 'selected' if client and client.source and client.source.value == 'fiverr' else '' }}>Fiverr</option>
                                <option value="direct" {{ 'selected' if client and client.source and client.source.value == 'direct' else '' }}>Direct</option>
                                <option value="other" {{ 'selected' if client and client.source and client.source.value == 'other' else '' }}>Other</option>
                            </select>
                        </div>
                        
                        <div class="mb-3">
                            <label for="source_url" class="form-label">Source URL</label>
                            <input type="url" class="form-control" id="source_url" name="source_url" 
                                   value="{{ client.source_url if client else '' }}"
                                   placeholder="e.g., Upwork profile, LinkedIn profile">
                        </div>
                    </div>
                </div>
                
                <div class="mb-3">
                    <label for="source_notes" class="form-label">Source Notes</label>
                    <textarea class="form-control" id="source_notes" name="source_notes" rows="2"
                              placeholder="Additional notes about how this client was found">{{ client.source_notes if client else '' }}</textarea>
                </div>
            </div>
        </div>

        <!-- Contact Information Tab -->
        <div class="card mb-3">
            <div class="card-header">
                <h5 class="mb-0">Contact Information</h5>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <h6>Primary Contact</h6>
                        <div class="mb-3">
                            <label for="contact_person" class="form-label">Contact Person</label>
                            <input type="text" class="form-control" id="contact_person" name="contact_person" 
                                   value="{{ client.contact_person if client else '' }}">
                        </div>
                        
                        <div class="mb-3">
                            <label for="email" class="form-label">Primary Email</label>
                            <input type="email" class="form-control" id="email" name="email" 
                                   value="{{ client.email if client else '' }}">
                        </div>
                        
                        <div class="mb-3">
                            <label for="phone" class="form-label">Primary Phone</label>
                            <input type="tel" class="form-control" id="phone" name="phone" 
                                   value="{{ client.phone if client else '' }}">
                        </div>
                        
                        <div class="mb-3">
                            <label for="mobile" class="form-label">Mobile Phone</label>
                            <input type="tel" class="form-control" id="mobile" name="mobile" 
                                   value="{{ client.mobile if client else '' }}">
                        </div>
                    </div>
                    
                    <div class="col-md-6">
                        <h6>Additional Contact Methods</h6>
                        <div class="mb-3">
                            <label for="alternative_email" class="form-label">Alternative Email</label>
                            <input type="email" class="form-control" id="alternative_email" name="alternative_email" 
                                   value="{{ client.alternative_email if client else '' }}">
                        </div>
                        
                        <div class="mb-3">
                            <label for="alternative_phone" class="form-label">Alternative Phone</label>
                            <input type="tel" class="form-control" id="alternative_phone" name="alternative_phone" 
                                   value="{{ client.alternative_phone if client else '' }}">
                        </div>
                        
                        <div class="mb-3">
                            <label for="telegram" class="form-label">Telegram</label>
                            <input type="text" class="form-control" id="telegram" name="telegram" 
                                   value="{{ client.telegram if client else '' }}" placeholder="@username">
                        </div>
                        
                        <div class="mb-3">
                            <label for="whatsapp" class="form-label">WhatsApp</label>
                            <input type="text" class="form-control" id="whatsapp" name="whatsapp" 
                                   value="{{ client.whatsapp if client else '' }}" placeholder="+1234567890">
                        </div>
                        
                        <div class="mb-3">
                            <label for="skype" class="form-label">Skype</label>
                            <input type="text" class="form-control" id="skype" name="skype" 
                                   value="{{ client.skype if client else '' }}">
                        </div>
                        
                        <div class="mb-3">
                            <label for="linkedin" class="form-label">LinkedIn Profile URL</label>
                            <input type="url" class="form-control" id="linkedin" name="linkedin" 
                                   value="{{ client.linkedin if client else '' }}">
                        </div>
                        
                        <div class="mb-3">
                            <label for="other_contact" class="form-label">Other Contact</label>
                            <input type="text" class="form-control" id="other_contact" name="other_contact" 
                                   value="{{ client.other_contact if client else '' }}"
                                   placeholder="Other contact method">
                        </div>
                    </div>
                </div>
                
                <div class="mb-3">
                    <label for="preferred_communication" class="form-label">Preferred Communication Method</label>
                    <select class="form-select" id="preferred_communication" name="preferred_communication">
                        <option value="">-- Select --</option>
                        <option value="email" {{ 'selected' if client and client.preferred_communication == 'email' else '' }}>Email</option>
                        <option value="phone" {{ 'selected' if client and client.preferred_communication == 'phone' else '' }}>Phone</option>
                        <option value="telegram" {{ 'selected' if client and client.preferred_communication == 'telegram' else '' }}>Telegram</option>
                        <option value="whatsapp" {{ 'selected' if client and client.preferred_communication == 'whatsapp' else '' }}>WhatsApp</option>
                        <option value="skype" {{ 'selected' if client and client.preferred_communication == 'skype' else '' }}>Skype</option>
                        <option value="linkedin" {{ 'selected' if client and client.preferred_communication == 'linkedin' else '' }}>LinkedIn</option>
                    </select>
                </div>
            </div>
        </div>

        <!-- Company Information Tab -->
        <div class="card mb-3">
            <div class="card-header">
                <h5 class="mb-0">Company Information</h5>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label for="company_name" class="form-label">Company Name</label>
                            <input type="text" class="form-control" id="company_name" name="company_name" 
                                   value="{{ client.company_name if client else '' }}">
                            <small class="form-text text-muted">If different from client name</small>
                        </div>
                        
                        <div class="mb-3">
                            <label for="company_registration" class="form-label">Registration/Tax ID</label>
                            <input type="text" class="form-control" id="company_registration" name="company_registration" 
                                   value="{{ client.company_registration if client else '' }}">
                        </div>
                        
                        <div class="mb-3">
                            <label for="company_website" class="form-label">Company Website</label>
                            <input type="url" class="form-control" id="company_website" name="company_website" 
                                   value="{{ client.company_website if client else '' }}">
                        </div>
                        
                        <div class="mb-3">
                            <label for="company_email" class="form-label">Company Email</label>
                            <input type="email" class="form-control" id="company_email" name="company_email" 
                                   value="{{ client.company_email if client else '' }}"
                                   placeholder="info@company.com">
                        </div>
                    </div>
                    
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label for="industry" class="form-label">Industry</label>
                            <input type="text" class="form-control" id="industry" name="industry" 
                                   value="{{ client.industry if client else '' }}"
                                   placeholder="e.g., Software Development, E-commerce">
                        </div>
                        
                        <div class="mb-3">
                            <label for="company_size" class="form-label">Company Size</label>
                            <select class="form-select" id="company_size" name="company_size">
                                <option value="">-- Select --</option>
                                <option value="1-10" {{ 'selected' if client and client.company_size == '1-10' else '' }}>1-10 employees</option>
                                <option value="11-50" {{ 'selected' if client and client.company_size == '11-50' else '' }}>11-50 employees</option>
                                <option value="51-200" {{ 'selected' if client and client.company_size == '51-200' else '' }}>51-200 employees</option>
                                <option value="201-500" {{ 'selected' if client and client.company_size == '201-500' else '' }}>201-500 employees</option>
                                <option value="501-1000" {{ 'selected' if client and client.company_size == '501-1000' else '' }}>501-1000 employees</option>
                                <option value="1000+" {{ 'selected' if client and client.company_size == '1000+' else '' }}>1000+ employees</option>
                            </select>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Address Information Tab -->
        <div class="card mb-3">
            <div class="card-header">
                <h5 class="mb-0">Address Information</h5>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label for="address_line1" class="form-label">Address Line 1</label>
                            <input type="text" class="form-control" id="address_line1" name="address_line1" 
                                   value="{{ client.address_line1 if client else '' }}">
                        </div>
                        
                        <div class="mb-3">
                            <label for="address_line2" class="form-label">Address Line 2</label>
                            <input type="text" class="form-control" id="address_line2" name="address_line2" 
                                   value="{{ client.address_line2 if client else '' }}"
                                   placeholder="Apartment, suite, etc.">
                        </div>
                        
                        <div class="mb-3">
                            <label for="city" class="form-label">City</label>
                            <input type="text" class="form-control" id="city" name="city" 
                                   value="{{ client.city if client else '' }}">
                        </div>
                        
                        <div class="mb-3">
                            <label for="state_province" class="form-label">State/Province</label>
                            <input type="text" class="form-control" id="state_province" name="state_province" 
                                   value="{{ client.state_province if client else '' }}">
                        </div>
                    </div>
                    
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label for="postal_code" class="form-label">Postal/ZIP Code</label>
                            <input type="text" class="form-control" id="postal_code" name="postal_code" 
                                   value="{{ client.postal_code if client else '' }}">
                        </div>
                        
                        <div class="mb-3">
                            <label for="country" class="form-label">Country</label>
                            <input type="text" class="form-control" id="country" name="country" 
                                   value="{{ client.country if client else '' }}">
                        </div>
                        
                        <div class="mb-3">
                            <label for="timezone" class="form-label">Timezone</label>
                            <input type="text" class="form-control" id="timezone" name="timezone" 
                                   value="{{ client.timezone if client else '' }}"
                                   placeholder="e.g., America/New_York, UTC, Europe/London">
                            <small class="form-text text-muted">IANA timezone identifier</small>
                        </div>
                        
                        <div class="mb-3">
                            <label for="working_hours" class="form-label">Working Hours</label>
                            <input type="text" class="form-control" id="working_hours" name="working_hours" 
                                   value="{{ client.working_hours if client else '' }}"
                                   placeholder="e.g., 9 AM - 5 PM EST">
                        </div>
                    </div>
                </div>
                
                <!-- Legacy address field (optional, for backward compatibility) -->
                <div class="mb-3">
                    <label for="address" class="form-label">Full Address (Legacy)</label>
                    <textarea class="form-control" id="address" name="address" rows="2"
                              placeholder="Full address as text (auto-filled from above fields)">{{ client.address if client else '' }}</textarea>
                    <small class="form-text text-muted">This field is auto-populated from the address components above</small>
                </div>
            </div>
        </div>

        <!-- Notes and Additional Information -->
        <div class="card mb-3">
            <div class="card-header">
                <h5 class="mb-0">Notes and Additional Information</h5>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label for="notes" class="form-label">Notes</label>
                            <textarea class="form-control" id="notes" name="notes" rows="4"
                                      placeholder="General notes about the client">{{ client.notes if client else '' }}</textarea>
                        </div>
                    </div>
                    
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label for="internal_notes" class="form-label">Internal Notes</label>
                            <textarea class="form-control" id="internal_notes" name="internal_notes" rows="4"
                                      placeholder="Internal-only notes (not shared with client)">{{ client.internal_notes if client else '' }}</textarea>
                        </div>
                    </div>
                </div>
                
                <div class="mb-3">
                    <label for="tags" class="form-label">Tags</label>
                    <input type="text" class="form-control" id="tags" name="tags" 
                           value="{{ client.tags if client else '' }}"
                           placeholder="Comma-separated tags (e.g., vip, recurring, startup)">
                    <small class="form-text text-muted">Use tags to categorize clients</small>
                </div>
                
                <div class="mb-3">
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" id="is_active" name="is_active" value="true"
                               {{ 'checked' if not client or client.is_active else '' }}>
                        <label class="form-check-label" for="is_active">
                            Active Client
                        </label>
                        <small class="form-text text-muted d-block">Uncheck to mark as inactive (archived clients are always inactive)</small>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="d-flex gap-2">
            <button type="submit" class="btn btn-primary">
                <i class="bi bi-save"></i> {{ 'Update' if client else 'Create' }} Client
            </button>
            <a href="{{ '/clients/' + client.id|string if client else '/clients' }}" class="btn btn-secondary">
                Cancel
            </a>
        </div>
    </form>
</div>

<script>
// Auto-populate legacy address field from components
document.addEventListener('DOMContentLoaded', function() {
    const addressFields = ['address_line1', 'address_line2', 'city', 'state_province', 'postal_code', 'country'];
    const addressField = document.getElementById('address');
    
    function updateAddress() {
        const parts = addressFields
            .map(id => document.getElementById(id)?.value)
            .filter(val => val && val.trim());
        addressField.value = parts.join(', ');
    }
    
    addressFields.forEach(id => {
        const field = document.getElementById(id);
        if (field) {
            field.addEventListener('input', updateAddress);
            field.addEventListener('change', updateAddress);
        }
    });
});
</script>
{% endblock %}
```

#### `templates/clients/detail.html`

```html
{% extends "base.html" %}

{% block title %}{{ client.name }}{% endblock %}

{% block content %}
<div class="container mt-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
            <h1>{{ client.name }}</h1>
            <p class="text-muted mb-0">
                Code: <strong>{{ client.client_code }}</strong>
                {% if client.source %}
                    | Source: <span class="badge bg-info">{{ client.source.value|title }}</span>
                {% endif %}
                {% if client.tags %}
                    | Tags: {% for tag in client.tags.split(',') %}<span class="badge bg-secondary">{{ tag.strip() }}</span> {% endfor %}
                {% endif %}
            </p>
        </div>
        <div>
            <a href="/clients/{{ client.id }}/edit" class="btn btn-outline-primary">
                <i class="bi bi-pencil"></i> Edit
            </a>
            <a href="/clients" class="btn btn-secondary">
                <i class="bi bi-arrow-left"></i> Back to Clients
            </a>
        </div>
    </div>

    <!-- Summary Cards -->
    <div class="row mb-4">
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <h5 class="card-title text-muted">Projects</h5>
                    <h2 class="mb-0">{{ project_count }}</h2>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <h5 class="card-title text-muted">Total Invoiced</h5>
                    <h2 class="mb-0 text-info">$0.00</h2>
                    <small class="text-muted">(Task 17)</small>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <h5 class="card-title text-muted">Total Received</h5>
                    <h2 class="mb-0 text-success">$0.00</h2>
                    <small class="text-muted">(Task 17)</small>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <h5 class="card-title text-muted">Outstanding</h5>
                    <h2 class="mb-0 text-warning">$0.00</h2>
                    <small class="text-muted">(Task 17)</small>
                </div>
            </div>
        </div>
    </div>

    <div class="row">
        <!-- Left Column -->
        <div class="col-md-6">
            <!-- Source Information -->
            {% if client.source or client.source_url or client.source_notes %}
            <div class="card mb-4">
                <div class="card-header">
                    <h5 class="mb-0"><i class="bi bi-info-circle"></i> Source Information</h5>
                </div>
                <div class="card-body">
                    <dl class="row mb-0">
                        {% if client.source %}
                        <dt class="col-sm-4">Source:</dt>
                        <dd class="col-sm-8">
                            <span class="badge bg-info">{{ client.source.value|title }}</span>
                        </dd>
                        {% endif %}
                        
                        {% if client.source_url %}
                        <dt class="col-sm-4">Source URL:</dt>
                        <dd class="col-sm-8">
                            <a href="{{ client.source_url }}" target="_blank">{{ client.source_url }}</a>
                        </dd>
                        {% endif %}
                        
                        {% if client.source_notes %}
                        <dt class="col-sm-4">Source Notes:</dt>
                        <dd class="col-sm-8">{{ client.source_notes|nl2br }}</dd>
                        {% endif %}
                    </dl>
                </div>
            </div>
            {% endif %}

            <!-- Primary Contact -->
            <div class="card mb-4">
                <div class="card-header">
                    <h5 class="mb-0"><i class="bi bi-person"></i> Primary Contact</h5>
                </div>
                <div class="card-body">
                    <dl class="row mb-0">
                        {% if client.contact_person %}
                        <dt class="col-sm-4">Contact Person:</dt>
                        <dd class="col-sm-8"><strong>{{ client.contact_person }}</strong></dd>
                        {% endif %}
                        
                        {% if client.email %}
                        <dt class="col-sm-4">Email:</dt>
                        <dd class="col-sm-8">
                            <a href="mailto:{{ client.email }}">{{ client.email }}</a>
                        </dd>
                        {% endif %}
                        
                        {% if client.phone %}
                        <dt class="col-sm-4">Phone:</dt>
                        <dd class="col-sm-8">
                            <a href="tel:{{ client.phone }}">{{ client.phone }}</a>
                        </dd>
                        {% endif %}
                        
                        {% if client.mobile %}
                        <dt class="col-sm-4">Mobile:</dt>
                        <dd class="col-sm-8">
                            <a href="tel:{{ client.mobile }}">{{ client.mobile }}</a>
                        </dd>
                        {% endif %}
                        
                        {% if client.preferred_communication %}
                        <dt class="col-sm-4">Preferred:</dt>
                        <dd class="col-sm-8">
                            <span class="badge bg-primary">{{ client.preferred_communication|title }}</span>
                        </dd>
                        {% endif %}
                    </dl>
                </div>
            </div>

            <!-- Additional Contact Methods -->
            {% if client.alternative_email or client.alternative_phone or client.telegram or client.whatsapp or client.skype or client.linkedin or client.other_contact %}
            <div class="card mb-4">
                <div class="card-header">
                    <h5 class="mb-0"><i class="bi bi-telephone"></i> Additional Contact Methods</h5>
                </div>
                <div class="card-body">
                    <dl class="row mb-0">
                        {% if client.alternative_email %}
                        <dt class="col-sm-4">Alt. Email:</dt>
                        <dd class="col-sm-8">
                            <a href="mailto:{{ client.alternative_email }}">{{ client.alternative_email }}</a>
                        </dd>
                        {% endif %}
                        
                        {% if client.alternative_phone %}
                        <dt class="col-sm-4">Alt. Phone:</dt>
                        <dd class="col-sm-8">
                            <a href="tel:{{ client.alternative_phone }}">{{ client.alternative_phone }}</a>
                        </dd>
                        {% endif %}
                        
                        {% if client.telegram %}
                        <dt class="col-sm-4">Telegram:</dt>
                        <dd class="col-sm-8">
                            <a href="https://t.me/{{ client.telegram.replace('@', '') }}" target="_blank">{{ client.telegram }}</a>
                        </dd>
                        {% endif %}
                        
                        {% if client.whatsapp %}
                        <dt class="col-sm-4">WhatsApp:</dt>
                        <dd class="col-sm-8">
                            <a href="https://wa.me/{{ client.whatsapp.replace('+', '').replace(' ', '') }}" target="_blank">{{ client.whatsapp }}</a>
                        </dd>
                        {% endif %}
                        
                        {% if client.skype %}
                        <dt class="col-sm-4">Skype:</dt>
                        <dd class="col-sm-8">
                            <a href="skype:{{ client.skype }}?call">{{ client.skype }}</a>
                        </dd>
                        {% endif %}
                        
                        {% if client.linkedin %}
                        <dt class="col-sm-4">LinkedIn:</dt>
                        <dd class="col-sm-8">
                            <a href="{{ client.linkedin }}" target="_blank">View Profile</a>
                        </dd>
                        {% endif %}
                        
                        {% if client.other_contact %}
                        <dt class="col-sm-4">Other:</dt>
                        <dd class="col-sm-8">{{ client.other_contact }}</dd>
                        {% endif %}
                    </dl>
                </div>
            </div>
            {% endif %}
        </div>

        <!-- Right Column -->
        <div class="col-md-6">
            <!-- Company Information -->
            {% if client.company_name or client.company_registration or client.company_website or client.company_email or client.industry or client.company_size %}
            <div class="card mb-4">
                <div class="card-header">
                    <h5 class="mb-0"><i class="bi bi-building"></i> Company Information</h5>
                </div>
                <div class="card-body">
                    <dl class="row mb-0">
                        {% if client.company_name %}
                        <dt class="col-sm-4">Company Name:</dt>
                        <dd class="col-sm-8"><strong>{{ client.company_name }}</strong></dd>
                        {% endif %}
                        
                        {% if client.company_registration %}
                        <dt class="col-sm-4">Registration:</dt>
                        <dd class="col-sm-8">{{ client.company_registration }}</dd>
                        {% endif %}
                        
                        {% if client.company_website %}
                        <dt class="col-sm-4">Website:</dt>
                        <dd class="col-sm-8">
                            <a href="{{ client.company_website }}" target="_blank">{{ client.company_website }}</a>
                        </dd>
                        {% endif %}
                        
                        {% if client.company_email %}
                        <dt class="col-sm-4">Company Email:</dt>
                        <dd class="col-sm-8">
                            <a href="mailto:{{ client.company_email }}">{{ client.company_email }}</a>
                        </dd>
                        {% endif %}
                        
                        {% if client.industry %}
                        <dt class="col-sm-4">Industry:</dt>
                        <dd class="col-sm-8">{{ client.industry }}</dd>
                        {% endif %}
                        
                        {% if client.company_size %}
                        <dt class="col-sm-4">Company Size:</dt>
                        <dd class="col-sm-8">{{ client.company_size }} employees</dd>
                        {% endif %}
                    </dl>
                </div>
            </div>
            {% endif %}

            <!-- Address Information -->
            {% if client.address_line1 or client.city or client.country or client.address %}
            <div class="card mb-4">
                <div class="card-header">
                    <h5 class="mb-0"><i class="bi bi-geo-alt"></i> Address</h5>
                </div>
                <div class="card-body">
                    {% if client.address_line1 or client.city or client.country %}
                    <address class="mb-0">
                        {% if client.address_line1 %}{{ client.address_line1 }}<br>{% endif %}
                        {% if client.address_line2 %}{{ client.address_line2 }}<br>{% endif %}
                        {% if client.city %}{{ client.city }}{% if client.state_province %}, {{ client.state_province }}{% endif %}{% if client.postal_code %} {{ client.postal_code }}{% endif %}<br>{% endif %}
                        {% if client.country %}{{ client.country }}{% endif %}
                    </address>
                    {% elif client.address %}
                    <p class="mb-0">{{ client.address|nl2br }}</p>
                    {% endif %}
                    
                    {% if client.timezone %}
                    <hr>
                    <strong>Timezone:</strong> {{ client.timezone }}
                    {% endif %}
                    
                    {% if client.working_hours %}
                    <br><strong>Working Hours:</strong> {{ client.working_hours }}
                    {% endif %}
                </div>
            </div>
            {% endif %}
        </div>
    </div>

    <!-- Notes Section -->
    {% if client.notes or client.internal_notes %}
    <div class="row">
        <div class="col-md-12">
            {% if client.notes %}
            <div class="card mb-4">
                <div class="card-header">
                    <h5 class="mb-0"><i class="bi bi-sticky"></i> Notes</h5>
                </div>
                <div class="card-body">
                    <p class="mb-0">{{ client.notes|nl2br }}</p>
                </div>
            </div>
            {% endif %}
            
            {% if client.internal_notes %}
            <div class="card mb-4">
                <div class="card-header">
                    <h5 class="mb-0"><i class="bi bi-lock"></i> Internal Notes</h5>
                </div>
                <div class="card-body">
                    <p class="mb-0">{{ client.internal_notes|nl2br }}</p>
                </div>
            </div>
            {% endif %}
        </div>
    </div>
    {% endif %}

    <!-- Linked Projects -->
    <div class="card">
        <div class="card-header">
            <h5 class="mb-0"><i class="bi bi-folder"></i> Linked Projects</h5>
        </div>
        <div class="card-body">
            {% if jobs %}
            <div class="table-responsive">
                <table class="table table-sm table-hover">
                    <thead>
                        <tr>
                            <th>Code</th>
                            <th>Title</th>
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
            <p class="text-muted mb-0">No projects linked to this client yet.</p>
            {% endif %}
        </div>
    </div>
</div>
{% endblock %}
```

### Step 6: Update Navigation (Top Navbar)

Update `templates/base.html` to add a "Clients" link in the top navbar. Add it after "Jobs" and before "Workers" for logical grouping:

```html
<nav class="navbar navbar-expand-lg navbar-dark bg-dark">
    <div class="container-fluid">
        <a class="navbar-brand" href="/">Upwork Tracker</a>
        <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
            <span class="navbar-toggler-icon"></span>
        </button>
        <div class="collapse navbar-collapse" id="navbarNav">
            <ul class="navbar-nav">
                <li class="nav-item">
                    <a class="nav-link" href="/">Dashboard</a>
                </li>
                <li class="nav-item">
                    <a class="nav-link" href="/jobs">Jobs</a>
                </li>
                <li class="nav-item">
                    <a class="nav-link" href="/clients">
                        <i class="bi bi-people"></i> Clients
                    </a>
                </li>
                <li class="nav-item">
                    <a class="nav-link" href="/workers">Workers</a>
                </li>
                <li class="nav-item">
                    <a class="nav-link" href="/payments">Payments</a>
                </li>
                <li class="nav-item">
                    <a class="nav-link" href="/expenses">Expenses</a>
                </li>
                <li class="nav-item">
                    <a class="nav-link" href="/settings">Settings</a>
                </li>
            </ul>
        </div>
    </div>
</nav>
```

**Navigation Structure:**
- Dashboard (home)
- Jobs (projects)
- **Clients** ← NEW: Separate CRUD page for client management
- Workers
- Payments
- Expenses
- Settings

This gives clients their own dedicated section in the navigation, making it clear they're managed separately from jobs.

### Step 7: Update Job Forms to Include Client Selection

**Important:** Clients have their own separate CRUD pages (`/clients`, `/clients/new`, `/clients/{id}`, `/clients/{id}/edit`). The job form should only include a dropdown to select an existing client, NOT duplicate client creation fields.

#### 7.1: Update Job Router to Pass Clients

Update `app/routers/jobs.py` - Modify the job form routes to include clients:

```python
@router.get("/jobs/new", response_class=HTMLResponse)
async def new_job_form(request: Request, db: Session = Depends(get_db_session)):
    """Show form to create new job"""
    from app.models import Client
    
    # Get all active clients for dropdown
    clients = db.query(Client).filter(Client.is_archived == False).order_by(Client.name).all()
    
    # ... existing code to get settings, etc. ...
    
    return templates.TemplateResponse("jobs/form.html", {
        "request": request,
        "job": None,
        "clients": clients,  # ADD THIS
        # ... other existing context ...
    })

@router.get("/jobs/{job_id}/edit", response_class=HTMLResponse)
async def edit_job_form(request: Request, job_id: int, db: Session = Depends(get_db_session)):
    """Show form to edit job"""
    from app.models import Client
    
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Get all active clients for dropdown
    clients = db.query(Client).filter(Client.is_archived == False).order_by(Client.name).all()
    
    # ... existing code ...
    
    return templates.TemplateResponse("jobs/form.html", {
        "request": request,
        "job": job,
        "clients": clients,  # ADD THIS
        # ... other existing context ...
    })
```

#### 7.2: Update Job Form Template

Update `templates/jobs/form.html` to include client selection dropdown:

```html
<!-- Client Selection (add this near the top of the form, after job title) -->
<div class="mb-3">
    <label for="client_id" class="form-label">
        Client
        <a href="/clients/new" target="_blank" class="btn btn-sm btn-outline-secondary ms-2" title="Create New Client">
            <i class="bi bi-plus-circle"></i> New Client
        </a>
    </label>
    <select class="form-select" id="client_id" name="client_id">
        <option value="">-- Select Client --</option>
        {% for client in clients %}
        <option value="{{ client.id }}" {{ 'selected' if job and job.client_id == client.id else '' }}>
            {{ client.client_code }} - {{ client.name }}
            {% if client.company_name and client.company_name != client.name %}
                ({{ client.company_name }})
            {% endif %}
        </option>
        {% endfor %}
    </select>
    <small class="form-text text-muted">
        Select an existing client or 
        <a href="/clients/new" target="_blank">create a new client</a> first.
    </small>
</div>
```

**Note:** The "New Client" button opens in a new tab so users can create a client without losing their job form data. After creating a client, they can refresh the job form page to see the new client in the dropdown.

#### 7.3: Update Job Create/Update Routes

Update the job creation and update routes in `app/routers/jobs.py` to handle `client_id`:

```python
@router.post("/jobs/new")
async def create_job(
    request: Request,
    # ... existing fields ...
    client_id: str = Form(None),  # ADD THIS
    # ... rest of existing fields ...
    db: Session = Depends(get_db_session)
):
    """Create new job"""
    # ... existing validation ...
    
    # Handle client_id
    client_id_int = None
    if client_id and client_id.strip():
        try:
            client_id_int = int(client_id)
            # Verify client exists
            client = db.query(Client).filter(Client.id == client_id_int).first()
            if not client:
                raise HTTPException(status_code=400, detail="Selected client not found")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid client ID")
    
    job = Job(
        # ... existing fields ...
        client_id=client_id_int,  # ADD THIS
        # ... rest of fields ...
    )
    
    # ... rest of creation logic ...

@router.post("/jobs/{job_id}/edit")
async def update_job(
    request: Request,
    job_id: int,
    # ... existing fields ...
    client_id: str = Form(None),  # ADD THIS
    # ... rest of existing fields ...
    db: Session = Depends(get_db_session)
):
    """Update job"""
    # ... existing validation ...
    
    # Handle client_id
    client_id_int = None
    if client_id and client_id.strip():
        try:
            client_id_int = int(client_id)
            # Verify client exists
            client = db.query(Client).filter(Client.id == client_id_int).first()
            if not client:
                raise HTTPException(status_code=400, detail="Selected client not found")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid client ID")
    
    job.client_id = client_id_int  # ADD THIS
    
    # ... rest of update logic ...
```

---

## Testing Checklist

### Database
- [ ] Migration runs successfully
- [ ] Client table created with correct schema
- [ ] Foreign key relationship works between jobs and clients
- [ ] Client codes are unique

### CRUD Operations
- [ ] Create new client with auto-generated code
- [ ] Create new client with custom code
- [ ] View client list (shows only active clients)
- [ ] View client detail page
- [ ] Edit client information
- [ ] Archive client (soft delete)
- [ ] Archived clients don't appear in list

### Client Code Generation
- [ ] First client gets C01
- [ ] Subsequent clients get C02, C03, etc.
- [ ] Handles gaps in numbering correctly

### Job Linking
- [ ] Can link job to client (via client_id dropdown in job form)
- [ ] Client dropdown in job form shows all active clients
- [ ] "New Client" button/link works in job form (opens in new tab)
- [ ] Client detail page shows linked projects
- [ ] Job detail page shows client information (if linked)
- [ ] Job form validates that selected client exists

### UI/UX
- [ ] Navigation includes "Clients" link in top navbar (between Jobs and Workers)
- [ ] Clients link is visible and accessible from all pages
- [ ] Forms validate required fields
- [ ] Error handling for duplicate codes
- [ ] Responsive design works on mobile
- [ ] Empty states show helpful messages
- [ ] Client list page shows "New Client" button prominently

### Edge Cases
- [ ] Handle client with no projects
- [ ] Handle client with no contact info
- [ ] Handle archived client (shouldn't appear in dropdowns)
- [ ] Handle client deletion attempt when linked to jobs (should prevent or warn)

---

## Dependencies

**This task has no dependencies** - it's a foundational task.

**Future tasks that depend on this:**
- Task 3: Project-Middleman-Client Relationships (will enhance client linking)
- Task 5: Invoice Model & Database (invoices link to clients)
- Task 17: Client Dashboard & Reports (will add financial calculations)

---

## Notes

1. **Backward Compatibility:** Keep existing `client_name`, `company_name`, etc. fields in Job model for now. We can migrate data later or keep both for flexibility.

2. **Client Code Format:** Using C01, C02 format to match existing pattern (W01 for workers, J01 for jobs, P0001 for payments).

3. **Soft Delete:** Using `is_archived` flag instead of hard delete to preserve data integrity.

4. **Financial Calculations:** Total invoiced, received, and outstanding balance will be implemented in Task 17 (Client Dashboard & Reports). For now, just show placeholders.

5. **Extensive Data Fields:** The Client model includes comprehensive data fields:
   - **Source Tracking:** Where the client was found (Upwork, LinkedIn, Direct, etc.) with URL and notes
   - **Multiple Contact Methods:** Primary and alternative emails/phones, plus Telegram, WhatsApp, Skype, LinkedIn
   - **Company Information:** Company name, registration, website, industry, size
   - **Detailed Address:** Structured address fields (line1, line2, city, state, postal, country) plus timezone and working hours
   - **Organization:** Tags for categorization, preferred communication method
   - **Notes:** Both public notes and internal-only notes
   - All fields are optional to allow flexibility in data entry

6. **Source Enum:** Reuses the existing `JobSource` enum (upwork, freelancer, linkedin, fiverr, direct, other) for consistency.

7. **Address Handling:** The system auto-populates the legacy `address` field from structured address components, but also allows manual entry for backward compatibility.

8. **Form Organization:** The client form is organized into logical sections (Basic Info, Contact, Company, Address, Notes) for better UX despite the large number of fields.

---

## Next Steps

After completing this task:
1. Test thoroughly using the checklist above
2. **Update job creation/edit forms** to include client dropdown (Step 7 above)
3. Test the workflow: Create client → Create job → Select client from dropdown
4. Proceed to Task 2: Middleman Management System (similar structure)
5. Then Task 3: Project-Middleman-Client Relationships (will enhance the linking)
