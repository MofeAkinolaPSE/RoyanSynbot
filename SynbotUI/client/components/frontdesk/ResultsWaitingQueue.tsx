import { useQuery } from "@tanstack/react-query";
import { FlaskConical, Loader2, ChevronRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";

/**
 * Patients whose results are back but who have not been seen again yet.
 *
 * Asked for directly: "if a patient is just waiting for a test result, let's
 * move them from the main queue and move them to the queue for lab reviews, so
 * they can just wait and then get their result review."
 *
 * The point is that these patients should NOT be re-queued from scratch. They
 * already saw the doctor; they are waiting on one thing. Keeping them in the
 * main queue makes the queue look longer than the real waiting workload and
 * pushes genuinely-new patients down.
 *
 * `awaiting_results` is set automatically when the last outstanding lab on an
 * encounter is resulted (see lab.py `_advance_encounter_after_result`).
 */

function waited(since?: string): string {
  if (!since) return "—";
  const mins = Math.round((Date.now() - new Date(since).getTime()) / 60000);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

export function ResultsWaitingQueue({
  onOpenPatient,
}: {
  /** Called with the encounter row, so the caller decides how to open it. */
  onOpenPatient?: (encounter: any) => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["queue", "awaiting_results"],
    queryFn: () => api.hospital.queue.list({ status: "awaiting_results" }),
    refetchInterval: 30_000,
  });

  const rows: any[] = data?.encounters ?? [];

  return (
    <Card className={cn(rows.length > 0 && "border-teal-500/40")}>
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-2">
        <FlaskConical className="h-4 w-4 text-teal-600 dark:text-teal-400" />
        <CardTitle className="text-sm">Waiting for result review</CardTitle>
        {rows.length > 0 && (
          <Badge variant="outline" className="border-teal-500/40 bg-teal-500/10 text-teal-700 dark:text-teal-300">
            {rows.length}
          </Badge>
        )}
      </CardHeader>

      <CardContent className="p-0">
        {isLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : rows.length === 0 ? (
          <p className="px-5 py-6 text-center text-xs text-muted-foreground">
            Nobody is waiting on a result. Patients appear here automatically once
            every test they are waiting for has been resulted.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="whitespace-nowrap">Queue #</TableHead>
                  <TableHead className="whitespace-nowrap">Patient</TableHead>
                  <TableHead className="whitespace-nowrap">Payer</TableHead>
                  <TableHead className="whitespace-nowrap">Results</TableHead>
                  <TableHead className="whitespace-nowrap">Waiting</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((enc) => (
                  <TableRow
                    key={enc.id}
                    onClick={() => onOpenPatient?.(enc)}
                    className={cn("border-l-2 border-l-teal-500/60", onOpenPatient && "cursor-pointer hover:bg-muted/40")}
                  >
                    <TableCell className="font-mono text-xs font-bold text-primary">
                      {enc.queue_number ?? String(enc.id).slice(0, 8)}
                    </TableCell>

                    <TableCell className="whitespace-nowrap">
                      <div className="text-sm leading-tight">{enc.patient_name ?? enc.mrn ?? "—"}</div>
                      {(enc.age_display || enc.gender) && (
                        <div className="text-xs text-muted-foreground">
                          {[enc.age_display, enc.gender].filter(Boolean).join(" · ")}
                        </div>
                      )}
                    </TableCell>

                    <TableCell className="whitespace-nowrap">
                      {enc.payer_type === "hmo" || enc.hmo_provider ? (
                        <>
                          <Badge variant="outline" className="text-xs whitespace-nowrap">
                            {enc.insurance?.hmo_name ?? enc.hmo_provider ?? "HMO"}
                          </Badge>
                          {enc.insurance?.membership_id && (
                            <div className="mt-0.5 font-mono text-xs text-muted-foreground">
                              {enc.insurance.membership_id}
                            </div>
                          )}
                        </>
                      ) : (
                        <span className="text-xs text-muted-foreground">Private</span>
                      )}
                    </TableCell>

                    <TableCell className="whitespace-nowrap text-xs">
                      {enc.lab_resulted_count ?? 0} of {enc.lab_order_count ?? 0} back
                    </TableCell>

                    {/* Time since the encounter opened, which is what the patient
                        has actually been in the building for. */}
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {waited(enc.created_at)}
                    </TableCell>

                    <TableCell className="w-8">
                      {onOpenPatient && <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
