import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  ScanLine, RefreshCw, Loader2, Clock, CheckCircle2, AlertTriangle,
  Timer, BarChart3,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { RadiologyWorkspacePanel } from "@/components/radiology/RadiologyWorkspacePanel";
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
  const [tab, setTab] = useState("worklist");
  const [statusFilter, setStatusFilter]     = useState("all");
  const [modalityFilter, setModalityFilter] = useState("all");

  const [panelOrder, setPanelOrder]           = useState<RadiologyOrder | null>(null);
  const [panelInitialTab, setPanelInitialTab] = useState<string | undefined>(undefined);

  // ── Queries ──────────────────────────────────────────────────────────────
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["radiology-orders", statusFilter, modalityFilter],
    queryFn: () => api.hospital.radiology.listOrders({
      ...(statusFilter !== "all" && { status: statusFilter }),
      ...(modalityFilter !== "all" && { modality: modalityFilter }),
    }),
    refetchInterval: 60_000,
  });
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
          <h1 className="text-2xl font-bold tracking-tight">Radiology & Diagnostics</h1>
          <p className="text-sm text-muted-foreground">Imaging requests, worklist, and reporting</p>
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
                              <span className="font-mono text-[12px] text-muted-foreground">{order.patient_mrn}</span>
                            )}
                          </div>
                        </TableCell>
                        <TableCell><ModalityBadge modality={order.modality} /></TableCell>
                        <TableCell className="text-sm">
                          <div className="flex flex-col gap-0.5">
                            <span className="font-medium">{order.body_part ?? "—"}</span>
                            <span className="text-[13px] text-muted-foreground truncate max-w-[200px]">{order.clinical_indication ?? ""}</span>
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
    </motion.div>
  );
}
