import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
// Re-exported so existing call sites keep their import path.
export { DetailRow } from "@/components/shared/panel-shared";

export const MODALITY_COLORS: Record<string, string> = {
  xray:        "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30",
  ultrasound:  "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  ct:          "bg-purple-500/20 text-purple-700 dark:text-purple-400 border-purple-500/30",
  mri:         "bg-indigo-500/20 text-indigo-700 dark:text-indigo-400 border-indigo-500/30",
  ecg:         "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30",
  echo:        "bg-pink-500/20 text-pink-700 dark:text-pink-400 border-pink-500/30",
  fluoroscopy: "bg-orange-500/20 text-orange-700 dark:text-orange-400 border-orange-500/30",
  mammography: "bg-rose-500/20 text-rose-700 dark:text-rose-400 border-rose-500/30",
  endoscopy:   "bg-teal-500/20 text-teal-700 dark:text-teal-400 border-teal-500/30",
};

export const ORDER_STATUS_COLORS: Record<string, string> = {
  ordered:     "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
  scheduled:   "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  in_progress: "bg-purple-500/20 text-purple-700 dark:text-purple-400 border-purple-500/30",
  reported:    "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
  cancelled:   "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30",
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

export function StatusBadge({ status }: { status?: string }) {
  const s = status ?? "ordered";
  const cls = ORDER_STATUS_COLORS[s] ?? ORDER_STATUS_COLORS.ordered;
  return <Badge variant="outline" className={cn("text-xs capitalize", cls)}>{s.replace(/_/g, " ")}</Badge>;
}

export function UrgencyBadge({ urgency }: { urgency?: string }) {
  const u = urgency ?? "routine";
  const cls = URGENCY_COLORS[u] ?? URGENCY_COLORS.routine;
  return <Badge variant="outline" className={cn("text-xs uppercase", cls)}>{u}</Badge>;
}

export function ModalityBadge({ modality }: { modality?: string }) {
  const m = modality ?? "other";
  const cls = MODALITY_COLORS[m] ?? "";
  return <Badge variant="outline" className={cn("text-xs uppercase", cls)}>{m}</Badge>;
}

export function elapsed(ts?: string) {
  if (!ts) return "—";
  const mins = Math.round((Date.now() - new Date(ts).getTime()) / 60000);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

// ─── Workflow Progress ─────────────────────────────────────────────────────
const WORKFLOW_STEPS = [
  { key: "ordered",     label: "Ordered" },
  { key: "scheduled",   label: "Scheduled" },
  { key: "in_progress", label: "In Progress" },
  { key: "reported",    label: "Reported" },
  { key: "verified",    label: "Verified" },
];

export function WorkflowProgress({ status, verified }: { status?: string; verified?: boolean }) {
  let currentIdx = WORKFLOW_STEPS.findIndex(s => s.key === status);
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
