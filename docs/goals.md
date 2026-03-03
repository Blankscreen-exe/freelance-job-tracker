Good. Let’s strip this down to what your agency **actually needs**, not what ERPs try to sell you.

You’re a 6-person software dev agency with:

* Work bringers (middlemen)
* Workers
* Fixed-fee projects
* Commission splits
* No complex accounting
* Money clarity as #1 priority

So here’s the **lean feature list** your system should have.

---

# 🧱 1️⃣ Core Foundation Features

## 🔐 Authentication & Roles

You need:

* Admin (full control)
* Middleman (can see their projects + commissions)
* Worker (see assigned work + payout status)

Optional later:

* Client login (read-only access to invoices/status)

---

# 👥 2️⃣ Client Management

For each client:

* Client name
* Contact info
* Linked projects
* Total invoiced
* Total received
* Outstanding balance
* Payment history log

Dashboard view:

* Total receivables
* Overdue clients

---

# 📁 3️⃣ Project Management (Financial First, Not Task-Heavy)

Each project should include:

### Basic Info

* Project name
* Client
* Middleman
* Fixed total contract amount
* Status (active / completed / paused)

### Financial Configuration

* Contract value
* Commission type:

  * % based
  * Flat amount
* Commission value
* Worker payout entries (fixed per worker or split-based)

---

# 💰 4️⃣ Money Flow Tracking (MOST IMPORTANT)

This is your core feature set.

For each project:

### Revenue Side

* Total contract value
* Amount invoiced
* Amount received
* Pending amount
* Payment schedule (optional)

### Distribution Side

* Middleman commission amount
* Worker payout amounts
* Total payable to workers
* Total already paid to workers
* Remaining payable

### Net View

* Gross income
* Total commission
* Total worker payouts
* Net retained profit

---

# 🧾 5️⃣ Invoicing System

### Client Invoices

* Generate invoice (PDF)
* Mark as sent
* Mark as paid
* Partial payments
* Invoice history

### Worker Payout Slips

* Generate payout sheet
* Mark as paid
* Payment history per worker

No tax complexity needed unless required legally.

---

# 👷 6️⃣ Worker Management

For each worker:

* Assigned projects
* Agreed payout per project
* Total earned (all-time)
* Total paid
* Pending payout
* Payment history

Dashboard:

* “You are owed X”
* “You have been paid Y”

Transparency keeps trust high.

---

# 📊 7️⃣ Dashboard & Reports (Simple But Clear)

### Admin Dashboard

* Total receivable
* Total received
* Total payable to workers
* Net retained earnings
* Top paying clients
* Projects at risk (unpaid)

### Middleman Dashboard

* Projects they brought
* Commission earned
* Commission paid vs pending

### Worker Dashboard

* Projects assigned
* Earnings
* Paid vs pending

No advanced BI needed.

---

# 🧮 8️⃣ Commission Logic Engine

You need logic like:

If:

* Contract = $10,000
* Commission = 20%

System auto-calculates:

* Middleman = $2,000
* Remaining = $8,000 for workers

Then:

* Worker A = $4,000
* Worker B = $4,000

This should auto-adjust if:

* Client partially pays
* You only distribute proportionally

This is the feature most existing tools don’t handle cleanly.

---

# 📂 9️⃣ Payment Tracking Log (Audit Trail)

For clarity, every money movement should be logged:

* Client payment received
* Worker payout sent
* Commission paid
* Adjustments made

Each entry:

* Date
* Amount
* Linked project
* Notes

This protects you from disputes.

---

# 🔎 1️⃣0️⃣ Filters & Search

You’ll need:

* Filter projects by unpaid status
* Filter workers by pending payout
* Filter middlemen by unpaid commission
* Filter clients by overdue amount

Small feature — huge usability impact.

---

# 🧰 1️⃣1️⃣ Optional But Useful (Not Required Now)

* Export CSV
* Basic charts
* Email invoice sender
* Multi-currency (if needed later)
* File attachments (contracts, agreements)

---

# 🧠 What You DO NOT Need (Right Now)

❌ Full double-entry accounting
❌ Tax/VAT engine
❌ HR modules
❌ Asset management
❌ Inventory
❌ Payroll tax calculations
❌ CRM marketing automation

That’s ERP creep.

---

# 🎯 Your Minimum Viable System (MVP)

If you want absolute minimal build:

1. Auth + roles
2. Clients
3. Projects
4. Payment received tracking
5. Commission calculation
6. Worker payout tracking
7. Simple dashboard totals
8. PDF invoice export

That alone solves 90% of your clarity problem.

---

# 🧠 Reality Check

The reason tools like Dolibarr and Bitrix24 feel “almost right but not perfect” is:

They’re built for traditional businesses.

Your model is:
Revenue share → middleman commission → worker distribution.

That’s more like an agency + affiliate hybrid.

Which is why custom logic gives you more clarity.

---

If you want next, I can:

* Design a clean database schema for this
* Show you the exact money flow logic in pseudocode
* Or reduce this to a 2-week build roadmap

Which direction do you want?
