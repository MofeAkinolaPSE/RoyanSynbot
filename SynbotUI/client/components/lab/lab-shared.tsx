import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export const ORDER_STATUS_COLORS: Record<string, string> = {
  ordered:          "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
  pending:          "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
  sample_collected: "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  collected:        "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  processing:       "bg-purple-500/20 text-purple-700 dark:text-purple-400 border-purple-500/30",
  resulted:         "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
  sent_out:         "bg-cyan-500/20 text-cyan-700 dark:text-cyan-400 border-cyan-500/30",
  cancelled:        "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30",
};

export const URGENCY_COLORS: Record<string, string> = {
  stat:    "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30",
  urgent:  "bg-orange-500/20 text-orange-700 dark:text-orange-400 border-orange-500/30",
  routine: "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30",
};

export const URGENCY_LEFT_BORDER: Record<string, string> = {
  stat:    "border-l-red-500",
  urgent:  "border-l-orange-400",
  routine: "border-l-transparent",
};

// Mirrors backend SPECIMEN_TYPES (src/routers/lab.py) — the CHECK constraint
// on royan_lab_specimens.specimen_type.
export const SPECIMEN_TYPES = [
  "blood", "urine", "stool", "sputum", "csf", "swab", "tissue", "serum", "plasma", "other",
];

export const SPECIMEN_STATUS_COLORS: Record<string, string> = {
  collected: "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  received:  "bg-purple-500/20 text-purple-700 dark:text-purple-400 border-purple-500/30",
  rejected:  "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30",
};

export function StatusBadge({ status }: { status?: string }) {
  const s = status ?? "pending";
  const cls = ORDER_STATUS_COLORS[s] ?? ORDER_STATUS_COLORS.pending;
  return <Badge variant="outline" className={cn("text-xs capitalize", cls)}>{s.replace(/_/g, " ")}</Badge>;
}

export function UrgencyBadge({ urgency }: { urgency?: string }) {
  const u = urgency ?? "routine";
  const cls = URGENCY_COLORS[u] ?? URGENCY_COLORS.routine;
  return <Badge variant="outline" className={cn("text-xs uppercase", cls)}>{u}</Badge>;
}

export function SpecimenStatusBadge({ status }: { status?: string }) {
  const s = status ?? "collected";
  const cls = SPECIMEN_STATUS_COLORS[s] ?? SPECIMEN_STATUS_COLORS.collected;
  return <Badge variant="outline" className={cn("text-xs capitalize", cls)}>{s}</Badge>;
}

export function elapsed(ts?: string) {
  if (!ts) return "—";
  const mins = Math.round((Date.now() - new Date(ts).getTime()) / 60000);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

// ─── Workflow Progress ─────────────────────────────────────────────────────
const WORKFLOW_STEPS = [
  { key: "ordered",          label: "Ordered" },
  { key: "sample_collected", label: "Collected" },
  { key: "processing",       label: "Processing" },
  { key: "resulted",         label: "Resulted" },
  { key: "verified",         label: "Verified" },
];

export function WorkflowProgress({ status, verified }: { status?: string; verified?: boolean }) {
  const normalised = status === "pending" ? "ordered" : status;
  let currentIdx = WORKFLOW_STEPS.findIndex(s => s.key === normalised);
  if (verified && currentIdx >= 0) currentIdx = WORKFLOW_STEPS.length - 1;

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
                "text-[12px] text-center leading-tight",
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
