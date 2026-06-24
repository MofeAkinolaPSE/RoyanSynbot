Let me read those research files first.

Let me check what's already built in the backend routers and services to understand the gap.

Let me check the existing migrations and frontend to complete the gap analysis.

Let me check the state of a few key hospital routers to know if they're complete or scaffolded.

Now I have a complete picture. Let me synthesize everything into the plan.

Here is the full plan.

---

## SynbotHealth — Implementation Plan

### What I found

**Backend is largely done.** Patient registration, queue/encounters, appointments, wards, lab, pharmacy, HMO coverage engine, hospital billing, Hope bridge, all hospital agents, and migrations 100–114 are all properly implemented.

**The frontend is the critical gap.** `App.jsx` still has pharma-era navigation (SageImport, FinanceAnalytics, CRM, HR). Not a single hospital UI page exists. This is where all four vista studies point.

The studies call for three things the backend already supports but the UI doesn't expose:
1. A **VistA-inspired Hospital OS interface** (vista-1) — the full clinical flow from patient search through encounter to discharge
2. An **HMO coverage engine UI** (vista-2, vista-3) — surfaces the backend coverage calculation at every decision point
3. An **enterprise-grade interaction design** (vista-4) — 3-panel layout, Kanban queue, smart patient cards, calendar, transparent billing

---

### Phase 1 — App Shell & Design System
**Why first:** Everything else mounts inside it.

- Rewrite `SynbotUI/src/App.jsx` — replace pharma nav with hospital nav, adopt 3-panel layout: `[Sidebar | Main Workspace | Context Panel]`
- New hospital navigation: Queue, Patients, Appointments, Wards, Lab, Pharmacy, Billing, HMO, Dashboard, Ask Synbot, Settings
- New `HospitalLayout.jsx` — persistent sidebar with notification badges, collapsible context panel on right
- Shared UI components: `PatientCard`, `StatusBadge` (Green=completed, Yellow=waiting, Red=critical, Blue=active), `AlertBanner`, `SplitCard`
- Centralized API hook `useApi.js` pointing to `/patients`, `/queue`, `/coverage`, `/billing_hospital`, etc.

---

### Phase 2 — Patient Lookup System *(vista-4 §3)*
**Why:** The study calls this the "most-used entry point" — staff spend most of their time here.

- `PatientSearchBar.jsx` — global fuzzy search persisted in the header, calls `GET /patients/search?q=`
- `PatientCard.jsx` — shows: name/age/gender, MRN, phone, HMO status badge (✅ active / ⚠️ expired), current status, last visit, `[View Profile]` + `[Add to Queue]` actions
- `PatientsPage.jsx` — search results list using PatientCard

---

### Phase 3 — Patient Profile Page *(vista-4 §4, vista-1 §2.1)*
**Why:** This is the VistA-inspired longitudinal record — the clinical command center per patient. The backend already returns the full payload from `GET /patients/{mrn}/profile` (encounters, lab orders, prescriptions, bills, timeline sorted by timestamp).

- `PatientProfilePage.jsx` — 3-column layout:
  - **Left (sticky):** demographics, HMO plan + status, allergies, blood group
  - **Center:** `EncounterTimeline` — chronological list of encounters, lab orders, prescriptions, billing events rendered as expandable cards
  - **Right (action panel):** `[New Encounter]` → `POST /queue/start`, `[Add Lab Order]`, `[Schedule Follow-up]`, `[Send Message]`

---

### Phase 4 — Clinical Queue Board *(vista-4 §5, vista-1 §3.5)*
**Why:** Real-time operational core. The backend exposes `GET /queue/board` and encounter state transitions via `POST /queue/{id}/advance`.

- `QueueBoardPage.jsx` — Kanban with 4 columns: **Waiting | Called | In Service | Completed**
- Each `PatientTile` shows: name, wait time (calculated from encounter `created_at`), assigned doctor, HMO badge, triage priority color
- `[Call Next]` button triggers `POST /queue/{id}/advance` with `new_status: "called"`
- Live updates via WebSocket `/ws/queue` (already exists in backend as `realtime_ws.py`)

