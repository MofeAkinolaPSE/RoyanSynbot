import { useQuery } from "@tanstack/react-query";
import { BedDouble, Loader2, AlertTriangle, Receipt } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { NoteEntryButtons } from "@/components/shared/NoteEntryButtons";

/**
 * The IPD queue — everyone currently in a bed.
 *
 * Built to the same shape as the OPD queue so staff can switch between them
 * without relearning the screen, but the columns answer inpatient questions:
 * where the patient is, how long they have been there, and what the stay has
 * cost so far.
 *
 * "an inpatient" means occupying a bed, not encounter_type = 'inpatient'. That
 * field records what was INTENDED at registration and is never corrected, so an
 * outpatient admitted after a bad result would be missing from this list and a
 * patient who went home would still be on it. Bed occupancy is the fact on the
 * ground, and it is the same fact that drives the room charge — so the queue and
 * the bill cannot disagree about who is admitted.
 */
const naira = (v: any) => `₦${Number(v ?? 0).toLocaleString()}`;

export function InpatientQueue({
  onOpen,
  onDoctorNote,
  onNurseNote,
}: {
  onOpen: (row: any) => void;
  /** Consultation note — SOAP, gated, signs and locks. */
  onDoctorNote?: (row: any) => void;
  /** Nursing note — free text, not gated on a diagnosis. */
  onNurseNote?: (row: any) => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["inpatient-queue"],
    queryFn: () => api.hospital.queue.listInpatients(),
    refetchInterval: 30_000,
  });

  const rows: any[] = data?.inpatients ?? [];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className="gap-1.5">
          <BedDouble className="h-3 w-3" /> {rows.length} admitted
        </Badge>
        {Number(data?.running_total) > 0 && (
          <Badge variant="outline" className="gap-1.5 tabular-nums">
            <Receipt className="h-3 w-3" /> {naira(data.running_total)} accrued
          </Badge>
        )}
        {Number(data?.unpriced) > 0 && (
          <Badge variant="outline" className="border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400">
            {data.unpriced} in an unpriced ward
          </Badge>
        )}
        {Number(data?.stale_beds) > 0 && (
          <Badge variant="outline" className="border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-400">
            {data.stale_beds} bed{data.stale_beds === 1 ? "" : "s"} held after discharge
          </Badge>
        )}
      </div>

      <Card className="border-border bg-muted/20">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="whitespace-nowrap">Location</TableHead>
                <TableHead className="whitespace-nowrap">Patient</TableHead>
                <TableHead className="whitespace-nowrap">Payer</TableHead>
                <TableHead className="whitespace-nowrap">Admitted</TableHead>
                <TableHead className="whitespace-nowrap">Stay</TableHead>
                <TableHead className="whitespace-nowrap">Running bill</TableHead>
                <TableHead className="whitespace-nowrap">Status</TableHead>
                <TableHead className="whitespace-nowrap">Notes</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={8} className="py-8 text-center text-muted-foreground">
                    <Loader2 className="mr-2 inline h-5 w-5 animate-spin" />Loading…
                  </TableCell>
                </TableRow>
              ) : rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="py-8 text-center text-muted-foreground">
                    Nobody is currently admitted. Patients appear here as soon as a nurse
                    places them in a bed.
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((r) => (
                  <TableRow
                    key={r.bed_id}
                    onClick={() => onOpen(r)}
                    className={cn(
                      "cursor-pointer border-l-2 hover:bg-muted/50",
                      r.encounter_closed ? "border-l-red-500" : "border-l-primary/40",
                    )}
                  >
                    <TableCell className="whitespace-nowrap">
                      <div className="text-sm font-medium">{r.room_name ?? r.ward_name ?? "—"}</div>
                      <div className="text-xs text-muted-foreground">
                        {r.ward_name && r.room_name ? `${r.ward_name} · ` : ""}bed {r.bed_number}
                      </div>
                    </TableCell>

                    <TableCell className="whitespace-nowrap">
                      <div className="text-sm leading-tight">{r.patient_name ?? "—"}</div>
                      <div className="text-xs text-muted-foreground">
                        {[r.mrn, r.age_display, r.gender].filter(Boolean).join(" · ")}
                      </div>
                    </TableCell>

                    <TableCell className="whitespace-nowrap">
                      {r.payer_type === "hmo" ? (
                        <>
                          <Badge variant="outline" className="text-xs">HMO</Badge>
                          {r.membership_id && (
                            <div className="mt-0.5 font-mono text-xs text-muted-foreground">
                              {r.membership_id}
                            </div>
                          )}
                        </>
                      ) : (
                        <span className="text-xs text-muted-foreground">Private</span>
                      )}
                    </TableCell>

                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {r.admitted_at ? new Date(r.admitted_at).toLocaleDateString() : "—"}
                    </TableCell>

                    <TableCell className="whitespace-nowrap text-xs">
                      {r.nights} night{r.nights === 1 ? "" : "s"}
                    </TableCell>

                    <TableCell className="whitespace-nowrap">
                      <div className="text-sm font-medium tabular-nums">{naira(r.running_total)}</div>
                      {r.needs_rate ? (
                        <div className="flex items-center gap-1 text-xs text-amber-600">
                          <AlertTriangle className="h-3 w-3" /> bed not priced
                        </div>
                      ) : (
                        <div className="text-xs text-muted-foreground tabular-nums">
                          {naira(r.daily_rate)}/night
                          {Number(r.other_charges) > 0 && ` + ${naira(r.other_charges)}`}
                        </div>
                      )}
                    </TableCell>

                    <TableCell className="whitespace-nowrap">
                      {r.encounter_closed ? (
                        <Badge variant="outline" className="border-red-500/40 bg-red-500/10 text-xs text-red-700 dark:text-red-400">
                          discharged — bed still held
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-xs capitalize">
                          {String(r.status ?? "admitted").replace(/_/g, " ")}
                        </Badge>
                      )}
                    </TableCell>

                    {/* An admitted patient is written on by both, all day. The
                        two records must never be one button. */}
                    <TableCell className="whitespace-nowrap">
                      {(onDoctorNote || onNurseNote) && (
                        <NoteEntryButtons
                          compact
                          onDoctorNote={() => onDoctorNote?.(r)}
                          onNurseNote={() => onNurseNote?.(r)}
                        />
                      )}
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
