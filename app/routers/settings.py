from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc
import json
from app.database import get_db
from app.models import SettingsVersion, User
from app.dependencies import get_db_session
from app.auth import get_current_user, require_role, UserRole as AuthUserRole
from app.config import BASE_DIR

router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "templates")

@router.get("/settings", response_class=HTMLResponse)
async def list_settings(
    request: Request, 
    db: Session = Depends(get_db_session),
    _: User = Depends(require_role([AuthUserRole.ADMIN]))
):
    versions = db.query(SettingsVersion).order_by(desc(SettingsVersion.created_at)).all()
    active_version = next((v for v in versions if v.is_active), None)
    
    return templates.TemplateResponse("settings/list.html", {
        "request": request,
        "versions": versions,
        "active_version": active_version
    })

@router.get("/settings/new", response_class=HTMLResponse)
async def new_settings_form(
    request: Request,
    _: User = Depends(require_role([AuthUserRole.ADMIN]))
):
    # Default rules JSON
    default_rules = {
        "currency_default": "USD",
        "connect_cost_per_unit": 0.15,  # $0.15 per connect
        "platform_fee": {"enabled": False, "mode": "percent", "value": 0.10, "apply_on": "net"},
        "rounding": {"mode": "2dp"},
        "require_percent_allocations_sum_to_1": True
    }
    
    return templates.TemplateResponse("settings/form.html", {
        "request": request,
        "version": None,
        "default_rules_json": json.dumps(default_rules, indent=2)
    })

@router.post("/settings/new")
async def create_settings(
    request: Request,
    name: str = Form(...),
    rules_json: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_role([AuthUserRole.ADMIN]))
):
    # Validate JSON
    try:
        json.loads(rules_json)
    except json.JSONDecodeError:
        return templates.TemplateResponse("settings/form.html", {
            "request": request,
            "version": None,
            "default_rules_json": rules_json,
            "error": "Invalid JSON format"
        }, status_code=400)
    
    version = SettingsVersion(
        name=name,
        rules_json=rules_json,
        notes=notes if notes else None,
        is_active=False
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    
    return RedirectResponse(url=f"/settings/{version.id}", status_code=303)

@router.get("/settings/{version_id}", response_class=HTMLResponse)
async def settings_detail(
    request: Request, 
    version_id: int, 
    db: Session = Depends(get_db_session),
    _: User = Depends(require_role([AuthUserRole.ADMIN]))
):
    version = db.query(SettingsVersion).filter(SettingsVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Settings version not found")
    
    rules = json.loads(version.rules_json)
    
    return templates.TemplateResponse("settings/detail.html", {
        "request": request,
        "version": version,
        "rules": rules,
        "rules_json": json.dumps(rules, indent=2)
    })

@router.post("/settings/{version_id}/activate")
async def activate_settings(
    version_id: int, 
    db: Session = Depends(get_db_session),
    _: User = Depends(require_role([AuthUserRole.ADMIN]))
):
    version = db.query(SettingsVersion).filter(SettingsVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Settings version not found")
    
    # Deactivate all others
    db.query(SettingsVersion).update({"is_active": False})
    
    # Activate this one
    version.is_active = True
    db.commit()
    
    return RedirectResponse(url="/settings", status_code=303)

@router.get("/settings/{version_id}/clone", response_class=HTMLResponse)
async def clone_settings_form(
    request: Request, 
    version_id: int, 
    db: Session = Depends(get_db_session),
    _: User = Depends(require_role([AuthUserRole.ADMIN]))
):
    version = db.query(SettingsVersion).filter(SettingsVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Settings version not found")
    
    return templates.TemplateResponse("settings/clone_form.html", {
        "request": request,
        "source_version": version,
        "rules_json": version.rules_json
    })

@router.post("/settings/{version_id}/clone")
async def clone_settings(
    request: Request,
    version_id: int,
    name: str = Form(...),
    rules_json: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_role([AuthUserRole.ADMIN]))
):
    source_version = db.query(SettingsVersion).filter(SettingsVersion.id == version_id).first()
    if not source_version:
        raise HTTPException(status_code=404, detail="Source settings version not found")
    
    # Validate JSON
    try:
        json.loads(rules_json)
    except json.JSONDecodeError:
        return templates.TemplateResponse("settings/clone_form.html", {
            "request": request,
            "source_version": source_version,
            "rules_json": rules_json,
            "error": "Invalid JSON format"
        }, status_code=400)
    
    new_version = SettingsVersion(
        name=name,
        rules_json=rules_json,
        notes=notes if notes else None,
        is_active=False
    )
    db.add(new_version)
    db.commit()
    db.refresh(new_version)
    
    return RedirectResponse(url=f"/settings/{new_version.id}", status_code=303)
