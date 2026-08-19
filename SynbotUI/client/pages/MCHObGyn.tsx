import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  Heart, RefreshCw, Loader2, Plus, Search,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { ANCWorkspacePanel } from "@/components/mch/ANCWorkspacePanel";
import { ANCStatusBadge, BoolCheck, DELIVERY_MODE_COLORS, emptyAnc, stripEmptyStrings } from "@/components/mch/mch-shared";

export default function MCHObGyn() {
  const { toast } = useToast();
  const qc = useQueryClient();

  // List filter — patient search
  const [filterQuery, setFilterQuery] = useState("");
  const [filterDebounced, setFilterDebounced] = useState("");
  const filterDebounceRef = useRef<ReturnType<typeof setTimeout>>();
  const [filterPatient, setFilterPatient] = useState<any | null>(null);

  // Selected row for the workspace panel
  const [selectedAnc, setSelectedAnc] = useState<any | null>(null);

  // Register ANC dialog
  const [ancOpen, setAncOpen] = useState(false);
  const [ancForm, setAncForm] = useState({ ...emptyAnc });
  const [regQuery, setRegQuery] = useState("");
  const [regDebounced, setRegDebounced] = useState("");
  const regDebounceRef = useRef<ReturnType<typeof setTimeout>>();
  const [regPatient, setRegPatient] = useState<any | null>(null);

  function handleFilterQueryChange(val: string) {
    setFilterQuery(val);
    if (filterDebounceRef.current) clearTimeout(filterDebounceRef.current);
    filterDebounceRef.current = setTimeout(() => setFilterDebounced(val), 400);
  }

  function handleRegQueryChange(val: string) {
    setRegQuery(val);
    if (regDebounceRef.current) clearTimeout(regDebounceRef.current);
    regDebounceRef.current = setTimeout(() => setRegDebounced(val), 400);
  }

  // Queries
  const { data: statsData } = useQuery({
    queryKey: ["mch-stats"],
    queryFn: () => api.hospital.mch.stats(),
  });

  const { data: ancData, isLoading: ancLoading, refetch: refetchAnc } = useQuery({
    queryKey: ["anc-list", filterPatient?.id],
    queryFn: () => api.hospital.mch.listAnc(filterPatient ? { patient_id: Number(filterPatient.id) } : {}),
  });

  const { data: filterSearchData, isFetching: filterSearching } = useQuery({
    queryKey: ["mch-patient-search", filterDebounced],
    queryFn: () => api.hospital.patients.search(filterDebounced),
    enabled: !filterPatient && filterDebounced.length >= 2,
  });
  const filterResults: any[] = Array.isArray(filterSearchData) ? filterSearchData : (filterSearchData?.patients ?? []);

  const { data: regSearchData, isFetching: regSearching } = useQuery({
    queryKey: ["mch-reg-patient-search", regDebounced],
    queryFn: () => api.hospital.patients.search(regDebounced),
    enabled: ancOpen && !regPatient && regDebounced.length >= 2,
  });
  const regResults: any[] = Array.isArray(regSearchData) ? regSearchData : (regSearchData?.patients ?? []);

  const stats = statsData?.anc || { total: 0, active: 0, delivered: 0, referred: 0 };
  const deliveryModes = statsData?.delivery_modes || {};
  const vaccineStats = statsData?.immunisation_counts || {};
  const ancList = ancData?.records || [];

  const resetRegForm = () => {
    setAncForm({ ...emptyAnc });
    setRegQuery("");
    setRegDebounced("");
    setRegPatient(null);
  };

  // Mutations
  const ancMut = useMutation({
    mutationFn: (d: typeof ancForm) => api.hospital.mch.registerAnc({
      ...stripEmptyStrings(d),
      patient_id: Number(regPatient.id),
      encounter_id: d.encounter_id ? Number(d.encounter_id) : undefined,
      gravida: d.gravida ? Number(d.gravida) : undefined,
      para: d.para ? Number(d.para) : undefined,
      gestational_age_weeks: d.gestational_age_weeks ? Number(d.gestational_age_weeks) : undefined,
    }),
    onSuccess: () => {
      toast({ title: "ANC registration complete" });
      setAncOpen(false);
      resetRegForm();
      qc.invalidateQueries({ queryKey: ["anc-list"] });
      qc.invalidateQueries({ queryKey: ["mch-stats"] });
    },
    onError: () => toast({ title: "Failed to register ANC patient", variant: "destructive" }),
  });

  return (
    <motion.div className="p-6 space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-500/20 rounded-lg">
            <Heart className="w-6 h-6 text-blue-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">MCH / OB-GYN</h1>
            <p className="text-sm text-muted-foreground">Antenatal care, deliveries, newborn assessment, and immunisation</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="border-border"
            onClick={() => { refetchAnc(); qc.invalidateQueries({ queryKey: ["mch-stats"] }); }}>
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button size="sm" className="bg-blue-700 hover:bg-blue-800"
            onClick={() => { resetRegForm(); setAncOpen(true); }}>
            <Plus className="w-4 h-4 mr-1" /> Register ANC
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Total ANC",  value: stats.total,    color: "text-foreground",  bg: "bg-muted/30" },
          { label: "Active",     value: stats.active,   color: "text-green-700",   bg: "bg-green-50" },
          { label: "Delivered",  value: stats.delivered,color: "text-blue-700",    bg: "bg-blue-50" },
          { label: "Referred",   value: stats.referred, color: "text-orange-700",  bg: "bg-orange-50" },
        ].map(k => (
          <Card key={k.label} className={cn("border-border", k.bg)}>
            <CardContent className="pt-4 pb-3">
              <p className="text-xs text-muted-foreground uppercase tracking-wide">{k.label}</p>
              <p className={cn("text-2xl font-bold mt-1", k.color)}>{k.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Tabs */}
      <Tabs defaultValue="anc">
        <TabsList className="bg-muted border border-border">
          <TabsTrigger value="anc">ANC Register</TabsTrigger>
          <TabsTrigger value="stats">Delivery Stats</TabsTrigger>
        </TabsList>

        {/* ANC Register Tab */}
        <TabsContent value="anc" className="mt-4 space-y-4">
          <div className="flex items-center gap-2 flex-wrap">
            {!filterPatient ? (
              <div className="relative flex-1 max-w-xs">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder="Search patient to filter…"
                  value={filterQuery}
                  onChange={e => handleFilterQueryChange(e.target.value)}
                  className="pl-9 bg-background border-border text-foreground text-sm h-8"
                />
                {filterQuery.length >= 2 && (filterSearching || filterResults.length > 0) && (
                  <div className="absolute z-10 mt-1 w-full max-h-48 overflow-y-auto rounded-md border bg-popover shadow-md">
                    {filterSearching && <p className="px-3 py-2 text-xs text-muted-foreground">Searching…</p>}
                    {filterResults.map((p: any) => (
                      <button key={p.id}
                        className="w-full text-left px-3 py-2 text-xs hover:bg-muted/40 transition-colors"
                        onClick={() => { setFilterPatient(p); setFilterQuery(""); setFilterDebounced(""); }}>
                        <p className="font-medium text-sm">{p.first_name} {p.last_name}</p>
                        <p className="text-muted-foreground">MRN: {p.mrn}</p>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-2 rounded-md border border-primary/40 bg-primary/5 px-3 py-1.5 text-xs">
                <span className="font-medium">{filterPatient.first_name} {filterPatient.last_name}</span>
                <span className="text-muted-foreground font-mono">{filterPatient.mrn}</span>
                <Button size="sm" variant="ghost" className="h-5 px-1.5 text-xs" onClick={() => setFilterPatient(null)}>Clear</Button>
              </div>
            )}
          </div>

          <Card className="border-border bg-muted/20">
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  <TableHead className="text-muted-foreground text-xs">ID</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Patient</TableHead>
                  <TableHead className="text-muted-foreground text-xs">G/P</TableHead>
                  <TableHead className="text-muted-foreground text-xs">EDD</TableHead>
                  <TableHead className="text-muted-foreground text-xs">GA (wks)</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {ancLoading
                  ? <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                      <Loader2 className="w-5 h-5 animate-spin inline mr-2" />Loading…
                    </TableCell></TableRow>
                  : ancList.length === 0
                    ? <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No ANC records found</TableCell></TableRow>
                    : ancList.map((r: any) => (
                      <TableRow key={r.id} className="border-border/50 hover:bg-muted/30 cursor-pointer"
                        onClick={() => setSelectedAnc(r)}>
                        <TableCell className="font-mono text-xs text-muted-foreground">{r.id}</TableCell>
                        <TableCell className="text-sm text-foreground">
                          {r.patient_name ?? `#${r.patient_id}`}
                          {r.mrn && <span className="text-xs text-muted-foreground font-mono ml-2">{r.mrn}</span>}
                        </TableCell>
                        <TableCell className="text-sm">G{r.gravida ?? "?"}/P{r.para ?? "?"}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{r.edd || "—"}</TableCell>
                        <TableCell className="text-sm">{r.gestational_age_weeks ?? "—"}</TableCell>
                        <TableCell><ANCStatusBadge status={r.status} /></TableCell>
                      </TableRow>
                    ))
                }
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        {/* Delivery Stats Tab */}
        <TabsContent value="stats" className="mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card className="border-border bg-muted/30">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Delivery Modes</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {Object.entries(deliveryModes).length === 0
                  ? <p className="text-muted-foreground text-sm">No delivery data</p>
                  : Object.entries(deliveryModes).map(([mode, count]) => (
                    <div key={mode} className="flex justify-between items-center">
                      <Badge variant="outline" className={cn("text-xs uppercase", DELIVERY_MODE_COLORS[mode] || "bg-muted text-muted-foreground")}>
                        {mode}
                      </Badge>
                      <span className="text-foreground font-semibold">{count as number}</span>
                    </div>
                  ))
                }
              </CardContent>
            </Card>
            <Card className="border-border bg-muted/30">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Top Vaccines Administered</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {Object.entries(vaccineStats).length === 0
                  ? <p className="text-muted-foreground text-sm">No immunisation data</p>
                  : Object.entries(vaccineStats)
                      .sort(([, a], [, b]) => (b as number) - (a as number))
                      .slice(0, 8)
                      .map(([vaccine, count]) => (
                        <div key={vaccine} className="flex justify-between items-center">
                          <span className="text-sm text-muted-foreground">{vaccine}</span>
                          <span className="text-foreground font-semibold">{count as number}</span>
                        </div>
                      ))
                }
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      {selectedAnc && (
        <ANCWorkspacePanel anc={selectedAnc} onClose={() => setSelectedAnc(null)} />
      )}

      {/* ── Register ANC Dialog ─────────────────────────────────────────────── */}
      <Dialog open={ancOpen} onOpenChange={(o) => { setAncOpen(o); if (!o) resetRegForm(); }}>
        <DialogContent className="bg-card border-border text-foreground max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Register ANC Patient</DialogTitle>
            <DialogDescription className="text-muted-foreground">Antenatal care registration</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Patient *</Label>
              {!regPatient ? (
                <>
                  <Input placeholder="Search patient by name, phone, or HMO ID…" value={regQuery}
                    onChange={e => handleRegQueryChange(e.target.value)}
                    className="bg-background border-border text-foreground text-sm h-8" />
                  {regSearching && <p className="text-xs text-muted-foreground">Searching…</p>}
                  {regResults.length > 0 && (
                    <div className="space-y-1.5 max-h-40 overflow-y-auto">
                      {regResults.map((p: any) => (
                        <button key={p.id}
                          className="w-full text-left rounded-md border px-3 py-2 text-xs hover:bg-muted/40 transition-colors"
                          onClick={() => setRegPatient(p)}>
                          <p className="font-medium text-sm">{p.first_name} {p.last_name}</p>
                          <p className="text-muted-foreground">MRN: {p.mrn} · {p.gender ?? "—"} · {p.phone ?? "—"}</p>
                        </button>
                      ))}
                    </div>
                  )}
                  {regDebounced.length >= 2 && !regSearching && regResults.length === 0 && (
                    <p className="text-xs text-muted-foreground">No patients found.</p>
                  )}
                </>
              ) : (
                <div className="rounded-md border border-primary/40 bg-primary/5 px-3 py-2 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">{regPatient.first_name} {regPatient.last_name}</p>
                    <p className="text-xs text-muted-foreground font-mono">{regPatient.mrn}</p>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => setRegPatient(null)}>Change</Button>
                </div>
              )}
            </div>
            {[
              { key: "encounter_id",           label: "Encounter ID",         type: "number" },
              { key: "gravida",                label: "Gravida",              type: "number" },
              { key: "para",                   label: "Para",                 type: "number" },
              { key: "lmp",                    label: "LMP (last period)",    type: "date" },
              { key: "edd",                    label: "Expected Delivery",    type: "date" },
              { key: "gestational_age_weeks",  label: "GA (weeks)",           type: "number" },
              { key: "blood_group",            label: "Blood Group" },
            ].map(f => (
              <div key={f.key} className="space-y-1">
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Input type={f.type || "text"} value={(ancForm as any)[f.key] || ""}
                  onChange={e => setAncForm(p => ({ ...p, [f.key]: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-8" />
              </div>
            ))}
            {[
              { key: "rhesus",    label: "Rhesus",     opts: ["positive", "negative"] },
              { key: "hiv_status",label: "HIV Status", opts: ["negative", "positive", "unknown"] },
              { key: "hbsag",     label: "HBsAg",      opts: ["negative", "positive", "unknown"] },
              { key: "syphilis",  label: "Syphilis",   opts: ["negative", "positive", "unknown"] },
            ].map(f => (
              <div key={f.key} className="space-y-1">
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Select value={(ancForm as any)[f.key]}
                  onValueChange={v => setAncForm(p => ({ ...p, [f.key]: v }))}>
                  <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover border-border">
                    {f.opts.map(o => <SelectItem key={o} value={o} className="capitalize">{o}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            ))}
            <div className="col-span-2 flex flex-wrap gap-4 mt-1">
              {[
                ["malaria_prophylaxis", "Malaria prophylaxis"],
                ["tetanus_toxoid", "Tetanus toxoid"],
                ["iron_folic_acid", "Iron/Folic acid"],
              ].map(([k, l]) => (
                <BoolCheck key={k} label={l} checked={!!(ancForm as any)[k]}
                  onChange={v => setAncForm(p => ({ ...p, [k]: v }))} />
              ))}
            </div>
            {[
              { key: "risk_factors",  label: "Risk Factors",   colSpan: 2 },
              { key: "referred_from", label: "Referred From" },
              { key: "notes",         label: "Notes",          colSpan: 2 },
            ].map(f => (
              <div key={f.key} className={cn("space-y-1", (f as any).colSpan === 2 ? "col-span-2" : "")}>
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Textarea value={(ancForm as any)[f.key] || ""}
                  onChange={e => setAncForm(p => ({ ...p, [f.key]: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-16 resize-none" />
              </div>
            ))}
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setAncOpen(false)}>Cancel</Button>
            <Button className="bg-blue-700 hover:bg-blue-800"
              disabled={ancMut.isPending || !regPatient}
              onClick={() => ancMut.mutate(ancForm)}>
              {ancMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Register
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
