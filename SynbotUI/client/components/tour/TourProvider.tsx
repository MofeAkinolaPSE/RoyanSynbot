import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { getTourStepsForRole, type TourStep } from "@/lib/tour-config";
import { TourStepContent } from "./TourStep";
import { api } from "@/lib/api-client";

type TourState = { completed?: boolean; skipped?: boolean; current_step?: number };

type TourContextValue = {
  startTourIfNeeded: (role: string, tourState: TourState | null | undefined) => void;
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

  const persist = useCallback((patch: TourState) => {
    void api.staff.updateTourState(patch).catch(() => {
      // Non-fatal — tour progress is a UX nicety, not critical state
    });
  }, []);

  const startTourIfNeeded = useCallback((role: string, tourState: TourState | null | undefined) => {
    if (tourState?.completed || tourState?.skipped) return;
    const roleSteps = getTourStepsForRole(role);
    if (roleSteps.length === 0) return;
    setSteps(roleSteps);
    setStepIndex(Math.min(tourState?.current_step ?? 0, roleSteps.length - 1));
    setOpen(true);
  }, []);

  const finish = useCallback(() => {
    setOpen(false);
    persist({ completed: true, current_step: steps.length });
  }, [persist, steps.length]);

  const skip = useCallback(() => {
    setOpen(false);
    persist({ skipped: true });
  }, [persist]);

  const next = useCallback(() => {
    setStepIndex((i) => {
      const nextIndex = i + 1;
      if (nextIndex >= steps.length) {
        finish();
        return i;
      }
      persist({ current_step: nextIndex });
      return nextIndex;
    });
  }, [steps.length, finish, persist]);

  const back = useCallback(() => {
    setStepIndex((i) => Math.max(0, i - 1));
  }, []);

  const value = useMemo(() => ({ startTourIfNeeded }), [startTourIfNeeded]);
  const currentStep = steps[stepIndex];

  return (
    <TourContext.Provider value={value}>
      {children}
      <Dialog open={open} onOpenChange={(o) => !o && skip()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Welcome — let's get you oriented</DialogTitle>
          </DialogHeader>
          {currentStep && <TourStepContent step={currentStep} index={stepIndex} total={steps.length} />}
          <DialogFooter className="flex-row items-center justify-between sm:justify-between">
            <Button variant="ghost" size="sm" onClick={skip}>Skip tour</Button>
            <div className="flex items-center gap-2">
              {stepIndex > 0 && (
                <Button variant="outline" size="sm" onClick={back}>Back</Button>
              )}
              {currentStep && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => navigate(currentStep.href)}
                >
                  Go to page
                </Button>
              )}
              <Button size="sm" onClick={next}>
                {stepIndex + 1 >= steps.length ? "Finish" : "Next"}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </TourContext.Provider>
  );
}
