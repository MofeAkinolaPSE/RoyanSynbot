import {
  LayoutDashboard,
  DollarSign,
  BarChart3,
  Users,
  Settings,
  MessageSquare,
  Workflow,
  Shield,
  ShieldCheck,
  Thermometer,
  Bot,
  ClipboardList,
  Activity,
  FlaskConical,
  Pill,
  BedDouble,
  Receipt,
  Package,
  CalendarCheck,
  Building2,
  Stethoscope,
  ScanLine,
  Scissors,
  HeartPulse,
  MessageSquare as MsgSquare,
  CreditCard,
  ConciergeBell,
  Bug,
  Database,
  Syringe,
  Wrench,
  Boxes,
  BookOpen,
  Inbox,
} from "lucide-react";

export type NavChild = {
  label: string;
  href: string;
  /**
   * Overrides the parent's roles for this page only.
   *
   * Grouping items under one heading otherwise forces every child to share the
   * parent's access. Folding Pharmacy QC under Pharmacy did exactly that and
   * dropped quality_assurance — the role the page exists for — while handing it
   * to nurses and doctors. A child states its own roles when they differ.
   */
  roles?: string[];
  /** Menu only (never access): show this entry only to people holding one of these roles. */
  showFor?: string[];
  /** Menu only (never access): hide this entry from people holding any of these roles. */
  hideFor?: string[];
  tourDescription?: string;
  tourEssential?: boolean;
  badgeKey?: "queue" | "lab";
};

export type NavItem = {
  label: string;
  icon: React.ElementType;
  href?: string;
  badge?: string;
  /** Static badge marker (e.g. "AI"); live counts (queue/lab) are computed at render time in Sidebar.tsx. */
  badgeKey?: "queue" | "lab";
  roles?: string[];
  children?: NavChild[];
  aiPulse?: boolean;
  /** Short description shown in the role-based tour — omit for items the tour shouldn't surface as a step. */
  tourDescription?: string;
  /**
   * Marks a page as part of a role's daily spine. Used by tour-config.ts to
   * keep the first-run tour finite: role visibility is not the same thing as
   * onboarding priority, and an admin can see 42 pages. Non-essential pages
   * keep their tourDescription and stay reachable from the sidebar and from
   * the replayable full tour.
   */
  tourEssential?: boolean;
};

