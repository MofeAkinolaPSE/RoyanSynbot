import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { SectionStatus } from "@/lib/soap-gate";

export const SOAP_SECTIONS = [
  { key: "s", letter: "S", title: "Subjective", hint: "What the patient tells you" },
  { key: "o", letter: "O", title: "Objective", hint: "What you find on examination" },
  { key: "a", letter: "A", title: "Assessment", hint: "Your diagnosis" },
  { key: "p", letter: "P", title: "Plan", hint: "Investigations and treatment" },
] as const;

export type SoapSectionKey = (typeof SOAP_SECTIONS)[number]["key"];

export const SECTION_STATUS_COLORS: Record<SectionStatus, string> = {
  locked: "bg-slate-500/15 text-slate-500 dark:text-slate-400 border-slate-500/25",
  active: "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  complete: "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
};

/** The round S/O/A/P badge used by the stepper and each section header. */
export function SoapLetterBadge({
  letter,
  status,
  className,
}: {
  letter: string;
  status: SectionStatus;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-sm font-semibold",
        SECTION_STATUS_COLORS[status],
        className,
      )}
    >
      {letter}
    </span>
  );
}

export function SectionStatusBadge({ status }: { status: SectionStatus }) {
  const label = status === "complete" ? "Complete" : status === "active" ? "In progress" : "Locked";
  return (
    <Badge variant="outline" className={cn("text-xs", SECTION_STATUS_COLORS[status])}>
      {label}
    </Badge>
  );
}

/** Small uppercase field label, matching the density of the OPD panel. */
export function FieldLabel({
  children,
  required,
  className,
}: {
  children: React.ReactNode;
  required?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground", className)}>
      {children}
      {required && <span className="ml-0.5 text-red-500">*</span>}
    </div>
  );
}
