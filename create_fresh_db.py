"""
Script to create a fresh database with all tables from models.
Run this before running migrations on a fresh database.
"""
from app.database import engine, Base
from app.models import *  # Import all models
from app.config import settings

print("Creating all database tables from models...")
Base.metadata.create_all(bind=engine)
print("[OK] All tables created successfully!")
print(f"Database: {settings.DATABASE_URL}")
print("\nNext step: Run 'alembic stamp head' to mark all migrations as applied.")