// Single source of truth for "which nav items / pages does this role see" — consumed
// by Sidebar.tsx for nav visibility and by tour-config.ts for the role-based walkthrough,
// so the two can never drift apart.
// Every page, defined once. NAV_ITEMS (below) arranges them into the sidebar's folders.
const PAGES: NavItem[] = [
  {
    label: "ROY Workstation",
    icon: LayoutDashboard,
    href: "/",
    tourDescription: "Your home base. Everything you have access to is one click away here, and the panels show what is happening across the hospital right now. If you get lost anywhere in the system, come back here.",
    tourEssential: true,
  },
  {
    label: "My Workspace",
    icon: Inbox,
    href: "/workspace",
    // Universal: every member of staff has one (their day, tasks, requests, messages,
    // work clock, leave and progress). Replaced the Staff Dashboard / Time Tracker /
    // Collaboration group, whose old links now redirect into its tabs.
    tourDescription: "Where your own work lives: what needs you today, tasks and reminders, requests from colleagues, messages, your work clock and leave. Items for your role - patients waiting, results to review, stock to act on - appear here too, and you can take one onto your list.",
    tourEssential: true,
  },

  // ── Hospital Operations (primary) ──────────────────────────────────
  {
    label: "Admin Dashboard",
    icon: LayoutDashboard,
    href: "/hospital/admin-dashboard",
    roles: ["admin", "management"],
    tourDescription: "The whole hospital at a glance — who is waiting, average wait time, bed occupancy, pending labs and prescriptions, plus alerts that need attention. Clinical numbers come first here, before financial ones.",
    tourEssential: true,
  },
  {
    label: "My Dashboard",
    icon: Stethoscope,
    href: "/hospital/doctor",
    roles: ["doctor", "admin", "management"],
    tourDescription: "Your own working day: the patients waiting for you, your appointments, and anything outstanding. Start here each morning rather than hunting through the queue.",
    tourEssential: true,
  },
  {
    label: "Nursing Station",
    icon: HeartPulse,
    href: "/hospital/nurse",
    roles: ["nurse", "admin", "ops", "doctor", "management", "physiotherapist"],
    tourDescription: "Your shift at a glance and the whole ward in one place — admission requests waiting on you, ward status, the active worklist, and the bedside record. Opening a patient gives you vitals, fluid balance, care plans and medication administration. The Notes tab holds their entire nursing record across every visit, and nursing notes are free text — you are not forced through a diagnosis.",
    tourEssential: true,
  },
  {
    label: "Front Desk",
    icon: ConciergeBell,
    href: "/hospital/front-desk",
    roles: ["admin", "ops", "receptionist", "management", "nurse"],
    tourDescription: "Check patients in, register a visit, and book appointments. Always search for the patient before creating a new one — nearly everyone is already here with years of history behind them, and a duplicate record splits that history in two.",
    tourEssential: true,
  },
  {
    label: "PCE / Patients",
    icon: Users,
    href: "/hospital/patients",
    roles: ["cashier", "hmo", "admin", "ops", "nurse", "doctor", "receptionist", "management", "physiotherapist"],
    tourDescription: "Search and open any patient's full record. Alongside today's visit you will find their history going back to 2016: past notes, lab results, imaging with reports, ward stays, immunisations and billing.",
    tourEssential: true,
  },
  {
    label: "Queue & Flow",
    icon: Activity,
    href: "/hospital/queue",
    badgeKey: "queue",
    roles: ["cashier", "hmo", "admin", "ops", "nurse", "doctor", "management", "physiotherapist"],
    tourDescription: "Everyone currently in the building — waiting, in triage, or with a doctor. Patients move through registered, triaged, nurse assessment, called, consulting, lab or pharmacy, billing, then discharged, and this page is the live view of that.",
    tourEssential: true,
  },
  {
    // "Diary" covers both halves: in a hospital the clinic diary IS the
    // appointment book, and your diary is your own day. One word, both
    // meanings, no explaining needed.
    //
    // Each child keeps its own roles — a receptionist books appointments but
    // has no place in the clinical task calendar, so grouping must not hand
    // them one or take the other away.
    label: "Diary",
    icon: CalendarCheck,
    roles: ["admin", "ops", "nurse", "doctor", "receptionist", "management"],
    tourDescription: "Appointments and your own schedule in one place. Marking a patient as arrived puts them straight onto the clinical queue — nobody needs to be told separately.",
    children: [
      {
        label: "Appointments",
        href: "/hospital/appointments",
        roles: ["admin", "ops", "nurse", "doctor", "receptionist", "management"],
      },
      {
        label: "My Schedule",
        href: "/calendar/tasks",
        roles: ["admin", "ops", "nurse", "doctor", "management"],
      },
    ],
  },
  {
    // reportGUide.md s10: one calendar over the real records; everyone sees the sources their roles open.
    label: "Hospital Calendar",
    icon: CalendarCheck,
    href: "/calendar",
    tourDescription: "Appointments, theatre, audits, equipment servicing, drugs expiring, staff leave, deliveries and HMO follow-ups on one calendar. Each entry is the real record - move it here and it moves on its own page too.",
  },
  {
    label: "Lab & Diagnostics",
    icon: FlaskConical,
    href: "/hospital/lab",
    badgeKey: "lab",
    roles: ["admin", "ops", "nurse", "doctor", "lab", "management"],
    tourDescription: "The lab worklist, where orders land the moment a doctor places them. Work a sample through collection, processing and result entry, then verify it — nothing reaches the requesting doctor until you do, which protects you as much as the patient.",
    tourEssential: true,
  },
  {
    // Three separate sidebar entries for one department read as three
    // departments. Grouped under one heading; every page keeps its own route,
    // so existing links and the tour are unaffected.
    label: "Pharmacy",
    icon: Pill,
    roles: ["store", "admin", "ops", "nurse", "doctor", "pharmacist", "management"],
    tourDescription: "Prescriptions waiting to be dispensed, arriving automatically from the consultation. Dosage, route and frequency are chosen from lists rather than typed. Note that allergy records start empty: the old system never held them, so an empty list means nothing was ever recorded, not that the patient has none.",
    tourEssential: true,
    children: [
      { label: "Dispensing",      href: "/hospital/pharmacy", roles: ["admin", "ops", "nurse", "doctor", "pharmacist", "management"] },
      { label: "Inventory",       href: "/hospital/pharmacy/inventory" },
      { label: "Department stores", href: "/hospital/stores", roles: ["store", "admin", "ops", "nurse", "doctor", "pharmacist", "management", "lab", "finance"] },
      { label: "Quality Control", href: "/quality-control", roles: ["admin", "ops", "pharmacist", "management", "quality_assurance"] },
    ],
  },
  {
    label: "Scancare (Radiology)",
    icon: ScanLine,
    href: "/hospital/radiology",
    roles: ["admin", "ops", "nurse", "doctor", "radiology", "management"],
    tourDescription: "The imaging worklist and report entry. New requests appear here as doctors place them; a patient's older imaging, including reports, sits on their chart rather than cluttering this list.",
    tourEssential: true,
  },
  {
    label: "Surgical Theatre",
    icon: Scissors,
    href: "/hospital/theatre",
    roles: ["admin", "ops", "nurse", "doctor", "management"],
    tourDescription: "Theatre bookings and the surgical diary. Book a case from the patient's consultation or here directly, choosing from the procedure catalogue so names and fees stay consistent.",
  },
  {
    label: "Specialist Clinics",
    icon: Stethoscope,
    href: "/hospital/specialist",
    roles: ["admin", "ops", "nurse", "doctor", "management"],
    tourDescription: "Structured note templates for specialist consultations, organised by specialty. Use these where a clinic has its own recognised format rather than a general SOAP note.",
  },
  {
    label: "MCH / OB-GYN",
    icon: HeartPulse,
    href: "/hospital/mch",
    roles: ["admin", "ops", "nurse", "doctor", "management"],
    tourDescription: "Antenatal care, delivery records and newborn assessment. Registering a baby here creates their own patient record linked to the mother, so the child has a chart from birth.",
  },
  {
    label: "Immunisation",
    icon: Syringe,
    href: "/hospital/immunisation",
    roles: ["admin", "ops", "nurse", "doctor", "management"],
    tourDescription: "Every baby on the immunisation programme with their schedule from birth to ten years. Shows what is due, what is overdue, and what has already been given.",
  },
  {
    label: "Digital Engagement",
    icon: MsgSquare,
    href: "/hospital/engagement",
    roles: ["admin", "ops", "management"],
    tourDescription: "Patient-facing communication — reminders, follow-ups and campaigns.",
  },
  {
    label: "Quality & Safety",
    icon: ShieldCheck,
    href: "/hospital/quality",
    roles: ["admin", "ops", "nurse", "doctor", "management", "quality_assurance"],
    tourDescription: "Incident reporting, infection control and HEFAMAA compliance. Report anything here rather than informally; the record is what protects the hospital and the staff involved.",
  },
  {
    // reportGUide.md s12: every report is written about one chosen record, from its facts only.
    // The server decides which kinds of record each role may report on; the analytics page stays.
    label: "Reports",
    icon: BarChart3,
    roles: ["auditor", "store", "cashier", "hmo", "admin", "management", "finance", "quality_assurance", "doctor", "nurse", "pharmacist", "ops", "receptionist"],
    tourDescription: "Write a report about one record - an incident, an audit, an HMO's account, a drug, a patient's encounter, a month. Everything recorded on it is gathered for you to review first, and the report is written only from that, with the record attached.",
    children: [
      { label: "Write a report", href: "/reports/new" },
      { label: "Report library", href: "/reports/library" },
      { label: "Analytics", href: "/hospital/reports", roles: ["admin", "management", "finance", "quality_assurance"] },
    ],
  },
  {
    label: "Wards & Beds",
    icon: BedDouble,
    href: "/hospital/wards",
    roles: ["admin", "ops", "nurse", "doctor", "management", "physiotherapist"],
    tourDescription: "Ward occupancy and bed assignment. Admit, transfer and discharge patients, and see at a glance which beds are free.",
  },
  {
    label: "Audits & Maintenance",
    icon: Wrench,
    href: "/hospital/audits-maintenance",
    roles: ["admin", "ops", "quality_assurance", "management"],
    tourDescription: "Facility audits, equipment servicing and maintenance schedules — the estate side of compliance.",
  },
  {
    label: "Compliance & Audits",
    icon: ShieldCheck,
    href: "/compliance",
    roles: ["admin", "quality_assurance", "management"],
    tourDescription: "Regulatory compliance and audit trails: NDPA, HEFAMAA and internal governance evidence.",
  },

  // ── Management & Admin (secondary) ────────────────────────────────
  {
    // The control centre (reportGUide.md s11): composed from every module's hub service, each
    // figure linking to the page that owns it. Finance reads it too, as the guide sets out.
    label: "Executive Overview",
    icon: BarChart3,
    href: "/executive",
    roles: ["auditor", "admin", "management", "finance"],
    tourDescription: "The hospital on one page: billing (HMO vs private), profit and cash from Roy Books, what HMOs owe, today's patients and beds, pharmacy stock, quality and staff - with a ranked list of what needs attention. Every figure opens the page that deals with it.",
  },
  {
    // Roy Books: the hospital's one finance hub, replacing Sage. Every screen that
    // records or shows money lives here - billing and the cashier, HMO cover and
    // tariffs as much as the ledger - so each fact has one home (ACE-Books.md s4).
    // The old Finance pages (analytics, reports, vendor payments, budget) duplicated
    // Roy Books screens and now redirect to them.
    label: "Finance",
    icon: BookOpen,
    roles: ["auditor", "store", "cashier", "hmo", "admin", "finance", "management", "pharmacist", "quality_assurance"],
    tourDescription: "The hospital's finance hub. Bills, cashier payments, HMO claims and pharmacy stock post here by themselves; this is where receivables, suppliers, the bank, the ledger, the financial statements and the month-end close live.",
    tourEssential: true,
    children: [
      { label: "Roy Books (Royan Hospital)", href: "/finance/books?company=RHL", roles: ["auditor", "admin", "finance", "management"] },
      { label: "Scancare Books",          href: "/finance/books?company=SCN", roles: ["auditor", "admin", "finance", "management"] },
      { label: "Billing & Cashier",       href: "/hospital/billing",         roles: ["auditor", "hmo", "cashier", "admin", "finance"] },
      { label: "Receivables (Patients & HMOs)", href: "/finance/books/sales", roles: ["auditor", "cashier", "hmo", "admin", "finance", "management"] },
      { label: "HMO Desk & Coverage",     href: "/hospital/hmo",             roles: ["auditor", "hmo", "admin", "finance", "management"] },
      { label: "Credit Control & Alerts", href: "/finance/ar",               roles: ["auditor", "admin", "finance", "management"] },
      { label: "Purchases & Payables",    href: "/finance/books/purchases",  roles: ["auditor", "admin", "finance", "management"] },
      { label: "Stock & Pharmacy Valuation", href: "/finance/books/stock",   roles: ["auditor", "store", "admin", "finance", "management", "pharmacist", "quality_assurance"] },
      { label: "Banking",                 href: "/finance/books/banking",    roles: ["auditor", "admin", "finance", "management"] },
      { label: "Journals & Ledger",       href: "/finance/books/ledger",     roles: ["auditor", "admin", "finance", "management"] },
      { label: "Financial Statements",    href: "/finance/books/statements", roles: ["auditor", "admin", "finance", "management"] },
      { label: "Report Center",           href: "/finance/books/reports",    roles: ["auditor", "admin", "finance", "management"] },
      { label: "Fixed Assets",            href: "/finance/books/assets",     roles: ["auditor", "admin", "finance", "management"] },
      { label: "Close & Controls",        href: "/finance/books/close",      roles: ["auditor", "admin", "finance", "management"] },
      { label: "Fee Schedule",            href: "/admin/fee-schedule",       roles: ["admin", "finance"] },
      { label: "Payment Gateway",         href: "/admin/payments",           roles: ["admin", "finance"] },
      { label: "Setup",                   href: "/finance/books/setup",      roles: ["admin", "finance", "management"] },
    ],
  },
  {
    label: "HR",
    icon: Users,
    href: "/hr",
    // Union of the two entries that were merged here: "management" could reach
    // the shift roster on /hospital/hr and must not lose it.
    roles: ["admin", "hr", "management"],
    tourDescription: "Staff records, shift roster, leave requests, timesheets and payroll — all six in one place.",
  },
  {
    // reportGUide.md s6: what to order (from real use), stock orders that close when the stock
    // arrives, and suppliers with what we buy from each.
    label: "Procurement & Stores",
    icon: Package,
    roles: ["auditor", "store", "admin", "ops", "pharmacist", "finance", "quality_assurance", "management"],
    tourDescription: "What to order and when, worked out from what the pharmacy actually uses; stock orders from request to delivery (they close by themselves when the stock is received); and who we buy from.",
    children: [
      { label: "Reorder plan & orders", href: "/procurement" },
      { label: "Supplier records", href: "/operations/suppliers", roles: ["admin", "ops"] },
    ],
  },
  {
    // reportGUide.md s7: CRM for a hospital - the HMO and corporate payers.
    label: "Patient Relations",
    icon: Building2,
    href: "/relations",
    roles: ["admin", "finance", "management"],
    tourDescription: "Every HMO and corporate payer: what we bill them and for which services, what they owe and how late, who is slipping, and the calls and follow-ups with each. Follow-ups you set appear on your My Day.",
  },
  {
    label: "Workflow",
    icon: Workflow,
    href: "/workflow",
    roles: ["admin"],
    tourDescription: "Automated processes and their current state — useful for seeing why something moved on its own.",
  },
  {
    label: "User Access",
    icon: Shield,
    href: "/admin/users",
    roles: ["admin"],
    tourDescription: "Create staff accounts and set roles. Roles decide which pages a person sees, so a nurse and a pharmacist looking at this system see genuinely different menus.",
  },
  {
    label: "Staff Registrations",
    icon: Users,
    href: "/admin/registrations",
    roles: ["admin"],
    tourDescription: "Approve or decline staff who have registered themselves and are waiting for access.",
  },
  {
    label: "Reliability Console",
    icon: Bug,
    href: "/admin/reliability",
    roles: ["admin"],
    tourDescription: "System health, error tracking and reliability signals — the first place to look if something is behaving oddly.",
  },
  {
    label: "Clinical Data Explorer",
    icon: Database,
    href: "/admin/clinical-explorer",
    roles: ["admin", "management", "ops"],
    tourDescription: "Query clinical data directly across the record, including everything migrated from the old system. Read-only.",
  },
  {
    label: "Audit Log",
    icon: ClipboardList,
    href: "/admin/audit-log",
    roles: ["admin"],
    tourDescription: "Who did what and when, across the system. Clinical notes cannot be edited or deleted by anyone, and this is where every other action is recorded.",
  },

  // ── AI & Tools ─────────────────────────────────────────────────────
  {
    label: "Ask Synbot",
    icon: MessageSquare,
    href: "/synbot",
    badge: "AI",
    aiPulse: true,
    tourDescription: "Ask Roy about patients, schedules, stock, or anything in your area. Roy knows the hospital's data and your role, and can send emails, create tasks and generate reports on request.",
    tourEssential: true,
  },
  {
    label: "Agent Stack",
    icon: Bot,
    href: "/agents",
    badge: "AI",
    aiPulse: true,
    roles: ["admin", "management"],
    tourDescription: "The automated agents running behind the scenes and what each one monitors.",
  },

  {
    label: "Settings",
    icon: Settings,
    href: "/settings",
    roles: ["admin"],
    tourDescription: "Your profile, preferences and notification settings.",
  },
];

