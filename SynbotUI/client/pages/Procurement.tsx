/**
 * Procurement & Stores (reportGUide.md s6): what to order, the stock orders, and who we buy from.
 *
 * Reorder plan: live shelf stock against what the pharmacy actually dispensed (180 days to the last
 * day dispensing data reaches). Stock orders: requested -> approved -> with the supplier -> received.
 * Nobody marks an order received: it closes when the stock arrives (Pharmacy > Receive stock, or a
 * supplier delivery in Roy Books).
 */
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Boxes, Building2, Package, ShoppingCart, Truck } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PageHeader } from "@/components/workspace/PageHeader";
import { KpiStrip } from "@/components/workspace/KpiStrip";
import { FilterBar } from "@/components/workspace/FilterBar";
import { useAuth } from "@/components/AuthProvider";
import { api } from "@/lib/api-client";
import { fmtDay, ReportButton } from "./ReportComposer";

type Dict = Record<string, any>;
const N = (v: any) => (v === null || v === undefined ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 }));
const M = (v: any) => {
  const n = Number(v ?? 0);
  return Math.abs(n) >= 1e6 ? `₦${(n / 1e6).toFixed(1)}M` : `₦${Math.round(n).toLocaleString()}`;
};
const PLAN: Record<string, { label: string; cls: string }> = {
  out_of_stock: { label: "Out of stock", cls: "border-red-500 text-red-600" },
  reorder_now: { label: "Order now", cls: "border-red-400 text-red-600" },
  reorder_soon: { label: "Order soon", cls: "border-amber-400 text-amber-600" },
  healthy: { label: "Enough", cls: "border-emerald-500 text-emerald-600" },
  no_recent_use: { label: "No recent use", cls: "text-muted-foreground" },
};
const ORDER: Record<string, string> = { recommended: "Requested", approved: "Approved", ordered: "With supplier", received: "Received", cancelled: "Cancelled" };
const PLACERS = ["pharmacist", "ops", "management", "admin"];
const APPROVERS = ["pharmacist", "ops", "finance", "management", "admin"];

export default function Procurement() {
  const qc = useQueryClient();
  const { roles } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "plan";
  const setTab = (t: string) => { const p = new URLSearchParams(params); p.set("tab", t); setParams(p, { replace: true }); };
  const ov = useQuery({ queryKey: ["procurement", "overview"], queryFn: () => api.stores.overview() });
  const o: Dict = ov.data ?? {};
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["procurement"] }); };

  return (
    <div className="flex flex-col gap-5">
      <PageHeader icon={ShoppingCart} title="Procurement & Stores"
        subtitle={`What to order, stock orders and suppliers · use measured to ${fmtDay(o.demand_to) || "…"} · purchases to ${fmtDay(o.purchases_to) || "…"}`} />
      <KpiStrip items={[
        { label: "To order now", value: N((o.out_of_stock ?? 0) + (o.reorder_now ?? 0)), icon: AlertTriangle,
          tone: (o.out_of_stock ?? 0) + (o.reorder_now ?? 0) ? "danger" : "default",
          sub: `${N(o.out_of_stock)} out of stock · ${M(o.to_order_value)} at last price`, onClick: () => setTab("plan") },
        { label: "Order soon", value: N(o.reorder_soon), icon: Boxes, tone: o.reorder_soon ? "warning" : "default",
          sub: `${N(o.expiry_risk)} drugs may expire before use`, onClick: () => setTab("plan") },
        { label: "Orders with suppliers", value: N(o.ordered), icon: Truck, tone: o.overdue_orders ? "danger" : "default",
          sub: `${N(o.overdue_orders)} overdue · ${N((o.requested ?? 0) + (o.approved ?? 0))} awaiting approval or placing`, onClick: () => setTab("orders") },
        { label: "Bought, last 12 months", value: M(o.purchases_12m), icon: Building2,
          sub: `${N(o.active_suppliers)} suppliers used`, onClick: () => setTab("suppliers") },
      ]} />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="plan">Reorder plan</TabsTrigger>
          <TabsTrigger value="orders">Stock orders{(o.requested ?? 0) + (o.approved ?? 0) + (o.ordered ?? 0) ? ` (${(o.requested ?? 0) + (o.approved ?? 0) + (o.ordered ?? 0)})` : ""}</TabsTrigger>
          <TabsTrigger value="suppliers">Suppliers</TabsTrigger>
        </TabsList>
        <TabsContent value="plan" className="mt-4"><Plan onRaised={refresh} /></TabsContent>
        <TabsContent value="orders" className="mt-4"><Orders roles={roles} onChange={refresh} /></TabsContent>
        <TabsContent value="suppliers" className="mt-4"><Suppliers /></TabsContent>
      </Tabs>
    </div>
  );
}

