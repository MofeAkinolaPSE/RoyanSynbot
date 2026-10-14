import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { ReceiptText, Loader2, ShieldCheck, Plus, Trash2, AlertTriangle, BedDouble, Building2 } from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { PANEL_WIDTH } from "@/components/shared/panel-shared";

interface GenerateBillPanelProps {
  encounter: {
    id: string | number;
    patient_id: string | number;
    patient_name?: string;
    patient_mrn?: string;
    queue_number?: string;
    chief_complaint?: string;
  };
  onClose: () => void;
}

interface ItemRow {
  key: string;
  source: "lab" | "pharmacy" | "manual";
  description: string;
  category: string;
  quantity: number;
  unit_price: number;
  matched: boolean;
}

const MANUAL_CATEGORIES = [
  { value: "consultation", label: "Consultation" },
  { value: "procedure", label: "Procedure" },
  { value: "misc", label: "Miscellaneous" },
];

let rowKeySeq = 0;
const nextKey = () => `row-${++rowKeySeq}`;

export function GenerateBillPanel({ encounter, onClose }: GenerateBillPanelProps) {
  const { toast } = useToast();
  const qc = useQueryClient();
  const [items, setItems] = useState<ItemRow[]>([]);
  const [discount, setDiscount] = useState("");
  const [notes, setNotes] = useState("");
  const [seeded, setSeeded] = useState(false);

  const { data: suggested, isLoading } = useQuery({
    queryKey: ["bill-suggested-items", encounter.id],
    queryFn: () => api.hospital.billing.getSuggestedItems(encounter.id),
  });

  // Seed the editable table once from what this encounter actually incurred
  // (lab + pharmacy) — staff can still edit/remove any row afterward.
  useEffect(() => {
    if (seeded || !suggested) return;
    const rows: ItemRow[] = (suggested.suggested_items || []).map((s: any) => ({
      key: nextKey(),
      source: s.category === "pharmacy" ? "pharmacy" : "lab",
      description: s.description,
      category: s.category,
      quantity: Number(s.quantity) || 1,
      unit_price: Number(s.unit_price) || 0,
      matched: !!s.matched,
    }));
    setItems(rows);
    setSeeded(true);
  }, [suggested, seeded]);

  const patient = suggested?.patient;
  const encounterInfo = suggested?.encounter;
  const admitted = !!encounterInfo?.admitted;
  const inpatientLines = suggested?.inpatient_lines || [];
  const inpatientRunningTotal = Number(suggested?.inpatient_running_total) || 0;

  const payerLabel = patient?.patient_type === "hmo"
    ? (patient?.hmo_provider || "HMO")
    : patient?.patient_type === "private" ? "Private" : "Cash / Self-pay";

  function addManualRow() {
    setItems(rows => [...rows, {
      key: nextKey(), source: "manual", description: "", category: "consultation", quantity: 1, unit_price: 0, matched: true,
    }]);
  }
  function updateRow(key: string, patch: Partial<ItemRow>) {
    setItems(rows => rows.map(r => (r.key === key ? { ...r, ...patch } : r)));
  }
  function removeRow(key: string) {
    setItems(rows => rows.filter(r => r.key !== key));
  }

  const total = items.reduce((s, r) => s + (Number(r.quantity) || 0) * (Number(r.unit_price) || 0), 0);
  const validItems = items.filter(r => r.description.trim() && (Number(r.unit_price) || 0) >= 0);
  const hasUnpricedMatches = items.some(r => r.source === "lab" && !r.matched && (Number(r.unit_price) || 0) === 0);

  const createMut = useMutation({
    mutationFn: () => api.hospital.billing.createBillFromEncounter({
      encounter_id: Number(encounter.id),
      patient_id: Number(encounter.patient_id),
      items: validItems.map(r => ({
        description: r.description.trim(),
        category: r.category,
        quantity: Number(r.quantity) || 1,
        unit_price: Number(r.unit_price) || 0,
      })),
      discount: Number(discount) || 0,
      notes: notes || undefined,
    }),
    onSuccess: () => {
      toast({ title: "Bill generated" });
      void qc.invalidateQueries({ queryKey: ["hospital-bills"] });
      void qc.invalidateQueries({ queryKey: ["hospital-billing-stats"] });
      void qc.invalidateQueries({ queryKey: ["hospital-unbilled-encounters"] });
      onClose();
    },
    onError: (e: any) => toast({ title: "Failed to generate bill", description: e.message, variant: "destructive" }),
  });

  return (
    <Sheet open onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className={cn(PANEL_WIDTH.default, "overflow-y-auto p-0 flex flex-col")} side="right">
        <SheetHeader className="px-5 pt-5 pb-4 border-b shrink-0">
          <div className="flex items-start gap-3">
            <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
              <ReceiptText className="h-5 w-5 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <SheetTitle className="text-base leading-tight">Generate Bill</SheetTitle>
              <div className="flex flex-wrap items-center gap-2 mt-1">
                <span className="text-sm text-muted-foreground">{encounter.patient_name ?? `Patient ID ${encounter.patient_id}`}</span>
                {encounter.patient_mrn && <Badge variant="outline" className="text-xs font-mono">{encounter.patient_mrn}</Badge>}
                {patient && (
                  <Badge variant="outline" className={cn(
                    "text-xs gap-1",
                    patient.patient_type === "hmo" ? "text-green-600 border-green-500/40 bg-green-500/10" : "text-muted-foreground",
                  )}>
                    <ShieldCheck className="h-3 w-3" />{payerLabel}
                  </Badge>
                )}
                {encounterInfo && (
                  <Badge variant="outline" className="text-xs gap-1">
                    {admitted ? <BedDouble className="h-3 w-3" /> : <Building2 className="h-3 w-3" />}
                    {admitted ? "In-house / Admitted" : "Outpatient"}
                  </Badge>
                )}
              </div>
              <p className="text-sm text-muted-foreground mt-1">
                {encounter.queue_number ?? `Encounter #${encounter.id}`}
                {encounter.chief_complaint ? ` · ${encounter.chief_complaint}` : ""}
              </p>
            </div>
          </div>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {isLoading ? (
            <div className="flex justify-center py-10"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
          ) : (
            <>
              {hasUnpricedMatches && (
                <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
                  <span>One or more lab tests couldn't be auto-priced from the catalog — set a price manually below before generating the bill.</span>
                </div>
              )}

              <div className="space-y-2">
                <div className="grid grid-cols-[1fr_100px_90px_110px_32px] gap-2 text-sm font-medium text-muted-foreground px-1">
                  <span>Item</span><span>Category</span><span>Qty</span><span>Unit Price (₦)</span><span></span>
                </div>
                {items.map(row => (
                  <div key={row.key} className="grid grid-cols-[1fr_100px_90px_110px_32px] gap-2 items-center">
                    {row.source === "manual" ? (
                      <Input className="h-8 text-sm" placeholder="Description" value={row.description}
                        onChange={e => updateRow(row.key, { description: e.target.value })} />
                    ) : (
                      <div className="flex items-center gap-1.5 text-sm truncate">
                        <span className="truncate">{row.description}</span>
                        {row.source === "lab" && !row.matched && (
                          <Badge variant="outline" className="text-xs text-amber-600 border-amber-500/40 shrink-0">needs price</Badge>
                        )}
                      </div>
                    )}
                    {row.source === "manual" ? (
                      <Select value={row.category} onValueChange={v => updateRow(row.key, { category: v })}>
                        <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {MANUAL_CATEGORIES.map(c => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    ) : (
                      <span className="text-sm text-muted-foreground capitalize">{row.category}</span>
                    )}
                    <Input type="number" min="1" className="h-8 text-sm" value={row.quantity}
                      onChange={e => updateRow(row.key, { quantity: Number(e.target.value) || 1 })} />
                    <Input type="number" min="0" className="h-8 text-sm" value={row.unit_price}
                      onChange={e => updateRow(row.key, { unit_price: Number(e.target.value) || 0 })} />
                    <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => removeRow(row.key)}>
                      <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                    </Button>
                  </div>
                ))}
                <Button variant="outline" size="sm" className="gap-1.5" onClick={addManualRow}>
                  <Plus className="h-3.5 w-3.5" /> Add Line (Consultation / Procedure / Misc)
                </Button>
              </div>

              {admitted && (
                <div className="rounded-md border p-3 space-y-1.5">
                  <div className="flex items-center gap-1.5 text-sm font-medium">
                    <BedDouble className="h-3.5 w-3.5 text-muted-foreground" /> Ward / Nursing Charges (from running bill)
                  </div>
                  {inpatientLines.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No ward charges recorded yet for this admission.</p>
                  ) : (
                    <ul className="space-y-1">
                      {inpatientLines.map((l: any) => (
                        <li key={l.id} className="flex items-center justify-between text-sm text-muted-foreground">
                          <span>{l.service_name} × {l.quantity}</span>
                          <span>₦{Number(l.total || 0).toLocaleString("en-NG", { minimumFractionDigits: 2 })}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className="text-sm text-muted-foreground pt-1 border-t">
                    Running total: ₦{inpatientRunningTotal.toLocaleString("en-NG", { minimumFractionDigits: 2 })} — shown on the printed invoice automatically, not re-billed here.
                  </p>
                </div>
              )}

              <div className="space-y-1">
                <Label className="text-sm">Discount (₦)</Label>
                <Input type="number" min="0" className="h-8 text-sm" value={discount} onChange={e => setDiscount(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label className="text-sm">Notes</Label>
                <Textarea rows={2} placeholder="Optional notes…" value={notes} onChange={e => setNotes(e.target.value)} />
              </div>

              <div className="rounded-md border p-3 flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Subtotal (excl. ward charges)</span>
                <span className="font-semibold">{`₦${total.toLocaleString("en-NG", { minimumFractionDigits: 2 })}`}</span>
              </div>
            </>
          )}
        </div>

        <Separator className="shrink-0" />
        <div className="px-5 py-3 flex justify-end gap-2 shrink-0">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={validItems.length === 0 || createMut.isPending} onClick={() => createMut.mutate()} className="gap-1.5">
            {createMut.isPending && <Loader2 className="h-4 w-4 animate-spin" />}Generate Bill
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
