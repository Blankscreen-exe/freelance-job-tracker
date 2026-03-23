import re
import json
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q
from django.http import HttpResponseBadRequest

from .models import (
    Job, Client, ClientContact, ClientCompany, ClientAddress,
    Middleman, Worker, Payment, Receipt,
    JobAllocation, SettingsVersion, ReceiptDistribution,
    JobCalculationSnapshot,
)
from .services.calculations import (
    get_job_totals, compute_allocations, compute_worker_totals,
    get_dashboard_totals, get_receipt_deductions, compute_receipt_distributions,
)
from .services.payment_generator import generate_payments_from_receipt
from .services.reports import get_pnl_data, get_ledger_entries, pnl_to_csv_rows, ledger_to_csv_rows


# ──────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────

@login_required
def dashboard(request):
    visible = get_visible_jobs(request.user)
    active_jobs = visible.filter(status='active').count()
    recent_jobs = visible.select_related('client')[:10]

    is_worker = not request.user.is_admin_user() and request.user.active_role == 'worker'

    if is_worker:
        # Worker dashboard: show only their own earnings/payments
        worker = getattr(request.user, 'worker_profile', None)
        if worker:
            wt = compute_worker_totals(worker)
        else:
            wt = {'earned': 0, 'paid': 0, 'due': 0}
        return render(request, 'dashboard.html', {
            'is_worker_view': True,
            'is_middleman_view': False,
            'worker_totals': wt,
            'totals': {'active_jobs': active_jobs},
            'recent_jobs': recent_jobs,
            'top_due_workers': [],
        })

    is_middleman = not request.user.is_admin_user() and request.user.active_role == 'middleman'

    # Admin / middleman dashboard
    totals = get_dashboard_totals(visible)

    # Top due workers — scoped to visible jobs for middlemen
    if is_middleman:
        visible_job_ids = visible.values_list('id', flat=True)
        worker_ids = set(
            JobAllocation.objects.filter(job_id__in=visible_job_ids).values_list('worker_id', flat=True)
        ) | set(
            Payment.objects.filter(job_id__in=visible_job_ids).values_list('worker_id', flat=True)
        )
        workers = Worker.objects.filter(id__in=worker_ids, is_archived=False)
    else:
        workers = Worker.objects.filter(is_archived=False)

    top_due = []
    for w in workers:
        wt = compute_worker_totals(w)
        if wt['due'] > 0:
            top_due.append({'id': w.id, 'name': w.name, 'due': wt['due']})
    top_due.sort(key=lambda x: x['due'], reverse=True)

    return render(request, 'dashboard.html', {
        'is_worker_view': False,
        'is_middleman_view': is_middleman,
        'totals': {**totals, 'active_jobs': active_jobs},
        'recent_jobs': recent_jobs,
        'top_due_workers': top_due[:5],
    })


# ──────────────────────────────────────────────
# Jobs
# ──────────────────────────────────────────────

@login_required
def job_list(request):
    jobs = get_visible_jobs(request.user).select_related('client', 'middleman')
    return render(request, 'jobs/list.html', {'jobs': jobs})


@login_required
def job_detail(request, pk):
    job = get_object_or_404(Job.objects.select_related('client', 'middleman', 'settings_version'), pk=pk)
    # Access check
    if not get_visible_jobs(request.user).filter(pk=pk).exists():
        messages.error(request, "You don't have access to this job.")
        return redirect('job_list')
    receipts = job.receipts.all()
    allocations = job.allocations.select_related('worker').all()
    payments = job.payments.select_related('worker').all()

    # Use calculation engine for totals
    if job.is_finalized and hasattr(job, 'snapshot'):
        try:
            snapshot = job.snapshot.data
            totals = snapshot.get('totals', {})
            alloc_results = snapshot.get('allocations', [])
        except Exception:
            totals = get_job_totals(job)
            alloc_results = compute_allocations(job, totals['net_distributable'])
    else:
        totals = get_job_totals(job)
        alloc_results = compute_allocations(job, totals['net_distributable'])

    # Build allocation display with earned amounts
    alloc_display = []
    for item in alloc_results:
        if isinstance(item, dict) and 'allocation' in item:
            alloc_display.append({'alloc': item['allocation'], 'earned': item['earned']})
        else:
            # Snapshot format
            alloc_obj = allocations.filter(id=item.get('allocation_id')).first()
            alloc_display.append({'alloc': alloc_obj, 'earned': Decimal(str(item.get('earned', 0)))})

    workers = Worker.objects.filter(is_archived=False)

    return render(request, 'jobs/detail.html', {
        'job': job,
        'receipts': receipts,
        'allocations': allocations,
        'alloc_display': alloc_display,
        'payments': payments,
        'totals': totals,
        'workers': workers,
    })


def _next_code(model, prefix, pad=2):
    """Generate the next sequential code like J01, W02, P0003."""
    last = model.objects.order_by('-id').first()
    num = 1
    if last:
        code_field = {
            'J': 'job_code', 'C': 'client_code', 'M': 'middleman_code',
            'W': 'worker_code', 'P': 'payment_code', 'E': 'expense_code',
        }.get(prefix, 'code')
        code = getattr(last, code_field, '')
        m = re.match(rf'{prefix}(\d+)', code)
        if m:
            num = int(m.group(1)) + 1
    return f"{prefix}{num:0{pad}d}"


@login_required
def job_create(request):
    if request.method == 'POST':
        sv = SettingsVersion.objects.filter(is_active=True).first()
        job = Job(
            job_code=_next_code(Job, 'J'),
            title=request.POST['title'],
            source=request.POST.get('source', ''),
            job_type=request.POST.get('job_type', 'fixed'),
            status=request.POST.get('status', 'draft'),
            contract_value=request.POST.get('contract_value') or 0,
            job_post_url=request.POST.get('job_post_url', ''),
            description=request.POST.get('description', ''),
            cover_letter=request.POST.get('cover_letter', ''),
            upwork_job_id=request.POST.get('upwork_job_id', ''),
            upwork_contract_id=request.POST.get('upwork_contract_id', ''),
            upwork_offer_id=request.POST.get('upwork_offer_id', ''),
            connects_used=request.POST.get('connects_used') or 0,
            commission_type=request.POST.get('commission_type', 'percent'),
            commission_value=request.POST.get('commission_value') or 0,
            start_date=request.POST.get('start_date') or None,
            end_date=request.POST.get('end_date') or None,
            settings_version=sv,
            created_by=request.user,
        )
        client_id = request.POST.get('client')
        if client_id:
            job.client_id = client_id
        middleman_id = request.POST.get('middleman')
        if middleman_id:
            job.middleman_id = middleman_id
        job.save()
        messages.success(request, f"Job {job.job_code} created.")
        return redirect('job_detail', pk=job.pk)

    clients = Client.objects.filter(is_archived=False)
    middlemen = Middleman.objects.filter(is_archived=False)
    return render(request, 'jobs/form.html', {
        'clients': clients,
        'middlemen': middlemen,
        'job': None,
    })


