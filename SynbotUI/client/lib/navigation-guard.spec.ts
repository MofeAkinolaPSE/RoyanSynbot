import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

function extractQuotedValues(source: string, pattern: RegExp): string[] {
  const values: string[] = [];
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(source)) !== null) {
    if (match[1]) values.push(match[1]);
  }
  return values;
}

describe("navigation guardrail", () => {
  it("detects orphan app routes and missing sidebar route references", () => {
    const appPath = path.resolve(__dirname, "../App.tsx");

    // Nav items used to be declared inline in components/Sidebar.tsx, and this
    // guard read them from there. They now live in lib/nav-items.ts, so
    // Sidebar.tsx contains no `href: "..."` literals at all — the guard was
    // silently matching zero routes and reporting all 52 app routes as
    // orphans. (It went unnoticed because a vite.config.ts resolution bug
    // meant `vitest --run` never started.) Both files are read so the guard
    // keeps working if any nav entry is ever declared inline again.
    const navSources = [
      path.resolve(__dirname, "./nav-items.ts"),
      path.resolve(__dirname, "../components/Sidebar.tsx"),
    ]
      .filter((p) => fs.existsSync(p))
      .map((p) => fs.readFileSync(p, "utf8"))
      .join("\n");

    const appSource = fs.readFileSync(appPath, "utf8");
    const sidebarSource = navSources;

    const appRoutes = new Set(
      extractQuotedValues(appSource, /<Route\s+path="([^"]+)"/g).filter((route) => route && route !== "*")
    );
    // a link may carry a query (Finance › Scancare Books is /finance/books?company=SCN); the route is the path
    const sidebarRoutes = new Set(extractQuotedValues(sidebarSource, /href:\s*"([^"]+)"/g).map((r) => r.split("?")[0]));

    const excludedFromSidebar = new Set([
      "/login",
      "/register",                  // public sign-up, pairs with /login — deliberately outside the app shell
      "/hospital/display",          // public full-screen queue board, explicitly "no sidebar" in App.tsx
      "/executive/summary",         // drilldown from Executive page, not a direct nav item
      "/finance/reports/ar/:bucket", // parameterised detail route
      "/hospital/hr",               // redirects to /hr after the two HR pages were merged; kept so existing links and bookmarks still resolve
      "/hospital/nursing",          // redirects to /hospital/nurse after Nursing Station and Nurse Dashboard were merged; same reasoning
      "/hospital/hmo/desk",         // HMO Desk became the first tab of HMO Desk & Coverage (/hospital/hmo); same reasoning
      // The old Finance group's pages duplicated Roy Books screens; they redirect there so old links and bookmarks still resolve.
      "/finance/analytics",         // -> Roy Books Control Tower
      "/finance/reports",           // -> Roy Books Report Center
      "/finance/vendor-payments",   // -> Roy Books Purchases > Payments
      "/finance/budget",            // -> Roy Books Setup > Budgets
      // Staff Dashboard, Collaboration and Time Tracker became tabs of My Workspace; they redirect there.
      "/staff/dashboard",
      "/staff/collaboration",
      "/staff/time-tracker",
    ]);

    const appRoutesForSidebar = [...appRoutes].filter(
      (route) => !excludedFromSidebar.has(route) && !route.includes(":")
    );

    const sidebarMissingInApp = [...sidebarRoutes].filter((route) => !appRoutes.has(route));
    const orphanAppRoutes = appRoutesForSidebar.filter((route) => !sidebarRoutes.has(route));

    expect(
      sidebarMissingInApp,
      `Sidebar references routes not present in App router: ${sidebarMissingInApp.join(", ")}`,
    ).toEqual([]);

    expect(
      orphanAppRoutes,
      `App routes missing sidebar references (potential orphan pages): ${orphanAppRoutes.join(", ")}`,
    ).toEqual([]);
  });

  // The check above only compares nav-items against App.tsx. It says nothing
  // about the hundreds of <Link to="..."> and navigate("...") calls scattered
  // through pages — which is how two dead links to "/operations" (a route that
  // has never existed) sat on the Executive dashboard, silently falling through
  // to the catch-all.
  it("every hardcoded link target resolves to a real route", () => {
    const CLIENT_DIR = path.resolve(__dirname, "..");
    const appSource = fs.readFileSync(path.join(CLIENT_DIR, "App.tsx"), "utf8");
    const declared = extractQuotedValues(appSource, /<Route\s+path="([^"]+)"/g);

    // A route with params matches by prefix; everything else must match exactly.
    const exact = new Set(declared.filter((r) => !r.includes(":") && r !== "*"));
    const prefixes = declared
      .filter((r) => r.includes(":"))
      .map((r) => r.slice(0, r.indexOf(":")));

    const resolves = (target: string) => {
      const clean = target.split("?")[0].split("#")[0].replace(/\/$/, "") || "/";
      if (exact.has(clean)) return true;
      return prefixes.some((p) => clean.startsWith(p));
    };

    const files: string[] = [];
    const walk = (dir: string) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const p = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          if (entry.name === "node_modules" || entry.name === "dist") continue;
          walk(p);
        } else if (/\.tsx?$/.test(entry.name) && !/\.spec\.tsx?$/.test(entry.name)) {
          files.push(p);
        }
      }
    };
    walk(CLIENT_DIR);

    const dead: string[] = [];
    for (const file of files) {
      const rel = path.relative(CLIENT_DIR, file).split(path.sep).join("/");
      const src = fs.readFileSync(file, "utf8");
      const targets = [
        ...extractQuotedValues(src, /<Link\s+to="(\/[^"]*)"/g),
        ...extractQuotedValues(src, /navigate\("(\/[^"]*)"\)/g),
      ];
      for (const t of targets) {
        // Template literals and computed paths are out of scope; only literals.
        if (t.includes("${")) continue;
        if (!resolves(t)) dead.push(`${rel} -> ${t}`);
      }
    }

    expect(dead, `links pointing at routes that do not exist:\n${dead.join("\n")}`).toEqual([]);
  });
});
