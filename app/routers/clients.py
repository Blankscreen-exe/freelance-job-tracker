from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models import Client, Job, JobSource, User
from app.dependencies import get_db_session
from app.utils import generate_client_code
from app.config import BASE_DIR
from app.template_filters import get_templates
from app.auth import get_current_user, get_active_role, UserRole as AuthUserRole

router = APIRouter()
templates = get_templates(BASE_DIR / "templates")

@router.get("/clients", response_class=HTMLResponse)
async def list_clients(
    request: Request, 
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user)
):
    """List all active clients"""
    active_role = get_active_role(request)
    
    if active_role == AuthUserRole.ADMIN:
        # Admin sees all clients
        clients = db.query(Client).filter(Client.is_archived == False).order_by(Client.name).all()
    elif active_role == AuthUserRole.WORKER:
        # Worker sees all clients (read-only)
        clients = db.query(Client).filter(Client.is_archived == False).order_by(Client.name).all()
    elif active_role == AuthUserRole.MIDDLEMAN:
        # Middleman sees only clients they created
        clients = db.query(Client).filter(
            Client.created_by_user_id == user.id,
            Client.is_archived == False
        ).order_by(Client.name).all()
    else:
        clients = []
    
    return templates.TemplateResponse("clients/list.html", {
        "request": request,
        "clients": clients
    })

@router.get("/clients/new", response_class=HTMLResponse)
async def new_client_form(
    request: Request, 
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user)
):
    """Show form to create new client"""
    # Only Admin and Middleman can create clients
    active_role = get_active_role(request)
    if active_role == AuthUserRole.WORKER:
        raise HTTPException(status_code=403, detail="Workers cannot create clients")
    
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
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user)
):
    """Create new client"""
    # Only Admin and Middleman can create clients
    active_role = get_active_role(request)
    if active_role == AuthUserRole.WORKER:
        raise HTTPException(status_code=403, detail="Workers cannot create clients")
    
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
        is_active=is_active.lower() == "true" if is_active else True,
        created_by_user_id=user.id  # Track ownership
    )
    
    db.add(client)
    db.commit()
    db.refresh(client)
    
    return RedirectResponse(url=f"/clients/{client.id}", status_code=303)

@router.get("/clients/{client_id}", response_class=HTMLResponse)
async def client_detail(request: Request, client_id: int, db: Session = Depends(get_db_session)):
    """Show client detail page"""
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
async def edit_client_form(
    request: Request, 
    client_id: int, 
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user)
):
    """Show form to edit client"""
    from app.models import JobSource
    
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Check ownership: Admin or creator can edit
    active_role = get_active_role(request)
    if active_role != AuthUserRole.ADMIN:
        if client.created_by_user_id != user.id:
            raise HTTPException(status_code=403, detail="You can only edit clients you created")
    
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
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user)
):
    """Update client"""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Check ownership: Admin or creator can edit
    active_role = get_active_role(request)
    if active_role != AuthUserRole.ADMIN:
        if client.created_by_user_id != user.id:
            raise HTTPException(status_code=403, detail="You can only edit clients you created")
    
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
