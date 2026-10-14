import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, AlertTriangle, Trash2, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";

/**
 * Expired stock, and the means to write it off.
 *
 * "We need to give the pharmacy the ability to remove any expired inventory."
 *
 * Disposal zeroes the batch rather than deleting it. Destroying expired drugs is
 * a regulated act — NAFDAC expects a record of what went, how much, and who
 * authorised it — so the row survives with the quantity and value written into
 * the audit trail. Deleting would erase the evidence that the disposal happened.
 *
 * Empty expired batches are hidden by default: there are ~15,000 of them and
 * they are history, not a hazard. The ones that can still be dispensed by
 * mistake are the point.
 */
const naira = (v: any) => `₦${Number(v ?? 0).toLocaleString()}`;

export function ExpiredStockTab() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [includeEmpty, setIncludeEmpty] = useState(false);
  const [disposing, setDisposing] = useState<any | null>(null);
  const [reason, setReason] = useState("");
  const [qty, setQty] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["expired-batches", includeEmpty],
    queryFn: () => api.hospital.pharmacy.inventory.expired({ include_empty: includeEmpty }),
  });

  const batches: any[] = data?.batches ?? [];

  const dispose = useMutation({
    mutationFn: () =>
      api.hospital.pharmacy.inventory.disposeBatch(disposing.id, {
        reason: reason.trim() || undefined,
        quantity: qty ? Number(qty) : undefined,
      }),
    onSuccess: (d: any) => {
      toast({
        title: "Disposal recorded",
        description: `${d.disposed} units written off — ${naira(d.value_disposed)}. The batch and this action stay on the audit trail.`,
      });
      setDisposing(null); setReason(""); setQty("");
      void qc.invalidateQueries({ queryKey: ["expired-batches"] });
      void qc.invalidateQueries({ queryKey: ["pharmacy-inventory"] });
    },
    onError: (e: any) =>
      toast({ title: "Could not record it", description: e?.message, variant: "destructive" }),
  });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <Badge variant="outline" className="gap-1.5">
          <AlertTriangle className="h-3 w-3" />
          {data?.with_stock ?? 0} expired batch{(data?.with_stock ?? 0) === 1 ? "" : "es"} still holding stock
        </Badge>
        {Number(data?.total_value) > 0 && (
          <Badge variant="outline" className="border-red-500/40 text-red-700 dark:text-red-400 tabular-nums">
            {naira(data.total_value)} at risk
          </Badge>
        )}
        <div className="ml-auto flex items-center gap-2">
          <Switch id="incl-empty" checked={includeEmpty} onCheckedChange={setIncludeEmpty} />
          <Label htmlFor="incl-empty" className="text-xs text-muted-foreground">
            Include already-empty batches
          </Label>
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-10">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : batches.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-10 text-center">
          <ShieldCheck className="h-6 w-6 text-green-600" />
          <p className="text-sm font-medium">No expired stock on the shelf</p>
          <p className="max-w-md text-xs text-muted-foreground">
            Nothing past its expiry date is still holding stock. Turn on
            already-empty batches above to review historical expiries.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Drug</TableHead>
                <TableHead>Batch</TableHead>
                <TableHead>Expired</TableHead>
                <TableHead className="text-right">On hand</TableHead>
                <TableHead className="text-right">Value</TableHead>
                <TableHead className="w-[110px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {batches.map((b) => {
                const onHand = Number(b.quantity_on_hand ?? 0);
                return (
                  <TableRow key={b.id} className={onHand > 0 ? "bg-red-500/5" : undefined}>
                    <TableCell className="text-sm font-medium">{b.drug_name ?? `Drug ${b.formulary_id}`}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{b.batch_number ?? "—"}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{b.expiry_date ?? "—"}</TableCell>
                    <TableCell className="text-right text-sm tabular-nums">{onHand.toLocaleString()}</TableCell>
                    <TableCell className="text-right text-sm tabular-nums">
                      {onHand > 0 ? naira(b.value_at_risk) : "—"}
                    </TableCell>
                    <TableCell>
                      {onHand > 0 ? (
                        <Button
                          size="sm" variant="outline"
                          className="h-7 gap-1 px-2 text-xs border-red-500/40 text-red-700 hover:bg-red-500/10 dark:text-red-400"
                          onClick={() => { setDisposing(b); setQty(String(onHand)); setReason(""); }}
                        >
                          <Trash2 className="h-3 w-3" /> Dispose
                        </Button>
                      ) : (
                        <span className="text-xs text-muted-foreground">already empty</span>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={!!disposing} onOpenChange={(o) => { if (!o) setDisposing(null); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Dispose of expired stock</DialogTitle>
            <DialogDescription>
              {disposing?.drug_name} · batch {disposing?.batch_number} · expired{" "}
              {disposing?.expiry_date}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div className="space-y-1">
              <Label className="text-xs">Quantity to dispose of</Label>
              <Input
                type="number" min="0.01" step="1" value={qty}
                onChange={(e) => setQty(e.target.value)}
                className="h-8 text-sm"
              />
              <p className="text-xs text-muted-foreground">
                Batch holds {Number(disposing?.quantity_on_hand ?? 0).toLocaleString()}.
                Dispose of less if only part is damaged.
              </p>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Reason</Label>
              <Input
                value={reason} onChange={(e) => setReason(e.target.value)}
                placeholder="Expired — destroyed per NAFDAC procedure"
                className="h-8 text-sm"
              />
            </div>
            <p className="rounded-md border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
              The batch record is kept and the quantity, value and your name go on
              the audit trail. Nothing is deleted.
            </p>
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setDisposing(null)}>Cancel</Button>
            <Button
              variant="destructive"
              disabled={dispose.isPending || !(Number(qty) > 0)}
              onClick={() => dispose.mutate()}
            >
              {dispose.isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              Record disposal
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
