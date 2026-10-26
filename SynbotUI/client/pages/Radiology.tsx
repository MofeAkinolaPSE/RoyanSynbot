import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DoneTodayCard, type DoneRow } from "@/components/shared/DoneTodayCard";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  ScanLine, RefreshCw, Loader2, Clock, CheckCircle2, AlertTriangle,
  Timer, BarChart3, Plus
} from "lucide-react";
import { api } from "@/lib/api-client";
import { ShowMeHow } from "@/components/tour/ShowMeHow";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { RadiologyWorkspacePanel } from "@/components/radiology/RadiologyWorkspacePanel";
import { HelpHint } from "@/components/help/HelpHint";
import { WalkInOrderDialog } from "@/components/radiology/WalkInOrderDialog";
import { ScancareDashboard, ScancareToBill } from "@/components/radiology/ScancareDashboard";
import { ScancareBilling } from "@/components/radiology/ScancareBilling";
import {
  StatusBadge, UrgencyBadge, ModalityBadge, elapsed, MODALITY_COLORS, URGENCY_LEFT_BORDER,
} from "@/components/radiology/radiology-shared";

const MODALITIES = ["xray", "ultrasound", "ct", "mri", "ecg", "echo", "fluoroscopy", "mammography", "endoscopy", "other"];

interface RadiologyOrder {
  id: string;
  patient_id?: string | number;
  patient_name?: string;
  patient_mrn?: string;
  modality?: string;
  body_part?: string;
  clinical_indication?: string;
  urgency?: string;
  status?: string;
  ordered_at?: string;
}

