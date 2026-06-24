# SynHealth Demo Readiness — Implementation Plan
**Strategic Vision-to-Reality Roadmap**  
*Synthesized from your vista-1 through vista-4 studies*

---

## 0. VISION ALIGNMENT CHECK ✅

Your study describes an **AI-Native Hospital Operating System** with:
- Layered architecture (Presentation → Application → Workflow → Data → Integration → Intelligence)
- Encounter-centric domain model (Patient → Encounter → Orders → Results)
- **HMO Coverage Engine** as the critical differentiator (Nigeria-specific)
- Safe read-only integration with Hope software
- Real-time queue + calendar as operational control centers
- Role-based dashboards (CMD, Doctor, Admin)

**Current State**: Backend mostly scaffolded. Questionnaire ready. Frontend minimal.  
**Gap**: No HMO rules engine. No encounter model. No queue visualization. No billing split logic.

**Strategic Correction Required**: Stop thinking "features" → Start thinking "operational workflows"

---

## 1. CORE IMPLEMENTATION STRATEGY

### Phase 1 (This Sprint): Demo MVP
**Goal**: Show a hospital could *actually use this* immediately.

**Scope**: Patient lookup → Queue board → Billing split (HMO visible)

---

### Phase 2 (After Site Visit): Royan-Specific Configuration
**Goal**: Adapt to Royan's exact Hope schema, contracts, and staff workflows.

---

### Phase 3 (Production Readiness): Full Hope Sync + Advanced Rules
**Goal**: Go live with read-only ETL from Hope, authority shifts to Synbot.

---

## 2. BACKEND ARCHITECTURE CHANGES (REQUIRED)

### 2.1 Domain Model — Core Entities

**Priority: CRITICAL** — These must exist before frontend can demo anything.

Add to `backend/src/domain/`:

```python
# Encounter (REPLACES vague "visit")
class Encounter(Base):
    id: UUID
    patient_id: UUID
    type: str  # "outpatient", "inpatient", "ae" (accident & emergency)
    start_time: datetime
    end_time: Optional[datetime]
    status: str  # "scheduled", "in_progress", "completed", "cancelled"
    chief_complaint: str
    provider_id: UUID  # doctor
    department: str  # "Cardiology", "A&E", etc.
    created_at: datetime
    
# Service (catalog of billable services)
class Service(Base):
    id: UUID
    name: str  # "Consultation", "Lab Test X", "Drug Y"
    code: str  # internal reference
    category: str  # "consultation", "lab", "imaging", "drug", "procedure"
    base_price: Decimal
    created_at: datetime

# Order (CPOE — Computerized Physician Order Entry)
class Order(Base):
    id: UUID
    encounter_id: UUID
    patient_id: UUID
    service_id: UUID
    type: str  # "lab", "imaging", "prescription", "procedure"
    status: str  # "pending", "in_progress", "completed", "cancelled"
    ordered_by: UUID  # doctor
    created_at: datetime

# HMO / Insurance relationship
class PatientInsurance(Base):
    id: UUID
    patient_id: UUID
    hmo_id: UUID
    plan: str  # "Basic", "Premium", "Executive"
    membership_id: str
    valid_from: date
    valid_to: date
    status: str  # "active", "expired", "suspended"

# HMO Entity
class HMO(Base):
    id: UUID
    name: str  # "AXA Mansard", "Hygeia", etc.
    code: str
    contact_info: str
    created_at: datetime

# Coverage Rule (THE CORE — reads this at billing time)
class CoverageRule(Base):
    id: UUID
    hmo_id: UUID
    service_id: UUID
    coverage_type: str  # "percentage", "fixed_amount", "not_covered"
    coverage_value: Decimal  # 80 (for 80%), or 15000 (fixed ₦), or 0 (not covered)
    requires_approval: bool
    limit_type: str  # "none", "per_visit", "per_month", "per_year"
    limit_value: Optional[Decimal]
    created_at: datetime

# QueueEntry (Real-time operational state)
class QueueEntry(Base):
    id: UUID
    patient_id: UUID
    encounter_id: UUID
    status: str  # "waiting", "called", "in_service", "completed"
    added_at: datetime
    called_at: Optional[datetime]
    started_service_at: Optional[datetime]
    completed_at: Optional[datetime]
    department: str
```

