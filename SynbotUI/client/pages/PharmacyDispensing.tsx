import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Pill, RefreshCw, Loader2, ClipboardList, CheckCircle2, XCircle,
  AlertTriangle, ShieldAlert, Package, TrendingDown, Plus, ArrowDownUp,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────
interface Prescription {
  id: string;
  encounter_id?: string;
  patient_id?: string;
  drug_name?: string;
  dose?: string;
  dosage?: string;
  frequency?: string;
  duration?: string;
  status?: string;
  prescribed_by?: string;
  dispensed_at?: string;
  counselled?: boolean;
}

const RX_STATUS_COLORS: Record<string, string> = {
  pending:    "bg-blue-500/20 text-blue-400 border-blue-500/30",
  active:     "bg-blue-500/20 text-blue-400 border-blue-500/30",
  dispensed:  "bg-green-500/20 text-green-400 border-green-500/30",
  cancelled:  "bg-slate-500/20 text-slate-300 border-slate-500/30",
  partially_dispensed: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  partial:    "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
};

function RxBadge({ status }: { status?: string }) {
  const s = status ?? "active";
  const cls = RX_STATUS_COLORS[s] ?? RX_STATUS_COLORS.active;
  return <Badge variant="outline" className={cn("text-xs capitalize", cls)}>{s}</Badge>;
}

const EMPTY_DISPENSE = { quantity_dispensed: "", dispensed_by: "", counselling_notes: "", counselled: false };
const EMPTY_CANCEL   = { reason: "" };