export default function Radiology() {
  const [walkInOpen, setWalkInOpen] = useState(false);
  // ?tab=billing opens Scancare's own Billing & cashier (Scancare Books links here)
  const [searchParams] = useSearchParams();
  const [tab, setTab] = useState(searchParams.get("tab") ?? "dashboard");
  // "active" = still to do, any day; reported scans move to "Reported today" (starts empty each morning)
  const [statusFilter, setStatusFilter]     = useState("active");
  const [modalityFilter, setModalityFilter] = useState("all");

  const [panelOrder, setPanelOrder]           = useState<RadiologyOrder | null>(null);
  const [panelInitialTab, setPanelInitialTab] = useState<string | undefined>(undefined);

  // ── Queries ──────────────────────────────────────────────────────────────
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["radiology-orders", statusFilter, modalityFilter],
    queryFn: () => api.hospital.radiology.listOrders({
      ...(statusFilter === "active" ? { view: "active" as const } : statusFilter !== "all" && { status: statusFilter }),
      ...(modalityFilter !== "all" && { modality: modalityFilter }),
    }),
    refetchInterval: 60_000,
  });
  const { data: doneData } = useQuery({
    queryKey: ["radiology-orders", "done-today"],
    queryFn: () => api.hospital.radiology.listOrders({ view: "done" }),
    refetchInterval: 60_000,
  });
  const doneRows: DoneRow[] = (doneData?.orders ?? []).map((o: any) => ({
    id: o.id, patient: o.patient_name ?? `Patient ${o.patient_id}`, mrn: o.patient_mrn,
    what: [o.test_name, o.modality ? String(o.modality).toUpperCase() : null].filter(Boolean).join(" · "), at: o.reported_at,
  }));
  const orders: RadiologyOrder[] = Array.isArray(data?.orders) ? data.orders : [];

  const { data: statsData } = useQuery({
    queryKey: ["radiology-stats"],
    queryFn: () => api.hospital.radiology.stats(),
    refetchInterval: 30_000,
  });
  const stats = statsData ?? {};

  // KPI counts — sourced from the /radiology/stats aggregate, not the
  // paginated worklist, so they stay accurate past the 50-row page limit.
  const pendingCount    = stats.pending ?? 0;
  const inProgressCount = stats.in_progress ?? 0;
  const reportedCount   = stats.reported ?? 0;
  const statCount       = stats.stat_pending ?? 0;

  function openPanel(order: RadiologyOrder, initialTab?: string) {
    setPanelOrder(order);
    setPanelInitialTab(initialTab);
  }

  function closePanel() {
    setPanelOrder(null);
    setPanelInitialTab(undefined);
  }

  return (
    <motion.div className="space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight">Scancare</h1>
            <ShowMeHow only={["scancare-report"]} />
            <Badge variant="outline" className="text-xs">Imaging · its own company and books</Badge>
            <HelpHint id="radiology-worklist-scope" />
            {/* Radiology could only ever RECEIVE work. ScanCare also takes
                clients off the street, so it needs to originate an order. */}
            <Button size="sm" className="ml-2 gap-1.5" onClick={() => setWalkInOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> Walk-in study
            </Button>
          </div>
          <p className="text-sm text-muted-foreground">Scancare's studies, worklist, reporting and billing. Every scan is billed on a Scancare invoice and posts to Scancare Books.</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refetch()} disabled={isFetching} className="gap-2">
          <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} /> Refresh
        </Button>
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
          <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
          <TabsTrigger value="billing">Billing & cashier</TabsTrigger>
          <TabsTrigger value="worklist" data-tour-id="radiology-worklist-tab">Worklist</TabsTrigger>
          <TabsTrigger value="tobill">Not yet billed</TabsTrigger>
          <TabsTrigger value="stats">TAT & Volume</TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard" className="mt-4"><ScancareDashboard /></TabsContent>
        <TabsContent value="billing" className="mt-4"><ScancareBilling /></TabsContent>
        <TabsContent value="tobill" className="mt-4"><ScancareToBill /></TabsContent>

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
                <SelectItem value="active">To do (open orders)</SelectItem>
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
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {orders.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                          <ScanLine className="mx-auto mb-2 h-6 w-6 opacity-30" />No radiology orders found
                        </TableCell>
                      </TableRow>
                    ) : orders.map((order) => (
                      <TableRow
                        key={order.id}
                        onClick={() => openPanel(order)}
                        className={cn(
                          "cursor-pointer transition-colors border-l-2 hover:bg-muted/50",
                          URGENCY_LEFT_BORDER[order.urgency ?? "routine"],
                        )}
                      >
                        <TableCell className="font-mono text-xs text-muted-foreground">#{order.id}</TableCell>
                        <TableCell>
                          <div className="flex flex-col gap-0.5">
                            <span className="text-sm font-medium leading-tight">
                              {order.patient_name ?? <span className="text-muted-foreground italic text-xs">ID {order.patient_id}</span>}
                            </span>
                            {order.patient_mrn && (
                              <span className="font-mono text-xs text-muted-foreground">{order.patient_mrn}</span>
                            )}
                          </div>
                        </TableCell>
                        <TableCell><ModalityBadge modality={order.modality} /></TableCell>
                        <TableCell className="text-sm">
                          <div className="flex flex-col gap-0.5">
                            <span className="font-medium">{order.body_part ?? "—"}</span>
                            <span className="text-xs text-muted-foreground truncate max-w-[200px]">{order.clinical_indication ?? ""}</span>
                          </div>
                        </TableCell>
                        <TableCell><UrgencyBadge urgency={order.urgency} /></TableCell>
                        <TableCell><StatusBadge status={order.status} /></TableCell>
                        <TableCell className="text-xs text-muted-foreground">{elapsed(order.ordered_at)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
          <DoneTodayCard title="Reported today" whatLabel="Study" rows={doneRows}
            onOpen={(id) => { const o = (doneData?.orders ?? []).find((x: any) => x.id === id); if (o) openPanel(o); }} />
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
                      <span className={cn("text-sm font-semibold", tat > 120 ? "text-red-700 dark:text-red-400" : tat > 60 ? "text-yellow-700 dark:text-yellow-400" : "text-green-700 dark:text-green-400")}>
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

      {/* ═══════════════════════════════════════════════════════════════════
          RADIOLOGY WORKSPACE PANEL — opens inline on row click, no navigation
      ════════════════════════════════════════════════════════════════════ */}
      {panelOrder && (
        <RadiologyWorkspacePanel order={panelOrder} initialTab={panelInitialTab} onClose={closePanel} />
      )}
      <WalkInOrderDialog open={walkInOpen} onOpenChange={setWalkInOpen} />

    </motion.div>
  );
}
