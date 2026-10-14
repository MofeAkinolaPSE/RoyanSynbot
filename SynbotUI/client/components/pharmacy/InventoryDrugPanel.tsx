import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Boxes, Loader2, Truck, Wand2
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useAuth } from "@/components/AuthProvider";
import { useToast } from "@/hooks/use-toast";
import { RiskTierBadge, DetailRow } from "@/components/pharmacy/pharmacy-shared";
import { BatchTable } from "@/components/pharmacy/BatchTable";
import { DispensingTrendChart } from "@/components/pharmacy/DispensingTrendChart";
import { HelpHint } from "@/components/help/HelpHint";
import { PANEL_WIDTH } from "@/components/shared/panel-shared";
import { cn } from "@/lib/utils";

const INVENTORY_WRITE_ROLES = ["pharmacist", "admin"];

const emptyReceiveForm = { batch_number: "", quantity_received: "", unit_cost: "", supplier: "", location: "", expiry_date: "" };

export function InventoryDrugPanel({ formularyId, onClose, onReorder }: {
  formularyId: number;
  onClose: () => void;
  onReorder: (formularyId: number, drugName: string, suggestedQty?: number | null) => void;
}) {
  const { roles } = useAuth();
  const canWrite = roles.some(r => INVENTORY_WRITE_ROLES.includes(r) || r === "admin");
  const { toast } = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState("detail");
  const [receiveForm, setReceiveForm] = useState({ ...emptyReceiveForm });
  const [adjustingId, setAdjustingId] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["inventory-drug", formularyId],
    queryFn: () => api.hospital.pharmacy.inventory.drug(formularyId),
    refetchInterval: 20_000,
  });

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ["inventory-drug", formularyId] });
    void qc.invalidateQueries({ queryKey: ["inventory-cards"] });
    void qc.invalidateQueries({ queryKey: ["inventory-summary"] });
  };

  // Prefill from the last delivery: "if they say it's amoxiclav, you can just
  // type a-m-o and the rest comes in." Fetched only when the tab is open so the
  // panel does not pay for it on every drug.
  const { data: suggestion } = useQuery({
    queryKey: ["restock-suggestion", formularyId],
    queryFn: () => api.hospital.pharmacy.inventory.restockSuggestion(formularyId),
    enabled: tab === "receive",
  });

  const applySuggestion = () => {
    const sg = suggestion?.suggested ?? {};
    setReceiveForm((f) => ({
      ...f,
      // batch_number is deliberately NOT prefilled — two deliveries sharing a
      // batch number cannot be told apart on a recall.
      quantity_received: sg.quantity != null ? String(sg.quantity) : f.quantity_received,
      unit_cost: sg.unit_cost != null ? String(sg.unit_cost) : f.unit_cost,
      supplier: sg.supplier ?? f.supplier,
      location: sg.location ?? f.location,
      expiry_date: sg.expiry_date ?? f.expiry_date,
    }));
  };

  const receiveMut = useMutation({
    mutationFn: () => api.hospital.pharmacy.inventory.receiveBatch(formularyId, {
      batch_number: receiveForm.batch_number,
      quantity_received: Number(receiveForm.quantity_received),
      unit_cost: receiveForm.unit_cost ? Number(receiveForm.unit_cost) : undefined,
      supplier: receiveForm.supplier || undefined,
      location: receiveForm.location || undefined,
      expiry_date: receiveForm.expiry_date || undefined,
    }),
    onSuccess: () => {
      toast({ title: "Batch received" });
      setReceiveForm({ ...emptyReceiveForm });
      invalidateAll();
    },
    onError: (e: any) => toast({ title: "Failed to receive batch", description: e.message, variant: "destructive" }),
  });

  const adjustMut = useMutation({
    mutationFn: ({ batchId, adjustment, reason }: { batchId: number; adjustment: number; reason: string }) =>
      api.hospital.pharmacy.inventory.adjustBatch(batchId, { adjustment, reason }),
    onMutate: ({ batchId }) => setAdjustingId(batchId),
    onSuccess: () => { toast({ title: "Batch adjusted" }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Adjustment failed", description: e.message, variant: "destructive" }),
    onSettled: () => setAdjustingId(null),
  });

  const formulary = data?.formulary;
  // Only stock that can actually be dispensed. Expired and emptied batches are
  // returned separately and shown behind a toggle: this panel opened on 112
  // rows for Clarithromycin, 111 of them long-empty, with the one batch holding
  // 285 units at the very bottom.
  const batches = data?.batches ?? [];
  const historical = data?.historical_batches ?? [];
  const historicalCount = Number(data?.historical_batch_count ?? 0);
  const [showHistory, setShowHistory] = useState(false);

  // Migrated per-batch pricing — the only place actual margin is visible, since
  // royan_inventory_batches carries a single unit_cost and no retail price.
  const { data: ratesData, isLoading: ratesLoading } = useQuery({
    queryKey: ["inventory-drug-rates", formularyId],
    queryFn: () => api.hospital.pharmacy.inventory.drugRates(formularyId),
    enabled: tab === "pricing",
    staleTime: 300_000,
  });
  const rates: any[] = ratesData?.rates ?? [];
  const risk = data?.risk;
  const demand = data?.demand ?? { current_window_qty: 0, prior_window_qty: 0, direction: "stable", confidence: "no_recent_demand" };
  const drugName = formulary?.generic_name || formulary?.brand_name || formulary?.code || "Drug";

  return (
    <Sheet open onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className={cn(PANEL_WIDTH.default, "overflow-y-auto p-0 flex flex-col")} side="right">
        {isLoading && !data ? (
          <div className="p-5 space-y-3">
            <Skeleton className="h-8 w-2/3" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : !formulary ? (
          <div className="p-5 text-sm text-muted-foreground">Drug not found.</div>
        ) : (
          <>
            <SheetHeader className="px-5 pt-5 pb-4 border-b shrink-0">
              <div className="flex items-start gap-3">
                <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                  <Boxes className="h-5 w-5 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <SheetTitle className="text-base leading-tight">{drugName}</SheetTitle>
                  <div className="flex flex-wrap items-center gap-2 mt-1">
                    {formulary.code && <Badge variant="outline" className="text-xs font-mono">{formulary.code}</Badge>}
                    {risk && <RiskTierBadge tier={risk.tier} />}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    {[formulary.form, formulary.strength, formulary.category].filter(Boolean).join(" · ")}
                  </p>
                </div>
              </div>
            </SheetHeader>

            <Tabs value={tab} onValueChange={setTab} className="flex-1 flex flex-col min-h-0">
              <TabsList className="mx-5 mt-3 bg-muted border border-border shrink-0 flex-wrap h-auto">
                <TabsTrigger value="detail">Detail</TabsTrigger>
                <TabsTrigger value="batches">Stock ({batches.length})</TabsTrigger>
                <TabsTrigger value="pricing">Pricing{rates.length > 0 ? ` (${rates.length})` : ""}</TabsTrigger>
                <TabsTrigger value="trend">Trend</TabsTrigger>
                {canWrite && <TabsTrigger value="receive">Receive Stock</TabsTrigger>}
              </TabsList>

              <div className="flex-1 overflow-y-auto px-5 py-4">
                {/* ── Detail ── */}
                <TabsContent value="detail" className="mt-0 space-y-3">
                  <section className="rounded-md border p-3 text-sm flex items-center justify-between">
                    <div>
                      <p className="text-xs text-muted-foreground">Total On Hand</p>
                      <p className="font-semibold text-lg tabular-nums">{data?.total_qty_on_hand ?? 0}</p>
                    </div>
                    {risk?.recommended_reorder_qty ? (
                      <Button size="sm" variant="outline" className="gap-1.5 border-amber-400/40 text-amber-500 hover:bg-amber-500/10"
                        onClick={() => onReorder(formularyId, drugName, risk.recommended_reorder_qty)}>
                        <Truck className="h-3.5 w-3.5" /> Reorder {risk.recommended_reorder_qty}
                      </Button>
                    ) : null}
                  </section>

                  <section className="rounded-md border p-3 space-y-1">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Why this tier</p>
                    <DetailRow label="Risk tier" value={risk?.tier} />
                    <DetailRow label="Stock coverage" value={risk?.stock_coverage_days != null ? `${risk.stock_coverage_days} days` : "No demand signal"} />
                    <DetailRow label="Lead time" value={formulary.lead_time_days ? `${formulary.lead_time_days} days` : "Default (14 days)"} />
                    <DetailRow label="Safety stock" value={formulary.safety_stock_days ? `${formulary.safety_stock_days} days` : "Default (7 days)"} />
                    <DetailRow label="Predicted stockout" value={risk?.predicted_stockout_date} />
                    <DetailRow label="Manual reorder floor" value={formulary.reorder_level != null ? String(formulary.reorder_level) : null} />
                  </section>

                  <section className="rounded-md border p-3 space-y-1">
                    <DetailRow label="Category" value={formulary.category} />
                    <DetailRow label="Drug class" value={formulary.drug_class} />
                    <DetailRow label="Unit" value={formulary.unit} />
                    <DetailRow label="Requires prescription" value={formulary.requires_prescription ? "Yes" : "No"} />
                    <DetailRow label="Controlled substance" value={formulary.is_controlled ? "Yes" : "No"} />
                  </section>
                </TabsContent>

                {/* ── Batches ── */}
                <TabsContent value="batches" className="mt-0 space-y-2">
                  {batches.length === 0 ? (
                    <p className="py-6 text-center text-xs text-muted-foreground">
                      No dispensable stock. Any quantity this drug had has been used
                      or has expired — use Receive Stock to bring more in.
                    </p>
                  ) : (
                    <BatchTable
                      batches={batches}
                      adjustingId={adjustingId}
                      onAdjust={(batch, adjustment, reason) => adjustMut.mutate({ batchId: batch.id, adjustment, reason })}
                    />
                  )}

                  {historicalCount > 0 && (
                    <div className="pt-1">
                      <button
                        onClick={() => setShowHistory((v) => !v)}
                        className="text-xs text-muted-foreground hover:text-foreground hover:underline"
                      >
                        {showHistory ? "Hide" : "Show"} {historicalCount} past batch
                        {historicalCount === 1 ? "" : "es"} (used up or expired)
                      </button>
                      {showHistory && (
                        <div className="mt-2 opacity-70">
                          <BatchTable batches={historical} adjustingId={null} onAdjust={() => {}} />
                        </div>
                      )}
                    </div>
                  )}
                </TabsContent>

                {/* ── Pricing (migrated per-batch rates) ── */}
                <TabsContent value="pricing" className="mt-0 space-y-2">
                  {ratesLoading ? (
                    <p className="text-xs text-muted-foreground">Loading…</p>
                  ) : rates.length === 0 ? (
                    <p className="text-xs italic text-muted-foreground">
                      No historical pricing for this drug.
                    </p>
                  ) : (
                    <>
                      <p className="text-xs text-muted-foreground">
                        Historical per-batch pricing migrated from the legacy system. Cost is what
                        Royan paid; MRP is the retail price.
                      </p>
                      <div className="overflow-x-auto rounded-md border">
                        <table className="w-full text-xs">
                          <thead className="bg-muted/40">
                            <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                              <th className="px-2 py-1.5">Batch</th>
                              <th className="px-2 py-1.5 text-right">Cost</th>
                              <th className="px-2 py-1.5 text-right">MRP</th>
                              <th className="px-2 py-1.5 text-right">Margin <HelpHint id="pharmacy-batch-margin" side="left" align="end" /></th>
                              <th className="px-2 py-1.5">Expiry</th>
                            </tr>
                          </thead>
                          <tbody>
                            {rates.map((r: any) => {
                              const expired = r.expiry_date && new Date(r.expiry_date) < new Date();
                              return (
                                <tr key={r.id} className="border-t">
                                  <td className="px-2 py-1.5 font-mono">{r.batch_number}</td>
                                  <td className="px-2 py-1.5 text-right tabular-nums">
                                    {r.purchase_price != null ? `₦${Number(r.purchase_price).toLocaleString()}` : "—"}
                                  </td>
                                  <td className="px-2 py-1.5 text-right tabular-nums">
                                    {r.mrp != null ? `₦${Number(r.mrp).toLocaleString()}` : "—"}
                                  </td>
                                  <td className="px-2 py-1.5 text-right tabular-nums">
                                    {r.margin != null ? (
                                      <span className={r.margin > 0 ? "text-green-600 dark:text-green-400" : "text-red-600"}>
                                        ₦{Number(r.margin).toLocaleString()}
                                        {r.margin_pct != null && (
                                          <span className="ml-1 text-xs text-muted-foreground">{r.margin_pct}%</span>
                                        )}
                                      </span>
                                    ) : "—"}
                                  </td>
                                  <td className={`px-2 py-1.5 ${expired ? "text-red-600" : "text-muted-foreground"}`}>
                                    {r.expiry_date ?? "—"}
                                    {expired && <span className="ml-1 text-xs">expired</span>}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}
                </TabsContent>

                {/* ── Trend ── */}
                <TabsContent value="trend" className="mt-0">
                  <DispensingTrendChart events={data?.recent_dispensing ?? []} demand={demand} />
                </TabsContent>

                {/* ── Receive Stock ── */}
                {canWrite && (
                  <TabsContent value="receive" className="mt-0 space-y-3">
                    {suggestion?.based_on && (
                      <div className="rounded-md border bg-muted/40 p-2.5 text-xs">
                        <p className="font-medium">Last delivery</p>
                        <p className="mt-0.5 text-muted-foreground">
                          {[
                            suggestion.based_on.last_received_at
                              ? new Date(suggestion.based_on.last_received_at).toLocaleDateString()
                              : null,
                            suggestion.suggested?.supplier,
                            suggestion.suggested?.unit_cost != null
                              ? `₦${Number(suggestion.suggested.unit_cost).toLocaleString()} each`
                              : null,
                          ].filter(Boolean).join(" · ") || "no details recorded"}
                        </p>
                        {suggestion.based_on.observed_shelf_life_days > 0 && (
                          <p className="mt-0.5 text-muted-foreground">
                            Shelf life was {suggestion.based_on.observed_shelf_life_days} days, so
                            the suggested expiry is {suggestion.suggested?.expiry_date} — moved
                            forward from the last date rather than copied.
                          </p>
                        )}
                        <Button
                          size="sm" variant="outline"
                          className="mt-1.5 h-7 gap-1 px-2 text-xs"
                          onClick={applySuggestion}
                        >
                          <Wand2 className="h-3 w-3" /> Fill from last delivery
                        </Button>
                      </div>
                    )}
                    <div className="grid grid-cols-2 gap-2">
                      <div className="col-span-2 space-y-1">
                        <Label className="text-xs">Batch Number *</Label>
                        <Input value={receiveForm.batch_number} onChange={e => setReceiveForm(f => ({ ...f, batch_number: e.target.value }))} />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs">Quantity Received *</Label>
                        <Input type="number" value={receiveForm.quantity_received} onChange={e => setReceiveForm(f => ({ ...f, quantity_received: e.target.value }))} />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs">Unit Cost</Label>
                        <Input type="number" value={receiveForm.unit_cost} onChange={e => setReceiveForm(f => ({ ...f, unit_cost: e.target.value }))} />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs">Expiry Date</Label>
                        <Input type="date" value={receiveForm.expiry_date} onChange={e => setReceiveForm(f => ({ ...f, expiry_date: e.target.value }))} />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs">Supplier</Label>
                        <Input value={receiveForm.supplier} onChange={e => setReceiveForm(f => ({ ...f, supplier: e.target.value }))} />
                      </div>
                      <div className="col-span-2 space-y-1">
                        <Label className="text-xs">Location</Label>
                        <Input value={receiveForm.location} onChange={e => setReceiveForm(f => ({ ...f, location: e.target.value }))} />
                      </div>
                    </div>
                    <Button size="sm" className="w-full gap-1.5"
                      disabled={!receiveForm.batch_number.trim() || !receiveForm.quantity_received.trim() || receiveMut.isPending}
                      onClick={() => receiveMut.mutate()}>
                      {receiveMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Boxes className="h-3.5 w-3.5" />}
                      Receive Batch
                    </Button>
                  </TabsContent>
                )}
              </div>
            </Tabs>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
