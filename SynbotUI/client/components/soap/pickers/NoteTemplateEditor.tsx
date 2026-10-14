import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { api, type NoteTemplateWrite } from "@/lib/api-client";

/**
 * Create or edit a doctor's own note template.
 *
 * A template is a bundle of phrases, each belonging to one SOAP section, so the
 * editor is four boxes: one line = one tickable phrase in the picker. "??"
 * marks a blank filled in per patient (lib/phrase-template.ts). The section the
 * doctor opened it from comes first, and can start from what they have already
 * written there, which is how most templates actually get made: you notice you
 * typed the same thing twice.
 */

export const TEMPLATE_SECTIONS = [
  { key: "subjective", label: "Subjective", example: "Pain in the ?? knee for ?? days." },
  { key: "objective", label: "Objective", example: "Chest clear, no added sounds." },
  { key: "assessment", label: "Assessment", example: "Uncomplicated malaria." },
  { key: "plan", label: "Plan", example: "Review in ?? weeks with results." },
] as const;

export type TemplateSectionKey = (typeof TEMPLATE_SECTIONS)[number]["key"];

/** Map a picker context (e.g. chief_complaint) onto the editor box it belongs in. */
export function sectionForContext(context: string): TemplateSectionKey {
  return (TEMPLATE_SECTIONS.find((s) => s.key === context)?.key ?? "subjective") as TemplateSectionKey;
}

const EMPTY: Record<TemplateSectionKey, string> = { subjective: "", objective: "", assessment: "", plan: "" };

const toLines = (text: string) =>
  text.split("\n").map((l) => l.trim()).filter(Boolean);

