import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
// Re-exported so existing call sites keep their import path.
export { DetailRow } from "@/components/shared/panel-shared";

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

export function naira(n?: number) {
  if (n === undefined || n === null) return "—";
  return `₦${n.toLocaleString("en-NG", { minimumFractionDigits: 2 })}`;
}

// Matches BILL_STATUS_ALLOWED exactly — "cancelled" (not a real status)
// dropped, "disputed"/"written_off" (real, reachable) added.
export const BILL_STATUS_COLORS: Record<string, string> = {
  pending:     "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
  partial:     "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  paid:        "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
  void:        "bg-muted text-muted-foreground border-border line-through",
  waived:      "bg-purple-500/20 text-purple-700 dark:text-purple-400 border-purple-500/30",
  disputed:    "bg-orange-500/20 text-orange-700 dark:text-orange-400 border-orange-500/30",
  written_off: "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30",
};
export const BILL_STATUSES = ["pending", "partial", "paid", "waived", "disputed", "written_off"] as const;
export const OPEN_BILL_STATUSES = ["pending", "partial", "disputed"] as const;

export function BillBadge({ status }: { status?: string }) {
  const s = status ?? "pending";
  return <Badge variant="outline" className={cn("text-xs capitalize", BILL_STATUS_COLORS[s] ?? BILL_STATUS_COLORS.pending)}>{s.replace(/_/g, " ")}</Badge>;
}

// Matches CLAIM_STATUS_ALLOWED exactly — "pending" (invalid, 422s
// server-side) dropped, "pre_authorised"/"paid" (real, previously
// unreachable via any filter pill) added.
export const CLAIM_STATUS_COLORS: Record<string, string> = {
  submitted:      "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  pre_authorised: "bg-cyan-500/20 text-cyan-700 dark:text-cyan-400 border-cyan-500/30",
  approved:       "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
  paid:           "bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 border-emerald-500/30",
  rejected:       "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30",
  disputed:       "bg-orange-500/20 text-orange-700 dark:text-orange-400 border-orange-500/30",
};
export const CLAIM_STATUSES = ["submitted", "pre_authorised", "approved", "paid", "rejected", "disputed"] as const;

export function ClaimBadge({ status }: { status?: string }) {
  const s = status ?? "submitted";
  return <Badge variant="outline" className={cn("text-xs capitalize", CLAIM_STATUS_COLORS[s] ?? CLAIM_STATUS_COLORS.submitted)}>{s.replace(/_/g, " ")}</Badge>;
}

export const PAYMENT_METHODS = ["pos", "cash", "transfer", "card", "hmo", "waiver"] as const;
export const PAYMENT_METHOD_LABELS: Record<string, string> = {
  pos: "POS", cash: "Cash", transfer: "Bank transfer", card: "Card (online)", hmo: "Move to HMO", waiver: "Waiver",
};
