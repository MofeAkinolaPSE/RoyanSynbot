/**
 * A person given every role on User Access (Royan's chiefs) must reach every page and see every menu entry.
 * Roles widen access; none of them takes a page away. Mirrors backend/src/roles.py ROLE_CATALOG.
 */
import { describe, expect, it } from "vitest";
import { NAV_ITEMS, type NavItem } from "@/lib/nav-items";
import { canViewByRoles, flattenNavItems, menuChildren, resolveRouteRoles, shownInMenu } from "@/lib/nav-access";

const EVERY_ROLE = ["doctor", "nurse", "pharmacist", "lab", "radiology", "physiotherapist", "receptionist", "finance", "hr",
  "ops", "quality_assurance", "hmo", "cashier", "store", "auditor", "management", "admin"];

describe("every role ticked on User Access", () => {
  it("can open every page", () => {
    const blocked = flattenNavItems().filter((e) => !canViewByRoles(EVERY_ROLE, e.roles)).map((e) => e.href);
    expect(blocked).toEqual([]);
  });

  it("sees every entry in the menu", () => {
    const hidden: string[] = [];
    for (const item of NAV_ITEMS as NavItem[]) {
      if (!item.children) {
        if (!canViewByRoles(EVERY_ROLE, item.roles) || !shownInMenu(EVERY_ROLE, item as any)) hidden.push(item.label);
        continue;
      }
      const shown = new Set(menuChildren(EVERY_ROLE, item).map((c) => c.label));
      for (const c of item.children) if (!shown.has(c.label)) hidden.push(`${item.label} > ${c.label}`);
    }
    expect(hidden).toEqual([]);
  });

  it("every role the menu mentions is one User Access offers", () => {
    const used = new Set<string>();
    for (const item of NAV_ITEMS as NavItem[]) {
      (item.roles ?? []).forEach((r) => used.add(r));
      (item.children ?? []).forEach((c) => (c.roles ?? []).forEach((r) => used.add(r)));
    }
    expect([...used].filter((r) => !EVERY_ROLE.includes(r) && r !== "viewer")).toEqual([]);
  });

  it("a doctor alone still gets the tidy clinical menu", () => {
    expect(shownInMenu(["doctor"], { hideFor: ["doctor", "nurse", "physiotherapist"] })).toBe(false);
    expect(shownInMenu(["doctor", "management"], { hideFor: ["doctor", "nurse", "physiotherapist"] })).toBe(true);
  });

  it("detail pages follow their section (e.g. a patient's record)", () => {
    expect(canViewByRoles(EVERY_ROLE, resolveRouteRoles("/hospital/patients/RH16-1557"))).toBe(true);
  });
});
