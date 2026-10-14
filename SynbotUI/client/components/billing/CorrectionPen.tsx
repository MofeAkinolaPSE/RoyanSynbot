import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PenLine, Loader2, Undo2, AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { SectionLabel, DetailRow } from "@/components/shared/panel-shared";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { askText } from "@/lib/ask";

/**
 * The correction pen — admin-only changes to a bill after it was issued.
 *
 * Reduce a charge (service not rendered), reallocate part of it to someone else,
 * or refund money already taken. The worked example from the meeting: a ₦90,000
 * blood bag ordered and not used, split so the patient does not carry all of it.
 *
 * Corrections are APPENDED, never applied over the original. The bill keeps its
 * issued figures and the effective total is derived from the trail, so "it says
 * ₦30,000" always comes with "it said ₦90,000, changed by whom, and why".
 * A mistake is undone by reversing it — which is itself a visible row — not by
 * deleting evidence.
 */
const naira = (v: any) => `₦${Number(v ?? 0).toLocaleString()}`;

const TYPES = [
  { value: "reduction", label: "Reduce the charge", hint: "Service was not rendered, or was over-charged" },
  { value: "reallocation", label: "Someone else carries it", hint: "The charge stands, but not against this patient" },
  { value: "refund", label: "Refund money taken", hint: "Return part of what has already been paid" },
];

export function CorrectionPen({ billId, isAdmin }: { billId: number | string; isAdmin: boolean }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [type, setType] = useState("reduction");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [to, setTo] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["bill-adjustments", billId],
    queryFn: () => api.hospital.billing.listAdjustments(billId),
  });

  const adjustments: any[] = data?.adjustments ?? [];
  const reversedIds = new Set(adjustments.filter((a) => a.reverses_id).map((a) => a.reverses_id));

  const reset = () => { setAmount(""); setReason(""); setTo(""); };

  const apply = useMutation({
    mutationFn: () =>
      api.hospital.billing.adjustBill(billId, {
        adjustment_type: type,
        amount: Number(amount),
        reason: reason.trim(),
        reallocated_to: type === "reallocation" ? to.trim() : undefined,
      }),
    onSuccess: () => {
      reset();
      void qc.invalidateQueries({ queryKey: ["bill-adjustments", billId] });
      void qc.invalidateQueries({ queryKey: ["bill", billId] });
      toast({ title: "Correction recorded" });
    },
    onError: (e: any) =>
      toast({ title: "Could not apply", description: e?.message, variant: "destructive" }),
  });

  const reverse = useMutation({
    mutationFn: ({ id, why }: { id: number; why: string }) =>
      api.hospital.billing.reverseAdjustment(billId, id, why),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["bill-adjustments", billId] });
      toast({ title: "Correction reversed" });
    },
    onError: (e: any) =>
      toast({ title: "Could not reverse", description: e?.message, variant: "destructive" }),
  });

  if (isLoading) {
    return <div className="flex justify-center py-6"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>;
  }

  const changed = Number(data?.original_subtotal ?? 0) !== Number(data?.effective_subtotal ?? 0);

  return (
    <div className="space-y-4">
      <section>
        <SectionLabel icon={<PenLine className="h-3.5 w-3.5" />} label="Effective total" />
        <DetailRow label="As issued" value={naira(data?.original_subtotal)} />
        {Number(data?.reduced) > 0 && <DetailRow label="Reduced" value={`− ${naira(data.reduced)}`} accent="text-amber-600" />}
        {Number(data?.reallocated) > 0 && <DetailRow label="Carried by others" value={`− ${naira(data.reallocated)}`} accent="text-amber-600" />}
        <DetailRow
          label="Patient now owes"
          value={naira(data?.effective_subtotal)}
          accent={changed ? "font-semibold text-green-600" : "font-semibold"}
        />
        {Number(data?.refunded) > 0 && (
          <DetailRow label="Refunded" value={naira(data.refunded)} accent="text-blue-600" />
        )}
      </section>

      {adjustments.length > 0 && (
        <section>
          <SectionLabel icon={<PenLine className="h-3.5 w-3.5" />} label="Correction trail" />
          <ul className="space-y-1.5">
            {adjustments.map((a) => {
              const isReversed = reversedIds.has(a.id);
              const isReversal = a.adjustment_type === "reversal";
              return (
                <li
                  key={a.id}
                  className={cn(
                    "rounded-md border px-2.5 py-2 text-xs",
                    isReversed && "opacity-50",
                    isReversal && "border-dashed",
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant="outline" className="text-xs capitalize">{a.adjustment_type}</Badge>
                        <span className="font-medium tabular-nums">{naira(a.amount)}</span>
                        {isReversed && <span className="text-xs italic text-muted-foreground">reversed</span>}
                      </div>
                      <p className="mt-0.5">{a.reason}</p>
                      {a.reallocated_to && (
                        <p className="text-muted-foreground">Carried by: {a.reallocated_to}</p>
                      )}
                      <p className="text-muted-foreground">
                        {a.adjusted_by ?? "—"}
                        {a.adjusted_at ? ` · ${new Date(a.adjusted_at).toLocaleString()}` : ""}
                      </p>
                    </div>
                    {isAdmin && !isReversed && !isReversal && (
                      <Button
                        size="sm" variant="ghost" className="h-7 shrink-0 gap-1 px-2 text-xs"
                        disabled={reverse.isPending}
                        onClick={async () => {
                          const why = await askText("Why is this correction being reversed?");
                          if (why && why.trim()) reverse.mutate({ id: a.id, why: why.trim() });
                        }}
                      >
                        <Undo2 className="h-3 w-3" /> Reverse
                      </Button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {isAdmin ? (
        <section>
          <SectionLabel icon={<PenLine className="h-3.5 w-3.5" />} label="Apply a correction" />
          <div className="space-y-2">
            <Select value={type} onValueChange={setType}>
              <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                {TYPES.map((t) => (
                  <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {TYPES.find((t) => t.value === type)?.hint}
            </p>

            <div className="space-y-1">
              <Label className="text-xs">Amount</Label>
              <Input
                type="number" min="0" step="100" value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="h-8 text-xs" placeholder="0"
              />
            </div>

            {type === "reallocation" && (
              <div className="space-y-1">
                <Label className="text-xs">Who carries it instead</Label>
                <Input
                  value={to} onChange={(e) => setTo(e.target.value)}
                  className="h-8 text-xs"
                  placeholder="e.g. Hospital absorbs, HMO, returned to supplier"
                />
              </div>
            )}

            <div className="space-y-1">
              <Label className="text-xs">Reason</Label>
              <Input
                value={reason} onChange={(e) => setReason(e.target.value)}
                className="h-8 text-xs"
                placeholder="Why is this being corrected?"
              />
            </div>

            <Button
              size="sm" className="w-full"
              disabled={
                apply.isPending ||
                !(Number(amount) > 0) ||
                reason.trim().length < 3 ||
                (type === "reallocation" && !to.trim())
              }
              onClick={() => apply.mutate()}
            >
              {apply.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
              Record correction
            </Button>
            <p className="text-xs text-muted-foreground">
              Corrections are added to the trail above, never applied over the original.
              Undo by reversing, which is itself recorded.
            </p>
          </div>
        </section>
      ) : (
        <p className="flex items-start gap-1.5 rounded-md border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          Corrections move money after the fact, so they are admin-only. Ask an
          administrator to apply one.
        </p>
      )}
    </div>
  );
}
