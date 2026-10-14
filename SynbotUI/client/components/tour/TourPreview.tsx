import { useState } from "react";
import { GraduationCap, Play, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { useTour } from "./TourProvider";
import { getTourStepsForRole, PREVIEW_ROLES } from "@/lib/tour-config";
import { getWalkthroughsForRole } from "@/lib/walkthroughs";

/**
 * Play any role's onboarding tour on demand, from the admin screen.
 *
 * Without this the only way to see what a new nurse meets on their first login
 * is to create a nurse account and log in as them — which is why nobody checks,
 * and why onboarding content rots unseen.
 *
 * Role is selectable rather than fixed to the viewer, because the useful
 * question is never "what does my tour look like" — an admin already knows.
 * It is "what does the nurse I am about to onboard actually see", and every
 * role sees a genuinely different tour.
 *
 * This runs through the same replay path as "Take the tour again", so previewing
 * never marks a tour complete and never overwrites the admin's own progress.
 */


export function TourPreview() {
  const { startTour } = useTour();
  const [role, setRole] = useState("nurse");

  const essential = getTourStepsForRole(role);
  const full = getTourStepsForRole(role, { full: true });
  const walkthroughs = getWalkthroughsForRole(role);
  const roleLabel = PREVIEW_ROLES.find((r) => r.value === role)?.label ?? role;

  return (
    <div className="pw-surface-interactive space-y-4 rounded-xl p-6">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <GraduationCap className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold text-foreground">Preview onboarding</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Play the first-login tour for any role without creating an account. Nothing is
            recorded — this will not mark the tour complete for you or for anyone else.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[200px] flex-1 space-y-1.5">
          <label htmlFor="tour-preview-role" className="text-xs font-medium text-muted-foreground">
            Role to preview as
          </label>
          <Select value={role} onValueChange={setRole}>
            <SelectTrigger id="tour-preview-role">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PREVIEW_ROLES.map((r) => (
                <SelectItem key={r.value} value={r.value}>
                  {r.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Button
          onClick={() => startTour(role)}
          disabled={essential.length === 0}
          className="gap-1.5"
        >
          <Play className="h-4 w-4" />
          Play first-login tour
        </Button>

        <Button
          variant="outline"
          onClick={() => startTour(role, { full: true })}
          disabled={full.length === 0}
          className="gap-1.5"
        >
          <Eye className="h-4 w-4" />
          Play full tour
        </Button>
      </div>

      {essential.length === 0 ? (
        <p className="text-xs text-amber-600 dark:text-amber-500">
          No tour is configured for {roleLabel}. Staff with only this role see no tour on first
          login.
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="outline" className="font-normal">
            First login: {essential.length} step{essential.length === 1 ? "" : "s"}
          </Badge>
          <Badge variant="outline" className="font-normal">
            Full tour: {full.length} page{full.length === 1 ? "" : "s"}
          </Badge>
          <Badge variant="outline" className="font-normal">
            {walkthroughs.length} task walkthrough{walkthroughs.length === 1 ? "" : "s"}
          </Badge>
          {full.length > essential.length && (
            <span>
              A new {roleLabel.toLowerCase()} meets the short version first; the rest stays
              available from their profile menu.
            </span>
          )}
        </div>
      )}
    </div>
  );
}
