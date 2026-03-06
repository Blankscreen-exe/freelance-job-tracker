from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Numeric, Date, DateTime, Text, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, date
from decimal import Decimal
import enum
from app.database import Base

class JobType(str, enum.Enum):
    FIXED = "fixed"
    HOURLY = "hourly"

class JobStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"

class ReceiptSource(str, enum.Enum):
    MILESTONE = "milestone"
    WEEKLY = "weekly"
    BONUS = "bonus"
    MANUAL = "manual"

class ShareType(str, enum.Enum):
    PERCENT = "percent"
    FIXED_AMOUNT = "fixed_amount"

class ConnectMode(str, enum.Enum):
    FIXED = "fixed"
    PERCENT = "percent"

class PlatformFeeApplyOn(str, enum.Enum):
    GROSS = "gross"
    NET = "net"

class JobSource(str, enum.Enum):
    UPWORK = "upwork"
    FREELANCER = "freelancer"
    LINKEDIN = "linkedin"
    FIVERR = "fiverr"
    DIRECT = "direct"
    OTHER = "other"

class ExpenseCategory(str, enum.Enum):
    CONNECTS = "connects"
    TOOLS = "tools"
    SOFTWARE = "software"
    SUBSCRIPTION = "subscription"
    MARKETING = "marketing"
    OFFICE = "office"
    OTHER = "other"

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    WORKER = "worker"
    MIDDLEMAN = "middleman"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, nullable=True)  # Email address
    password_hash = Column(String, nullable=False)  # bcrypt hashed password
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    roles = relationship("UserRoleAssignment", back_populates="user", cascade="all, delete-orphan")
    worker = relationship("Worker", back_populates="user", uselist=False)
    middleman = relationship("Middleman", back_populates="user", uselist=False)
    created_jobs = relationship("Job", foreign_keys="Job.created_by_user_id", back_populates="created_by_user")
    created_clients = relationship("Client", foreign_keys="Client.created_by_user_id", back_populates="created_by_user")

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

# Temporary stub for Middleman - will be replaced in Task 2
class Middleman(Base):
    __tablename__ = "middlemen"
    
    id = Column(Integer, primary_key=True, index=True)
    middleman_code = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="middleman")
    # jobs relationship will be added in Task 2

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

    # Ownership tracking
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_by_user = relationship("User", foreign_keys=[created_by_user_id], back_populates="created_clients")

    # Relationships
    jobs = relationship("Job", back_populates="client")

class Worker(Base):
    __tablename__ = "workers"

    id = Column(Integer, primary_key=True, index=True)
    worker_code = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    contact = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    is_archived = Column(Boolean, default=False)
    is_owner = Column(Boolean, default=False)  # Mark this worker as the owner/me
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    allocations = relationship("JobAllocation", back_populates="worker")
    payments = relationship("Payment", back_populates="worker")
    user = relationship("User", back_populates="worker")

class SettingsVersion(Base):
    __tablename__ = "settings_versions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    is_active = Column(Boolean, default=False)
    rules_json = Column(Text, nullable=False)  # JSON string
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    jobs = relationship("Job", back_populates="settings_version")

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_code = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=False)
    client_name = Column(String, nullable=True)
    job_post_url = Column(String, nullable=False)
    
    # Job source and description
    source = Column(SQLEnum(JobSource), nullable=True)
    description = Column(Text, nullable=True)  # HTML content from Quill.js
    cover_letter = Column(Text, nullable=True)  # HTML content from Quill.js
    
    # Company/Client details
    company_name = Column(String, nullable=True)
    company_website = Column(String, nullable=True)
    company_email = Column(String, nullable=True)
    company_phone = Column(String, nullable=True)
    company_address = Column(Text, nullable=True)
    client_notes = Column(Text, nullable=True)
    
    # Client relationship (NEW)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)  # Link to Client
    
    # Ownership tracking
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_by_user = relationship("User", foreign_keys=[created_by_user_id], back_populates="created_jobs")
    
    # Upwork-specific fields (kept for backward compatibility)
    upwork_job_id = Column(String, nullable=True)
    upwork_contract_id = Column(String, nullable=True)
    upwork_offer_id = Column(String, nullable=True)
    job_type = Column(SQLEnum(JobType), nullable=False)
    status = Column(SQLEnum(JobStatus), default=JobStatus.DRAFT)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    
    # Versioning
    settings_version_id = Column(Integer, ForeignKey("settings_versions.id"), nullable=False)
    
    # Overrides
    connect_override_mode = Column(String, nullable=True)  # fixed_amount/percent_of_received (deprecated)
    connect_override_value = Column(Numeric(10, 2), nullable=True)  # deprecated
    connects_used = Column(Integer, nullable=True)  # Number of connects used for this job
    platform_fee_override_enabled = Column(Boolean, nullable=True)
    platform_fee_override_mode = Column(String, nullable=True)
    platform_fee_override_value = Column(Numeric(10, 2), nullable=True)
    platform_fee_override_apply_on = Column(String, nullable=True)  # gross/net
    
    # Flags
    is_finalized = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    settings_version = relationship("SettingsVersion", back_populates="jobs")
    client = relationship("Client", back_populates="jobs")
    receipts = relationship("Receipt", back_populates="job", cascade="all, delete-orphan")
    allocations = relationship("JobAllocation", back_populates="job", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="job")
    snapshot = relationship("JobCalculationSnapshot", back_populates="job", uselist=False, cascade="all, delete-orphan")

class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    received_date = Column(Date, nullable=False)
    amount_received = Column(Numeric(10, 2), nullable=False)
    source = Column(SQLEnum(ReceiptSource), nullable=False)
    upwork_transaction_id = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    selected_allocation_ids = Column(Text, nullable=True)  # JSON string of allocation IDs
    use_custom_allocations = Column(Boolean, default=False)  # Flag for custom vs predefined allocations
    custom_allocations = Column(Text, nullable=True)  # JSON string of custom allocations

    job = relationship("Job", back_populates="receipts")

class JobAllocation(Base):
    __tablename__ = "job_allocations"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=True)  # null = admin/you
    label = Column(String, nullable=False)  # "YOU" or role like Dev/Design
    role = Column(String, nullable=True)
    share_type = Column(SQLEnum(ShareType), nullable=False)
    share_value = Column(Numeric(10, 2), nullable=False)
    notes = Column(Text, nullable=True)

    job = relationship("Job", back_populates="allocations")
    worker = relationship("Worker", back_populates="allocations")

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    payment_code = Column(String, unique=True, index=True, nullable=False)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True)
    amount_paid = Column(Numeric(10, 2), nullable=False)
    paid_date = Column(Date, nullable=False)
    method = Column(String, nullable=True)
    reference = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    is_auto_generated = Column(Boolean, default=False)
    is_paid = Column(Boolean, default=False)

    worker = relationship("Worker", back_populates="payments")
    job = relationship("Job", back_populates="payments")

class JobCalculationSnapshot(Base):
    __tablename__ = "job_calculation_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), unique=True, nullable=False)
    settings_version_id = Column(Integer, ForeignKey("settings_versions.id"), nullable=False)
    snapshot_json = Column(Text, nullable=False)  # JSON string
    finalized_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="snapshot")

class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    expense_code = Column(String, unique=True, index=True, nullable=False)
    expense_date = Column(Date, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    category = Column(SQLEnum(ExpenseCategory), nullable=False)
    description = Column(String, nullable=False)
    vendor = Column(String, nullable=True)
    reference = Column(String, nullable=True)  # receipt/invoice number
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
