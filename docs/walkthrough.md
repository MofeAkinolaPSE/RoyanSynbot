# SynbotHealth — Live Demo Walkthrough
### Royan Hospital | Presenter Script

> **Total runtime:** ~33 minutes  
> **Patients used:** Mr. Emeka Okafor (outpatient) · Mrs. Halima Bello (emergency/inpatient)  
> **Stack must be running:** `bash deploy/start-dev.sh` — wait for all services healthy before presenting  
> **Open in browser:** `https://localhost` (dismiss the self-signed cert warning once)

---

## Before You Begin — Pre-Demo Checklist

- [ ] Stack is running (`docker compose ps` — all services show "running" or "healthy")
- [ ] Browser open at `https://localhost` — cert warning dismissed
- [ ] Patient portal open in a second tab (or phone): `https://localhost/portal`
- [ ] Zoom / screen share is showing the browser, NOT the terminal
- [ ] Have the AskSynbot questions written somewhere you can copy-paste quickly
- [ ] If Hope Bridge is not connected to the real DRM Hope PC, confirm `HOPE_MOCK=1` is set in `deploy/.env` — mock data will load automatically

---

## THE STORY

> *"Royan Hospital sees hundreds of patients every day. Today we follow two of them — Mr. Emeka Okafor, a 48-year-old hypertensive patient coming for an outpatient review, and Mrs. Halima Bello, a 34-year-old who walks in as an emergency. By the time their visits are done, you will have seen every major feature of SynbotHealth in action."*

---

## Scene 1 — The Platform: Login & Role-Based Access
**⏱ ~2 minutes**

**What to do:**
1. Open `https://localhost` — the SynbotHealth login screen appears.
2. Say: *"Every staff member logs in with their own credentials. The system gives each role exactly what they need — nothing more."*
3. Log in as **Admin** (username: `admin`, password: from `.env` → `ADMIN_PASSWORD`).
   - Point to the full navigation: Dashboard, Finance, HR, Operations, CRM, Workflow, AskSynbot.
   - Say: *"Admin sees everything."*
4. Log out. Log in as **Doctor** (create this account in Settings if not done — role: `doctor`).
   - Show: Clinical Queue, Patient List, AskSynbot. Finance menu is gone.
   - Say: *"A doctor sees clinical tools and the AI assistant. They cannot touch payroll or billing."*
5. Log out. Log in as **Receptionist** (role: `receptionist`).
   - Show: Front Desk, Queue Management. Most menus are hidden.
   - Say: *"Same platform, completely different experience per role. This is RBAC — Role-Based Access Control — enforced at the API level, not just the UI."*

> **Talking point:** JWT tokens are short-lived (45 minutes). The system silently refreshes them in the background. Nobody gets timed out mid-consultation.

---

## Scene 2 — Front Desk: Registering Mr. Emeka Okafor
**⏱ ~3 minutes** | Logged in as: **Receptionist**

**What to do:**
1. Navigate to **Front Desk → New Patient Registration**.
2. Say: *"Mr. Emeka Okafor has just walked in. He's 48, visiting for a routine review of his blood pressure and diabetes. He's a new patient."*
3. Fill in the registration form:
   - **Full Name:** Emeka Okafor
   - **Date of Birth:** 15 March 1978
   - **Phone:** 08031234567
   - **Gender:** Male
   - **Address:** 12 Bode Thomas Street, Surulere, Lagos
   - **Next of Kin:** Ngozi Okafor — 08031234568
4. Click **Save**. A **Medical Record Number is auto-assigned**: e.g. `RYN-00247`.
5. Point to the **NDPA 2023 Consent checkbox** — say: *"The system requires informed consent before storing any patient data. This is not optional — it's built into the registration flow to keep the hospital compliant with Nigeria's Data Protection Act."*
6. Assign to queue: **Outpatient → General Consultation**.
7. Point to the **Live Queue Board** on the right side of the screen — Mr. Okafor's card appears instantly.
   - Say: *"That update happened without a page refresh. WebSocket connection — the queue board is live."*

> **Talking point:** The MRN format `RYN-XXXXX` is configurable. On this system it is set to Royan Hospital's prefix. Every downstream record — labs, billing, prescriptions — links back to this single patient identity.

