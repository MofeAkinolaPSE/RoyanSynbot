import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
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
  BedDouble, Building2, Users, RefreshCw, Loader2, Plus, UserPlus, Trash2,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────
interface Ward {
  id: string;
  name: string;
  ward_type?: string;
  total_beds?: number;
  occupied_beds?: number;
  description?: string;
}

interface Bed {
  id: string;
  ward_id: string;
  bed_number?: string;
  bed_type?: string;
  status?: string;
  patient_id?: string;
  current_patient_id?: string;
  admitted_at?: string;
  notes?: string;
}

const BED_STATUS_COLORS: Record<string, string> = {
  available:   "bg-green-500/20 text-green-400 border-green-500/30",
  occupied:    "bg-red-500/20 text-red-400 border-red-500/30",
  maintenance: "bg-slate-500/20 text-slate-300 border-slate-500/30",
  reserved:    "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
};

function BedBadge({ status }: { status?: string }) {
  const s = status ?? "available";
  const cls = BED_STATUS_COLORS[s] ?? BED_STATUS_COLORS.maintenance;
  return (
    <Badge variant="outline" className={cn("text-xs capitalize", cls)}>
      {s}
    </Badge>
  );
}

function occupancyColor(pct: number) {
  if (pct >= 90) return "bg-red-500";
  if (pct >= 75) return "bg-amber-500";
  return "bg-green-500";
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function WardsAndBeds() {
  const qc = useQueryClient();
  const { toast } = useToast();

  const [tab, setTab] = useState("wards");
  const [selectedWard, setSelectedWard] = useState<string>("all");
  const [admitOpen, setAdmitOpen] = useState(false);
  const [createWardOpen, setCreateWardOpen] = useState(false);
  const [activeBed, setActiveBed] = useState<Bed | null>(null);
  const [admitForm, setAdmitForm] = useState({ patient_id: "", notes: "" });
  const [wardForm, setWardForm] = useState({ name: "", ward_type: "general", total_beds: 10, description: "" });

  // Wards query
  const { data: wardsData, isLoading: wardsLoading, refetch: refetchWards } = useQuery({
    queryKey: ["wards"],
    queryFn: () => api.hospital.wards.list(),
    staleTime: 60_000,
  });
  const wards: Ward[] = Array.isArray(wardsData?.wards) ? wardsData.wards : Array.isArray(wardsData) ? wardsData : [];

  // Beds query (for selected ward)
  const { data: bedsData, isLoading: bedsLoading, refetch: refetchBeds } = useQuery({
    queryKey: ["beds", selectedWard],
    queryFn: () => selectedWard !== "all" ? api.hospital.wards.beds(selectedWard) : Promise.resolve({ beds: [] }),
    enabled: selectedWard !== "all",
    staleTime: 30_000,
  });
  const beds: Bed[] = Array.isArray(bedsData?.beds) ? bedsData.beds : Array.isArray(bedsData) ? bedsData : [];

  const totalBeds     = wards.reduce((s, w) => s + (w.total_beds ?? 0), 0);
  const occupiedBeds  = wards.reduce((s, w) => s + (w.occupied_beds ?? 0), 0);
  const availableBeds = totalBeds - occupiedBeds;

  // Mutations
  const admitMut = useMutation({
    mutationFn: () => {
      if (!activeBed) return Promise.reject();
      return api.hospital.wards.admitBed(activeBed.ward_id, activeBed.id, admitForm);
    },
    onSuccess: () => {
      toast({ title: "Patient admitted to bed" });
      setAdmitOpen(false);
      setAdmitForm({ patient_id: "", notes: "" });
      void qc.invalidateQueries({ queryKey: ["beds"] });
      void qc.invalidateQueries({ queryKey: ["wards"] });
    },
    onError: (e: any) => toast({ title: "Admission failed", description: e.message, variant: "destructive" }),
  });

  const freeMut = useMutation({
    mutationFn: (bed: Bed) => api.hospital.wards.freeBed(bed.ward_id, bed.id),
    onSuccess: () => {
      toast({ title: "Bed freed" });
      void qc.invalidateQueries({ queryKey: ["beds"] });
      void qc.invalidateQueries({ queryKey: ["wards"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const createWardMut = useMutation({
    mutationFn: () => api.hospital.wards.create(wardForm),
    onSuccess: () => {
      toast({ title: "Ward created" });
      setCreateWardOpen(false);
      setWardForm({ name: "", ward_type: "general", total_beds: 10, description: "" });
      void qc.invalidateQueries({ queryKey: ["wards"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  return (
    <motion.div className="space-y-6" {...motionTransitions.fadeInUp}>
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Wards & Beds</h1>
          <p className="text-sm text-muted-foreground">Ward occupancy, bed assignments, and admissions</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => { void refetchWards(); void refetchBeds(); }} className="gap-2">
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </Button>
          <Button size="sm" onClick={() => setCreateWardOpen(true)} className="gap-2">
            <Plus className="h-3.5 w-3.5" /> Add Ward
          </Button>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "Total Beds",      value: totalBeds,     icon: <BedDouble className="h-4 w-4" />,  color: "text-blue-400" },
          { label: "Occupied",        value: occupiedBeds,  icon: <Users className="h-4 w-4" />,      color: "text-red-400"  },
          { label: "Available",       value: availableBeds, icon: <Building2 className="h-4 w-4" />,  color: "text-green-400" },
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
          <TabsTrigger value="wards">Ward Overview</TabsTrigger>
          <TabsTrigger value="beds">Bed Detail</TabsTrigger>
        </TabsList>

        {/* Ward overview tab */}
        <TabsContent value="wards">
          {wardsLoading ? (
            <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : wards.length === 0 ? (
            <div className="py-16 text-center text-sm text-muted-foreground">
              <Building2 className="mx-auto mb-3 h-8 w-8 opacity-30" />No wards configured
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 mt-4">
              {wards.map(w => {
                const total    = w.total_beds   ?? 0;
                const occupied = w.occupied_beds ?? 0;
                const pct      = total > 0 ? Math.round((occupied / total) * 100) : 0;
                return (
                  <Card
                    key={w.id}
                    className="cursor-pointer hover:border-primary/40 transition-colors"
                    onClick={() => { setSelectedWard(w.id); setTab("beds"); }}
                  >
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">{w.name}</CardTitle>
                      <p className="text-xs text-muted-foreground capitalize">{w.ward_type}</p>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <div className="flex justify-between text-sm">
                        <span>{occupied} / {total} beds</span>
                        <span className={cn("font-semibold", pct >= 90 ? "text-red-400" : pct >= 75 ? "text-amber-400" : "text-green-400")}>
                          {pct}%
                        </span>
                      </div>
                      <Progress value={pct} className="h-2" indicatorClassName={occupancyColor(pct)} />
                      {w.description && (
                        <p className="text-xs text-muted-foreground">{w.description}</p>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </TabsContent>

        {/* Beds tab */}
        <TabsContent value="beds" className="space-y-4">
          <div className="flex items-center gap-3 mt-4">
            <Label className="shrink-0 text-sm">Filter by Ward</Label>
            <Select value={selectedWard} onValueChange={setSelectedWard}>
              <SelectTrigger className="w-64">
                <SelectValue placeholder="Select ward" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">-- Select a ward --</SelectItem>
                {wards.map(w => <SelectItem key={w.id} value={w.id}>{w.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          {selectedWard === "all" ? (
            <div className="py-12 text-center text-sm text-muted-foreground">Select a ward to view beds</div>
          ) : bedsLoading ? (
            <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : (
            <Card>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Bed No.</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Patient MRN</TableHead>
                      <TableHead>Admitted</TableHead>
                      <TableHead>Notes</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {beds.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">No beds found for this ward</TableCell>
                      </TableRow>
                    ) : beds.map(bed => (
                      <TableRow key={bed.id}>
                        <TableCell className="font-mono text-sm">{bed.bed_number ?? String(bed.id).slice(0, 6)}</TableCell>
                        <TableCell className="capitalize text-xs">{bed.bed_type ?? "standard"}</TableCell>
                        <TableCell><BedBadge status={bed.status} /></TableCell>
                        <TableCell className="font-mono text-xs">{bed.current_patient_id ?? bed.patient_id ?? "—"}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {bed.admitted_at ? new Date(bed.admitted_at).toLocaleDateString() : "—"}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-[120px] truncate">{bed.notes ?? "—"}</TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            {bed.status === "available" && (
                              <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1"
                                onClick={() => { setActiveBed(bed); setAdmitOpen(true); }}>
                                <UserPlus className="h-3 w-3" /> Admit
                              </Button>
                            )}
                            {bed.status === "occupied" && (
                              <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1 border-green-500/40 text-green-400 hover:bg-green-500/10"
                                onClick={() => freeMut.mutate(bed)} disabled={freeMut.isPending}>
                                <Trash2 className="h-3 w-3" /> Free
                              </Button>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* ── Admit Dialog ───────────────────────────────────────────────── */}
      <Dialog open={admitOpen} onOpenChange={setAdmitOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Admit Patient</DialogTitle>
            <DialogDescription>Bed {activeBed?.bed_number ?? String(activeBed?.id ?? "").slice(0, 6)}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Patient MRN *</Label>
              <Input value={admitForm.patient_id} onChange={e => setAdmitForm(f => ({ ...f, patient_id: e.target.value }))} placeholder="e.g. RHN-000001" />
            </div>
            <div className="space-y-1">
              <Label>Notes</Label>
              <Input value={admitForm.notes} onChange={e => setAdmitForm(f => ({ ...f, notes: e.target.value }))} placeholder="Admission notes (optional)" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAdmitOpen(false)}>Cancel</Button>
            <Button disabled={!admitForm.patient_id.trim() || admitMut.isPending} onClick={() => admitMut.mutate()}>
              {admitMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}Confirm Admission
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Create Ward Dialog ─────────────────────────────────────────── */}
      <Dialog open={createWardOpen} onOpenChange={setCreateWardOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create Ward</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4 py-2">
            <div className="col-span-2 space-y-1">
              <Label>Ward Name *</Label>
              <Input value={wardForm.name} onChange={e => setWardForm(f => ({ ...f, name: e.target.value }))} placeholder="e.g. Male Medical Ward" />
            </div>
            <div className="space-y-1">
              <Label>Ward Type</Label>
              <Select value={wardForm.ward_type} onValueChange={v => setWardForm(f => ({ ...f, ward_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["general", "maternity", "pediatrics", "icu", "surgical", "emergency", "isolation"].map(t => (
                    <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Total Beds</Label>
              <Input type="number" min={1} value={wardForm.total_beds}
                onChange={e => setWardForm(f => ({ ...f, total_beds: parseInt(e.target.value) || 1 }))} />
            </div>
            <div className="col-span-2 space-y-1">
              <Label>Description</Label>
              <Input value={wardForm.description} onChange={e => setWardForm(f => ({ ...f, description: e.target.value }))} placeholder="Optional description" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateWardOpen(false)}>Cancel</Button>
            <Button disabled={!wardForm.name.trim() || createWardMut.isPending} onClick={() => createWardMut.mutate()}>
              {createWardMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}Create Ward
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
