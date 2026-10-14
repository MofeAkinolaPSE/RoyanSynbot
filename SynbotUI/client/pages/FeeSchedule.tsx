import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { DollarSign, RefreshCw, Loader2, Plus, Pencil, Trash2, ToggleLeft, ToggleRight } from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { ConsultationFees } from "@/components/billing/ConsultationFees";

const FEE_CATEGORIES = ["consultation", "procedure", "lab", "radiology", "pharmacy", "nursing", "theatre", "ward", "other"];

const CATEGORY_COLORS: Record<string, string> = {
  consultation: "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  lab:          "bg-purple-500/20 text-purple-700 dark:text-purple-400 border-purple-500/30",
  pharmacy:     "bg-orange-500/20 text-orange-700 dark:text-orange-400 border-orange-500/30",
  radiology:    "bg-cyan-500/20 text-cyan-700 dark:text-cyan-400 border-cyan-500/30",
  theatre:      "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30",
  ward:         "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
  nursing:      "bg-pink-500/20 text-pink-700 dark:text-pink-400 border-pink-500/30",
  procedure:    "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
};

const EMPTY_FORM = { service_name: "", category: "consultation", base_price: "", unit: "per visit", notes: "" };

export default function FeeSchedule() {
  const qc = useQueryClient();
  const { toast } = useToast();

  const [categoryFilter, setCategoryFilter] = useState("all");
  const [showInactive, setShowInactive] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editFee, setEditFee] = useState<any | null>(null);
  const [form, setForm] = useState({ ...EMPTY_FORM });

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["fee-schedule", categoryFilter, showInactive],
    queryFn: () => api.admin.feeSchedule.list(
      categoryFilter !== "all" ? categoryFilter : undefined,
      !showInactive,
    ),
    staleTime: 120_000,
  });

  const fees: any[] = Array.isArray(data?.fees) ? data.fees : [];
  const summary: Record<string, any> = data?.summary ?? {};

  // KPIs
  const totalActive = fees.filter(f => f.active).length;
  const totalServices = fees.length;
  const avgPrice = fees.length ? fees.reduce((s, f) => s + Number(f.base_price || 0), 0) / fees.length : 0;
  const categories = Object.keys(summary).length;

  const saveMut = useMutation({
    mutationFn: () => {
      const payload = { ...form, base_price: Number(form.base_price) };
      return editFee
        ? api.admin.feeSchedule.update(editFee.id, payload)
        : api.admin.feeSchedule.create(payload);
    },
    onSuccess: () => {
      toast({ title: editFee ? "Fee updated" : "Fee created" });
      setFormOpen(false);
      setEditFee(null);
      setForm({ ...EMPTY_FORM });
      void qc.invalidateQueries({ queryKey: ["fee-schedule"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => api.admin.feeSchedule.delete(id),
    onSuccess: () => { toast({ title: "Fee deactivated" }); void qc.invalidateQueries({ queryKey: ["fee-schedule"] }); },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  function openEdit(fee: any) {
    setEditFee(fee);
    setForm({
      service_name: fee.service_name ?? "",
      category: fee.category ?? "consultation",
      base_price: String(fee.base_price ?? ""),
      unit: fee.unit ?? "per visit",
      notes: fee.notes ?? "",
    });
    setFormOpen(true);
  }

  return (
    <motion.div className="space-y-6" {...motionTransitions.fadeInUp}>
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Fee Schedule</h1>
          <p className="text-sm text-muted-foreground">Manage hospital service pricing</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => void refetch()} disabled={isFetching} className="gap-2">
            <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} /> Refresh
          </Button>
          <Button size="sm" className="gap-2" onClick={() => { setEditFee(null); setForm({ ...EMPTY_FORM }); setFormOpen(true); }}>
            <Plus className="h-3.5 w-3.5" /> Add Service
          </Button>
        </div>
      </div>

      <ConsultationFees />

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "Active Services", value: totalActive, color: "text-blue-700 dark:text-blue-400" },
          { label: "Total Entries", value: totalServices, color: "text-slate-700 dark:text-slate-400" },
          { label: "Categories", value: categories, color: "text-purple-700 dark:text-purple-400" },
          { label: "Avg Price (₦)", value: `₦${avgPrice.toLocaleString("en-NG", { maximumFractionDigits: 0 })}`, color: "text-green-700 dark:text-green-400" },
        ].map(k => (
          <Card key={k.label}>
            <CardContent className="pt-5">
              <p className="text-xs text-muted-foreground">{k.label}</p>
              <p className={cn("text-2xl font-bold", k.color)}>{k.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        {["all", ...FEE_CATEGORIES].map(cat => (
          <button
            key={cat}
            onClick={() => setCategoryFilter(cat)}
            className={cn(
              "rounded-full border px-3 py-1 text-xs capitalize transition-colors",
              categoryFilter === cat ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-muted",
            )}
          >{cat === "all" ? "All" : cat}</button>
        ))}
        <button
          onClick={() => setShowInactive(!showInactive)}
          className={cn(
            "ml-auto flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors",
            showInactive ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-muted",
          )}
        >
          {showInactive ? <ToggleRight className="h-3.5 w-3.5" /> : <ToggleLeft className="h-3.5 w-3.5" />}
          Show Inactive
        </button>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Service Name</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Base Price</TableHead>
                  <TableHead>Unit</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Notes</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {fees.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="py-12 text-center text-muted-foreground">
                      <DollarSign className="mx-auto mb-2 h-6 w-6 opacity-30" />No services found
                    </TableCell>
                  </TableRow>
                ) : fees.map(fee => (
                  <TableRow key={fee.id} className={cn(!fee.active && "opacity-50")}>
                    <TableCell className="font-medium">{fee.service_name}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className={cn("text-xs capitalize", CATEGORY_COLORS[fee.category] ?? "")}>
                        {fee.category}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono">₦{Number(fee.base_price ?? 0).toLocaleString()}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{fee.unit}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className={cn("text-xs", fee.active ? "border-green-500/30 text-green-700 dark:text-green-400 bg-green-500/10" : "border-slate-500/30 text-slate-700 dark:text-slate-400")}>
                        {fee.active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-[150px] truncate">{fee.notes ?? "—"}</TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => openEdit(fee)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        {fee.active && (
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-red-400 hover:text-red-300 hover:bg-red-500/10"
                            onClick={() => deleteMut.mutate(fee.id)} disabled={deleteMut.isPending}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
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

      {/* ── Add / Edit Dialog ─────────────────────────────────────────────── */}
      <Dialog open={formOpen} onOpenChange={v => { setFormOpen(v); if (!v) setEditFee(null); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editFee ? "Edit Service Fee" : "Add Service Fee"}</DialogTitle>
            <DialogDescription>{editFee ? `Editing: ${editFee.service_name}` : "Add a new service to the fee schedule"}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Service Name *</Label>
              <Input value={form.service_name} onChange={e => setForm(f => ({ ...f, service_name: e.target.value }))} placeholder="e.g. Initial Consultation" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Category *</Label>
                <Select value={form.category} onValueChange={v => setForm(f => ({ ...f, category: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {FEE_CATEGORIES.map(c => <SelectItem key={c} value={c}>{c.replace(/\b\w/g, x => x.toUpperCase())}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Base Price (₦) *</Label>
                <Input type="number" min="0" value={form.base_price} onChange={e => setForm(f => ({ ...f, base_price: e.target.value }))} placeholder="0.00" />
              </div>
            </div>
            <div className="space-y-1">
              <Label>Unit</Label>
              <Input value={form.unit} onChange={e => setForm(f => ({ ...f, unit: e.target.value }))} placeholder="e.g. per visit, per test" />
            </div>
            <div className="space-y-1">
              <Label>Notes</Label>
              <Input value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} placeholder="Optional notes..." />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFormOpen(false)}>Cancel</Button>
            <Button
              disabled={!form.service_name.trim() || !form.base_price || saveMut.isPending}
              onClick={() => saveMut.mutate()}
            >
              {saveMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {editFee ? "Save Changes" : "Add Service"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
