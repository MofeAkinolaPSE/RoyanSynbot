import { CheckCircle2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

/** Midnight today (this computer's clock - Lagos at Royan). Every "done" list starts empty each morning. */
export function startOfToday(): Date {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

export const doneToday = (iso?: string | null) => !!iso && new Date(iso) >= startOfToday();

export type DoneRow = { id: string | number; patient: string; mrn?: string; what: string; by?: string; at?: string | null };

/**
 * The bottom half of every department queue, the same as Queue & Flow's "Recently discharged": whatever was
 * finished today leaves the main list and shows here; tomorrow the list starts clean. Unfinished work is never
 * moved here - it stays on the main list, whatever day it was ordered.
 */
export function DoneTodayCard({ title, rows, whatLabel = "Service", byLabel, onOpen }: {
  title: string; rows: DoneRow[]; whatLabel?: string; byLabel?: string; onOpen?: (id: DoneRow["id"]) => void;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <CheckCircle2 className="h-4 w-4 text-green-600" /> {title} ({rows.length})
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {rows.length === 0 ? (
          <p className="px-4 pb-4 text-sm text-foreground/70">Nothing finished yet today.</p>
        ) : (
          <Table>
            <TableHeader><TableRow>
              <TableHead>Patient</TableHead><TableHead>{whatLabel}</TableHead>{byLabel && <TableHead>{byLabel}</TableHead>}<TableHead>Finished</TableHead>
            </TableRow></TableHeader>
            <TableBody>{rows.map((r) => (
              <TableRow key={r.id} className={onOpen ? "cursor-pointer hover:bg-muted/30" : undefined} onClick={() => onOpen?.(r.id)}>
                <TableCell><div className="text-sm font-medium">{r.patient}</div>{r.mrn && <div className="font-mono text-xs text-foreground/70">{r.mrn}</div>}</TableCell>
                <TableCell className="text-sm">{r.what}</TableCell>
                {byLabel && <TableCell className="text-sm">{r.by ?? "—"}</TableCell>}
                <TableCell className="text-sm">{r.at ? new Date(r.at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : "—"}</TableCell>
              </TableRow>
            ))}</TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
