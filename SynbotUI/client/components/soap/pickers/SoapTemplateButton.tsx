import { useState } from "react";
import { FileText, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { NoteTemplatePicker } from "./NoteTemplatePicker";
import { ExamFindingPicker } from "./ExamFindingPicker";

export type TemplateSource = "note" | "exam-ros" | "exam-pe" | "exam-hpi";

const SOURCE_LABEL: Record<TemplateSource, string> = {
  note: "Note templates",
  "exam-ros": "Review of systems",
  "exam-pe": "Physical examination",
  "exam-hpi": "History templates",
};

const EXAM_CATEGORY: Record<string, string> = {
  "exam-ros": "Review Of System",
  "exam-pe": "Physical Examination",
  "exam-hpi": "HPI",
};

/**
 * The per-section "Template" button — the thing the MD asked for by name:
 * "There's a template for each points in the notes. Template for S, O, A, P."
 *
 * One source renders a plain button. Two or more render a dropdown, because
 * Objective legitimately wants both physical-exam findings and note-template
 * prose, and forcing them into one list would mix short tickable findings with
 * full paragraphs.
 */
export function SoapTemplateButton({
  sources,
  contextTypes,
  patientSex,
  onInsert,
  label = "Template",
  disabled,
  currentText,
}: {
  sources: TemplateSource[];
  /** For the "note" source: which context_type(s) this section wants. */
  contextTypes?: string[];
  patientSex?: string | null;
  onInsert: (text: string) => void;
  label?: string;
  disabled?: boolean;
  /** What is already written in this section; offered when saving a new template. */
  currentText?: string;
}) {
  const [openSource, setOpenSource] = useState<TemplateSource | null>(null);

  const trigger =
    sources.length === 1 ? (
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-6 gap-1 px-2 text-xs"
        disabled={disabled}
        onClick={() => setOpenSource(sources[0])}
      >
        <FileText className="h-3 w-3" />
        {label}
      </Button>
    ) : (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="outline" size="sm" className="h-6 gap-1 px-2 text-xs" disabled={disabled}>
            <FileText className="h-3 w-3" />
            {label}
            <ChevronDown className="h-3 w-3" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {sources.map((s) => (
            <DropdownMenuItem key={s} className="text-xs" onClick={() => setOpenSource(s)}>
              {SOURCE_LABEL[s]}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    );

  const close = () => setOpenSource(null);

  return (
    <>
      {trigger}

      {openSource === "note" && (
        <NoteTemplatePicker
          open
          onOpenChange={(v) => !v && close()}
          contextTypes={contextTypes ?? ["general"]}
          title={label === "Template" ? "Insert from template" : label}
          seedText={currentText}
          onInsert={(t) => {
            onInsert(t);
            close();
          }}
        />
      )}

      {openSource && openSource !== "note" && (
        <ExamFindingPicker
          open
          onOpenChange={(v) => !v && close()}
          category={EXAM_CATEGORY[openSource]}
          patientSex={patientSex}
          title={SOURCE_LABEL[openSource]}
          onInsert={(t) => {
            onInsert(t);
            close();
          }}
        />
      )}
    </>
  );
}
