import json
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import AbstractUser


# ──────────────────────────────────────────────
# User & Roles
# ──────────────────────────────────────────────

class User(AbstractUser):
    """Custom user with role support. Every non-admin user gets both Worker and Middleman roles."""

    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        WORKER = 'worker', 'Worker'
        MIDDLEMAN = 'middleman', 'Middleman'

    # Active role for role-switching UI (worker or middleman view)
    active_role = models.CharField(max_length=20, choices=Role.choices, default=Role.WORKER)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    def is_admin_user(self):
        return self.is_superuser or self.roles.filter(role=self.Role.ADMIN).exists()

    def has_role(self, role):
        return self.roles.filter(role=role).exists()

    def get_roles(self):
        return list(self.roles.values_list('role', flat=True))


class UserRole(models.Model):
    """Many-to-many role assignments for users."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='roles')
    role = models.CharField(max_length=20, choices=User.Role.choices)

    class Meta:
        unique_together = ('user', 'role')

    def __str__(self):
        return f"{self.user.username} - {self.role}"


# ──────────────────────────────────────────────
# Client
# ──────────────────────────────────────────────

class Client(models.Model):
    client_code = models.CharField(max_length=10, unique=True)  # C01, C02
    name = models.CharField(max_length=200)

    # Source info
    source = models.CharField(max_length=100, blank=True, default='')
    source_url = models.URLField(max_length=500, blank=True, default='')
    source_notes = models.TextField(blank=True, default='')

    # Notes
    notes = models.TextField(blank=True, default='')
    internal_notes = models.TextField(blank=True, default='')
    tags = models.CharField(max_length=500, blank=True, default='')

    # Status
    is_archived = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # Ownership
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_clients')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.client_code} - {self.name}"

    def primary_email(self):
        c = self.contacts.filter(contact_type='email', is_primary=True).first()
        return c.value if c else ''

    def primary_company(self):
        c = self.companies.filter(is_current=True).first()
        return c.company_name if c else ''


class ClientContact(models.Model):
    class ContactType(models.TextChoices):
        EMAIL = 'email', 'Email'
        PHONE = 'phone', 'Phone'
        MOBILE = 'mobile', 'Mobile'
        TELEGRAM = 'telegram', 'Telegram'
        WHATSAPP = 'whatsapp', 'WhatsApp'
        SKYPE = 'skype', 'Skype'
        LINKEDIN = 'linkedin', 'LinkedIn'
        OTHER = 'other', 'Other'

    class Label(models.TextChoices):
        WORK = 'work', 'Work'
        PERSONAL = 'personal', 'Personal'
        OTHER = 'other', 'Other'

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='contacts')
    contact_type = models.CharField(max_length=20, choices=ContactType.choices)
    value = models.CharField(max_length=300)
    label = models.CharField(max_length=20, choices=Label.choices, default=Label.WORK)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ['-is_primary', 'contact_type']

    def __str__(self):
        return f"{self.get_contact_type_display()}: {self.value}"


class ClientCompany(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='companies')
    company_name = models.CharField(max_length=200)
    role = models.CharField(max_length=200, blank=True, default='')
    website = models.URLField(max_length=500, blank=True, default='')
    registration = models.CharField(max_length=100, blank=True, default='')
    industry = models.CharField(max_length=100, blank=True, default='')
    size = models.CharField(max_length=50, blank=True, default='')
    is_current = models.BooleanField(default=True)

    class Meta:
        ordering = ['-is_current', 'company_name']
        verbose_name_plural = 'client companies'

    def __str__(self):
        return f"{self.company_name} ({self.role})" if self.role else self.company_name


class ClientAddress(models.Model):
    class Label(models.TextChoices):
        OFFICE = 'office', 'Office'
        HOME = 'home', 'Home'
        OTHER = 'other', 'Other'

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField(max_length=20, choices=Label.choices, default=Label.OFFICE)
    address_line1 = models.CharField(max_length=300, blank=True, default='')
    address_line2 = models.CharField(max_length=300, blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    state = models.CharField(max_length=100, blank=True, default='')
    postal_code = models.CharField(max_length=20, blank=True, default='')
    country = models.CharField(max_length=100, blank=True, default='')
    timezone = models.CharField(max_length=50, blank=True, default='')
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ['-is_primary', 'label']
        verbose_name_plural = 'client addresses'

    def __str__(self):
        parts = [p for p in [self.city, self.country] if p]
        return f"{self.get_label_display()}: {', '.join(parts)}" if parts else self.get_label_display()


# ──────────────────────────────────────────────
# Middleman (Work Bringer)
# ──────────────────────────────────────────────

class Middleman(models.Model):
    middleman_code = models.CharField(max_length=10, unique=True)  # M01, M02
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=50, blank=True, default='')
    contact = models.CharField(max_length=200, blank=True, default='')  # alt contact (telegram, etc.)
    notes = models.TextField(blank=True, default='')
    is_archived = models.BooleanField(default=False)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='middleman_profile')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'middlemen'

    def __str__(self):
        return f"{self.middleman_code} - {self.name}"


# ──────────────────────────────────────────────
# Worker
# ──────────────────────────────────────────────

class Worker(models.Model):
    worker_code = models.CharField(max_length=10, unique=True)  # W01, W02
    name = models.CharField(max_length=200)
    contact = models.CharField(max_length=200, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    is_archived = models.BooleanField(default=False)
    is_owner = models.BooleanField(default=False)  # marks the agency owner's own worker entity
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='worker_profile')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.worker_code} - {self.name}"


# ──────────────────────────────────────────────
# Settings Version (versioned calculation rules)
# ──────────────────────────────────────────────

class SettingsVersion(models.Model):
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=False)
    rules_json = models.TextField(default='{}')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({'active' if self.is_active else 'inactive'})"

    @property
    def rules(self):
        return json.loads(self.rules_json)

    @rules.setter
    def rules(self, value):
        self.rules_json = json.dumps(value)

    def get_connect_default(self):
        r = self.rules
        return r.get('connect_default', {'mode': 'percent', 'value': 0.05})

    def get_platform_fee(self):
        r = self.rules
        return r.get('platform_fee', {'enabled': False, 'mode': 'percent', 'value': 0, 'apply_on': 'net'})


# ──────────────────────────────────────────────
# Job (Project)
# ──────────────────────────────────────────────

class Job(models.Model):
    class JobType(models.TextChoices):
        FIXED = 'fixed', 'Fixed'
        HOURLY = 'hourly', 'Hourly'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        ACTIVE = 'active', 'Active'
        COMPLETED = 'completed', 'Completed'
        ARCHIVED = 'archived', 'Archived'

    class CommissionType(models.TextChoices):
        PERCENT = 'percent', 'Percentage'
        FLAT = 'flat', 'Flat Amount'

    class JobSource(models.TextChoices):
        UPWORK = 'upwork', 'Upwork'
        FREELANCER = 'freelancer', 'Freelancer'
        LINKEDIN = 'linkedin', 'LinkedIn'
        FIVERR = 'fiverr', 'Fiverr'
        DIRECT = 'direct', 'Direct'
        OTHER = 'other', 'Other'

    job_code = models.CharField(max_length=10, unique=True)  # J01, J02
    title = models.CharField(max_length=300)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, related_name='jobs')
    middleman = models.ForeignKey(Middleman, on_delete=models.SET_NULL, null=True, blank=True, related_name='jobs')
    source = models.CharField(max_length=20, choices=JobSource.choices, blank=True, default='')
    job_post_url = models.URLField(max_length=500, blank=True, default='')
    description = models.TextField(blank=True, default='')
    cover_letter = models.TextField(blank=True, default='')
    upwork_job_id = models.CharField(max_length=100, blank=True, default='')
    upwork_contract_id = models.CharField(max_length=100, blank=True, default='')
    upwork_offer_id = models.CharField(max_length=100, blank=True, default='')
    job_type = models.CharField(max_length=10, choices=JobType.choices, default=JobType.FIXED)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    contract_value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    # Commission (for middleman)
    commission_type = models.CharField(max_length=10, choices=CommissionType.choices, default=CommissionType.PERCENT)
    commission_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    # Versioned settings
    settings_version = models.ForeignKey(SettingsVersion, on_delete=models.SET_NULL, null=True, blank=True)

    # Connects
    connects_used = models.IntegerField(default=0)

    # Overrides (job-specific)
    connect_override_mode = models.CharField(max_length=30, blank=True, default='')
    connect_override_value = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    platform_fee_override_enabled = models.BooleanField(null=True, blank=True)
    platform_fee_override_mode = models.CharField(max_length=30, blank=True, default='')
    platform_fee_override_value = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    platform_fee_override_apply_on = models.CharField(max_length=10, blank=True, default='')

    is_finalized = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_jobs')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.job_code} - {self.title}"


# ──────────────────────────────────────────────
# Receipt (income per job)
# ──────────────────────────────────────────────

class Receipt(models.Model):
    class Source(models.TextChoices):
        MILESTONE = 'milestone', 'Milestone'
        WEEKLY = 'weekly', 'Weekly'
        BONUS = 'bonus', 'Bonus'
        MANUAL = 'manual', 'Manual'

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='receipts')
    received_date = models.DateField()
    amount_received = models.DecimalField(max_digits=12, decimal_places=2)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MILESTONE)
    upwork_transaction_id = models.CharField(max_length=100, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-received_date']

    def __str__(self):
        return f"Receipt {self.amount_received} for {self.job.job_code}"


# ──────────────────────────────────────────────
# Job Allocation (worker share per job)
# ──────────────────────────────────────────────

class JobAllocation(models.Model):
    class ShareType(models.TextChoices):
        PERCENT = 'percent', 'Percentage'
        FIXED = 'fixed_amount', 'Fixed Amount'

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='allocations')
    worker = models.ForeignKey(Worker, on_delete=models.SET_NULL, null=True, blank=True, related_name='allocations')
    label = models.CharField(max_length=100, blank=True, default='')
    role = models.CharField(max_length=100, blank=True, default='')
    share_type = models.CharField(max_length=20, choices=ShareType.choices, default=ShareType.PERCENT)
    share_value = models.DecimalField(max_digits=10, decimal_places=4)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.label or self.worker} - {self.share_value} ({self.share_type})"


# ──────────────────────────────────────────────
# Payment (to workers)
# ──────────────────────────────────────────────

class Payment(models.Model):
    payment_code = models.CharField(max_length=20, unique=True)  # P0001, P0002
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='payments')
    job = models.ForeignKey(Job, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    paid_date = models.DateField()
    method = models.CharField(max_length=100, blank=True, default='')
    reference = models.CharField(max_length=200, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    is_auto_generated = models.BooleanField(default=False)  # auto-created from receipt
    is_paid = models.BooleanField(default=False)  # paid or pending
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-paid_date']

    def __str__(self):
        return f"{self.payment_code} - {self.amount_paid} to {self.worker}"


# ──────────────────────────────────────────────
# Job Calculation Snapshot (for finalized jobs)
# ──────────────────────────────────────────────

class JobCalculationSnapshot(models.Model):
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name='snapshot')
    settings_version = models.ForeignKey(SettingsVersion, on_delete=models.SET_NULL, null=True)
    snapshot_json = models.TextField(default='{}')
    finalized_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Snapshot for {self.job.job_code}"

    @property
    def data(self):
        return json.loads(self.snapshot_json)


# ──────────────────────────────────────────────
# Receipt Distribution (immutable per-receipt allocation snapshot)
# ──────────────────────────────────────────────

class ReceiptDistribution(models.Model):
    """Records exactly how a receipt was split among workers at the time it was created.
    Immutable — editing allocations does NOT change existing distributions."""

    class ShareType(models.TextChoices):
        PERCENT = 'percent', 'Percentage'
        FIXED = 'fixed_amount', 'Fixed Amount'

    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE, related_name='distributions')
    worker = models.ForeignKey(Worker, on_delete=models.SET_NULL, null=True, blank=True, related_name='distributions')
    label = models.CharField(max_length=100, blank=True, default='')  # role label: "Dev", "Design", "YOU"
    share_type = models.CharField(max_length=20, choices=ShareType.choices)
    share_value = models.DecimalField(max_digits=10, decimal_places=4)  # the split config at moment of receipt
    computed_amount = models.DecimalField(max_digits=12, decimal_places=2)  # actual $ after deductions
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        who = self.worker or self.label or 'Owner'
        return f"{who}: {self.computed_amount} from Receipt #{self.receipt_id}"


# ──────────────────────────────────────────────
# Expense (agency-level business expenses)
# ──────────────────────────────────────────────

class Expense(models.Model):
    class Category(models.TextChoices):
        CONNECTS = 'connects', 'Connects'
        TOOLS = 'tools', 'Tools'
        SOFTWARE = 'software', 'Software'
        SUBSCRIPTION = 'subscription', 'Subscription'
        MARKETING = 'marketing', 'Marketing'
        OFFICE = 'office', 'Office'
        OTHER = 'other', 'Other'

    expense_code = models.CharField(max_length=10, unique=True)  # E001, E002
    expense_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    description = models.CharField(max_length=300)
    vendor = models.CharField(max_length=200, blank=True, default='')
    reference = models.CharField(max_length=200, blank=True, default='')  # receipt/invoice number
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_expenses')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-expense_date']

    def __str__(self):
        return f"{self.expense_code} - {self.description} ({self.amount})"


# ──────────────────────────────────────────────
# App Settings (singleton branding & theming)
# ──────────────────────────────────────────────

class AppSettings(models.Model):
    # Branding
    app_name = models.CharField(max_length=100, default='Job Tracker')
    logo = models.ImageField(upload_to='branding/', blank=True, null=True)
    favicon = models.ImageField(upload_to='branding/', blank=True, null=True)
    footer_text = models.CharField(max_length=300, blank=True, default='')
    show_footer = models.BooleanField(default=False)

    # Colors
    primary_color = models.CharField(max_length=7, default='#0d6efd')
    accent_color = models.CharField(max_length=7, default='#6c757d')

    # Sidebar & navbar (light theme)
    sidebar_bg_light = models.CharField(max_length=7, default='#212529')
    sidebar_text_light = models.CharField(max_length=7, default='#adb5bd')
    topbar_bg_light = models.CharField(max_length=7, default='#212529')

    # Sidebar & navbar (dark theme)
    sidebar_bg_dark = models.CharField(max_length=7, default='#1a1d21')
    sidebar_text_dark = models.CharField(max_length=7, default='#adb5bd')
    topbar_bg_dark = models.CharField(max_length=7, default='#1a1d21')

    # Login page
    login_bg_color = models.CharField(max_length=7, default='#212529')
    login_bg_image = models.ImageField(upload_to='branding/', blank=True, null=True)

    # Default theme
    default_theme = models.CharField(max_length=10, default='dark', choices=[('dark', 'Dark'), ('light', 'Light')])

    class Meta:
        verbose_name = 'App Settings'
        verbose_name_plural = 'App Settings'

    def __str__(self):
        return 'App Settings'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
