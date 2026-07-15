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
} from "lucide-react";

export type NavChild = { label: string; href: string };

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
};

// Single source of truth for "which nav items / pages does this role see" — consumed
// by Sidebar.tsx for nav visibility and by tour-config.ts for the role-based walkthrough,
// so the two can never drift apart.
export const NAV_ITEMS: NavItem[] = [
  {
    label: "Dashboard",
    icon: LayoutDashboard,
    href: "/",
    tourDescription: "Your home base — a live overview of what's happening across the hospital.",
  },

  // ── Hospital Operations (primary) ──────────────────────────────────
  {
    label: "Admin Dashboard",
    icon: LayoutDashboard,
    href: "/hospital/admin-dashboard",
    roles: ["admin", "management"],
    tourDescription: "Hospital-wide KPIs, alerts, and operational health at a glance.",
  },
  {
    label: "My Dashboard",
    icon: Stethoscope,
    href: "/hospital/doctor",
    roles: ["doctor", "admin", "management"],
    tourDescription: "Your patient queue, appointments, and clinical tasks for the day.",
  },
  {
    label: "Nurse Dashboard",
    icon: HeartPulse,
    href: "/hospital/nurse",
    roles: ["nurse", "admin"],
    tourDescription: "Ward status, patient assignments, and vitals entry for your shift.",
  },
  {
    label: "Front Desk",
    icon: ConciergeBell,
    href: "/hospital/front-desk",
    roles: ["admin", "ops", "receptionist", "management", "nurse"],
    tourDescription: "Patient check-in, registration, and appointment scheduling.",
  },
  {
    label: "CPRS / Patients",
    icon: Users,
    href: "/hospital/patients",
    roles: ["admin", "ops", "nurse", "doctor", "receptionist", "management"],
    tourDescription: "Search and open any patient's full clinical record.",
  },
  {
    label: "Queue & Flow",
    icon: Activity,
    href: "/hospital/queue",
    badgeKey: "queue",
    roles: ["admin", "ops", "nurse", "doctor", "management"],
    tourDescription: "See who's waiting, in triage, or in consultation right now.",
  },
  {
    label: "Appointments",
    icon: CalendarCheck,
    href: "/hospital/appointments",
    roles: ["admin", "ops", "nurse", "doctor", "receptionist", "management"],
    tourDescription: "Book, view, and manage patient appointments.",
  },
  {
    label: "Lab & Diagnostics",
    icon: FlaskConical,
    href: "/hospital/lab",
    badgeKey: "lab",
    roles: ["admin", "ops", "nurse", "doctor", "lab", "management"],
    tourDescription: "Order tests, track pending results, and review lab reports.",
  },
  {
    label: "Pharmacy",
    icon: Pill,
    href: "/hospital/pharmacy",
    roles: ["admin", "ops", "nurse", "doctor", "pharmacist", "management"],
    tourDescription: "Dispense prescriptions and track drug stock levels.",
  },
  {
    label: "Nursing Station",
    icon: Activity,
    href: "/hospital/nursing",
    roles: ["admin", "ops", "nurse", "doctor", "management"],
    tourDescription: "Nursing notes, handovers, and care plan documentation.",
  },
  {
    label: "Radiology",
    icon: ScanLine,
    href: "/hospital/radiology",
    roles: ["admin", "ops", "nurse", "doctor", "radiology", "management"],
    tourDescription: "Imaging worklist, report entry, and pending reviews.",
  },
  {
    label: "Surgical Theatre",
    icon: Scissors,
    href: "/hospital/theatre",
    roles: ["admin", "ops", "nurse", "doctor", "management"],
  },
  {
    label: "Specialist Clinics",
    icon: Stethoscope,
    href: "/hospital/specialist",
    roles: ["admin", "ops", "nurse", "doctor", "management"],
  },
  {
    label: "MCH / OB-GYN",
    icon: HeartPulse,
    href: "/hospital/mch",
    roles: ["admin", "ops", "nurse", "doctor", "management"],
  },
  {
    label: "Digital Engagement",
    icon: MsgSquare,
    href: "/hospital/engagement",
    roles: ["admin", "ops", "management"],
  },
  {
    label: "Quality & Safety",
    icon: ShieldCheck,
    href: "/hospital/quality",
    roles: ["admin", "ops", "nurse", "doctor", "management", "quality_assurance"],
  },
  {
    label: "HR — Shifts",
    icon: Users,
    href: "/hospital/hr",
    roles: ["admin", "hr", "management"],
  },
  {
    label: "Reports & Analytics",
    icon: BarChart3,
    href: "/hospital/reports",
    roles: ["admin", "management", "finance", "quality_assurance"],
  },
  {
    label: "Scheduling",
    icon: CalendarCheck,
    href: "/calendar/tasks",
    roles: ["admin", "ops", "nurse", "doctor", "management"],
  },
  {
    label: "Wards & Beds",
    icon: BedDouble,
    href: "/hospital/wards",
    roles: ["admin", "ops", "nurse", "doctor", "management"],
  },
  {
    label: "Compliance & Audits",
    icon: ShieldCheck,
    href: "/compliance",
    roles: ["admin", "quality_assurance", "management"],
  },
  {
    label: "Billing",
    icon: Receipt,
    href: "/hospital/billing",
    roles: ["admin", "finance"],
    tourDescription: "Patient bills, HMO claims, and revenue reconciliation.",
  },
  {
    label: "HMO & Coverage",
    icon: Building2,
    href: "/hospital/hmo",
    roles: ["admin", "finance"],
  },

  // ── Management & Admin (secondary) ────────────────────────────────
  {
    label: "Executive Summary",
    icon: BarChart3,
    href: "/executive",
    roles: ["admin", "management"],
    tourDescription: "High-level hospital performance — revenue, patient flow, KPIs.",
  },
  {
    label: "Finance",
    icon: DollarSign,
    roles: ["admin", "finance"],
    children: [
      { label: "Analytics",        href: "/finance/analytics" },
      { label: "Reports",          href: "/finance/reports" },
      { label: "AR & Alerts",      href: "/finance/ar" },
      { label: "Vendor Payments",  href: "/finance/vendor-payments" },
      { label: "Budget",           href: "/finance/budget" },
    ],
  },
  {
    label: "HR",
    icon: Users,
    href: "/hr",
    roles: ["admin", "hr"],
    tourDescription: "Manage staff records, shifts, timesheets, and payroll summaries.",
  },
  {
    label: "Staff Dashboard",
    icon: ClipboardList,
    roles: ["admin", "hr", "ops", "management"],
    children: [
      { label: "Dashboard",     href: "/staff/dashboard" },
      { label: "Time Tracker",  href: "/staff/time-tracker" },
      { label: "Collaboration", href: "/staff/collaboration" },
    ],
  },
  {
    label: "Procurement",
    icon: Package,
    href: "/operations/suppliers",
    roles: ["admin", "ops"],
  },
  {
    label: "Workflow",
    icon: Workflow,
    href: "/workflow",
    roles: ["admin"],
  },
  {
    label: "User Access",
    icon: Shield,
    href: "/admin/users",
    roles: ["admin"],
  },
  {
    label: "Staff Registrations",
    icon: Users,
    href: "/admin/registrations",
    roles: ["admin"],
  },
  {
    label: "Reliability Console",
    icon: Bug,
    href: "/admin/reliability",
    roles: ["admin"],
  },
  {
    label: "Clinical Data Explorer",
    icon: Database,
    href: "/admin/clinical-explorer",
    roles: ["admin", "management", "ops"],
  },
  {
    label: "Fee Schedule",
    icon: DollarSign,
    href: "/admin/fee-schedule",
    roles: ["admin", "finance"],
  },
  {
    label: "Payment Gateway",
    icon: CreditCard,
    href: "/admin/payments",
    roles: ["admin", "finance"],
  },
  {
    label: "Audit Log",
    icon: ClipboardList,
    href: "/admin/audit-log",
    roles: ["admin"],
  },

  // ── AI & Tools ─────────────────────────────────────────────────────
  {
    label: "Ask Synbot",
    icon: MessageSquare,
    href: "/synbot",
    badge: "AI",
    aiPulse: true,
    tourDescription: "Chat with Roy — ask about patients, appointments, tasks, or anything role-specific.",
  },
  {
    label: "Agent Stack",
    icon: Bot,
    href: "/agents",
    badge: "AI",
    aiPulse: true,
    roles: ["admin", "management"],
  },

  {
    label: "Settings",
    icon: Settings,
    href: "/settings",
    roles: ["admin"],
  },
];
