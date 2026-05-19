import re
import json
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q, Count
from django.http import HttpResponseBadRequest

from .models import (
    Job, Client, ClientContact, ClientCompany, ClientAddress,
    Middleman, Worker, Payment, Receipt,
    JobAllocation, SettingsVersion, ReceiptDistribution,
    JobCalculationSnapshot, User, UserRole, JobNote,
    Expense, Vendor, ExpenseCategory, MagicLinkToken,
)
from .services.calculations import (
    get_job_totals, compute_allocations, compute_worker_totals,
    get_dashboard_totals, get_receipt_deductions, compute_receipt_distributions,
    recompute_expense_coverage,
)
from .services.payment_generator import generate_payments_from_receipt
from .services.reports import get_pnl_data, get_ledger_entries, pnl_to_csv_rows, ledger_to_csv_rows
from .services.email import send_invitation, send_magic_link


def _send_invitation_quietly(request, email, username, password):
    """Fire an invitation email; silently swallow failures so user creation is never blocked."""
    from django.conf import settings as django_settings
    try:
        login_url = request.build_absolute_uri('/login/')
        app_name = getattr(django_settings, 'APP_NAME', 'Job Tracker')
        send_invitation(to=email, username=username, password=password,
                        login_url=login_url, app_name=app_name)
        messages.info(request, f"Invitation email sent to {email}.")
    except Exception as exc:
        messages.warning(request, f"User created, but invitation email could not be sent: {exc}")


# ──────────────────────────────────────────────
# Magic Link Authentication
# ──────────────────────────────────────────────