@login_required
def job_edit(request, pk):
    job = get_object_or_404(Job, pk=pk)
    if request.method == 'POST':
        job.title = request.POST['title']
        job.source = request.POST.get('source', '')
        job.job_type = request.POST.get('job_type', 'fixed')
        job.status = request.POST.get('status', job.status)
        job.contract_value = request.POST.get('contract_value') or 0
        job.job_post_url = request.POST.get('job_post_url', '')
        job.description = request.POST.get('description', '')
        job.cover_letter = request.POST.get('cover_letter', '')
        job.upwork_job_id = request.POST.get('upwork_job_id', '')
        job.upwork_contract_id = request.POST.get('upwork_contract_id', '')
        job.upwork_offer_id = request.POST.get('upwork_offer_id', '')
        job.connects_used = request.POST.get('connects_used') or 0
        job.commission_type = request.POST.get('commission_type', 'percent')
        job.commission_value = request.POST.get('commission_value') or 0
        job.start_date = request.POST.get('start_date') or None
        job.end_date = request.POST.get('end_date') or None
        client_id = request.POST.get('client')
        job.client_id = client_id if client_id else None
        middleman_id = request.POST.get('middleman')
        job.middleman_id = middleman_id if middleman_id else None
        job.save()
        messages.success(request, f"Job {job.job_code} updated.")
        return redirect('job_detail', pk=job.pk)

    clients = Client.objects.filter(is_archived=False)
    middlemen = Middleman.objects.filter(is_archived=False)
    return render(request, 'jobs/form.html', {
        'job': job,
        'clients': clients,
        'middlemen': middlemen,
    })


# ──────────────────────────────────────────────
# Clients
# ──────────────────────────────────────────────

_CLIENT_FIELDS = ['name', 'source', 'source_url', 'source_notes', 'notes', 'internal_notes', 'tags']


def _populate_client_from_post(client, post):
    for f in _CLIENT_FIELDS:
        setattr(client, f, post.get(f, ''))


def _save_client_related(client, post):
    """Save contacts, companies, and addresses from POST data."""
    # Contacts: contact_type[], contact_value[], contact_label[], contact_primary
    client.contacts.all().delete()
    types = post.getlist('contact_type')
    values = post.getlist('contact_value')
    labels = post.getlist('contact_label')
    primary_idx = post.get('contact_primary', '')
    for i, (ct, cv) in enumerate(zip(types, values)):
        if cv.strip():
            ClientContact.objects.create(
                client=client, contact_type=ct, value=cv.strip(),
                label=labels[i] if i < len(labels) else 'work',
                is_primary=(str(i) == primary_idx),
            )

    # Companies: comp_name[], comp_role[], comp_website[], comp_registration[], comp_industry[], comp_size[], comp_current[]
    client.companies.all().delete()
    names = post.getlist('comp_name')
    roles = post.getlist('comp_role')
    websites = post.getlist('comp_website')
    registrations = post.getlist('comp_registration')
    industries = post.getlist('comp_industry')
    sizes = post.getlist('comp_size')
    current_indices = post.getlist('comp_current')
    for i, name in enumerate(names):
        if name.strip():
            ClientCompany.objects.create(
                client=client, company_name=name.strip(),
                role=roles[i] if i < len(roles) else '',
                website=websites[i] if i < len(websites) else '',
                registration=registrations[i] if i < len(registrations) else '',
                industry=industries[i] if i < len(industries) else '',
                size=sizes[i] if i < len(sizes) else '',
                is_current=(str(i) in current_indices),
            )

    # Addresses: addr_label[], addr_line1[], addr_line2[], addr_city[], addr_state[], addr_postal[], addr_country[], addr_tz[], addr_primary
    client.addresses.all().delete()
    addr_labels = post.getlist('addr_label')
    lines1 = post.getlist('addr_line1')
    lines2 = post.getlist('addr_line2')
    cities = post.getlist('addr_city')
    states = post.getlist('addr_state')
    postals = post.getlist('addr_postal')
    countries = post.getlist('addr_country')
    timezones = post.getlist('addr_tz')
    addr_primary = post.get('addr_primary', '')
    for i in range(len(lines1)):
        if lines1[i].strip() or (i < len(cities) and cities[i].strip()):
            ClientAddress.objects.create(
                client=client,
                label=addr_labels[i] if i < len(addr_labels) else 'office',
                address_line1=lines1[i].strip() if i < len(lines1) else '',
                address_line2=lines2[i].strip() if i < len(lines2) else '',
                city=cities[i].strip() if i < len(cities) else '',
                state=states[i].strip() if i < len(states) else '',
                postal_code=postals[i].strip() if i < len(postals) else '',
                country=countries[i].strip() if i < len(countries) else '',
                timezone=timezones[i].strip() if i < len(timezones) else '',
                is_primary=(str(i) == addr_primary),
            )

@login_required
def client_list(request):
    if not request.user.is_admin_user() and request.user.active_role != 'middleman':
        messages.error(request, "Access restricted.")
        return redirect('dashboard')
    clients = Client.objects.filter(is_archived=False).prefetch_related('contacts', 'companies')
    if not request.user.is_admin_user():
        clients = clients.filter(created_by=request.user)
    return render(request, 'clients/list.html', {'clients': clients})


@login_required
def client_detail(request, pk):
    client = get_object_or_404(Client.objects.prefetch_related('contacts', 'companies', 'addresses'), pk=pk)
    jobs = client.jobs.all()
    return render(request, 'clients/detail.html', {'client': client, 'jobs': jobs})


