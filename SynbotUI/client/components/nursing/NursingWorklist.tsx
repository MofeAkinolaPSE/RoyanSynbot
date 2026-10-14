import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, NotebookPen } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { fmtDate } from "@/components/nursing/nursing-shared";

/**
 * The full active-encounter worklist with status filtering.
 *
 * Deliberately excludes "discharged" — the only terminal encounter status
 * (ENCOUNTER_STATUS_ALLOWED, backend/src/constants.py). This is a worklist of
 * who needs nursing attention now, not a historical browser.
 *
 * Lifted out of NursingStation during the merge into NurseDashboard. The
 * dashboard's own cards each answer one question ("who is waiting", "who is an
 * inpatient"); this is the one view that shows everybody at once, which is what
 * a nurse taking over a shift actually wants.
 */
const ACTIVE_STATUSES = [
  "patient_registered", "triaged", "nurse_assessment", "called",
  "consulting", "lab_ordered", "awaiting_results", "pharmacy_dispensing", "billing_pending",
];

export function NursingWorklist({
  onOpen,
  onEncountersLoaded,
}: {
  onOpen: (encounter: any, tab?: string) => void;
  /** Lets the parent reuse this list (e.g. to resolve notes) without refetching. */
  onEncountersLoaded?: (encounters: any[]) => void;
}) {
  const [filterStatus, setFilterStatus] = useState("all");

  const { data, isLoading } = useQuery({
    queryKey: ["nursing-worklist", filterStatus],
    queryFn: () =>
      api.hospital.queue.list(
        filterStatus === "all" ? ({ active_only: true } as any) : { status: filterStatus },
      ),
    refetchInterval: 30_000,
  });

  const encounters: any[] = data?.encounters ?? [];

  // In an effect, not during render: calling a parent setter mid-render is how
  // you get an infinite re-render loop.
  useEffect(() => {
    if (onEncountersLoaded) onEncountersLoaded(encounters);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {["all", ...ACTIVE_STATUSES].map((s) => (
          <button
            key={s}
            onClick={() => setFilterStatus(s)}
            className={cn(
              "rounded-full border px-3 py-1 text-xs transition-colors",
              filterStatus === s
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border text-muted-foreground hover:border-primary/50",
            )}
          >
            {s === "all" ? "All Active" : s.replace(/_/g, " ")}
          </button>
        ))}
      </div>

      <Card className="border-border bg-muted/20">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="border-border">
                <TableHead className="text-xs text-muted-foreground">Queue #</TableHead>
                <TableHead className="text-xs text-muted-foreground">Patient</TableHead>
                <TableHead className="text-xs text-muted-foreground">Department</TableHead>
                <TableHead className="text-xs text-muted-foreground">Status</TableHead>
                <TableHead className="hidden text-xs text-muted-foreground sm:table-cell">Chief Complaint</TableHead>
                <TableHead className="text-xs text-muted-foreground">Opened</TableHead>
                <TableHead className="w-[90px] text-xs text-muted-foreground" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                    <Loader2 className="mr-2 inline h-5 w-5 animate-spin" />Loading…
                  </TableCell>
                </TableRow>
              ) : encounters.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                    No active encounters
                  </TableCell>
                </TableRow>
              ) : (
                encounters.map((enc: any) => (
                  <TableRow
                    key={enc.id}
                    className="cursor-pointer border-border/50 hover:bg-muted"
                    onClick={() => onOpen(enc)}
                  >
                    <TableCell className="font-mono text-xs font-semibold text-primary">
                      {enc.queue_number ?? String(enc.id).slice(0, 6)}
                    </TableCell>
                    <TableCell>
                      <div className="text-sm font-medium">{enc.patient_name ?? "Unknown"}</div>
                      <div className="text-xs text-muted-foreground">
                        {[enc.mrn, enc.age_display, enc.gender].filter(Boolean).join(" · ")}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{enc.department ?? "—"}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs capitalize">
                        {enc.status?.replace(/_/g, " ")}
                      </Badge>
                    </TableCell>
                    <TableCell className="hidden max-w-[180px] truncate text-xs text-muted-foreground sm:table-cell">
                      {enc.chief_complaint ?? "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{fmtDate(enc.created_at)}</TableCell>
                    <TableCell className="w-[90px]">
                      {/* Straight into the nursing record, rather than landing on
                          Detail and hunting for the Notes tab. */}
                      <Button
                        size="sm" variant="ghost" className="h-7 gap-1 px-2 text-xs"
                        onClick={(e) => { e.stopPropagation(); onOpen(enc, "notes"); }}
                      >
                        <NotebookPen className="h-3 w-3" /> Notes
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  );
}
