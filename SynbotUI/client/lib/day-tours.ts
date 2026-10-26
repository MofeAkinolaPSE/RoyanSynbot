/**
 * First sign-in tour: a typical day in each role, in the order the work happens (Oct 2026).
 *
 * The old tour listed every page a role could open, in menu order, with a generic line each. This walks a person
 * through their day instead - the front desk assigns doctors to rooms and checks patients in; a doctor opens My
 * Dashboard, consults, orders, reviews results; management sees the whole hospital. Each step opens its page and
 * says what to press there, naming controls exactly as they appear on screen. Roy's chat guide
 * (backend/src/knowledge/roy_feature_guide.md) and the "Show me how" walkthroughs (walkthroughs.ts) describe the
 * same tasks in more depth; keep the three in step.
 *
 * Rules (checked by day-tours.spec.ts): every step's page must be one the role can open, and every role on User
 * Access has a day.
 */

export type DayStep = {
  /** What this part of the day is, e.g. "Check a patient in". */
  title: string;
  /** The page the step opens. */
  href: string;
  /** One or two sentences: when in the day and why. */
  body: string;
  /** What to press there, in order. */
  points?: string[];
};

const WORKSPACE: DayStep = {
  title: "Your own day: tasks, messages and the work clock",
  href: "/workspace",
  body: "Clock in here when you arrive and out when you leave. Work for your role, requests from colleagues and messages land here too.",
  points: [
    "My Day: Start work when you arrive, Break, End work when you leave.",
    "Task, Reminder, Note at the top; Ask sends a colleague a request; Message opens a conversation.",
    "Leave requests your leave; HR approves it.",
  ],
};

const HELP: DayStep = {
  title: "Help is always one click away",
  href: "/",
  body: "Ask Roy anything about the system with the chat button at the bottom right - for example \"how do I record a payment?\". Pages with a Show me how button walk you through a task step by step.",
  points: [
    "Roy: the round chat button, bottom right of every page.",
    "Show me how: at the top of Front Desk, Queue, Lab, Scancare, Pharmacy, Billing, the HMO Desk and the nursing record.",
    "Take the tour again: your name at the bottom of the menu, then Take the tour again.",
  ],
};

const HOME: DayStep = {
  title: "Your home page: ROY Workstation",
  href: "/",
  body: "Everything you have access to starts here, and the panels show what is happening in the hospital now. If you get lost anywhere, come back here.",
  points: ["Open on any panel goes to its full page.", "The menu on the left is A to Z; your pages are inside its sections."],
};

