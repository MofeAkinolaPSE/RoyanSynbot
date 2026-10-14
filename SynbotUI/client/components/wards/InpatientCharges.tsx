import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Receipt, Loader2, Plus, X, AlertTriangle, FileText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { SectionLabel } from "@/components/shared/panel-shared";
import { CatalogCombobox } from "@/components/shared/CatalogCombobox";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

/**
 * The running bill for an admitted patient.
 *
 * "when a patient is in admission... you can even generate the billing for the
 * patient that's in admission" and "every time you add a new consultant, a new
 * lab, a new scan, a drug, the bill must also keep track of that."
 *
 * This is what makes the inpatient panel different from the outpatient one. An
 * outpatient bill is settled once at the end of a visit; an inpatient bill grows
 * every day they stay and every time anything is added, so the number has to be
 * visible while they are still in the bed rather than assembled at discharge.
 *
 * The room charge is DERIVED from the admission date, not stored, so it cannot
 * drift from the real length of stay. It appears alongside ad-hoc charges but
 * cannot be deleted — removing it would mean claiming the patient was not in the
 * bed.
 */
const naira = (v: any) => `₦${Number(v ?? 0).toLocaleString()}`;

const CATEGORIES = [
  "consultation", "lab", "imaging", "pharmacy",
  "procedure", "nursing", "consumable", "ambulance", "misc",
];

export function InpatientCharges({
  encounterId,
  onGenerateBill,
}: {
  encounterId: number | string;
  onGenerateBill?: () => void;
}) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ description: "", category: "misc", quantity: "1", unit_price: "" });

  const { data, isLoading } = useQuery({
    queryKey: ["encounter-charges", encounterId],
    queryFn: () => api.hospital.billing.encounterCharges(encounterId),
    refetchInterval: 60_000,
  });

  const charges: any[] = data?.charges ?? [];
  const total = Number(data?.total ?? 0);
  const unpricedRoom = charges.some((c: any) => c.needs_rate);

  const reset = () => setForm({ description: "", category: "misc", quantity: "1", unit_price: "" });

  const add = useMutation({
    mutationFn: () =>
      api.hospital.billing.addEncounterCharge(encounterId, {
        description: form.description.trim(),
        category: form.category,
        quantity: Number(form.quantity) || 1,
        unit_price: Number(form.unit_price) || 0,
      }),
    onSuccess: () => {
      reset();
      setAdding(false);
      void qc.invalidateQueries({ queryKey: ["encounter-charges", encounterId] });
      toast({ title: "Charge added to the running bill" });
    },
    onError: (e: any) =>
      toast({ title: "Could not add", description: e?.message, variant: "destructive" }),
  });

  const remove = useMutation({
    mutationFn: (chargeId: number) =>
      api.hospital.billing.removeEncounterCharge(encounterId, chargeId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["encounter-charges", encounterId] });
      toast({ title: "Charge removed" });
    },
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <SectionLabel icon={<Receipt className="h-3.5 w-3.5" />} label="Running charges" />
        <Badge variant="outline" className="ml-auto text-xs tabular-nums">{naira(total)}</Badge>
      </div>

      {unpricedRoom && (
        <p className="flex items-start gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          This ward has no nightly rate set, so the bed is charging nothing. Set it on
          the billing page before this patient is discharged.
        </p>
      )}

      {isLoading ? (
        <div className="flex justify-center py-6">
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        </div>
      ) : charges.length === 0 ? (
        <p className="py-4 text-center text-xs text-muted-foreground">
          Nothing charged yet. Room charges appear once a nightly rate is set for the ward.
        </p>
      ) : (
        <ul className="space-y-1">
          {charges.map((c: any, i: number) => (
            <li
              key={c.id ?? `derived-${i}`}
              className="flex items-start justify-between gap-2 border-b border-border/30 py-1.5 last:border-0"
            >
              <div className="min-w-0">
                <p className="text-xs font-medium">{c.description}</p>
                <p className="text-xs text-muted-foreground">
                  <span className="capitalize">{c.category}</span>
                  {Number(c.quantity) !== 1 && ` · ${c.quantity} × ${naira(c.unit_price)}`}
                  {c.derived && " · from the admission date"}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <span className="text-xs font-medium tabular-nums">{naira(c.total)}</span>
                {/* Derived room charges have no delete: removing one would
                    assert the patient was never in the bed. Change the stay or
                    the rate instead. */}
                {!c.derived && c.id && (
                  <Button
                    size="icon" variant="ghost" className="h-6 w-6"
                    aria-label={`Remove ${c.description}`}
                    disabled={remove.isPending}
                    onClick={() => remove.mutate(c.id)}
                  >
                    <X className="h-3 w-3" />
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {!adding ? (
        <div className="flex gap-2">
          <Button size="sm" variant="outline" className="flex-1 gap-1.5" onClick={() => setAdding(true)}>
            <Plus className="h-3.5 w-3.5" /> Add charge
          </Button>
          {onGenerateBill && (
            <Button size="sm" className="flex-1 gap-1.5" onClick={onGenerateBill}>
              <FileText className="h-3.5 w-3.5" /> Generate bill
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-2 rounded-md border bg-muted/30 p-2.5">
          <div className="space-y-1">
            <Label className="text-xs">Service</Label>
            {/* Catalogue-backed, so the price comes from the priced catalogue
                rather than being typed from memory. Free text still allowed —
                not everything chargeable is in the catalogue. */}
            <CatalogCombobox
              value={form.description}
              onChange={(v) => setForm((f) => ({ ...f, description: v }))}
              onSelect={(o) => {
                // Selecting from the catalogue fills the price and category too,
                // so the common case is one action rather than three fields
                // typed from memory. 1,119 of 1,221 services are priced.
                setForm((f) => ({
                  ...f,
                  description: o.label,
                  unit_price: o.raw?.base_price != null ? String(o.raw.base_price) : f.unit_price,
                  category: o.raw?.category ?? f.category,
                }));
              }}
              queryKey="inpatient-service-catalog"
              fetcher={(q) => api.hospital.coverage.services({ q, limit: 20 })}
              mapResults={(d) =>
                (d?.services ?? []).map((x: any) => ({
                  id: x.id,
                  label: x.name,
                  sublabel: x.base_price ? `₦${Number(x.base_price).toLocaleString()}` : "not priced",
                  raw: { base_price: x.base_price, category: x.category },
                }))
              }
              placeholder="Search services, or type your own…"
            />
          </div>

          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1">
              <Label className="text-xs">Qty</Label>
              <Input
                type="number" min="1" step="1" className="h-8 text-xs"
                value={form.quantity}
                onChange={(e) => setForm((f) => ({ ...f, quantity: e.target.value }))}
              />
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-xs">Unit price</Label>
              <Input
                type="number" min="0" step="100" className="h-8 text-xs"
                value={form.unit_price}
                onChange={(e) => setForm((f) => ({ ...f, unit_price: e.target.value }))}
              />
            </div>
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Category</Label>
            <Select value={form.category} onValueChange={(v) => setForm((f) => ({ ...f, category: v }))}>
              <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                {CATEGORIES.map((c) => (
                  <SelectItem key={c} value={c} className="capitalize">{c}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex gap-2">
            <Button
              size="sm" className="flex-1"
              disabled={add.isPending || !form.description.trim() || !(Number(form.unit_price) >= 0)}
              onClick={() => add.mutate()}
            >
              {add.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
              Add
            </Button>
            <Button size="sm" variant="ghost" onClick={() => { setAdding(false); reset(); }}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
