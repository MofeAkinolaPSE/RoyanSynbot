import { useRef, useState } from "react";
import { UnitCostsPanel } from "@/components/books/UnitCostsPanel";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Boxes, RefreshCw, Loader2, Package, Plus, Truck, AlertOctagon, AlertTriangle,
  Eye, TrendingUp, Search,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useAuth } from "@/components/AuthProvider";
import { useToast } from "@/hooks/use-toast";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { DrugInventoryCard, type DrugCard } from "@/components/pharmacy/DrugInventoryCard";
import { InventoryDrugPanel } from "@/components/pharmacy/InventoryDrugPanel";
import { elapsed } from "@/components/pharmacy/pharmacy-shared";
import { ExpiredStockTab } from "@/components/pharmacy/ExpiredStockTab";
import { InventoryReportTab } from "@/components/pharmacy/InventoryReportTab";

const INVENTORY_WRITE_ROLES = ["pharmacist", "admin"];

const CATEGORY_TABS = [
  { value: "", label: "All" },
  { value: "drug", label: "Drugs" },
  { value: "vaccine", label: "Vaccines" },
  { value: "consumable", label: "Consumables" },
  { value: "other", label: "Other" },
];

const TIER_PILLS = [
  { value: "", label: "All Tiers" },
  { value: "CRITICAL", label: "Critical" },
  { value: "WARNING", label: "Warning" },
  { value: "MONITOR", label: "Monitor" },
  { value: "ADEQUATE", label: "Adequate" },
];

const REPLENISH_STATUS_COLORS: Record<string, string> = {
  recommended: "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
  approved:    "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  ordered:     "bg-purple-500/20 text-purple-700 dark:text-purple-400 border-purple-500/30",
  received:    "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
  cancelled:   "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30",
};

const EMPTY_DRUG_FORM = {
  generic_name: "", brand_name: "", category: "drug", form: "tablet", strength: "", unit: "tablet",
  lead_time_days: "", safety_stock_days: "", reorder_level: "",
  batch_number: "", quantity_received: "", unit_cost: "", supplier: "", location: "", expiry_date: "",
};

const EMPTY_REORDER_FORM = { formulary_id: "", drug_name: "", requested_qty: "", ward: "", urgency: "routine", unit: "" };

