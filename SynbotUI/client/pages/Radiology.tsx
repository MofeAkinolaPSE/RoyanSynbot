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
  ScanLine, RefreshCw, Loader2, Clock, CheckCircle2, AlertTriangle,
  Timer, Plus, FileText, BarChart3,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";

const MODALITIES = ["xray", "ultrasound", "ct", "mri", "ecg", "echo", "fluoroscopy", "mammography", "endoscopy", "other"];

const MODALITY_COLORS: Record<string, string> = {
  xray:        "bg-slate-500/20 text-slate-300 border-slate-500/30",
  ultrasound:  "bg-blue-500/20 text-blue-400 border-blue-500/30",
  ct:          "bg-purple-500/20 text-purple-400 border-purple-500/30",
  mri:         "bg-indigo-500/20 text-indigo-400 border-indigo-500/30",
  ecg:         "bg-red-500/20 text-red-400 border-red-500/30",
  echo:        "bg-pink-500/20 text-pink-400 border-pink-500/30",
  fluoroscopy: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  mammography: "bg-rose-500/20 text-rose-400 border-rose-500/30",
  endoscopy:   "bg-teal-500/20 text-teal-400 border-teal-500/30",
};

const STATUS_COLORS: Record<string, string> = {
  ordered:     "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  scheduled:   "bg-blue-500/20 text-blue-400 border-blue-500/30",
  in_progress: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  reported:    "bg-green-500/20 text-green-400 border-green-500/30",
  cancelled:   "bg-slate-500/20 text-slate-300 border-slate-500/30",
};

const STATUS_NEXT: Record<string, string> = {
  ordered: "scheduled", scheduled: "in_progress", in_progress: "reported",
};

