import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Pill, Loader2, Check, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

/**
 * Prescriptions pharmacy has pushed to the front desk for authorisation.
 *
 * "there will be a pop-up that says request front desk approval, so all the
 * pharmacy needs to do is push that to the front desk page... once they approve
 * that drug, pharmacy can dispense."
 *
 * The gate is enforced server-side in pharmacy_dispensing.dispense_prescription,
 * not by hiding a button here — a hidden button is not a rule, and pharmacy has
 * its own screen.
 *
 * Always shown, even when nothing is waiting: the desk asked for the card to stay in one place so
 * they know where a request will appear (it used to vanish when the queue emptied, and a request
 * arriving later was easy to miss). Empty, it says so in one quiet line.
 */
export function PharmacyApprovalsCard() {
  const qc = useQueryClient();
  const { toast } = useToast();

  const { data, isLoading } = useQuery({
    queryKey: ["pharmacy-pending-approvals"],
    queryFn: () => api.hospital.pharmacy.pendingApprovals(),
    refetchInterval: 30_000,
  });
  const rows: any[] = data?.prescriptions ?? [];

  const decide = useMutation({
    mutationFn: ({ id, approved }: { id: number; approved: boolean }) =>
      api.hospital.pharmacy.decideApproval(id, approved),
    onSuccess: (_r, v) => {
      void qc.invalidateQueries({ queryKey: ["pharmacy-pending-approvals"] });
      toast({ title: v.approved ? "Approved — pharmacy can dispense" : "Rejected" });
    },
    onError: (e: any) =>
      toast({ title: "Could not save the decision", description: e?.message, variant: "destructive" }),
  });

  return (
    <Card className={rows.length ? "border-amber-500/40" : undefined}>
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-2">
        <Pill className="h-4 w-4 text-amber-600 dark:text-amber-500" />
        <CardTitle className="text-sm">Pharmacy approvals waiting</CardTitle>
        <Badge variant="outline" className={rows.length ? "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400" : "text-muted-foreground"}>
          {rows.length}
        </Badge>
      </CardHeader>

      <CardContent className="space-y-2 pt-0">
        {isLoading ? (
          <div className="flex justify-center py-6">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : rows.length === 0 ? (
          <p className="py-2 text-xs text-muted-foreground">Nothing waiting. When pharmacy asks the desk to approve a drug, it appears here.</p>
        ) : (
          rows.map((rx) => (
            <div key={rx.id} className="rounded-md border bg-muted/30 p-2.5">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{rx.drug_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {[rx.dosage, rx.frequency].filter(Boolean).join(" · ")}
                    {rx.quantity ? ` · ${rx.quantity} ${rx.unit ?? ""}`.trimEnd() : ""}
                  </p>
                  <p className="mt-0.5 text-xs">
                    {rx.patient_name ?? "Patient"}
                    {rx.patient_mrn && (
                      <span className="ml-1.5 font-mono text-muted-foreground">{rx.patient_mrn}</span>
                    )}
                  </p>
                  {rx.approval_note && (
                    <p className="mt-1 text-xs italic text-muted-foreground">"{rx.approval_note}"</p>
                  )}
                </div>

                <div className="flex shrink-0 gap-1">
                  <Button
                    size="icon" variant="outline"
                    className={cn("h-7 w-7 border-green-500/40 text-green-700 hover:bg-green-500/10 dark:text-green-400")}
                    aria-label="Approve"
                    disabled={decide.isPending}
                    onClick={() => decide.mutate({ id: rx.id, approved: true })}
                  >
                    <Check className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    size="icon" variant="outline"
                    className="h-7 w-7 border-red-500/40 text-red-700 hover:bg-red-500/10 dark:text-red-400"
                    aria-label="Reject"
                    disabled={decide.isPending}
                    onClick={() => decide.mutate({ id: rx.id, approved: false })}
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