---

## Scene 3 — Doctor's Consultation + AskSynbot AI
**⏱ ~5 minutes** | Switch to: **Doctor**

**What to do:**
1. Log out, log back in as Doctor.
2. Navigate to **Clinical Queue**. Mr. Okafor's card is there. Click **Start Consultation**.
3. His patient record opens. Point out:
   - Demographics tab (what was just registered)
   - **History tab** — if Hope Bridge is connected, previous visits from DRM Hope appear here automatically. If HOPE_MOCK=1, show the mock history entries.
   - Say: *"The doctor does not have to ask the patient for their entire history. SynbotHealth has already pulled it from the hospital's existing DRM Hope system in the background."*
4. Open the **AskSynbot panel** (chat icon, usually top-right or side panel).
5. Type this question exactly:
   > *"What are the common causes of uncontrolled hypertension in a 48-year-old male patient with Type 2 diabetes, and what first-line management steps should be considered?"*
6. Wait for the response (~2–4 seconds). Point out:
   - The AI answer with clinical reasoning
   - The **NDPA 2023 disclaimer** at the bottom of every AI response: *"This information is AI-generated and intended for clinical reference only. It does not constitute medical advice."*
   - Say: *"This is RAG — Retrieval-Augmented Generation. The AI searches the hospital's own clinical knowledge base first, then uses DeepSeek's language model to compose the answer. It never hallucinates blindly — it grounds its response in documents we have approved."*
7. Back in the consultation view, click **New Lab Order**. Add:
   - Full Blood Count (FBC)
   - Random Blood Sugar (RBS)
   - Lipid Profile
8. Click **Save Clinical Notes**. Type: *"Patient presents with poorly controlled BP. On Amlodipine 5mg. Pending labs to guide management."*
9. Say: *"The note is timestamped, linked to the doctor's account, and cannot be deleted — only amended with a visible audit trail."*

> **Talking point:** AskSynbot is also available on the staff dashboard for non-clinical staff. A finance officer can ask *"What was our revenue last Tuesday?"* and get a data-backed answer from the hospital's own records.

---

## Scene 4 — Laboratory Module
**⏱ ~3 minutes** | Switch to: **Lab Technician**

**What to do:**
1. Log out, log in as Lab Technician.
2. Navigate to **Laboratory → Pending Orders**.
3. Mr. Okafor's three orders appear (FBC, RBS, Lipid Profile). Click his name.
4. Click **Mark Specimen Received** for FBC and RBS.
5. Enter results:
   - **FBC:** All values within normal range
   - **RBS:** `9.2 mmol/L` — above normal (flag this as **Abnormal** in the dropdown)
   - **Lipid Profile:** LDL elevated — flag as **Abnormal**
6. Click **Submit Results**.
7. Say: *"Results are immediately available to the requesting doctor. No phone calls, no paper forms."*
8. Point to the **notification bell** — a new alert has appeared:
   > *"Lab Turnaround Agent: Average TAT for RBS today is 52 minutes — exceeds the 45-minute target. Review bottlenecks."*
9. Say: *"That alert was not triggered manually. The Lab Turnaround Agent monitors every test in real time. When the average processing time drifts above the threshold, it fires automatically and logs the event for the Quality & Safety report."*

> **Talking point:** The agent runs continuously in the background. The lab manager sees a running TAT dashboard; management sees it in the daily EOS briefing. Nobody has to chase the numbers.

---

## Scene 5 — Pharmacy Dispensing
**⏱ ~2 minutes** | Switch to: **Pharmacist**

**What to do:**
1. Log in as Pharmacist. Navigate to **Pharmacy → Dispensing Queue**.
2. Mr. Okafor's prescription appears (generated by the doctor in Scene 3).
3. Click his name. The prescription shows:
   - Metformin 500mg × 60 tablets
   - Amlodipine 10mg × 30 tablets
4. Check inventory — the system shows live stock counts:
   - Metformin 500mg: **240 units** in stock
   - Amlodipine 10mg: **85 units** in stock
