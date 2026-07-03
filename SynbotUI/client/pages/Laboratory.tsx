import { useState, useMemo } from "react";
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
  FlaskConical, AlertTriangle, Clock, CheckCircle2, RefreshCw,
  Loader2, Timer, Activity, SendHorizonal, Ruler, Plus, Trash2,
  Upload, Eye, Search, User, Droplets, Stethoscope, TestTube,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/components/AuthProvider";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { AlertBanner } from "@/components/AlertBanner";
import { InlineWarning } from "@/components/InlineWarning";

// ─── Types ────────────────────────────────────────────────────────────────────
interface LabOrder {
  id: string;
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

const ORDER_STATUS_COLORS: Record<string, string> = {
  ordered:          "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  pending:          "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  sample_collected: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  collected:        "bg-blue-500/20 text-blue-400 border-blue-500/30",
  processing:       "bg-purple-500/20 text-purple-400 border-purple-500/30",
  resulted:         "bg-green-500/20 text-green-400 border-green-500/30",
  sent_out:         "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
  cancelled:        "bg-slate-500/20 text-slate-300 border-slate-500/30",
};

const URGENCY_COLORS: Record<string, string> = {
  stat:    "bg-red-500/20 text-red-400 border-red-500/30",
  urgent:  "bg-orange-500/20 text-orange-400 border-orange-500/30",
  routine: "bg-slate-500/20 text-slate-300 border-slate-500/30",
};

const URGENCY_LEFT_BORDER: Record<string, string> = {
  stat:    "border-l-red-500",
  urgent:  "border-l-orange-400",
  routine: "border-l-transparent",
};

function StatusBadge({ status }: { status?: string }) {
  const s = status ?? "pending";
  const cls = ORDER_STATUS_COLORS[s] ?? ORDER_STATUS_COLORS.pending;
  return <Badge variant="outline" className={cn("text-xs capitalize", cls)}>{s.replace(/_/g, " ")}</Badge>;
}

function UrgencyBadge({ urgency }: { urgency?: string }) {
  const u = urgency ?? "routine";
  const cls = URGENCY_COLORS[u] ?? URGENCY_COLORS.routine;
  return <Badge variant="outline" className={cn("text-xs uppercase", cls)}>{u}</Badge>;
}

function elapsed(ts?: string) {
  if (!ts) return "—";
  const mins = Math.round((Date.now() - new Date(ts).getTime()) / 60000);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

// ─── Workflow Progress ─────────────────────────────────────────────────────
const WORKFLOW_STEPS = [
  { key: "ordered",          label: "Ordered" },
  { key: "sample_collected", label: "Collected" },
  { key: "processing",       label: "Processing" },
  { key: "resulted",         label: "Resulted" },
];

function WorkflowProgress({ status }: { status?: string }) {
  const normalised = status === "pending" ? "ordered" : status;
  const currentIdx = WORKFLOW_STEPS.findIndex(s => s.key === normalised);

  return (
    <div className="flex items-start">
      {WORKFLOW_STEPS.map((step, i) => {
        const done   = i <= currentIdx;
        const active = i === currentIdx;
        return (
          <div key={step.key} className="flex items-start flex-1">
            <div className="flex flex-col items-center gap-1 flex-1">
              <div className={cn(
                "h-3 w-3 rounded-full border-2 transition-colors",
                done
                  ? "bg-blue-500 border-blue-500"
                  : "bg-background border-muted-foreground/30",
                active && "ring-4 ring-blue-500/20",
              )} />
              <span className={cn(
                "text-[10px] text-center leading-tight",
                done ? "text-blue-400 font-medium" : "text-muted-foreground",
              )}>{step.label}</span>
            </div>
            {i < WORKFLOW_STEPS.length - 1 && (
              <div className={cn(
                "h-0.5 flex-1 mt-1.5",
                i < currentIdx ? "bg-blue-500" : "bg-muted",
              )} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Detail row: label + value ─────────────────────────────────────────────
function DetailRow({ label, value, mono = false, accent }: {
  label: string; value?: string | null; mono?: boolean; accent?: string;
}) {
  if (!value) return null;
  return (
    <div className="flex items-start justify-between gap-3 py-1 border-b border-border/30 last:border-0">
      <span className="text-xs text-muted-foreground shrink-0">{label}</span>
      <span className={cn("text-xs text-right font-medium", mono && "font-mono", accent)}>{value}</span>
    </div>
  );
}

const EMPTY_RESULT = { result_value: "", result_unit: "", reference_range: "", is_critical: false, notes: "" };

// ─── Component ────────────────────────────────────────────────────────────────
export default function Laboratory() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const { roles } = useAuth();

  const canUploadReports = roles.some(r => ["admin", "lab", "lab_technician", "doctor"].includes(r));

  const [tab, setTab]                   = useState("orders");
  const [urgencyFilter, setUrgencyFilter] = useState("all");
  const [statusFilter, setStatusFilter]   = useState("all");
  const [searchTerm, setSearchTerm]       = useState("");

  // Dialog states
  const [detailOpen, setDetailOpen]     = useState(false);
  const [detailOrder, setDetailOrder]   = useState<LabOrder | null>(null);
  const [resultOpen, setResultOpen]     = useState(false);
  const [sendOutOpen, setSendOutOpen]   = useState(false);
  const [activeOrder, setActiveOrder]   = useState<LabOrder | null>(null);
  const [resultForm, setResultForm]     = useState({ ...EMPTY_RESULT });
  const [sendOutForm, setSendOutForm]   = useState({ external_lab: "", notes: "" });
  const [refRangeOpen, setRefRangeOpen] = useState(false);
  const [rrForm, setRrForm]             = useState<Record<string, any>>({ test_name: "", unit: "", normal_low: "", normal_high: "" });

  const [uploadOpen, setUploadOpen]       = useState(false);
  const [uploadOrderId, setUploadOrderId] = useState<string | null>(null);
  const [uploadFile, setUploadFile]       = useState<File | null>(null);
  const [uploading, setUploading]         = useState(false);
  const [viewerOpen, setViewerOpen]       = useState(false);
  const [viewerUrl, setViewerUrl]         = useState<string | null>(null);
  const [viewerIsImage, setViewerIsImage] = useState(false);

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
  const critOrders: LabOrder[] = Array.isArray(critData?.orders)
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

  // KPI values
  const pending          = statsData?.pending           ?? 0;
  const sampleCollecting = statsData?.sample_collecting ?? 0;
  const processing       = statsData?.processing        ?? 0;
  const statOverdue      = statsData?.stat_overdue      ?? 0;
  const urgentOverdue    = statsData?.urgent_overdue    ?? 0;
  const criticalActive   = critOrders.length;

  // ── Mutations ─────────────────────────────────────────────────────────────
  const collectMut = useMutation({
    mutationFn: (order: LabOrder) => api.hospital.lab.collect(order.id),
    onSuccess: () => {
      toast({ title: "Sample collected" });
      void qc.invalidateQueries({ queryKey: ["lab-orders"] });
      void qc.invalidateQueries({ queryKey: ["lab-stats"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const resultMut = useMutation({
    mutationFn: () => activeOrder ? api.hospital.lab.recordResult(activeOrder.id, resultForm) : Promise.reject(),
    onSuccess: () => {
      toast({ title: "Result recorded" });
      setResultOpen(false);
      setResultForm({ ...EMPTY_RESULT });
      void qc.invalidateQueries({ queryKey: ["lab-orders"] });
      void qc.invalidateQueries({ queryKey: ["lab-stats"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const sendOutMut = useMutation({
    mutationFn: () => activeOrder ? api.hospital.lab.sendOut(activeOrder.id, sendOutForm) : Promise.reject(),
    onSuccess: () => {
      toast({ title: "Order sent out" });
      setSendOutOpen(false);
      setSendOutForm({ external_lab: "", notes: "" });
      void qc.invalidateQueries({ queryKey: ["lab-orders"] });
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

  async function handleUploadReport() {
    if (!uploadOrderId || !uploadFile) return;
    setUploading(true);
    try {
      await api.hospital.lab.uploadReport(uploadOrderId, uploadFile);
      toast({ title: "Report uploaded successfully" });
      setUploadOpen(false);
      setUploadFile(null);
      void qc.invalidateQueries({ queryKey: ["lab-orders"] });
    } catch (e: any) {
      toast({ title: "Upload failed", description: e.message, variant: "destructive" });
    } finally {
      setUploading(false);
    }
  }

  function openReportViewer(url: string) {
    const lower = url.toLowerCase();
    setViewerIsImage(lower.endsWith(".jpg") || lower.endsWith(".jpeg") || lower.endsWith(".png") || lower.endsWith(".webp"));
    setViewerUrl(url);
    setViewerOpen(true);
  }

  function openDetail(order: LabOrder) {
    setDetailOrder(order);
    setDetailOpen(true);
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
                <p className="text-[11px] text-muted-foreground">Pending</p>
                <p className="text-2xl font-bold">{pending}</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">awaiting collection</p>
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
                <p className="text-[11px] text-muted-foreground">In Collection</p>
                <p className="text-2xl font-bold">{sampleCollecting}</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">sample collected</p>
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
                <p className="text-[11px] text-muted-foreground">Processing</p>
                <p className="text-2xl font-bold">{processing}</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">in analyzer</p>
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
                <p className="text-[11px] text-muted-foreground">Critical</p>
                <p className={cn("text-2xl font-bold", criticalActive > 0 && "text-red-400")}>
                  {criticalActive}
                </p>
                <p className="text-[10px] text-muted-foreground mt-0.5">active alerts</p>
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
                <p className="text-[11px] text-muted-foreground">STAT Overdue</p>
                <p className={cn("text-2xl font-bold", statOverdue > 0 && "text-red-400")}>{statOverdue}</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">&gt;30 min pending</p>
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
                <p className="text-[11px] text-muted-foreground">Urgent Overdue</p>
                <p className={cn("text-2xl font-bold", urgentOverdue > 0 && "text-orange-400")}>{urgentOverdue}</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">&gt;2 h pending</p>
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
                      <TableHead>Test</TableHead>
                      <TableHead className="w-[90px]">Urgency</TableHead>
                      <TableHead className="w-[130px]">Status</TableHead>
                      <TableHead className="w-[80px]">Sample</TableHead>
                      <TableHead className="w-[80px]">Elapsed</TableHead>
                      <TableHead className="w-[120px]">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {orders.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={8} className="py-12 text-center text-muted-foreground">
                          <FlaskConical className="mx-auto mb-2 h-6 w-6 opacity-30" />
                          {searchTerm ? "No orders match your search" : "No orders in queue"}
                        </TableCell>
                      </TableRow>
                    ) : orders.map(order => (
                      <TableRow
                        key={order.id}
                        onClick={() => openDetail(order)}
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
                              <span className="font-mono text-[10px] text-muted-foreground">{order.patient_mrn}</span>
                            )}
                          </div>
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
                              <span className="font-mono text-[10px] text-muted-foreground">LOINC: {order.loinc_code}</span>
                            )}
                          </div>
                        </TableCell>

                        {/* Urgency */}
                        <TableCell><UrgencyBadge urgency={order.urgency} /></TableCell>

                        {/* Status */}
                        <TableCell>
                          <div className="flex flex-col gap-1">
                            <StatusBadge status={order.status} />
                            {order.status === "sent_out" && order.external_lab && (
                              <span className="text-[10px] text-cyan-400">{order.external_lab}</span>
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

                        {/* Actions — stop propagation so clicks don't open detail */}
                        <TableCell onClick={e => e.stopPropagation()}>
                          <div className="flex gap-1 flex-wrap">
                            {["pending", "ordered"].includes(order.status ?? "") && (
                              <Button size="sm" variant="outline" className="h-7 px-2 text-xs"
                                onClick={() => collectMut.mutate(order)}
                                disabled={collectMut.isPending}>
                                Collect
                              </Button>
                            )}
                            {["collected", "sample_collected", "processing"].includes(order.status ?? "") && (
                              <>
                                <Button size="sm" variant="outline" className="h-7 px-2 text-xs"
                                  onClick={() => { setActiveOrder(order); setResultOpen(true); }}>
                                  Result
                                </Button>
                                <Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-cyan-400 hover:text-cyan-300"
                                  onClick={() => { setActiveOrder(order); setSendOutOpen(true); }}>
                                  <SendHorizonal className="h-3.5 w-3.5" />
                                </Button>
                              </>
                            )}
                            {order.status === "resulted" && canUploadReports && !order.report_file_url && (
                              <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1"
                                onClick={() => { setUploadOrderId(order.id); setUploadOpen(true); }}>
                                <Upload className="h-3 w-3" /> Upload
                              </Button>
                            )}
                            {order.report_file_url && (
                              <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1 text-primary border-primary/40"
                                onClick={() => openReportViewer(order.report_file_url!)}>
                                <Eye className="h-3 w-3" /> Report
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
                <CardTitle className="flex items-center gap-2 text-sm text-red-400">
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
                    {critOrders.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3} className="py-6 text-center text-muted-foreground text-xs">
                          <CheckCircle2 className="mx-auto mb-1 h-4 w-4 text-green-400" />No critical results
                        </TableCell>
                      </TableRow>
                    ) : critOrders.map(o => (
                      <TableRow key={o.id} className="bg-red-500/5">
                        <TableCell className="font-mono text-xs">{String(o.id).slice(0, 8)}</TableCell>
                        <TableCell className="text-sm">{o.test_name}</TableCell>
                        <TableCell className="text-sm font-semibold text-red-400">
                          {o.result_summary ?? [o.result_data?.value, o.result_data?.unit].filter(Boolean).join(" ") ?? "Critical"}
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
          <div className="flex justify-end">
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
                        <TableCell className="text-xs text-green-400">
                          {rr.normal_low != null && rr.normal_high != null
                            ? `${rr.normal_low}–${rr.normal_high}`
                            : "—"}
                        </TableCell>
                        <TableCell className="text-xs text-red-400">
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
          ORDER DETAIL DIALOG — opens on row click
      ════════════════════════════════════════════════════════════════════ */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FlaskConical className="h-4 w-4 text-blue-400" />
              {detailOrder?.test_name ?? "Lab Order"}
              {detailOrder?.is_critical && (
                <Badge variant="outline" className="ml-1 text-red-400 border-red-500/30 bg-red-500/10 animate-pulse">
                  Critical
                </Badge>
              )}
            </DialogTitle>
            <DialogDescription className="flex items-center gap-2 flex-wrap">
              <span>Order #{detailOrder?.id}</span>
              {detailOrder?.urgency && (
                <UrgencyBadge urgency={detailOrder.urgency} />
              )}
              <span className="text-muted-foreground">· Ordered {elapsed(detailOrder?.ordered_at)} ago</span>
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-6 sm:grid-cols-2 py-2">
            {/* Patient Info */}
            <div className="space-y-2">
              <div className="flex items-center gap-1.5 mb-3">
                <User className="h-3.5 w-3.5 text-muted-foreground" />
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Patient</h4>
              </div>
              <DetailRow label="Name"        value={detailOrder?.patient_name} />
              <DetailRow label="MRN"         value={detailOrder?.patient_mrn} mono />
              <DetailRow label="Gender"      value={detailOrder?.patient_gender} />
              <DetailRow label="Date of Birth" value={detailOrder?.patient_dob} />
              <DetailRow label="Blood Group" value={detailOrder?.patient_blood_group} accent="text-red-400 font-semibold" />
              <DetailRow label="HMO"         value={detailOrder?.patient_hmo ?? "None"} />
              <DetailRow label="Phone"       value={detailOrder?.patient_phone} mono />
              {!detailOrder?.patient_name && (
                <p className="text-xs text-muted-foreground italic">Patient ID: {detailOrder?.patient_id}</p>
              )}
            </div>

            {/* Order Details */}
            <div className="space-y-2">
              <div className="flex items-center gap-1.5 mb-3">
                <Stethoscope className="h-3.5 w-3.5 text-muted-foreground" />
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Order Details</h4>
              </div>
              <DetailRow label="Test"        value={detailOrder?.test_name} />
              <DetailRow label="LOINC Code"  value={detailOrder?.loinc_code} mono />
              <DetailRow label="Sample Type" value={detailOrder?.sample_type} />
              <DetailRow label="Ordered by"  value={detailOrder?.ordered_by} mono />
              <DetailRow label="Ordered at"  value={detailOrder?.ordered_at
                ? new Date(detailOrder.ordered_at).toLocaleString("en-GB", {
                    day: "numeric", month: "short", year: "numeric",
                    hour: "2-digit", minute: "2-digit",
                  })
                : undefined}
              />
              {detailOrder?.result_summary && (
                <DetailRow
                  label="Result"
                  value={detailOrder.result_summary}
                  accent={detailOrder.is_critical ? "text-red-400" : "text-green-400"}
                />
              )}
              {detailOrder?.notes && (
                <div className="py-1">
                  <p className="text-xs text-muted-foreground mb-0.5">Notes</p>
                  <p className="text-xs bg-muted/40 rounded p-2">{detailOrder.notes}</p>
                </div>
              )}
            </div>
          </div>

          {/* Workflow Progress */}
          <div className="border-t pt-4 space-y-3">
            <div className="flex items-center gap-1.5">
              <Activity className="h-3.5 w-3.5 text-muted-foreground" />
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Workflow</h4>
            </div>
            <WorkflowProgress status={detailOrder?.status} />
          </div>

          <DialogFooter className="gap-2 flex-wrap">
            {["pending", "ordered"].includes(detailOrder?.status ?? "") && (
              <Button
                onClick={() => { if (detailOrder) { collectMut.mutate(detailOrder); setDetailOpen(false); } }}
                disabled={collectMut.isPending}
                className="gap-2"
              >
                {collectMut.isPending
                  ? <Loader2 className="h-4 w-4 animate-spin" />
                  : <Droplets className="h-4 w-4" />}
                Collect Sample
              </Button>
            )}
            {["collected", "sample_collected", "processing"].includes(detailOrder?.status ?? "") && (
              <>
                <Button onClick={() => { setActiveOrder(detailOrder); setResultOpen(true); setDetailOpen(false); }} className="gap-2">
                  <FlaskConical className="h-4 w-4" /> Record Result
                </Button>
                <Button variant="outline" className="gap-2 text-cyan-400 border-cyan-500/30"
                  onClick={() => { setActiveOrder(detailOrder); setSendOutOpen(true); setDetailOpen(false); }}>
                  <SendHorizonal className="h-3.5 w-3.5" /> Send Out
                </Button>
              </>
            )}
            {detailOrder?.status === "resulted" && canUploadReports && !detailOrder?.report_file_url && (
              <Button variant="outline" className="gap-2"
                onClick={() => { setUploadOrderId(detailOrder!.id); setUploadOpen(true); setDetailOpen(false); }}>
                <Upload className="h-3.5 w-3.5" /> Upload Report
              </Button>
            )}
            {detailOrder?.report_file_url && (
              <Button variant="outline" className="gap-2 text-primary border-primary/40"
                onClick={() => openReportViewer(detailOrder!.report_file_url!)}>
                <Eye className="h-3.5 w-3.5" /> View Report
              </Button>
            )}
            <Button variant="outline" onClick={() => setDetailOpen(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Record Result Dialog ───────────────────────────────────────────── */}
      <Dialog open={resultOpen} onOpenChange={setResultOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Record Lab Result</DialogTitle>
            <DialogDescription>
              {activeOrder?.test_name} — Order #{activeOrder?.id}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Result Value *</Label>
                <Input value={resultForm.result_value}
                  onChange={e => setResultForm(f => ({ ...f, result_value: e.target.value }))}
                  placeholder="e.g. 14.2" />
              </div>
              <div className="space-y-1">
                <Label>Unit</Label>
                <Input value={resultForm.result_unit}
                  onChange={e => setResultForm(f => ({ ...f, result_unit: e.target.value }))}
                  placeholder="e.g. g/dL" />
              </div>
            </div>
            <div className="space-y-1">
              <Label>Reference Range</Label>
              <Input value={resultForm.reference_range}
                onChange={e => setResultForm(f => ({ ...f, reference_range: e.target.value }))}
                placeholder="e.g. 12.0–16.0 g/dL" />
            </div>
            <div className="space-y-1">
              <Label>Notes</Label>
              <Textarea value={resultForm.notes}
                onChange={e => setResultForm(f => ({ ...f, notes: e.target.value }))}
                placeholder="Clinical notes..." rows={2} />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox id="is-critical" checked={resultForm.is_critical}
                onCheckedChange={v => setResultForm(f => ({ ...f, is_critical: !!v }))} />
              <Label htmlFor="is-critical" className="cursor-pointer text-red-400">
                Mark as Critical Result
              </Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResultOpen(false)}>Cancel</Button>
            <Button
              disabled={!resultForm.result_value.trim() || resultMut.isPending}
              onClick={() => resultMut.mutate()}
              className={resultForm.is_critical ? "bg-red-600 hover:bg-red-700" : ""}
            >
              {resultMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {resultForm.is_critical ? "Save Critical Result" : "Save Result"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Send Out Dialog ────────────────────────────────────────────────── */}
      <Dialog open={sendOutOpen} onOpenChange={setSendOutOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Send Out to External Lab</DialogTitle>
            <DialogDescription>{activeOrder?.test_name}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>External Lab Name *</Label>
              <Input value={sendOutForm.external_lab}
                onChange={e => setSendOutForm(f => ({ ...f, external_lab: e.target.value }))}
                placeholder="e.g. MLSCN Lagos" />
            </div>
            <div className="space-y-1">
              <Label>Notes</Label>
              <Input value={sendOutForm.notes}
                onChange={e => setSendOutForm(f => ({ ...f, notes: e.target.value }))}
                placeholder="Optional notes..." />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSendOutOpen(false)}>Cancel</Button>
            <Button disabled={!sendOutForm.external_lab.trim() || sendOutMut.isPending} onClick={() => sendOutMut.mutate()}>
              {sendOutMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <SendHorizonal className="mr-2 h-3.5 w-3.5" />}
              Send Out
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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

      {/* ── Upload Lab Report Dialog ───────────────────────────────────────── */}
      <Dialog open={uploadOpen} onOpenChange={o => { if (!uploading) setUploadOpen(o); }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Upload className="h-4 w-4" /> Upload Lab Report
            </DialogTitle>
            <DialogDescription>Attach a PDF or image to Order #{uploadOrderId}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1">
              <Label htmlFor="report-file">File (PDF, JPG, PNG — max 20 MB)</Label>
              <Input id="report-file" type="file" accept=".pdf,.jpg,.jpeg,.png,.webp"
                onChange={e => setUploadFile(e.target.files?.[0] ?? null)} className="cursor-pointer" />
            </div>
            {uploadFile && (
              <p className="text-xs text-muted-foreground">Selected: {uploadFile.name} ({(uploadFile.size / 1024).toFixed(0)} KB)</p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setUploadOpen(false); setUploadFile(null); }}>Cancel</Button>
            <Button disabled={!uploadFile || uploading} onClick={handleUploadReport} className="gap-1.5">
              {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
              {uploading ? "Uploading…" : "Upload Report"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Lab Report Viewer Dialog ───────────────────────────────────────── */}
      <Dialog open={viewerOpen} onOpenChange={setViewerOpen}>
        <DialogContent className="max-w-3xl h-[85vh] flex flex-col p-0">
          <DialogHeader className="px-4 pt-4 pb-2 border-b">
            <DialogTitle className="flex items-center gap-2 text-sm">
              <Eye className="h-4 w-4" /> Lab Report
            </DialogTitle>
          </DialogHeader>
          <div className="flex-1 overflow-hidden">
            {viewerUrl && (
              viewerIsImage
                ? <img src={viewerUrl} alt="Lab report" className="w-full h-full object-contain p-2" />
                : <iframe src={viewerUrl} title="Lab report" className="w-full h-full border-0" />
            )}
          </div>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
