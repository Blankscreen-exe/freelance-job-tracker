from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, UserRole, Client, ClientContact, ClientCompany, ClientAddress,
    Middleman, Worker,
    SettingsVersion, Job, Receipt, JobAllocation,
    Payment, JobCalculationSnapshot, ReceiptDistribution, Expense,
)


class UserRoleInline(admin.TabularInline):
    model = UserRole
    extra = 1


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [UserRoleInline]
    list_display = ('username', 'email', 'active_role', 'is_superuser', 'is_active')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Role Settings', {'fields': ('active_role',)}),
    )


class ClientContactInline(admin.TabularInline):
    model = ClientContact
    extra = 0


class ClientCompanyInline(admin.TabularInline):
    model = ClientCompany
    extra = 0


class ClientAddressInline(admin.TabularInline):
    model = ClientAddress
    extra = 0


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('client_code', 'name', 'primary_company', 'primary_email', 'source', 'is_archived')
    list_filter = ('is_archived', 'source', 'is_active')
    search_fields = ('name',)
    inlines = [ClientContactInline, ClientCompanyInline, ClientAddressInline]
    fieldsets = (
        (None, {'fields': ('client_code', 'name', 'is_archived', 'is_active', 'created_by')}),
        ('Source', {'fields': ('source', 'source_url', 'source_notes')}),
        ('Notes', {'fields': ('notes', 'internal_notes', 'tags')}),
    )


@admin.register(Middleman)
class MiddlemanAdmin(admin.ModelAdmin):
    list_display = ('middleman_code', 'name', 'email', 'is_archived')
    list_filter = ('is_archived',)
    search_fields = ('name', 'email')


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ('worker_code', 'name', 'contact', 'is_owner', 'is_archived')
    list_filter = ('is_archived', 'is_owner')
    search_fields = ('name', 'contact')


@admin.register(SettingsVersion)
class SettingsVersionAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at')
    list_filter = ('is_active',)


class ReceiptInline(admin.TabularInline):
    model = Receipt
    extra = 0


class AllocationInline(admin.TabularInline):
    model = JobAllocation
    extra = 0


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('job_code', 'title', 'client', 'source', 'status', 'contract_value')
    list_filter = ('status', 'job_type', 'source')
    search_fields = ('title', 'job_code')
    inlines = [ReceiptInline, AllocationInline, PaymentInline]


class ReceiptDistributionInline(admin.TabularInline):
    model = ReceiptDistribution
    extra = 0
    readonly_fields = ('worker', 'label', 'share_type', 'share_value', 'computed_amount', 'created_at')


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ('job', 'amount_received', 'received_date', 'source')
    list_filter = ('source',)
    inlines = [ReceiptDistributionInline]


@admin.register(JobAllocation)
class JobAllocationAdmin(admin.ModelAdmin):
    list_display = ('job', 'worker', 'label', 'share_type', 'share_value')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('payment_code', 'worker', 'job', 'amount_paid', 'paid_date', 'is_paid', 'is_auto_generated')
    list_filter = ('paid_date', 'is_paid', 'is_auto_generated')
    search_fields = ('payment_code',)


@admin.register(JobCalculationSnapshot)
class SnapshotAdmin(admin.ModelAdmin):
    list_display = ('job', 'finalized_at')


@admin.register(ReceiptDistribution)
class ReceiptDistributionAdmin(admin.ModelAdmin):
    list_display = ('receipt', 'worker', 'label', 'share_type', 'share_value', 'computed_amount')
    list_filter = ('share_type',)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('expense_code', 'description', 'amount', 'category', 'expense_date', 'vendor')
    list_filter = ('category', 'expense_date')
    search_fields = ('description', 'vendor', 'expense_code')
