import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

/**
 * Guards against the class of bug that `tsc` cannot see.
 *
 * A double cast (`x as unknown as T`) silences the compiler completely. In
 * OrderDialog that turned a {value,label}[] into a claimed string[], which the
 * select then rendered as a React child — and rendering an object as a child
 * throws at runtime. The dialog was dead on open and typechecking stayed green,
 * because the cast is precisely an instruction to stop checking.
 *
 * Components render. A silenced type error in a component becomes a blank
 * screen in front of a clinician, so the bar there is higher than in lib code
 * that talks to browser globals.
 */

const CLIENT_DIR = path.resolve(__dirname, "..");

// Narrow, justified exemptions. Anything added here should be talking to an
// untyped external surface (a browser global, a third-party payload), never
// reshaping data that flows into JSX.
const ALLOWED = new Set(["lib/wp-config.ts"]);

const toPosix = (p: string) => p.split(path.sep).join("/");

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === "dist") continue;
      walk(p, out);
    } else if (/\.tsx?$/.test(entry.name) && !/\.spec\.tsx?$/.test(entry.name)) {
      out.push(p);
    }
  }
  return out;
}

describe("render safety", () => {
  it("no double casts outside the allowlist", () => {
    const offenders: string[] = [];
    for (const file of walk(CLIENT_DIR)) {
      const rel = path.relative(CLIENT_DIR, file).replace(/\\/g, "/");
      if (ALLOWED.has(rel)) continue;
      const src = fs.readFileSync(file, "utf8");
      src.split("\n").forEach((line, i) => {
        if (line.includes("as unknown as")) offenders.push(`${rel}:${i + 1}`);
      });
    }
    expect(
      offenders,
      `double casts defeat typechecking and have already shipped a runtime crash:\n${offenders.join("\n")}`,
    ).toEqual([]);
  });

  // Radix Select throws on an empty-string item value. This took the whole
  // Coverage Rules page down, not just its filter.
  it("no Select item carries an empty value", () => {
    const offenders: string[] = [];
    for (const file of walk(CLIENT_DIR)) {
      const rel = path.relative(CLIENT_DIR, file).replace(/\\/g, "/");
      const src = fs.readFileSync(file, "utf8");
      src.split("\n").forEach((line, i) => {
        if (/<SelectItem\s[^>]*value=""/.test(line)) offenders.push(`${rel}:${i + 1}`);
      });
    }
    expect(
      offenders,
      `Radix throws on an empty SelectItem value — use a sentinel like "__all":\n${offenders.join("\n")}`,
    ).toEqual([]);
  });
});

describe("source hygiene", () => {
  // A `\b` written through a shell heredoc collapsed into an actual backspace
  // byte inside a regex literal, silently turning /\b\w/g into /\w/g — which
  // uppercases every letter instead of word initials. It looked correct in the
  // editor, in grep, and in a diff.
  it("no stray control characters in source", () => {
    const offenders: string[] = [];
    for (const file of walk(CLIENT_DIR)) {
      const rel = toPosix(path.relative(CLIENT_DIR, file));
      const src = fs.readFileSync(file, "utf8");
      src.split("\n").forEach((line, i) => {
        // Tab and the line terminators are legitimate; nothing else is.
        if (/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(line)) offenders.push(`${rel}:${i + 1}`);
      });
    }
    expect(
      offenders,
      `control characters in source (invisible in an editor):\n${offenders.join("\n")}`,
    ).toEqual([]);
  });
});

describe("type scale", () => {
  // 317 places hardcoded text-[9px]…text-[13px]. Every one of them was at or
  // below the xs token, and none of them responded when the scale was raised —
  // which is why an earlier bump did not fix the "I have to zoom in" complaint.
  // Anything below the scale must go through a token so it can be raised again.
  it("no text size below the token scale is hardcoded", () => {
    const offenders: string[] = [];
    for (const file of walk(CLIENT_DIR)) {
      const rel = toPosix(path.relative(CLIENT_DIR, file));
      const src = fs.readFileSync(file, "utf8");
      src.split("\n").forEach((line, i) => {
        const m = line.match(/text-\[(\d+)px\]/);
        if (m && Number(m[1]) <= 14) offenders.push(`${rel}:${i + 1}  ${m[0]}`);
      });
    }
    expect(
      offenders,
      `use text-xs (token-driven) instead of a hardcoded size:\n${offenders.join("\n")}`,
    ).toEqual([]);
  });
});

describe("panel vocabulary stays single-sourced", () => {
  const PANEL_SHARED = "components/shared/panel-shared.tsx";

  // DetailRow lived in 10 files and SectionLabel in 11. That is how they
  // drifted: seven DetailRow copies guarded with `!value`, which hides a
  // numeric 0, so "Balance: 0" rendered as nothing.
  it.each(["DetailRow", "SectionLabel"])("%s is defined exactly once", (name) => {
    const definers: string[] = [];
    for (const file of walk(CLIENT_DIR)) {
      const rel = toPosix(path.relative(CLIENT_DIR, file));
      const src = fs.readFileSync(file, "utf8");
      if (new RegExp(`(export\\s+)?function ${name}\\b`).test(src)) definers.push(rel);
    }
    expect(definers, `${name} should only be declared in ${PANEL_SHARED}`).toEqual([PANEL_SHARED]);
  });

  it("DetailRow renders a zero rather than swallowing it", () => {
    const src = fs.readFileSync(path.join(CLIENT_DIR, PANEL_SHARED), "utf8");
    const body = src.slice(src.indexOf("export function DetailRow"));
    // `!value` is falsy for 0 — the exact bug this consolidation removed.
    expect(
      /if\s*\(\s*!value\s*\)/.test(body),
      "DetailRow must not guard with `!value`: 0 is a real, displayable value",
    ).toBe(false);
    expect(body).toContain('value === ""');
  });

  it("panel widths come from the shared constant, not per-file strings", () => {
    const offenders: string[] = [];
    for (const file of walk(CLIENT_DIR)) {
      const rel = toPosix(path.relative(CLIENT_DIR, file));
      if (rel === PANEL_SHARED) continue;
      const src = fs.readFileSync(file, "utf8");
      // A hardcoded sheet width on a SheetContent is how the 14 panels drifted.
      if (/<SheetContent[^>]*className="[^"]*\bw-\[\d+px\]/.test(src)) offenders.push(rel);
    }
    expect(
      offenders,
      `use PANEL_WIDTH / WorkspaceSheet instead of a hardcoded width:\n${offenders.join("\n")}`,
    ).toEqual([]);
  });
});
