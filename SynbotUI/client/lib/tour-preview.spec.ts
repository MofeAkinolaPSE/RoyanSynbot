import { describe, it, expect } from "vitest";
import { PREVIEW_ROLES, getTourStepsForRole } from "./tour-config";
import { NAV_ITEMS } from "./nav-items";

/**
 * The admin "Preview onboarding" panel is the only place anyone sees what a new
 * starter meets, so it has to stay honest about which roles exist. A role added
 * to the nav but missing here becomes impossible to preview, and nobody finds
 * out until a new starter reports an empty first login.
 */

function rolesUsedInNav(): Set<string> {
  const out = new Set<string>();
  for (const item of NAV_ITEMS) {
    for (const r of item.roles ?? []) out.add(r);
  }
  return out;
}

describe("tour preview roles", () => {
  it("has no duplicates and no blank labels", () => {
    const values = PREVIEW_ROLES.map((r) => r.value);
    expect(new Set(values).size).toBe(values.length);
    for (const r of PREVIEW_ROLES) expect(r.label.trim(), r.value).not.toBe("");
  });

  it("only offers roles the nav actually recognises", () => {
    const known = rolesUsedInNav();
    const unknown = PREVIEW_ROLES.map((r) => r.value).filter((v) => !known.has(v));
    expect(unknown, `preview roles not used by any nav item: ${unknown.join(", ")}`).toEqual([]);
  });

  it("offers every role that has pages of its own", () => {
    const offered = new Set(PREVIEW_ROLES.map((r) => r.value));
    // "queue" is a capability flag on a couple of items rather than a job role
    // anyone is hired into, so it is not something to onboard.
    const notAJobRole = new Set(["queue"]);
    const missing = [...rolesUsedInNav()]
      .filter((r) => !offered.has(r) && !notAJobRole.has(r));
    expect(missing, `roles in the nav with no preview option: ${missing.join(", ")}`).toEqual([]);
  });

  it("every offered role resolves to a non-empty tour", () => {
    const empty = PREVIEW_ROLES
      .filter((r) => getTourStepsForRole(r.value).length === 0)
      .map((r) => r.value);
    expect(empty, `roles offered for preview with no tour: ${empty.join(", ")}`).toEqual([]);
  });
});
