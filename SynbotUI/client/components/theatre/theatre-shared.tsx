import { Badge } from "@/components/ui/badge";
import { CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

export const URGENCY_COLORS: Record<string, string> = {
  elective:  "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  urgent:    "bg-orange-500/20 text-orange-700 dark:text-orange-400 border-orange-500/30",
  emergency: "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30",
};

export const STATUS_COLORS: Record<string, string> = {
  scheduled:  "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30",
  pre_op:     "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
  in_theatre: "bg-sky-500/20 text-sky-700 dark:text-sky-400 border-sky-500/30",
  recovery:   "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  completed:  "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
  cancelled:  "bg-slate-500/20 text-slate-700 dark:text-slate-400 border-slate-500/30",
};

export const STATUS_NEXT: Record<string, string> = {
  scheduled:  "Start Pre-Op",
  pre_op:     "Move to Theatre",
  in_theatre: "Send to Recovery",
  recovery:   "Mark Completed",
};

export const STATUS_TRANSITIONS: Record<string, string> = {
  scheduled:  "pre_op",
  pre_op:     "in_theatre",
  in_theatre: "recovery",
  recovery:   "completed",
};

export const CASE_TYPES = ["general", "regional", "local", "sedation"];
export const URGENCY_LEVELS = ["elective", "urgent", "emergency"];

export function StatusBadge({ status }: { status?: string }) {
  const s = status ?? "scheduled";
  const cls = STATUS_COLORS[s] ?? STATUS_COLORS.scheduled;
  return <Badge variant="outline" className={cn("text-xs capitalize", cls)}>{s.replace(/_/g, " ")}</Badge>;
}

export function UrgencyBadge({ urgency }: { urgency?: string }) {
  const u = urgency ?? "elective";
  const cls = URGENCY_COLORS[u] ?? URGENCY_COLORS.elective;
  return <Badge variant="outline" className={cn("text-xs uppercase", cls)}>{u}</Badge>;
}

export function elapsed(ts?: string) {
  if (!ts) return "—";
  const mins = Math.round((Date.now() - new Date(ts).getTime()) / 60000);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

export function CheckItem({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer group">
      <div
        onClick={() => onChange(!checked)}
        className={cn(
          "w-5 h-5 rounded border flex items-center justify-center transition-colors cursor-pointer",
          checked ? "bg-green-500/20 border-green-500" : "border-border group-hover:border-ring"
        )}
      >
        {checked && <CheckCircle2 className="w-3 h-3 text-green-500" />}
      </div>
      <span className="text-sm text-foreground">{label}</span>
    </label>
  );
}

// ─── Workflow Progress ─────────────────────────────────────────────────────
const WORKFLOW_STEPS = [
  { key: "scheduled",  label: "Scheduled" },
  { key: "pre_op",     label: "Pre-Op" },
  { key: "in_theatre", label: "In Theatre" },
  { key: "recovery",   label: "Recovery" },
  { key: "completed",  label: "Completed" },
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