5. Click **Dispense**. Stock counts decrement immediately.
6. Point to the **Expiry Monitoring Agent** alert in the sidebar:
   > *"Batch AMX-2024-09 (Amoxicillin 500mg) expires in 14 days — 120 units remaining. Consider prioritising or returning to supplier."*
7. Say: *"The hospital never has to run a manual stock audit to catch expiring drugs. The agent checks every batch every night and surfaces anything that needs action before it becomes waste — or worse, a patient safety issue."*

> **Talking point:** The inventory router connects directly to the hospital's procurement workflow. When stock drops below the reorder threshold, a procurement suggestion is automatically raised for the stores manager to approve.

---

## Scene 6 — Billing, HMO & Patient Portal Payment
**⏱ ~4 minutes** | Switch between: **Finance role** and **Patient Portal**

**Part A — Finance view:**
1. Log in as Finance. Navigate to **Billing → Today's Invoices**.
2. Mr. Okafor's invoice has been auto-generated:
   - Consultation fee: ₦5,000
   - Lab (×3): ₦6,000
   - Drugs: ₦3,500
   - **Gross total: ₦14,500**
3. Select his HMO plan from the dropdown (e.g., AXA Mansard). HMO coverage applies:
   - HMO covers: ₦2,000
   - **Patient responsibility: ₦12,500**
4. Say: *"The HMO fee schedules are configured per plan. The system calculates the split automatically — no manual arithmetic."*

**Part B — Patient Portal (use phone or second browser tab):**
1. Open `https://localhost/portal` on your phone or a second browser tab (mobile-sized window if on desktop).
2. Say: *"This is the patient-facing portal — designed for mobile. Mr. Okafor can access it on his phone right now while he waits."*
3. Log in as Mr. Okafor: MRN `RYN-00247`, phone `08031234567`.
4. Show the three tabs:
   - **Appointments** — today's visit listed
   - **Results** — FBC normal, RBS 9.2 mmol/L (flagged abnormal with colour coding), Lipid Profile elevated
   - **Billing** — outstanding balance ₦12,500 shown clearly
5. Tap **Pay Now via Paystack**.
6. Say: *"In a live deployment, this opens the Paystack payment page. He pays from his phone — card, bank transfer, or USSD."*
7. Switch back to the Finance view on the main screen. The invoice status has updated to **Paid** (or **Payment Initiated** in demo mode).
8. Say: *"Finance sees the payment in real time. No manual reconciliation, no end-of-day chase."*

> **Talking point:** The portal is a Progressive Web App. Mr. Okafor can add it to his phone's home screen like a native app. It works offline for viewing previously loaded results.

---

## Scene 7 — Emergency Admission: Mrs. Halima Bello
**⏱ ~4 minutes** | Switch to: **Receptionist**, then **Ward Manager**

**What to do:**
1. Log in as Receptionist. Navigate to **Front Desk → Emergency Registration**.
2. Say: *"Twenty minutes later, Mrs. Halima Bello walks in — 34 years old, severe abdominal pain. This is an emergency."*
3. Register her quickly:
   - **Name:** Halima Bello
   - **DOB:** 2 August 1991
   - **Phone:** 08057891234
   - **Presenting complaint:** Acute abdomen, right lower quadrant pain
   - Set priority: **Emergency**
4. As soon as you save, point to the notification that fires:
   > *"Bed Capacity Agent: Ward B is at 87% occupancy (13/15 beds). Recommending Ward A (60% — 6/10 beds occupied)."*
5. Say: *"The Bed Capacity Agent runs continuously. The moment a new admission is triggered, it checks every ward and proactively recommends the best placement. Nobody has to call the ward to ask if there's a bed."*
6. Accept the recommendation: Assign to **Ward A, Bed 7**.
7. Log out. Log in as **Ward Manager / Nurse**.
8. Navigate to **Wards → Ward A**. Show the live bed map:
   - Beds shown as coloured tiles: green (vacant), orange (occupied), red (critical)
   - Bed 7 is now orange — Mrs. Bello's name on it
9. Click Bed 7 → Add nursing note: *"Patient arrived conscious. BP 110/70. Pain score 8/10. IV line established."*
10. Say: *"Every nurse's note is timestamped, attributed, and part of the permanent record. The ward manager can see all notes for all patients on their ward from one screen."*

