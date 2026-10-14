import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { AlertOctagon, AlertTriangle, Eye, CheckCircle2 } from "lucide-react";
// Re-exported so existing call sites keep their import path.
export { DetailRow } from "@/components/shared/panel-shared";

export const RX_STATUS_COLORS: Record<string, string> = {
  pending:              "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
  partially_dispensed:  "bg-amber-500/20 text-amber-700 dark:text-amber-400 border-amber-500/30",
  dispensed:            "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
  cancelled:            "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30",
  returned:             "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30",
};

export const MED_ADMIN_STATUS_COLORS: Record<string, string> = {
  given:         "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
  refused:       "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30",
  held:          "bg-orange-500/20 text-orange-700 dark:text-orange-400 border-orange-500/30",
  not_available: "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30",
  omitted:       "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30",
};

export function StatusBadge({ status }: { status?: string }) {
  const s = status ?? "pending";
  const cls = RX_STATUS_COLORS[s] ?? RX_STATUS_COLORS.pending;
  return <Badge variant="outline" className={cn("text-xs capitalize", cls)}>{s.replace(/_/g, " ")}</Badge>;
}

export function MedAdminStatusBadge({ status }: { status?: string }) {
  const s = status ?? "given";
  const cls = MED_ADMIN_STATUS_COLORS[s] ?? MED_ADMIN_STATUS_COLORS.given;
  return <Badge variant="outline" className={cn("text-xs capitalize", cls)}>{s.replace(/_/g, " ")}</Badge>;
}

// ─── Inventory risk tier — reserved status colors, never reused for anything
// else, always icon + label (never color-alone). ─────────────────────────
export const INVENTORY_TIER_META: Record<string, { label: string; cls: string; Icon: typeof AlertOctagon }> = {
  CRITICAL: { label: "Critical",  cls: "bg-red-500/15 text-red-500 border-red-500/30",       Icon: AlertOctagon },
  WARNING:  { label: "Warning",   cls: "bg-amber-500/15 text-amber-500 border-amber-500/30",  Icon: AlertTriangle },
  MONITOR:  { label: "Monitor",   cls: "bg-blue-500/15 text-blue-500 border-blue-500/30",     Icon: Eye },
  ADEQUATE: { label: "Adequate",  cls: "bg-green-500/15 text-green-500 border-green-500/30",  Icon: CheckCircle2 },
};

export function RiskTierBadge({ tier }: { tier?: string }) {
  const meta = INVENTORY_TIER_META[tier ?? "MONITOR"] ?? INVENTORY_TIER_META.MONITOR;
  const { Icon } = meta;
  return (
    <Badge variant="outline" className={cn("text-xs gap-1", meta.cls)}>
      <Icon className="h-3 w-3" />{meta.label}
    </Badge>
  );
}

export function elapsed(ts?: string) {
  if (!ts) return "—";
  const mins = Math.round((Date.now() - new Date(ts).getTime()) / 60000);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

// ─── Workflow Progress ─────────────────────────────────────────────────────
// 3 steps only — Prescribed / Partially Dispensed / Dispensed. Administration
// is a separate, possibly-repeated event stream (shown as a count/list in the
// panel's Administer tab), not a stepper position — a prescription can be
// legitimately administered many times against one "Dispensed" state.
const WORKFLOW_STEPS = [
  { key: "pending",              label: "Prescribed" },
  { key: "partially_dispensed",  label: "Partially Dispensed" },
  { key: "dispensed",            label: "Dispensed" },
];

export function WorkflowProgress({ status }: { status?: string }) {
  const currentIdx = WORKFLOW_STEPS.findIndex(s => s.key === status);

  return (
    <div className="flex items-start">
      {WORKFLOW_STEPS.map((step, i) => {
        const done   = i <= currentIdx;
        const active = i === currentIdx;
        return (
          <div key={step.key} className="flex items-start flex-1">
            <div className="flex flex-col items-center gap-1 flex-1">
              <div className={cn(
                "h-3 w-3 rounded-full border-2 transition-colors",
                done
                  ? "bg-blue-500 border-blue-500"
                  : "bg-background border-muted-foreground/30",
                active && "ring-4 ring-blue-500/20",
              )} />
              <span className={cn(
                "text-xs text-center leading-tight",
                done ? "text-blue-700 dark:text-blue-400 font-medium" : "text-muted-foreground",
              )}>{step.label}</span>
            </div>
            {i < WORKFLOW_STEPS.length - 1 && (
              <div className={cn(
                "h-0.5 flex-1 mt-1.5",
                i < currentIdx ? "bg-blue-500" : "bg-muted",
              )} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Detail row: label + value ─────────────────────────────────────────────
