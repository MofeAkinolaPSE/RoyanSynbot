import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DoneTodayCard, type DoneRow } from "@/components/shared/DoneTodayCard";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Pill, RefreshCw, Loader2, ClipboardList, CheckCircle2, Undo2, Boxes,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { ShowMeHow } from "@/components/tour/ShowMeHow";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { PharmacyWorkspacePanel } from "@/components/pharmacy/PharmacyWorkspacePanel";
import { StatusBadge, elapsed } from "@/components/pharmacy/pharmacy-shared";

interface Prescription {
  id: string;
  patient_id?: string;
  patient_name?: string;
  patient_mrn?: string;
  drug_name?: string;
  dose?: string;
  dosage?: string;
  frequency?: string;
  status?: string;
  prescribed_at?: string;
}

export default function PharmacyDispensing() {
  const navigate = useNavigate();

  const [tab, setTab]                   = useState("prescriptions");
  // "active" = still to dispense, any day; dispensed ones move to "Dispensed today" (starts empty each morning)
  const [statusFilter, setStatusFilter] = useState("active");

  // Workspace panel state
  const [panelRx, setPanelRx]                 = useState<Prescription | null>(null);
  const [panelInitialTab, setPanelInitialTab] = useState<string | undefined>(undefined);

  // ── Queries ────────────────────────────────────────────────────────────────
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["pharmacy-rx", statusFilter],
    queryFn: () => api.hospital.pharmacy.listRx(statusFilter === "active" ? { view: "active" } : statusFilter !== "all" ? { status: statusFilter } : undefined),
    refetchInterval: 60_000,
  });
  const { data: doneData } = useQuery({
    queryKey: ["pharmacy-rx", "done-today"],
    queryFn: () => api.hospital.pharmacy.listRx({ view: "done" }),
    refetchInterval: 60_000,
  });
  const doneList: any[] = doneData?.prescriptions ?? [];
  const doneRows: DoneRow[] = doneList.map((r: any) => ({
    id: r.id, patient: r.patient_name ?? `Patient ${r.patient_id}`, mrn: r.patient_mrn,
    what: [r.drug_name, r.quantity ? `× ${r.quantity}` : null].filter(Boolean).join(" "), at: r.dispensed_at,
  }));
  const rxList: Prescription[] = Array.isArray(data?.prescriptions) ? data.prescriptions : Array.isArray(data) ? data : [];

  const { data: statsData } = useQuery({
    queryKey: ["pharmacy-stats"],
    queryFn: () => api.hospital.pharmacy.stats(),
    refetchInterval: 30_000,
  });
  const stats = statsData ?? {};

  const { data: returnsData, isLoading: returnsLoading } = useQuery({
    queryKey: ["pharmacy-returns"],
    queryFn: () => api.hospital.pharmacy.listReturns(),
    enabled: tab === "returns",
    staleTime: 30_000,
  });
  const returnsList: any[] = Array.isArray(returnsData?.returns) ? returnsData.returns : [];

  // KPI counts — sourced from /pharmacy/stats, not client-side filters over a
  // possibly-filtered/paginated worklist. Stock-level KPIs moved to the
  // Pharmacy Inventory workspace, correctly scoped to live batches.
  const activeCount    = stats.active ?? 0;
  const pendingCount   = stats.pending ?? 0;
  const dispensedCount = stats.dispensed ?? 0;
  const returnedCount  = stats.returned ?? 0;

  function openPanel(rx: Prescription, initialTab?: string) {
    setPanelRx(rx);
    setPanelInitialTab(initialTab);
  }
  function closePanel() {
    setPanelRx(null);
    setPanelInitialTab(undefined);
  }

  return (
    <motion.div className="space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight">Pharmacy</h1>
            <ShowMeHow only={["dispensing"]} />
          </div>
          <p className="text-sm text-muted-foreground">Prescriptions, dispensing, and returns</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="gap-2" data-tour-id="pharmacy-inventory-link" onClick={() => navigate("/hospital/pharmacy/inventory")}>
            <Boxes className="h-3.5 w-3.5" /> Inventory Workspace
          </Button>
          <Button variant="outline" size="sm" onClick={() => void refetch()} disabled={isFetching} className="gap-2">
            <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} /> Refresh
          </Button>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "Active Rx",         value: activeCount,    icon: <Pill className="h-4 w-4" />,         color: "text-blue-400"   },
          { label: "Pending Dispense",  value: pendingCount,   icon: <ClipboardList className="h-4 w-4" />,color: "text-yellow-400" },
          { label: "Dispensed",         value: dispensedCount, icon: <CheckCircle2 className="h-4 w-4" />, color: "text-green-400"  },
          { label: "Returned",          value: returnedCount,  icon: <Undo2 className="h-4 w-4" />,        color: "text-orange-400" },
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
          <TabsTrigger value="prescriptions" data-tour-id="pharmacy-queue">Prescriptions</TabsTrigger>
          <TabsTrigger value="returns">Returns</TabsTrigger>
        </TabsList>

        {/* ── Prescriptions Tab ─────────────────────────────────────────── */}
        <TabsContent value="prescriptions" className="space-y-4">
          <div className="mt-4 flex flex-wrap gap-2">
            {["active", "all", "pending", "partially_dispensed", "dispensed", "cancelled", "returned"].map(s => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={cn(
                  "rounded-full border px-3 py-1 text-xs capitalize transition-colors",
                  statusFilter === s ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-muted",
                )}
              >{s === "active" ? "To dispense" : s === "all" ? "All" : s.replace(/_/g, " ")}</button>
            ))}
          </div>

          <Card>
            <CardContent className="p-0">
              {isLoading ? (
                <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Rx #</TableHead>
                      <TableHead>Patient</TableHead>
                      <TableHead>Drug</TableHead>
                      <TableHead>Dose / Frequency</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Prescribed</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rxList.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                          <Pill className="mx-auto mb-2 h-6 w-6 opacity-30" />No prescriptions found
                        </TableCell>
                      </TableRow>
                    ) : rxList.map(rx => (
                      <TableRow key={rx.id} onClick={() => openPanel(rx)} className="cursor-pointer hover:bg-muted/50">
                        <TableCell className="font-mono text-xs text-muted-foreground">#{rx.id}</TableCell>
                        <TableCell>
                          <div className="flex flex-col gap-0.5">
                            <span className="text-sm font-medium leading-tight">
                              {rx.patient_name ?? <span className="text-muted-foreground italic text-xs">ID {rx.patient_id}</span>}
                            </span>
                            {rx.patient_mrn && <span className="font-mono text-xs text-muted-foreground">{rx.patient_mrn}</span>}
                          </div>
                        </TableCell>
                        <TableCell className="text-sm font-medium">{rx.drug_name}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{rx.dosage ?? rx.dose} · {rx.frequency}</TableCell>
                        <TableCell><StatusBadge status={rx.status} /></TableCell>
                        <TableCell className="text-xs text-muted-foreground">{elapsed(rx.prescribed_at)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
          <DoneTodayCard title="Dispensed today" whatLabel="Drug" rows={doneRows}
            onOpen={(id) => { const r = doneList.find((x) => x.id === id); if (r) openPanel(r); }} />
        </TabsContent>

        {/* ── Returns (SOR) Tab ──────────────────────────────────────────── */}
        <TabsContent value="returns" className="space-y-4">
          <Card className="mt-4">
            <CardContent className="p-0">
              {returnsLoading ? (
                <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Dispensing #</TableHead>
                      <TableHead>Quantity</TableHead>
                      <TableHead>Reason</TableHead>
                      <TableHead>Restocked</TableHead>
                      <TableHead>Processed By</TableHead>
                      <TableHead>Date</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {returnsList.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                          No returns recorded — record a return from a prescription's Dispense tab.
                        </TableCell>
                      </TableRow>
                    ) : returnsList.map((r: any) => (
                      <TableRow key={r.id}>
                        <TableCell className="font-mono text-xs">{r.dispensing_id}</TableCell>
                        <TableCell className="text-sm font-semibold">{r.quantity_returned}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{r.reason ?? "—"}</TableCell>
                        <TableCell>
                          {r.restocked
                            ? <CheckCircle2 className="h-4 w-4 text-green-400" />
                            : <span className="text-muted-foreground text-xs">—</span>}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">{r.processed_by ?? "—"}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {r.processed_at ? new Date(r.processed_at).toLocaleString() : "—"}
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
          PHARMACY WORKSPACE PANEL — opens inline on row click, no navigation
      ════════════════════════════════════════════════════════════════════ */}
      {panelRx && (
        <PharmacyWorkspacePanel prescription={panelRx} initialTab={panelInitialTab} onClose={closePanel} />
      )}
    </motion.div>
  );
}