// ---------------------------------------------------------------------------
// The sidebar: pages grouped by the job a person does (reportGUide.md s2.2), so the
// menu is a short list of folders rather than ~35 standalone pages. Every page keeps
// its own definition above (roles, tour text, badge) and is placed by label, so the
// grouping cannot drift from what each page allows.
// ---------------------------------------------------------------------------

function page(label: string): NavItem {
  const p = PAGES.find((x) => x.label === label);
  if (!p) throw new Error(`nav-items: no page "${label}"`);
  return p;
}

/** A page as a child of a folder, carrying its roles, tour text and badge. */
function child(label: string, over: Partial<NavChild> = {}): NavChild {
  const p = page(label);
  return {
    label: p.label, href: p.href as string, roles: p.roles, tourDescription: p.tourDescription,
    tourEssential: p.tourEssential, badgeKey: p.badgeKey, ...over,
  };
}

/** The roles that can see at least one child (undefined = someone with any role can). */
function unionRoles(children: NavChild[], parentRoles?: string[]): string[] | undefined {
  const sets = children.map((c) => c.roles ?? parentRoles);
  if (sets.some((s) => !s)) return undefined;
  return Array.from(new Set(sets.flat() as string[]));
}

function folder(label: string, icon: React.ElementType, tourDescription: string, children: NavChild[], extra: Partial<NavItem> = {}): NavItem {
  return { label, icon, tourDescription, children, roles: unionRoles(children), ...extra };
}