---

## Scene 8 — Theatre Scheduling & Inpatient Management
**⏱ ~3 minutes** | Logged in as: **Doctor / Surgeon**

**What to do:**
1. Log in as Doctor. Pull up Mrs. Bello's record.
2. Add clinical note: *"Clinical findings consistent with acute appendicitis. Patient for emergency appendectomy."*
3. Navigate to **Theatre → Schedule Case**.
4. Fill in:
   - **Patient:** Halima Bello (RYN-00248)
   - **Procedure:** Appendectomy
   - **Theatre:** Theatre 2
   - **Scheduled time:** Tomorrow 09:00
   - **Surgeon:** Dr. [Your Name]
   - **Anaesthetist:** Dr. [Name]
5. The system checks the pre-op checklist automatically:
   - Lab clearance: ✅ (FBC ordered)
   - Consent signed: ✅
   - Anaesthesia review: ⏳ (pending)
6. Say: *"The system will not allow the theatre booking to be finalised until all pre-op requirements are met. This prevents cases going to theatre without clearance."*
7. After the procedure (simulated): Navigate to **Theatre → Completed Cases**. Click **Record Post-Op**.
   - Anaesthesia time: 1h 20min
   - Estimated blood loss: 150ml
   - Post-op status: Stable
8. Navigate to **Wards → Transfer**. Transfer Mrs. Bello from Theatre to Recovery Ward, Bed 3.
9. Say: *"The patient's location is tracked throughout the hospital. Billing, nursing records, and the executive dashboard all update automatically with every transfer."*

---

## Scene 9 — Executive Dashboard & AI Intelligence
**⏱ ~4 minutes** | Log in as: **Admin**

**What to do:**
1. Log in as Admin. Open the **Executive Dashboard**.
2. Walk through the KPI tiles (point to each):
   - **Patients today:** 47 (OPD 38, Emergency 9)
   - **Bed occupancy:** 71%
   - **Revenue today:** ₦387,500
   - **Average lab TAT:** 52 min (flagged — above 45 min target)
   - **Outstanding HMO receivables:** ₦1.2M
3. Say: *"This is the CEO's view. One screen tells the whole story of the hospital's day."*
4. Navigate to **Finance Analytics**. Show:
   - Daily revenue trend (7-day chart)
   - AR aging table — HMO invoices by age (30/60/90 days)
   - Top revenue services
5. Navigate to **Operations → Patient Flow**.
   - Show the flow map: patients currently at triage, consultation, lab, pharmacy, billing
   - Say: *"The Patient Flow Agent tracks every patient's position in the care journey. Management can see in real time if there's a bottleneck — e.g., 12 patients waiting for lab results."*
6. Navigate to **AI Agents → Active Alerts**.
   - Show the **Billing Reconciliation Agent** flag:
     > *"3 invoices have HMO coverage discrepancies — billed amount does not match the contracted fee schedule. Review recommended."*
   - Show the **Clinical Compliance Agent** score: e.g., 94% — click to see which protocols have deviations.
7. Navigate to **EOS (End of Shift Briefing)**. Click **Generate Briefing for Today**.
   - Wait 3–5 seconds. An AI-generated narrative appears:
     > *"Today's morning shift processed 47 patients across outpatient and emergency departments. Revenue of ₦387,500 was recorded, with ₦12,500 collected via the patient portal. Lab turnaround averaged 52 minutes — 7 minutes above target, primarily driven by RBS processing delays between 10:00 and 12:00. Bed occupancy peaked at 87% in Ward B. Mrs. Bello's appendectomy is scheduled for tomorrow. Three HMO billing discrepancies require Finance review before close of business..."*
   - Say: *"This briefing is generated automatically from the day's actual data. The outgoing shift doctor or manager reads this before handover. No notes to compile, no spreadsheets — the AI writes it."*

> **Talking point:** The EOS briefing uses the same RAG pipeline as AskSynbot, but queries the hospital's live operational data instead of the clinical knowledge base. It is contextual, accurate, and available in seconds.

---

