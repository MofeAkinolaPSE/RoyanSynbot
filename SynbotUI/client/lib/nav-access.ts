import { NAV_ITEMS, type NavItem } from "@/lib/nav-items";

// Single home for "does this role see this item" — was previously copy-pasted
// as private closures in Sidebar.tsx AND tour-config.ts, and reimplemented a
// third time (differently) as ProtectedRoute.tsx's hand-written accessMap.
// That duplication is what let sidebar visibility and router-level access
// drift apart (a receptionist could see "Front Desk" in the sidebar but get
// bounced out on click, etc.) — this is the one function all three now share.
export function canViewByRoles(userRoles: string[], allowed?: string[]): boolean {
  if (!allowed || allowed.length === 0) return true;
  return userRoles.some((role) => allowed.includes(role));
}

interface FlatNavEntry {
  href: string;
  roles?: string[];
  label: string;
  icon: NavItem["icon"];
}

// Walks NAV_ITEMS once, emitting one entry per item with an href and one per
// child (children inherit the PARENT's roles — NavChild has no roles field
// of its own, e.g. Finance's "Analytics"/"Reports"/... all inherit Finance's
// [admin, finance]).
export function flattenNavItems(): FlatNavEntry[] {
  const entries: FlatNavEntry[] = [];
  for (const item of NAV_ITEMS as NavItem[]) {
    if (item.href) entries.push({ href: item.href, roles: item.roles, label: item.label, icon: item.icon });
    if (item.children) {
      for (const child of item.children) {
        entries.push({ href: child.href, roles: item.roles, label: child.label, icon: item.icon });
      }
    }
  }
  return entries;
}

let _flatCache: FlatNavEntry[] | null = null;
function flatCached(): FlatNavEntry[] {
  if (!_flatCache) _flatCache = flattenNavItems();
  return _flatCache;
}

// Exact-href lookup (label/icon/roles) for rendering a quick-access card —
// distinct from resolveRouteRoles below, which does prefix matching for
// route *access*, not exact lookup for card *display*.
export function getNavEntryByHref(href: string): FlatNavEntry | undefined {
  return flatCached().find((e) => e.href === href);
}

// Routes that exist but have no nav-items entry at all (not reachable from
// the sidebar) — a documented escape hatch, not currently needed: every
// dynamic/detail route in App.tsx resolves via boundary-safe prefix match
// against its parent nav entry (e.g. /hospital/patients/:mrn -> the
// /hospital/patients entry's roles). Add here only if a genuinely new
// standalone route needs roles a prefix match can't supply.
const RESIDUAL_ROUTE_ROLES: Record<string, string[]> = {};

// Longest-matching-href-wins, boundary-safe (an href only matches if the
// pathname equals it exactly or continues with "/", so "/hospital/patients"
// never falsely matches "/hospital/patientsomething"). Returns undefined for
// "no restriction" (universal access), matching nav-items' own convention
// for items with no roles array.
export function resolveRouteRoles(pathname: string): string[] | undefined {
  const flat = flatCached();
  let best: FlatNavEntry | undefined;
  for (const entry of flat) {
    const isMatch = pathname === entry.href || pathname.startsWith(entry.href + "/");
    if (!isMatch) continue;
    if (!best || entry.href.length > best.href.length) best = entry;
  }
  if (best) return best.roles;

  for (const [prefix, roles] of Object.entries(RESIDUAL_ROUTE_ROLES)) {
    if (pathname === prefix || pathname.startsWith(prefix + "/")) return roles;
  }
  return undefined;
}