### 2.2 Coverage Engine — Core Logic

**File**: `backend/src/billing/coverage_engine.py`

```python
def calculate_coverage(patient_id: UUID, service_id: UUID) -> dict:
    """
    Core algorithm: Given a patient + service, return HMO split.
    Called at: Order creation, Billing generation, UI display.
    """
    patient = get_patient(patient_id)
    insurance = get_patient_insurance(patient_id)
    service = get_service(service_id)
    
    if not insurance or insurance.status != "active":
        return {
            "hmo_pays": 0,
            "patient_pays": service.base_price,
            "requires_approval": False,
            "notes": "No active insurance"
        }
    
    rule = get_coverage_rule(insurance.hmo_id, service_id)
    
    if not rule or rule.coverage_type == "not_covered":
        return {
            "hmo_pays": 0,
            "patient_pays": service.base_price,
            "requires_approval": False,
            "notes": "Service not covered under this plan"
        }
    
    if rule.coverage_type == "percentage":
        hmo_pays = service.base_price * (rule.coverage_value / 100)
    elif rule.coverage_type == "fixed_amount":
        hmo_pays = min(rule.coverage_value, service.base_price)
    
    patient_pays = service.base_price - hmo_pays
    
    return {
        "hmo_pays": hmo_pays,
        "patient_pays": patient_pays,
        "requires_approval": rule.requires_approval,
        "hmo_id": insurance.hmo_id,
        "plan": insurance.plan,
        "limit_type": rule.limit_type,
        "notes": f"{rule.coverage_value}% covered by {insurance.hmo_id}"
    }
```

### 2.3 New API Endpoints (FastAPI Routes)

**File**: `backend/app.py` — Add routes:

```python
# Encounters
@app.post("/encounters")
def create_encounter(payload: dict) -> dict:
    # Create a new visit/encounter
    # Link to patient, doctor, department

@app.get("/patients/{patient_id}/encounters")
def get_patient_encounters(patient_id: UUID) -> list[dict]:
    # Timeline of all visits

# Orders
@app.post("/orders")
def create_order(payload: dict) -> dict:
    # Doctor creates lab/imaging/prescription order
    # Calls coverage_engine to show HMO split

@app.get("/orders/{order_id}")
def get_order(order_id: UUID) -> dict:
    # Returns order + coverage info

# Queue (Real-time)
@app.get("/queue/department/{department}")
def get_queue(department: str) -> list[dict]:
    # Returns waiting → called → in_service patients

@app.post("/queue/{patient_id}/call")
def call_patient(patient_id: UUID) -> dict:
    # Move from "waiting" → "called"

@app.post("/queue/{patient_id}/start-service")
def start_service(patient_id: UUID) -> dict:
    # Move from "called" → "in_service"

@app.post("/queue/{patient_id}/complete")
def complete_service(patient_id: UUID) -> dict:
    # Move from "in_service" → "completed"

# Coverage Rules (Admin)
@app.post("/hmos/{hmo_id}/coverage-rules")
def create_coverage_rule(hmo_id: UUID, payload: dict) -> dict:
    # Admin configures HMO coverage (80% labs, 100% consultation, etc.)

@app.get("/hmos/{hmo_id}/coverage-rules")
def get_hmo_coverage_rules(hmo_id: UUID) -> list[dict]:
    # List all rules for an HMO

# Billing
@app.post("/billing/calculate")
def calculate_bill(patient_id: UUID, service_ids: list[UUID]) -> dict:
    # Calculate total bill with HMO split
    coverage_breakdowns = [calculate_coverage(patient_id, sid) for sid in service_ids]
    return {
        "total": sum(c["hmo_pays"] + c["patient_pays"] for c in coverage_breakdowns),
        "hmo_total": sum(c["hmo_pays"] for c in coverage_breakdowns),
        "patient_total": sum(c["patient_pays"] for c in coverage_breakdowns),
        "breakdowns": coverage_breakdowns
    }
```

