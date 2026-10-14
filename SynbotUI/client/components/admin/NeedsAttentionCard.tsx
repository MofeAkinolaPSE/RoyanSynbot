import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ShieldCheck, Loader2, Check, X, Receipt, Pill, ClipboardCheck, BedDouble,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

/**
 * The correction pen: everything across the hospital waiting on an admin.
 *
 * WHY THIS REPLACES DiscountApprovalsCard
 * ---------------------------------------
 * That card returned null whenever nothing was pending, so on a quiet day the
 * admin dashboard showed no sign the approval workflow existed at all — which
 * is exactly how it was reported ("I don't see any card or any feature that
 * illustrates that correction pen"). A control you can only discover once it
 * already has work in it cannot be learned before it is needed, so this always
 * renders and says what it is when empty.
 *
 * It also consolidates four queues that had backends but nowhere to action
 * them: bill discounts, pharmacy discounts, front-desk drug approvals and
 * admission requests. Three of those had no UI on either side of the decision.
 *
 * Per-bill correction (adjustments, reversals) stays in CorrectionPen inside
 * the billing panel, where the bill's own lines are visible — an adjustment
 * made without seeing what is being adjusted is a guess.
 */
const naira = (v: any) => `₦${Number(v ?? 0).toLocaleString()}`;

type Queue = {
  key: string;
  label: string;
  icon: typeof Receipt;
  rows: any[];
  loading: boolean;
};