export default function Inventory() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const { roles } = useAuth();
  const canWrite = roles.some(r => INVENTORY_WRITE_ROLES.includes(r) || r === "admin");

  const [tab, setTab] = useState("stock");
  const [category, setCategory] = useState("");
  const [riskTier, setRiskTier] = useState("");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [openDrugId, setOpenDrugId] = useState<number | null>(null);
  const [addDrugOpen, setAddDrugOpen] = useState(false);
  const [drugForm, setDrugForm] = useState({ ...EMPTY_DRUG_FORM });
  const [matchedDrug, setMatchedDrug] = useState<any | null>(null);
  const [nameResults, setNameResults] = useState<any[]>([]);
  const [nameDropdownOpen, setNameDropdownOpen] = useState(false);
  const nameDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [reorderOpen, setReorderOpen] = useState(false);
  const [reorderForm, setReorderForm] = useState({ ...EMPTY_REORDER_FORM });

  const handleSearchChange = (val: string) => {
    setSearch(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedSearch(val), 400);
  };

  // Typeahead against the existing catalog: picking a suggestion switches
  // the dialog from "create a new drug" to "receive stock against this
  // drug" (see receiveExistingDrugMut) so restocking never creates a
  // duplicate catalog row for a drug that's already there.
  const handleGenericNameChange = (val: string) => {
    setDrugForm(f => ({ ...f, generic_name: val }));
    if (matchedDrug && val !== matchedDrug.generic_name) setMatchedDrug(null);
    if (nameDebounceRef.current) clearTimeout(nameDebounceRef.current);
    if (val.trim().length < 2) {
      setNameResults([]);
      setNameDropdownOpen(false);
      return;
    }
    nameDebounceRef.current = setTimeout(async () => {
      try {
        const res = await api.hospital.pharmacy.inventory.drugs({ search: val, limit: 8 });
        const drugs = res?.drugs ?? [];
        setNameResults(drugs);
        setNameDropdownOpen(drugs.length > 0);
      } catch {
        setNameResults([]);
        setNameDropdownOpen(false);
      }
    }, 300);
  };

  const selectMatchedDrug = (drug: any) => {
    setMatchedDrug(drug);
    setDrugForm(f => ({
      ...f,
      generic_name: drug.generic_name ?? f.generic_name,
      brand_name: drug.brand_name ?? "",
      category: drug.category ?? f.category,
      form: drug.form ?? "",
      strength: drug.strength ?? "",
    }));
    setNameDropdownOpen(false);
  };

  // ── Queries ────────────────────────────────────────────────────────────────
  const { data: summaryData, isFetching: summaryFetching, refetch: refetchSummary } = useQuery({
    queryKey: ["inventory-summary"],
    queryFn: () => api.hospital.pharmacy.inventory.summary(),
    refetchInterval: 60_000,
  });
  const summary = summaryData ?? {};
  const tierCounts = summary.tier_counts ?? { CRITICAL: 0, WARNING: 0, MONITOR: 0, ADEQUATE: 0 };

  const { data: cardsData, isLoading: cardsLoading, refetch: refetchCards } = useQuery({
    queryKey: ["inventory-cards", category, riskTier, debouncedSearch],
    queryFn: () => api.hospital.pharmacy.inventory.cards({
      category: category || undefined, risk_tier: riskTier || undefined, search: debouncedSearch || undefined,
    }),
    enabled: tab === "stock",
  });
  const cards: DrugCard[] = cardsData?.cards ?? [];

  const { data: mostPrescribedData } = useQuery({
    queryKey: ["inventory-trends-most-prescribed"],
    queryFn: () => api.hospital.pharmacy.inventory.trendsMostPrescribed({ window_days: 30, limit: 10 }),
    enabled: tab === "trending",
  });
  const mostPrescribed: any[] = mostPrescribedData?.drugs ?? [];

  const { data: recentlyDispensedData } = useQuery({
    queryKey: ["inventory-trends-recent"],
    queryFn: () => api.hospital.pharmacy.inventory.trendsRecentlyDispensed(20),
    enabled: tab === "trending",
  });
  const recentlyDispensed: any[] = recentlyDispensedData?.events ?? [];

  const { data: replenData } = useQuery({
    queryKey: ["inventory-replenishment"],
    queryFn: () => api.hospital.pharmacy.listReplenishmentRequests(),
    enabled: tab === "replenishment",
  });
  const replenishmentRequests: any[] = replenData?.requests ?? [];

  // ── Mutations ──────────────────────────────────────────────────────────────
  const invalidateInventory = () => {
    void qc.invalidateQueries({ queryKey: ["inventory-summary"] });
    void qc.invalidateQueries({ queryKey: ["inventory-cards"] });
  };

  const addDrugMut = useMutation({
    mutationFn: () => api.hospital.pharmacy.inventory.addDrug({
      generic_name: drugForm.generic_name,
      brand_name: drugForm.brand_name || undefined,
      category: drugForm.category,
      form: drugForm.form || undefined,
      strength: drugForm.strength || undefined,
      unit: drugForm.unit || undefined,
      lead_time_days: drugForm.lead_time_days ? Number(drugForm.lead_time_days) : undefined,
      safety_stock_days: drugForm.safety_stock_days ? Number(drugForm.safety_stock_days) : undefined,
      reorder_level: drugForm.reorder_level ? Number(drugForm.reorder_level) : undefined,
      batch_number: drugForm.batch_number || undefined,
      quantity_received: drugForm.quantity_received ? Number(drugForm.quantity_received) : undefined,
      unit_cost: drugForm.unit_cost ? Number(drugForm.unit_cost) : undefined,
      supplier: drugForm.supplier || undefined,
      location: drugForm.location || undefined,
      expiry_date: drugForm.expiry_date || undefined,
    }),
    onSuccess: () => {
      toast({ title: "Drug added" });
      setAddDrugOpen(false);
      setDrugForm({ ...EMPTY_DRUG_FORM });
      setMatchedDrug(null);
      invalidateInventory();
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const receiveExistingDrugMut = useMutation({
    mutationFn: () => api.hospital.pharmacy.inventory.receiveBatch(matchedDrug.id, {
      batch_number: drugForm.batch_number,
      quantity_received: Number(drugForm.quantity_received),
      unit_cost: drugForm.unit_cost ? Number(drugForm.unit_cost) : undefined,
      supplier: drugForm.supplier || undefined,
      location: drugForm.location || undefined,
      expiry_date: drugForm.expiry_date || undefined,
    }),
    onSuccess: () => {
      toast({ title: "Stock added", description: `${matchedDrug.generic_name} restocked — on-hand quantity updated.` });
      setAddDrugOpen(false);
      setDrugForm({ ...EMPTY_DRUG_FORM });
      setMatchedDrug(null);
      void qc.invalidateQueries({ queryKey: ["inventory-drug", matchedDrug.id] });
      invalidateInventory();
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const reorderMut = useMutation({
    mutationFn: () => api.hospital.pharmacy.createReplenishmentRequest({
      formulary_id: reorderForm.formulary_id || undefined,
      drug_name: reorderForm.drug_name || undefined,
      requested_qty: reorderForm.requested_qty ? Number(reorderForm.requested_qty) : undefined,
      ward: reorderForm.ward || undefined,
      urgency: reorderForm.urgency,
      unit: reorderForm.unit || undefined,
    }),
    onSuccess: () => {
      toast({ title: "Replenishment requested" });
      setReorderOpen(false);
      setReorderForm({ ...EMPTY_REORDER_FORM });
      void qc.invalidateQueries({ queryKey: ["inventory-replenishment"] });
      invalidateInventory();
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const updateReplenishStatusMut = useMutation({
    mutationFn: ({ id, status }: { id: number | string; status: string }) => api.hospital.pharmacy.updateReplenishmentStatus(id, status),
    onSuccess: () => {
      toast({ title: "Request updated" });
      void qc.invalidateQueries({ queryKey: ["inventory-replenishment"] });
      invalidateInventory();
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  function openReorder(card: DrugCard) {
    setReorderForm({
      formulary_id: String(card.formulary_id), drug_name: card.drug_name,
      requested_qty: card.recommended_reorder_qty ? String(card.recommended_reorder_qty) : "",
      ward: "", urgency: "routine", unit: "",
    });
    setReorderOpen(true);
  }
  function openReorderFromPanel(formularyId: number, drugName: string, suggestedQty?: number | null) {
    setReorderForm({
      formulary_id: String(formularyId), drug_name: drugName,
      requested_qty: suggestedQty ? String(suggestedQty) : "", ward: "", urgency: "routine", unit: "",
    });
    setReorderOpen(true);
  }

  return (
    <motion.div className="space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Pharmacy Inventory</h1>
          <p className="text-sm text-muted-foreground">Live stock, batch &amp; expiry tracking, reorder risk, and demand trends</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => { void refetchSummary(); void refetchCards(); }} disabled={summaryFetching} className="gap-2">
          <RefreshCw className={cn("h-3.5 w-3.5", summaryFetching && "animate-spin")} /> Refresh
        </Button>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {[
          { label: "Total SKUs",     value: summary.total_skus ?? 0,                icon: <Boxes className="h-4 w-4" />,        color: "text-blue-400" },
          { label: "Stock Value",    value: `₦${Number(summary.stock_value ?? 0).toLocaleString()}`, icon: <Package className="h-4 w-4" />, color: "text-slate-400" },
          { label: "Critical",       value: tierCounts.CRITICAL ?? 0,               icon: <AlertOctagon className="h-4 w-4" />, color: (tierCounts.CRITICAL ?? 0) > 0 ? "text-red-500" : "text-slate-400" },
          { label: "Warning",        value: tierCounts.WARNING ?? 0,                icon: <AlertTriangle className="h-4 w-4" />, color: (tierCounts.WARNING ?? 0) > 0 ? "text-amber-500" : "text-slate-400" },
          { label: "Expiring Soon",  value: summary.expiring_soon_count ?? 0,       icon: <Eye className="h-4 w-4" />,          color: (summary.expiring_soon_count ?? 0) > 0 ? "text-amber-500" : "text-slate-400" },
          { label: "Pending Reorders", value: summary.pending_replenishment_count ?? 0, icon: <Truck className="h-4 w-4" />,   color: "text-blue-400" },
        ].map(k => (
          <Card key={k.label}>
            <CardContent className="pt-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">{k.label}</p>
                  <p className="text-xl font-bold tabular-nums">{k.value}</p>
                </div>
                <span className={k.color}>{k.icon}</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="stock">Stock</TabsTrigger>
          <TabsTrigger value="trending">Trending</TabsTrigger>
          <TabsTrigger value="replenishment">Replenishment</TabsTrigger>
          <TabsTrigger value="expired">Expired Stock</TabsTrigger>
          <TabsTrigger value="costs">Unit costs</TabsTrigger>
          <TabsTrigger value="report">Report</TabsTrigger>
        </TabsList>

        {/* ── Stock Tab ─────────────────────────────────────────────────── */}
        <TabsContent value="stock" className="space-y-4">
          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap gap-2">
              {CATEGORY_TABS.map(c => (
                <button key={c.value} onClick={() => setCategory(c.value)}
                  className={cn("rounded-full border px-3 py-1 text-xs transition-colors",
                    category === c.value ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-muted")}>
                  {c.label}
                </button>
              ))}
            </div>
            {canWrite && (
              <Button size="sm" className="gap-2" onClick={() => setAddDrugOpen(true)}>
                <Plus className="h-3.5 w-3.5" /> Add Drug
              </Button>
            )}
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap gap-2">
              {TIER_PILLS.map(t => (
                <button key={t.value} onClick={() => setRiskTier(t.value)}
                  className={cn("rounded-full border px-3 py-1 text-xs transition-colors",
                    riskTier === t.value ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-muted")}>
                  {t.label}
                </button>
              ))}
            </div>
            <div className="relative w-full sm:w-64">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
              <Input placeholder="Search drugs…" value={search} onChange={e => handleSearchChange(e.target.value)} className="pl-8 h-8 text-sm" />
            </div>
          </div>

          {cardsLoading ? (
            <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : cards.length === 0 ? (
            <Card><CardContent className="py-12 text-center text-muted-foreground">
              <Package className="mx-auto mb-2 h-6 w-6 opacity-30" />
              No live stock found{debouncedSearch ? ` matching "${debouncedSearch}"` : ""}.
              {canWrite && <p className="mt-1 text-xs">Add a drug and receive its first batch to get started.</p>}
            </CardContent></Card>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {cards.map(card => (
                <DrugInventoryCard key={card.formulary_id} card={card} onOpen={c => setOpenDrugId(c.formulary_id)} onReorder={openReorder} />
              ))}
            </div>
          )}
        </TabsContent>

        {/* ── Trending Tab ──────────────────────────────────────────────── */}
        <TabsContent value="trending" className="space-y-4">
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <TrendingUp className="h-4 w-4" /> Most Prescribed — Last 30 Days
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {mostPrescribed.length === 0 ? (
                  <p className="px-4 py-6 text-sm text-center text-muted-foreground">No prescribing activity in this window yet.</p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow><TableHead>Drug</TableHead><TableHead>Rx Count</TableHead><TableHead>Total Qty</TableHead></TableRow>
                    </TableHeader>
                    <TableBody>
                      {mostPrescribed.map((d, i) => (
                        <TableRow key={`${d.drug_name}-${i}`}>
                          <TableCell className="text-sm font-medium">{d.drug_name}</TableCell>
                          <TableCell className="text-sm tabular-nums">{d.rx_count}</TableCell>
                          <TableCell className="text-sm tabular-nums text-muted-foreground">{d.total_qty}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <Boxes className="h-4 w-4" /> Recently Dispensed
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {recentlyDispensed.length === 0 ? (
                  <p className="px-4 py-6 text-sm text-center text-muted-foreground">No dispensing events recorded yet.</p>
                ) : (
                  <div className="max-h-[360px] overflow-y-auto divide-y divide-border/50">
                    {recentlyDispensed.map((e: any) => (
                      <div key={e.id} className="px-4 py-2.5 text-xs flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <p className="font-medium truncate">{e.drug_name}</p>
                          <p className="text-muted-foreground">{e.quantity_dispensed} {e.unit}{e.batch_number ? ` · Batch ${e.batch_number}` : ""}</p>
                        </div>
                        <span className="text-muted-foreground shrink-0">{elapsed(e.dispensed_at)} ago</span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* ── Replenishment Tab ─────────────────────────────────────────── */}
        <TabsContent value="replenishment" className="space-y-4">
          <Card className="mt-4">
            <CardContent className="p-0">
              {replenishmentRequests.length === 0 ? (
                <p className="px-4 py-6 text-sm text-center text-muted-foreground">No replenishment requests</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Drug</TableHead><TableHead>Qty</TableHead><TableHead>Ward</TableHead>
                      <TableHead>Urgency</TableHead><TableHead>Status</TableHead><TableHead>Requested</TableHead><TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {replenishmentRequests.map((r: any) => (
                      <TableRow key={r.id}>
                        <TableCell className="text-sm font-medium">{r.sku}</TableCell>
                        <TableCell className="text-sm tabular-nums">{r.requested_qty}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{r.ward ?? "—"}</TableCell>
                        <TableCell className="text-xs text-muted-foreground capitalize">{r.urgency ?? "—"}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cn("text-xs capitalize", REPLENISH_STATUS_COLORS[r.status] ?? "")}>{r.status}</Badge>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">{elapsed(r.created_at)}</TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            {r.status === "recommended" && (
                              <Button size="sm" variant="ghost" className="h-6 px-2 text-xs"
                                onClick={() => updateReplenishStatusMut.mutate({ id: r.id, status: "approved" })}>Approve</Button>
                            )}
                            {r.status === "approved" && (
                              <Button size="sm" variant="ghost" className="h-6 px-2 text-xs"
                                onClick={() => updateReplenishStatusMut.mutate({ id: r.id, status: "ordered" })}>Mark Ordered</Button>
                            )}
                            {r.status === "ordered" && (
                              <span className="px-2 text-xs text-muted-foreground" title="Closes by itself when the stock is received here or delivered through Roy Books">
                                closes on receipt
                              </span>
                            )}
                            {!["received", "cancelled"].includes(r.status) && (
                              <Button size="sm" variant="ghost" className="h-6 px-2 text-xs text-red-500"
                                onClick={() => updateReplenishStatusMut.mutate({ id: r.id, status: "cancelled" })}>Cancel</Button>
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

        <TabsContent value="expired" className="mt-4">
          <ExpiredStockTab />
        </TabsContent>

        {/* the same unit costs Finance sees in Roy Books > Stock: pharmacy and finance work from one list */}
        <TabsContent value="costs" className="mt-4"><UnitCostsPanel /></TabsContent>

        <TabsContent value="report" className="mt-4">
          <InventoryReportTab />
        </TabsContent>
      </Tabs>

      {openDrugId != null && (
        <InventoryDrugPanel formularyId={openDrugId} onClose={() => setOpenDrugId(null)} onReorder={openReorderFromPanel} />
      )}

      {/* ── Add Drug Dialog ────────────────────────────────────────────────── */}
      <Dialog open={addDrugOpen} onOpenChange={(open) => {
        setAddDrugOpen(open);
        if (!open) { setMatchedDrug(null); setNameResults([]); setNameDropdownOpen(false); }
      }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle>{matchedDrug ? "Restock Existing Drug" : "Add Drug to Catalog"}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3 py-2 max-h-[60vh] overflow-y-auto pr-1">
            <div className="col-span-2 space-y-1 relative">
              <Label className="text-xs">Generic Name *</Label>
              <Input
                value={drugForm.generic_name}
                onChange={e => handleGenericNameChange(e.target.value)}
                onFocus={() => { if (nameResults.length > 0 && !matchedDrug) setNameDropdownOpen(true); }}
                onBlur={() => setTimeout(() => setNameDropdownOpen(false), 150)}
                placeholder="Start typing to search existing drugs…"
                autoComplete="off"
              />
              {nameDropdownOpen && (
                <div className="absolute z-50 mt-1 w-full max-h-56 overflow-y-auto rounded-md border bg-popover shadow-md">
                  {nameResults.map((d: any) => (
                    <button
                      key={d.id}
                      type="button"
                      onMouseDown={() => selectMatchedDrug(d)}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground"
                    >
                      <div className="font-medium">{d.generic_name}</div>
                      <div className="text-xs text-muted-foreground">
                        {[d.brand_name, d.strength, d.code].filter(Boolean).join(" · ")}
                      </div>
                    </button>
                  ))}
                </div>
              )}
              {matchedDrug && (
                <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">
                  Matched existing drug — this will add stock to it, not create a duplicate.{" "}
                  <button type="button" className="underline" onClick={() => setMatchedDrug(null)}>
                    Add as new drug instead
                  </button>
                </p>
              )}
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Brand Name</Label>
              <Input disabled={!!matchedDrug} value={drugForm.brand_name} onChange={e => setDrugForm(f => ({ ...f, brand_name: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Category</Label>
              <Select disabled={!!matchedDrug} value={drugForm.category} onValueChange={v => setDrugForm(f => ({ ...f, category: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="drug">Drug</SelectItem>
                  <SelectItem value="vaccine">Vaccine</SelectItem>
                  <SelectItem value="consumable">Consumable</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Form</Label>
              <Input disabled={!!matchedDrug} value={drugForm.form} onChange={e => setDrugForm(f => ({ ...f, form: e.target.value }))} placeholder="tablet, syrup, injection…" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Strength</Label>
              <Input disabled={!!matchedDrug} value={drugForm.strength} onChange={e => setDrugForm(f => ({ ...f, strength: e.target.value }))} placeholder="e.g. 500mg" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Lead Time (days)</Label>
              <Input disabled={!!matchedDrug} type="number" value={drugForm.lead_time_days} onChange={e => setDrugForm(f => ({ ...f, lead_time_days: e.target.value }))} placeholder="Default 14" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Safety Stock (days)</Label>
              <Input disabled={!!matchedDrug} type="number" value={drugForm.safety_stock_days} onChange={e => setDrugForm(f => ({ ...f, safety_stock_days: e.target.value }))} placeholder="Default 7" />
            </div>
            <div className="col-span-2 border-t pt-2 mt-1">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {matchedDrug ? "New Batch (required)" : "First Batch (optional)"}
              </p>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Batch Number</Label>
              <Input value={drugForm.batch_number} onChange={e => setDrugForm(f => ({ ...f, batch_number: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Quantity Received</Label>
              <Input type="number" value={drugForm.quantity_received} onChange={e => setDrugForm(f => ({ ...f, quantity_received: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Unit Cost</Label>
              <Input type="number" value={drugForm.unit_cost} onChange={e => setDrugForm(f => ({ ...f, unit_cost: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Expiry Date</Label>
              <Input type="date" value={drugForm.expiry_date} onChange={e => setDrugForm(f => ({ ...f, expiry_date: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddDrugOpen(false)}>Cancel</Button>
            {matchedDrug ? (
              <Button
                disabled={!drugForm.batch_number.trim() || !Number(drugForm.quantity_received) || receiveExistingDrugMut.isPending}
                onClick={() => receiveExistingDrugMut.mutate()}
              >
                {receiveExistingDrugMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Add Stock
              </Button>
            ) : (
              <Button disabled={!drugForm.generic_name.trim() || addDrugMut.isPending} onClick={() => addDrugMut.mutate()}>
                {addDrugMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Add Drug
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Reorder / Replenishment Dialog ─────────────────────────────────── */}
      <Dialog open={reorderOpen} onOpenChange={setReorderOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader><DialogTitle>Request Replenishment — {reorderForm.drug_name}</DialogTitle></DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1">
              <Label className="text-xs">Quantity</Label>
              <Input type="number" value={reorderForm.requested_qty} onChange={e => setReorderForm(f => ({ ...f, requested_qty: e.target.value }))}
                placeholder="Leave blank to auto-compute" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Ward (optional)</Label>
                <Input value={reorderForm.ward} onChange={e => setReorderForm(f => ({ ...f, ward: e.target.value }))} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Urgency</Label>
                <Select value={reorderForm.urgency} onValueChange={v => setReorderForm(f => ({ ...f, urgency: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="routine">Routine</SelectItem>
                    <SelectItem value="urgent">Urgent</SelectItem>
                    <SelectItem value="stat">STAT</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReorderOpen(false)}>Cancel</Button>
            <Button disabled={reorderMut.isPending} onClick={() => reorderMut.mutate()}>
              {reorderMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Submit Request
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
