# User Role System Update Plan

## Overview

This document outlines the changes needed to update the user role system based on clarified requirements. The system will automatically create Worker and Middleman entities for all users, track data ownership via `created_by_user_id`, and implement role-based data filtering.

## Key Changes Summary

1. **Automatic Role Assignment**: All non-admin users automatically get both Worker and Middleman roles
2. **Automatic Entity Creation**: Worker and Middleman entities are auto-created when a user is created
3. **Data Ownership**: Jobs and Clients track ownership via `created_by_user_id`
4. **Role-Based Views**: Different data views based on active role (Worker vs Middleman)
5. **Job Visibility Rules**: Workers see jobs they're assigned to, with special rules for jobs with payment history

---

## 1. Database Schema Changes

### 1.1 Update Job Model (`app/models.py`)

Add `created_by_user_id` field to track job ownership:

```python
class Job(Base):
    # ... existing fields ...
    
    # Ownership tracking
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])
    
    # Keep existing middleman_id for backward compatibility if needed
    # Or remove it if we're fully migrating to created_by_user_id
```

### 1.2 Update Client Model (`app/models.py`)

Add `created_by_user_id` field to track client ownership:

```python
class Client(Base):
    # ... existing fields ...
    
    # Ownership tracking
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])
```

### 1.3 Update Worker Model (`app/models.py`)

Add fields to link to User and make name/email non-editable:

```python
class Worker(Base):
    # ... existing fields ...
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, unique=True)
    user = relationship("User", back_populates="worker")
    
    # Note: name and contact should be synced from User and not directly editable
    # via Worker entity (enforced in application logic)
```

### 1.4 Update Middleman Model (`app/models.py`)

Ensure it has user_id and proper fields:

```python
class Middleman(Base):
    # ... existing fields ...
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, unique=True)
    user = relationship("User", back_populates="middleman")
    
    # Note: name should be synced from User and not directly editable
```

### 1.5 Alembic Migration

Create migration to:
1. Add `created_by_user_id` to `jobs` table
2. Add `created_by_user_id` to `clients` table
3. Ensure `user_id` exists on `workers` and `middlemen` tables
4. Create indexes on `created_by_user_id` fields

---

## 2. User Creation Flow Changes

### 2.1 Update User Creation Form (`app/routers/users.py`)

**Changes:**
- Remove role selection checkboxes for normal users
- Add email field
- Simplify form: only username, email, password
- Auto-assign Worker and Middleman roles
- Auto-create Worker and Middleman entities

**New Form Fields:**
- Username (required, cannot be changed)
- Email (required, can be changed by admin)
- Password (required, can be changed by user)

**Removed:**
- Role checkboxes (Worker/Middleman - auto-assigned)
- Worker/Middleman dropdowns (auto-created)
- Admin checkbox (separate flow or always available)

### 2.2 Update User Creation Logic (`app/routers/users.py`)

```python
@router.post("/users/new")
async def create_user(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    is_admin: bool = Form(False),  # Optional: for creating admin users
    db: Session = Depends(get_db_session),
    _: User = Depends(require_role([AuthUserRole.ADMIN]))
):
    # Create user
    user = User(
        username=username,
        password_hash=hash_password(password),
        is_active=True
    )
    db.add(user)
    db.flush()
    
    # Auto-assign Worker and Middleman roles (unless admin)
    if not is_admin:
        # Assign Worker role
        worker_role = UserRoleAssignment(user_id=user.id, role=UserRole.WORKER)
        db.add(worker_role)
        
        # Assign Middleman role
        middleman_role = UserRoleAssignment(user_id=user.id, role=UserRole.MIDDLEMAN)
        db.add(middleman_role)
        
        # Create Worker entity
        worker = Worker(
            worker_code=generate_worker_code(db),
            name=username,  # Use username as name initially
            contact=email,  # Use email as contact
            user_id=user.id
        )
        db.add(worker)
        
        # Create Middleman entity
        middleman = Middleman(
            middleman_code=generate_middleman_code(db),
            name=username,  # Use username as name initially
            user_id=user.id
        )
        db.add(middleman)
    else:
        # Admin also gets Worker and Middleman entities (for full access)
        admin_role = UserRoleAssignment(user_id=user.id, role=UserRole.ADMIN)
        db.add(admin_role)
        
        # Also create Worker and Middleman entities for admin
        worker = Worker(
            worker_code=generate_worker_code(db),
            name=username,
            contact=email,
            user_id=user.id
        )
        db.add(worker)
        
        middleman = Middleman(
            middleman_code=generate_middleman_code(db),
            name=username,
            user_id=user.id
        )
        db.add(middleman)
    
    db.commit()
    return RedirectResponse(url=f"/users/{user.id}", status_code=303)
```