@login_required
def client_create(request):
    if request.method == 'POST':
        client = Client(client_code=_next_code(Client, 'C'), created_by=request.user)
        _populate_client_from_post(client, request.POST)
        client.save()
        _save_client_related(client, request.POST)
        messages.success(request, f"Client {client.client_code} created.")
        return redirect('client_detail', pk=client.pk)

    return render(request, 'clients/form.html', {'client': None, 'contact_types': ClientContact.ContactType.choices, 'contact_labels': ClientContact.Label.choices, 'addr_labels': ClientAddress.Label.choices})


@login_required
def client_edit(request, pk):
    client = get_object_or_404(Client.objects.prefetch_related('contacts', 'companies', 'addresses'), pk=pk)
    if request.method == 'POST':
        _populate_client_from_post(client, request.POST)
        client.save()
        _save_client_related(client, request.POST)
        messages.success(request, f"Client {client.client_code} updated.")
        return redirect('client_detail', pk=client.pk)

    return render(request, 'clients/form.html', {'client': client, 'contact_types': ClientContact.ContactType.choices, 'contact_labels': ClientContact.Label.choices, 'addr_labels': ClientAddress.Label.choices})


# ──────────────────────────────────────────────
# Middlemen
# ──────────────────────────────────────────────

@login_required
def team_roster(request):
    role_filter = request.GET.get('role', '')
    search = request.GET.get('q', '').strip()

    roster = []

    if role_filter in ('', 'worker'):
        workers = Worker.objects.filter(is_archived=False)
        if search:
            workers = workers.filter(name__icontains=search)
        for w in workers:
            roster.append({
                'role': 'worker',
                'code': w.worker_code,
                'name': w.name,
                'contact': w.contact or '-',
                'pk': w.pk,
                'detail_url': 'worker_detail',
                'edit_url': 'worker_edit',
            })

    if role_filter in ('', 'middleman'):
        middlemen = Middleman.objects.filter(is_archived=False)
        if search:
            middlemen = middlemen.filter(name__icontains=search)
        for m in middlemen:
            roster.append({
                'role': 'middleman',
                'code': m.middleman_code,
                'name': m.name,
                'contact': m.email or m.phone or '-',
                'pk': m.pk,
                'detail_url': 'middleman_detail',
                'edit_url': 'middleman_edit',
            })

    roster.sort(key=lambda x: x['name'].lower())

    return render(request, 'team/roster.html', {
        'roster': roster,
        'role_filter': role_filter,
        'search': search,
    })


@login_required
def middleman_detail(request, pk):
    middleman = get_object_or_404(Middleman, pk=pk)
    # Show jobs via created_by (single source of truth) OR legacy middleman FK
    if middleman.user:
        jobs = Job.objects.filter(
            Q(created_by=middleman.user) | Q(middleman=middleman)
        ).distinct()
    else:
        jobs = middleman.jobs.all()
    return render(request, 'middlemen/detail.html', {'middleman': middleman, 'jobs': jobs})


@login_required
def middleman_create(request):
    if request.method == 'POST':
        middleman = Middleman(
            middleman_code=_next_code(Middleman, 'M'),
            name=request.POST['name'],
            email=request.POST.get('email', ''),
            phone=request.POST.get('phone', ''),
            contact=request.POST.get('contact', ''),
            notes=request.POST.get('notes', ''),
        )
        middleman.save()
        messages.success(request, f"Middleman {middleman.middleman_code} created.")
        return redirect('middleman_detail', pk=middleman.pk)

    return render(request, 'middlemen/form.html', {'middleman': None})


@login_required
def middleman_edit(request, pk):
    middleman = get_object_or_404(Middleman, pk=pk)
    if request.method == 'POST':
        middleman.name = request.POST['name']
        middleman.email = request.POST.get('email', '')
        middleman.phone = request.POST.get('phone', '')
        middleman.contact = request.POST.get('contact', '')
        middleman.notes = request.POST.get('notes', '')
        middleman.save()
        messages.success(request, f"Middleman {middleman.middleman_code} updated.")
        return redirect('middleman_detail', pk=middleman.pk)

    return render(request, 'middlemen/form.html', {'middleman': middleman})


# ──────────────────────────────────────────────
# Workers
# ──────────────────────────────────────────────



@login_required
def worker_detail(request, pk):
    worker = get_object_or_404(Worker, pk=pk)
    allocations = worker.allocations.select_related('job').all()
    payments = worker.payments.select_related('job').all()

    wt = compute_worker_totals(worker)

    return render(request, 'workers/detail.html', {
        'worker': worker,
        'allocations': allocations,
        'payments': payments,
        'total_earned': wt['earned'],
        'total_paid': wt['paid'],
        'total_due': wt['due'],
    })


@login_required
def worker_create(request):
    if request.method == 'POST':
        worker = Worker(
            worker_code=_next_code(Worker, 'W'),
            name=request.POST['name'],
            contact=request.POST.get('contact', ''),
            notes=request.POST.get('notes', ''),
            is_owner=request.POST.get('is_owner') == 'on',
        )
        worker.save()
        messages.success(request, f"Worker {worker.worker_code} created.")
        return redirect('worker_detail', pk=worker.pk)

    return render(request, 'workers/form.html', {'worker': None})


@login_required
def worker_edit(request, pk):
    worker = get_object_or_404(Worker, pk=pk)
    if request.method == 'POST':
        worker.name = request.POST['name']
        worker.contact = request.POST.get('contact', '')
        worker.notes = request.POST.get('notes', '')
        worker.is_owner = request.POST.get('is_owner') == 'on'
        worker.save()
        messages.success(request, f"Worker {worker.worker_code} updated.")
        return redirect('worker_detail', pk=worker.pk)

    return render(request, 'workers/form.html', {'worker': worker})


# ──────────────────────────────────────────────
# Payments
# ──────────────────────────────────────────────

