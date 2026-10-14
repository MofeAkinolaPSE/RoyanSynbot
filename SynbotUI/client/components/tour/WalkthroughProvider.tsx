import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { getWalkthroughById, type Walkthrough } from "@/lib/walkthroughs";
import { WalkthroughPlayer } from "./WalkthroughPlayer";

/**
 * Holds the running walkthrough at app level.
 *
 * This has to live above the router. A walkthrough that moves between pages
 * (Front Desk → the patient chart, say) unmounts whichever page launched it,
 * and if the player were rendered by that page it would die halfway through.
 * Mounting it once at the root is what makes cross-page walkthroughs possible
 * at all, and it is also what lets a walkthrough be minimised and resumed
 * rather than destroyed.
 */

type WalkthroughState = {
  walkthrough: Walkthrough;
  step: number;
  minimised: boolean;
};

type Ctx = {
  active: WalkthroughState | null;
  start: (id: string) => void;
  goToStep: (n: number) => void;
  minimise: () => void;
  resume: () => void;
  stop: () => void;
};

const WalkthroughCtx = createContext<Ctx | null>(null);

export function useWalkthrough(): Ctx {
  const ctx = useContext(WalkthroughCtx);
  if (!ctx) throw new Error("useWalkthrough must be used inside WalkthroughProvider");
  return ctx;
}

export function WalkthroughProvider({ children }: { children: React.ReactNode }) {
  const [active, setActive] = useState<WalkthroughState | null>(null);

  const start = useCallback((id: string) => {
    const w = getWalkthroughById(id);
    if (!w) return;
    setActive({ walkthrough: w, step: 0, minimised: false });
  }, []);

  const goToStep = useCallback((n: number) => {
    setActive((s) => {
      if (!s) return s;
      const clamped = Math.max(0, Math.min(n, s.walkthrough.steps.length - 1));
      return { ...s, step: clamped, minimised: false };
    });
  }, []);

  const minimise = useCallback(() => {
    setActive((s) => (s ? { ...s, minimised: true } : s));
  }, []);

  const resume = useCallback(() => {
    setActive((s) => (s ? { ...s, minimised: false } : s));
  }, []);

  const stop = useCallback(() => setActive(null), []);

  const value = useMemo(
    () => ({ active, start, goToStep, minimise, resume, stop }),
    [active, start, goToStep, minimise, resume, stop],
  );

  return (
    <WalkthroughCtx.Provider value={value}>
      {children}
      {active && <WalkthroughPlayer />}
    </WalkthroughCtx.Provider>
  );
}