### 2.4 Database Migrations

**File**: `backend/migrations/010_encounter_queue_hmo_core.sql`

```sql
-- Core entities for Demo

CREATE TABLE encounters (
    id UUID PRIMARY KEY,
    patient_id UUID NOT NULL,
    type VARCHAR(20) NOT NULL,  -- outpatient, inpatient, ae
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'scheduled',
    chief_complaint TEXT,
    provider_id UUID,
    department VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (patient_id) REFERENCES synhealth_patients(id)
);

CREATE TABLE services (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) UNIQUE,
    category VARCHAR(50),  -- consultation, lab, imaging, drug
    base_price DECIMAL(12,2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE orders (
    id UUID PRIMARY KEY,
    encounter_id UUID NOT NULL,
    patient_id UUID NOT NULL,
    service_id UUID NOT NULL,
    type VARCHAR(50),  -- lab, imaging, prescription
    status VARCHAR(20) DEFAULT 'pending',
    ordered_by UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (encounter_id) REFERENCES encounters(id),
    FOREIGN KEY (service_id) REFERENCES services(id),
    FOREIGN KEY (patient_id) REFERENCES synhealth_patients(id)
);

CREATE TABLE hmos (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) UNIQUE,
    contact_info TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE patient_insurance (
    id UUID PRIMARY KEY,
    patient_id UUID NOT NULL,
    hmo_id UUID NOT NULL,
    plan VARCHAR(100),
    membership_id VARCHAR(100),
    valid_from DATE,
    valid_to DATE,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (patient_id) REFERENCES synhealth_patients(id),
    FOREIGN KEY (hmo_id) REFERENCES hmos(id)
);

CREATE TABLE coverage_rules (
    id UUID PRIMARY KEY,
    hmo_id UUID NOT NULL,
    service_id UUID NOT NULL,
    coverage_type VARCHAR(50),  -- percentage, fixed_amount, not_covered
    coverage_value DECIMAL(12,2),
    requires_approval BOOLEAN DEFAULT FALSE,
    limit_type VARCHAR(50),
    limit_value DECIMAL(12,2),
    created_at TIMESTAMPTZ DEFAULT now(),
    FOREIGN KEY (hmo_id) REFERENCES hmos(id),
    FOREIGN KEY (service_id) REFERENCES services(id)
);

CREATE TABLE queue_entries (
    id UUID PRIMARY KEY,
    patient_id UUID NOT NULL,
    encounter_id UUID,
    status VARCHAR(20) DEFAULT 'waiting',  -- waiting, called, in_service, completed
    department VARCHAR(100),
    added_at TIMESTAMPTZ DEFAULT now(),
    called_at TIMESTAMPTZ,
    started_service_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    FOREIGN KEY (patient_id) REFERENCES synhealth_patients(id)
);

-- Indices for performance
CREATE INDEX idx_encounters_patient ON encounters(patient_id);
CREATE INDEX idx_encounters_status ON encounters(status);
CREATE INDEX idx_orders_patient ON orders(patient_id);
CREATE INDEX idx_orders_encounter ON orders(encounter_id);
CREATE INDEX idx_queue_status ON queue_entries(status);
CREATE INDEX idx_queue_department ON queue_entries(department);
```

---

## 3. FRONTEND COMPONENTS (React/Vue scaffold)

**Priority**: Patient lookup + Queue board + Billing split

### 3.1 Core Components To Build

