import { useQuery } from "@tanstack/react-query";
import { NotebookPen, Loader2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { HelpHint } from "@/components/help/HelpHint";
import { api } from "@/lib/api-client";
import { fmtDate } from "@/components/nursing/nursing-shared";

/**
 * Ward-wide nursing notes, newest first.
 *
 * Every other note listing in the app is scoped to one patient or one
 * encounter, which answers the wrong question at a nurses' station: the person
 * standing there wants to know what has been written across the ward this
 * shift, not to open patients one at a time to find out.
 *
 * Lifted out of NursingStation during the merge into NurseDashboard so the
 * feed survives the page being retired.
 */
export function RecentNursingNotes({
  encounters,
  onOpenNote,
  limit = 12,
}: {
  /** Used to resolve a note back to a live encounter the panel can open. */
  encounters: any[];
  onOpenNote?: (encounter: any, tab: string) => void;
  limit?: number;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["nursing-recent-notes", limit],
    queryFn: () => api.hospital.clinical.listRecentNotes({ note_type: "nursing", limit }),
    refetchInterval: 60_000,
  });
  const notes: any[] = data?.notes ?? [];

  return (
    <Card className="border-border">
      <CardContent className="p-0">
        <div className="flex items-center gap-2 border-b px-4 py-2.5">
          <NotebookPen className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Recent nursing notes
          </span>
          <HelpHint id="nursing-notes-ungated" />
          <span className="ml-auto text-xs text-muted-foreground">
            {notes.length > 0 ? `${notes.length} most recent` : ""}
          </span>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-6">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : notes.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-muted-foreground">
            No nursing notes written yet. Notes recorded on any patient appear here.
          </p>
        ) : (
          <ul className="divide-y">
            {notes.map((n: any) => {
              // Prefer the live encounter (it carries queue number, department
              // and the rest). Where the encounter has closed, synthesise the
              // minimum the panel needs from the note itself — the panel reads
              // notes PATIENT-scoped, so a closed encounter is no reason to
              // refuse access to that patient's nursing record.
              const enc =
                encounters.find((e: any) => e.id === n.encounter_id) ??
                (n.patient_id
                  ? {
                      id: n.encounter_id,
                      patient_id: n.patient_id,
                      patient_name: n.patient_name,
                      patient_mrn: n.patient_mrn,
                      created_at: n.created_at,
                    }
                  : null);
              return (
                <li key={n.id}>
                  <button
                    onClick={() => enc && onOpenNote?.(enc, "notes")}
                    disabled={!enc || !onOpenNote}
                    className="flex w-full items-start gap-3 px-4 py-2.5 text-left transition-colors hover:bg-muted/50 disabled:cursor-default disabled:hover:bg-transparent"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline gap-x-2">
                        <span className="text-sm font-medium">
                          {n.patient_name ?? `Patient ${n.patient_id}`}
                        </span>
                        {n.patient_mrn && (
                          <span className="font-mono text-xs text-muted-foreground">{n.patient_mrn}</span>
                        )}
                      </div>
                      <p className="line-clamp-2 text-xs text-muted-foreground">
                        {n.content || n.assessment || n.subjective || "—"}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="text-xs text-muted-foreground">{fmtDate(n.created_at)}</div>
                      <div className="text-xs text-muted-foreground">{n.author_name ?? "—"}</div>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
