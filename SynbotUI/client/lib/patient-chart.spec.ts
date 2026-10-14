import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

/**
 * Guards on the patient chart, which is one 3,000-line component and therefore
 * the easiest place in the app for a silent inconsistency to survive.
 */

const CHART = path.resolve(__dirname, "../pages/PatientProfile.tsx");
const src = () => fs.readFileSync(CHART, "utf8");

describe("patient chart tabs", () => {
  // setMainTab("billing") and setMainTab("documents") both shipped in a
  // "View all" during this work. Neither tab exists, so the content area would
  // simply have gone blank — no error, no clue.
  it("every setMainTab target is a tab that renders", () => {
    const s = src();
    const rendered = new Set(
      Array.from(s.matchAll(/mainTab === "([a-z_]+)"/g)).map((m) => m[1]),
    );
    const targets = Array.from(s.matchAll(/setMainTab\("([a-z_]+)"\)/g)).map((m) => m[1]);
    const dead = [...new Set(targets)].filter((t) => !rendered.has(t));
    expect(
      dead,
      `setMainTab targets with no matching render branch: ${dead.join(", ")}`,
    ).toEqual([]);
  });

  it("the chart no longer routes clinical records through a flat dialog", () => {
    const s = src();
    // Lab, radiology and theatre records each have a full workspace panel.
    // Rebuilding a label/value summary of them here is what the rework removed.
    expect(s).toContain("<LabWorkspacePanel");
    expect(s).toContain("<RadiologyWorkspacePanel");
    expect(s).toContain("<TheatreWorkspacePanel");
    expect(s).toContain("<RecordDetailPanel");
    // The old centred dialog rendered recordDetail.rows inline; the panel owns
    // that now.
    expect(s).not.toContain("recordDetail.rows");
  });
});
