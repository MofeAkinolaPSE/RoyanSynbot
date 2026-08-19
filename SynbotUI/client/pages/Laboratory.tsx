import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  FlaskConical, AlertTriangle, Clock, CheckCircle2, RefreshCw,
  Loader2, Timer, Activity, Ruler, Plus, Trash2, Search, TestTube,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { AlertBanner } from "@/components/AlertBanner";
import { InlineWarning } from "@/components/InlineWarning";
import { LabWorkspacePanel } from "@/components/lab/LabWorkspacePanel";
import {
  StatusBadge, UrgencyBadge, elapsed, URGENCY_LEFT_BORDER,
} from "@/components/lab/lab-shared";

// ─── Types ────────────────────────────────────────────────────────────────────
interface LabOrder {
  id: string;
  lab_order_id?: string;
  patient_id?: string | number;
  test_name?: string;
  loinc_code?: string;
  urgency?: string;
  status?: string;
  ordered_at?: string;
  sample_type?: string;
  sample_collected_at?: string;
  ordered_by?: string;
  notes?: string;
  encounter_id?: string | number;
  is_critical?: boolean;
  result_value?: string;
  result_unit?: string;
  result_summary?: string;
  reference_range?: string;
  result_data?: Record<string, any>;
  external_lab?: string;
  report_file_url?: string;
  // Enriched patient fields
  patient_name?: string;
  patient_mrn?: string;
  patient_gender?: string;
  patient_dob?: string;
  patient_blood_group?: string;
  patient_hmo?: string;
  patient_phone?: string;
}