function Plan({ onRaised }: { onRaised: () => void }) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("needs");
  const [raise, setRaise] = useState<Dict | null>(null);
  const q = useQuery({ queryKey: ["procurement", "plan"], queryFn: () => api.stores.plan() });
  const items: Dict[] = q.data?.items ?? [];
  const rows = items.filter((i) =>
    (!search || `${i.drug} ${i.code} ${i.brand ?? ""}`.toLowerCase().includes(search.toLowerCase())) &&
    (status === "" || (status === "needs" ? ["out_of_stock", "reorder_now", "reorder_soon"].includes(i.status)
      : status === "expiry" ? !!i.expiry_risk_qty : i.status === status)));
  return (
    <div className="space-y-3">
      <FilterBar search={{ value: search, onChange: setSearch, placeholder: "Search drug or code" }}
        selects={[{ label: "Show", value: status, onChange: setStatus, placeholder: "All drugs",
          options: [{ value: "needs", label: "Needs ordering (now or soon)" }, ...Object.entries(PLAN).map(([k, v]) => ({ value: k, label: v.label })),
                    { value: "expiry", label: "May expire before use" }] }]} />
      <p className="text-xs text-muted-foreground">
        Use per day = units dispensed in the {q.data?.demand_days ?? 180} days to {fmtDay(q.data?.demand_to)}. Order when the shelf will not cover the
        supplier lead time plus safety stock; the suggestion tops cover up by a further review period, less what is already on order. Expired stock is not counted as cover.
      </p>
      <div className="rounded-xl border bg-card">
        {q.isLoading ? <p className="p-6 text-sm text-muted-foreground">Working out the plan...</p> : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Drug</TableHead><TableHead>Status</TableHead><TableHead className="text-right">On shelf</TableHead>
                <TableHead className="text-right">Use / day</TableHead><TableHead className="text-right">Cover (days)</TableHead>
                <TableHead className="text-right">On order</TableHead><TableHead className="text-right">Suggest</TableHead>
                <TableHead>Last bought from</TableHead><TableHead />
              </TableRow></TableHeader>
              <TableBody>
                {rows.length === 0 && <TableRow><TableCell colSpan={9} className="py-6 text-center text-sm text-muted-foreground">Nothing in this view.</TableCell></TableRow>}
                {rows.slice(0, 300).map((i) => (
                  <TableRow key={i.formulary_id}>
                    <TableCell><div className="font-medium">{i.drug}</div><div className="text-xs text-muted-foreground">{i.code}{i.strength ? ` · ${i.strength}` : ""}{i.expiry_risk_qty ? <span className="text-amber-600"> · {N(i.expiry_risk_qty)} may expire unused</span> : null}</div></TableCell>
                    <TableCell><Badge variant="outline" className={PLAN[i.status]?.cls}>{PLAN[i.status]?.label ?? i.status}</Badge></TableCell>
                    <TableCell className="text-right tabular-nums">{N(i.on_hand)}{i.expired ? <div className="text-xs text-red-600">+{N(i.expired)} expired</div> : null}</TableCell>
                    <TableCell className="text-right tabular-nums">{i.per_day ? N(i.per_day) : "—"}</TableCell>
                    <TableCell className="text-right tabular-nums">{i.cover_days ?? "—"}<div className="text-xs text-muted-foreground">needs {i.lead_days + i.safety_days}</div></TableCell>
                    <TableCell className="text-right tabular-nums">{i.on_order ? N(i.on_order) : "—"}</TableCell>
                    <TableCell className="text-right tabular-nums font-medium">{i.suggested_qty ? N(i.suggested_qty) : "—"}{i.suggested_value ? <div className="text-xs text-muted-foreground">{M(i.suggested_value)}</div> : null}</TableCell>
                    <TableCell className="text-xs">{i.last_supplier ?? <span className="text-muted-foreground">no purchase recorded</span>}{i.last_cost ? <div className="text-muted-foreground">₦{N(i.last_cost)} · {fmtDay(i.last_bought)}</div> : null}</TableCell>
                    <TableCell className="text-right">
                      {i.open_orders ? <span className="text-xs text-muted-foreground">order open</span>
                        : <Button size="sm" variant="outline" onClick={() => setRaise(i)}>Request</Button>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {rows.length > 300 && <p className="p-3 text-xs text-muted-foreground">Showing the first 300 of {rows.length}; narrow the search.</p>}
          </div>
        )}
      </div>
      <RaiseDialog item={raise} onClose={() => setRaise(null)} onDone={onRaised} />
    </div>
  );
}

function RaiseDialog({ item, onClose, onDone }: { item: Dict | null; onClose: () => void; onDone: () => void }) {
  const [qty, setQty] = useState("");
  const [notes, setNotes] = useState("");
  const [forId, setForId] = useState<number | null>(null);
  if (item && forId !== item.formulary_id) { setForId(item.formulary_id); setQty(item.suggested_qty ? String(item.suggested_qty) : ""); setNotes(""); }
  const m = useMutation({
    mutationFn: () => api.stores.raise({ formulary_id: item!.formulary_id, quantity: Number(qty), notes: notes || undefined,
                                               urgency: item!.status === "out_of_stock" ? "urgent" : "routine", supplier_id: item!.last_supplier_id || undefined }),
    onSuccess: () => { toast.success("Stock order requested - it now waits for approval"); onDone(); onClose(); },
    onError: (e: any) => toast.error(e?.message || "Could not request the order"),
  });
  return (
    <Dialog open={!!item} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Request stock: {item?.drug}</DialogTitle>
          <DialogDescription>{item ? `${N(item.on_hand)} on the shelf, ${item.per_day ? `${N(item.per_day)} used a day` : "no recent use"}.` : ""}</DialogDescription></DialogHeader>
        <div className="space-y-1.5"><Label>Quantity</Label><Input type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)} /></div>
        <div className="space-y-1.5"><Label>Notes</Label><Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
        <DialogFooter><Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button disabled={!(Number(qty) > 0) || m.isPending} onClick={() => m.mutate()}>Request</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Orders({ roles, onChange }: { roles: string[]; onChange: () => void }) {
  const [status, setStatus] = useState("open");
  const [placing, setPlacing] = useState<Dict | null>(null);
  const [cancelling, setCancelling] = useState<Dict | null>(null);
  const q = useQuery({ queryKey: ["procurement", "orders", status], queryFn: () => api.stores.orders(status || undefined) });
  const can = (list: string[]) => roles.some((r) => list.includes(r));
  const approve = useMutation({
    mutationFn: (id: number) => api.stores.approve(id),
    onSuccess: () => { toast.success("Approved"); onChange(); }, onError: (e: any) => toast.error(e?.message || "Could not approve"),
  });
  return (
    <div className="space-y-3">
      <FilterBar selects={[{ label: "Status", value: status, onChange: setStatus, placeholder: "All orders",
        options: [{ value: "open", label: "Open" }, ...Object.entries(ORDER).map(([k, v]) => ({ value: k, label: v }))] }]} />
      <div className="rounded-xl border bg-card">
        <Table>
          <TableHeader><TableRow><TableHead>Order</TableHead><TableHead>Drug</TableHead><TableHead className="text-right">Qty</TableHead>
            <TableHead>Status</TableHead><TableHead>Supplier · expected</TableHead><TableHead>Raised</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>
            {(q.data?.orders ?? []).length === 0 && <TableRow><TableCell colSpan={7} className="py-6 text-center text-sm text-muted-foreground">No orders.</TableCell></TableRow>}
            {(q.data?.orders ?? []).map((r: Dict) => (
              <TableRow key={r.id}>
                <TableCell className="text-xs text-muted-foreground">#{r.id}{r.urgency && r.urgency !== "routine" ? <Badge variant="outline" className="ml-1 border-red-400 text-xs text-red-600">{r.urgency}</Badge> : null}</TableCell>
                <TableCell className="font-medium">{r.drug}</TableCell>
                <TableCell className="text-right tabular-nums">{N(r.requested_qty)}{r.received_qty ? <div className="text-xs text-muted-foreground">got {N(r.received_qty)}</div> : null}</TableCell>
                <TableCell><Badge variant="outline">{ORDER[r.status] ?? r.status}</Badge>{r.overdue && <div className="text-xs text-red-600">overdue</div>}</TableCell>
                <TableCell className="text-xs">{r.supplier ?? "—"}{r.expected_date ? <div className="text-muted-foreground">expected {fmtDay(r.expected_date)}</div> : null}
                  {r.status === "received" && <div className="text-muted-foreground">received {fmtDay(r.fulfilled_at)} ({(r.received_source ?? "").replace(/_/g, " ")})</div>}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{fmtDay(r.created_at)}<div>{r.created_by_name}</div></TableCell>
                <TableCell className="text-right">
                  <div className="flex flex-wrap justify-end gap-1">
                    {r.status === "recommended" && can(APPROVERS) && <Button size="sm" variant="outline" disabled={approve.isPending} onClick={() => approve.mutate(r.id)}>Approve</Button>}
                    {r.status === "approved" && can(PLACERS) && <Button size="sm" variant="outline" onClick={() => setPlacing(r)}>Place with supplier</Button>}
                    {r.status === "ordered" && <span className="px-1 text-xs text-muted-foreground" title="Closes by itself when the stock is received">closes on receipt</span>}
                    {["recommended", "approved", "ordered"].includes(r.status) && can(PLACERS) && <Button size="sm" variant="ghost" className="text-red-600" onClick={() => setCancelling(r)}>Cancel</Button>}
                    <ReportButton type="stock_order" kind="stock_order" id={r.id} label="Report" />
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <PlaceDialog order={placing} onClose={() => setPlacing(null)} onDone={onChange} />
      <CancelDialog order={cancelling} onClose={() => setCancelling(null)} onDone={onChange} />
    </div>
  );
}

function PlaceDialog({ order, onClose, onDone }: { order: Dict | null; onClose: () => void; onDone: () => void }) {
  const sup = useQuery({ queryKey: ["procurement", "suppliers"], queryFn: () => api.stores.suppliers(), enabled: !!order });
  const [supplier, setSupplier] = useState("");
  const [date, setDate] = useState("");
  const [forId, setForId] = useState<number | null>(null);
  if (order && forId !== order.id) {
    setForId(order.id); setSupplier(order.supplier_id ?? "");
    setDate(new Date(Date.now() + 14 * 864e5).toISOString().slice(0, 10));
  }
  const list: Dict[] = sup.data?.suppliers ?? [];
  const m = useMutation({
    mutationFn: () => api.stores.place(order!.id, { supplier_id: supplier, expected_date: date }),
    onSuccess: () => { toast.success("Placed - it will close when the stock is received"); onDone(); onClose(); },
    onError: (e: any) => toast.error(e?.message || "Could not place the order"),
  });
  return (
    <Dialog open={!!order} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Place with supplier: {order?.drug}</DialogTitle>
          <DialogDescription>{order ? `${N(order.requested_qty)} units` : ""}</DialogDescription></DialogHeader>
        <div className="space-y-1.5">
          <Label>Supplier</Label>
          <select className="h-9 w-full rounded-md border bg-background px-2 text-sm" value={supplier} onChange={(e) => setSupplier(e.target.value)}>
            <option value="">Choose a supplier</option>
            {list.map((s) => <option key={s.id} value={s.id}>{s.name}{s.spend_12m ? ` - ${M(s.spend_12m)} in 12 months` : ""}</option>)}
          </select>
        </div>
        <div className="space-y-1.5"><Label>Expected delivery</Label><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></div>
        <DialogFooter><Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button disabled={!supplier || !date || m.isPending} onClick={() => m.mutate()}>Place order</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CancelDialog({ order, onClose, onDone }: { order: Dict | null; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const m = useMutation({
    mutationFn: () => api.stores.cancel(order!.id, reason),
    onSuccess: () => { toast.success("Order cancelled"); setReason(""); onDone(); onClose(); },
    onError: (e: any) => toast.error(e?.message || "Could not cancel"),
  });
  return (
    <Dialog open={!!order} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Cancel order #{order?.id}</DialogTitle><DialogDescription>{order?.drug}</DialogDescription></DialogHeader>
        <div className="space-y-1.5"><Label>Reason</Label><Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></div>
        <DialogFooter><Button variant="ghost" onClick={onClose}>Keep it</Button>
          <Button variant="destructive" disabled={!reason.trim() || m.isPending} onClick={() => m.mutate()}>Cancel order</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Suppliers() {
  const [search, setSearch] = useState("");
  const [show, setShow] = useState("active");
  const q = useQuery({ queryKey: ["procurement", "suppliers"], queryFn: () => api.stores.suppliers() });
  const d: Dict = q.data ?? {};
  const rows: Dict[] = useMemo(() => (d.suppliers ?? []).filter((s: Dict) =>
    (!search || s.name.toLowerCase().includes(search.toLowerCase())) &&
    (show === "" || (show === "active" ? s.spend_12m > 0 : show === "owe" ? s.owed > 0 : s.open_orders > 0))), [d, search, show]);
  return (
    <div className="space-y-3">
      <KpiStrip items={[
        { label: "Bought from, 12 months", value: N(d.active_12m), icon: Building2, sub: `to ${fmtDay(d.purchases_to)}` },
        { label: "Bought, 12 months", value: M(d.spend_12m), icon: Package, sub: "Hope goods received, at cost" },
        { label: "We owe suppliers", value: d.owed ? M(d.owed) : "—", icon: Truck, sub: d.owed ? `${M(d.overdue)} past due` : "supplier bills start in Roy Books at go-live" },
        { label: "Suppliers on record", value: N((d.suppliers ?? []).length), icon: Building2 },
      ]} />
      <FilterBar search={{ value: search, onChange: setSearch, placeholder: "Search supplier" }}
        selects={[{ label: "Show", value: show, onChange: setShow, placeholder: "All suppliers",
          options: [{ value: "active", label: "Bought from in 12 months" }, { value: "owe", label: "We owe" }, { value: "orders", label: "Orders open" }] }]} />
      <div className="rounded-xl border bg-card">
        <Table>
          <TableHeader><TableRow><TableHead>Supplier</TableHead><TableHead className="text-right">Bought, 12 months</TableHead>
            <TableHead className="text-right">Deliveries</TableHead><TableHead className="text-right">Products</TableHead><TableHead>Last delivery</TableHead>
            <TableHead className="text-right">We owe</TableHead><TableHead className="text-right">Open orders</TableHead></TableRow></TableHeader>
          <TableBody>
            {rows.map((s) => (
              <TableRow key={s.id}>
                <TableCell><div className="font-medium">{s.name}</div><div className="text-xs text-muted-foreground">{[s.contact_name, s.phone, s.payment_terms].filter(Boolean).join(" · ") || "no contact recorded"}</div></TableCell>
                <TableCell className="text-right tabular-nums">{M(s.spend_12m)}</TableCell>
                <TableCell className="text-right tabular-nums">{N(s.deliveries_12m)}</TableCell>
                <TableCell className="text-right tabular-nums">{N(s.products_12m)}</TableCell>
                <TableCell className="text-xs">{fmtDay(s.last_delivery) || "—"}</TableCell>
                <TableCell className={`text-right tabular-nums ${s.overdue ? "text-red-600" : ""}`}>{s.owed ? M(s.owed) : "—"}</TableCell>
                <TableCell className="text-right tabular-nums">{s.open_orders || "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
