import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Percent, Loader2, Check, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

/**
 * Discounts a cashier has applied, waiting on an admin.
 *
 * "once the discount is added, before the bill can be confirmed, the admin needs
 * to confirm that discount is relevant... so admin will have a UI card in their
 * dashboard that shows them that there is a new discount waiting for approval."
 *
 * The bill cannot be settled while this is outstanding — enforced server-side in
 * record_payment, because a bill is reachable from several screens and hiding a
 * button on one of them is not a control.
 *
 * Rejecting clears the discount rather than leaving it applied-but-unapproved,
 * which would be indistinguishable from an approved one everywhere else.
 */
const naira = (v: any) => `₦${Number(v ?? 0).toLocaleString()}`;

export function DiscountApprovalsCard() {
  const qc = useQueryClient();
  const { toast } = useToast();

  const { data, isLoading } = useQuery({
    queryKey: ["pending-discounts"],
    queryFn: () => api.hospital.billing.pendingDiscounts(),
    refetchInterval: 60_000,
  });
  const bills: any[] = data?.bills ?? [];

  const decide = useMutation({
    mutationFn: ({ id, approve }: { id: number; approve: boolean }) =>
      api.hospital.billing.decideDiscount(id, approve),
    onSuccess: (_r, v) => {
      void qc.invalidateQueries({ queryKey: ["pending-discounts"] });
      void qc.invalidateQueries({ queryKey: ["hospital-bills"] });
      toast({ title: v.approve ? "Discount approved" : "Discount rejected and cleared" });
    },
    onError: (e: any) =>
      toast({ title: "Could not save", description: e?.message, variant: "destructive" }),
  });

  // Nothing pending, nothing to show.
  if (!isLoading && bills.length === 0) return null;

  return (
    <Card className="border-amber-500/40">
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-2">
        <Percent className="h-4 w-4 text-amber-600 dark:text-amber-500" />
        <CardTitle className="text-sm">
          {bills.length === 1
            ? "1 discount waiting for approval"
            : `${bills.length} discounts waiting for approval`}
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-2 pt-0">
        {isLoading ? (
          <div className="flex justify-center py-6">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : (
          bills.map((b) => (
            <div key={b.id} className="rounded-md border bg-muted/30 p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-mono text-xs font-semibold text-primary">
                      {b.bill_number ?? `Bill ${b.id}`}
                    </span>
                    <span className="text-sm">{b.patient_name ?? "Patient"}</span>
                    {b.patient_mrn && (
                      <span className="font-mono text-xs text-muted-foreground">{b.patient_mrn}</span>
                    )}
                  </div>

                  <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs">
                    <span className="text-muted-foreground">
                      Subtotal <span className="tabular-nums">{naira(b.subtotal)}</span>
                    </span>
                    <span className="font-medium text-amber-700 dark:text-amber-400">
                      Discount <span className="tabular-nums">{naira(b.discount)}</span>
                      {b.discount_pct != null && (
                        <span className={cn("ml-1", b.discount_pct >= 50 && "font-semibold")}>
                          ({b.discount_pct}%)
                        </span>
                      )}
                    </span>
                  </div>

                  {b.discount_reason ? (
                    <p className="mt-1 text-xs italic">"{b.discount_reason}"</p>
                  ) : (
                    <p className="mt-1 text-xs italic text-muted-foreground">No reason given</p>
                  )}
                </div>

                <div className="flex shrink-0 gap-1">
                  <Button
                    size="icon" variant="outline"
                    className="h-7 w-7 border-green-500/40 text-green-700 hover:bg-green-500/10 dark:text-green-400"
                    aria-label="Approve discount"
                    disabled={decide.isPending}
                    onClick={() => decide.mutate({ id: b.id, approve: true })}
                  >
                    <Check className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    size="icon" variant="outline"
                    className="h-7 w-7 border-red-500/40 text-red-700 hover:bg-red-500/10 dark:text-red-400"
                    aria-label="Reject discount"
                    disabled={decide.isPending}
                    onClick={() => decide.mutate({ id: b.id, approve: false })}
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}
