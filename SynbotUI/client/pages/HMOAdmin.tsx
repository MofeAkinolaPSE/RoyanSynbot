import { useState } from "react";
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
  ShieldCheck, Plus, Loader2, Building2, ListChecks, Tag,
  RefreshCw, CheckCircle2, XCircle, Clock, KeyRound,
  Database, Users, CalendarCheck, FlaskConical, Pill, Receipt, BedDouble,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────

interface HMO {
  id: number;
  name: string;
  code?: string;
  contact_phone?: string;
  contact_email?: string;
  is_active?: boolean;
  notes?: string;
}

interface Service {
  id: number;
  service_code: string;
  name: string;
  category?: string;
  base_price?: number;
  is_active?: boolean;
}

interface CoverageRule {
  id: number;
  hmo_id: number;
  service_id: number;
  coverage_type: string;
  coverage_value: number;
  requires_approval: boolean;
  limit_type: string;
  limit_value?: number;
  notes?: string;
}

const COVERAGE_TYPES = ["percentage", "fixed", "none"] as const;
const LIMIT_TYPES    = ["none", "per_visit", "per_month", "per_year", "lifetime"] as const;
const CATEGORIES     = ["consultation", "lab", "pharmacy", "ward", "procedure", "imaging", "misc"] as const;

// ─── Component ────────────────────────────────────────────────────────────────

