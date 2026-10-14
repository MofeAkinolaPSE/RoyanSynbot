import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api-client";
import { PhrasePickerDialog, type PhraseGroup } from "./PhrasePickerDialog";
import { NoteTemplateEditor, sectionForContext } from "./NoteTemplateEditor";

const RECENT_KEY = "synbot_recent_note_templates";
const RECENT_MAX = 5;

function readRecent(context: string): string[] {
  try {
    const raw = window.localStorage.getItem(`${RECENT_KEY}:${context}`);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

function pushRecent(context: string, id: string) {
  try {
    const next = [id, ...readRecent(context).filter((x) => x !== id)].slice(0, RECENT_MAX);
    window.localStorage.setItem(`${RECENT_KEY}:${context}`, JSON.stringify(next));
  } catch {
    /* private mode — recents are a convenience, not a requirement */
  }
}

/**
 * Adapter: royan_note_templates / royan_note_template_texts -> PhrasePickerDialog.
 *
 * The crux of the per-section design: the SAME template yields different
 * phrases depending on which SOAP button opened it. "SK/AK/SQ Cancer" opened
 * from Assessment shows only its assessment phrases; opened from Plan, only
 * its plan phrases. contextTypes drives both the template list and the phrase
 * fetch, so a template with nothing for this section never even appears.
 *
 * Ordering is the doctor's own first, then shared/system — the MD keeps his own
 * daily templates and rejected the generic ones as "too detailed for me".
 * "New template" writes one; Edit/Delete appear only on templates the doctor
 * owns (is_mine, decided by the server).
 */
export function NoteTemplatePicker({
  open,
  onOpenChange,
  contextTypes,
  title,
  onInsert,
  seedText,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  /** Section context(s). First entry is the primary fetch key. */
  contextTypes: string[];
  title: string;
  onInsert: (text: string) => void;
  /** The text already in the note section, offered as a starting point for a new template. */
  seedText?: string;
}) {
  const primaryContext = contextTypes[0] ?? "general";
  const [activeId, setActiveId] = useState<string | null>(null);
  const [editor, setEditor] = useState<null | { id?: string; name?: string; shared?: boolean }>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const { data: tplData, isLoading: loadingTemplates } = useQuery({
    queryKey: ["note-templates", primaryContext],
    queryFn: () => api.hospital.clinical.listNoteTemplates({ context_type: primaryContext }),
    enabled: open,
    staleTime: 300_000,
  });

  const templates: any[] = tplData?.templates ?? [];

  const { data: textData, isLoading: loadingTexts } = useQuery({
    queryKey: ["note-template-texts", activeId, primaryContext],
    queryFn: () => api.hospital.clinical.listNoteTemplateTexts(activeId!, primaryContext),
    enabled: open && !!activeId,
    staleTime: 300_000,
  });

  const groups: PhraseGroup[] = useMemo(() => {
    const recent = readRecent(primaryContext);
    const decorated = templates.map((t) => ({
      id: String(t.id),
      label: t.name,
      sublabel: t.category ?? undefined,
      // "Yours" = you own it; "shared" = a colleague's own template they share.
      tag: t.is_mine ? "Yours" : t.scope === "personal" ? "shared" : undefined,
      _recentIdx: recent.indexOf(String(t.id)),
      _personal: !!t.is_mine,
    }));

    decorated.sort((a, b) => {
      // Recently used first, then your own, then alphabetical.
      const aR = a._recentIdx === -1 ? 999 : a._recentIdx;
      const bR = b._recentIdx === -1 ? 999 : b._recentIdx;
      if (aR !== bR) return aR - bR;
      if (a._personal !== b._personal) return a._personal ? -1 : 1;
      return a.label.localeCompare(b.label);
    });

    return decorated.map(({ _recentIdx, _personal, ...g }) => ({
      ...g,
      items:
        g.id === activeId
          ? (textData?.texts ?? []).map((x: any) => ({ id: x.id, text: x.text }))
          : undefined,
    }));
  }, [templates, activeId, textData, primaryContext]);

  const active = templates.find((t) => String(t.id) === activeId);

  const remove = useMutation({
    mutationFn: () => api.hospital.clinical.deleteNoteTemplate(activeId!),
    onSuccess: () => {
      toast({ title: "Template deleted", description: active?.name });
      setActiveId(null);
      queryClient.invalidateQueries({ queryKey: ["note-templates"] });
    },
    onError: (err: any) =>
      toast({ title: "Could not delete the template", description: err?.message, variant: "destructive" }),
  });

  const extraActions = (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="gap-1"
        data-tour-id="note-template-new"
        onClick={() => setEditor({})}
      >
        <Plus className="h-3.5 w-3.5" /> New template
      </Button>
      {active?.is_mine && (
        <>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="gap-1"
            onClick={() => setEditor({ id: String(active.id), name: active.name, shared: !!active.is_shared })}
          >
            <Pencil className="h-3.5 w-3.5" /> Edit
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="gap-1 text-destructive hover:text-destructive"
            onClick={() => setConfirmDelete(true)}
          >
            <Trash2 className="h-3.5 w-3.5" /> Delete
          </Button>
        </>
      )}
    </>
  );

  return (
    <>
    <PhrasePickerDialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description="Pick a template, tick the phrases that apply, then fill in any blanks for this patient."
      groups={groups}
      activeGroupId={activeId}
      onActiveGroupChange={(id) => {
        setActiveId(id);
        pushRecent(primaryContext, id);
      }}
      isLoadingGroups={loadingTemplates}
      isLoadingItems={loadingTexts}
      composeMode="lines"
      onInsert={onInsert}
      extraActions={extraActions}
    />

    <NoteTemplateEditor
      open={!!editor}
      onOpenChange={(v) => !v && setEditor(null)}
      templateId={editor?.id ?? null}
      initialName={editor?.name}
      initialShared={editor?.shared}
      initialSection={sectionForContext(primaryContext)}
      seedText={editor?.id ? undefined : seedText}
      onSaved={(id) => id && setActiveId(id)}
    />

    <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete "{active?.name}"?</AlertDialogTitle>
          <AlertDialogDescription>
            It disappears from your template list{active?.is_shared ? " and from other doctors' lists" : ""}. Notes
            already written with it are not changed.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={() => remove.mutate()}>Delete</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
    </>
  );
}