const diary = page("Diary").children ?? [];
const pharmacy = page("Pharmacy");
const procurement = page("Procurement & Stores").children ?? [];

// The sidebar: home (ROY Workstation) first, then every section A-Z so people can find what they are looking for
// (Oct 2026). Pages inside a section keep the order they are listed in below.
const SECTIONS: NavItem[] = [

  // Everyone's own day. Doctors and nurses get their clinical home (patients / the ward) with the
  // workspace built in, so they do not also see a separate My Workspace; everyone else does.
  folder("My Workspace", Inbox,
    "Your own day in one place: your patients or ward if you are clinical, then what needs you today, tasks and reminders, requests from colleagues, messages, your work clock and leave - plus your own appointments and schedule.",
    [
      child("My Dashboard", { roles: ["doctor", "admin", "management"], showFor: ["doctor"] }),
      child("Nursing Station", { showFor: ["nurse", "physiotherapist"] }),
      child("My Workspace", { label: "Tasks, inbox & messages", hideFor: ["doctor", "nurse", "physiotherapist"] }),
      // Appointments and My Schedule are personal: a doctor sees the patients booked to them, and My
      // Schedule is your own appointments, tasks and events. The whole hospital is the Hospital Calendar.
      ...diary.map((d) => ({ ...d, roles: d.roles ?? page("Diary").roles })),
    ]),

  folder("Patients & Flow", Users,
    "Check patients in at the front desk, open any patient's full record, follow everyone through the queue, and manage ward beds.",
    [child("Front Desk"), child("PCE / Patients", { label: "Patients (PCE)" }), child("Queue & Flow"), child("Wards & Beds")]),

  folder("Clinical Services", Stethoscope,
    "The departments a patient is sent to: lab, imaging, theatre, specialist clinics, maternity and immunisation.",
    [child("Lab & Diagnostics"), child("Surgical Theatre"), child("Specialist Clinics"), child("MCH / OB-GYN"), child("Immunisation")]),

  folder("Pharmacy", pharmacy.icon, pharmacy.tourDescription as string,
    [...(pharmacy.children ?? []).map((c) => ({ ...c, roles: c.roles ?? pharmacy.roles })),
     ...procurement.map((c) => ({ ...c, roles: c.roles ?? page("Procurement & Stores").roles }))],
    { tourEssential: true }),

  folder("Quality & Compliance", ShieldCheck,
    "Incidents, infection control and HEFAMAA, facility audits and equipment maintenance, and regulatory compliance evidence.",
    [child("Quality & Safety"), child("Audits & Maintenance"), child("Compliance & Audits", { label: "Compliance (NDPA / HEFAMAA)" })]),

  page("Reports"),

  folder("Management", BarChart3,
    "The hospital at a glance for management: the executive overview, the admin dashboard, HMO and corporate accounts, patient engagement and the clinical data explorer.",
    [child("Executive Overview"), child("Admin Dashboard"), child("Patient Relations"), child("Digital Engagement"), child("Clinical Data Explorer")]),

  // Standalone: everything happening across the hospital, for management and the teams that run it.
  { ...page("Hospital Calendar"), roles: ["admin", "management", "ops", "quality_assurance", "hr", "finance"] },

  page("Scancare (Radiology)"),
  page("Finance"),
  page("HR"),

  folder("Users & Access", Shield,
    "Create logins and set roles, approve staff who registered themselves, and see who did what.",
    [child("User Access"), child("Staff Registrations"), child("Audit Log")]),

  folder("System", Settings,
    "Workflows, system health, the automated agents and settings.",
    [child("Workflow"), child("Reliability Console"), child("Agent Stack"), child("Settings")]),

  page("Ask Synbot"),
];

export const NAV_ITEMS: NavItem[] = [
  page("ROY Workstation"),
  ...[...SECTIONS].sort((x, y) => x.label.localeCompare(y.label, "en", { sensitivity: "base" })),
];