// ─── Component ────────────────────────────────────────────────────────────────
export default function PharmacyDispensing() {
  const qc = useQueryClient();
  const { toast } = useToast();

  const [tab, setTab]                     = useState("prescriptions");
  const [statusFilter, setStatusFilter]   = useState("all");
  const [dispenseOpen, setDispenseOpen]   = useState(false);
  const [cancelOpen, setCancelOpen]       = useState(false);
  const [activeRx, setActiveRx]           = useState<Prescription | null>(null);
  const [dispenseForm, setDispenseForm]   = useState({ ...EMPTY_DISPENSE });
  const [cancelForm, setCancelForm]       = useState({ ...EMPTY_CANCEL });

  // Safety alert state
  const [allergyAlert, setAllergyAlert]   = useState<any[] | null>(null);
  const [ddiAlert, setDdiAlert]           = useState<any[] | null>(null);
  const [safetyOpen, setSafetyOpen]       = useState(false);
  const [overrideFlags, setOverrideFlags] = useState({ override_allergy: false, acknowledge_ddi: false });

  // Inventory state
  const [adjustOpen, setAdjustOpen]       = useState(false);
  const [activeItem, setActiveItem]       = useState<any | null>(null);
  const [adjustForm, setAdjustForm]       = useState({ adjustment: "", reason: "manual_adjustment" });
  const [addItemOpen, setAddItemOpen]     = useState(false);
  const [itemForm, setItemForm]           = useState<Record<string, any>>({ drug_name: "", formulation: "", strength: "", unit: "tablet", stock_quantity: "0", reorder_level: "0" });

  // ── Queries ────────────────────────────────────────────────────────────────
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["pharmacy-rx", statusFilter],
    queryFn: () => api.hospital.pharmacy.listRx(statusFilter !== "all" ? { status: statusFilter } : undefined),
    refetchInterval: 60_000,
  });
  const rxList: Prescription[] = Array.isArray(data?.prescriptions) ? data.prescriptions : Array.isArray(data) ? data : [];

  const { data: invData, isLoading: invLoading, refetch: refetchInv } = useQuery({
    queryKey: ["pharmacy-inventory"],
    queryFn: () => api.hospital.pharmacy.listInventory(),
    enabled: tab === "inventory",
    staleTime: 60_000,
  });
  const inventory: any[] = Array.isArray(invData?.inventory) ? invData.inventory : [];
  const lowStockCount = inventory.filter(i => Number(i.stock_quantity ?? 0) <= Number(i.reorder_level ?? 0)).length;

  // KPI counts
  const active    = rxList.filter(r => ["active", "pending"].includes(r.status ?? "")).length;
  const pending   = rxList.filter(r => ["active", "pending"].includes(r.status ?? "") && !r.dispensed_at).length;
  const dispensed = rxList.filter(r => r.status === "dispensed").length;
  const cancelled = rxList.filter(r => r.status === "cancelled").length;

  // ── Mutations ──────────────────────────────────────────────────────────────
  const doDispense = (extraFlags = {}) => {
    if (!activeRx) return Promise.reject();
    return api.hospital.pharmacy.dispense(activeRx.id, { ...dispenseForm, ...extraFlags });
  };

  const dispenseMut = useMutation({
    mutationFn: (flags?: Record<string, any>) => doDispense(flags),
    onSuccess: (res: any) => {
      // Safety gate: if backend returns ok=false show alert dialog
      if (res?.ok === false) {
        if (res.allergy_alert) { setAllergyAlert(res.allergies ?? []); setDdiAlert(null); setSafetyOpen(true); }
        else if (res.ddi_alert) { setDdiAlert(res.interactions ?? []); setAllergyAlert(null); setSafetyOpen(true); }
        return;
      }
      toast({ title: "Prescription dispensed" });
      setDispenseOpen(false);
      setSafetyOpen(false);
      setDispenseForm({ ...EMPTY_DISPENSE });
      setOverrideFlags({ override_allergy: false, acknowledge_ddi: false });
      void qc.invalidateQueries({ queryKey: ["pharmacy-rx"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const cancelMut = useMutation({
    mutationFn: () => activeRx ? api.hospital.pharmacy.cancel(activeRx.id, cancelForm) : Promise.reject(),
    onSuccess: () => {
      toast({ title: "Prescription cancelled" });
      setCancelOpen(false);
      setCancelForm({ ...EMPTY_CANCEL });
      void qc.invalidateQueries({ queryKey: ["pharmacy-rx"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const adjustMut = useMutation({
    mutationFn: () => activeItem ? api.hospital.pharmacy.adjustStock(activeItem.id, { adjustment: Number(adjustForm.adjustment), reason: adjustForm.reason }) : Promise.reject(),
    onSuccess: () => {
      toast({ title: "Stock adjusted" });
      setAdjustOpen(false);
      setAdjustForm({ adjustment: "", reason: "manual_adjustment" });
      void qc.invalidateQueries({ queryKey: ["pharmacy-inventory"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const addItemMut = useMutation({
    mutationFn: () => api.hospital.pharmacy.addInventoryItem({ ...itemForm, stock_quantity: Number(itemForm.stock_quantity), reorder_level: Number(itemForm.reorder_level) }),
    onSuccess: () => {
      toast({ title: "Drug added to inventory" });
      setAddItemOpen(false);
      setItemForm({ drug_name: "", formulation: "", strength: "", unit: "tablet", stock_quantity: "0", reorder_level: "0" });
      void qc.invalidateQueries({ queryKey: ["pharmacy-inventory"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  return (
    <motion.div className="space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Pharmacy</h1>
          <p className="text-sm text-muted-foreground">Prescriptions, dispensing, and drug inventory</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => { void refetch(); void refetchInv(); }} disabled={isFetching} className="gap-2">
          <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} /> Refresh
        </Button>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "Active Rx",         value: active,        icon: <Pill className="h-4 w-4" />,         color: "text-blue-400"   },
          { label: "Pending Dispense",  value: pending,       icon: <ClipboardList className="h-4 w-4" />,color: "text-yellow-400" },
          { label: "Dispensed",         value: dispensed,     icon: <CheckCircle2 className="h-4 w-4" />, color: "text-green-400"  },
          { label: "Low Stock Items",   value: lowStockCount, icon: <TrendingDown className="h-4 w-4" />, color: lowStockCount > 0 ? "text-red-400" : "text-slate-400" },
        ].map(k => (
          <Card key={k.label}>
            <CardContent className="pt-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">{k.label}</p>
                  <p className="text-2xl font-bold">{k.value}</p>
                </div>
                <span className={k.color}>{k.icon}</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="prescriptions">Prescriptions</TabsTrigger>
          <TabsTrigger value="inventory">Drug Inventory</TabsTrigger>
        </TabsList>

        {/* ── Prescriptions Tab ─────────────────────────────────────────── */}
        <TabsContent value="prescriptions" className="space-y-4">
          <div className="mt-4 flex flex-wrap gap-2">
            {["all", "active", "dispensed", "partial", "cancelled"].map(s => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={cn(
                  "rounded-full border px-3 py-1 text-xs capitalize transition-colors",
                  statusFilter === s ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-muted",
                )}
              >{s === "all" ? "All" : s}</button>
            ))}
          </div>

          <Card>
            <CardContent className="p-0">
              {isLoading ? (
                <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Rx #</TableHead>
                      <TableHead>Patient</TableHead>
                      <TableHead>Drug</TableHead>
                      <TableHead>Dose / Frequency</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Counselled</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rxList.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                          <Pill className="mx-auto mb-2 h-6 w-6 opacity-30" />No prescriptions found
                        </TableCell>
                      </TableRow>
                    ) : rxList.map(rx => (
                      <TableRow key={rx.id}>
                        <TableCell className="font-mono text-xs">{String(rx.id).slice(0, 8)}</TableCell>
                        <TableCell className="font-mono text-xs">{rx.patient_id ? String(rx.patient_id).slice(0, 8) : "—"}</TableCell>
                        <TableCell className="text-sm font-medium">{rx.drug_name}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{rx.dosage ?? rx.dose} · {rx.frequency}</TableCell>
                        <TableCell><RxBadge status={rx.status} /></TableCell>
                        <TableCell>
                          {rx.counselled
                            ? <CheckCircle2 className="h-4 w-4 text-green-400" />
                            : <span className="text-muted-foreground text-xs">—</span>}
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            {["active", "pending", "partially_dispensed"].includes(rx.status ?? "") && (
                              <>
                                <Button size="sm" variant="outline" className="h-7 px-2 text-xs"
                                  onClick={() => { setActiveRx(rx); setDispenseOpen(true); }}>
                                  Dispense
                                </Button>
                                <Button size="sm" variant="outline" className="h-7 px-2 text-xs border-red-500/30 text-red-400 hover:bg-red-500/10"
                                  onClick={() => { setActiveRx(rx); setCancelOpen(true); }}>
                                  Cancel
                                </Button>
                              </>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Inventory Tab ──────────────────────────────────────────────── */}
        <TabsContent value="inventory" className="space-y-4">
          <div className="mt-4 flex justify-end">
            <Button size="sm" className="gap-2" onClick={() => setAddItemOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> Add Drug
            </Button>
          </div>
          <Card>
            <CardContent className="p-0">
              {invLoading ? (
                <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Drug Name</TableHead>
                      <TableHead>Formulation</TableHead>
                      <TableHead>Strength</TableHead>
                      <TableHead>Stock</TableHead>
                      <TableHead>Reorder Level</TableHead>
                      <TableHead>Unit Cost</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {inventory.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                          <Package className="mx-auto mb-2 h-6 w-6 opacity-30" />No inventory items found
                        </TableCell>
                      </TableRow>
                    ) : inventory.map((item: any) => {
                      const isLow = Number(item.stock_quantity ?? 0) <= Number(item.reorder_level ?? 0);
                      return (
                        <TableRow key={item.id} className={isLow ? "bg-red-500/5" : ""}>
                          <TableCell className="text-sm font-medium">
                            {item.drug_name}
                            {isLow && <TrendingDown className="ml-1.5 inline h-3.5 w-3.5 text-red-400" />}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground capitalize">{item.formulation ?? "—"}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">{item.strength ?? "—"}</TableCell>
                          <TableCell className={cn("text-sm font-semibold", isLow ? "text-red-400" : "text-green-400")}>
                            {item.stock_quantity ?? 0} {item.unit}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">{item.reorder_level ?? 0}</TableCell>
                          <TableCell className="text-xs font-mono">₦{Number(item.unit_cost ?? 0).toLocaleString()}</TableCell>
                          <TableCell>
                            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs gap-1"
                              onClick={() => { setActiveItem(item); setAdjustOpen(true); }}>
                              <ArrowDownUp className="h-3.5 w-3.5" /> Adjust
                            </Button>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── Dispense Dialog ────────────────────────────────────────────────── */}
      <Dialog open={dispenseOpen} onOpenChange={v => { setDispenseOpen(v); if (!v) setOverrideFlags({ override_allergy: false, acknowledge_ddi: false }); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Dispense Prescription</DialogTitle>
            <DialogDescription>
              {activeRx?.drug_name} — Rx {String(activeRx?.id ?? "").slice(0, 8)}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Quantity Dispensed *</Label>
                <Input value={dispenseForm.quantity_dispensed}
                  onChange={e => setDispenseForm(f => ({ ...f, quantity_dispensed: e.target.value }))}
                  placeholder="e.g. 30 tablets" />
              </div>
              <div className="space-y-1">
                <Label>Dispensed By</Label>
                <Input value={dispenseForm.dispensed_by}
                  onChange={e => setDispenseForm(f => ({ ...f, dispensed_by: e.target.value }))}
                  placeholder="Staff name" />
              </div>
            </div>
            <div className="space-y-1">
              <Label>Counselling Notes</Label>
              <Textarea value={dispenseForm.counselling_notes}
                onChange={e => setDispenseForm(f => ({ ...f, counselling_notes: e.target.value }))}
                placeholder="Usage instructions, side effects, food interactions..." rows={3} />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="counselled-check"
                checked={dispenseForm.counselled}
                onCheckedChange={v => setDispenseForm(f => ({ ...f, counselled: !!v }))}
              />
              <Label htmlFor="counselled-check" className="cursor-pointer">Patient counselled</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDispenseOpen(false)}>Cancel</Button>
            <Button
              disabled={!dispenseForm.quantity_dispensed.trim() || dispenseMut.isPending}
              onClick={() => dispenseMut.mutate(overrideFlags)}
            >
              {dispenseMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}Confirm Dispense
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Safety Alert Dialog ─────────────────────────────────────────────── */}
      <Dialog open={safetyOpen} onOpenChange={setSafetyOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-400">
              <ShieldAlert className="h-5 w-5" />
              {allergyAlert ? "Allergy Alert" : "Drug Interaction Warning"}
            </DialogTitle>
            <DialogDescription>
              {allergyAlert
                ? "This patient has a documented allergy to this drug or a related substance."
                : "A potentially dangerous drug interaction was detected."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            {(allergyAlert ?? ddiAlert ?? []).map((item: any, i: number) => (
              <div key={i} className="rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-sm">
                {allergyAlert ? (
                  <>
                    <p className="font-semibold">{item.allergen}</p>
                    <p className="text-xs text-muted-foreground capitalize">Severity: {item.severity} — {item.reaction ?? "—"}</p>
                  </>
                ) : (
                  <>
                    <p className="font-semibold capitalize">{item.severity}: {item.drug}</p>
                    <p className="text-xs text-muted-foreground">{item.description ?? "—"}</p>
                  </>
                )}
              </div>
            ))}
            <p className="text-xs text-muted-foreground">
              By clicking Override, you acknowledge this safety alert and take clinical responsibility for this decision.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSafetyOpen(false)}>Cancel Dispense</Button>
            <Button
              variant="destructive"
              disabled={dispenseMut.isPending}
              onClick={() => {
                const flags = allergyAlert
                  ? { override_allergy: true, acknowledge_ddi: false }
                  : { override_allergy: false, acknowledge_ddi: true };
                setOverrideFlags(flags);
                dispenseMut.mutate(flags);
              }}
            >
              {dispenseMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <AlertTriangle className="mr-2 h-4 w-4" />}
              Override & Dispense
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Cancel Dialog ──────────────────────────────────────────────────── */}
      <Dialog open={cancelOpen} onOpenChange={setCancelOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Cancel Prescription</DialogTitle>
            <DialogDescription>Rx {String(activeRx?.id ?? "").slice(0, 8)} — {activeRx?.drug_name}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1">
              <Label>Cancellation Reason *</Label>
              <Textarea value={cancelForm.reason}
                onChange={e => setCancelForm({ reason: e.target.value })}
                placeholder="State reason for cancellation..." rows={3} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelOpen(false)}>Back</Button>
            <Button variant="destructive"
              disabled={!cancelForm.reason.trim() || cancelMut.isPending}
              onClick={() => cancelMut.mutate()}
            >
              {cancelMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}Cancel Prescription
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Stock Adjust Dialog ─────────────────────────────────────────────── */}
      <Dialog open={adjustOpen} onOpenChange={setAdjustOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Adjust Stock</DialogTitle>
            <DialogDescription>{activeItem?.drug_name} — Current: {activeItem?.stock_quantity} {activeItem?.unit}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1">
              <Label>Adjustment Quantity *</Label>
              <Input type="number" value={adjustForm.adjustment}
                onChange={e => setAdjustForm(f => ({ ...f, adjustment: e.target.value }))}
                placeholder="+30 receipt or -5 issue" />
              <p className="text-[10px] text-muted-foreground">Positive = stock in, Negative = stock out / loss</p>
            </div>
            <div className="space-y-1">
              <Label>Reason</Label>
              <Select value={adjustForm.reason} onValueChange={v => setAdjustForm(f => ({ ...f, reason: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="manual_adjustment">Manual Adjustment</SelectItem>
                  <SelectItem value="stock_receipt">Stock Receipt</SelectItem>
                  <SelectItem value="stock_count">Cycle Count</SelectItem>
                  <SelectItem value="wastage">Wastage / Expiry</SelectItem>
                  <SelectItem value="dispensing">Dispensing Correction</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAdjustOpen(false)}>Cancel</Button>
            <Button disabled={!adjustForm.adjustment || adjustMut.isPending} onClick={() => adjustMut.mutate()}>
              {adjustMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Apply
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Add Drug Dialog ─────────────────────────────────────────────────── */}
      <Dialog open={addItemOpen} onOpenChange={setAddItemOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add Drug to Inventory</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 py-2">
            <div className="col-span-2 space-y-1">
              <Label>Drug Name *</Label>
              <Input value={itemForm.drug_name} onChange={e => setItemForm(f => ({ ...f, drug_name: e.target.value }))} placeholder="e.g. Amoxicillin" />
            </div>
            <div className="space-y-1">
              <Label>Formulation</Label>
              <Input value={itemForm.formulation} onChange={e => setItemForm(f => ({ ...f, formulation: e.target.value }))} placeholder="tablet | syrup | injection" />
            </div>
            <div className="space-y-1">
              <Label>Strength</Label>
              <Input value={itemForm.strength} onChange={e => setItemForm(f => ({ ...f, strength: e.target.value }))} placeholder="500mg" />
            </div>
            <div className="space-y-1">
              <Label>Unit</Label>
              <Input value={itemForm.unit} onChange={e => setItemForm(f => ({ ...f, unit: e.target.value }))} placeholder="tablet" />
            </div>
            <div className="space-y-1">
              <Label>Initial Stock</Label>
              <Input type="number" value={itemForm.stock_quantity} onChange={e => setItemForm(f => ({ ...f, stock_quantity: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>Reorder Level</Label>
              <Input type="number" value={itemForm.reorder_level} onChange={e => setItemForm(f => ({ ...f, reorder_level: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>Unit Cost (₦)</Label>
              <Input type="number" value={itemForm.unit_cost ?? ""} onChange={e => setItemForm(f => ({ ...f, unit_cost: e.target.value }))} placeholder="0" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddItemOpen(false)}>Cancel</Button>
            <Button disabled={!itemForm.drug_name?.trim() || addItemMut.isPending} onClick={() => addItemMut.mutate()}>
              {addItemMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Add Drug
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