```
components/
├── Patient/
│   ├── PatientSearch.tsx       (Fuzzy search + dropdown)
│   ├── PatientCard.tsx         (Summary card with HMO badge)
│   ├── PatientProfile.tsx      (Full profile + timeline)
│   └── PatientInsuranceBadge.tsx (Shows HMO + plan + active status)
│
├── Queue/
│   ├── QueueBoard.tsx          (4-column real-time board)
│   ├── QueueEntry.tsx          (Individual tile)
│   ├── QueueActionPanel.tsx    (Call, Start Service, Complete buttons)
│   └── WaitTimeDisplay.tsx
│
├── Billing/
│   ├── BillingCalculator.tsx   (Input services → show split)
│   ├── BillingSplit.tsx        (HMO % vs Patient % visual)
│   ├── ServiceSelector.tsx     (Dropdown with coverage info inline)
│   └── InvoicePreview.tsx
│
├── Encounter/
│   ├── EncounterTimeline.tsx   (List of past visits)
│   ├── NewEncounterForm.tsx    (Chief complaint, provider, dept)
│   └── EncounterSummary.tsx
│
├── Layout/
│   ├── Sidebar.tsx             (Navigation)
│   ├── TopBar.tsx              (HMO filter, alerts)
│   ├── ContextPanel.tsx        (Right-side detail pane)
│   └── Dashboard.tsx           (Main layout wrapper)
│
└── Common/
    ├── HMOBadge.tsx            (Everywhere)
    ├── StatusTag.tsx           (waiting, called, completed)
    ├── AlertCard.tsx           (Compliance, overdue, etc.)
    └── LoadingSpinner.tsx
```

### 3.2 Key User Flows (Wireframe Descriptions)

**Flow 1: Find Patient & Check HMO Coverage**
```
1. Staff types "John Doe" in search → fuzzy results
2. Clicks patient card → sees HMO badge (AXA Premium ✅ Active)
3. Right panel shows: last visit, current status, insurance valid until date
```

**Flow 2: Admit Patient to Queue**
```
1. From patient profile, staff clicks "Add to Queue"
2. System creates QueueEntry(status="waiting", department="Cardiology")
3. Patient appears in queue board under "Waiting" column
```

**Flow 3: Call & Service Patient**
```
1. Doctor clicks "Call Next" from queue board
2. Patient moves from "Waiting" → "Called" (updates real-time)
3. Doctor clicks "Start Service"
4. Patient moves to "In Service" column
5. At end, "Complete" → patient moves to "Completed"
```

**Flow 4: Create Order & See HMO Split**
```
1. Doctor clicks "New Order" on patient profile
2. Selects "Lab Test" from dropdown
3. System instantly shows:
   - Price: ₦15,000
   - Coverage: 80% (AXA Premium)
   - HMO pays: ₦12,000
   - Patient pays: ₦3,000
4. Doctor confirms order
```

**Flow 5: Generate Bill**
```
1. After encounter complete, click "Generate Bill"
2. System shows:
   - Consultation ₦10,000 (100% covered)
   - Lab ₦15,000 (80% covered)
   - Drug ₦5,000 (50% covered)
   - TOTAL: ₦30,000
   - HMO PAYS: ₦22,000
   - PATIENT PAYS: ₦8,000
```

---

## 4. IMPLEMENTATION ROADMAP (DETAILED)

### Sprint 1: Backend Core (Week 1)

**Day 1-2: Data Model**
- [ ] Create `backend/src/domain/` folder
- [ ] Define Encounter, Service, Order, PatientInsurance, HMO, CoverageRule, QueueEntry classes
- [ ] Write migration `010_encounter_queue_hmo_core.sql`
- [ ] Run migration on local DB

**Day 3: Coverage Engine**
- [ ] Write `backend/src/billing/coverage_engine.py` with `calculate_coverage()`
- [ ] Unit tests (happy path + edge cases)

**Day 4-5: API Endpoints**
- [ ] POST/GET `/encounters`
- [ ] POST/GET `/orders`
- [ ] GET `/queue/{department}`, POST `/queue/{patient_id}/call`, etc.
- [ ] POST `/billing/calculate`
- [ ] Integration tests with mock Hope data

**Verification**:
```bash
pytest backend/tests/test_coverage_engine.py
pytest backend/tests/test_billing_api.py
```

---

### Sprint 2: Frontend Components (Week 2)

**Day 1-2: Patient Lookup**
- [ ] PatientSearch.tsx (fuzzy search, debounced API calls)
- [ ] PatientCard.tsx (show HMO badge, last visit, status)
- [ ] PatientProfile.tsx (basic layout: left summary + center timeline + right actions)

