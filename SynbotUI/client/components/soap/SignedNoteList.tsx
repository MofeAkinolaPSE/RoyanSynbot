import { useState } from "react";
import { FilePlus2, Lock, PenLine } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { summariseSoap } from "@/lib/soap-format";
import { AddendumDialog } from "./AddendumDialog";
import { HelpHint } from "@/components/help/HelpHint";

/**
 * Existing notes for an encounter, with their addenda.
 *
 * Addenda always render immediately beneath the note they correct — a reader
 * must never encounter the original text without the correction attached, or
 * the amendment trail is worse than useless.
 *
 * Signed notes show a lock and offer "Amend"; unsigned ones say so plainly
 * (the backend only signs when the acting user maps to a royan_staff row, so
 * an unsigned note is a real state a clinician can hit).
 */
export function SignedNoteList({
  notes,
  encounterId,
  onChanged,
  className,
  maxHeight = "max-h-48",
}: {
  notes: any[];
  encounterId: string | number;
  onChanged?: () => void;
  className?: string;
  maxHeight?: string;
}) {
  const [amending, setAmending] = useState<any | null>(null);

  if (!notes?.length) return null;

  return (
    <>
      <ScrollArea className={cn("rounded-md border", maxHeight, className)}>
        <div className="divide-y">
          {notes.map((n) => {
            const signed = !!n.signed_at;
            const addenda: any[] = n.addenda ?? [];
            return (
              <div key={n.id} className="p-2 text-xs">
                <div className="mb-1 flex items-start gap-1.5">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-medium">
                        {n.note_title || (n.note_type ? String(n.note_type).replace(/_/g, " ") : "Clinical note")}
                      </span>
                      {signed ? (
                        <Badge variant="outline" className="gap-0.5 border-green-500/30 bg-green-500/15 text-xs text-green-700 dark:text-green-400">
                          <Lock className="h-2.5 w-2.5" /> signed
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="border-amber-500/30 bg-amber-500/15 text-xs text-amber-700 dark:text-amber-400">
                          unsigned
                        </Badge>
                      )}
                      {!signed && (
                        <HelpHint id="note-unsigned" />
                      )}
                      {addenda.length > 0 && (
                        <Badge variant="outline" className="text-xs">
                          {addenda.length} addend{addenda.length === 1 ? "um" : "a"}
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {n.author_name ? `${n.author_name} · ` : ""}
                      {n.created_at ? new Date(n.created_at).toLocaleString() : ""}
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-6 shrink-0 gap-1 px-1.5 text-xs"
                    data-tour-id="note-amend-button"
                    onClick={() => setAmending(n)}
                  >
                    <PenLine className="h-3 w-3" /> Amend
                  </Button>
                </div>

                <p className="whitespace-pre-wrap text-foreground">{summariseSoap(n)}</p>

                {addenda.map((a) => (
                  <div key={a.id} className="mt-1.5 border-l-2 border-amber-500/60 pl-2">
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <FilePlus2 className="h-2.5 w-2.5" />
                      <span className="font-medium">Addendum</span>
                      {a.author_name && <span>· {a.author_name}</span>}
                      {a.created_at && <span>· {new Date(a.created_at).toLocaleString()}</span>}
                    </div>
                    {a.reason && <p className="text-xs italic text-muted-foreground">Reason: {a.reason}</p>}
                    <p className="whitespace-pre-wrap text-xs">{a.content}</p>
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </ScrollArea>

      {amending && (
        <AddendumDialog
          open
          onOpenChange={(v) => !v && setAmending(null)}
          encounterId={encounterId}
          note={amending}
          onAdded={onChanged}
        />
      )}
    </>
  );
}