const DAYS: Record<string, DayStep[]> = {
  // ── Front desk ───────────────────────────────────────────────────────────────
  receptionist: [
    {
      title: "Start of the day: put each doctor in a consulting room",
      href: "/hospital/front-desk",
      body: "As each doctor arrives, assign them to a room on Consulting rooms today. Only doctors on seat appear when you check a patient in.",
      points: ["Consulting rooms today (right): Assign a doctor next to a room, type the doctor's name.", "The cross frees the room when they leave."],
    },
    {
      title: "Check a patient in",
      href: "/hospital/front-desk",
      body: "Search first - most patients are already in the system. Then fill in today's visit and issue the ticket.",
      points: [
        "Search by name, phone or MRN; try another spelling before deciding they are new.",
        "Choose the visit type, the Payer (Private or HMO / Insurance), the Doctor (doctors on seat, with their room and how many are waiting) and the Priority.",
        "Type the complaint, then Register Encounter & Issue Ticket. The patient goes to vitals, then the doctor.",
        "Already on the queue means they are checked in today - do not register them twice.",
      ],
    },
    {
      title: "Register a new patient",
      href: "/hospital/patients",
      body: "Only when the search finds nobody. A duplicate record splits the patient's history in two.",
      points: ["Register Patient, fill in the form and save.", "Then check them in at Front Desk for today's visit."],
    },
    {
      title: "Book and receive appointments",
      href: "/hospital/appointments",
      body: "Appointments belong to a doctor's slots.",
      points: ["Book Appointment: choose the patient and a free slot. Next available slot finds the soonest.", "When they come in, mark Arrived - that puts them straight on the queue."],
    },
    {
      title: "Approve drugs for the pharmacy",
      href: "/hospital/front-desk",
      body: "Pharmacy approvals waiting is always on the right. When the pharmacy asks the desk to approve a drug, it appears there.",
      points: ["Tick to approve, cross to reject."],
    },
    {
      title: "The waiting-room screen",
      href: "/hospital/front-desk",
      body: "Display board at the top opens the screen for the waiting room's TV: queue numbers and which room to go to.",
    },
    WORKSPACE,
    HELP,
  ],

  // ── Doctor ───────────────────────────────────────────────────────────────────
  doctor: [
    {
      title: "Your day starts on My Dashboard",
      href: "/hospital/doctor",
      body: "My patients shows today's appointments, the patients waiting for you, results to review and who you have finished with. The front desk checks patients in to you here.",
      points: ["Begin next to a patient opens the consultation.", "Results to review: lab and Scancare results that have come back for your patients.", "My Day (a tab here): Start work when you arrive."],
    },
    {
      title: "The consultation",
      href: "/hospital/doctor",
      body: "Begin opens the patient's consultation: Summary, Vitals (the nurse's), Results, Notes, Orders, Prescribe and Referral.",
      points: ["Notes: the SOAP note - Subjective, Objective, Assessment, Plan.", "Each section stays open while you type; Continue to the next section when ready.", "Add diagnosis: type the condition in words; the ICD-10 code fills itself.", "Sign note when finished; corrections are made later with Amend."],
    },
    {
      title: "Order tests, scans and drugs",
      href: "/hospital/doctor",
      body: "In the consultation's Orders tab, order everything the patient needs. HMO patients show what their HMO covers at the top.",
      points: ["Order Lab Test, Order Radiology, Order Medication, Book Surgery.", "Prescribe tab: the same prescription form.", "Request Admission sends the patient to Wards & Beds."],
    },
    {
      title: "Finish the visit",
      href: "/hospital/queue",
      body: "After the consultation the patient pays at the cashier, then goes for lab, scan or pharmacy.",
      points: ["End consultation when you are done.", "End - see again with results: the patient comes back to you when the results are in."],
    },
    {
      title: "Read results as the printed report",
      href: "/hospital/doctor",
      body: "When results come back they are on My Dashboard and in the consultation's Results tab.",
      points: ["View report opens the result on the Scancare report sheet; Print prints it.", "Print all lab results gives the whole visit on one report."],
    },
    {
      title: "Your appointments",
      href: "/hospital/appointments",
      body: "My appointments shows only the patients booked into your slots.",
    },
    {
      title: "Your diary",
      href: "/calendar/tasks",
      body: "My Schedule: your appointments, your tasks and the events you are invited to - nobody else's.",
    },
    {
      title: "A patient's whole record",
      href: "/hospital/patients",
      body: "Search for any patient to open their chart: past visits, notes, medications, results and scans, including the old system's records.",
      points: ["View report on any result or scan opens it as the printed report."],
    },
    HELP,
  ],

  // ── Nurse ────────────────────────────────────────────────────────────────────
  nurse: [
    {
      title: "Your day starts at the Nursing Station",
      href: "/hospital/nurse",
      body: "Patients waiting for you, admission requests, inpatients, free beds and critical flags - your ward on one page.",
      points: ["Vitals next to a patient, fill in, then Save & Confirm Vitals.", "My Day (a tab here): Start work when you arrive."],
    },
    {
      title: "Move patients through the queue",
      href: "/hospital/queue",
      body: "Today's outpatients in order: vitals, then the doctor, then the cashier, then lab, scan or pharmacy.",
      points: ["Vitals on a patient waiting for vitals; the doctor sees them at once.", "Doctor sends a patient with vitals done to the doctor.", "Choose the nurse in the Nurse column to take a patient."],
    },
    {
      title: "The nursing record",
      href: "/hospital/nurse",
      body: "Open a patient for their nursing record: Notes, Vitals, Flowsheet, Fluid Balance, Care Plans and MAR.",
      points: ["Notes are free text: write and Save note.", "Show me how in the record walks you through it."],
    },
    {
      title: "Admit, transfer and free beds",
      href: "/hospital/wards",
      body: "When a doctor requests an admission, pick a free bed and Confirm Admission. Free Bed after a discharge.",
    },
    {
      title: "Check patients in when the desk is busy",
      href: "/hospital/front-desk",
      body: "Search, choose payer, doctor and priority, then Register Encounter & Issue Ticket.",
    },
    {
      title: "Immunisation and maternity",
      href: "/hospital/immunisation",
      body: "Each child's schedule shows what is due and overdue. Antenatal, delivery and newborn records are on MCH / OB-GYN.",
    },
    {
      title: "Report an incident",
      href: "/hospital/quality",
      body: "Falls, medication errors, near misses: Report Incident, fill in the details, then Submit Report.",
    },
    HELP,
  ],

  // ── Cashier ──────────────────────────────────────────────────────────────────
  cashier: [
    {
      title: "Who is coming to pay",
      href: "/hospital/queue",
      body: "The visit goes vitals, doctor, cashier, services. A patient comes to you after the doctor, for the consultation and everything that was ordered.",
    },
    {
      title: "Take a payment",
      href: "/hospital/billing",
      body: "Open the patient's bill on Bills.",
      points: ["Record Payment: the amount owed is filled in; choose Cash, POS, Transfer or Card and save.", "Receipt or Print Invoice for the patient.", "Lab, scan and pharmacy can serve the patient once the bill is paid."],
    },
    {
      title: "Part payments",
      href: "/hospital/billing",
      body: "If the patient pays part and must be seen now, Release services lets lab, scan and pharmacy go ahead; the balance stays on their account.",
    },
    {
      title: "HMO patients",
      href: "/hospital/billing",
      body: "An HMO visit's bill shows What the HMO covers. A service the HMO team marked not covered is the patient's to pay here.",
      points: ["If the patient needs it covered, Request HMO approval with the reason - the HMO team asks the HMO."],
    },
    {
      title: "Corrections",
      href: "/hospital/billing",
      body: "A discount is requested here and approved by an administrator. A wrong bill is voided with a reason; its orders can then be billed again.",
    },
    {
      title: "Patients' accounts",
      href: "/finance/books/sales",
      body: "Receivables: every invoice, paid or not. Record receipt takes a payment against an older invoice.",
    },
    WORKSPACE,
    HELP,
  ],

  // ── HMO officer ──────────────────────────────────────────────────────────────
  hmo: [
    {
      title: "Today's HMO patients",
      href: "/hospital/hmo",
      body: "HMO Desk shows every HMO patient on the queue now, where they are, what was ordered and what the pharmacy has given.",
    },
    {
      title: "Check what the HMO covers",
      href: "/hospital/hmo",
      body: "Open a patient. Under Services - what the HMO covers, mark each billed service Covered or Not covered before the claims form goes out.",
      points: ["Not covered moves it to the patient to pay; it is held at lab, scan or pharmacy until paid, and stays off the claim.", "Unless you mark it, the HMO pays in full."],
    },
    {
      title: "Approval requests",
      href: "/hospital/hmo",
      body: "When a doctor or the cashier asks for a not-covered service to be approved, ask the HMO, then record the answer.",
      points: ["HMO approved: enter the HMO's authorisation code - it goes back on the HMO's bill and the claim.", "HMO declined: the patient pays."],
    },
    {
      title: "The claims form",
      href: "/hospital/hmo",
      body: "Open Royan claims form prints the visit's claim. The patient signs on the signature pad; then I have checked the claims form.",
    },
    {
      title: "HMO bills and what HMOs owe",
      href: "/finance/books/sales",
      body: "Receivables shows each HMO's invoices and what is unpaid; Billing & Cashier has the visit bills.",
    },
    WORKSPACE,
    HELP,
  ],

  // ── Pharmacist ───────────────────────────────────────────────────────────────
  pharmacist: [
    {
      title: "Prescriptions waiting",
      href: "/hospital/pharmacy",
      body: "Prescriptions arrive as soon as the doctor prescribes. To Dispense lists what is waiting.",
    },
    {
      title: "Dispense",
      href: "/hospital/pharmacy",
      body: "Open a prescription: it opens on Dispense with the prescribed quantity and the drug's price filled in.",
      points: ["Check them, keep Auto (FEFO) for the batch, tick Counselling given, then Dispense.", "Unpaid (private) prescriptions are held: send the patient to the cashier first.", "Allergy or interaction warning: Override & Dispense records your reason."],
    },
    {
      title: "Returns, discounts and signatures",
      href: "/hospital/pharmacy",
      body: "On a dispensed item: Record Return, Request Discount (an administrator approves), Capture Signature for the collector.",
    },
    {
      title: "Check the stock",
      href: "/hospital/pharmacy/inventory",
      body: "Stock, Expired Stock, Replenishment, Trending and Report. Each item shows its batches and expiry dates.",
    },
    {
      title: "Reorder",
      href: "/procurement",
      body: "The Reorder plan works out what to order from actual use: Order now, Order soon, Enough, May expire before use. Stock orders close when the stock arrives.",
    },
    {
      title: "Quality control",
      href: "/quality-control",
      body: "Expiring and expired batches, recalls and medication incidents.",
    },
    WORKSPACE,
    HELP,
  ],

  // ── Laboratory ───────────────────────────────────────────────────────────────
  lab: [
    {
      title: "Orders waiting",
      href: "/hospital/lab",
      body: "Order Queue: the doctors' orders as they are placed. STAT and urgent orders sort to the top.",
    },
    {
      title: "Take and receive the sample",
      href: "/hospital/lab",
      body: "Open an order: Collect Specimen, then Receive Specimen (Reject Specimen if it is unusable). Unpaid private orders are held until the patient pays.",
    },
    {
      title: "Record the result",
      href: "/hospital/lab",
      body: "Record Result: the test's lines are already there - investigation, units and normal range. Type only the observed values.",
      points: ["Edit lines unlocks them for an exception; Add line adds one.", "Values outside the range print in red."],
    },
    {
      title: "Verify and release",
      href: "/hospital/lab",
      body: "Verify & Authenticate releases the result to the doctor. A wrong verified result: Amend Result - the original stays on record.",
    },
    {
      title: "The printed report",
      href: "/hospital/lab",
      body: "View report shows the result on the Scancare report sheet with the patient's details; Print prints it.",
    },
    {
      title: "Critical values and send-outs",
      href: "/hospital/lab",
      body: "Turnaround & Critical flags critical values - still phone the doctor. Send Out records a test sent to an outside lab.",
    },
    WORKSPACE,
    HELP,
  ],

  // ── Scancare (radiology) ─────────────────────────────────────────────────────
  radiology: [
    {
      title: "Scancare's day",
      href: "/hospital/radiology",
      body: "Dashboard, Billing & cashier, Worklist, Not yet billed and TAT & Volume. Studies ordered by doctors and walk-ins are on Worklist.",
      points: ["Walk-in study registers a patient who comes straight to Scancare."],
    },
    {
      title: "Do the scan",
      href: "/hospital/radiology",
      body: "Open a study: Schedule, then Start Scan. Unpaid private studies are held until the patient pays.",
    },
    {
      title: "Write the report",
      href: "/hospital/radiology",
      body: "The report form opens with Scancare's standard report for that study and this patient's indication.",
      points: ["Fill in every ___ (measurements) and change what differs.", "Common phrases for this study adds a phrase with one click.", "Save Report, then Verify & Finalize."],
    },
    {
      title: "The printed report",
      href: "/hospital/radiology",
      body: "View report (print) shows the scan on the Scancare report sheet; Print prints it. Amend Report corrects a finalized report.",
    },
    WORKSPACE,
    HELP,
  ],

  // ── Stores ───────────────────────────────────────────────────────────────────
  store: [
    {
      title: "Department stores",
      href: "/hospital/stores",
      body: "Each department's stock and the central store: stock in, issues to departments, counts and adjustments.",
    },
    { title: "Pharmacy stock", href: "/hospital/pharmacy/inventory", body: "Stock, expired stock and replenishment, with batches and expiry dates." },
    {
      title: "Reorder",
      href: "/procurement",
      body: "Reorder plan (Order now, Order soon, Enough, May expire before use) and Stock orders, which close when the stock is received.",
    },
    { title: "What the stock is worth", href: "/finance/books/stock", body: "Ledger, books and shelf compared; Stock counts lists every batch before you count." },
    WORKSPACE,
    HELP,
  ],

  // ── Finance ──────────────────────────────────────────────────────────────────
  finance: [
    {
      title: "Roy Books: the finance hub",
      href: "/finance/books?company=RHL",
      body: "Bills, cashier payments, HMO claims and pharmacy stock post here automatically. A yellow banner means Data issues are open.",
      points: ["Scancare Books is Scancare's own company."],
    },
    { title: "Billing & Cashier", href: "/hospital/billing", body: "Every bill and payment; discounts waiting for approval; voids with reasons." },
    {
      title: "Receivables",
      href: "/finance/books/sales",
      body: "Invoice register: every invoice, paid or not. Record receipt takes payment; Aged receivables shows who is late.",
    },
    { title: "Credit control", href: "/finance/ar", body: "What HMOs and corporate payers owe, aged, with alerts: Statement, Record receipt, HMO bill." },
    { title: "Suppliers and payments", href: "/finance/books/purchases", body: "Pay supplier ticks the bills being paid; One-off payment pays anyone without a supplier record." },
    { title: "Banking", href: "/finance/books/banking", body: "Bank accounts and reconciliation." },
    { title: "Statements and reports", href: "/finance/books/statements", body: "P&L, balance sheet and cash flow; the Report Center has Royan's reports first (HMO vs private, claims ageing)." },
    { title: "Month end", href: "/finance/books/close", body: "Data issues lists every difference to resolve; Close period at month end." },
    { title: "The hospital on one page", href: "/executive", body: "Executive Overview: billing, profit and cash, what HMOs owe, patients, stock and staff." },
    HELP,
  ],

  // ── HR ───────────────────────────────────────────────────────────────────────
  hr: [
    { title: "Start in HR", href: "/hr", body: "Overview, Staff directory, Shift roster, Leave, Timesheets and Payroll.", points: ["Add staff record for a new employee."] },
    { title: "Approve leave", href: "/hr", body: "Staff request leave from their own workspace; approve or decline it on Leave. It shows on the Hospital Calendar." },
    { title: "Rosters and time", href: "/hr", body: "Shift roster plans who is on; Timesheets come from staff's Start work / End work." },
    { title: "Payroll", href: "/hr", body: "Run payroll on Payroll; it posts to Roy Books." },
    { title: "The hospital's diary", href: "/calendar", body: "Everyone's leave alongside appointments, theatre, audits and deliveries." },
    WORKSPACE,
    HELP,
  ],

  // ── Quality ──────────────────────────────────────────────────────────────────
  quality_assurance: [
    { title: "Quality & Safety", href: "/hospital/quality", body: "Incidents, Infection Control and HEFAMAA: Report Incident, Log Infection, Submit Checklist." },
    { title: "Audits & Maintenance", href: "/hospital/audits-maintenance", body: "Facility audits, equipment servicing and maintenance - what is due and overdue." },
    { title: "Compliance", href: "/compliance", body: "The compliance score and what is pulling it down; HEFAMAA assessments; the audit trail." },
    { title: "Pharmacy quality control", href: "/quality-control", body: "Expiring and expired batches, recalls and medication incidents." },
    { title: "Write a report", href: "/reports/new", body: "Pick the report type and the record it is about (an incident, an audit, a month), review and generate; Download Word." },
    { title: "The hospital's diary", href: "/calendar", body: "Audits, servicing and maintenance on the calendar; drag one to another day to move it." },
    HELP,
  ],

  // ── Operations ───────────────────────────────────────────────────────────────
  ops: [
    { title: "Front Desk and rooms", href: "/hospital/front-desk", body: "Doctors to consulting rooms, check-ins, pharmacy approvals and the waiting-room display." },
    { title: "Patient flow", href: "/hospital/queue", body: "Today's outpatients in order: vitals, doctor, cashier, services, discharge - and where each one is waiting." },
    { title: "Wards & Beds", href: "/hospital/wards", body: "Occupancy, admissions and free beds." },
    { title: "Stores and reorders", href: "/procurement", body: "Reorder plan, stock orders and suppliers." },
    { title: "Audits & Maintenance", href: "/hospital/audits-maintenance", body: "What is due and overdue for servicing and maintenance." },
    { title: "The hospital's diary", href: "/calendar", body: "Appointments, theatre, audits, maintenance, leave and deliveries together." },
    WORKSPACE,
    HELP,
  ],

  // ── Physiotherapy ────────────────────────────────────────────────────────────
  physiotherapist: [
    { title: "Your patients", href: "/hospital/nurse", body: "The Nursing Station shows patients waiting, inpatients and your workspace tabs." },
    { title: "The queue", href: "/hospital/queue", body: "Today's outpatients and where each one is." },
    { title: "Patients on the wards", href: "/hospital/wards", body: "Inpatients by ward and bed for therapy sessions." },
    { title: "A patient's record", href: "/hospital/patients", body: "Search by name, phone or MRN to open the full chart: visits, notes, results and scans." },
    HELP,
  ],

  // ── Auditor (read-only) ──────────────────────────────────────────────────────
  auditor: [
    { title: "Read-only, everything in the books", href: "/finance/books?company=RHL", body: "You can open every ledger, statement and report; nothing can be changed from this account." },
    { title: "Journals and the ledger", href: "/finance/books/ledger", body: "Journal entries, Journals by type, General ledger, Trial balance, Chart of accounts." },
    { title: "Statements", href: "/finance/books/statements", body: "P&L, balance sheet and cash flow for any period." },
    { title: "Receivables", href: "/finance/books/sales", body: "Every invoice and receipt, aged receivables." },
    { title: "Stock in the books", href: "/finance/books/stock", body: "Ledger, books and shelf compared; batch-level stock." },
    { title: "The executive view", href: "/executive", body: "The hospital on one page: billing, profit and cash, what HMOs owe, stock and staff." },
    HELP,
  ],
};