@login_required
def payment_list(request):
    payments = Payment.objects.select_related('worker', 'job').all()

    # Role-based filtering
    if not request.user.is_admin_user():
        if request.user.active_role == 'worker':
            worker = getattr(request.user, 'worker_profile', None)
            payments = payments.filter(worker=worker) if worker else payments.none()
        elif request.user.active_role == 'middleman':
            visible_job_ids = get_visible_jobs(request.user).values_list('id', flat=True)
            payments = payments.filter(job_id__in=visible_job_ids)

    # Filters
    worker_id = request.GET.get('worker')
    job_id = request.GET.get('job')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if worker_id:
        payments = payments.filter(worker_id=worker_id)
    if job_id:
        payments = payments.filter(job_id=job_id)
    if date_from:
        payments = payments.filter(paid_date__gte=date_from)
    if date_to:
        payments = payments.filter(paid_date__lte=date_to)

    is_worker = not request.user.is_admin_user() and request.user.active_role == 'worker'
    is_middleman = not request.user.is_admin_user() and request.user.active_role == 'middleman'
    if is_worker:
        workers = Worker.objects.none()
        jobs = get_visible_jobs(request.user)
    elif is_middleman:
        visible = get_visible_jobs(request.user)
        visible_job_ids = visible.values_list('id', flat=True)
        worker_ids = set(
            JobAllocation.objects.filter(job_id__in=visible_job_ids).values_list('worker_id', flat=True)
        ) | set(
            Payment.objects.filter(job_id__in=visible_job_ids).values_list('worker_id', flat=True)
        )
        workers = Worker.objects.filter(id__in=worker_ids, is_archived=False)
        jobs = visible
    else:
        workers = Worker.objects.filter(is_archived=False)
        jobs = Job.objects.exclude(status='archived')

    return render(request, 'payments/list.html', {
        'payments': payments,
        'workers': workers,
        'jobs': jobs,
        'is_worker_view': is_worker,
        'filters': {'worker': worker_id, 'job': job_id, 'date_from': date_from, 'date_to': date_to},
    })


@login_required
def payment_create(request):
    if request.method == 'POST':
        payment = Payment(
            payment_code=_next_code(Payment, 'P', pad=4),
            worker_id=request.POST['worker'],
            amount_paid=request.POST['amount_paid'],
            paid_date=request.POST['paid_date'],
            method=request.POST.get('method', ''),
            reference=request.POST.get('reference', ''),
            notes=request.POST.get('notes', ''),
        )
        job_id = request.POST.get('job')
        if job_id:
            payment.job_id = job_id
        payment.save()
        messages.success(request, f"Payment {payment.payment_code} recorded.")
        return redirect('payment_list')

    workers = Worker.objects.filter(is_archived=False)
    jobs = Job.objects.exclude(status='archived')
    return render(request, 'payments/form.html', {
        'payment': None,
        'workers': workers,
        'jobs': jobs,
    })


