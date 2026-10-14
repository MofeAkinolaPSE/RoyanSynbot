import { Lock } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SectionState } from "@/lib/soap-gate";
import { SoapLetterBadge, SectionStatusBadge } from "./soap-shared";
import { HelpHint } from "@/components/help/HelpHint";

/**
 * Chrome for one SOAP section: letter badge, title, status, template-button
 * slot, and the lock treatment.
 *
 * A locked section is RENDERED, not hidden — greyed, non-collapsible, with its
 * blockedReason printed inline. Hiding future sections would read as a missing
 * feature; showing them disabled with "Add a chief complaint to continue"
 * teaches the sequence the MD insisted on.
 */
export function SoapSectionShell({
  letter,
  title,
  hint,
  state,
  templateSlot,
  summary,
  expanded,
  onToggle,
  children,
}: {
  letter: string;
  title: string;
  hint?: string;
  state: SectionState;
  templateSlot?: React.ReactNode;
  summary?: React.ReactNode;
  expanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  const locked = state.status === "locked";
  const open = expanded && !locked;

  return (
    <div
      className={cn(
        "rounded-lg border transition-colors",
        locked ? "border-dashed bg-muted/30" : "bg-card",
        state.status === "active" && "border-blue-500/40",
      )}
    >
      <div
        className={cn(
          "flex items-center gap-2 px-3 py-2",
          !locked && "cursor-pointer select-none",
        )}
        onClick={() => !locked && onToggle()}
        role={locked ? undefined : "button"}
        aria-expanded={open}
        aria-disabled={locked}
      >
        <SoapLetterBadge letter={letter} status={state.status} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className={cn("text-sm font-medium", locked && "text-muted-foreground")}>{title}</span>
            {locked && <Lock className="h-3 w-3 text-muted-foreground" />}
            {locked && <HelpHint id="note-locked-section" />}
            <SectionStatusBadge status={state.status} />
          </div>
          {locked ? (
            // The whole point of rendering a locked section: say why.
            <p className="mt-0.5 text-xs text-muted-foreground">{state.blockedReason}</p>
          ) : !open && summary ? (
            <div className="mt-0.5 truncate text-xs text-muted-foreground">{summary}</div>
          ) : hint && open ? (
            <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>
          ) : null}
        </div>
        {!locked && templateSlot && (
          <div onClick={(e) => e.stopPropagation()} className="shrink-0">
            {templateSlot}
          </div>
        )}
      </div>

      {open && <div className="space-y-3 border-t px-3 py-3">{children}</div>}
    </div>
  );
}
