import { Check, Lock } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SoapGate } from "@/lib/soap-gate";
import { SOAP_SECTIONS, SECTION_STATUS_COLORS } from "./soap-shared";

/**
 * The S -> O -> A -> P progress rail.
 *
 * Deliberately shows all four at all times, including locked ones. The MD
 * asked for a strict order; a stepper that hides what comes next teaches
 * nothing, whereas a visibly locked step with a reason teaches the rule on
 * first use.
 */
export function SoapProgressStepper({
  gate,
  onJump,
  className,
}: {
  gate: SoapGate;
  onJump?: (key: "s" | "o" | "a" | "p") => void;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-1", className)}>
      {SOAP_SECTIONS.map((section, i) => {
        const state = gate[section.key];
        const clickable = state.status !== "locked" && !!onJump;
        return (
          <div key={section.key} className="flex flex-1 items-center gap-1">
            <button
              type="button"
              disabled={!clickable}
              onClick={() => clickable && onJump?.(section.key)}
              title={state.blockedReason ?? section.title}
              className={cn(
                "flex min-w-0 flex-1 items-center gap-1.5 rounded-md border px-2 py-1 text-left transition-colors",
                SECTION_STATUS_COLORS[state.status],
                clickable ? "cursor-pointer hover:brightness-95" : "cursor-default",
              )}
            >
              <span className="flex h-4 w-4 shrink-0 items-center justify-center">
                {state.status === "complete" ? (
                  <Check className="h-3.5 w-3.5" />
                ) : state.status === "locked" ? (
                  <Lock className="h-3 w-3" />
                ) : (
                  <span className="text-xs font-bold">{section.letter}</span>
                )}
              </span>
              <span className="truncate text-xs font-medium">{section.title}</span>
            </button>
            {i < SOAP_SECTIONS.length - 1 && (
              <span className="h-px w-2 shrink-0 bg-border" aria-hidden />
            )}
          </div>
        );
      })}
    </div>
  );
}
