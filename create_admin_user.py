"""
Script to create the default admin user.
This should be run after creating a fresh database.
Uses raw SQL to avoid relationship issues with Middleman model.
"""
from app.database import engine
from app.auth import hash_password
from sqlalchemy import text

# Use raw SQL to avoid relationship initialization issues
with engine.connect() as conn:
    # Check if admin user already exists
    result = conn.execute(text("SELECT id FROM users WHERE username = 'admin'"))
    existing = result.fetchone()
    
    if existing:
        print("Admin user already exists!")
    else:
        # Create admin user
        password_hash = hash_password("admin123")
        conn.execute(text("""
            INSERT INTO users (username, password_hash, is_active, created_at, updated_at)
            VALUES ('admin', :password_hash, 1, datetime('now'), datetime('now'))
        """), {"password_hash": password_hash})
        
        # Get the admin user ID
        result = conn.execute(text("SELECT id FROM users WHERE username = 'admin'"))
        admin_id = result.fetchone()[0]
        
        # Assign ADMIN role
        conn.execute(text("""
            INSERT INTO user_role_assignments (user_id, role, created_at)
            VALUES (:user_id, 'ADMIN', datetime('now'))
        """), {"user_id": admin_id})
        
        conn.commit()
        
        print("[OK] Admin user created successfully!")
        print("Username: admin")
        print("Password: admin123")
        print("\nPlease change the password after first login!")
