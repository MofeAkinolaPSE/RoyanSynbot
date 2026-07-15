Good—this is the layer where everything you’ve designed either **clicks instantly for staff… or completely fails adoption**.

What you’re asking for is not just UI—it’s:

> **Interaction Design for a Hospital Operating System**

I’ll structure this as a **frontend blueprint your dev agent can execute directly**.

---

# 1. Core Frontend Philosophy (Non-Negotiable)

This system must feel like:

```text
Fast. Predictable. Context-aware. Zero-friction.
```

### Golden Rules:

* 1–2 clicks to complete critical actions
* Always show **what matters now**
* Never overload doctors with irrelevant data
* Every screen = **decision-making surface**

---

# 2. Global UI System (Foundation)

## A. Layout Structure

```text
[ Sidebar ] [ Main Workspace ] [ Context Panel ]
```

* **Sidebar** → Navigation (stable)
* **Main Workspace** → Active work
* **Right Panel** → Details / Actions (dynamic)

---

## B. Color Logic (Functional, not aesthetic only)

| Color  | Meaning              |
| ------ | -------------------- |
| Green  | Completed / Stable   |
| Yellow | Waiting / Attention  |
| Red    | Critical / Delay     |
| Blue   | Active / In progress |

---

## C. Interaction Speed

* Instant search (no page reloads)
* Inline edits (no modal overload)
* Real-time updates (queue, billing, alerts)

---

# 3. Patient Lookup Experience (Critical Entry Point)

This is where staff spend most time.

---

## A. Search Bar (Top-Level Component)

```text
Search: Name / Phone / ID / HMO ID
```

### Behavior:

* Instant suggestions
* Fuzzy search
* Keyboard-first navigation

---

## B. Patient Card (Search Result UI)

This must feel premium.

---

### Patient Card Design

```text
┌──────────────────────────────┐
│ John Doe (45, M)             │
│ ID: P-10234                  │
│ Phone: 0803xxxxxxx           │
│ HMO: AXA Premium ✅ Active   │
│ Last Visit: 12 May 2026      │
│ Status: Waiting 🟡           │
│                              │
│ [View] [Add to Queue]        │
└──────────────────────────────┘
```

---

## C. Smart Indicators

* HMO Active → ✅
* Expired → ⚠️
* High-risk patient → 🔴
* Frequent visitor → 🔁

---

# 4. Patient Profile Page (Command Center)

---

## Layout

```text
LEFT: Patient Summary
CENTER: Timeline (Encounters)
RIGHT: Actions
```

---

## A. Left Panel (Sticky Summary)

* Name, age, gender
* HMO + plan
* Alerts (allergies, chronic conditions)
* Contact info

---

## B. Center Panel (Timeline — VERY IMPORTANT)

```text
[Today]
Consultation → Lab → Prescription

[Last Week]
Follow-up visit

[Last Month]
Initial diagnosis
```

👉 This is your **VistA-inspired longitudinal record**

---

## C. Right Panel (Action Engine)

Buttons:

* * New Encounter
* * Add Order (Lab, Drug)
* * Schedule Follow-up
* * Send Message

---

# 5. Queue UI (Real-Time Core)

---

## A. Queue Board

```text
Waiting | Called | In Service | Completed
```

Each column = live state

---

## B. Patient Tile

```text
John Doe
Wait Time: 12 mins
Doctor: Dr. A
HMO: AXA
```

---

## C. Interaction

* Drag & drop (optional)
* “Call Next” button
* Auto-prioritization (future AI)

---

# 6. Calendar UI (Scheduling Control Center)

(Extending what we designed earlier)

---

## A. Visual Hierarchy

Each event shows:

```text
[Time]
Patient Name
Doctor
Type (Consultation / Lab)
Status Color
```

---

## B. Click Behavior

Right panel opens:

* Full appointment details
* Edit / reschedule
* Send reminder

---

## C. Smart Features

* “Next Available Slot”
* Conflict warnings
* Overbook alerts

---

# 7. Billing UI (HMO-Aware)

This must feel **transparent and trustworthy**

---

## A. Service Selection

Doctor selects service:

```text
Consultation → ₦10,000
Coverage: 80%
Patient Pays: ₦2,000
```

---

## B. Bill Summary

```text
Total: ₦50,000
HMO: ₦35,000
Patient: ₦15,000
```