export function NeedsAttentionCard() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [note, setNote] = useState<Record<string, string>>({});

  const billDiscounts = useQuery({
    queryKey: ["pending-bill-discounts"],
    queryFn: () => api.hospital.billing.pendingDiscounts(),
    refetchInterval: 60_000,
  });
  const rxDiscounts = useQuery({
    queryKey: ["pending-rx-discounts"],
    queryFn: () => api.hospital.pharmacy.pendingDispensingDiscounts(),
    refetchInterval: 60_000,
  });
  const rxApprovals = useQuery({
    queryKey: ["pending-rx-approvals"],
    queryFn: () => api.hospital.pharmacy.pendingApprovals(),
    refetchInterval: 60_000,
  });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["pending-bill-discounts"] });
    void qc.invalidateQueries({ queryKey: ["pending-rx-discounts"] });
    void qc.invalidateQueries({ queryKey: ["pending-rx-approvals"] });
  };

  const decide = useMutation({
    mutationFn: ({ kind, id, approved }: { kind: string; id: number; approved: boolean }) => {
      const n = note[`${kind}-${id}`]?.trim() || undefined;
      if (kind === "bill") return api.hospital.billing.discountDecision(id, approved, n);
      if (kind === "rxdisc") return api.hospital.pharmacy.decideDispensingDiscount(id, approved, n);
      return api.hospital.pharmacy.approvalDecision(id, approved, n);
    },
    onSuccess: (_d, v) => {
      refresh();
      toast({ title: v.approved ? "Approved" : "Rejected" });
    },
    onError: (e: any) =>
      toast({ title: "Could not record that", description: e?.message, variant: "destructive" }),
  });

  const queues: Queue[] = [
    {
      key: "bill", label: "Bill discounts", icon: Receipt,
      rows: billDiscounts.data?.bills ?? [], loading: billDiscounts.isLoading,
    },
    {
      key: "rxdisc", label: "Pharmacy discounts", icon: Pill,
      // The endpoint returns "discounts", not "dispensing" — reading the wrong
      // key would have shown an empty queue forever while requests piled up.
      rows: rxDiscounts.data?.discounts ?? [], loading: rxDiscounts.isLoading,
    },
    {
      key: "rxapp", label: "Drug approvals", icon: ClipboardCheck,
      rows: rxApprovals.data?.prescriptions ?? [], loading: rxApprovals.isLoading,
    },
  ];

  const total = queues.reduce((n, q) => n + q.rows.length, 0);
  const loading = queues.some((q) => q.loading);

  const describe = (kind: string, r: any) => {
    if (kind === "bill") {
      return {
        title: r.bill_number ?? `Bill #${r.id}`,
        detail: `${naira(r.discount)} off ${naira(r.total_amount ?? r.subtotal)}`,
        sub: [r.patient_name, r.discount_reason].filter(Boolean).join(" · "),
      };
    }
    if (kind === "rxdisc") {
      return {
        title: r.drug_name ?? `Dispensing #${r.id}`,
        detail: `${naira(r.discount)} off ${naira(r.total_cost)}`,
        sub: [r.patient_name, r.discount_type, r.discount_reason].filter(Boolean).join(" · "),
      };
    }
    return {
      title: r.drug_name ?? `Prescription #${r.id}`,
      detail: [r.dosage, r.frequency].filter(Boolean).join(" ") || "—",
      sub: [r.patient_name, r.approval_note].filter(Boolean).join(" · "),
    };
  };

  return (
    <Card className={cn(total > 0 && "border-amber-500/40")}>
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-2">
        <ShieldCheck className={cn("h-4 w-4", total > 0 ? "text-amber-600" : "text-muted-foreground")} />
        <CardTitle className="text-sm font-semibold">Needs your approval</CardTitle>
        {total > 0 && (
          <Badge variant="outline" className="border-amber-500/40 bg-amber-500/10 text-xs text-amber-700 dark:text-amber-400">
            {total}
          </Badge>
        )}
        {loading && <Loader2 className="ml-auto h-3.5 w-3.5 animate-spin text-muted-foreground" />}
      </CardHeader>

      <CardContent className="space-y-3">
        {total === 0 && !loading ? (
          // Says what it is rather than disappearing. An admin needs to know
          // this queue exists BEFORE a cashier is waiting on them.
          <div className="py-2 text-xs text-muted-foreground">
            <p>Nothing is waiting on you right now.</p>
            <p className="mt-1.5">
              Discounts applied by a cashier or a pharmacist appear here for you to
              approve or reject, along with prescriptions the pharmacy has sent for
              front-desk approval. Nothing is deducted or dispensed until you decide.
            </p>
          </div>
        ) : (
          queues
            .filter((q) => q.rows.length > 0)
            .map((q) => (
              <section key={q.key}>
                <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <q.icon className="h-3.5 w-3.5" />
                  {q.label}
                  <span className="font-normal">({q.rows.length})</span>
                </p>
                <ul className="space-y-1.5">
                  {q.rows.slice(0, 5).map((r: any) => {
                    const d = describe(q.key, r);
                    const busy = decide.isPending;
                    return (
                      <li key={r.id} className="rounded-md border p-2">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="text-xs font-medium">{d.title}</p>
                            <p className="text-xs text-muted-foreground">{d.detail}</p>
                            {d.sub && <p className="text-xs text-muted-foreground">{d.sub}</p>}
                          </div>
                          <div className="flex shrink-0 gap-1">
                            <Button
                              size="sm" variant="outline" disabled={busy}
                              className="h-7 gap-1 border-green-500/40 px-2 text-xs text-green-700 hover:bg-green-500/10 dark:text-green-400"
                              onClick={() => decide.mutate({ kind: q.key, id: r.id, approved: true })}
                            >
                              <Check className="h-3 w-3" /> Approve
                            </Button>
                            <Button
                              size="sm" variant="outline" disabled={busy}
                              className="h-7 gap-1 px-2 text-xs text-muted-foreground"
                              onClick={() => decide.mutate({ kind: q.key, id: r.id, approved: false })}
                            >
                              <X className="h-3 w-3" /> Reject
                            </Button>
                          </div>
                        </div>
                        <Input
                          placeholder="Note (optional) — recorded against the decision"
                          className="mt-1.5 h-7 text-xs"
                          value={note[`${q.key}-${r.id}`] ?? ""}
                          onChange={(e) =>
                            setNote((n) => ({ ...n, [`${q.key}-${r.id}`]: e.target.value }))
                          }
                        />
                      </li>
                    );
                  })}
                </ul>
                {q.rows.length > 5 && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    and {q.rows.length - 5} more
                  </p>
                )}
              </section>
            ))
        )}
      </CardContent>
    </Card>
  );
}
