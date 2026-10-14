import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Loader2, ShieldAlert } from "lucide-react";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api-client";
import { summariseSoap } from "@/lib/soap-format";
import { FieldLabel } from "./soap-shared";

/**
 * Add a correction to a signed clinical note.
 *
 * This is the ONLY way to change what a note says. The original is never
 * rewritten — there is deliberately no PATCH/PUT/DELETE for
 * royan_encounter_notes anywhere in the stack.
 *
 *   "don't alter, no alteration... this is what they are requesting in court.
 *    You can't be changing what you have written four, five years ago."
 *
 * The dialog shows the original above the input so the clinician is amending
 * something they can see, and states plainly that both versions persist.
 */
export function AddendumDialog({
  open,
  onOpenChange,
  encounterId,
  note,
  onAdded,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  encounterId: string | number;
  note: any;
  onAdded?: () => void;
}) {
  const { toast } = useToast();
  const [content, setContent] = useState("");
  const [reason, setReason] = useState("");

  const mut = useMutation({
    mutationFn: () =>
      api.hospital.clinical.addNoteAddendum(encounterId, note.id, {
        content: content.trim(),
        reason: reason.trim() || undefined,
      }),
    onSuccess: () => {
      toast({
        title: "Addendum recorded",
        description: "The original note is unchanged; your correction is appended.",
      });
      setContent("");
      setReason("");
      onAdded?.();
      onOpenChange(false);
    },
    onError: (e: any) =>
      toast({
        title: "Could not record addendum",
        description: e?.message ?? "Please try again.",
        variant: "destructive",
      }),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] flex-col sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add addendum</DialogTitle>
          <DialogDescription>
            Corrections are appended, never applied over the original.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
          <p className="text-amber-800 dark:text-amber-300">
            This note is part of the medical record. Signing an addendum leaves both the original
            text and your correction permanently visible, each with its own author and timestamp.
          </p>
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
          <div>
            <FieldLabel>Original note</FieldLabel>
            <ScrollArea className="max-h-32 rounded-md border bg-muted/30 p-2">
              <p className="whitespace-pre-wrap text-xs text-muted-foreground">
                {summariseSoap(note) || "(no content)"}
              </p>
            </ScrollArea>
            <p className="mt-1 text-xs text-muted-foreground">
              {note.author_name ? `By ${note.author_name} · ` : ""}
              {note.created_at ? new Date(note.created_at).toLocaleString() : ""}
            </p>
          </div>

          <div>
            <FieldLabel>Reason for amendment</FieldLabel>
            <Input
              data-tour-id="addendum-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. transcription error, result received after signing"
              className="h-8 text-xs"
            />
          </div>

          <div>
            <FieldLabel required>Correction</FieldLabel>
            <Textarea
              rows={5}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="State what is being corrected or added…"
              className="text-xs"
            />
          </div>
        </div>

        <DialogFooter className="shrink-0">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={() => mut.mutate()} disabled={!content.trim() || mut.isPending}>
            {mut.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            Sign addendum
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
