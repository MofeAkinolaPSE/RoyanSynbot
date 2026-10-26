import { Compass } from "lucide-react";
import { NAV_ITEMS } from "@/lib/nav-items";
import { canViewByRoles, getNavEntryByHref, menuChildren, resolveRouteRoles } from "@/lib/nav-access";
import { getDayTour } from "@/lib/day-tours";

export type TourStep = {
  label: string;
  href: string;
  description: string;
  icon: React.ElementType;
  /** What to press on that page (day tours). */
  points?: string[];
  /** The page's name in the menu, shown so people learn where it lives. */
  page?: string;
};

/**
 * Above this many steps, a first-run tour stops being an introduction and
 * starts being an endurance test — people skip it, and skipping is sticky.
 * Roles over the threshold get only their daily spine (tourEssential); roles
 * under it get everything they can see, because for a lab scientist with three
 * pages the "full" tour is already short.
 */
const MAX_INTRO_STEPS = 8;

type StepSource = { label: string; href: string; tourDescription: string; tourEssential?: boolean; icon: React.ElementType };

// Pages now sit inside folders, so steps come from top-level pages AND folder children - with the
// same access and menu-placement rules as the sidebar, so the tour never shows what the menu hides.
function visibleStepsForRole(role: string): StepSource[] {
  const out: StepSource[] = [];
  for (const item of NAV_ITEMS) {
    if (item.children) {
      for (const c of menuChildren([role], item)) {
        if (c.tourDescription) out.push({ label: c.label, href: c.href, tourDescription: c.tourDescription, tourEssential: c.tourEssential, icon: item.icon });
      }
    } else if (item.href && item.tourDescription && canViewByRoles([role], item.roles)) {
      out.push({ label: item.label, href: item.href, tourDescription: item.tourDescription, tourEssential: item.tourEssential, icon: item.icon });
    }
  }
  return out;
}

function toStep(item: StepSource): TourStep {
  return { label: item.label, href: item.href, description: item.tourDescription, icon: item.icon };
}

/**
 * Builds a role's tour steps from NAV_ITEMS — the same array that drives
 * Sidebar.tsx's nav visibility — so the tour can never show a page the sidebar
 * doesn't expose for that role, and vice versa.
 *
 * `full: true` returns every page that role can see, for the replayable
 * "take the tour again" path. The default (first run) is trimmed to the daily
 * spine so the introduction stays finite: an admin can see 42 pages, which is
 * a reference list, not an onboarding.
 */
export function getTourStepsForRole(role: string, opts?: { full?: boolean }): TourStep[] {
  // First sign-in: a typical day in this role (day-tours.ts), never a page the role cannot open.
  const day = !opts?.full ? getDayTour(role) : undefined;
  if (day?.length) {
    return day
      .filter((d) => canViewByRoles([role], resolveRouteRoles(d.href.split("?")[0])))
      .map((d) => {
        const nav = getNavEntryByHref(d.href) ?? getNavEntryByHref(d.href.split("?")[0]);
        return { label: d.title, href: d.href, description: d.body, points: d.points, page: nav?.label ?? (d.href === "/" ? "ROY Workstation" : undefined),
                 icon: nav?.icon ?? Compass };
      });
  }
  const visible = visibleStepsForRole(role);

  if (opts?.full || visible.length <= MAX_INTRO_STEPS) {
    return visible.map(toStep);
  }

  const essential = visible.filter((item) => item.tourEssential);
  // If a role somehow has nothing marked essential, showing a long tour beats
  // showing none at all.
  return (essential.length > 0 ? essential : visible).map(toStep);
}

/** Every page a role can see — used by the replayable tour and any "all pages" listing. */
export function getFullTourStepsForRole(role: string): TourStep[] {
  return getTourStepsForRole(role, { full: true });
}

/**
 * Roles offered in the admin "Preview onboarding" panel.
 *
 * Kept here rather than in the component so a spec can check it against the
 * roles nav-items actually uses — otherwise a role added to the nav later
 * quietly becomes impossible to preview, which is exactly the kind of gap
 * nobody notices until a new starter reports a broken first login.
 */
export const PREVIEW_ROLES: { value: string; label: string }[] = [
  { value: "doctor", label: "Doctor" },
  { value: "nurse", label: "Nurse" },
  { value: "pharmacist", label: "Pharmacist" },
  { value: "lab", label: "Laboratory" },
  { value: "radiology", label: "Radiology" },
  { value: "receptionist", label: "Front desk" },
  { value: "finance", label: "Finance" },
  { value: "quality_assurance", label: "Quality assurance" },
  { value: "physiotherapist", label: "Physiotherapy" },
  { value: "hr", label: "HR" },
  { value: "management", label: "Management" },
  { value: "ops", label: "Operations" },
  { value: "hmo", label: "HMO officer" },
  { value: "cashier", label: "Billing & cashier" },
  { value: "store", label: "Stores" },
  { value: "auditor", label: "Auditor" },
  { value: "admin", label: "Administrator" },
];