export default function HMOAdmin() {
  const qc = useQueryClient();
  const { toast } = useToast();

  // ── HMOs ─────────────────────────────────────────────────────────────────────
  const [hmoOpen, setHmoOpen] = useState(false);
  const [hmoForm, setHmoForm] = useState({ name: "", code: "", contact_phone: "", contact_email: "", notes: "" });

  const { data: hmosData, isLoading: hmosLoading, refetch: refetchHmos } = useQuery({
    queryKey: ["hmos"],
    queryFn: () => api.hospital.coverage.hmos(),
    staleTime: 60_000,
  });
  const hmos: HMO[] = hmosData?.hmos ?? hmosData ?? [];

  const hmoMut = useMutation({
    mutationFn: () => api.hospital.coverage.createHmo(hmoForm),
    onSuccess: () => {
      toast({ title: "HMO created", description: hmoForm.name });
      setHmoOpen(false);
      setHmoForm({ name: "", code: "", contact_phone: "", contact_email: "", notes: "" });
      void qc.invalidateQueries({ queryKey: ["hmos"] });
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  // ── Services ──────────────────────────────────────────────────────────────────
  const [serviceOpen, setServiceOpen] = useState(false);
  const [serviceForm, setServiceForm] = useState({ service_code: "", name: "", category: "misc", base_price: "" });

  const { data: servicesData, isLoading: servicesLoading, refetch: refetchServices } = useQuery({
    queryKey: ["services-catalog"],
    queryFn: () => api.hospital.coverage.services(),
    staleTime: 60_000,
  });
  const services: Service[] = servicesData?.services ?? servicesData ?? [];

  const serviceMut = useMutation({
    mutationFn: () => api.hospital.coverage.createService({
      ...serviceForm,
      base_price: parseFloat(serviceForm.base_price) || 0,
    }),
    onSuccess: () => {
      toast({ title: "Service created" });
      setServiceOpen(false);
      setServiceForm({ service_code: "", name: "", category: "misc", base_price: "" });
      void qc.invalidateQueries({ queryKey: ["services-catalog"] });
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  // ── Coverage Rules ────────────────────────────────────────────────────────────
  const [ruleOpen, setRuleOpen] = useState(false);
  const [selectedHmoId, setSelectedHmoId] = useState<string>("");
  const [ruleForm, setRuleForm] = useState({
    hmo_id: "",
    service_id: "",
    coverage_type: "percentage" as typeof COVERAGE_TYPES[number],
    coverage_value: "",
    requires_approval: false,
    limit_type: "none" as typeof LIMIT_TYPES[number],
    limit_value: "",
    notes: "",
  });

  const { data: rulesData, isLoading: rulesLoading, refetch: refetchRules } = useQuery({
    queryKey: ["coverage-rules", selectedHmoId],
    queryFn: () => api.hospital.coverage.listRules(selectedHmoId || undefined),
    enabled: true,
    staleTime: 30_000,
  });
  const rules: CoverageRule[] = rulesData?.rules ?? [];

  const ruleMut = useMutation({
    mutationFn: () => api.hospital.coverage.createRule({
      ...ruleForm,
      hmo_id: parseInt(ruleForm.hmo_id),
      service_id: parseInt(ruleForm.service_id),
      coverage_value: parseFloat(ruleForm.coverage_value) || 0,
      limit_value: ruleForm.limit_value ? parseFloat(ruleForm.limit_value) : undefined,
    }),
    onSuccess: () => {
      toast({ title: "Coverage rule created" });
      setRuleOpen(false);
      setRuleForm({ hmo_id: "", service_id: "", coverage_type: "percentage", coverage_value: "", requires_approval: false, limit_type: "none", limit_value: "", notes: "" });
      void qc.invalidateQueries({ queryKey: ["coverage-rules"] });
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  // ─── Approvals ────────────────────────────────────────────────────────────────
  const [approvalFilter, setApprovalFilter] = useState("pending");
  const [resolveOpen, setResolveOpen] = useState(false);
  const [activeAuth, setActiveAuth] = useState<any>(null);
  const [resolveForm, setResolveForm] = useState({ status: "approved", approval_code: "", notes: "" });

  const { data: authsData, isLoading: authsLoading, refetch: refetchAuths } = useQuery({
    queryKey: ["coverage-authorizations", approvalFilter],
    queryFn: () => api.hospital.coverage.listAuthorizations(approvalFilter !== "all" ? approvalFilter : undefined),
    staleTime: 30_000,
  });
  const authorizations: any[] = authsData?.authorizations ?? [];

  const resolveMut = useMutation({
    mutationFn: () => api.hospital.coverage.resolveAuthorization(activeAuth.id, resolveForm),
    onSuccess: () => {
      toast({ title: resolveForm.status === "approved" ? "Authorization approved" : "Authorization rejected" });
      setResolveOpen(false);
      setResolveForm({ status: "approved", approval_code: "", notes: "" });
      void qc.invalidateQueries({ queryKey: ["coverage-authorizations"] });
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  // ─── Hope Sync ───────────────────────────────────────────────────────────────
  const [syncResults, setSyncResults] = useState<Record<string, { ok: boolean; synced?: number; skipped?: number; error?: string; at: string }>>({});
  const [syncingEntity, setSyncingEntity] = useState<string | null>(null);

  const HOPE_ENTITIES = [
    { key: "patients",     label: "Patients",      icon: Users },
    { key: "appointments", label: "Appointments",   icon: CalendarCheck },
    { key: "admissions",   label: "Admissions",     icon: BedDouble },
    { key: "lab",          label: "Lab Results",    icon: FlaskConical },
    { key: "pharmacy",     label: "Pharmacy",       icon: Pill },
    { key: "billing",      label: "Billing",        icon: Receipt },
  ] as const;

  const syncMut = useMutation({
    mutationFn: (entity: string) => {
      setSyncingEntity(entity);
      return api.hospital.hope.sync(entity as any, 200);
    },
    onSuccess: (data: any, entity) => {
      setSyncResults(r => ({
        ...r,
        [entity]: { ok: true, synced: data.synced ?? data.inserted ?? 0, skipped: data.skipped ?? 0, at: new Date().toLocaleTimeString() },
      }));
      setSyncingEntity(null);
      toast({ title: `${entity} sync complete`, description: `${data.synced ?? data.inserted ?? 0} records synced` });
    },
    onError: (e: any, entity) => {
      setSyncResults(r => ({
        ...r,
        [entity]: { ok: false, error: e.message, at: new Date().toLocaleTimeString() },
      }));
      setSyncingEntity(null);
      toast({ title: `${entity} sync failed`, description: e.message, variant: "destructive" });
    },
  });

  // ─── Render ──────────────────────────────────────────────────────────────────

  return (
    <motion.div className="space-y-6" {...motionTransitions.fadeInUp}>
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">HMO & Coverage Engine</h1>
        <p className="text-sm text-muted-foreground">
          Configure health maintenance organisations, service pricing, and coverage rules
        </p>
      </div>

      <Tabs defaultValue="hmos">
        <TabsList className="mb-4">
          <TabsTrigger value="hmos" className="gap-2">
            <Building2 className="h-4 w-4" /> HMOs
          </TabsTrigger>
          <TabsTrigger value="rules" className="gap-2">
            <ListChecks className="h-4 w-4" /> Coverage Rules
          </TabsTrigger>
          <TabsTrigger value="services" className="gap-2">
            <Tag className="h-4 w-4" /> Service Catalog
          </TabsTrigger>
          <TabsTrigger value="approvals" className="gap-2">
            <KeyRound className="h-4 w-4" /> Approvals
            {authorizations.filter(a => a.status === "pending").length > 0 && (
              <span className="ml-1 rounded-full bg-orange-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
                {authorizations.filter(a => a.status === "pending").length}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="hope" className="gap-2">
            <Database className="h-4 w-4" /> Hope Sync
          </TabsTrigger>
        </TabsList>

        {/* ── HMOs Tab ───────────────────────────────────────────────────────── */}
        <TabsContent value="hmos" className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">{hmos.length} registered HMO{hmos.length !== 1 ? "s" : ""}</p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => void refetchHmos()} className="gap-2">
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
              <Button size="sm" onClick={() => setHmoOpen(true)} className="gap-2">
                <Plus className="h-3.5 w-3.5" /> Add HMO
              </Button>
            </div>
          </div>

          {hmosLoading ? (
            <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : hmos.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border py-16 text-center text-sm text-muted-foreground">
              <ShieldCheck className="mx-auto mb-3 h-8 w-8 opacity-30" />
              No HMOs configured yet
            </div>
          ) : (
            <Card>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>HMO Name</TableHead>
                      <TableHead>Code</TableHead>
                      <TableHead>Phone</TableHead>
                      <TableHead>Email</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {hmos.map(h => (
                      <TableRow key={h.id}>
                        <TableCell className="font-medium">{h.name}</TableCell>
                        <TableCell className="font-mono text-xs">{h.code ?? "—"}</TableCell>
                        <TableCell className="text-sm">{h.contact_phone ?? "—"}</TableCell>
                        <TableCell className="text-sm">{h.contact_email ?? "—"}</TableCell>
                        <TableCell>
                          {h.is_active !== false ? (
                            <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/30 text-xs">
                              <CheckCircle2 className="mr-1 h-3 w-3" /> Active
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="bg-slate-500/10 text-slate-400 border-slate-500/30 text-xs">
                              <XCircle className="mr-1 h-3 w-3" /> Inactive
                            </Badge>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ── Coverage Rules Tab ─────────────────────────────────────────────── */}
        <TabsContent value="rules" className="space-y-4">
          <div className="flex items-center gap-3">
            <Select value={selectedHmoId} onValueChange={setSelectedHmoId}>
              <SelectTrigger className="w-56">
                <SelectValue placeholder="Filter by HMO…" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">All HMOs</SelectItem>
                {hmos.map(h => <SelectItem key={h.id} value={String(h.id)}>{h.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <Button variant="outline" size="sm" onClick={() => void refetchRules()}>
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
            <Button size="sm" onClick={() => setRuleOpen(true)} className="gap-2">
              <Plus className="h-3.5 w-3.5" /> Add Rule
            </Button>
          </div>

          {rulesLoading ? (
            <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : rules.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border py-16 text-center text-sm text-muted-foreground">
              <ListChecks className="mx-auto mb-3 h-8 w-8 opacity-30" />
              No coverage rules configured
            </div>
          ) : (
            <Card>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>HMO</TableHead>
                      <TableHead>Service</TableHead>
                      <TableHead>Coverage</TableHead>
                      <TableHead>Value</TableHead>
                      <TableHead>Approval</TableHead>
                      <TableHead>Limit</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rules.map(r => {
                      const hmo     = hmos.find(h => h.id === r.hmo_id);
                      const service = services.find(s => s.id === r.service_id);
                      return (
                        <TableRow key={r.id}>
                          <TableCell className="text-sm">{hmo?.name ?? `HMO ${r.hmo_id}`}</TableCell>
                          <TableCell className="text-sm">{service?.name ?? `Service ${r.service_id}`}</TableCell>
                          <TableCell className="capitalize text-xs">{r.coverage_type}</TableCell>
                          <TableCell className="text-sm font-medium">
                            {r.coverage_type === "percentage"
                              ? `${r.coverage_value}%`
                              : r.coverage_type === "fixed"
                              ? `₦${Number(r.coverage_value).toLocaleString()}`
                              : "—"}
                          </TableCell>
                          <TableCell>
                            {r.requires_approval ? (
                              <Badge variant="outline" className="text-[10px] bg-orange-500/10 text-orange-400 border-orange-500/30">Required</Badge>
                            ) : (
                              <span className="text-xs text-muted-foreground">No</span>
                            )}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground capitalize">
                            {r.limit_type !== "none"
                              ? `${r.limit_value ? `₦${Number(r.limit_value).toLocaleString()} ` : ""}${r.limit_type.replace(/_/g, " ")}`
                              : "—"}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ── Service Catalog Tab ────────────────────────────────────────────── */}
        <TabsContent value="services" className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">{services.length} services</p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => void refetchServices()}>
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
              <Button size="sm" onClick={() => setServiceOpen(true)} className="gap-2">
                <Plus className="h-3.5 w-3.5" /> Add Service
              </Button>
            </div>
          </div>

          {servicesLoading ? (
            <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : services.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border py-16 text-center text-sm text-muted-foreground">
              <Tag className="mx-auto mb-3 h-8 w-8 opacity-30" />
              No services in catalog yet
            </div>
          ) : (
            <Card>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Code</TableHead>
                      <TableHead>Service Name</TableHead>
                      <TableHead>Category</TableHead>
                      <TableHead>Base Price</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {services.map(s => (
                      <TableRow key={s.id}>
                        <TableCell className="font-mono text-xs">{s.service_code}</TableCell>
                        <TableCell className="font-medium">{s.name}</TableCell>
                        <TableCell className="capitalize text-xs">{s.category ?? "—"}</TableCell>
                        <TableCell className="text-sm">
                          {s.base_price ? `₦${Number(s.base_price).toLocaleString()}` : "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ── Approvals Tab ─────────────────────────────────────────────────── */}
        <TabsContent value="approvals" className="space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex gap-2">
              {["pending", "approved", "rejected", "all"].map(s => (
                <button key={s} onClick={() => setApprovalFilter(s)}
                  className={cn("rounded-full border px-3 py-1 text-xs capitalize transition-colors",
                    approvalFilter === s ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-muted")}>
                  {s === "all" ? "All" : s}
                </button>
              ))}
            </div>
            <Button variant="outline" size="sm" onClick={() => void refetchAuths()} className="gap-2">
              <RefreshCw className="h-3.5 w-3.5" /> Refresh
            </Button>
          </div>
          <Card>
            <CardContent className="p-0">
              {authsLoading ? (
                <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Patient ID</TableHead>
                      <TableHead>Service</TableHead>
                      <TableHead>HMO</TableHead>
                      <TableHead>Requested</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Approval Code</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {authorizations.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                          <KeyRound className="mx-auto mb-2 h-6 w-6 opacity-30" />
                          No {approvalFilter !== "all" ? approvalFilter : ""} authorization requests
                        </TableCell>
                      </TableRow>
                    ) : authorizations.map(auth => (
                      <TableRow key={auth.id}>
                        <TableCell className="font-mono text-xs">{auth.patient_id ?? "—"}</TableCell>
                        <TableCell className="text-sm">{auth.service_name ?? `Service #${auth.service_id}` ?? "—"}</TableCell>
                        <TableCell className="text-sm">{auth.hmo_name ?? "—"}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {auth.created_at ? new Date(auth.created_at).toLocaleDateString() : "—"}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cn("text-xs capitalize",
                            auth.status === "approved" ? "border-green-500/30 bg-green-500/10 text-green-400" :
                            auth.status === "rejected" ? "border-red-500/30 bg-red-500/10 text-red-400" :
                            "border-orange-500/30 bg-orange-500/10 text-orange-400")}>
                            {auth.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-mono text-xs">{auth.approval_code ?? "—"}</TableCell>
                        <TableCell>
                          {auth.status === "pending" && (
                            <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1"
                              onClick={() => { setActiveAuth(auth); setResolveOpen(true); }}>
                              <KeyRound className="h-3 w-3" /> Resolve
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Hope Sync Tab ─────────────────────────────────────────────────── */}
        <TabsContent value="hope" className="space-y-4">
          <div>
            <p className="text-sm text-muted-foreground">
              Pull data from the Hope legacy HMS into Synbot. Read-only — no changes are written back.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {HOPE_ENTITIES.map(({ key, label, icon: Icon }) => {
              const result = syncResults[key];
              const isSyncing = syncingEntity === key;
              return (
                <Card key={key}>
                  <CardContent className="pt-5">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted">
                          <Icon className="h-4 w-4 text-muted-foreground" />
                        </div>
                        <div>
                          <p className="text-sm font-semibold">{label}</p>
                          {result ? (
                            result.ok ? (
                              <p className="text-[11px] text-green-400">
                                {result.synced ?? 0} synced · {result.at}
                              </p>
                            ) : (
                              <p className="text-[11px] text-red-400 truncate max-w-[120px]">
                                Error: {result.error}
                              </p>
                            )
                          ) : (
                            <p className="text-[11px] text-muted-foreground">Not synced yet</p>
                          )}
                        </div>
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-3 w-full gap-2"
                      disabled={isSyncing || syncMut.isPending}
                      onClick={() => syncMut.mutate(key)}
                    >
                      {isSyncing
                        ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Syncing…</>
                        : <><RefreshCw className="h-3.5 w-3.5" /> Sync Now</>
                      }
                    </Button>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Sync All Entities</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground mb-3">
                Triggers a sequential sync for all 6 entities. May take 30–60 seconds.
              </p>
              <Button
                variant="outline"
                disabled={syncMut.isPending}
                className="gap-2"
                onClick={() => {
                  const entities = HOPE_ENTITIES.map(e => e.key);
                  const run = (idx: number) => {
                    if (idx >= entities.length) return;
                    syncMut.mutate(entities[idx], { onSettled: () => run(idx + 1) });
                  };
                  run(0);
                }}
              >
                <Database className="h-4 w-4" />
                Sync All from Hope
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── Resolve Authorization Dialog ──────────────────────────────────── */}
      <Dialog open={resolveOpen} onOpenChange={setResolveOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Resolve Authorization</DialogTitle>
            <DialogDescription>
              {activeAuth?.service_name} · Patient {activeAuth?.patient_id}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Decision *</Label>
              <Select value={resolveForm.status} onValueChange={v => setResolveForm(f => ({ ...f, status: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="approved">Approved</SelectItem>
                  <SelectItem value="rejected">Rejected</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {resolveForm.status === "approved" && (
              <div className="space-y-1">
                <Label>HMO Approval Code</Label>
                <Input
                  value={resolveForm.approval_code}
                  onChange={e => setResolveForm(f => ({ ...f, approval_code: e.target.value }))}
                  placeholder="e.g. AUTH-2024-0001"
                />
              </div>
            )}
            <div className="space-y-1">
              <Label>Notes</Label>
              <Textarea
                value={resolveForm.notes}
                onChange={e => setResolveForm(f => ({ ...f, notes: e.target.value }))}
                placeholder="Reason or additional notes..."
                rows={2}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResolveOpen(false)}>Cancel</Button>
            <Button
              disabled={resolveMut.isPending}
              className={resolveForm.status === "rejected" ? "bg-destructive hover:bg-destructive/90" : ""}
              onClick={() => resolveMut.mutate()}
            >
              {resolveMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {resolveForm.status === "approved" ? "Approve" : "Reject"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={hmoOpen} onOpenChange={setHmoOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add HMO</DialogTitle>
            <DialogDescription>Register a new Health Maintenance Organisation</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>HMO Name *</Label>
              <Input
                value={hmoForm.name}
                onChange={e => setHmoForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. AXA Mansard"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Code</Label>
                <Input
                  value={hmoForm.code}
                  onChange={e => setHmoForm(f => ({ ...f, code: e.target.value }))}
                  placeholder="e.g. AXA"
                />
              </div>
              <div className="space-y-1">
                <Label>Phone</Label>
                <Input
                  value={hmoForm.contact_phone}
                  onChange={e => setHmoForm(f => ({ ...f, contact_phone: e.target.value }))}
                  placeholder="+234…"
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label>Email</Label>
              <Input
                type="email"
                value={hmoForm.contact_email}
                onChange={e => setHmoForm(f => ({ ...f, contact_email: e.target.value }))}
                placeholder="claims@hmo.com"
              />
            </div>
            <div className="space-y-1">
              <Label>Notes</Label>
              <Input
                value={hmoForm.notes}
                onChange={e => setHmoForm(f => ({ ...f, notes: e.target.value }))}
                placeholder="Optional notes…"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setHmoOpen(false)}>Cancel</Button>
            <Button disabled={!hmoForm.name.trim() || hmoMut.isPending} onClick={() => hmoMut.mutate()}>
              {hmoMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create HMO
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Add Coverage Rule Dialog ───────────────────────────────────────── */}
      <Dialog open={ruleOpen} onOpenChange={setRuleOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add Coverage Rule</DialogTitle>
            <DialogDescription>Define what an HMO covers for a given service</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>HMO *</Label>
              <Select value={ruleForm.hmo_id} onValueChange={v => setRuleForm(f => ({ ...f, hmo_id: v }))}>
                <SelectTrigger><SelectValue placeholder="Select HMO" /></SelectTrigger>
                <SelectContent>
                  {hmos.map(h => <SelectItem key={h.id} value={String(h.id)}>{h.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Service *</Label>
              <Select value={ruleForm.service_id} onValueChange={v => setRuleForm(f => ({ ...f, service_id: v }))}>
                <SelectTrigger><SelectValue placeholder="Select service" /></SelectTrigger>
                <SelectContent>
                  {services.map(s => <SelectItem key={s.id} value={String(s.id)}>{s.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Coverage Type</Label>
                <Select value={ruleForm.coverage_type} onValueChange={v => setRuleForm(f => ({ ...f, coverage_type: v as any }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {COVERAGE_TYPES.map(t => <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>
                  {ruleForm.coverage_type === "percentage" ? "Coverage %" : ruleForm.coverage_type === "fixed" ? "Fixed Amount (₦)" : "Value"}
                </Label>
                <Input
                  type="number"
                  min={0}
                  max={ruleForm.coverage_type === "percentage" ? 100 : undefined}
                  value={ruleForm.coverage_value}
                  onChange={e => setRuleForm(f => ({ ...f, coverage_value: e.target.value }))}
                  placeholder={ruleForm.coverage_type === "percentage" ? "e.g. 80" : "e.g. 5000"}
                />
              </div>
            </div>
            <div className="flex items-center gap-3">
              <input
                id="requires-approval"
                type="checkbox"
                checked={ruleForm.requires_approval}
                onChange={e => setRuleForm(f => ({ ...f, requires_approval: e.target.checked }))}
                className="rounded border-border"
              />
              <Label htmlFor="requires-approval">Requires pre-authorization</Label>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Limit Type</Label>
                <Select value={ruleForm.limit_type} onValueChange={v => setRuleForm(f => ({ ...f, limit_type: v as any }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {LIMIT_TYPES.map(t => <SelectItem key={t} value={t} className="capitalize">{t.replace(/_/g, " ")}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              {ruleForm.limit_type !== "none" && (
                <div className="space-y-1">
                  <Label>Limit (₦)</Label>
                  <Input
                    type="number"
                    min={0}
                    value={ruleForm.limit_value}
                    onChange={e => setRuleForm(f => ({ ...f, limit_value: e.target.value }))}
                    placeholder="e.g. 50000"
                  />
                </div>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRuleOpen(false)}>Cancel</Button>
            <Button disabled={!ruleForm.hmo_id || !ruleForm.service_id || ruleMut.isPending} onClick={() => ruleMut.mutate()}>
              {ruleMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create Rule
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Add Service Dialog ─────────────────────────────────────────────── */}
      <Dialog open={serviceOpen} onOpenChange={setServiceOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add Service</DialogTitle>
            <DialogDescription>Add a billable service to the catalog</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Code *</Label>
                <Input
                  value={serviceForm.service_code}
                  onChange={e => setServiceForm(f => ({ ...f, service_code: e.target.value }))}
                  placeholder="e.g. CONS-001"
                />
              </div>
              <div className="space-y-1">
                <Label>Category</Label>
                <Select value={serviceForm.category} onValueChange={v => setServiceForm(f => ({ ...f, category: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {CATEGORIES.map(c => <SelectItem key={c} value={c} className="capitalize">{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1">
              <Label>Service Name *</Label>
              <Input
                value={serviceForm.name}
                onChange={e => setServiceForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. General Consultation"
              />
            </div>
            <div className="space-y-1">
              <Label>Base Price (₦)</Label>
              <Input
                type="number"
                min={0}
                value={serviceForm.base_price}
                onChange={e => setServiceForm(f => ({ ...f, base_price: e.target.value }))}
                placeholder="e.g. 10000"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setServiceOpen(false)}>Cancel</Button>
            <Button
              disabled={!serviceForm.service_code.trim() || !serviceForm.name.trim() || serviceMut.isPending}
              onClick={() => serviceMut.mutate()}
            >
              {serviceMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Add Service
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