function fmtDate(ts?: string) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("en-NG", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function elapsed(ts?: string) {
  if (!ts) return "—";
  const mins = Math.round((Date.now() - new Date(ts).getTime()) / 60000);
  return mins < 60 ? `${mins}m` : `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

const EMPTY_ORDER = { encounter_id: "", patient_id: "", modality: "xray", body_part: "", clinical_indication: "", urgency: "routine", notes: "" };
const EMPTY_REPORT = { report: "", impression: "", radiologist_id: "" };

export default function Radiology() {
  const qc = useQueryClient();
  const { toast } = useToast();

  const [tab, setTab] = useState("worklist");
  const [statusFilter, setStatusFilter]   = useState("all");
  const [modalityFilter, setModalityFilter] = useState("all");
  const [orderOpen, setOrderOpen]         = useState(false);
  const [reportOpen, setReportOpen]       = useState(false);
  const [activeOrder, setActiveOrder]     = useState<any | null>(null);
  const [orderForm, setOrderForm]         = useState({ ...EMPTY_ORDER });
  const [reportForm, setReportForm]       = useState({ ...EMPTY_REPORT });

  // ── Queries ────────────────────────────────────────────────────────────────
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["radiology-orders", statusFilter, modalityFilter],
    queryFn: () => api.hospital.radiology.listOrders({
      ...(statusFilter !== "all" && { status: statusFilter }),
      ...(modalityFilter !== "all" && { modality: modalityFilter }),
    }),
    refetchInterval: 60_000,
  });
  const orders: any[] = Array.isArray(data?.orders) ? data.orders : [];

  const { data: statsData } = useQuery({
    queryKey: ["radiology-stats"],
    queryFn: () => api.hospital.radiology.stats(),
    enabled: tab === "stats",
    staleTime: 120_000,
  });
  const stats = statsData ?? {};

  // KPI counts
  const pendingCount = orders.filter(o => ["ordered", "scheduled"].includes(o.status)).length;
  const inProgressCount = orders.filter(o => o.status === "in_progress").length;
  const reportedCount = orders.filter(o => o.status === "reported").length;
  const statCount = orders.filter(o => o.urgency === "stat").length;

  // ── Mutations ──────────────────────────────────────────────────────────────
  const createOrderMut = useMutation({
    mutationFn: () => api.hospital.radiology.createOrder({
      ...orderForm,
      patient_id: Number(orderForm.patient_id),
      encounter_id: Number(orderForm.encounter_id),
    }),
    onSuccess: () => {
      toast({ title: "Imaging request created" });
      setOrderOpen(false);
      setOrderForm({ ...EMPTY_ORDER });
      void qc.invalidateQueries({ queryKey: ["radiology-orders"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const advanceStatusMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.hospital.radiology.advanceStatus(id, { status }),
    onSuccess: () => { toast({ title: "Status updated" }); void qc.invalidateQueries({ queryKey: ["radiology-orders"] }); },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const reportMut = useMutation({
    mutationFn: () => activeOrder ? api.hospital.radiology.submitReport(activeOrder.id, reportForm) : Promise.reject(),
    onSuccess: () => {
      toast({ title: "Report submitted" });
      setReportOpen(false);
      setReportForm({ ...EMPTY_REPORT });
      void qc.invalidateQueries({ queryKey: ["radiology-orders"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  return (
    <motion.div className="space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Radiology & Diagnostics</h1>
          <p className="text-sm text-muted-foreground">Imaging requests, worklist, and reporting</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => void refetch()} disabled={isFetching} className="gap-2">
            <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} /> Refresh
          </Button>
          <Button size="sm" className="gap-2" onClick={() => setOrderOpen(true)}>
            <Plus className="h-3.5 w-3.5" /> New Request
          </Button>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "Pending / Scheduled", value: pendingCount,    icon: <Clock className="h-4 w-4" />,       color: "text-yellow-400" },
          { label: "In Progress",         value: inProgressCount, icon: <ScanLine className="h-4 w-4" />,    color: "text-purple-400" },
          { label: "Reported",            value: reportedCount,   icon: <CheckCircle2 className="h-4 w-4" />,color: "text-green-400"  },
          { label: "STAT Orders",         value: statCount,       icon: <AlertTriangle className="h-4 w-4" />,color: statCount > 0 ? "text-red-400" : "text-slate-400" },
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
          <TabsTrigger value="worklist">Worklist</TabsTrigger>
          <TabsTrigger value="stats">TAT & Volume</TabsTrigger>
        </TabsList>

        {/* ── Worklist Tab ───────────────────────────────────────────────── */}
        <TabsContent value="worklist" className="space-y-4">
          <div className="mt-4 flex flex-wrap gap-3">
            <Select value={modalityFilter} onValueChange={setModalityFilter}>
              <SelectTrigger className="w-36"><SelectValue placeholder="Modality" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Modalities</SelectItem>
                {MODALITIES.map(m => <SelectItem key={m} value={m}>{m.toUpperCase()}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-36"><SelectValue placeholder="Status" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Statuses</SelectItem>
                {["ordered", "scheduled", "in_progress", "reported", "cancelled"].map(s => (
                  <SelectItem key={s} value={s} className="capitalize">{s.replace(/_/g, " ")}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Card>
            <CardContent className="p-0">
              {isLoading ? (
                <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Order #</TableHead>
                      <TableHead>Patient</TableHead>
                      <TableHead>Modality</TableHead>
                      <TableHead>Body Part / Indication</TableHead>
                      <TableHead>Urgency</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Elapsed</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {orders.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={8} className="py-10 text-center text-muted-foreground">
                          <ScanLine className="mx-auto mb-2 h-6 w-6 opacity-30" />No radiology orders found
                        </TableCell>
                      </TableRow>
                    ) : orders.map((order: any) => (
                      <TableRow key={order.id}>
                        <TableCell className="font-mono text-xs">{String(order.id).slice(0, 8)}</TableCell>
                        <TableCell className="font-mono text-xs">{order.patient_id ? String(order.patient_id).slice(0, 8) : "—"}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cn("text-xs uppercase", MODALITY_COLORS[order.modality] ?? "")}>
                            {order.modality}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm">
                          <div className="flex flex-col gap-0.5">
                            <span className="font-medium">{order.body_part ?? "—"}</span>
                            <span className="text-[11px] text-muted-foreground truncate max-w-[200px]">{order.clinical_indication ?? ""}</span>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cn("text-xs capitalize",
                            order.urgency === "stat" ? "border-red-500/30 text-red-400 bg-red-500/10" :
                            order.urgency === "urgent" ? "border-orange-500/30 text-orange-400" :
                            "border-slate-500/30 text-slate-400"
                          )}>
                            {order.urgency}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cn("text-xs capitalize", STATUS_COLORS[order.status] ?? "")}>
                            {order.status?.replace(/_/g, " ")}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">{elapsed(order.ordered_at)}</TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            {STATUS_NEXT[order.status] && order.status !== "in_progress" && (
                              <Button size="sm" variant="outline" className="h-7 px-2 text-xs"
                                onClick={() => advanceStatusMut.mutate({ id: order.id, status: STATUS_NEXT[order.status] })}
                                disabled={advanceStatusMut.isPending}>
                                {STATUS_NEXT[order.status] === "scheduled" ? "Schedule" : "Start Scan"}
                              </Button>
                            )}
                            {order.status === "in_progress" && (
                              <Button size="sm" variant="outline" className="h-7 px-2 text-xs"
                                onClick={() => { setActiveOrder(order); setReportOpen(true); }}>
                                <FileText className="mr-1 h-3.5 w-3.5" /> Report
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

        {/* ── TAT & Volume Tab ───────────────────────────────────────────── */}
        <TabsContent value="stats" className="mt-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <BarChart3 className="h-4 w-4" /> Modality Volume
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {Object.entries(stats.modality_counts ?? {}).map(([mod, count]: [string, any]) => (
                    <div key={mod} className="flex items-center justify-between">
                      <Badge variant="outline" className={cn("text-xs uppercase", MODALITY_COLORS[mod] ?? "")}>{mod}</Badge>
                      <span className="text-sm font-semibold">{count}</span>
                    </div>
                  ))}
                  {Object.keys(stats.modality_counts ?? {}).length === 0 && (
                    <p className="text-xs text-muted-foreground py-4 text-center">No data yet</p>
                  )}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Timer className="h-4 w-4" /> Average TAT (minutes)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {Object.entries(stats.avg_tat_minutes ?? {}).map(([mod, tat]: [string, any]) => (
                    <div key={mod} className="flex items-center justify-between">
                      <Badge variant="outline" className={cn("text-xs uppercase", MODALITY_COLORS[mod] ?? "")}>{mod}</Badge>
                      <span className={cn("text-sm font-semibold", tat > 120 ? "text-red-400" : tat > 60 ? "text-yellow-400" : "text-green-400")}>
                        {tat < 60 ? `${tat}m` : `${Math.floor(tat / 60)}h ${Math.round(tat % 60)}m`}
                      </span>
                    </div>
                  ))}
                  {Object.keys(stats.avg_tat_minutes ?? {}).length === 0 && (
                    <p className="text-xs text-muted-foreground py-4 text-center">No TAT data yet</p>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      {/* ── New Imaging Request Dialog ─────────────────────────────────────── */}
      <Dialog open={orderOpen} onOpenChange={setOrderOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>New Imaging Request</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Patient ID *</Label>
                <Input value={orderForm.patient_id} onChange={e => setOrderForm(f => ({ ...f, patient_id: e.target.value }))}
                  placeholder="Patient ID" className="h-8 text-sm" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Encounter ID *</Label>
                <Input value={orderForm.encounter_id} onChange={e => setOrderForm(f => ({ ...f, encounter_id: e.target.value }))}
                  placeholder="Encounter ID" className="h-8 text-sm" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Modality *</Label>
                <Select value={orderForm.modality} onValueChange={v => setOrderForm(f => ({ ...f, modality: v }))}>
                  <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {MODALITIES.map(m => <SelectItem key={m} value={m}>{m.toUpperCase()}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Urgency</Label>
                <Select value={orderForm.urgency} onValueChange={v => setOrderForm(f => ({ ...f, urgency: v }))}>
                  <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="routine">Routine</SelectItem>
                    <SelectItem value="urgent">Urgent</SelectItem>
                    <SelectItem value="stat">STAT</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Body Part / Region</Label>
              <Input value={orderForm.body_part} onChange={e => setOrderForm(f => ({ ...f, body_part: e.target.value }))}
                placeholder="e.g. Chest, Abdomen, Left Knee" className="h-8 text-sm" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Clinical Indication *</Label>
              <Textarea value={orderForm.clinical_indication}
                onChange={e => setOrderForm(f => ({ ...f, clinical_indication: e.target.value }))}
                placeholder="Reason for imaging request..." rows={2} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Notes</Label>
              <Input value={orderForm.notes} onChange={e => setOrderForm(f => ({ ...f, notes: e.target.value }))}
                placeholder="Optional notes for radiologist" className="h-8 text-sm" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOrderOpen(false)}>Cancel</Button>
            <Button disabled={!orderForm.patient_id || !orderForm.encounter_id || !orderForm.clinical_indication.trim() || createOrderMut.isPending}
              onClick={() => createOrderMut.mutate()}>
              {createOrderMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Submit Request
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Report Submission Dialog ───────────────────────────────────────── */}
      <Dialog open={reportOpen} onOpenChange={setReportOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Submit Radiology Report</DialogTitle>
            <DialogDescription>
              {activeOrder?.modality?.toUpperCase()} — {activeOrder?.body_part ?? "—"} — Order {String(activeOrder?.id ?? "").slice(0, 8)}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1">
              <Label className="text-xs">Radiologist</Label>
              <Input value={reportForm.radiologist_id}
                onChange={e => setReportForm(f => ({ ...f, radiologist_id: e.target.value }))}
                placeholder="Radiologist name / ID" className="h-8 text-sm" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Report *</Label>
              <Textarea value={reportForm.report}
                onChange={e => setReportForm(f => ({ ...f, report: e.target.value }))}
                placeholder="Detailed radiological findings..." rows={5}
                className="font-mono text-sm" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Impression / Conclusion</Label>
              <Textarea value={reportForm.impression}
                onChange={e => setReportForm(f => ({ ...f, impression: e.target.value }))}
                placeholder="Brief impression and clinical recommendation..." rows={3} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReportOpen(false)}>Cancel</Button>
            <Button disabled={!reportForm.report.trim() || reportMut.isPending}
              onClick={() => reportMut.mutate()}>
              {reportMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Submit Report
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
