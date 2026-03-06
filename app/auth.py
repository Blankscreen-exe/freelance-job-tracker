from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.orm import Session
from app.models import User, UserRole
from app.dependencies import get_db_session
import bcrypt

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

def get_current_user(request: Request, db: Session = Depends(get_db_session)) -> User:
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
    """Dependency function to require specific role(s)"""
    def role_checker(
        request: Request,
        user: User = Depends(get_current_user)
    ):
        # Get active role from session
        role_str = request.session.get("active_role")
        if not role_str:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No active role")
        active_role = UserRole(role_str)
        
        # Admin has access to everything
        if active_role == UserRole.ADMIN:
            return user
        
        # Check if user has the required role
        if active_role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        
        return user
    return role_checker
