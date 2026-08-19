// Presentation-only curation for the ROY Workstation (root "/" page) — which
// of a role's *available* pages get featured as quick-access cards, and
// which role's metric block wins when a user holds more than one role.
//
// IMPORTANT: this is a curation layer, not an access-control layer. At
// render time, Workstation.tsx always intersects WORKSTATION_FEATURED with
// the real nav-items.ts role check (via canViewByRoles) before showing a
// card — so a stale or wrong entry here can only make a card silently fail
// to appear (fail closed), never grant a card to a role that shouldn't see
// it. The actual RBAC guarantee lives in nav-items.ts + nav-access.ts.

// Priority order used to pick ONE metric block when a user holds multiple
// roles (e.g. a nurse who is also management) — most senior/specific first,
// so the page doesn't stack every role's metrics on top of each other.
export const ROLE_PRIORITY = [
  "admin",
  "management",
  "doctor",
  "nurse",
  "finance",
  "hr",
  "quality_assurance",
  "lab",
  "radiology",
  "pharmacist",
  "receptionist",
  "ops",
  "physiotherapist",
] as const;

export type RoleKey = (typeof ROLE_PRIORITY)[number];

export function resolvePrimaryRole(userRoles: string[]): RoleKey | null {
  for (const role of ROLE_PRIORITY) {
    if (userRoles.includes(role)) return role;
  }
  return null;
}

// Featured quick-access hrefs per role — a curated subset of what that role
// can already see in the sidebar, not the full sidebar dumped as cards.
export const WORKSTATION_FEATURED: Record<RoleKey, string[]> = {
  admin: [
    "/hospital/admin-dashboard", "/hospital/patients", "/hospital/queue",
    "/hospital/billing", "/hospital/hr", "/hospital/quality", "/admin/registrations",
  ],
  management: [
    "/hospital/admin-dashboard", "/executive", "/hospital/patients",
    "/hospital/queue", "/hospital/hr", "/hospital/reports",
  ],
  doctor: [
    "/hospital/doctor", "/hospital/patients", "/hospital/queue",
    "/hospital/appointments", "/hospital/lab", "/calendar/tasks",
  ],
  nurse: [
    "/hospital/nurse", "/hospital/patients", "/hospital/queue",
    "/hospital/wards", "/hospital/nursing",
  ],
  lab: ["/hospital/lab", "/hospital/patients", "/hospital/queue"],
  radiology: ["/hospital/radiology", "/hospital/patients", "/hospital/queue"],
  pharmacist: ["/hospital/pharmacy", "/hospital/pharmacy/inventory", "/hospital/patients"],
  finance: ["/hospital/billing", "/hospital/hmo", "/admin/fee-schedule", "/hospital/reports"],
  hr: ["/hospital/hr", "/hr", "/staff/dashboard"],
  quality_assurance: [
    "/hospital/quality", "/compliance", "/hospital/audits-maintenance", "/hospital/reports",
  ],
  receptionist: ["/hospital/front-desk", "/hospital/appointments", "/hospital/patients"],
  ops: [
    "/hospital/queue", "/hospital/wards", "/hospital/audits-maintenance",
    "/operations/suppliers", "/hospital/engagement",
  ],
  physiotherapist: ["/hospital/patients", "/hospital/queue", "/hospital/wards", "/hospital/nursing"],
};