### 2.3 Add Email Field to User Model (`app/models.py`)

```python
class User(Base):
    # ... existing fields ...
    email = Column(String, nullable=True)  # Add email field
    # ... rest of fields ...
```

---

## 3. Data Ownership & Filtering

### 3.1 Job Creation/Update (`app/routers/jobs.py`)

**When creating a job:**
- Set `created_by_user_id` to current user's ID
- Only Admin and Middleman (in Middleman view) can create jobs
- Workers cannot create jobs

**When updating a job:**
- Only Admin and the user who created it (in Middleman view) can edit
- Workers cannot edit jobs

**Job visibility:**
- **Admin**: See all jobs
- **Worker**: See only jobs where they have allocations OR jobs where they have payment history
- **Middleman**: See only jobs they created (`created_by_user_id == user.id`)

### 3.2 Client Creation/Update (`app/routers/clients.py`)

**When creating a client:**
- Set `created_by_user_id` to current user's ID
- Only Admin and Middleman (in Middleman view) can create clients
- Workers cannot create clients

**When updating a client:**
- Only Admin and the user who created it (in Middleman view) can edit
- Workers cannot edit clients

**Client visibility:**
- **Admin**: See all clients
- **Worker**: See all clients (read-only, for Worker Roster context)
- **Middleman**: See only clients they created (`created_by_user_id == user.id`)

### 3.3 Payment Visibility (`app/routers/payments.py`)

**Payment visibility:**
- **Admin**: See all payments
- **Worker**: See only payments related to jobs they were assigned to (even if allocation removed, if payment exists)
- **Middleman**: See only payments related to jobs they created

### 3.4 Worker Roster Page

Create a new page accessible to all logged-in users:

**Route**: `/workers/roster` or `/workers` (update existing)

**Visibility**: All authenticated users can view

**Content**: List of all workers (not filtered by role)

---

## 4. Job Assignment Rules

### 4.1 Who Can Assign Jobs to Workers

- **Admin**: Can assign any job to any worker
- **Middleman**: Can assign jobs they created to any worker
- **Worker**: Cannot assign jobs

### 4.2 Job Allocation Logic

When creating/updating `JobAllocation`:
- Check if user is Admin OR (user is Middleman AND `job.created_by_user_id == user.id`)
- If not, return 403 Forbidden

### 4.3 Worker Job Visibility Rules

Workers see a job if:
1. They have an active allocation (`JobAllocation.worker_id == user.worker.id`)
2. OR they have payment history for that job (even if allocation was removed)

**Query logic:**
```python
# Get jobs with active allocations
jobs_with_allocations = db.query(Job).join(JobAllocation).filter(
    JobAllocation.worker_id == user.worker.id,
    Job.is_archived == False
).distinct().all()

# Get jobs with payment history (even if allocation removed)
jobs_with_payments = db.query(Job).join(Payment).filter(
    Payment.worker_id == user.worker.id
).distinct().all()

# Combine and deduplicate
all_visible_jobs = list(set(jobs_with_allocations + jobs_with_payments))
```

---

## 5. Role Switching UI

### 5.1 Navbar Dropdown (`templates/base.html`)

