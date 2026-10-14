import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
export { SectionLabel } from "@/components/shared/panel-shared";
// Re-exported so existing call sites keep their import path.
export { DetailRow } from "@/components/shared/panel-shared";

export const BED_STATUS_COLORS: Record<string, string> = {
  available:   "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
  occupied:    "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30",
  maintenance: "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30",
  reserved:    "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
};

export function BedBadge({ status }: { status?: string }) {
  const s = status ?? "available";
  const cls = BED_STATUS_COLORS[s] ?? BED_STATUS_COLORS.maintenance;
  return (
    <Badge variant="outline" className={cn("text-xs capitalize", cls)}>
      {s}
    </Badge>
  );
}

export function elapsed(ts?: string) {
  if (!ts) return "—";
  const mins = Math.round((Date.now() - new Date(ts).getTime()) / 60000);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