export function NoteTemplateEditor({
  open,
  onOpenChange,
  templateId,
  initialName,
  initialShared,
  initialSection,
  seedText,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  /** Set to edit an existing template; omit to create one. */
  templateId?: string | null;
  initialName?: string;
  initialShared?: boolean;
  initialSection: TemplateSectionKey;
  /** What the doctor has already written in the section that opened this. */
  seedText?: string;
  onSaved?: (id: string) => void;
}) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const editing = !!templateId;

  const [name, setName] = useState("");
  const [shared, setShared] = useState(false);
  const [sections, setSections] = useState<Record<TemplateSectionKey, string>>(EMPTY);
  // Phrases in sections this editor does not show (e.g. chief_complaint on a
  // migrated template). Sent back untouched so saving never drops them.
  const [preserved, setPreserved] = useState<{ context_type: string; text: string }[]>([]);

  const { data: existing, isLoading: loadingExisting } = useQuery({
    queryKey: ["note-template-texts", templateId, "all"],
    queryFn: () => api.hospital.clinical.listNoteTemplateTexts(templateId!),
    enabled: open && editing,
    staleTime: 0,
  });

  useEffect(() => {
    if (!open) return;
    setName(initialName ?? "");
    setShared(initialShared ?? false);
    setSections(EMPTY);
    setPreserved([]);
  }, [open, initialName, initialShared]);

  useEffect(() => {
    if (!open || !editing || !existing) return;
    const next = { ...EMPTY };
    const keep: { context_type: string; text: string }[] = [];
    for (const t of existing.texts ?? []) {
      if (t.context_type in next) {
        const k = t.context_type as TemplateSectionKey;
        next[k] = next[k] ? `${next[k]}\n${t.text}` : t.text;
      } else {
        keep.push({ context_type: t.context_type, text: t.text });
      }
    }
    setSections(next);
    setPreserved(keep);
  }, [open, editing, existing]);

  const ordered = useMemo(
    () => [...TEMPLATE_SECTIONS].sort((a, b) => (a.key === initialSection ? -1 : b.key === initialSection ? 1 : 0)),
    [initialSection],
  );

  const phrases = useMemo(
    () => [
      ...TEMPLATE_SECTIONS.flatMap((s) => toLines(sections[s.key]).map((text) => ({ context_type: s.key, text }))),
      ...preserved,
    ],
    [sections, preserved],
  );

  const save = useMutation({
    mutationFn: () => {
      const body: NoteTemplateWrite = { name: name.trim(), is_shared: shared, phrases };
      return editing
        ? api.hospital.clinical.updateNoteTemplate(templateId!, body)
        : api.hospital.clinical.createNoteTemplate(body);
    },
    onSuccess: (res: any) => {
      queryClient.invalidateQueries({ queryKey: ["note-templates"] });
      queryClient.invalidateQueries({ queryKey: ["note-template-texts"] });
      toast({ title: editing ? "Template updated" : "Template saved", description: `${name.trim()}: ${phrases.length} phrase${phrases.length === 1 ? "" : "s"}.` });
      onSaved?.(String(res?.template?.id ?? res?.id ?? templateId ?? ""));
      onOpenChange(false);
    },
    onError: (err: any) =>
      toast({ title: "Could not save the template", description: err?.message ?? "Please try again.", variant: "destructive" }),
  });

  const canSave = name.trim().length > 0 && phrases.length > 0 && !save.isPending;
  const seedLines = seedText ? toLines(seedText) : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{editing ? "Edit template" : "New template"}</DialogTitle>
          <DialogDescription>
            Write one phrase per line. Each line becomes a phrase you can tick in the template picker. Type{" "}
            <code className="rounded bg-muted px-1">??</code> where a detail changes per patient.
          </DialogDescription>
        </DialogHeader>

        {editing && loadingExisting ? (
          <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading template…
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="note-template-name">Template name</Label>
              <Input
                id="note-template-name"
                data-tour-id="note-template-name"
                value={name}
                maxLength={120}
                placeholder="e.g. Routine antenatal review"
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            <div data-tour-id="note-template-phrases" className="space-y-4">
            {ordered.map((s) => {
              const count = toLines(sections[s.key]).length;
              const isOrigin = s.key === initialSection;
              return (
                <div key={s.key} className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <Label htmlFor={`note-template-${s.key}`}>
                      {s.label}
                      <span className="ml-2 text-xs font-normal text-muted-foreground">
                        {count ? `${count} phrase${count === 1 ? "" : "s"}` : "optional"}
                      </span>
                    </Label>
                    {isOrigin && seedLines.length > 0 && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2 text-xs"
                        data-tour-id="note-template-use-written"
                        onClick={() =>
                          setSections((prev) => ({
                            ...prev,
                            [s.key]: prev[s.key].trim() ? `${prev[s.key]}\n${seedLines.join("\n")}` : seedLines.join("\n"),
                          }))
                        }
                      >
                        Use what I've written in this section
                      </Button>
                    )}
                  </div>
                  <Textarea
                    id={`note-template-${s.key}`}
                    rows={isOrigin ? 5 : 3}
                    value={sections[s.key]}
                    placeholder={s.example}
                    onChange={(e) => setSections((prev) => ({ ...prev, [s.key]: e.target.value }))}
                  />
                </div>
              );
            })}
            </div>

            {preserved.length > 0 && (
              <p className="text-xs text-muted-foreground">
                {preserved.length} other phrase{preserved.length === 1 ? "" : "s"} from this template (chief complaint or
                review of systems) will be kept as they are.
              </p>
            )}

            <div className="flex items-start justify-between gap-4 rounded-md border p-3">
              <div>
                <Label htmlFor="note-template-shared">Share with other doctors</Label>
                <p className="text-xs text-muted-foreground">
                  Off: only you see it. On: every doctor can use it, but only you can change it.
                </p>
              </div>
              <Switch id="note-template-shared" checked={shared} onCheckedChange={setShared} />
            </div>
          </div>
        )}

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button data-tour-id="note-template-save" disabled={!canSave} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {editing ? "Save changes" : "Save template"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