// ── Management: the whole hospital ─────────────────────────────────────────────
const MANAGEMENT: DayStep[] = [
  { ...HOME },
  {
    title: "The hospital on one page",
    href: "/executive",
    body: "Executive Overview: billing (HMO vs private), profit and cash from Roy Books, what HMOs owe, today's patients and beds, stock, quality and staff. A ranked list shows what needs attention; every figure opens the page behind it.",
    points: ["Executive report writes a summary."],
  },
  { title: "Today, live", href: "/hospital/admin-dashboard", body: "Admin Dashboard: patients waiting, average wait, bed occupancy, pending labs and prescriptions, and alerts." },
  {
    title: "How a patient moves through the hospital",
    href: "/hospital/queue",
    body: "Queue & Flow: front desk, then vitals, the doctor, the cashier, then lab, Scancare or pharmacy, then discharge. Each patient shows where they are waiting.",
  },
  { title: "Front Desk", href: "/hospital/front-desk", body: "Doctors assigned to consulting rooms each morning; check-ins with payer, doctor and priority." },
  { title: "The doctors' view", href: "/hospital/doctor", body: "My Dashboard: each doctor's patients, consultations, orders and results." },
  { title: "Lab and Scancare", href: "/hospital/lab", body: "Orders, results and verification; results print on the Scancare report sheet. Scancare (Radiology) runs as its own company." },
  { title: "Pharmacy and stock", href: "/hospital/pharmacy", body: "Dispensing, stock, department stores, the reorder plan and quality control." },
  { title: "Billing and the HMO Desk", href: "/hospital/hmo", body: "The HMO Desk checks what each HMO covers before the claims form; the cashier takes payments on Billing & Cashier." },
  { title: "Roy Books", href: "/finance/books?company=RHL", body: "The finance hub: receivables, payables, banking, ledger, statements, the Report Center and month end." },
  { title: "Who owes the hospital", href: "/finance/ar", body: "Credit Control: HMOs and corporate payers, aged, with alerts." },
  { title: "HMO and corporate relationships", href: "/relations", body: "Patient Relations: every payer, what they bill and owe, contacts and follow-ups." },
  { title: "Staff and payroll", href: "/hr", body: "HR: staff directory, rosters, leave, timesheets and payroll." },
  { title: "Quality and compliance", href: "/hospital/quality", body: "Incidents, infection control, HEFAMAA; Audits & Maintenance and Compliance sit in the same section." },
  { title: "The hospital's diary", href: "/calendar", body: "Every doctor's appointments, theatre, audits, servicing, leave, deliveries and HMO follow-ups." },
  { title: "Reports", href: "/reports/new", body: "Write a report about any record (an incident, an HMO, a month) and download it as Word; Analytics for trends." },
  HELP,
];

