import { Stethoscope, HeartPulse } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * The two ways to write on a patient, kept visibly apart.
 *
 * A doctor's note and a nurse's note are different records with different rules,
 * and until now both queues offered one undifferentiated "Workspace" button that
 * happened to open whichever panel the page had wired:
 *
 *   DOCTOR  -> SOAP note. Strict S→O→A→P gating, requires a structured
 *              diagnosis, signs and locks permanently, corrections only by
 *              addendum. note_type 'soap'.
 *   NURSE   -> Nursing note. Deliberately UNGATED — an observation must not be
 *              held hostage to a diagnosis — free text, same signing and
 *              addendum rules. note_type 'nursing'.
 *
 * Writing an observation into a doctor's SOAP note, or a consultation into the
 * nursing record, misfiles it in a record that is read years later. So the two
 * buttons never share a colour, an icon or a word.
 *
 * BOTH are always shown, whatever the viewer's role. A doctor legitimately reads
 * the nursing record and a nurse reads the consultation; hiding one would answer
 * "who is looking" when the real question is "which record is this".
 */
export function NoteEntryButtons({
  onDoctorNote,
  onNurseNote,
  size = "sm",
  className,
  compact = false,
}: {
  onDoctorNote: () => void;
  onNurseNote: () => void;
  size?: "sm" | "default";
  className?: string;
  /** Icons only, for a crowded table row. */
  compact?: boolean;
}) {
  return (
    <div className={cn("flex flex-wrap gap-1", className)}>
      <Button
        size={size}
        variant="outline"
        title="Doctor's consultation note — SOAP, signs and locks"
        aria-label="Add doctor note"
        className={cn(
          "gap-1 border-blue-500/40 text-blue-700 hover:bg-blue-500/10 dark:text-blue-400",
          size === "sm" && "h-7 px-2 text-xs",
        )}
        onClick={(e) => { e.stopPropagation(); onDoctorNote(); }}
      >
        <Stethoscope className="h-3 w-3" />
        {compact ? "Dr" : "Doctor note"}
      </Button>

      <Button
        size={size}
        variant="outline"
        title="Nursing note — free text, not gated on a diagnosis"
        aria-label="Add nurse note"
        className={cn(
          "gap-1 border-teal-500/40 text-teal-700 hover:bg-teal-500/10 dark:text-teal-400",
          size === "sm" && "h-7 px-2 text-xs",
        )}
        onClick={(e) => { e.stopPropagation(); onNurseNote(); }}
      >
        <HeartPulse className="h-3 w-3" />
        {compact ? "Nurse" : "Nurse note"}
      </Button>
    </div>
  );
}
