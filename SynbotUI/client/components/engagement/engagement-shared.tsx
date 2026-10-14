import { cn } from "@/lib/utils";
export { SectionLabel } from "@/components/shared/panel-shared";
// Re-exported so existing call sites keep their import path.
export { DetailRow } from "@/components/shared/panel-shared";

export const TELE_STATUS_COLORS: Record<string, string> = {
  scheduled:  "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  active:     "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
  completed:  "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30",
  cancelled:  "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30",
  no_show:    "bg-orange-500/20 text-orange-700 dark:text-orange-400 border-orange-500/30",
};

export interface TeleAction {
  status: string;
  label: string;
}

// Mirrors backend TRANSITIONS (telemedicine.py) exactly — scheduled can go
// to active/cancelled/no_show, active can go to completed/cancelled. The
// previous frontend only exposed the scheduled->active->completed happy
// path, leaving cancelled/no_show unreachable despite full backend support.
export const TELE_ACTIONS: Record<string, TeleAction[]> = {
  scheduled: [
    { status: "active", label: "Start Session" },
    { status: "no_show", label: "Mark No Show" },
    { status: "cancelled", label: "Cancel Session" },
  ],
  active: [
    { status: "completed", label: "End Session" },
    { status: "cancelled", label: "Cancel Session" },
  ],
};