---

## C. Visual Breakdown

Use:

* progress bars
* split cards

---

# 8. HMO Visibility (Everywhere)

HMO should NEVER be hidden.

---

## Always show:

* HMO name
* Plan
* Coverage status

---

## At Decision Points:

* consultation
* orders
* billing

---

# 9. Alerts & Notifications UI

---

## Types:

* Overdue patient
* Equipment issue
* HMO approval needed

---

## Display:

* Top banner (critical)
* Sidebar badge
* Inline warnings

---

# 10. Facilities & Compliance UI (Differentiator)

---

## Dashboard Cards:

* Maintenance due
* Equipment downtime
* Compliance risks

---

## Task View:

```text
Fumigation → Due Today ⚠️
Calibration → Completed ✅
```

---

# 11. Micro-Interactions (This is what makes it feel premium)

* Hover = quick preview
* Click = expand detail
* Inline edit = no page reload
* Auto-save = no “submit anxiety”

---

# 12. Performance Requirements

* < 200ms interactions
* optimistic UI updates
* offline-safe (important in Nigeria)

---

# 13. Design System (Dev Guidance)

Use:

* Component-based UI (React)
* Reusable cards:

  * PatientCard
  * AppointmentCard
  * BillingCard
  * AlertCard

---

# 14. Frontend Agent Prompt (What You Asked For)

---

SYSTEM GOAL:
Design a modern, enterprise-grade hospital frontend for RoyanHealth that enables fast, intuitive, and context-aware interaction with complex backend systems (EMR, HMO engine, scheduling, queue, billing).

---

CORE PRINCIPLES:

* Prioritize speed and clarity over visual complexity
* Design for real-time hospital operations
* Minimize clicks for critical workflows
* Surface actionable data, not raw data
* Ensure all UI elements reflect backend logic dynamically

---

PATIENT INTERFACE:

Implement a dynamic patient search system with real-time suggestions.

Each patient must be represented using a Patient Card containing:

* Name, age, gender
* Patient ID
* Phone number
* HMO provider + plan + status
* Last visit date
* Current status (Waiting, In Service, Completed)

Include quick actions:

* View Profile
* Add to Queue

---

PATIENT PROFILE PAGE:

Layout:

* Left: Patient summary (sticky)
* Center: Timeline of encounters
* Right: Action panel

Ensure:

* Longitudinal record view (history over time)
* Quick access to orders, notes, scheduling
* Real-time updates

---

QUEUE INTERFACE:

Design a Kanban-style queue:

* Columns: Waiting, Called, In Service, Completed
* Each patient tile shows:

  * Name
  * Wait time
  * Assigned doctor
  * HMO

Enable:

* One-click “Call Next”
* Real-time updates

---

CALENDAR INTERFACE:

Transform calendar into a scheduling control system.

Each event must include:

* Patient
* Doctor
* Type
* Status

Enable:

* Multi-view (day, week, doctor)
* Inline editing
* Right-side detail panel

---

BILLING INTERFACE:

Display transparent cost breakdown:

* Total cost
* HMO contribution
* Patient payment

Show coverage dynamically based on HMO rules.

---

HMO INTEGRATION UI:

At every service interaction:

* Display coverage %
* Show patient responsibility
* Alert if approval required

---

ALERT SYSTEM:

Display:

* Critical alerts (top banner)
* Inline warnings
* Notification badges

---

FACILITIES & COMPLIANCE:

Include dashboards for:

* Maintenance schedules
* Compliance tasks
* Risk alerts

---

INTERACTION DESIGN:

* Use inline editing wherever possible
* Avoid modal overuse
* Enable keyboard navigation
* Implement real-time UI updates

---

PERFORMANCE:

* Ensure sub-second response time
* Use optimistic updates
* Support unstable network conditions

---

OUTPUT:

* Component-based UI structure
* Fully dynamic interaction with backend systems
* Enterprise-grade usability for hospital staff

END.

---

# 15. Final Insight

If backend = brain
Then frontend = **reflex system**

---

If this layer is done right:

* staff don’t “learn” the system
* they **flow through it**

---

If you want next:

* I can map this into **actual React component tree + state management**
* Or build **Builder.io UI prompts for each page**
* Or define **API ↔ UI binding contracts**

This is where Synbot starts feeling like a real product.