**Day 3: Queue Board**
- [ ] QueueBoard.tsx (4-column Kanban: Waiting | Called | In Service | Completed)
- [ ] QueueEntry.tsx (patient tile with wait time)
- [ ] QueueActionPanel.tsx (Call, Start, Complete buttons + real-time updates via WebSocket or polling)

**Day 4: Billing UI**
- [ ] ServiceSelector.tsx (dropdown showing price + coverage inline)
- [ ] BillingSplit.tsx (visual: 80% HMO vs 20% Patient)
- [ ] BillingCalculator.tsx (select multiple services, show total split)

**Day 5: Integration + Polish**
- [ ] Connect frontend to backend APIs
- [ ] Error handling (service not covered, insurance expired)
- [ ] Loading states + optimistic updates
- [ ] Responsive for tablet (important for hospital staff)

**Verification**:
- Staff can find a patient in < 2 seconds
- HMO badge always visible
- Queue real-time updates when status changes
- Billing split calculates instantly

---

### Sprint 3: Hope Integration + Demo Prep (Week 3)

**Day 1-2: Hope Bridge Testing**
- [ ] Run hope-bridge on Windows PC at hospital
- [ ] Sync patient data → confirm Synbot receives it
- [ ] Sync HMO info (if available in Hope)

**Day 3: Seed Demo Data**
- [ ] Create 5–10 realistic patients with HMO associations
- [ ] Create 3 HMOs with different coverage rules
- [ ] Create service catalog (consultations, labs, drugs)

**Day 4: Demo Walkthrough Prep**
- [ ] Dry-run all user flows with sample data
- [ ] Create demo script (5-minute walkthrough)
- [ ] Prepare "Ask Me" questions (What happens if HMO expires? What if service not covered?)

**Day 5: Stakeholder Feedback**
- [ ] Demo to hospital directors / staff
- [ ] Collect feedback on UI/UX
- [ ] Prioritize follow-up features

---

## 5. SUCCESS CRITERIA (Demo Readiness)

### ✅ Minimum Viable Demo
- [x] Patient lookup works (< 2 sec)
- [x] HMO status visible on every patient card
- [x] Queue board shows real-time state changes
- [x] Order creation shows instant HMO coverage calculation
- [x] Billing shows HMO vs patient split
- [x] No errors in happy path (valid patient + active insurance)

### ⚠️ Known Limitations (To Disclose)
- Approval workflows not yet implemented
- Equipment/facility management visible as mock only
- Calendar shows appointments but not fully interactive
- Capitation rules not yet supported

---

## 6. POST-DEMO ROADMAP (Weeks 4+)

### After Client Feedback:

1. **Calendar UI** → Full appointment management
2. **Advanced HMO Rules** → Capitation, per-visit limits, drug formularies
3. **Compliance Alerts** → Maintenance due, audit schedules
4. **Equipment Management** → Track downtime, schedule calibration
5. **AI Layer** → Queue optimization, predictive alerts

---

## 7. QUESTIONNAIRE RESPONSES — What We'll Extract

When you provide client answers, we'll identify:

| Question | What It Tells Us |
|----------|------------------|
| Hope edition + DB backend | ETL complexity |
| Active Hope modules | Scope of sync required |
| Current HMO contracts | Coverage rules to build |
| Daily patient volume | Performance targets |
| Staff roles | Dashboard customization needed |
| Go-live timeline | Sprint sequencing |

---

## 8. RISK MITIGATION

| Risk | Mitigation |
|------|-----------|
| HMO rules too complex | Start with % only, add limits later |
| Hope schema unknown | Use mock data in demo, real schema post-visit |
| Queue real-time delays | Use WebSocket + polling fallback |
| Billing calculation errors | Unit tests + manual verification of every rule |
| Adoption hesitation | Show queue efficiency (time to see doctor ↓) + billing transparency |

---

## NEXT STEPS (What You Should Do Now)

1. **Provide questionnaire responses** → I'll extract Royan-specific requirements
2. **Review this plan** → Make any directional changes before coding
3. **Start Sprint 1** → Backend model + coverage engine (most critical path item)
4. **Parallel: Design Hope schema mapping** → What Hope tables → Synbot tables

**Ready to begin?**
