import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function fmtDate(ts?: string) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("en-NG", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function elapsed(ts?: string) {
  if (!ts) return "—";
  const mins = Math.round((Date.now() - new Date(ts).getTime()) / 60000);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

// ─── Pain score ────────────────────────────────────────────────────────────
export function PainBadge({ score }: { score?: number | null }) {
  if (score == null) return <span className="text-muted-foreground text-xs">—</span>;
  const cls = score >= 7 ? "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30"
    : score >= 4 ? "bg-orange-500/20 text-orange-700 dark:text-orange-400 border-orange-500/30"
    : "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30";
  return <Badge variant="outline" className={cn("text-xs", cls)}>{score}/10</Badge>;
}

// ─── MAR status ──────────────────────────────────────────────────────────
export const MAR_STATUS_COLORS: Record<string, string> = {
  administered: "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
  scheduled:    "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30",
  held:         "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
  missed:       "bg-orange-500/20 text-orange-700 dark:text-orange-400 border-orange-500/30",
  refused:      "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30",
};

export function MarStatusBadge({ status }: { status?: string }) {
  const s = status ?? "administered";
  return <Badge variant="outline" className={cn("text-[12px] capitalize", MAR_STATUS_COLORS[s] ?? MAR_STATUS_COLORS.administered)}>{s}</Badge>;
}

// ─── Care plan status / priority ───────────────────────────────────────────
export const CARE_PLAN_STATUS_COLORS: Record<string, string> = {
  active:       "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  resolved:     "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
  deferred:     "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30",
  discontinued: "bg-slate-500/20 text-slate-700 dark:text-slate-400 border-slate-500/30",
};

export function CarePlanStatusBadge({ status }: { status?: string }) {
  const s = status ?? "active";
  return <Badge variant="outline" className={cn("text-xs capitalize", CARE_PLAN_STATUS_COLORS[s] ?? CARE_PLAN_STATUS_COLORS.active)}>{s}</Badge>;
}

export const CARE_PLAN_PRIORITY_COLORS: Record<string, string> = {
  low:      "bg-slate-500/20 text-slate-700 dark:text-slate-400 border-slate-500/30",
  medium:   "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
  high:     "bg-orange-500/20 text-orange-700 dark:text-orange-400 border-orange-500/30",
  critical: "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30",
};

export function CarePlanPriorityBadge({ priority }: { priority?: string }) {
  const p = priority ?? "medium";
  return <Badge variant="outline" className={cn("text-xs capitalize", CARE_PLAN_PRIORITY_COLORS[p] ?? CARE_PLAN_PRIORITY_COLORS.medium)}>{p}</Badge>;
}

// ─── Fluid type ────────────────────────────────────────────────────────────
export function FluidTypeBadge({ type }: { type?: string }) {
  const cls = type === "intake"
    ? "text-blue-700 dark:text-blue-400 border-blue-500/30 bg-blue-500/10"
    : "text-orange-700 dark:text-orange-400 border-orange-500/30 bg-orange-500/10";
  return <Badge variant="outline" className={cn("text-xs capitalize", cls)}>{type}</Badge>;
}

// ─── Detail row: label + value ─────────────────────────────────────────────
export function DetailRow({ label, value, mono = false, accent }: {
  label: string; value?: string | null; mono?: boolean; accent?: string;
}) {
  if (!value) return null;
  return (
    <div className="flex items-start justify-between gap-3 py-1 border-b border-border/30 last:border-0">
      <span className="text-xs text-muted-foreground shrink-0">{label}</span>
      <span className={cn("text-xs text-right font-medium", mono && "font-mono", accent)}>{value}</span>
    </div>
  );
}