def magic_link_request(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        try:
            user = User.objects.get(email=email, is_active=True)
            token = MagicLinkToken.create_for_user(user)
            magic_url = request.build_absolute_uri(f'/auth/magic-link/{token.token}/')
            try:
                from django.conf import settings as django_settings
                app_name = getattr(django_settings, 'APP_NAME', 'Job Tracker')
                send_magic_link(to=email, magic_url=magic_url, app_name=app_name,
                                expiry_minutes=MagicLinkToken.EXPIRY_MINUTES)
            except Exception as exc:
                messages.error(request, f"Could not send magic link email: {exc}")
                return render(request, 'registration/magic_link_request.html')
        except User.DoesNotExist:
            pass  # Don't reveal whether the email exists
        messages.success(request, "If that email is registered, you'll receive a login link shortly.")
        return redirect('magic_link_request')
    return render(request, 'registration/magic_link_request.html')


def magic_link_verify(request, token):
    if request.user.is_authenticated:
        return redirect('dashboard')
    try:
        ml_token = MagicLinkToken.objects.select_related('user').get(token=token)
    except MagicLinkToken.DoesNotExist:
        messages.error(request, "Invalid login link.")
        return redirect('login')

    if not ml_token.is_valid():
        messages.error(request, "This login link has expired or already been used.")
        return redirect('login')

    ml_token.is_used = True
    ml_token.save(update_fields=['is_used'])

    from django.contrib.auth import login
    login(request, ml_token.user, backend='django.contrib.auth.backends.ModelBackend')
    return redirect('dashboard')


# ──────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────

@login_required
def dashboard(request):
    visible = get_visible_jobs(request.user)
    active_jobs = visible.filter(status='active').count()
    recent_jobs = visible.select_related('client')[:10]

    my_expenses = Expense.objects.filter(
        created_by=request.user
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

    is_worker = not request.user.is_admin_user() and request.user.active_role == 'worker'

    if is_worker:
        worker = getattr(request.user, 'worker_profile', None)
        if worker:
            wt = compute_worker_totals(worker)
        else:
            wt = {'earned': Decimal('0.00'), 'paid': Decimal('0.00'), 'due': Decimal('0.00')}
        net_position = Decimal(str(wt['earned'])) - my_expenses
        return render(request, 'dashboard.html', {
            'is_worker_view': True,
            'is_middleman_view': False,
            'worker_totals': wt,
            'my_expenses': my_expenses,
            'net_position': net_position,
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
        'my_expenses': my_expenses,
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
    note = JobNote.objects.filter(job=job, user=request.user).first()

    return render(request, 'jobs/detail.html', {
        'job': job,
        'receipts': receipts,
        'allocations': allocations,
        'alloc_display': alloc_display,
        'payments': payments,
        'totals': totals,
        'workers': workers,
        'note': note,
    })


@login_required
def job_note_save(request, pk):
    if request.method != 'POST':
        return redirect('job_detail', pk=pk)
    job = get_object_or_404(Job, pk=pk)
    if not get_visible_jobs(request.user).filter(pk=pk).exists():
        messages.error(request, "You don't have access to this job.")
        return redirect('job_list')
    body = request.POST.get('body', '').strip()
    note, _ = JobNote.objects.get_or_create(job=job, user=request.user)
    note.body = body
    note.save()
    messages.success(request, "Notes saved.")
    return redirect('job_detail', pk=pk)


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

    users_qs = User.objects.filter(is_active=True).prefetch_related(
        'roles', 'worker_profile', 'middleman_profile',
    )

    roster = []
    for u in users_qs:
        worker = getattr(u, 'worker_profile', None)
        middleman = getattr(u, 'middleman_profile', None)

        # Skip both profiles archived (treat as inactive from roster perspective)
        worker_active = worker and not worker.is_archived
        middleman_active = middleman and not middleman.is_archived

        roles = u.get_roles()
        if u.is_superuser and 'admin' not in roles:
            roles = ['admin'] + roles

        if role_filter == 'worker' and not worker_active:
            continue
        if role_filter == 'middleman' and not middleman_active:
            continue
        if role_filter == 'admin' and not u.is_admin_user():
            continue

        name = (worker.name if worker_active else None) \
            or (middleman.name if middleman_active else None) \
            or u.username

        if search and search.lower() not in name.lower():
            continue

        contact = (worker.contact if worker_active and worker.contact else None) \
            or (middleman.email or middleman.phone if middleman_active else None) \
            or '-'

        codes = []
        if worker_active:
            codes.append(('worker', worker.worker_code, worker.pk))
        if middleman_active:
            codes.append(('middleman', middleman.middleman_code, middleman.pk))

        roster.append({
            'user_id': u.pk,
            'username': u.username,
            'name': name,
            'roles': roles,
            'codes': codes,
            'contact': contact,
            'worker': worker if worker_active else None,
            'middleman': middleman if middleman_active else None,
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
    if not request.user.is_admin_user():
        messages.error(request, "Access restricted.")
        return redirect('team_roster')
    return _person_create(
        request,
        kind='middleman',
        Model=Middleman,
        code_prefix='M',
        profile_attr='middleman_profile',
        role_value=User.Role.MIDDLEMAN,
        form_template='middlemen/form.html',
        detail_url_name='middleman_detail',
    )


@login_required
def middleman_edit(request, pk):
    if not request.user.is_admin_user() and request.user.active_role != 'middleman':
        messages.error(request, "Access restricted.")
        return redirect('team_roster')
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
    if not request.user.is_admin_user() and request.user.active_role != 'middleman':
        messages.error(request, "Access restricted.")
        return redirect('team_roster')
    return _person_create(
        request,
        kind='worker',
        Model=Worker,
        code_prefix='W',
        profile_attr='worker_profile',
        role_value=User.Role.WORKER,
        form_template='workers/form.html',
        detail_url_name='worker_detail',
    )


def _person_create(request, *, kind, Model, code_prefix, profile_attr, role_value, form_template, detail_url_name):
    """Shared create flow for Worker / Middleman. Always provisions a User (link or create)."""
    import secrets

    # Users available to be linked: those without this kind of profile yet.
    available_users = User.objects.filter(**{f'{profile_attr}__isnull': True}).order_by('username')

    _FORM_DEFAULTS = {
        'name': '', 'contact': '', 'notes': '', 'email': '', 'phone': '',
        'login_mode': '', 'existing_user_id': '', 'new_username': '',
        'new_email': '', 'password_mode': 'auto', 'new_password': '',
        'is_owner': False,
    }

    def _form_ctx(form_data=None):
        ctx = {
            kind: None,
            'available_users': available_users,
            'form': form_data if form_data is not None else _FORM_DEFAULTS,
        }
        # The legacy templates also check `worker`/`middleman` truthiness; keep both keys.
        return ctx

    if request.method != 'POST':
        return render(request, form_template, _form_ctx())

    post = request.POST
    form_data = {k: post.get(k, '') for k in (
        'name', 'contact', 'notes', 'email', 'phone',
        'login_mode', 'existing_user_id',
        'new_username', 'new_email', 'password_mode', 'new_password',
    )}
    form_data['is_owner'] = post.get('is_owner') == 'on'

    name = post.get('name', '').strip()
    if not name:
        messages.error(request, "Name is required.")
        return render(request, form_template, _form_ctx(form_data))

    login_mode = post.get('login_mode', '')
    linked_user = None
    plaintext_password = None  # set only when auto-generating

    if login_mode == 'link':
        user_id = post.get('existing_user_id')
        if not user_id:
            messages.error(request, "Select a user to link.")
            return render(request, form_template, _form_ctx(form_data))
        try:
            linked_user = User.objects.get(pk=user_id, **{f'{profile_attr}__isnull': True})
        except User.DoesNotExist:
            messages.error(request, "Selected user is not available.")
            return render(request, form_template, _form_ctx(form_data))
        if not linked_user.roles.filter(role=role_value).exists():
            UserRole.objects.create(user=linked_user, role=role_value)

    elif login_mode == 'create':
        username = post.get('new_username', '').strip()
        email = post.get('new_email', '').strip()
        password_mode = post.get('password_mode', 'auto')
        if not username:
            messages.error(request, "Username is required.")
            return render(request, form_template, _form_ctx(form_data))
        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' already exists.")
            return render(request, form_template, _form_ctx(form_data))
        if password_mode == 'custom':
            pw = post.get('new_password', '')
            if not pw:
                messages.error(request, "Password is required.")
                return render(request, form_template, _form_ctx(form_data))
        else:
            pw = secrets.token_urlsafe(9)
            plaintext_password = pw
        linked_user = User.objects.create_user(username=username, email=email, password=pw)
        linked_user.active_role = role_value
        linked_user.save()
        UserRole.objects.create(user=linked_user, role=role_value)
        if email:
            _send_invitation_quietly(request, email, username, pw)

    else:
        messages.error(request, "Choose how to set up the login account.")
        return render(request, form_template, _form_ctx(form_data))

    if kind == 'worker':
        person = Worker.objects.create(
            worker_code=_next_code(Worker, code_prefix),
            name=name,
            contact=post.get('contact', ''),
            notes=post.get('notes', ''),
            is_owner=post.get('is_owner') == 'on',
            user=linked_user,
        )
        label = f"Worker {person.worker_code}"
    else:
        person = Middleman.objects.create(
            middleman_code=_next_code(Middleman, code_prefix),
            name=name,
            email=post.get('email', ''),
            phone=post.get('phone', ''),
            contact=post.get('contact', ''),
            notes=post.get('notes', ''),
            user=linked_user,
        )
        label = f"Middleman {person.middleman_code}"

    messages.success(request, f"{label} created.")

    if plaintext_password:
        return render(request, 'team/credentials.html', {
            'kind_label': kind.title(),
            'subject_name': person.name,
            'subject_pk': person.pk,
            'detail_url_name': detail_url_name,
            'username': linked_user.username,
            'password': plaintext_password,
        })

    return redirect(detail_url_name, pk=person.pk)


@login_required
def worker_edit(request, pk):
    worker = get_object_or_404(Worker, pk=pk)
    if not request.user.is_admin_user() and request.user.active_role != 'middleman':
        # Workers may only edit their own profile
        own_worker = getattr(request.user, 'worker_profile', None)
        if not own_worker or own_worker.pk != worker.pk:
            messages.error(request, "Access restricted.")
            return redirect('team_roster')
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
            amount=request.POST['amount_paid'],
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
        payment.amount = request.POST['amount_paid']
        payment.paid_date = request.POST['paid_date']
        payment.method = request.POST.get('method', '')

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
        worker = payment.worker
        was_paid = payment.is_paid
        payment.delete()
        if was_paid:
            recompute_expense_coverage(worker)
        messages.success(request, "Payment deleted.")
    return redirect('payment_list')


@login_required
def payment_mark_paid(request, pk):
    if request.method == 'POST':
        payment = get_object_or_404(Payment, pk=pk)
        payment.is_paid = True
        payment.save()
        recompute_expense_coverage(payment.worker)
        messages.success(request, f"Payment {payment.payment_code} marked as paid.")
    return redirect(request.POST.get('next', 'payment_list'))


@login_required
def payment_mark_unpaid(request, pk):
    if request.method == 'POST':
        payment = get_object_or_404(Payment, pk=pk)
        payment.is_paid = False
        payment.save()
        recompute_expense_coverage(payment.worker)
        messages.success(request, f"Payment {payment.payment_code} marked as unpaid.")
    return redirect(request.POST.get('next', 'payment_list'))


# ──────────────────────────────────────────────
# Settings Versions
# ──────────────────────────────────────────────

def _admin_required(request):
    if not request.user.is_admin_user():
        messages.error(request, "Admin access required.")
        return redirect('dashboard')
    return None


@login_required
def settings_list(request):
    r = _admin_required(request)
    if r: return r
    versions = SettingsVersion.objects.all()
    return render(request, 'settings/list.html', {'versions': versions})


@login_required
def settings_detail(request, pk):
    r = _admin_required(request)
    if r: return r
    version = get_object_or_404(SettingsVersion, pk=pk)
    return render(request, 'settings/detail.html', {'version': version})


@login_required
def settings_create(request):
    r = _admin_required(request)
    if r: return r
    if request.method == 'POST':
        rules = {
            'currency_default': request.POST.get('currency_default', 'USD'),
            'platform_fee': {
                'enabled': request.POST.get('platform_fee_enabled') == 'on',
                'mode': request.POST.get('platform_fee_mode', 'percent'),
                'value': float(request.POST.get('platform_fee_value', 0)),
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
    r = _admin_required(request)
    if r: return r
    if request.method == 'POST':
        SettingsVersion.objects.update(is_active=False)
        sv = get_object_or_404(SettingsVersion, pk=pk)
        sv.is_active = True
        sv.save()
        messages.success(request, f"'{sv.name}' is now the active settings version.")
    return redirect('settings_list')


@login_required
def settings_clone(request, pk):
    r = _admin_required(request)
    if r: return r
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


@login_required
def branding_settings(request):
    if not request.user.is_admin_user():
        return redirect('dashboard')
    from .models import AppSettings
    branding = AppSettings.get()
    if request.method == 'POST':
        branding.app_name = request.POST.get('app_name', branding.app_name)
        branding.footer_text = request.POST.get('footer_text', '')
        branding.show_footer = request.POST.get('show_footer') == 'on'
        branding.primary_color_light = request.POST.get('primary_color_light', '#0d6efd')
        branding.accent_color_light = request.POST.get('accent_color_light', '#6c757d')
        branding.primary_color_dark = request.POST.get('primary_color_dark', '#0d6efd')
        branding.accent_color_dark = request.POST.get('accent_color_dark', '#6c757d')
        branding.sidebar_bg_light = request.POST.get('sidebar_bg_light', '#212529')
        branding.sidebar_text_light = request.POST.get('sidebar_text_light', '#adb5bd')
        branding.topbar_bg_light = request.POST.get('topbar_bg_light', '#212529')
        branding.sidebar_bg_dark = request.POST.get('sidebar_bg_dark', '#1a1d21')
        branding.sidebar_text_dark = request.POST.get('sidebar_text_dark', '#adb5bd')
        branding.topbar_bg_dark = request.POST.get('topbar_bg_dark', '#1a1d21')
        branding.login_bg_color = request.POST.get('login_bg_color', '#212529')
        branding.default_theme = request.POST.get('default_theme', 'dark')
        if request.FILES.get('logo'):
            branding.logo = request.FILES['logo']
        if request.POST.get('clear_logo'):
            branding.logo = None
        if request.FILES.get('favicon'):
            branding.favicon = request.FILES['favicon']
        if request.POST.get('clear_favicon'):
            branding.favicon = None
        if request.FILES.get('login_bg_image'):
            branding.login_bg_image = request.FILES['login_bg_image']
        if request.POST.get('clear_login_bg_image'):
            branding.login_bg_image = None
        branding.save()
        messages.success(request, "Branding settings updated.")
        return redirect('branding_settings')
    return render(request, 'settings/branding.html', {'branding': branding})


@login_required
def smtp_settings(request):
    if not request.user.is_admin_user():
        return redirect('dashboard')
    from .models import SmtpSettings
    smtp = SmtpSettings.get()
    if request.method == 'POST':
        smtp.is_enabled = request.POST.get('is_enabled') == 'on'
        smtp.host = request.POST.get('host', '').strip()
        smtp.port = int(request.POST.get('port') or 587)
        smtp.username = request.POST.get('username', '').strip()
        pw = request.POST.get('password', '')
        if pw:
            smtp.password = pw
        smtp.use_tls = request.POST.get('use_tls') == 'on'
        smtp.use_ssl = request.POST.get('use_ssl') == 'on'
        smtp.from_email = request.POST.get('from_email', '').strip()
        smtp.from_name = request.POST.get('from_name', '').strip()
        smtp.save()
        messages.success(request, "SMTP settings saved.")
        return redirect('smtp_settings')
    return render(request, 'settings/smtp.html', {'smtp': smtp})


@login_required
def smtp_test(request):
    if not request.user.is_admin_user():
        return redirect('dashboard')
    if request.method == 'POST':
        to_email = request.POST.get('test_email', '').strip()
        if not to_email:
            messages.error(request, "Enter a recipient email address.")
            return redirect('smtp_settings')
        try:
            from .services.email import send_email
            from .models import AppSettings
            app_name = AppSettings.get().app_name
            send_email(
                to=to_email,
                subject=f'Test Email from {app_name}',
                body=f'This is a test email sent from {app_name} to confirm your SMTP configuration is working.',
            )
            messages.success(request, f"Test email sent to {to_email}.")
        except Exception as e:
            messages.error(request, f"Failed: {e}")
    return redirect('smtp_settings')


# ──────────────────────────────────────────────
# Receipts
# ──────────────────────────────────────────────

@login_required
def receipt_list(request):
    if not request.user.is_admin_user() and request.user.active_role not in ('admin', 'middleman'):
        messages.error(request, "Access restricted.")
        return redirect('dashboard')

    receipts = Receipt.objects.select_related('job').annotate(
        dist_count=Count('distributions', distinct=True),
    ).order_by('-received_date')

    if not request.user.is_admin_user():
        receipts = receipts.filter(job__in=get_visible_jobs(request.user))

    job_id    = request.GET.get('job')
    source    = request.GET.get('source')
    date_from = request.GET.get('date_from')
    date_to   = request.GET.get('date_to')

    if job_id:
        receipts = receipts.filter(job_id=job_id)
    if source:
        receipts = receipts.filter(source=source)
    if date_from:
        receipts = receipts.filter(received_date__gte=date_from)
    if date_to:
        receipts = receipts.filter(received_date__lte=date_to)

    total = receipts.aggregate(s=Sum('amount_received'))['s'] or Decimal('0.00')

    jobs = Job.objects.exclude(status='archived') if request.user.is_admin_user() \
        else get_visible_jobs(request.user).exclude(status='archived')

    return render(request, 'receipts/list.html', {
        'receipts': receipts,
        'total': total,
        'jobs': jobs,
        'sources': Receipt.Source.choices,
        'filters': {'job': job_id, 'source': source, 'date_from': date_from, 'date_to': date_to},
    })


@login_required
def receipt_new(request):
    """Two-step receipt creation: step 1 pick a job, step 2 fill in the receipt."""
    if not request.user.is_admin_user() and request.user.active_role not in ('admin', 'middleman'):
        messages.error(request, "Access restricted.")
        return redirect('dashboard')

    jobs = get_visible_jobs(request.user).filter(is_finalized=False).order_by('-created_at')

    if request.method == 'POST':
        job = get_object_or_404(Job, pk=request.POST.get('job_pk'))
        if job.is_finalized:
            messages.error(request, "Cannot add receipts to a finalized job.")
            return redirect('receipt_new')

        allocations = job.allocations.select_related('worker').all()
        receipt = Receipt(
            job=job,
            received_date=request.POST['received_date'],
            amount_received=request.POST['amount_received'],
            source=request.POST.get('source', 'milestone'),
            notes=request.POST.get('notes', ''),
        )
        receipt.save()

        use_custom = request.POST.get('use_custom') == 'on'
        if use_custom:
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
            selected_ids = request.POST.getlist('allocation_ids')
            selected = allocations.filter(id__in=selected_ids) if selected_ids else allocations
            alloc_data = [{
                'worker': a.worker,
                'label': a.label,
                'share_type': a.share_type,
                'share_value': str(a.share_value),
            } for a in selected]

        if alloc_data:
            pf = get_receipt_deductions(job, receipt)
            distributions = compute_receipt_distributions(receipt, alloc_data, pf)
            for dist in distributions:
                ReceiptDistribution.objects.create(
                    receipt=receipt,
                    worker=dist['worker'],
                    label=dist['label'],
                    share_type=dist['share_type'],
                    share_value=dist['share_value'],
                    computed_amount=dist['computed_amount'],
                )

        auto_payments = generate_payments_from_receipt(receipt)
        if auto_payments:
            messages.info(request, f"{len(auto_payments)} payment(s) auto-generated.")
        messages.success(request, f"Receipt of ${receipt.amount_received} added.")
        return redirect('job_detail', pk=job.pk)

    # GET — step 1 (no job) or step 2 (job selected)
    job_pk = request.GET.get('job')
    selected_job = None
    allocations = []
    workers = []
    if job_pk:
        selected_job = get_object_or_404(Job, pk=job_pk)
        if selected_job.is_finalized:
            messages.error(request, f"{selected_job.job_code} is finalized and cannot receive new receipts.")
            selected_job = None
        else:
            allocations = selected_job.allocations.select_related('worker').all()
            workers = Worker.objects.filter(is_archived=False)

    return render(request, 'receipts/new.html', {
        'jobs': jobs,
        'selected_job': selected_job,
        'allocations': allocations,
        'workers': workers,
    })


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
            pf = get_receipt_deductions(job, receipt)
            distributions = compute_receipt_distributions(receipt, alloc_data, pf)
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

                pf = get_receipt_deductions(job, receipt)
                new_dists = compute_receipt_distributions(receipt, alloc_data, pf)
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
        next_url = request.POST.get('next') or request.GET.get('next')
        return redirect(next_url if next_url else 'job_detail', pk=job.pk) if not next_url \
            else redirect(next_url)
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
        if email:
            _send_invitation_quietly(request, email, username, password)
        return redirect('user_list')

    return render(request, 'users/form.html', {'user_obj': None})


@login_required
def user_resend_invitation(request, pk):
    import secrets
    if not request.user.is_admin_user():
        messages.error(request, "Admin access required.")
        return redirect('user_list')
    if request.method != 'POST':
        return redirect('user_list')

    target = get_object_or_404(User, pk=pk)
    if not target.email:
        messages.error(request, f"User '{target.username}' has no email address — cannot send invitation.")
        return redirect('user_list')

    new_password = secrets.token_urlsafe(9)
    target.set_password(new_password)
    target.save(update_fields=['password'])

    _send_invitation_quietly(request, target.email, target.username, new_password)
    return redirect('user_list')


@login_required
def user_detail(request, pk):
    if not request.user.is_admin_user():
        return redirect('dashboard')
    user_obj = get_object_or_404(User.objects.prefetch_related('roles'), pk=pk)
    return render(request, 'users/detail.html', {
        'user_obj': user_obj,
        'worker': getattr(user_obj, 'worker_profile', None),
        'middleman': getattr(user_obj, 'middleman_profile', None),
        'is_self': user_obj.pk == request.user.pk,
    })


# ──────────────────────────────────────────────
# Account deletion (self + admin)
# ──────────────────────────────────────────────

def _archive_and_unlink(user_obj):
    """Archive the linked Worker / Middleman profiles and unlink them from the user."""
    worker = getattr(user_obj, 'worker_profile', None)
    if worker:
        worker.is_archived = True
        worker.user = None
        worker.save()
    middleman = getattr(user_obj, 'middleman_profile', None)
    if middleman:
        middleman.is_archived = True
        middleman.user = None
        middleman.save()


@login_required
def account_self_delete(request):
    if request.method != 'POST':
        return redirect('profile')
    if request.user.is_admin_user():
        # Admins delete themselves via the user-management page (with the "last admin" guard).
        messages.error(request, "Admins cannot self-delete from the profile page. Use the User Management page.")
        return redirect('profile')

    if request.POST.get('confirm_username', '').strip() != request.user.username:
        messages.error(request, "Username confirmation didn't match. Account not deleted.")
        return redirect('profile')

    from django.contrib.auth import logout
    user_obj = request.user
    _archive_and_unlink(user_obj)
    username = user_obj.username
    logout(request)
    user_obj.delete()
    messages.success(request, f"Account '{username}' deleted.")
    return redirect('login')


@login_required
def user_delete(request, pk):
    if not request.user.is_admin_user():
        return redirect('dashboard')
    if request.method != 'POST':
        return redirect('user_detail', pk=pk)

    user_obj = get_object_or_404(User, pk=pk)

    if user_obj.pk == request.user.pk:
        messages.error(request, "You cannot delete your own admin account here. Have another admin do it.")
        return redirect('user_detail', pk=pk)

    if user_obj.is_admin_user():
        remaining_admins = User.objects.filter(roles__role=User.Role.ADMIN).exclude(pk=user_obj.pk).count()
        if remaining_admins == 0 and not User.objects.filter(is_superuser=True).exclude(pk=user_obj.pk).exists():
            messages.error(request, "Cannot delete the last admin account.")
            return redirect('user_detail', pk=pk)

    _archive_and_unlink(user_obj)
    username = user_obj.username
    user_obj.delete()
    messages.success(request, f"User '{username}' deleted; their worker/middleman profiles were archived.")
    return redirect('user_list')


@login_required
def user_delete_worker_profile(request, pk):
    if not request.user.is_admin_user():
        return redirect('dashboard')
    if request.method != 'POST':
        return redirect('user_detail', pk=pk)
    user_obj = get_object_or_404(User, pk=pk)
    worker = getattr(user_obj, 'worker_profile', None)
    if not worker:
        messages.error(request, "No worker profile to delete.")
        return redirect('user_detail', pk=pk)

    worker.is_archived = True
    worker.user = None
    worker.save()
    user_obj.roles.filter(role=User.Role.WORKER).delete()
    if user_obj.active_role == User.Role.WORKER:
        remaining = list(user_obj.roles.values_list('role', flat=True))
        user_obj.active_role = remaining[0] if remaining else User.Role.WORKER
        user_obj.save()
    messages.success(request, f"Worker profile for '{user_obj.username}' archived and unlinked.")
    return redirect('user_detail', pk=pk)


@login_required
def user_delete_middleman_profile(request, pk):
    if not request.user.is_admin_user():
        return redirect('dashboard')
    if request.method != 'POST':
        return redirect('user_detail', pk=pk)
    user_obj = get_object_or_404(User, pk=pk)
    middleman = getattr(user_obj, 'middleman_profile', None)
    if not middleman:
        messages.error(request, "No middleman profile to delete.")
        return redirect('user_detail', pk=pk)

    middleman.is_archived = True
    middleman.user = None
    middleman.save()
    user_obj.roles.filter(role=User.Role.MIDDLEMAN).delete()
    if user_obj.active_role == User.Role.MIDDLEMAN:
        remaining = list(user_obj.roles.values_list('role', flat=True))
        user_obj.active_role = remaining[0] if remaining else User.Role.WORKER
        user_obj.save()
    messages.success(request, f"Middleman profile for '{user_obj.username}' archived and unlinked.")
    return redirect('user_detail', pk=pk)


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

@login_required
def expense_list(request):
    expenses = Expense.objects.select_related('created_by', 'vendor').all()

    category = request.GET.get('category')
    vendor_id = request.GET.get('vendor')
    submitted_by = request.GET.get('submitted_by')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if category:
        expenses = expenses.filter(category_id=category)
    if vendor_id:
        expenses = expenses.filter(vendor_id=vendor_id)
    if submitted_by:
        expenses = expenses.filter(created_by_id=submitted_by)
    if date_from:
        expenses = expenses.filter(expense_date__gte=date_from)
    if date_to:
        expenses = expenses.filter(expense_date__lte=date_to)

    total = expenses.aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    total_covered = not expenses.filter(is_paid=False).exists()
    vendors = Vendor.objects.filter(is_archived=False)
    all_users = User.objects.filter(is_active=True).order_by('username') if request.user.is_admin_user() else None

    return render(request, 'expenses/list.html', {
        'expenses': expenses,
        'total': total,
        'total_covered': total_covered,
        'categories': ExpenseCategory.objects.filter(is_archived=False),
        'vendors': vendors,
        'all_users': all_users,
        'filters': {
            'category': category, 'vendor': vendor_id,
            'submitted_by': submitted_by,
            'date_from': date_from, 'date_to': date_to,
        },
    })


@login_required
def expense_create(request):
    if request.method == 'POST':
        vendor_id = request.POST.get('vendor') or None
        if request.user.is_admin_user():
            owner_id = request.POST.get('created_by') or None
            owner = User.objects.filter(pk=owner_id).first() if owner_id else request.user
        else:
            owner = request.user
        Expense.objects.create(
            expense_code=_next_code(Expense, 'E', pad=3),
            expense_date=request.POST['expense_date'],
            amount=request.POST['amount'],
            category_id=request.POST.get('category') or None,
            description=request.POST['description'],
            vendor_id=vendor_id,
            reference=request.POST.get('reference', ''),
            notes=request.POST.get('notes', ''),
            created_by=owner,
        )
        messages.success(request, "Expense recorded.")
        return redirect('expense_list')
    vendors = Vendor.objects.filter(is_archived=False)
    all_users = User.objects.filter(is_active=True).order_by('username') if request.user.is_admin_user() else None
    return render(request, 'expenses/form.html', {
        'expense': None,
        'categories': ExpenseCategory.objects.filter(is_archived=False),
        'vendors': vendors,
        'all_users': all_users,
    })


@login_required
def expense_detail(request, pk):
    return render(request, 'expenses/detail.html', {
        'expense': get_object_or_404(Expense.objects.select_related('created_by', 'vendor'), pk=pk),
    })


@login_required
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if not request.user.is_admin_user() and expense.created_by != request.user:
        messages.error(request, "You can only edit your own expenses.")
        return redirect('expense_list')
    if request.method == 'POST':
        expense.expense_date = request.POST['expense_date']
        expense.amount = request.POST['amount']
        expense.category_id = request.POST.get('category') or None
        expense.description = request.POST['description']
        expense.vendor_id = request.POST.get('vendor') or None
        expense.notes = request.POST.get('notes', '')
        expense.is_paid = 'is_paid' in request.POST
        if request.user.is_admin_user():
            owner_id = request.POST.get('created_by') or None
            if owner_id:
                expense.created_by = User.objects.filter(pk=owner_id).first()
        expense.save()
        messages.success(request, "Expense updated.")
        return redirect('expense_detail', pk=pk)
    vendors = Vendor.objects.filter(is_archived=False)
    all_users = User.objects.filter(is_active=True).order_by('username') if request.user.is_admin_user() else None
    return render(request, 'expenses/form.html', {
        'expense': expense,
        'categories': ExpenseCategory.objects.filter(is_archived=False),
        'vendors': vendors,
        'all_users': all_users,
    })


@login_required
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if not request.user.is_admin_user() and expense.created_by != request.user:
        messages.error(request, "You can only delete your own expenses.")
        return redirect('expense_list')
    if request.method == 'POST':
        expense.delete()
        messages.success(request, "Expense deleted.")
    return redirect('expense_list')


@login_required
def expense_tracking(request):
    from datetime import date, timedelta as td
    from .services.calculations import get_owner_earnings_for_period

    date_to = date.today()
    date_from = date_to - td(days=30)
    if request.GET.get('date_from'):
        date_from = date.fromisoformat(request.GET['date_from'])
    if request.GET.get('date_to'):
        date_to = date.fromisoformat(request.GET['date_to'])

    is_worker = not request.user.is_admin_user() and request.user.active_role == 'worker'

    chart_labels = []
    chart_covered = []
    chart_uncovered = []
    chart_earnings = []

    if is_worker:
        worker_profile = getattr(request.user, 'worker_profile', None)

        my_expenses = Expense.objects.filter(
            created_by=request.user,
            expense_date__gte=date_from, expense_date__lte=date_to,
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

        covered_expenses = Expense.objects.filter(
            created_by=request.user,
            expense_date__gte=date_from, expense_date__lte=date_to,
            is_paid=True,
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

        uncovered_expenses = Expense.objects.filter(
            created_by=request.user,
            expense_date__gte=date_from, expense_date__lte=date_to,
            is_paid=False,
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

        coverage_pct = (covered_expenses / my_expenses * 100) if my_expenses > 0 else Decimal(0)

        my_earnings = Payment.objects.filter(
            worker=worker_profile,
            paid_date__gte=date_from,
            paid_date__lte=date_to,
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00') if worker_profile else Decimal('0.00')

        net = my_earnings - my_expenses

        cat_qs = (
            Expense.objects
            .filter(created_by=request.user, expense_date__gte=date_from, expense_date__lte=date_to)
            .values('category__name')
            .annotate(total=Sum('amount'))
            .order_by('-total')
        )
        category_labels = [row['category__name'] or 'Uncategorized' for row in cat_qs]
        category_data = [float(row['total']) for row in cat_qs]

        current = date_from
        while current <= date_to:
            chart_labels.append(current.strftime('%b %d'))
            day_cov = Expense.objects.filter(
                created_by=request.user, expense_date=current, is_paid=True,
            ).aggregate(s=Sum('amount'))['s'] or 0
            day_uncov = Expense.objects.filter(
                created_by=request.user, expense_date=current, is_paid=False,
            ).aggregate(s=Sum('amount'))['s'] or 0
            day_earn = Payment.objects.filter(
                worker=worker_profile, paid_date=current,
            ).aggregate(s=Sum('amount'))['s'] or 0 if worker_profile else 0
            chart_covered.append(float(day_cov))
            chart_uncovered.append(float(day_uncov))
            chart_earnings.append(float(day_earn))
            current += td(days=1)

        return render(request, 'expenses/tracking.html', {
            'date_from': date_from, 'date_to': date_to,
            'is_personal': True,
            'my_expenses': my_expenses,
            'my_earnings': my_earnings,
            'net': net,
            'covered_expenses': covered_expenses,
            'uncovered_expenses': uncovered_expenses,
            'coverage_pct': coverage_pct,
            'category_labels': json.dumps(category_labels),
            'category_data': json.dumps(category_data),
            'chart_labels': json.dumps(chart_labels),
            'chart_covered': json.dumps(chart_covered),
            'chart_uncovered': json.dumps(chart_uncovered),
            'chart_earnings': json.dumps(chart_earnings),
        })

    # Admin / middleman: agency-wide view
    global_income = Receipt.objects.aggregate(s=Sum('amount_received'))['s'] or Decimal('0.00')
    global_expenses = Expense.objects.aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    global_owner_earnings = get_owner_earnings_for_period()
    global_profit = global_owner_earnings - global_expenses

    total_expenses = Expense.objects.filter(
        expense_date__gte=date_from, expense_date__lte=date_to,
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    total_earnings = Receipt.objects.filter(
        received_date__gte=date_from, received_date__lte=date_to,
    ).aggregate(s=Sum('amount_received'))['s'] or Decimal('0.00')
    owner_earnings = get_owner_earnings_for_period(date_from, date_to)
    # worker payouts in period = total receipts minus owner's share
    worker_payouts = total_earnings - owner_earnings
    profit = owner_earnings - total_expenses
    margin = (profit / owner_earnings * 100) if owner_earnings > 0 else Decimal(0)

    covered_expenses = Expense.objects.filter(
        expense_date__gte=date_from, expense_date__lte=date_to, is_paid=True,
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    uncovered_expenses = Expense.objects.filter(
        expense_date__gte=date_from, expense_date__lte=date_to, is_paid=False,
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    coverage_pct = (covered_expenses / total_expenses * 100) if total_expenses > 0 else Decimal(0)

    cat_qs = (
        Expense.objects
        .filter(expense_date__gte=date_from, expense_date__lte=date_to)
        .values('category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    category_labels = [row['category__name'] or 'Uncategorized' for row in cat_qs]
    category_data = [float(row['total']) for row in cat_qs]

    current = date_from
    while current <= date_to:
        chart_labels.append(current.strftime('%b %d'))
        day_cov = Expense.objects.filter(expense_date=current, is_paid=True).aggregate(s=Sum('amount'))['s'] or 0
        day_uncov = Expense.objects.filter(expense_date=current, is_paid=False).aggregate(s=Sum('amount'))['s'] or 0
        day_earn = Receipt.objects.filter(received_date=current).aggregate(s=Sum('amount_received'))['s'] or 0
        chart_covered.append(float(day_cov))
        chart_uncovered.append(float(day_uncov))
        chart_earnings.append(float(day_earn))
        current += td(days=1)

    return render(request, 'expenses/tracking.html', {
        'date_from': date_from, 'date_to': date_to,
        'is_personal': False,
        'global_income': global_income,
        'global_expenses': global_expenses,
        'global_profit': global_profit,
        'total_expenses': total_expenses,
        'total_earnings': total_earnings,
        'owner_earnings': owner_earnings,
        'worker_payouts': worker_payouts,
        'profit': profit,
        'margin': margin,
        'covered_expenses': covered_expenses,
        'uncovered_expenses': uncovered_expenses,
        'coverage_pct': coverage_pct,
        'category_labels': json.dumps(category_labels),
        'category_data': json.dumps(category_data),
        'chart_labels': json.dumps(chart_labels),
        'chart_covered': json.dumps(chart_covered),
        'chart_uncovered': json.dumps(chart_uncovered),
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
