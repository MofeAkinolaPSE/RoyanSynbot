import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
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
  BedDouble, Building2, Users, RefreshCw, Loader2, Plus,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { BedWorkspacePanel } from "@/components/wards/BedWorkspacePanel";
import { BedBadge } from "@/components/wards/wards-shared";

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
  current_patient_id?: string;
  patient_name?: string;
  patient_mrn?: string;
  admitted_at?: string;
  notes?: string;
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
  const [createWardOpen, setCreateWardOpen] = useState(false);
  const [wardForm, setWardForm] = useState({ name: "", ward_type: "general", total_beds: 10, description: "" });
  const [selectedBed, setSelectedBed] = useState<Bed | null>(null);
  const [addBedOpen, setAddBedOpen] = useState(false);
  const [addBedForm, setAddBedForm] = useState({ bed_number: "", bed_type: "standard" });

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

  const selectedWardObj = wards.find(w => w.id === selectedWard);

  // Mutations
  const createWardMut = useMutation({
    mutationFn: () => api.hospital.wards.create(wardForm),
    onSuccess: (res: any) => {
      const bedsProvisioned = Array.isArray(res?.beds) ? res.beds.length : 0;
      toast({ title: "Ward created", description: bedsProvisioned > 0 ? `${bedsProvisioned} bed(s) provisioned` : undefined });
      setCreateWardOpen(false);
      setWardForm({ name: "", ward_type: "general", total_beds: 10, description: "" });
      void qc.invalidateQueries({ queryKey: ["wards"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const addBedMut = useMutation({
    mutationFn: () => api.hospital.wards.addBed(selectedWard, addBedForm),
    onSuccess: () => {
      toast({ title: "Bed added" });
      setAddBedOpen(false);
      setAddBedForm({ bed_number: "", bed_type: "standard" });
      void qc.invalidateQueries({ queryKey: ["beds", selectedWard] });
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
                        <span className={cn("font-semibold", pct >= 90 ? "text-red-700 dark:text-red-400" : pct >= 75 ? "text-amber-700 dark:text-amber-400" : "text-green-700 dark:text-green-400")}>
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
          <div className="flex items-center gap-3 mt-4 flex-wrap">
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
            {selectedWard !== "all" && (
              <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setAddBedOpen(o => !o)}>
                <Plus className="h-3.5 w-3.5" /> Add Bed
              </Button>
            )}
          </div>

          {selectedWard !== "all" && addBedOpen && (
            <Card className="border-primary/30">
              <CardContent className="pt-4 flex flex-wrap items-end gap-3">
                <div className="space-y-1">
                  <Label className="text-xs">Bed Number *</Label>
                  <Input className="w-40" placeholder="e.g. 006" value={addBedForm.bed_number}
                    onChange={e => setAddBedForm(f => ({ ...f, bed_number: e.target.value }))} />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Bed Type</Label>
                  <Select value={addBedForm.bed_type} onValueChange={v => setAddBedForm(f => ({ ...f, bed_type: v }))}>
                    <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {["standard", "icu", "isolation", "maternity", "recovery"].map(t => (
                        <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Button size="sm" disabled={!addBedForm.bed_number.trim() || addBedMut.isPending} onClick={() => addBedMut.mutate()}>
                  {addBedMut.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : null}Add
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setAddBedOpen(false)}>Cancel</Button>
              </CardContent>
            </Card>
          )}

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
                      <TableHead>Patient</TableHead>
                      <TableHead>Admitted</TableHead>
                      <TableHead>Notes</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {beds.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">No beds found for this ward</TableCell>
                      </TableRow>
                    ) : beds.map(bed => (
                      <TableRow key={bed.id} className="cursor-pointer hover:bg-muted/40"
                        onClick={() => setSelectedBed({ ...bed, ward_name: selectedWardObj?.name } as any)}>
                        <TableCell className="font-mono text-sm">{bed.bed_number ?? String(bed.id).slice(0, 6)}</TableCell>
                        <TableCell className="capitalize text-xs">{bed.bed_type ?? "standard"}</TableCell>
                        <TableCell><BedBadge status={bed.status} /></TableCell>
                        <TableCell className="text-xs">
                          {bed.patient_name ? (
                            <div className="flex flex-col">
                              <span className="font-medium">{bed.patient_name}</span>
                              {bed.patient_mrn && <span className="font-mono text-[12px] text-muted-foreground">{bed.patient_mrn}</span>}
                            </div>
                          ) : bed.current_patient_id ? (
                            <span className="text-muted-foreground/50 italic">Empty</span>
                          ) : "—"}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {bed.admitted_at ? new Date(bed.admitted_at).toLocaleDateString() : "—"}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-[120px] truncate">{bed.notes ?? "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

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

      {selectedBed && (
        <BedWorkspacePanel bed={selectedBed} onClose={() => setSelectedBed(null)} />
      )}
    </motion.div>
  );
}
