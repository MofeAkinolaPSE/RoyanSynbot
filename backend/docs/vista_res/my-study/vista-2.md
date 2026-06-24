Good—you just hit one of the **hardest, most critical layers in hospital systems**:

> **HMO / Insurance Billing Logic**

If you get this wrong → system gets rejected
If you get it right → you become indispensable

Let’s break this down properly and embed it into Synbot’s architecture.

---

# 1. Reality of HMOs in Nigeria (Ground Truth)

In Nigeria, HMOs (Health Maintenance Organizations) like:

* NHIS (public scheme)
* Private HMOs (AXA Mansard, Hygeia, Avon, etc.)

Operate on:

### A. Predefined Coverage Agreements

Each hospital has:

* Contracts with HMOs
* Service pricing rules
* Coverage lists

---

### B. Service Coverage Logic

For EACH HMO:

| Service      | Covered? | Coverage %        | Limit           |
| ------------ | -------- | ----------------- | --------------- |
| Consultation | Yes      | 100%              | Unlimited       |
| Lab Test     | Yes      | 80%               | ₦X/month        |
| Drugs        | Partial  | 50%               | formulary-based |
| Surgery      | Maybe    | approval required |                 |

---

### C. Payment Flow

```text
Patient → Service → Bill Generated → HMO Covers Portion → Patient Pays Balance
```

---

### D. Approval Workflow (VERY IMPORTANT)

Some services require:

* Pre-authorization
* HMO approval code

---

# 2. What This Means for Synbot

You are NOT building:

> “Discount system”

You are building:

> **Insurance Rules Engine**

---

# 3. Core Concept You Need

## Coverage Engine (New Core Module)

This sits inside:

```text
Billing System + EMR + Orders
```

---

# 4. Data Model (Critical Design)

## 4.1 HMO Entity

```text
HMO:
- name
- plan_types (basic, premium, executive)
```

---

## 4.2 Patient Insurance

```text
PatientInsurance:
- patient_id
- hmo_id
- plan
- membership_id
- validity
```

---

## 4.3 Service Catalog

```text
Service:
- name (consultation, lab test, drug)
- base_price
- category
```

---

## 4.4 Coverage Rules (THE CORE)

```text
CoverageRule:
- hmo_id
- service_id
- coverage_type (% / fixed / none)
- coverage_value
- requires_approval (boolean)
- limit_type (none / per_visit / per_month)
- limit_value
```

---

# 5. Billing Logic Flow (This is where magic happens)

## Step-by-step:

```text
1. Patient receives service
2. System identifies:
   → patient HMO
   → service
3. Fetch coverage rule
4. Calculate:
   → HMO portion
   → patient portion
5. Check:
   → limits
   → approval requirements
6. Generate bill:
   → split payment
```

---

## Example:

Consultation = ₦10,000
HMO covers 80%

```text
HMO pays: ₦8,000  
Patient pays: ₦2,000
```

---

# 6. Advanced Nigerian Reality You MUST Handle

## 1. Capitation (Very Important)

Some HMOs:

* Pay hospitals monthly per patient
* Cover consultations fully

👉 So:

```text
Consultation = ₦0 at point of service
```

---

## 2. Drug Formularies

* Not all drugs covered
* Some require substitution

---

## 3. Approval Codes

For:

* surgery
* expensive tests

Workflow:

```text
Doctor → Request → HMO Approval → Code issued → Service proceeds
```

---

## 4. Delayed Payments

Hospital:

* logs HMO receivable
* reconciles later

---

# 7. UI/Workflow Integration (Where It Shows Up)

---

## A. At Consultation Level

Doctor selects service:

👉 System shows:

```text
Covered: YES (80%)
Patient Pays: ₦2,000
Approval Required: NO
```

---

## B. At Billing Page

Split invoice:

```text
Total: ₦50,000
HMO: ₦35,000
Patient: ₦15,000
```

---

## C. Alerts

* “Service not covered”
* “Approval required”
* “Limit exceeded”

---

# 8. Where This Fits in Synbot Architecture

Add new module:

```text
Insurance & Coverage Engine
```

Sits between:

```text
Orders → Billing → Payments
```

---

# 9. Backend Logic (Agent Thinking)

You need a function like:

```python
def calculate_coverage(patient_id, service_id):
    hmo = get_patient_hmo(patient_id)
    rule = get_coverage_rule(hmo, service_id)

    if not rule:
        return full_patient_payment()

    if rule.requires_approval:
        flag_for_approval()

    covered_amount = compute(rule)
    patient_amount = total - covered_amount

    return breakdown
```

---

# 10. Smart Design Decision (Very Important)

DO NOT hardcode HMO rules.

Instead:

👉 Build:

> **Configurable Rules Engine**

Because:

* every hospital contract differs
* rules change frequently

---

# 11. Synbot Advantage (Where You Win)

Once this is built:

## AI Layer Can Do:

* “Why was this claim rejected?”
* “Which HMO owes us the most?”
* “Which services are underutilized?”

---

# 12. Integration With Existing System (Hope Software)

During overlay phase:

* Pull:

  * patient HMO data
  * billing records

* Recalculate inside Synbot

👉 Eventually:
Synbot becomes **source of truth**

---

# 13. Risks (Be Aware)

## 1. Wrong Calculations = Trust Loss

Billing must be:

* accurate
* transparent

---

## 2. Contract Complexity

Each HMO:

* different logic

---

## 3. Edge Cases

* expired coverage
* partial approvals
* overrides

---

# 14. What You Should Build First (Practical)

## Phase 1

* HMO + Patient Insurance
* Basic % coverage

---

## Phase 2

* limits
* approvals

---

## Phase 3

* capitation
* advanced rules

---

# 15. Final Insight

You’re not adding “discounts”

You’re adding:

> **Financial intelligence layer for healthcare delivery**

---

# 16. Next Step (Recommended)

We should now:

* Design **Django models for HMO engine**
* Build **coverage calculation API**
* Integrate into:

  * billing
  * orders
  * consultation flow

---

If you want, I’ll next:
👉 Design the **full database schema + API endpoints for HMO engine (production-ready)**

This is one of the most complex parts of the system—getting it right puts you ahead of most EMR systems in your region.
