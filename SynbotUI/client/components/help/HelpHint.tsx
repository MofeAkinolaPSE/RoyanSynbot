import { HelpCircle, AlertTriangle } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { getHelpHint } from "@/lib/help-hints";
import { cn } from "@/lib/utils";

/**
 * A small "?" beside a control that explains it in place.
 *
 * Popover rather than Tooltip on purpose: a tooltip needs a hover, and a good
 * share of this is read on tablets at a bedside where there is no hover. A tap
 * or a click both work here, and it is keyboard reachable.
 *
 * Unknown ids render nothing rather than an empty bubble, so a hint removed
 * from the registry degrades to silence instead of a dead control.
 */
export function HelpHint({
  id,
  className,
  side = "top",
  align = "start",
}: {
  id: string;
  className?: string;
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
}) {
  const hint = getHelpHint(id);
  if (!hint) return null;

  const Icon = hint.safetyCritical ? AlertTriangle : HelpCircle;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Help: ${hint.title}`}
          onClick={(e) => e.stopPropagation()}
          className={cn(
            "inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full align-middle transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
            hint.safetyCritical
              ? "text-amber-600 hover:text-amber-700 dark:text-amber-500 dark:hover:text-amber-400"
              : "text-muted-foreground/60 hover:text-muted-foreground",
            className,
          )}
        >
          <Icon className="h-3.5 w-3.5" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        side={side}
        align={align}
        className="w-[300px] p-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-2">
          {hint.safetyCritical && (
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-500" />
          )}
          <div className="space-y-1.5">
            <p className="text-xs font-semibold leading-tight">{hint.title}</p>
            <p className="text-xs leading-relaxed text-muted-foreground">{hint.body}</p>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
