import { GraduationCap, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/components/AuthProvider";
import { getWalkthroughsForRoles, type Walkthrough } from "@/lib/walkthroughs";
import { useWalkthrough } from "./WalkthroughProvider";

/**
 * "Show me how" — the on-demand entry point to a task walkthrough.
 *
 * Placed on the page it teaches rather than fired on first login: the moment
 * someone actually needs to know how the SOAP note works is when they are
 * looking at one, not on their first morning while a patient waits.
 *
 * `only` narrows to specific walkthroughs for a given screen; omit it to offer
 * everything available to that role.
 */
export function ShowMeHow({
  only,
  label = "Show me how",
  className,
}: {
  only?: string[];
  label?: string;
  className?: string;
}) {
  const { roles } = useAuth();
  const { start: startWalkthrough } = useWalkthrough();

  // every walkthrough any of the person's roles may use (a chief with every role sees them all)
  let available = getWalkthroughsForRoles(roles?.length ? roles : ["admin"]);
  if (only?.length) available = available.filter((w) => only.includes(w.id));

  if (available.length === 0) return null;

  const start = (w: Walkthrough) => startWalkthrough(w.id);

  return (
    <>
      {available.length === 1 ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className={className ?? "h-7 gap-1.5 px-2 text-xs text-muted-foreground"}
          onClick={() => start(available[0])}
        >
          <GraduationCap className="h-3.5 w-3.5" />
          {label}
        </Button>
      ) : (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className={className ?? "h-7 gap-1.5 px-2 text-xs text-muted-foreground"}
            >
              <GraduationCap className="h-3.5 w-3.5" />
              {label}
              <ChevronDown className="h-3 w-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-72">
            {available.map((w) => (
              <DropdownMenuItem
                key={w.id}
                onClick={() => start(w)}
                className="flex flex-col items-start gap-0.5 py-2"
              >
                <span className="text-xs font-medium">{w.title}</span>
                <span className="text-xs text-muted-foreground">{w.summary}</span>
                <span className="text-xs text-muted-foreground">
                  {w.estMinutes} min · {w.steps.length} steps
                </span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}

    </>
  );
}
