import { NAV_ITEMS } from "@/lib/nav-items";
import { canViewByRoles } from "@/lib/nav-access";

export type TourStep = {
  label: string;
  href: string;
  description: string;
  icon: React.ElementType;
};

/**
 * Builds a role's tour steps directly from NAV_ITEMS — the same array that
 * drives Sidebar.tsx's nav visibility — so the tour can never show a page
 * the sidebar doesn't actually expose for that role, and vice versa.
 */
export function getTourStepsForRole(role: string): TourStep[] {
  return NAV_ITEMS.filter(
    (item) =>
      !!item.href &&
      !!item.tourDescription &&
      canViewByRoles([role], item.roles),
  ).map((item) => ({
    label: item.label,
    href: item.href as string,
    description: item.tourDescription as string,
    icon: item.icon,
  }));
}
