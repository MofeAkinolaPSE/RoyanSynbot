import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Compass, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getTourStepsForRole, type TourStep } from "@/lib/tour-config";
import { TourStepContent } from "./TourStep";
import { api } from "@/lib/api-client";

type TourState = { completed?: boolean; skipped?: boolean; current_step?: number };

type TourContextValue = {
  /** First-run trigger. Does nothing once the user has completed or skipped. */
  startTourIfNeeded: (role: string, tourState: TourState | null | undefined) => void;
  /**
   * Replay, on demand. Ignores completed/skipped state entirely.
   * `full: true` walks every page the role can see rather than the daily spine.
   */
  startTour: (role: string, opts?: { full?: boolean }) => void;
  /** True when this role has anything to show — lets menus hide a dead entry. */
  hasTour: (role: string) => boolean;
};

const TourContext = createContext<TourContextValue | null>(null);

export function useTour() {
  const ctx = useContext(TourContext);
  if (!ctx) throw new Error("useTour must be used within a TourProvider");
  return ctx;
}

export function TourProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [steps, setSteps] = useState<TourStep[]>([]);
  const [stepIndex, setStepIndex] = useState(0);
  const [open, setOpen] = useState(false);
  // A replay is not the user's first run: it must not overwrite their saved
  // progress, and dismissing it must not re-mark the tour as skipped.
  const [isReplay, setIsReplay] = useState(false);

  const persist = useCallback((patch: TourState) => {
    void api.staff.updateTourState(patch).catch(() => {
      // Non-fatal — tour progress is a UX nicety, not critical state
    });
  }, []);

  const startTourIfNeeded = useCallback((role: string, tourState: TourState | null | undefined) => {
    if (tourState?.completed || tourState?.skipped) return;
    const roleSteps = getTourStepsForRole(role);
    if (roleSteps.length === 0) return;
    setIsReplay(false);
    setSteps(roleSteps);
    setStepIndex(Math.min(tourState?.current_step ?? 0, roleSteps.length - 1));
    setOpen(true);
  }, []);

  /**
   * Deliberately separate from startTourIfNeeded rather than a `force` flag on
   * it: the first-run path resumes saved progress and writes back to it, while
   * a replay always starts at step one and writes nothing. Conflating them
   * would mean someone re-watching the tour silently rewound their own
   * recorded progress.
   */
  const startTour = useCallback((role: string, opts?: { full?: boolean }) => {
    const roleSteps = getTourStepsForRole(role, opts);
    if (roleSteps.length === 0) return;
    setIsReplay(true);
    setSteps(roleSteps);
    setStepIndex(0);
    setOpen(true);
  }, []);

  const hasTour = useCallback(
    (role: string) => getTourStepsForRole(role).length > 0,
    [],
  );

  const finish = useCallback(() => {
    setOpen(false);
    if (!isReplay) persist({ completed: true, current_step: steps.length });
  }, [persist, steps.length, isReplay]);

  const skip = useCallback(() => {
    setOpen(false);
    if (!isReplay) persist({ skipped: true });
  }, [persist, isReplay]);

  const next = useCallback(() => {
    setStepIndex((i) => {
      const nextIndex = i + 1;
      if (nextIndex >= steps.length) {
        finish();
        return i;
      }
      if (!isReplay) persist({ current_step: nextIndex });
      return nextIndex;
    });
  }, [steps.length, finish, persist, isReplay]);

  const back = useCallback(() => {
    setStepIndex((i) => Math.max(0, i - 1));
  }, []);

  const value = useMemo(
    () => ({ startTourIfNeeded, startTour, hasTour }),
    [startTourIfNeeded, startTour, hasTour],
  );
  const currentStep = steps[stepIndex];

  // The tour walks the person's day: each step opens its page behind the card, so they see the real screen while
  // they read what to do on it. The card does not block the page - they can try things as they go.
  const location = useLocation();
  useEffect(() => {
    if (!open || !currentStep) return;
    const here = location.pathname + location.search;
    if (here !== currentStep.href) navigate(currentStep.href);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, stepIndex, currentStep?.href]);

  return (
    <TourContext.Provider value={value}>
      {children}
      {open && currentStep && (
        <div role="dialog" aria-modal="false" aria-label={isReplay ? "Guided tour" : "Welcome tour"}
          className="fixed bottom-4 right-4 z-[60] w-[min(440px,calc(100vw-2rem))] rounded-xl border bg-card p-5 text-card-foreground shadow-2xl">
          <div className="mb-3 flex items-center justify-between gap-2">
            <p className="flex items-center gap-2 text-sm font-semibold">
              <Compass className="h-4 w-4 text-primary" />
              {isReplay ? "Your day in Royan" : "Welcome - here is your day in Royan"}
            </p>
            <button type="button" aria-label="Close the tour" className="rounded p-1 text-muted-foreground hover:bg-muted" onClick={skip}>
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="max-h-[55vh] overflow-y-auto pr-1">
            <TourStepContent step={currentStep} index={stepIndex} total={steps.length} />
          </div>
          <div className="mt-4 flex items-center justify-between gap-2 border-t pt-3">
            <Button variant="ghost" size="sm" onClick={skip}>
              {isReplay ? "Close" : "Skip tour"}
            </Button>
            <div className="flex items-center gap-2">
              {stepIndex > 0 && (
                <Button variant="outline" size="sm" onClick={back}>Back</Button>
              )}
              <Button size="sm" onClick={next}>
                {stepIndex + 1 >= steps.length ? "Finish" : "Next"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </TourContext.Provider>
  );
}