interface TurnaroundStat {
  test_name?: string;
  avg_minutes?: number;
  count?: number;
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function Laboratory() {
  const qc = useQueryClient();
  const { toast } = useToast();

  const [tab, setTab]                   = useState("orders");
  const [urgencyFilter, setUrgencyFilter] = useState("all");
  const [statusFilter, setStatusFilter]   = useState("all");
  const [searchTerm, setSearchTerm]       = useState("");

  // Workspace panel state
  const [panelOrder, setPanelOrder]           = useState<LabOrder | null>(null);
  const [panelInitialTab, setPanelInitialTab] = useState<string | undefined>(undefined);

  // Page-level (master-data) dialogs
  const [refRangeOpen, setRefRangeOpen] = useState(false);
  const [rrForm, setRrForm]             = useState<Record<string, any>>({ test_name: "", unit: "", normal_low: "", normal_high: "" });
  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [newTemplateForm, setNewTemplateForm] = useState<{ test_name: string; analytes: Array<{ name: string; unit: string; normal_low: string; normal_high: string }> }>(
    { test_name: "", analytes: [{ name: "", unit: "", normal_low: "", normal_high: "" }] },
  );

  // ── Queries ──────────────────────────────────────────────────────────────
  const { data: ordersData, isLoading: ordersLoading, refetch, isFetching } = useQuery({
    queryKey: ["lab-orders", urgencyFilter, statusFilter],
    queryFn: () => api.hospital.lab.listOrders({
      ...(urgencyFilter !== "all" && { urgency: urgencyFilter }),
      ...(statusFilter  !== "all" && { status:  statusFilter  }),
    }),
    refetchInterval: 30_000,
  });
  const rawOrders: LabOrder[] = Array.isArray(ordersData?.orders)
    ? ordersData.orders
    : Array.isArray(ordersData) ? ordersData : [];

  // Client-side search filter
  const orders = useMemo(() => {
    const q = searchTerm.trim().toLowerCase();
    if (!q) return rawOrders;
    return rawOrders.filter(o =>
      (o.patient_name ?? "").toLowerCase().includes(q) ||
      (o.patient_mrn  ?? "").toLowerCase().includes(q) ||
      (o.test_name    ?? "").toLowerCase().includes(q) ||
      String(o.id).includes(q)
    );
  }, [rawOrders, searchTerm]);

  const { data: statsData } = useQuery({
    queryKey: ["lab-stats"],
    queryFn: () => api.hospital.lab.stats(),
    refetchInterval: 30_000,
  });

  const { data: tatData } = useQuery({
    queryKey: ["lab-turnaround"],
    queryFn: () => api.hospital.lab.turnaround(),
    enabled: tab === "turnaround",
    staleTime: 120_000,
  });
  const tatStats: TurnaroundStat[] = Array.isArray(tatData?.stats)
    ? tatData.stats
    : Array.isArray(tatData?.records)
    ? tatData.records.map((r: any) => ({ test_name: r.test_name, avg_minutes: r.turnaround_minutes, count: 1 }))
    : Array.isArray(tatData) ? tatData : [];

  const { data: critData } = useQuery({
    queryKey: ["lab-critical"],
    queryFn: () => api.hospital.lab.critical(),
    refetchInterval: 30_000,
  });
  // Rows here are royan_lab_results rows (not orders) — `id` is the result id,
  // `lab_order_id` is the order to open.
  const critResults: LabOrder[] = Array.isArray(critData?.orders)
    ? critData.orders
    : Array.isArray(critData?.critical_results)
    ? critData.critical_results
    : Array.isArray(critData) ? critData : [];

  const { data: refRangeData, isLoading: rrLoading } = useQuery({
    queryKey: ["lab-ref-ranges"],
    queryFn: () => api.hospital.lab.listReferenceRanges(),
    enabled: tab === "references",
    staleTime: 300_000,
  });
  const refRanges: any[] = Array.isArray(refRangeData?.ranges) ? refRangeData.ranges : [];

  const { data: allTemplatesData, refetch: refetchTemplates } = useQuery({
    queryKey: ["lab-templates"],
    queryFn: () => api.hospital.lab.listTemplates(),
    enabled: templatesOpen,
    staleTime: 60_000,
  });
  const allTemplates: any[] = Array.isArray(allTemplatesData?.templates) ? allTemplatesData.templates : [];

  // KPI values
  const pending          = statsData?.pending           ?? 0;
  const sampleCollecting = statsData?.sample_collecting ?? 0;
  const processing       = statsData?.processing        ?? 0;
  const statOverdue      = statsData?.stat_overdue      ?? 0;
  const urgentOverdue    = statsData?.urgent_overdue    ?? 0;
  const criticalActive   = critResults.length;

  // ── Mutations (page-level master data only — order workflow lives in LabWorkspacePanel) ──
  const createTemplateMut = useMutation({
    mutationFn: () => api.hospital.lab.createTemplate({
      test_name: newTemplateForm.test_name,
      analytes: newTemplateForm.analytes
        .filter(a => a.name.trim())
        .map(a => ({
          name: a.name, unit: a.unit || undefined,
          normal_low: a.normal_low !== "" ? Number(a.normal_low) : undefined,
          normal_high: a.normal_high !== "" ? Number(a.normal_high) : undefined,
        })),
    }),
    onSuccess: () => {
      toast({ title: "Template saved" });
      setNewTemplateForm({ test_name: "", analytes: [{ name: "", unit: "", normal_low: "", normal_high: "" }] });
      void refetchTemplates();
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const addRrMut = useMutation({
    mutationFn: () => api.hospital.lab.createReferenceRange(rrForm),
    onSuccess: () => {
      toast({ title: "Reference range added" });
      setRefRangeOpen(false);
      setRrForm({ test_name: "", unit: "", normal_low: "", normal_high: "" });
      void qc.invalidateQueries({ queryKey: ["lab-ref-ranges"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const deleteRrMut = useMutation({
    mutationFn: (id: number) => api.hospital.lab.deleteReferenceRange(id),
    onSuccess: () => {
      toast({ title: "Reference range removed" });
      void qc.invalidateQueries({ queryKey: ["lab-ref-ranges"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  function openPanel(order: LabOrder, initialTab?: string) {
    setPanelOrder(order);
    setPanelInitialTab(initialTab);
  }

  function closePanel() {
    setPanelOrder(null);
    setPanelInitialTab(undefined);
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <motion.div className="space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />

      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Laboratory</h1>
          <p className="text-sm text-muted-foreground">Order queue, results, and turnaround analytics</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refetch()} disabled={isFetching} className="gap-2">
          <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} /> Refresh
        </Button>
      </div>

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        {/* Pending */}
        <Card className="border-yellow-500/20">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-[13px] text-muted-foreground">Pending</p>
                <p className="text-2xl font-bold">{pending}</p>
                <p className="text-[12px] text-muted-foreground mt-0.5">awaiting collection</p>
              </div>
              <Clock className="h-4 w-4 text-yellow-400 mt-0.5" />
            </div>
          </CardContent>
        </Card>

        {/* In Collection */}
        <Card className="border-blue-500/20">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-[13px] text-muted-foreground">In Collection</p>
                <p className="text-2xl font-bold">{sampleCollecting}</p>
                <p className="text-[12px] text-muted-foreground mt-0.5">sample collected</p>
              </div>
              <TestTube className="h-4 w-4 text-blue-400 mt-0.5" />
            </div>
          </CardContent>
        </Card>

        {/* Processing */}
        <Card className="border-purple-500/20">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-[13px] text-muted-foreground">Processing</p>
                <p className="text-2xl font-bold">{processing}</p>
                <p className="text-[12px] text-muted-foreground mt-0.5">in analyzer</p>
              </div>
              <Activity className="h-4 w-4 text-purple-400 mt-0.5" />
            </div>
          </CardContent>
        </Card>

        {/* Critical Results */}
        <Card className={cn(
          "border-red-500/20 transition-colors",
          criticalActive > 0 && "border-red-500/60 bg-red-500/5",
        )}>
          <CardContent className="pt-4 pb-3">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-[13px] text-muted-foreground">Critical</p>
                <p className={cn("text-2xl font-bold", criticalActive > 0 && "text-red-700 dark:text-red-400")}>
                  {criticalActive}
                </p>
                <p className="text-[12px] text-muted-foreground mt-0.5">active alerts</p>
              </div>
              <AlertTriangle className={cn(
                "h-4 w-4 text-red-400 mt-0.5",
                criticalActive > 0 && "animate-pulse",
              )} />
            </div>
          </CardContent>
        </Card>

        {/* STAT Overdue */}
        <Card className={cn(
          "border-orange-500/20",
          statOverdue > 0 && "border-red-500/50 bg-red-500/5",
        )}>
          <CardContent className="pt-4 pb-3">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-[13px] text-muted-foreground">STAT Overdue</p>
                <p className={cn("text-2xl font-bold", statOverdue > 0 && "text-red-700 dark:text-red-400")}>{statOverdue}</p>
                <p className="text-[12px] text-muted-foreground mt-0.5">&gt;30 min pending</p>
              </div>
              <AlertTriangle className="h-4 w-4 text-orange-400 mt-0.5" />
            </div>
          </CardContent>
        </Card>

        {/* Urgent Overdue */}
        <Card className={cn(
          "border-orange-500/20",
          urgentOverdue > 0 && "border-orange-500/50 bg-orange-500/5",
        )}>
          <CardContent className="pt-4 pb-3">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-[13px] text-muted-foreground">Urgent Overdue</p>
                <p className={cn("text-2xl font-bold", urgentOverdue > 0 && "text-orange-700 dark:text-orange-400")}>{urgentOverdue}</p>
                <p className="text-[12px] text-muted-foreground mt-0.5">&gt;2 h pending</p>
              </div>
              <Timer className="h-4 w-4 text-orange-400 mt-0.5" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Tabs ────────────────────────────────────────────────────────────── */}
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="orders">Order Queue</TabsTrigger>
          <TabsTrigger value="turnaround">Turnaround & Critical</TabsTrigger>
          <TabsTrigger value="references">Reference Ranges</TabsTrigger>
        </TabsList>

        {/* ── Order Queue tab ─────────────────────────────────────────────── */}
        <TabsContent value="orders" className="space-y-4">
          {/* Filters + Search */}
          <div className="mt-4 flex flex-wrap gap-3 items-center">
            <div className="relative flex-1 min-w-[200px] max-w-sm">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                className="pl-8 h-9 text-sm"
                placeholder="Search patient, test, order #…"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
              />
            </div>
            <Select value={urgencyFilter} onValueChange={setUrgencyFilter}>
              <SelectTrigger className="w-36 h-9">
                <SelectValue placeholder="Urgency" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Urgencies</SelectItem>
                <SelectItem value="stat">STAT</SelectItem>
                <SelectItem value="urgent">Urgent</SelectItem>
                <SelectItem value="routine">Routine</SelectItem>
              </SelectContent>
            </Select>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-44 h-9">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Statuses</SelectItem>
                <SelectItem value="ordered">Ordered</SelectItem>
                <SelectItem value="sample_collected">Sample Collected</SelectItem>
                <SelectItem value="processing">Processing</SelectItem>
                <SelectItem value="resulted">Resulted</SelectItem>
                <SelectItem value="sent_out">Sent Out</SelectItem>
              </SelectContent>
            </Select>
            {(searchTerm || urgencyFilter !== "all" || statusFilter !== "all") && (
              <Button variant="ghost" size="sm" className="h-9 text-xs text-muted-foreground"
                onClick={() => { setSearchTerm(""); setUrgencyFilter("all"); setStatusFilter("all"); }}>
                Clear filters
              </Button>
            )}
            {searchTerm && (
              <span className="text-xs text-muted-foreground">{orders.length} result{orders.length !== 1 ? "s" : ""}</span>
            )}
          </div>

          <Card>
            <CardContent className="p-0">
              {ordersLoading ? (
                <div className="flex justify-center py-16">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[90px]">Order #</TableHead>
                      <TableHead>Patient</TableHead>
                      <TableHead className="w-[110px]">Payer</TableHead>
                      <TableHead>Test</TableHead>
                      <TableHead className="w-[120px]">Req. By</TableHead>
                      <TableHead className="w-[90px]">Urgency</TableHead>
                      <TableHead className="w-[130px]">Status</TableHead>
                      <TableHead className="w-[80px]">Sample</TableHead>
                      <TableHead className="w-[80px]">Elapsed</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {orders.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={9} className="py-12 text-center text-muted-foreground">
                          <FlaskConical className="mx-auto mb-2 h-6 w-6 opacity-30" />
                          {searchTerm ? "No orders match your search" : "No orders in queue"}
                        </TableCell>
                      </TableRow>
                    ) : orders.map(order => (
                      <TableRow
                        key={order.id}
                        onClick={() => openPanel(order)}
                        className={cn(
                          "cursor-pointer transition-colors border-l-2",
                          "hover:bg-muted/50",
                          URGENCY_LEFT_BORDER[order.urgency ?? "routine"],
                          order.is_critical && "bg-red-500/5 hover:bg-red-500/10",
                        )}
                      >
                        {/* Order # */}
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          #{order.id}
                        </TableCell>

                        {/* Patient */}
                        <TableCell>
                          <div className="flex flex-col gap-0.5">
                            <span className="text-sm font-medium leading-tight">
                              {order.patient_name ?? <span className="text-muted-foreground italic text-xs">ID {order.patient_id}</span>}
                            </span>
                            {order.patient_mrn && (
                              <span className="font-mono text-[12px] text-muted-foreground">{order.patient_mrn}</span>
                            )}
                          </div>
                        </TableCell>

                        {/* Payer */}
                        <TableCell className="text-xs">
                          {order.patient_hmo ? (
                            <Badge variant="outline" className="text-[12px] whitespace-nowrap">{order.patient_hmo}</Badge>
                          ) : (
                            <span className="text-muted-foreground">Private</span>
                          )}
                        </TableCell>

                        {/* Test */}
                        <TableCell>
                          <div className="flex flex-col gap-0.5">
                            <span className="text-sm font-medium leading-tight">
                              {order.test_name}
                              {order.is_critical && <InlineWarning message="Critical" severity="critical" className="ml-2" />}
                              {order.urgency === "stat" && !order.is_critical && <InlineWarning message="STAT" severity="warning" className="ml-2" />}
                            </span>
                            {order.loinc_code && (
                              <span className="font-mono text-[12px] text-muted-foreground">LOINC: {order.loinc_code}</span>
                            )}
                          </div>
                        </TableCell>

                        {/* Requested by */}
                        <TableCell className="text-xs text-muted-foreground truncate max-w-[120px]">
                          {order.ordered_by ?? "—"}
                        </TableCell>

                        {/* Urgency */}
                        <TableCell><UrgencyBadge urgency={order.urgency} /></TableCell>

                        {/* Status */}
                        <TableCell>
                          <div className="flex flex-col gap-1">
                            <StatusBadge status={order.status} />
                            {order.status === "sent_out" && order.external_lab && (
                              <span className="text-[12px] text-cyan-700 dark:text-cyan-400">{order.external_lab}</span>
                            )}
                          </div>
                        </TableCell>

                        {/* Sample type */}
                        <TableCell className="text-xs text-muted-foreground capitalize">
                          {order.sample_type ?? "—"}
                        </TableCell>

                        {/* Elapsed */}
                        <TableCell className="text-xs text-muted-foreground">
                          {elapsed(order.ordered_at)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Turnaround & Critical tab ───────────────────────────────────── */}
        <TabsContent value="turnaround" className="space-y-4 mt-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Timer className="h-4 w-4" /> Turnaround Times
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Test</TableHead>
                      <TableHead>Avg TAT</TableHead>
                      <TableHead>Count</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {tatStats.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3} className="py-6 text-center text-muted-foreground text-xs">No TAT data yet</TableCell>
                      </TableRow>
                    ) : tatStats.map((s, i) => (
                      <TableRow key={i}>
                        <TableCell className="text-sm">{s.test_name}</TableCell>
                        <TableCell className="text-sm">
                          {s.avg_minutes !== undefined ? (
                            s.avg_minutes < 60
                              ? `${Math.round(s.avg_minutes)}m`
                              : `${Math.floor(s.avg_minutes / 60)}h ${Math.round(s.avg_minutes % 60)}m`
                          ) : "—"}
                        </TableCell>
                        <TableCell className="text-sm">{s.count ?? "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm text-red-700 dark:text-red-400">
                  <AlertTriangle className="h-4 w-4" /> Critical Results
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Order</TableHead>
                      <TableHead>Test</TableHead>
                      <TableHead>Result</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {critResults.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3} className="py-6 text-center text-muted-foreground text-xs">
                          <CheckCircle2 className="mx-auto mb-1 h-4 w-4 text-green-400" />No critical results
                        </TableCell>
                      </TableRow>
                    ) : critResults.map(r => (
                      <TableRow key={r.id} className="bg-red-500/5 cursor-pointer hover:bg-red-500/10"
                        onClick={() => openPanel({
                          id: r.lab_order_id ?? r.id,
                          test_name: r.test_name,
                          patient_name: r.patient_name,
                          patient_mrn: r.patient_mrn,
                          urgency: r.urgency,
                          is_critical: true,
                        } as LabOrder, "result")}>
                        <TableCell className="font-mono text-xs">#{r.lab_order_id ?? r.id}</TableCell>
                        <TableCell className="text-sm">
                          {r.test_name ?? "—"}
                          {r.patient_mrn && <span className="block text-[12px] text-muted-foreground font-mono">{r.patient_mrn}</span>}
                        </TableCell>
                        <TableCell className="text-sm font-semibold text-red-700 dark:text-red-400">
                          {r.result_summary ?? [r.result_data?.value, r.result_data?.unit].filter(Boolean).join(" ") ?? "Critical"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* ── Reference Ranges tab ────────────────────────────────────────── */}
        <TabsContent value="references" className="space-y-4 mt-4">
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="outline" className="gap-2" onClick={() => setTemplatesOpen(true)}>
              <TestTube className="h-3.5 w-3.5" /> Result Templates
            </Button>
            <Button size="sm" className="gap-2" onClick={() => setRefRangeOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> Add Range
            </Button>
          </div>
          <Card>
            <CardContent className="p-0">
              {rrLoading ? (
                <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Test Name</TableHead>
                      <TableHead>LOINC</TableHead>
                      <TableHead>Gender</TableHead>
                      <TableHead>Age Range</TableHead>
                      <TableHead>Normal Range</TableHead>
                      <TableHead>Critical Range</TableHead>
                      <TableHead>Unit</TableHead>
                      <TableHead></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {refRanges.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={8} className="py-8 text-center text-muted-foreground">
                          <Ruler className="mx-auto mb-2 h-6 w-6 opacity-30" />No reference ranges defined
                        </TableCell>
                      </TableRow>
                    ) : refRanges.map((rr: any) => (
                      <TableRow key={rr.id}>
                        <TableCell className="text-sm font-medium">{rr.test_name}</TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">{rr.loinc_code ?? "—"}</TableCell>
                        <TableCell className="text-xs capitalize">{rr.gender ?? "all"}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {rr.age_min != null || rr.age_max != null
                            ? `${rr.age_min ?? 0}–${rr.age_max ?? "∞"} yrs`
                            : "All ages"}
                        </TableCell>
                        <TableCell className="text-xs text-green-700 dark:text-green-400">
                          {rr.normal_low != null && rr.normal_high != null
                            ? `${rr.normal_low}–${rr.normal_high}`
                            : "—"}
                        </TableCell>
                        <TableCell className="text-xs text-red-700 dark:text-red-400">
                          {rr.critical_low != null || rr.critical_high != null
                            ? `<${rr.critical_low ?? "?"} or >${rr.critical_high ?? "?"}`
                            : "—"}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">{rr.unit ?? "—"}</TableCell>
                        <TableCell>
                          <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-red-400 hover:bg-red-500/10"
                            onClick={() => deleteRrMut.mutate(rr.id)} disabled={deleteRrMut.isPending}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ═══════════════════════════════════════════════════════════════════
          LAB WORKSPACE PANEL — opens inline on row click, no navigation
      ════════════════════════════════════════════════════════════════════ */}
      {panelOrder && (
        <LabWorkspacePanel order={panelOrder} initialTab={panelInitialTab} onClose={closePanel} />
      )}

      {/* ── Add Reference Range Dialog ─────────────────────────────────────── */}
      <Dialog open={refRangeOpen} onOpenChange={setRefRangeOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader><DialogTitle>Add Reference Range</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3 py-2">
            <div className="col-span-2 space-y-1">
              <Label>Test Name *</Label>
              <Input value={rrForm.test_name} onChange={e => setRrForm(f => ({ ...f, test_name: e.target.value }))} placeholder="e.g. Haemoglobin" />
            </div>
            <div className="space-y-1">
              <Label>LOINC Code</Label>
              <Input value={rrForm.loinc_code ?? ""} onChange={e => setRrForm(f => ({ ...f, loinc_code: e.target.value }))} placeholder="e.g. 718-7" />
            </div>
            <div className="space-y-1">
              <Label>Unit</Label>
              <Input value={rrForm.unit} onChange={e => setRrForm(f => ({ ...f, unit: e.target.value }))} placeholder="g/dL" />
            </div>
            <div className="space-y-1">
              <Label>Normal Low</Label>
              <Input type="number" value={rrForm.normal_low} onChange={e => setRrForm(f => ({ ...f, normal_low: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>Normal High</Label>
              <Input type="number" value={rrForm.normal_high} onChange={e => setRrForm(f => ({ ...f, normal_high: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>Critical Low</Label>
              <Input type="number" value={rrForm.critical_low ?? ""} onChange={e => setRrForm(f => ({ ...f, critical_low: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>Critical High</Label>
              <Input type="number" value={rrForm.critical_high ?? ""} onChange={e => setRrForm(f => ({ ...f, critical_high: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>Gender</Label>
              <Select value={rrForm.gender ?? "all"} onValueChange={v => setRrForm(f => ({ ...f, gender: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="male">Male</SelectItem>
                  <SelectItem value="female">Female</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRefRangeOpen(false)}>Cancel</Button>
            <Button disabled={!rrForm.test_name?.trim() || addRrMut.isPending} onClick={() => addRrMut.mutate()}>
              {addRrMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Add Range
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Result Templates Manager Dialog ────────────────────────────────── */}
      <Dialog open={templatesOpen} onOpenChange={setTemplatesOpen}>
        <DialogContent className="sm:max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><TestTube className="h-4 w-4" /> Lab Result Templates</DialogTitle>
            <DialogDescription>Per-test analyte fields shown in the Record Result form (e.g. "Serum Bilirubin" → Total/Direct Bilirubin).</DialogDescription>
          </DialogHeader>

          <div className="space-y-2 py-2">
            {allTemplates.length === 0 ? (
              <p className="text-xs text-muted-foreground text-center py-4">No templates yet — create one below.</p>
            ) : allTemplates.map((t: any) => (
              <div key={t.id} className="rounded border p-2 text-xs">
                <div className="font-medium">{t.test_name} <span className="text-muted-foreground">(v{t.version})</span></div>
                <div className="text-muted-foreground mt-1">{(t.analytes ?? []).map((a: any) => a.name).join(", ")}</div>
              </div>
            ))}
          </div>

          <div className="border-t pt-3 space-y-3">
            <Label>New Template</Label>
            <Input value={newTemplateForm.test_name}
              onChange={e => setNewTemplateForm(f => ({ ...f, test_name: e.target.value }))}
              placeholder="Test name, e.g. Serum Bilirubin (Total And Direct)" />
            {newTemplateForm.analytes.map((a, i) => (
              <div key={i} className="grid grid-cols-[1fr_70px_70px_70px_auto] gap-2 items-end">
                <Input placeholder="Analyte name" value={a.name}
                  onChange={e => setNewTemplateForm(f => ({ ...f, analytes: f.analytes.map((x, j) => j === i ? { ...x, name: e.target.value } : x) }))} />
                <Input placeholder="Unit" value={a.unit}
                  onChange={e => setNewTemplateForm(f => ({ ...f, analytes: f.analytes.map((x, j) => j === i ? { ...x, unit: e.target.value } : x) }))} />
                <Input placeholder="Low" type="number" value={a.normal_low}
                  onChange={e => setNewTemplateForm(f => ({ ...f, analytes: f.analytes.map((x, j) => j === i ? { ...x, normal_low: e.target.value } : x) }))} />
                <Input placeholder="High" type="number" value={a.normal_high}
                  onChange={e => setNewTemplateForm(f => ({ ...f, analytes: f.analytes.map((x, j) => j === i ? { ...x, normal_high: e.target.value } : x) }))} />
                <Button size="icon" variant="ghost"
                  onClick={() => setNewTemplateForm(f => ({ ...f, analytes: f.analytes.filter((_, j) => j !== i) }))}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
            <Button size="sm" variant="outline" className="gap-2"
              onClick={() => setNewTemplateForm(f => ({ ...f, analytes: [...f.analytes, { name: "", unit: "", normal_low: "", normal_high: "" }] }))}>
              <Plus className="h-3.5 w-3.5" /> Add Analyte
            </Button>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setTemplatesOpen(false)}>Close</Button>
            <Button
              disabled={!newTemplateForm.test_name.trim() || !newTemplateForm.analytes.some(a => a.name.trim()) || createTemplateMut.isPending}
              onClick={() => createTemplateMut.mutate()}
            >
              {createTemplateMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Save Template
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
