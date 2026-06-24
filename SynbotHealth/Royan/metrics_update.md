
Got it—this is exactly the kind of shift that turns Synbot from “generic ops tool” into a **domain-native system**.

You’re not just rearranging UI.
You’re redefining **what the hospital considers “important.”**

Let’s do this in 3 layers:

1. Extract what matters (from hospital context)
2. Redesign dashboard logic (what shows first)
3. Give you a **clean backend prompt** to implement

---

# 1. What Matters in a Hospital (Not Finance-First)

From the data you shared + typical hospital ops, leadership (CMD, doctors, admin) care about:

## A. Patient Flow (TOP PRIORITY)

* Patients waiting
* Average wait time
* Queue bottlenecks
* Patients seen today

👉 This is your **primary dashboard anchor**

---

## B. Clinical Activity

* Number of consultations today
* Diagnoses distribution (optional later)
* Follow-ups scheduled
* Active cases

---

## C. Operational Efficiency

* Staff workload (who is overloaded)
* Department throughput (lab, pharmacy, etc.)
* Service turnaround time

---

## D. Compliance & Safety (Underrated but powerful)

From your audit docs:

* Maintenance overdue
* Compliance gaps
* Deviations logged
* Risk alerts

👉 This is a **huge differentiator vs competitors**

---

## E. Facilities Health

* Equipment status
* Maintenance schedules
* Downtime

---

## F. Financials (NOT FIRST)

* Daily revenue
* Outstanding payments

👉 Important, but NOT the landing view

---

# 2. New Dashboard Hierarchy (Critical Shift)

## OLD (Placeware style)

1. Financials
2. Ops
3. Misc

---

## NEW (Hospital-first logic)

## 🟢 MAIN DASHBOARD (Executive / CMD View)

### SECTION 1 — Live Hospital Status (Top Row)

* Patients in queue
* Avg wait time
* Patients seen today
* Active consultations

---

### SECTION 2 — Flow & Bottlenecks

* Queue per department
* Longest waiting patient
* Department load (OPD, lab, etc.)

---

### SECTION 3 — Clinical Snapshot

* Consultations today
* Follow-ups scheduled
* Admission/discharge (if applicable)

---

### SECTION 4 — Operational Alerts

* Overdue maintenance
* Equipment issues
* Staff overload warnings

---

### SECTION 5 — Financial Summary (Compact)

* Revenue today
* Pending payments

---

# 3. Sidebar Restructure (This changes perception instantly)

## Current (likely generic)

* Dashboard
* Reports
* Finance
* etc.

---

## Hospital Version (Synbot Health)

```text
Dashboard
Patients
Queue & Flow
Consultations (EMR)
Lab & Diagnostics
Pharmacy
Scheduling
Facilities & Maintenance
Compliance & Audits
Reports & Analytics
Billing
Settings
```

---

## Key Insight:

> The order of the sidebar defines what the system “feels like”

---

# 4. Page-Level Design Thinking

## Patients

* registry
* history
* visit timeline

---

## Queue & Flow (Your strength)

* live queue
* call next
* wait tracking

---

## Consultations

* doctor notes
* diagnosis
* prescriptions

---

## Facilities & Maintenance (from your audit docs)

* maintenance logs
* schedules
* alerts

---

## Compliance

* audits
* deviations
* CAPA tracking

---

# 5. KPI Cards (Concrete List)

Use these as your core metrics:

## Tier 1 (Top Cards)

* Patients Waiting
* Avg Wait Time
* Patients Seen Today
* Active Consultations

---

## Tier 2

* Department Load
* Staff Utilization
* Lab Turnaround Time

---

## Tier 3

* Maintenance Due
* Compliance Issues
* Equipment Downtime

---

## Tier 4

* Revenue Today
* Outstanding Payments

---

# 6. Now the Important Part — Backend Agent Prompt

Here’s the structured prompt you can feed directly:

---

SYSTEM GOAL:
Design and restructure Synbot Health dashboards and navigation to reflect a hospital-first operational system instead of a finance-first system.

CONTEXT:
This system will be used by hospital leadership (CMD), doctors, nurses, and admin staff. The primary focus is patient flow, clinical activity, and operational efficiency—not financial reporting.

---

DASHBOARD STRUCTURE:

1. MAIN DASHBOARD (Executive View)

SECTION A: LIVE HOSPITAL STATUS (TOP PRIORITY)

* Patients currently waiting
* Average patient wait time
* Number of patients seen today
* Active consultations

SECTION B: PATIENT FLOW & BOTTLENECKS

* Queue distribution per department
* Longest waiting patient
* Department workload visualization

SECTION C: CLINICAL ACTIVITY SNAPSHOT

* Total consultations today
* Follow-ups scheduled
* Active patient cases

SECTION D: OPERATIONAL ALERTS

* Overdue maintenance tasks
* Equipment issues
* Staff overload indicators

SECTION E: FINANCIAL SUMMARY (MINIMIZED PRIORITY)

* Revenue today
* Outstanding payments

---

SIDEBAR NAVIGATION (ORDER MATTERS):

1. Dashboard
2. Patients
3. Queue & Flow
4. Consultations (EMR)
5. Lab & Diagnostics
6. Pharmacy
7. Scheduling
8. Facilities & Maintenance
9. Compliance & Audits
10. Reports & Analytics
11. Billing
12. Settings

---

DESIGN PRINCIPLES:

* Prioritize real-time operational visibility over financial reporting
* Keep clinical and patient-related data at the top
* Surface alerts and risks early (maintenance, compliance, delays)
* Ensure dashboards are actionable (not just informational)
* Reduce cognitive load for doctors and administrators

---

DATA PRIORITY RULES:

* Real-time data > historical summaries
* Patient flow > financial metrics
* Operational risks > passive reporting
* Alerts > static charts

---

OUTPUT REQUIREMENTS:

* Update dashboard layout to reflect new hierarchy
* Reorder sidebar navigation accordingly
* Redesign KPI cards to match hospital priorities
* Ensure modular structure for future expansion (AI insights, predictions)

END.

---

# 7. Final Insight (This is the real shift)

You’re moving from:

> “Business dashboard”

To:

> **“Hospital command center”**

---

If you want next step, we can:

* Map this into **actual Django models → API → UI binding**
* Or design **Builder.io UI blocks for each section**
* Or define **real-time data pipelines (queue + sync layer)**

This is where Synbot starts feeling like a real product.
