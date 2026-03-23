from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Auth / Profile
    path('auth/switch-role/', views.switch_role, name='switch_role'),
    path('profile/', views.profile, name='profile'),
    path('profile/change-password/', views.change_password, name='change_password'),

    # Users (admin only)
    path('users/', views.user_list, name='user_list'),
    path('users/new/', views.user_create, name='user_create'),
    path('users/<int:pk>/', views.user_detail, name='user_detail'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),

    # Jobs
    path('jobs/', views.job_list, name='job_list'),
    path('jobs/new/', views.job_create, name='job_create'),
    path('jobs/<int:pk>/', views.job_detail, name='job_detail'),
    path('jobs/<int:pk>/edit/', views.job_edit, name='job_edit'),
    path('jobs/<int:pk>/archive/', views.job_archive, name='job_archive'),
    path('jobs/<int:pk>/finalize/', views.job_finalize, name='job_finalize'),
    path('jobs/<int:pk>/unfinalize/', views.job_unfinalize, name='job_unfinalize'),

    # Receipts (nested under jobs)
    path('jobs/<int:job_pk>/receipts/new/', views.receipt_create, name='receipt_create'),
    path('receipts/<int:pk>/edit/', views.receipt_edit, name='receipt_edit'),
    path('receipts/<int:pk>/delete/', views.receipt_delete, name='receipt_delete'),

    # Allocations (nested under jobs)
    path('jobs/<int:job_pk>/allocations/new/', views.allocation_create, name='allocation_create'),
    path('allocations/<int:pk>/edit/', views.allocation_edit, name='allocation_edit'),
    path('allocations/<int:pk>/delete/', views.allocation_delete, name='allocation_delete'),

    # Team Roster (unified workers + middlemen)
    path('team/', views.team_roster, name='team_roster'),

    # Clients
    path('clients/', views.client_list, name='client_list'),
    path('clients/new/', views.client_create, name='client_create'),
    path('clients/<int:pk>/', views.client_detail, name='client_detail'),
    path('clients/<int:pk>/edit/', views.client_edit, name='client_edit'),
    path('clients/<int:pk>/archive/', views.client_archive, name='client_archive'),

    # Middlemen (detail/create/edit)
    path('middlemen/new/', views.middleman_create, name='middleman_create'),
    path('middlemen/<int:pk>/', views.middleman_detail, name='middleman_detail'),
    path('middlemen/<int:pk>/edit/', views.middleman_edit, name='middleman_edit'),

    # Workers (detail/create/edit/invoice/archive)
    path('workers/new/', views.worker_create, name='worker_create'),
    path('workers/<int:pk>/', views.worker_detail, name='worker_detail'),
    path('workers/<int:pk>/edit/', views.worker_edit, name='worker_edit'),
    path('workers/<int:pk>/invoice/', views.worker_invoice, name='worker_invoice'),
    path('workers/<int:pk>/archive/', views.worker_archive, name='worker_archive'),

    # Payments
    path('payments/', views.payment_list, name='payment_list'),
    path('payments/new/', views.payment_create, name='payment_create'),
    path('payments/<int:pk>/edit/', views.payment_edit, name='payment_edit'),
    path('payments/<int:pk>/delete/', views.payment_delete, name='payment_delete'),
    path('payments/<int:pk>/mark-paid/', views.payment_mark_paid, name='payment_mark_paid'),
    path('payments/<int:pk>/mark-unpaid/', views.payment_mark_unpaid, name='payment_mark_unpaid'),

    # Expenses
    path('expenses/', views.expense_list, name='expense_list'),
    path('expenses/new/', views.expense_create, name='expense_create'),
    path('expenses/tracking/', views.expense_tracking, name='expense_tracking'),
    path('expenses/<int:pk>/', views.expense_detail, name='expense_detail'),
    path('expenses/<int:pk>/edit/', views.expense_edit, name='expense_edit'),
    path('expenses/<int:pk>/delete/', views.expense_delete, name='expense_delete'),

    # Reports
    path('reports/pnl/', views.pnl_report, name='pnl_report'),
    path('reports/pnl/export/', views.pnl_export, name='pnl_export'),
    path('reports/ledger/', views.ledger_report, name='ledger_report'),
    path('reports/ledger/export/', views.ledger_export, name='ledger_export'),

    # Settings
    path('settings/', views.settings_list, name='settings_list'),
    path('settings/new/', views.settings_create, name='settings_create'),
    path('settings/<int:pk>/', views.settings_detail, name='settings_detail'),
    path('settings/<int:pk>/activate/', views.settings_activate, name='settings_activate'),
    path('settings/<int:pk>/clone/', views.settings_clone, name='settings_clone'),
]