@login_required
def payment_edit(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    if request.method == 'POST':
        payment.worker_id = request.POST['worker']
        payment.amount_paid = request.POST['amount_paid']
        payment.paid_date = request.POST['paid_date']
        payment.method = request.POST.get('method', '')
        payment.reference = request.POST.get('reference', '')
        payment.notes = request.POST.get('notes', '')
        job_id = request.POST.get('job')
        payment.job_id = job_id if job_id else None
        payment.save()
        messages.success(request, f"Payment {payment.payment_code} updated.")
        return redirect('payment_list')

    workers = Worker.objects.filter(is_archived=False)
    jobs = Job.objects.exclude(status='archived')
    return render(request, 'payments/form.html', {
        'payment': payment,
        'workers': workers,
        'jobs': jobs,
    })


@login_required
def payment_delete(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    if request.method == 'POST':
        payment.delete()
        messages.success(request, "Payment deleted.")
    return redirect('payment_list')


@login_required
def payment_mark_paid(request, pk):
    if request.method == 'POST':
        payment = get_object_or_404(Payment, pk=pk)
        payment.is_paid = True
        payment.save()
        messages.success(request, f"Payment {payment.payment_code} marked as paid.")
    return redirect(request.POST.get('next', 'payment_list'))


@login_required
def payment_mark_unpaid(request, pk):
    if request.method == 'POST':
        payment = get_object_or_404(Payment, pk=pk)
        payment.is_paid = False
        payment.save()
        messages.success(request, f"Payment {payment.payment_code} marked as unpaid.")
    return redirect(request.POST.get('next', 'payment_list'))


# ──────────────────────────────────────────────
# Settings Versions
# ──────────────────────────────────────────────

@login_required
def settings_list(request):
    versions = SettingsVersion.objects.all()
    return render(request, 'settings/list.html', {'versions': versions})


@login_required
def settings_detail(request, pk):
    version = get_object_or_404(SettingsVersion, pk=pk)
    return render(request, 'settings/detail.html', {'version': version})


@login_required
def settings_create(request):
    if request.method == 'POST':
        rules = {
            'currency_default': request.POST.get('currency_default', 'USD'),
            'connect_cost_per_unit': float(request.POST.get('connect_cost_per_unit', 0.15)),
            'platform_fee': {
                'enabled': request.POST.get('platform_fee_enabled') == 'on',
                'mode': request.POST.get('platform_fee_mode', 'percent'),
                'value': float(request.POST.get('platform_fee_value', 0)),
                'apply_on': request.POST.get('platform_fee_apply_on', 'net'),
            },
        }
        sv = SettingsVersion(
            name=request.POST['name'],
            rules_json=json.dumps(rules),
            notes=request.POST.get('notes', ''),
        )
        sv.save()
        messages.success(request, f"Settings version '{sv.name}' created.")
        return redirect('settings_list')

    return render(request, 'settings/form.html', {'version': None})


@login_required
def settings_activate(request, pk):
    if request.method == 'POST':
        SettingsVersion.objects.update(is_active=False)
        sv = get_object_or_404(SettingsVersion, pk=pk)
        sv.is_active = True
        sv.save()
        messages.success(request, f"'{sv.name}' is now the active settings version.")
    return redirect('settings_list')


@login_required
def settings_clone(request, pk):
    if request.method == 'POST':
        original = get_object_or_404(SettingsVersion, pk=pk)
        clone = SettingsVersion(
            name=f"{original.name} (Copy)",
            is_active=False,
            rules_json=original.rules_json,
            notes=original.notes,
        )
        clone.save()
        messages.success(request, f"Cloned '{original.name}' as '{clone.name}'.")
        return redirect('settings_detail', pk=clone.pk)
    return redirect('settings_detail', pk=pk)


# ──────────────────────────────────────────────
# Receipts (nested under jobs)
# ──────────────────────────────────────────────

@login_required
def receipt_create(request, job_pk):
    job = get_object_or_404(Job, pk=job_pk)
    if job.is_finalized:
        messages.error(request, "Cannot add receipts to a finalized job.")
        return redirect('job_detail', pk=job.pk)

    allocations = job.allocations.select_related('worker').all()

    if request.method == 'POST':
        receipt = Receipt(
            job=job,
            received_date=request.POST['received_date'],
            amount_received=request.POST['amount_received'],
            source=request.POST.get('source', 'milestone'),
            upwork_transaction_id=request.POST.get('upwork_transaction_id', ''),
            notes=request.POST.get('notes', ''),
        )
        receipt.save()

        # Determine which allocations to use for distribution
        use_custom = request.POST.get('use_custom') == 'on'

        if use_custom:
            # Parse custom allocation rows from form
            alloc_data = []
            idx = 0
            while f'custom_worker_{idx}' in request.POST:
                worker_id = request.POST.get(f'custom_worker_{idx}')
                share_type = request.POST.get(f'custom_share_type_{idx}', 'percent')
                share_value = request.POST.get(f'custom_share_value_{idx}', '0')
                label = request.POST.get(f'custom_label_{idx}', '')
                worker = Worker.objects.filter(pk=worker_id).first() if worker_id else None
                alloc_data.append({
                    'worker': worker,
                    'label': label or (worker.name if worker else 'Owner'),
                    'share_type': share_type,
                    'share_value': share_value,
                })
                idx += 1
        else:
            # Use predefined allocations (selected checkboxes)
            selected_ids = request.POST.getlist('allocation_ids')
            if selected_ids:
                selected = allocations.filter(id__in=selected_ids)
            else:
                selected = allocations  # default: all

            alloc_data = [{
                'worker': a.worker,
                'label': a.label,
                'share_type': a.share_type,
                'share_value': str(a.share_value),
            } for a in selected]

        # Compute deductions and create ReceiptDistribution rows
        if alloc_data:
            connect_ded, pf = get_receipt_deductions(job, receipt)
            distributions = compute_receipt_distributions(receipt, alloc_data, connect_ded, pf)
            for dist in distributions:
                ReceiptDistribution.objects.create(
                    receipt=receipt,
                    worker=dist['worker'],
                    label=dist['label'],
                    share_type=dist['share_type'],
                    share_value=dist['share_value'],
                    computed_amount=dist['computed_amount'],
                )

        # Auto-generate payments from distributions
        auto_payments = generate_payments_from_receipt(receipt)
        if auto_payments:
            messages.info(request, f"{len(auto_payments)} payment(s) auto-generated.")

        messages.success(request, f"Receipt of ${receipt.amount_received} added.")
        return redirect('job_detail', pk=job.pk)

    workers = Worker.objects.filter(is_archived=False)
    return render(request, 'receipts/form.html', {
        'job': job,
        'allocations': allocations,
        'workers': workers,
        'receipt': None,
    })


@login_required
def receipt_edit(request, pk):
    receipt = get_object_or_404(Receipt.objects.select_related('job'), pk=pk)
    job = receipt.job
    if job.is_finalized:
        messages.error(request, "Cannot edit receipts on a finalized job.")
        return redirect('job_detail', pk=job.pk)

    if request.method == 'POST':
        old_amount = receipt.amount_received
        receipt.received_date = request.POST['received_date']
        receipt.amount_received = request.POST['amount_received']
        receipt.source = request.POST.get('source', receipt.source)
        receipt.upwork_transaction_id = request.POST.get('upwork_transaction_id', '')
        receipt.notes = request.POST.get('notes', '')
        receipt.save()

        # If amount changed, recompute distributions and regenerate payments
        if Decimal(str(receipt.amount_received)) != old_amount:
            old_distributions = list(receipt.distributions.values(
                'worker_id', 'label', 'share_type', 'share_value'
            ))
            receipt.distributions.all().delete()

            # Delete old auto-generated payments for this receipt
            Payment.objects.filter(
                job=job, is_auto_generated=True, reference=f"Receipt #{receipt.id}",
            ).delete()

            if old_distributions:
                alloc_data = [{
                    'worker': Worker.objects.filter(pk=d['worker_id']).first() if d['worker_id'] else None,
                    'label': d['label'],
                    'share_type': d['share_type'],
                    'share_value': str(d['share_value']),
                } for d in old_distributions]

                connect_ded, pf = get_receipt_deductions(job, receipt)
                new_dists = compute_receipt_distributions(receipt, alloc_data, connect_ded, pf)
                for dist in new_dists:
                    ReceiptDistribution.objects.create(
                        receipt=receipt,
                        worker=dist['worker'],
                        label=dist['label'],
                        share_type=dist['share_type'],
                        share_value=dist['share_value'],
                        computed_amount=dist['computed_amount'],
                    )

                # Regenerate auto-payments
                auto_payments = generate_payments_from_receipt(receipt)
                if auto_payments:
                    messages.info(request, f"{len(auto_payments)} payment(s) regenerated.")

        messages.success(request, "Receipt updated.")
        return redirect('job_detail', pk=job.pk)

    return render(request, 'receipts/form.html', {
        'job': job,
        'receipt': receipt,
        'allocations': job.allocations.select_related('worker').all(),
        'workers': Worker.objects.filter(is_archived=False),
    })


@login_required
def receipt_delete(request, pk):
    receipt = get_object_or_404(Receipt.objects.select_related('job'), pk=pk)
    job = receipt.job
    if job.is_finalized:
        messages.error(request, "Cannot delete receipts from a finalized job.")
        return redirect('job_detail', pk=job.pk)

    if request.method == 'POST':
        # Also delete auto-generated payments linked to this receipt
        Payment.objects.filter(
            job=job,
            is_auto_generated=True,
            reference=f"Receipt #{receipt.id}",
        ).delete()
        receipt.delete()  # CASCADE deletes distributions
        messages.success(request, "Receipt deleted.")
    return redirect('job_detail', pk=job.pk)


# ──────────────────────────────────────────────
# Allocations (nested under jobs)
# ──────────────────────────────────────────────

@login_required
def allocation_create(request, job_pk):
    job = get_object_or_404(Job, pk=job_pk)
    if job.is_finalized:
        messages.error(request, "Cannot add allocations to a finalized job.")
        return redirect('job_detail', pk=job.pk)

    if request.method == 'POST':
        worker_id = request.POST.get('worker')
        alloc = JobAllocation(
            job=job,
            worker_id=worker_id if worker_id else None,
            label=request.POST.get('label', ''),
            role=request.POST.get('role', ''),
            share_type=request.POST.get('share_type', 'percent'),
            share_value=request.POST.get('share_value', 0),
            notes=request.POST.get('notes', ''),
        )
        alloc.save()
        messages.success(request, f"Allocation added for {alloc.label or alloc.worker or 'Owner'}.")
        return redirect('job_detail', pk=job.pk)

    workers = Worker.objects.filter(is_archived=False)
    return render(request, 'allocations/form.html', {
        'job': job,
        'allocation': None,
        'workers': workers,
    })


@login_required
def allocation_edit(request, pk):
    alloc = get_object_or_404(JobAllocation.objects.select_related('job'), pk=pk)
    job = alloc.job
    if job.is_finalized:
        messages.error(request, "Cannot edit allocations on a finalized job.")
        return redirect('job_detail', pk=job.pk)

    if request.method == 'POST':
        worker_id = request.POST.get('worker')
        alloc.worker_id = worker_id if worker_id else None
        alloc.label = request.POST.get('label', '')
        alloc.role = request.POST.get('role', '')
        alloc.share_type = request.POST.get('share_type', 'percent')
        alloc.share_value = request.POST.get('share_value', 0)
        alloc.notes = request.POST.get('notes', '')
        alloc.save()
        messages.success(request, "Allocation updated.")
        return redirect('job_detail', pk=job.pk)

    workers = Worker.objects.filter(is_archived=False)
    return render(request, 'allocations/form.html', {
        'job': job,
        'allocation': alloc,
        'workers': workers,
    })


@login_required
def allocation_delete(request, pk):
    alloc = get_object_or_404(JobAllocation.objects.select_related('job'), pk=pk)
    job = alloc.job
    if job.is_finalized:
        messages.error(request, "Cannot delete allocations from a finalized job.")
        return redirect('job_detail', pk=job.pk)

    if request.method == 'POST':
        alloc.delete()
        messages.success(request, "Allocation deleted.")
    return redirect('job_detail', pk=job.pk)


# ──────────────────────────────────────────────
# Job Actions (archive, finalize, unfinalize)
# ──────────────────────────────────────────────

@login_required
def job_archive(request, pk):
    if request.method == 'POST':
        job = get_object_or_404(Job, pk=pk)
        job.status = 'archived'
        job.save()
        messages.success(request, f"Job {job.job_code} archived.")
    return redirect('job_list')


@login_required
def job_finalize(request, pk):
    if request.method == 'POST':
        job = get_object_or_404(Job.objects.select_related('settings_version'), pk=pk)
        if job.is_finalized:
            messages.warning(request, "Job is already finalized.")
            return redirect('job_detail', pk=pk)

        totals = get_job_totals(job)
        alloc_results = compute_allocations(job, totals['net_distributable'])

        snapshot_data = {
            'totals': {k: str(v) for k, v in totals.items()},
            'allocations': [{
                'allocation_id': item['allocation'].id,
                'worker_name': str(item['allocation'].worker) if item['allocation'].worker else 'Owner',
                'label': item['allocation'].label,
                'share_type': item['allocation'].share_type,
                'share_value': str(item['allocation'].share_value),
                'earned': str(item['earned']),
            } for item in alloc_results],
        }

        JobCalculationSnapshot.objects.update_or_create(
            job=job,
            defaults={
                'settings_version': job.settings_version,
                'snapshot_json': json.dumps(snapshot_data),
            },
        )
        job.is_finalized = True
        job.save()
        messages.success(request, f"Job {job.job_code} finalized. Calculations locked.")
    return redirect('job_detail', pk=pk)


@login_required
def job_unfinalize(request, pk):
    if request.method == 'POST':
        job = get_object_or_404(Job, pk=pk)
        JobCalculationSnapshot.objects.filter(job=job).delete()
        job.is_finalized = False
        job.save()
        messages.success(request, f"Job {job.job_code} unfinalized. Edits re-enabled.")
    return redirect('job_detail', pk=pk)


# ──────────────────────────────────────────────
# Phase 6: Auth, Profile, Role Switching, User Management
# ──────────────────────────────────────────────

@login_required
def switch_role(request):
    if request.method == 'POST':
        role = request.POST.get('role', '')
        if role in ('worker', 'middleman') and request.user.has_role(role):
            request.user.active_role = role
            request.user.save(update_fields=['active_role'])
            messages.success(request, f"Switched to {role.title()} view.")
        else:
            messages.error(request, "Invalid role switch.")
    return redirect('dashboard')


@login_required
def profile(request):
    if request.method == 'POST' and request.FILES.get('avatar'):
        from PIL import Image
        from io import BytesIO
        from django.core.files.uploadedfile import InMemoryUploadedFile

        img = Image.open(request.FILES['avatar'])
        img = img.convert('RGB')

        # Center-crop to square
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        img = img.crop((left, top, left + side, top + side))

        # Resize to 200x200
        img = img.resize((200, 200), Image.LANCZOS)

        # Save to buffer
        buf = BytesIO()
        img.save(buf, format='JPEG', quality=85)
        buf.seek(0)

        filename = f'{request.user.id}.jpg'
        request.user.avatar.save(
            filename,
            InMemoryUploadedFile(buf, 'avatar', filename, 'image/jpeg', buf.getbuffer().nbytes, None),
            save=True,
        )
        messages.success(request, "Profile picture updated.")
        return redirect('profile')

    return render(request, 'registration/profile.html')


@login_required
def change_password(request):
    if request.method == 'POST':
        from django.contrib.auth import update_session_auth_hash
        current = request.POST.get('current_password', '')
        new = request.POST.get('new_password', '')
        confirm = request.POST.get('confirm_password', '')

        if not request.user.check_password(current):
            messages.error(request, "Current password is incorrect.")
        elif new != confirm:
            messages.error(request, "New passwords don't match.")
        elif len(new) < 6:
            messages.error(request, "Password must be at least 6 characters.")
        else:
            request.user.set_password(new)
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, "Password changed successfully.")
    return redirect('profile')


# User management (admin only)

@login_required
def user_list(request):
    if not request.user.is_admin_user():
        messages.error(request, "Admin access required.")
        return redirect('dashboard')
    from .models import User
    users = User.objects.prefetch_related('roles').all()
    return render(request, 'users/list.html', {'users': users})


@login_required
def user_create(request):
    if not request.user.is_admin_user():
        messages.error(request, "Admin access required.")
        return redirect('dashboard')
    from .models import User, UserRole

    if request.method == 'POST':
        username = request.POST['username']
        email = request.POST.get('email', '')
        password = request.POST['password']
        selected_roles = request.POST.getlist('roles')

        if not selected_roles:
            messages.error(request, "Select at least one role.")
            return render(request, 'users/form.html', {'user_obj': None})

        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' already exists.")
            return render(request, 'users/form.html', {'user_obj': None})

        user = User.objects.create_user(username=username, email=email, password=password)
        user.active_role = selected_roles[0]
        user.save()

        for role in selected_roles:
            UserRole.objects.create(user=user, role=role)

        if 'worker' in selected_roles:
            Worker.objects.create(
                worker_code=_next_code(Worker, 'W'),
                name=username, contact=email, user=user,
            )
        if 'middleman' in selected_roles:
            Middleman.objects.create(
                middleman_code=_next_code(Middleman, 'M'),
                name=username, email=email, user=user,
            )

        messages.success(request, f"User '{username}' created.")
        return redirect('user_list')

    return render(request, 'users/form.html', {'user_obj': None})


@login_required
def user_detail(request, pk):
    if not request.user.is_admin_user():
        return redirect('dashboard')
    from .models import User
    user_obj = get_object_or_404(User.objects.prefetch_related('roles'), pk=pk)
    return render(request, 'users/detail.html', {
        'user_obj': user_obj,
        'worker': getattr(user_obj, 'worker_profile', None),
        'middleman': getattr(user_obj, 'middleman_profile', None),
    })


@login_required
def user_edit(request, pk):
    if not request.user.is_admin_user():
        return redirect('dashboard')
    from .models import User
    user_obj = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        user_obj.email = request.POST.get('email', '')
        user_obj.is_active = request.POST.get('is_active') == 'on'
        user_obj.save()

        selected_roles = request.POST.getlist('roles')
        if selected_roles:
            current_roles = set(user_obj.roles.values_list('role', flat=True))
            new_roles = set(selected_roles)

            # Add new roles
            for role in new_roles - current_roles:
                UserRole.objects.create(user=user_obj, role=role)
                if role == 'worker' and not hasattr(user_obj, 'worker_profile'):
                    Worker.objects.create(
                        worker_code=_next_code(Worker, 'W'),
                        name=user_obj.username, contact=user_obj.email, user=user_obj,
                    )
                elif role == 'middleman' and not hasattr(user_obj, 'middleman_profile'):
                    Middleman.objects.create(
                        middleman_code=_next_code(Middleman, 'M'),
                        name=user_obj.username, email=user_obj.email, user=user_obj,
                    )

            # Remove old roles
            user_obj.roles.filter(role__in=current_roles - new_roles).delete()

            # Update active_role if it was removed
            if user_obj.active_role not in new_roles:
                user_obj.active_role = selected_roles[0]
                user_obj.save()

        messages.success(request, f"User '{user_obj.username}' updated.")
        return redirect('user_detail', pk=pk)
    return render(request, 'users/form.html', {'user_obj': user_obj})


# ──────────────────────────────────────────────
# Phase 7: Role-based filtering helpers
# ──────────────────────────────────────────────

def get_visible_jobs(user):
    """Return a queryset of jobs visible to this user based on their active role."""
    base = Job.objects.exclude(status='archived')
    if user.is_admin_user():
        return base
    if user.active_role == 'worker':
        worker = getattr(user, 'worker_profile', None)
        if not worker:
            return Job.objects.none()
        job_ids = set(
            JobAllocation.objects.filter(worker=worker).values_list('job_id', flat=True)
        ) | set(
            Payment.objects.filter(worker=worker).values_list('job_id', flat=True)
        )
        return base.filter(id__in=job_ids)
    if user.active_role == 'middleman':
        middleman = getattr(user, 'middleman_profile', None)
        if middleman:
            return base.filter(Q(created_by=user) | Q(middleman=middleman)).distinct()
        return base.filter(created_by=user)
    return Job.objects.none()


# ──────────────────────────────────────────────
# Phase 8: Expenses
# ──────────────────────────────────────────────

from .models import Expense


@login_required
def expense_list(request):
    if not request.user.is_admin_user() and request.user.active_role == 'worker':
        messages.error(request, "Access restricted.")
        return redirect('dashboard')

    expenses = Expense.objects.all()
    if not request.user.is_admin_user() and request.user.active_role == 'middleman':
        expenses = expenses.filter(created_by=request.user)

    category = request.GET.get('category')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if category:
        expenses = expenses.filter(category=category)
    if date_from:
        expenses = expenses.filter(expense_date__gte=date_from)
    if date_to:
        expenses = expenses.filter(expense_date__lte=date_to)

    total = expenses.aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    return render(request, 'expenses/list.html', {
        'expenses': expenses, 'total': total,
        'categories': Expense.Category.choices,
        'filters': {'category': category, 'date_from': date_from, 'date_to': date_to},
    })


@login_required
def expense_create(request):
    if request.method == 'POST':
        Expense.objects.create(
            expense_code=_next_code(Expense, 'E', pad=3),
            expense_date=request.POST['expense_date'],
            amount=request.POST['amount'],
            category=request.POST.get('category', 'other'),
            description=request.POST['description'],
            vendor=request.POST.get('vendor', ''),
            reference=request.POST.get('reference', ''),
            notes=request.POST.get('notes', ''),
            created_by=request.user,
        )
        messages.success(request, "Expense recorded.")
        return redirect('expense_list')
    return render(request, 'expenses/form.html', {'expense': None, 'categories': Expense.Category.choices})


@login_required
def expense_detail(request, pk):
    return render(request, 'expenses/detail.html', {'expense': get_object_or_404(Expense, pk=pk)})


@login_required
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        expense.expense_date = request.POST['expense_date']
        expense.amount = request.POST['amount']
        expense.category = request.POST.get('category', expense.category)
        expense.description = request.POST['description']
        expense.vendor = request.POST.get('vendor', '')
        expense.reference = request.POST.get('reference', '')
        expense.notes = request.POST.get('notes', '')
        expense.save()
        messages.success(request, "Expense updated.")
        return redirect('expense_detail', pk=pk)
    return render(request, 'expenses/form.html', {'expense': expense, 'categories': Expense.Category.choices})


@login_required
def expense_delete(request, pk):
    if request.method == 'POST':
        get_object_or_404(Expense, pk=pk).delete()
        messages.success(request, "Expense deleted.")
    return redirect('expense_list')


@login_required
def expense_tracking(request):
    from datetime import date, timedelta
    from .services.calculations import get_owner_earnings_for_period

    date_to = date.today()
    date_from = date_to - timedelta(days=30)
    if request.GET.get('date_from'):
        date_from = date.fromisoformat(request.GET['date_from'])
    if request.GET.get('date_to'):
        date_to = date.fromisoformat(request.GET['date_to'])

    total_expenses = Expense.objects.filter(
        expense_date__gte=date_from, expense_date__lte=date_to
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    total_earnings = Receipt.objects.filter(
        received_date__gte=date_from, received_date__lte=date_to
    ).aggregate(s=Sum('amount_received'))['s'] or Decimal('0.00')
    owner_earnings = get_owner_earnings_for_period(date_from, date_to)
    profit = owner_earnings - total_expenses
    margin = (profit / owner_earnings * 100) if owner_earnings > 0 else Decimal(0)

    # Chart data — daily breakdown
    from datetime import timedelta as td
    chart_labels = []
    chart_expenses = []
    chart_earnings = []
    current = date_from
    while current <= date_to:
        chart_labels.append(current.strftime('%b %d'))
        day_exp = Expense.objects.filter(expense_date=current).aggregate(s=Sum('amount'))['s'] or 0
        day_earn = Receipt.objects.filter(received_date=current).aggregate(s=Sum('amount_received'))['s'] or 0
        chart_expenses.append(float(day_exp))
        chart_earnings.append(float(day_earn))
        current += td(days=1)

    return render(request, 'expenses/tracking.html', {
        'date_from': date_from, 'date_to': date_to,
        'total_expenses': total_expenses, 'total_earnings': total_earnings,
        'owner_earnings': owner_earnings, 'profit': profit, 'margin': margin,
        'chart_labels': json.dumps(chart_labels),
        'chart_expenses': json.dumps(chart_expenses),
        'chart_earnings': json.dumps(chart_earnings),
    })


# ──────────────────────────────────────────────
# Phase 9: Archive actions
# ──────────────────────────────────────────────

@login_required
def worker_invoice(request, pk):
    worker = get_object_or_404(Worker, pk=pk)
    wt = compute_worker_totals(worker)
    distributions = ReceiptDistribution.objects.filter(
        worker=worker
    ).select_related('receipt__job').order_by('-receipt__received_date')

    # Try WeasyPrint PDF, fall back to HTML
    try:
        from weasyprint import HTML
        from django.template.loader import render_to_string
        html_string = render_to_string('workers/invoice.html', {
            'worker': worker, 'totals': wt, 'distributions': distributions,
        })
        from django.http import HttpResponse
        pdf = HTML(string=html_string).write_pdf()
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{worker.worker_code}_invoice.pdf"'
        return response
    except ImportError:
        return render(request, 'workers/invoice.html', {
            'worker': worker, 'totals': wt, 'distributions': distributions,
        })


@login_required
def worker_archive(request, pk):
    if request.method == 'POST':
        w = get_object_or_404(Worker, pk=pk)
        w.is_archived = True
        w.save()
        messages.success(request, f"Worker {w.worker_code} archived.")
    return redirect('team_roster')


@login_required
def client_archive(request, pk):
    if request.method == 'POST':
        c = get_object_or_404(Client, pk=pk)
        c.is_archived = True
        c.save()
        messages.success(request, f"Client {c.client_code} archived.")
    return redirect('client_list')


# ──────────────────────────────────────────────
# Reports: P&L and Ledger
# ──────────────────────────────────────────────

def _parse_report_dates(request):
    """Parse date_from/date_to from GET params, default to last 30 days."""
    from datetime import date, timedelta
    date_to = date.today()
    date_from = date_to - timedelta(days=30)
    if request.GET.get('date_from'):
        date_from = date.fromisoformat(request.GET['date_from'])
    if request.GET.get('date_to'):
        date_to = date.fromisoformat(request.GET['date_to'])
    return date_from, date_to


@login_required
def pnl_report(request):
    if request.user.active_role == 'worker' and not request.user.is_admin_user():
        messages.info(request, "P&L reports are not available for worker accounts.")
        return redirect('dashboard')

    date_from, date_to = _parse_report_dates(request)
    visible = get_visible_jobs(request.user)
    pnl = get_pnl_data(request.user, date_from, date_to, visible)
    pnl['abs_net_profit'] = abs(pnl['net_profit'])
    return render(request, 'reports/pnl.html', pnl)


@login_required
def pnl_export(request):
    import csv
    from django.http import HttpResponse

    if request.user.active_role == 'worker' and not request.user.is_admin_user():
        return redirect('dashboard')

    date_from, date_to = _parse_report_dates(request)
    visible = get_visible_jobs(request.user)
    pnl = get_pnl_data(request.user, date_from, date_to, visible)
    rows = pnl_to_csv_rows(pnl)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="pnl_{date_from}_{date_to}.csv"'
    writer = csv.writer(response)
    for row in rows:
        writer.writerow(row)
    return response


@login_required
def ledger_report(request):
    if request.user.active_role == 'worker' and not request.user.is_admin_user():
        messages.info(request, "Ledger is not available for worker accounts.")
        return redirect('dashboard')

    date_from, date_to = _parse_report_dates(request)
    entry_type = request.GET.get('type') or None
    visible = get_visible_jobs(request.user)
    entries = get_ledger_entries(request.user, date_from, date_to, visible, entry_type)

    # Running balance + absolute amounts for template display
    running = Decimal(0)
    for e in reversed(entries):
        running += e['amount']
        e['balance'] = running
        e['abs_amount'] = abs(e['amount'])
        e['abs_balance'] = abs(running)

    return render(request, 'reports/ledger.html', {
        'date_from': date_from,
        'date_to': date_to,
        'entry_type': entry_type or '',
        'entries': entries,
        'is_admin': request.user.is_admin_user(),
    })


@login_required
def ledger_export(request):
    import csv
    from django.http import HttpResponse

    if request.user.active_role == 'worker' and not request.user.is_admin_user():
        return redirect('dashboard')

    date_from, date_to = _parse_report_dates(request)
    entry_type = request.GET.get('type') or None
    visible = get_visible_jobs(request.user)
    entries = get_ledger_entries(request.user, date_from, date_to, visible, entry_type)
    rows = ledger_to_csv_rows(entries)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="ledger_{date_from}_{date_to}.csv"'
    writer = csv.writer(response)
    for row in rows:
        writer.writerow(row)
    return response