Update the role switcher to:
- Show for users with both Worker and Middleman roles
- Display as dropdown in navbar
- Show current active role
- Allow switching between Worker and Middleman views
- Admin users don't need role switcher (they see everything)

**Implementation:**
```html
{% if user_roles|length > 1 and 'admin' not in user_roles %}
<div class="dropdown ms-auto">
    <button class="btn btn-outline-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown">
        <i class="bi bi-arrow-repeat"></i> View: {{ active_role|title }}
    </button>
    <ul class="dropdown-menu dropdown-menu-end">
        {% for role in user_roles %}
        {% if role in ['worker', 'middleman'] %}
        <li>
            <form method="POST" action="/auth/switch-role" style="display: inline;">
                <input type="hidden" name="role" value="{{ role }}">
                <button type="submit" class="dropdown-item {% if role == active_role %}active{% endif %}">
                    <i class="bi bi-{% if role == 'worker' %}person-workspace{% else %}person-badge{% endif %}"></i>
                    {{ role|title }} View
                </button>
            </form>
        </li>
        {% endif %}
        {% endfor %}
    </ul>
</div>
{% endif %}
```

---

## 6. Route Protection Updates

### 6.1 Job Routes (`app/routers/jobs.py`)

**Create Job**: 
- Allowed: Admin, Middleman (in Middleman view)
- Not allowed: Worker

**Edit Job**:
- Allowed: Admin, Middleman who created it
- Not allowed: Worker, other Middlemen

**View Job**:
- Admin: All jobs
- Worker: Jobs they're assigned to or have payment history
- Middleman: Jobs they created

### 6.2 Client Routes (`app/routers/clients.py`)

**Create Client**:
- Allowed: Admin, Middleman (in Middleman view)
- Not allowed: Worker

**Edit Client**:
- Allowed: Admin, Middleman who created it
- Not allowed: Worker, other Middlemen

**View Client**:
- Admin: All clients
- Worker: All clients (read-only)
- Middleman: Clients they created

### 6.3 Payment Routes (`app/routers/payments.py`)

**Create Payment**:
- Allowed: Admin, Middleman (for their jobs)
- Not allowed: Worker

**View Payment**:
- Admin: All payments
- Worker: Payments for their jobs
- Middleman: Payments for their jobs

---

## 7. Dashboard Updates

### 7.1 Worker Dashboard (`app/routers/dashboard.py`)

Show:
- Jobs assigned to them (with allocations)
- Jobs with payment history (even if allocation removed)
- Payment history related to them
- Total earnings
- Paid vs pending payouts

### 7.2 Middleman Dashboard (`app/routers/dashboard.py`)

Show:
- Jobs they created
- Clients they created
- Payments related to their jobs
- Commission earned (when commission system is implemented)
- Commission paid vs pending

### 7.3 Admin Dashboard

Show:
- All data (no filtering)
- Full system overview

---

## 8. Worker/Middleman Entity Management

### 8.1 Prevent Direct Editing

- Worker and Middleman entities should NOT be directly editable via their CRUD pages
- Name and contact should be synced from User entity
- Only Admin can update email (which syncs to Worker.contact)
- Users can update their own password

### 8.2 Sync Logic

When User email is updated:
- Update `Worker.contact` if user has worker entity
- Keep `Worker.name` = `User.username` (immutable)

---

## 9. Implementation Tasks

### Phase 1: Database & Models
1. [ ] Add `email` field to User model
2. [ ] Add `created_by_user_id` to Job model
3. [ ] Add `created_by_user_id` to Client model
4. [ ] Create Alembic migration
5. [ ] Update Worker/Middleman models to ensure proper relationships

### Phase 2: User Creation
6. [ ] Update user creation form (remove role selection, add email)
7. [ ] Update user creation logic (auto-create roles and entities)
8. [ ] Add utility functions for generating Worker/Middleman codes
9. [ ] Update user edit form (email editable by admin only)

### Phase 3: Data Ownership
10. [ ] Update job creation to set `created_by_user_id`
11. [ ] Update client creation to set `created_by_user_id`
12. [ ] Add ownership checks to edit routes
13. [ ] Update job assignment logic (Admin + Middleman only)

