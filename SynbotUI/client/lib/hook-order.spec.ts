import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

/**
 * Catches a hook reading a variable that is declared further down the file.
 *
 * This shipped and blanked the clinical queue:
 *
 *     const [queueKind] = useState(() => searchParams.get("kind") ...);  // line 1
 *     const [searchParams] = useSearchParams();                          // line 4
 *
 * useState runs its initialiser IMMEDIATELY, so that throws
 * "Cannot access 'searchParams' before initialization" on first render and the
 * whole page goes blank.
 *
 * Nothing else caught it. tsc allows it because the read sits inside an arrow
 * function and it cannot prove when the closure runs; the test suite has no DOM
 * and renders nothing; vite build only compiles. A render smoke test would be
 * the thorough answer, but that needs jsdom and testing-library, which are not
 * installed — this static check costs no dependencies and catches the same
 * class.
 */

const CLIENT_DIR = path.resolve(__dirname, "..");

/** Hooks whose callback argument runs during the render that declares it. */
const EAGER_HOOKS = ["useState", "useMemo", "useReducer"];

function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "node_modules" || entry.name === "dist") continue;
        walk(p);
      } else if (/\.tsx?$/.test(entry.name) && !/\.spec\.tsx?$/.test(entry.name)) {
        out.push(p);
      }
    }
  };
  walk(CLIENT_DIR);
  return out;
}

describe("hook declaration order", () => {
  it("no eager hook initialiser reads a variable declared below it", () => {
    const offenders: string[] = [];

    for (const file of sourceFiles()) {
      const src = fs.readFileSync(file, "utf8");
      const rel = path.relative(CLIENT_DIR, file).split(path.sep).join("/");

      for (const hook of EAGER_HOOKS) {
        const pattern = new RegExp(
          `const \\[(\\w+)[^\\]]*\\]\\s*=\\s*${hook}[^(]*\\(\\s*\\(\\)\\s*=>([\\s\\S]*?)\\);`,
          "g",
        );
        for (const m of src.matchAll(pattern)) {
          const [, name, body] = m;
          const reads = new Set(body.match(/\b[a-z]\w+\b/g) ?? []);
          for (const ident of reads) {
            // Where is this identifier declared? Only const destructuring and
            // plain const are checked — function declarations hoist, so they
            // are genuinely safe to reference early.
            const decl = new RegExp(`const \\[?${ident}\\b`).exec(src);
            if (decl && decl.index > m.index!) {
              offenders.push(
                `${rel}: ${hook} initialiser for '${name}' reads '${ident}', declared below`,
              );
            }
          }
        }
      }
    }

    expect(
      [...new Set(offenders)],
      `hooks reading variables declared later — these throw on first render:\n${offenders.join("\n")}`,
    ).toEqual([]);
  });
});