DAYS.management = MANAGEMENT;
DAYS.admin = [
  ...MANAGEMENT.slice(0, -1),
  {
    title: "Staff accounts",
    href: "/admin/users",
    body: "User Access: New user, tick every role the person needs - the preview shows their menu. Edit access, Password and Deactivate on each account.",
    points: ["Staff Registrations: approve people who registered themselves; the login is attached to their HR record."],
  },
  { title: "Who did what", href: "/admin/audit-log", body: "The Audit Log records every action, by whom and when." },
  { title: "System health", href: "/admin/reliability", body: "Reliability Console: errors and health. Start here if something behaves oddly." },
  HELP,
];

/** Roles in the order a combined account is toured (a chief with every role gets the management tour). */
export const TOUR_ROLE_PRIORITY = [
  "admin", "management", "doctor", "nurse", "receptionist", "cashier", "hmo", "pharmacist", "lab", "radiology",
  "finance", "hr", "quality_assurance", "store", "ops", "physiotherapist", "auditor",
];

export function primaryTourRole(roles: string[] | null | undefined): string {
  const have = new Set((roles ?? []).map((r) => r.toLowerCase()));
  return TOUR_ROLE_PRIORITY.find((r) => have.has(r)) ?? (roles?.[0] ?? "viewer");
}

export function getDayTour(role: string): DayStep[] | undefined {
  return DAYS[role];
}

export const DAY_TOUR_ROLES = Object.keys(DAYS);
