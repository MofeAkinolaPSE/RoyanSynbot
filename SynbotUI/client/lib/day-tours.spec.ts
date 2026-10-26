import { describe, expect, it } from "vitest";
import { DAY_TOUR_ROLES, getDayTour, primaryTourRole } from "@/lib/day-tours";
import { canViewByRoles, resolveRouteRoles } from "@/lib/nav-access";
import { getTourStepsForRole, PREVIEW_ROLES } from "@/lib/tour-config";

/**
 * The first sign-in tour is a typical day in each role. It rots in two quiet ways: a role nobody wrote a day for
 * (they get the old page list), and a step pointing at a page the role cannot open (the tour bounces them).
 */
describe("day tours", () => {
  it("every role offered on User Access has a day", () => {
    const missing = PREVIEW_ROLES.map((r) => r.value).filter((r) => !getDayTour(r)?.length);
    expect(missing).toEqual([]);
  });

  it("every step opens a page that role can open", () => {
    const bad: string[] = [];
    for (const role of DAY_TOUR_ROLES) {
      for (const step of getDayTour(role) ?? []) {
        if (!canViewByRoles([role], resolveRouteRoles(step.href.split("?")[0]))) bad.push(`${role}: ${step.title} -> ${step.href}`);
      }
    }
    expect(bad).toEqual([]);
  });

  it("the tour shown is the day, not the page list", () => {
    for (const role of DAY_TOUR_ROLES) {
      expect(getTourStepsForRole(role).length, role).toBe(getDayTour(role)!.length);
    }
  });

  it("steps say something useful", () => {
    for (const role of DAY_TOUR_ROLES) {
      for (const s of getDayTour(role)!) {
        expect(s.title.trim().length, `${role}: title`).toBeGreaterThan(5);
        expect(s.body.trim().length, `${role}: ${s.title}`).toBeGreaterThan(30);
      }
    }
  });

  it("a person with several roles gets their most senior role's day", () => {
    expect(primaryTourRole(["cashier", "management", "doctor"])).toBe("management");
    expect(primaryTourRole(["auditor", "nurse"])).toBe("nurse");
    expect(primaryTourRole(["receptionist"])).toBe("receptionist");
  });

  it("management sees the whole hospital", () => {
    const pages = new Set((getDayTour("management") ?? []).map((s) => s.href.split("?")[0]));
    for (const p of ["/executive", "/hospital/queue", "/hospital/front-desk", "/hospital/doctor", "/hospital/lab", "/hospital/pharmacy",
                     "/hospital/hmo", "/finance/books", "/hr", "/hospital/quality", "/calendar", "/reports/new"]) {
      expect(pages.has(p), p).toBe(true);
    }
  });
});