---

### Phase 5 — Appointments & Calendar *(vista-4 §6, vista-1 §3.4)*
**Why:** Scheduling control center. Backend has full slot/booking system.

- `AppointmentsPage.jsx` — FullCalendar-based (day/week/doctor views)
- Each calendar event card: patient name, doctor, appointment type, status color
- Click → right context panel opens: full appointment details, reschedule, send reminder
- `[Next Available Slot]` feature using `GET /appointments/slots`
- New booking via `POST /appointments/book`

---

### Phase 6 — HMO-Aware Billing UI *(vista-2 full, vista-3 full, vista-4 §7)*
**Why:** The most complex and highest-stakes UI. Gets billing wrong → trust collapses. The coverage engine is fully built; it just needs a surface.

- `BillingPage.jsx`:
  - Service line item entry — on each service selection, fires `POST /coverage/quote` and instantly shows: `Covered: 80% | Patient Pays: ₦2,000 | Approval Required: No`
  - Visual bill summary: progress-bar split of Total / HMO portion / Patient responsibility
  - Inline alerts: "Service not covered", "Approval required — contact HMO", "Monthly limit exceeded"
  - Submit via `POST /billing_hospital/from-encounter`
- `HMOAdminPage.jsx` (admin-only):
  - List/create HMOs, add plans, define coverage rules
  - Coverage rule matrix: service rows × HMO columns

---

### Phase 7 — Role-Based Dashboards *(vista-1 §7)*
**Why:** Different roles see completely different information. Route based on JWT role claim.

- `CMDDashboard.jsx` — hospital-wide: current bed occupancy, patient flow today, active risk alerts from agents, executive KPI summary
- `DoctorDashboard.jsx` — personalized: today's schedule, list of assigned encounters, pending lab results to review
- `AdminDashboard.jsx` — operations: billing summary, HMO receivables, staff activity, compliance tasks due
- Role routing: `cmd` → CMD, `doctor` → Doctor, `admin` / `staff` → Admin

---

### Phase 8 — Backend Gap: Clinical Notes *(vista-1 §3.1)*
**Why:** Encounters exist but the SOAP note write/read endpoints need verification.

- Read `queue_clinical.py` fully to check if `POST /queue/{id}/notes` and `GET /queue/{id}/notes` exist
- If missing: add them — free-text + structured notes (chief complaint, assessment, plan) stored on encounter
- Surface in patient profile timeline and doctor dashboard

---

### Phase 9 — Alerts & Notification System *(vista-4 §9)*
**Why:** The system must proactively surface critical state — not wait for staff to go looking.

- `AlertBanner.jsx` — top-of-page banner for critical system alerts (bed shortage, overdue HMO approval)
- `NotificationBadge.jsx` — sidebar badges counting pending items per section
- `InlineWarning.jsx` — per-row contextual warnings in queue, billing, lab
- Feed: poll `/agents/exec/patient_flow_agent/run` and `/agents/exec/bed_capacity_agent/run` on dashboard load

---

### Phase 10 — Intelligence Layer UI *(vista-1 §6)*
**Why:** This is the Synbot competitive advantage over legacy systems like VistA.

- Rebrand `AskSynbot` page for clinical context — queries like "Summarize John Doe's last 3 encounters", "Which HMO owes us the most this month?"
- CDS alerts inline in order creation: surface drug interaction warnings and abnormal lab flag thresholds
- Agent summary cards in dashboards: patient flow bottleneck, bed prediction for next 48h

---

### Execution Priority

| Priority | Phases | Outcome |
|---|---|---|
| **1** | 1, 2, 3, 4 | Core clinical flow working end-to-end |
| **2** | 5, 6 | Scheduling and revenue operational |
| **3** | 7, 9 | Visibility and alerts layer |
| **4** | 8, 10 | Clinical depth and AI advantage |

---

The backend is ready. The entire implementation is a frontend build, with one backend verification task (Phase 8). Phases 1–4 alone would give a functioning hospital OS for patient registration, triage, queue management, and profile review. Ready to start when you say go.