### Phase 4: Data Filtering
14. [ ] Update job list route with role-based filtering
15. [ ] Update client list route with role-based filtering
16. [ ] Update payment list route with role-based filtering
17. [ ] Implement worker job visibility rules (allocations + payment history)
18. [ ] Create Worker Roster page (visible to all)

### Phase 5: UI Updates
19. [ ] Update navbar role switcher (better UI)
20. [ ] Update dashboard routes for each role
21. [ ] Update job/client forms to show ownership
22. [ ] Hide Worker/Middleman CRUD pages from normal users

### Phase 6: Testing
23. [ ] Test user creation (auto roles/entities)
24. [ ] Test role switching
25. [ ] Test data filtering for each role
26. [ ] Test job assignment permissions
27. [ ] Test job visibility rules (with/without payments)

---

## 10. Code Generation Utilities

### 10.1 Update `app/utils.py`

Add functions to generate Worker and Middleman codes:

```python
def generate_worker_code(db: Session) -> str:
    """Generate next worker code (W01, W02, etc.)"""
    workers = db.query(Worker).all()
    if not workers:
        return "W01"
    import re
    max_num = 0
    for worker in workers:
        match = re.match(r'W(\d+)', worker.worker_code)
        if match:
            num = int(match.group(1))
            max_num = max(max_num, num)
    return f"W{max_num + 1:02d}"

def generate_middleman_code(db: Session) -> str:
    """Generate next middleman code (M01, M02, etc.)"""
    middlemen = db.query(Middleman).all()
    if not middlemen:
        return "M01"
    import re
    max_num = 0
    for middleman in middlemen:
        match = re.match(r'M(\d+)', middleman.middleman_code)
        if match:
            num = int(match.group(1))
            max_num = max(max_num, num)
    return f"M{max_num + 1:02d}"
```

---

## 11. Migration Strategy

### 11.1 Existing Data

For existing users:
- Create Worker and Middleman entities if they don't exist
- Assign Worker and Middleman roles if they don't have them
- Set `created_by_user_id` for existing jobs/clients (use admin user or first user)

### 11.2 Migration Script

Create a data migration script to:
1. Create Worker/Middleman entities for existing users
2. Assign Worker/Middleman roles to existing users
3. Set `created_by_user_id` for existing jobs/clients

---

## 12. Notes & Considerations

1. **Worker Name/Email Immutability**: Once set, Worker.name = User.username cannot be changed. Worker.contact can be updated when User.email is updated by admin.

2. **Job Visibility with Payments**: The logic to show jobs with payment history even if allocation is removed requires careful querying to avoid performance issues.

3. **Role Switching**: When switching roles, the dashboard and data views should update immediately without page refresh if possible.

4. **Admin Access**: Admin users have full access regardless of active role, but they also have Worker/Middleman entities for consistency.

5. **Worker Roster**: This is a read-only list page showing all workers, accessible to all authenticated users.

6. **Email Field**: Consider adding email validation and uniqueness checks.

---

## 13. Testing Checklist

- [ ] Create new user → Verify Worker and Middleman entities created
- [ ] Create new user → Verify both roles assigned
- [ ] Login as Worker → Verify only assigned jobs visible
- [ ] Login as Middleman → Verify only own jobs/clients visible
- [ ] Create job as Middleman → Verify `created_by_user_id` set
- [ ] Create client as Middleman → Verify `created_by_user_id` set
- [ ] Assign job to worker → Verify only Admin/Middleman can do this
- [ ] Remove allocation after payment → Verify worker still sees job
- [ ] Switch roles → Verify data changes appropriately
- [ ] Worker Roster → Verify all users can access
- [ ] Admin access → Verify admin sees all data regardless of role

---

## Next Steps

1. Review and approve this plan
2. Implement Phase 1 (Database & Models)
3. Implement Phase 2 (User Creation)
4. Continue with remaining phases
5. Test thoroughly
6. Deploy
