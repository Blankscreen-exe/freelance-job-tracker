# Django Migration — Remaining Work

Gap analysis: what the FastAPI app has that the Django app is still missing.

---

## Phase 1: Missing Model Fields

### 1.1 Client Model — Add ~25 missing fields
- Source info: `source_url`, `source_notes`
- Primary contact: `contact_person`, `mobile`
- Alt contacts: `alternative_email`, `alternative_phone`, `telegram`, `whatsapp`, `skype`, `linkedin`, `other_contact`
- Company info: `company_name`, `company_registration`, `company_website`, `company_email`
- Address: `address_line1`, `address_line2`, `city`, `state_province`, `postal_code`, `country`, `timezone`
- Extra: `industry`, `company_size`, `preferred_communication`, `working_hours`, `internal_notes`, `tags`, `is_active`, `last_contacted`

### 1.2 Job Model — Add missing fields
- `source` (JobSource enum: UPWORK/FREELANCER/LINKEDIN/FIVERR/DIRECT/OTHER)
- `client_name` (legacy/fallback text field)
- `description` (HTML/text)
- `cover_letter` (HTML/text)
- `connects_used` (integer)
- Company fields: `company_name`, `company_website`, `company_email`, `company_phone`, `company_address`, `client_notes`

### 1.3 Worker Model
- Add `is_owner` boolean (marks admin's own worker entity)

### 1.4 Payment Model
- Add `is_auto_generated` boolean (flag for auto-created payments)
- Add `is_paid` boolean (paid/unpaid status)

### 1.5 Receipt Model
- Add `selected_allocation_ids` (JSON — which allocations this receipt distributes to)
- Add `use_custom_allocations` (boolean)
- Add `custom_allocations` (JSON — override allocations for this specific receipt)

### 1.6 New: Expense Model (entirely missing)
- `expense_code` (unique, E001 etc.)
- `expense_date`, `amount` (Decimal), `category` (ExpenseCategory enum), `description`, `vendor`, `reference`, `notes`
- ExpenseCategory enum: CONNECTS, TOOLS, SOFTWARE, SUBSCRIPTION, MARKETING, OFFICE, OTHER

### 1.7 New: JobSource Enum
- UPWORK, FREELANCER, LINKEDIN, FIVERR, DIRECT, OTHER

---

## Phase 2: Business Logic / Services

### 2.1 Calculation Service (`core/services/calculations.py`)
- `get_job_totals(job)` — total_received, connect_deduction, platform_fee, net_distributable
- `compute_allocations(job)` — per-allocation earned amounts (percent or fixed of net_distributable)
- `compute_worker_totals(worker)` — earned, paid, due
- `get_dashboard_totals()` — aggregate totals for dashboard
- `get_earnings_for_period(start, end)` — sum receipts in date range
- `get_owner_earnings_for_period(start, end)` — sum owner allocations in date range

### 2.2 Payment Generator (`core/services/payment_generator.py`)
- `generate_payments_from_receipt(receipt)` — auto-create Payment records when receipt is added
  - Supports predefined allocations (selected or all)
  - Supports custom allocations (JSON overrides)
  - Distributes connect cost and platform fee proportionally across workers

### 2.3 Expense Calculations (`core/services/expense_calculations.py`)
- `get_expense_totals(start, end)` — sum expenses in date range
- `get_expenses_by_month(year, month)` — monthly breakdown
- `get_expense_chart_data(start, end)` — Chart.js data (daily/monthly)
- `calculate_profit(start, end)` — owner_earnings - expenses
- `calculate_margin(start, end)` — (profit / owner_earnings) * 100

---

## Phase 3: Missing Routes / Views

### 3.1 Auth & Profile
- [ ] `POST /auth/switch-role/` — switch active role between Worker/Middleman
- [ ] `GET /profile/` — user profile page
- [ ] `POST /profile/change-password/` — change own password

### 3.2 User Management (Admin only)
- [ ] `GET /users/` — list all users
- [ ] `GET /users/new/` + `POST` — create user (auto-creates Worker + Middleman entities)
- [ ] `GET /users/<id>/` — user detail
- [ ] `GET /users/<id>/edit/` + `POST` — edit user

### 3.3 Receipt CRUD (nested under jobs)
- [ ] `POST /jobs/<id>/receipts/new/` — create receipt (with allocation selection)
- [ ] `GET /receipts/<id>/edit/` + `POST` — edit receipt
- [ ] `POST /receipts/<id>/delete/` — delete receipt

### 3.4 Allocation CRUD (nested under jobs)
- [ ] `POST /jobs/<id>/allocations/new/` — create allocation
- [ ] `GET /allocations/<id>/edit/` + `POST` — edit allocation
- [ ] `POST /allocations/<id>/delete/` — delete allocation

### 3.5 Job Actions
- [ ] `POST /jobs/<id>/archive/` — archive (soft delete)
- [ ] `POST /jobs/<id>/finalize/` — create calculation snapshot
- [ ] `POST /jobs/<id>/unfinalize/` — remove snapshot, re-enable edits

### 3.6 Client Actions
- [ ] `POST /clients/<id>/archive/` — archive (soft delete)

### 3.7 Worker Actions
- [ ] `POST /workers/<id>/archive/` — archive (soft delete)
- [ ] `GET /workers/<id>/invoice/` — generate PDF invoice (WeasyPrint)

### 3.8 Payment Enhancements
- [ ] `GET /payments/<id>/edit/` + `POST` — edit payment
- [ ] `POST /payments/<id>/delete/` — delete payment
- [ ] `POST /payments/<id>/mark-paid/` — mark as paid
- [ ] `POST /payments/<id>/mark-unpaid/` — mark as unpaid
- [ ] Add date/worker/job filters to payment list

### 3.9 Settings Enhancements
- [ ] `GET /settings/<id>/clone/` + `POST` — clone settings version

### 3.10 Expenses Module (entirely missing)
- [ ] `GET /expenses/` — list with date/category filters
- [ ] `GET /expenses/new/` + `POST` — create expense
- [ ] `GET /expenses/<id>/` — expense detail
- [ ] `GET /expenses/<id>/edit/` + `POST` — edit expense
- [ ] `POST /expenses/<id>/delete/` — delete expense
- [ ] `GET /expenses/tracking/` — tracking dashboard with Chart.js analytics

---

## Phase 4: Missing Templates

- [ ] `home.html` — public landing page
- [ ] `auth/profile.html` — user profile + password change
- [ ] `receipts/form.html` — receipt create/edit
- [ ] `allocations/form.html` — allocation create/edit
- [ ] `users/list.html` — user list (admin)
- [ ] `users/form.html` — user create/edit (admin)
- [ ] `users/detail.html` — user detail (admin)
- [ ] `expenses/list.html` — expense list with filters
- [ ] `expenses/form.html` — expense create/edit
- [ ] `expenses/detail.html` — expense detail
- [ ] `expenses/tracking.html` — expense tracking dashboard with charts
- [ ] `settings/clone_form.html` — clone settings version form
- [ ] `workers/invoice.html` — PDF invoice template
- [ ] `errors/403.html` — forbidden error page

---

## Phase 5: Missing Behaviors

### 5.1 Role-Based Data Filtering
- [ ] Dashboard: Admin=all data, Worker=assigned jobs only, Middleman=created jobs only
- [ ] Job list: filter by role
- [ ] Client list: Admin/Worker see all, Middleman sees own
- [ ] Payment list: filter by role ownership

### 5.2 Auto-Payment Generation
- [ ] When receipt is added → auto-create Payment records for workers based on allocations
- [ ] Support predefined allocations (selected subset or all)
- [ ] Support custom allocations (JSON overrides per receipt)
- [ ] Proportional connect/platform fee distribution

### 5.3 Middleware / Auth
- [ ] Public landing page at `/` (move dashboard to `/dashboard/`)
- [ ] 403 error handler template
- [ ] Session-based role switching

---

## Suggested Implementation Order

1. **Phase 1** — Model fields + migration (foundation for everything else)
2. **Phase 2** — Business logic services (calculations, payment generator)
3. **Phase 3.3–3.4** — Receipt + Allocation CRUD (core job management)
4. **Phase 3.5–3.7** — Archive, finalize, worker invoice
5. **Phase 3.8** — Payment enhancements
6. **Phase 3.1–3.2** — Auth/profile, user management
7. **Phase 3.9–3.10** — Settings clone, Expenses module
8. **Phase 5** — Role-based filtering, auto-payment, middleware
9. **Phase 4** — Remaining templates (built alongside their views)
