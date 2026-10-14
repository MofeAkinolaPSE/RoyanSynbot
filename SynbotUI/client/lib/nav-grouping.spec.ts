import { describe, expect, it } from "vitest";
import { visibleNav } from "./nav-access";

const menu = (...roles: string[]) => visibleNav(roles);
const folder = (roles: string[], label: string) => menu(...roles).find((n) => n.label === label);

describe("sidebar grouping", () => {
  it("prints each role's menu", () => {
    for (const r of ["doctor", "nurse", "pharmacist", "receptionist", "finance", "hr", "admin"]) {
      console.log(`\n${r}:\n` + menu(r).map((n) => `  ${n.label}${n.children.length ? ` - ${n.children.join(", ")}` : ""}`).join("\n"));
    }
  });

  it("gives doctors and nurses one clinical home with the workspace built in", () => {
    const doc = folder(["doctor"], "My Workspace")!.children;
    expect(doc).toContain("My Dashboard");
    expect(doc).not.toContain("Tasks, inbox & messages");
    expect(doc).toEqual(expect.arrayContaining(["Appointments", "My Schedule"]));
    expect(doc).not.toContain("Hospital Calendar");                       // personal folder only
    expect(menu("doctor").map((n) => n.label)).not.toContain("Hospital Calendar");
    expect(menu("management").map((n) => n.label)).toContain("Hospital Calendar");
    const nurse = folder(["nurse"], "My Workspace")!.children;
    expect(nurse).toContain("Nursing Station");
    expect(nurse).not.toContain("My Dashboard");
    expect(nurse).not.toContain("Tasks, inbox & messages");
    expect(folder(["pharmacist"], "My Workspace")!.children).toContain("Tasks, inbox & messages");
  });

  it("puts procurement under pharmacy and the quality pages together", () => {
    expect(folder(["pharmacist"], "Pharmacy")!.children).toEqual(expect.arrayContaining(["Dispensing", "Inventory", "Reorder plan & orders"]));
    expect(folder(["admin"], "Quality & Compliance")!.children).toHaveLength(3);
    expect(folder(["admin"], "Users & Access")!.children).toEqual(["User Access", "Staff Registrations", "Audit Log"]);
    expect(folder(["doctor"], "Users & Access")).toBeUndefined();
  });

  it("keeps the top level short", () => {
    // 15: Scancare is a separate business with its own top-level entry (finance meeting, Oct 2026)
    expect(menu("admin").length).toBeLessThanOrEqual(15);
    expect(menu("doctor").length).toBeLessThanOrEqual(10);
  });
});
