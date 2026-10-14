import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api-client";
import { PhrasePickerDialog, type PhraseGroup } from "./PhrasePickerDialog";

/**
 * Adapter: royan_exam_templates / royan_exam_template_findings -> picker.
 *
 * Two things make this different from NoteTemplatePicker, which is why they
 * are separate adapters rather than one component with flags:
 *
 * 1. VOLUME. 44,405 findings exist — ~2,760 per organ system for Review Of
 *    System. Fetching a system's full set would freeze the panel, so the
 *    server caps at `limit` and we search server-side once the user types.
 *    (This will not reproduce against a small dev stub.)
 *
 * 2. COMPOSITION. Output is grouped per system — "Respiratory: cough,
 *    dyspnoea." — not one phrase per line.
 *
 * Plus the fast path that matches real clinic behaviour: 41,385 ROS findings
 * exist, but a doctor documenting a normal review clicks "Negative" a dozen
 * times. "Mark remaining systems Negative" does that in one action.
 */
export function ExamFindingPicker({
  open,
  onOpenChange,
  category,
  patientSex,
  title,
  onInsert,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  /** "Review Of System" | "Physical Examination" | "HPI" */
  category: string;
  patientSex?: string | null;
  title: string;
  onInsert: (text: string) => void;
}) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [itemQuery, setItemQuery] = useState("");

  const { data: tplData, isLoading: loadingTemplates } = useQuery({
    queryKey: ["exam-templates", category, patientSex ?? ""],
    queryFn: () => api.hospital.clinical.listExamTemplates({ category, patient_sex: patientSex }),
    enabled: open,
    staleTime: 300_000,
  });

  const templates: any[] = tplData?.templates ?? [];

  const { data: findingData, isLoading: loadingFindings } = useQuery({
    queryKey: ["exam-findings", activeId, itemQuery],
    queryFn: () =>
      api.hospital.clinical.listExamFindings(activeId!, {
        q: itemQuery.trim() || undefined,
        limit: 100,
      }),
    enabled: open && !!activeId,
    staleTime: 120_000,
  });

  const groups: PhraseGroup[] = useMemo(
    () =>
      templates.map((t) => ({
        id: String(t.id),
        label: t.organ_system,
        sublabel: t.is_female_only ? "female only" : undefined,
        items:
          String(t.id) === activeId
            ? (findingData?.findings ?? []).map((f: any) => ({
                id: f.id,
                text: f.finding,
                group: t.organ_system,
              }))
            : undefined,
      })),
    [templates, activeId, findingData],
  );

  const markAllNegative = () => {
    const line = templates.map((t) => `${t.organ_system}: Negative.`).join("\n");
    if (line) onInsert(line);
    onOpenChange(false);
  };

  return (
    <PhrasePickerDialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description="Tick findings under each system. Selections compose into one line per system."
      groups={groups}
      activeGroupId={activeId}
      onActiveGroupChange={setActiveId}
      isLoadingGroups={loadingTemplates}
      isLoadingItems={loadingFindings}
      onSearchItems={setItemQuery}
      composeMode="grouped"
      onInsert={onInsert}
      extraActions={
        category === "Review Of System" && templates.length > 0 ? (
          <Button variant="outline" size="sm" className="text-xs" onClick={markAllNegative}>
            All systems Negative
          </Button>
        ) : null
      }
    />
  );
}
