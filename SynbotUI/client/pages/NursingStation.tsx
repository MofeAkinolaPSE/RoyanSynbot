import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { HeartPulse, RefreshCw, Loader2 } from "lucide-react";
import { api } from "@/lib/api-client";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { NursingWorkspacePanel } from "@/components/nursing/NursingWorkspacePanel";
import { fmtDate } from "@/components/nursing/nursing-shared";

// Deliberately excludes "discharged" — the only terminal encounter status
// (ENCOUNTER_STATUS_ALLOWED, backend/src/constants.py). This is a worklist
// of who needs nursing attention right now, not a historical browser.
const ACTIVE_STATUSES = [
  "patient_registered", "triaged", "nurse_assessment", "called",
  "consulting", "lab_ordered", "pharmacy_dispensing", "billing_pending",
];

export default function NursingStation() {
  const [filterStatus, setFilterStatus] = useState("all");
  const [panelEncounter, setPanelEncounter] = useState<any | null>(null);

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["nursing-worklist", filterStatus],
    queryFn: () => api.hospital.queue.list(
      filterStatus === "all" ? ({ active_only: true } as any) : { status: filterStatus }
    ),
    refetchInterval: 30_000,
  });
  const encounters: any[] = data?.encounters ?? [];

  function openPanel(enc: any) {
    // queue_clinical.py's own encounter-enrichment helper names the field
    // `mrn`, not `patient_mrn` like every other department's enrichment —
    // normalize it here so the panel matches the shared prop convention.
    setPanelEncounter({ ...enc, patient_mrn: enc.mrn });
  }

  return (
    <motion.div className="p-6 space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-500/20 rounded-lg">
            <HeartPulse className="w-6 h-6 text-blue-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Nursing Station</h1>
            <p className="text-sm text-muted-foreground">Active encounters — vitals, fluid balance, care plans, MAR</p>
          </div>
        </div>
        <Button variant="outline" size="sm" className="border-border gap-2" onClick={() => refetch()}>
          {isFetching ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} Refresh
        </Button>
      </div>

      <div className="flex gap-2 flex-wrap">
        {["all", ...ACTIVE_STATUSES].map(s => (
          <button key={s}
            onClick={() => setFilterStatus(s)}
            className={cn(
              "px-3 py-1 rounded-full text-xs border transition-colors",
              filterStatus === s
                ? "bg-blue-700 border-blue-600 text-white"
                : "border-border text-muted-foreground hover:border-primary/50"
            )}>
            {s === "all" ? "All Active" : s.replace(/_/g, " ")}
          </button>
        ))}
      </div>

      <Card className="border-border bg-muted/20">
        <Table>
          <TableHeader>
            <TableRow className="border-border">
              <TableHead className="text-muted-foreground text-xs">Queue #</TableHead>
              <TableHead className="text-muted-foreground text-xs">Patient</TableHead>
              <TableHead className="text-muted-foreground text-xs">Department</TableHead>
              <TableHead className="text-muted-foreground text-xs">Status</TableHead>
              <TableHead className="text-muted-foreground text-xs hidden sm:table-cell">Chief Complaint</TableHead>
              <TableHead className="text-muted-foreground text-xs">Opened</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground"><Loader2 className="w-5 h-5 animate-spin inline mr-2" />Loading…</TableCell></TableRow>
            ) : encounters.length === 0 ? (
              <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No active encounters</TableCell></TableRow>
            ) : encounters.map((enc: any) => (
              <TableRow key={enc.id} className="border-border/50 hover:bg-muted cursor-pointer" onClick={() => openPanel(enc)}>
                <TableCell className="font-mono text-xs text-primary font-semibold">{enc.queue_number ?? String(enc.id).slice(0, 6)}</TableCell>
                <TableCell>
                  <div className="text-sm font-medium">{enc.patient_name ?? "Unknown"}</div>
                  {enc.mrn && <div className="text-[12px] font-mono text-muted-foreground">{enc.mrn}</div>}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">{enc.department ?? "—"}</TableCell>
                <TableCell><Badge variant="outline" className="text-[12px] capitalize">{enc.status?.replace(/_/g, " ")}</Badge></TableCell>
                <TableCell className="hidden sm:table-cell text-xs text-muted-foreground max-w-[180px] truncate">{enc.chief_complaint ?? "—"}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{fmtDate(enc.created_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      {panelEncounter && (
        <NursingWorkspacePanel encounter={panelEncounter} onClose={() => setPanelEncounter(null)} />
      )}
    </motion.div>
  );
}