## Scene 10 — Hope Bridge Integration & Live Notifications
**⏱ ~3 minutes** | Logged in as: **Admin**

**What to do:**
1. Navigate to **Settings → Integrations → Hope Bridge**.
2. Show the sync status panel:
   - **Status:** Connected (green dot) — or "Mock Mode" if HOPE_MOCK=1
   - **Last sync:** 2 minutes ago
   - **Records imported today:** 14 patients, 8 appointments, 3 lab results
3. Say: *"DRM Hope is the hospital's existing HMS — it has years of patient history. SynbotHealth does not replace it. Instead, the Hope Bridge service runs quietly on the same Windows PC as DRM Hope, reads patient and appointment data via ODBC, and pushes it to SynbotHealth every 60 seconds. Staff see a unified view. Existing workflows are not disrupted."*
4. If HOPE_MOCK=1: Say: *"We are running in mock mode today — the bridge is simulating DRM Hope data. When deployed on site, the team will point it at the real database and it will start syncing live records."*
5. Navigate to the **Notifications panel** (bell icon, top-right).
6. Scroll through the live notification feed from this session:
   - 🔔 Lab TAT alert (Scene 4)
   - 🔔 Expiry warning — Amoxicillin (Scene 5)
   - 🔔 Bed capacity recommendation (Scene 7)
   - 🔔 Billing reconciliation discrepancies (Scene 9)
7. Say: *"Every alert you saw during this demo arrived through the same WebSocket channel — live, without a single page refresh. Any staff member subscribed to a notification type receives it the moment it fires."*

---

## Closing — The Final AskSynbot Moment
**⏱ ~1 minute**

1. Open **AskSynbot** from any page.
2. Type:
   > *"Give me a brief summary of today's hospital performance and the key actions that need to be taken before end of business."*
3. The AI responds with a synthesised summary pulling from the dashboard data.
4. Say: *"That question could be asked by a CEO, a medical director, or a department head. They get a clear, data-backed answer in seconds — from their own hospital's data, running on their own server, with no data leaving the building."*
5. Close with: *"SynbotHealth is not a reporting tool. It is an intelligent operating layer for the hospital. Every department is connected, every alert is actionable, and every decision has data behind it."*

---

## Fallback Notes (If Something Breaks Live)

| Feature | Fallback |
|---|---|
| AskSynbot gives no response | Refresh the page — if still broken, show a pre-saved screenshot |
| Hope Bridge shows disconnected | Say *"In mock mode today — live sync demo available on deployment"* — not a problem |
| Patient portal payment button | Say *"Paystack gateway is in test mode — in production this opens a live payment page"* |
| Lab TAT agent alert doesn't fire | Manually open **AI Agents → Active Alerts** and scroll to show a recent lab alert |
| Docker container not responding | `docker compose -f deploy/docker-compose.yml restart backend` from terminal |
| Bed capacity agent doesn't fire | Navigate to **Wards** and show the bed map manually — explain the agent runs in background |

---

## Quick Reference — Demo Credentials

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | *(from deploy/.env → ADMIN_PASSWORD)* |
| Doctor | `dr.adeyemi` | `Demo1234!` *(create in Settings → Users)* |
| Lab Tech | `lab.tech` | `Demo1234!` |
| Pharmacist | `pharmacist` | `Demo1234!` |
| Finance | `finance` | `Demo1234!` |
| Receptionist | `receptionist` | `Demo1234!` |

> Create these accounts before the presentation via **Settings → User Management → Add User**.

## Quick Reference — Demo Patient Data

| Field | Mr. Emeka Okafor | Mrs. Halima Bello |
|---|---|---|
| MRN | RYN-00247 | RYN-00248 |
| DOB | 15 Mar 1978 | 2 Aug 1991 |
| Phone | 08031234567 | 08057891234 |
| Visit type | Outpatient | Emergency |
| Key lab value | RBS 9.2 mmol/L | N/A |
| Bill amount | ₦12,500 | Inpatient (ongoing) |
| Portal login | MRN + phone | N/A |

---

*SynbotHealth by Neurolayer — built for Nigerian hospitals, deployed on your infrastructure.*
