/**
 * Pick one or more access roles, and see exactly what the person will be able to open.
 * The preview is computed with visibleNav() - the sidebar's own rule over NAV_ITEMS -
 * so it cannot drift from the menu they will actually get (reportGUide.md s4).
 */
import { visibleNav } from "@/lib/nav-access";

export type RoleDef = { key: string; label: string; team: string; about: string };

export function RolePicker({ catalog, value, onChange }: { catalog: RoleDef[]; value: string[]; onChange: (v: string[]) => void }) {
  // Viewer is the "nothing else" role: picking a real role replaces it, picking viewer clears the rest.
  const toggle = (k: string) =>
    onChange(value.includes(k) ? value.filter((x) => x !== k)
      : k === "viewer" ? ["viewer"] : [...value.filter((x) => x !== "viewer"), k]);
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {catalog.map((r) => (
        <label key={r.key}
               className={`flex cursor-pointer gap-2.5 rounded-lg border p-2.5 text-sm transition-colors ${value.includes(r.key) ? "border-primary bg-primary/5" : "hover:bg-muted/40"}`}>
          <input type="checkbox" className="mt-0.5 h-4 w-4 shrink-0 accent-primary" checked={value.includes(r.key)} onChange={() => toggle(r.key)} />
          <span>
            <span className="font-medium">{r.label}</span>
            <span className="block text-xs text-muted-foreground">{r.about}</span>
          </span>
        </label>
      ))}
    </div>
  );
}

export function AccessPreview({ roles }: { roles: string[] }) {
  if (!roles.length) return <p className="text-xs text-muted-foreground">Choose at least one role.</p>;
  const nav = visibleNav(roles);
  return (
    <div className="rounded-lg border bg-muted/30 p-3 text-xs">
      <div className="mb-1.5 font-medium text-foreground">They will be able to open ({nav.length} menu items):</div>
      <ul className="grid gap-x-4 gap-y-0.5 sm:grid-cols-2">
        {nav.map((n) => (
          <li key={n.label}>
            <span className="font-medium">{n.label}</span>
            {n.children.length > 0 && <span className="text-muted-foreground"> - {n.children.join(", ")}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

