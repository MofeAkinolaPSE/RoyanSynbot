import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import {
  ChevronLeft, ChevronRight, GraduationCap, X, Minus, MousePointerClick,
  Eye, AlertTriangle, List, Check, ArrowDown, ArrowUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useWalkthrough } from "./WalkthroughProvider";

type Rect = { top: number; left: number; width: number; height: number };

const PAD = 8;
const CARD_W = 420;
const GAP = 16;

function findAnchor(id?: string): HTMLElement | null {
  if (!id) return null;
  return document.querySelector<HTMLElement>(`[data-tour-id="${id}"]`);
}

/**
 * Plays a task walkthrough over the live page.
 *
 * The spotlight is a real cut-out: four dimmed panels are drawn AROUND the
 * target, so nothing is painted on top of it. That is what makes the target
 * both fully legible and genuinely clickable — an overlay covering the whole
 * screen, however transparent, would swallow the very click the step is asking
 * for.
 *
 * The dim never blocks the page. Panels are pointer-events:none, so scrolling,
 * opening a tab and clicking anywhere all keep working while the walkthrough
 * runs. It guides; it does not trap.
 *
 * Steps marked action:"click" advance when the learner actually presses the
 * highlighted control, so the walkthrough is driven by doing. Steps marked
 * caution are controls that commit something irreversible — those stay
 * observe-only and say so, because staff rehearse against live clinical data.
 */
export function WalkthroughPlayer() {
  const navigate = useNavigate();
  const { active, goToStep, minimise, resume, stop } = useWalkthrough();
  const [rect, setRect] = useState<Rect | null>(null);
  const [showSteps, setShowSteps] = useState(false);
  const [nudge, setNudge] = useState(0);
  const lastNavigated = useRef<string | null>(null);

  const walkthrough = active?.walkthrough;
  const i = active?.step ?? 0;
  const step = walkthrough?.steps[i];
  const isLast = walkthrough ? i === walkthrough.steps.length - 1 : false;
  const wantsClick = step?.action === "click" && !!step.anchor;

  const next = useCallback(() => {
    if (!walkthrough) return;
    if (i >= walkthrough.steps.length - 1) stop();
    else goToStep(i + 1);
  }, [walkthrough, i, goToStep, stop]);

  // Route moves are per step. Guarded so re-measuring cannot re-navigate and
  // fight a user who has since moved somewhere else deliberately.
  useEffect(() => {
    if (!step?.navigateTo) {
      lastNavigated.current = null;
      return;
    }
    const key = `${i}:${step.navigateTo}`;
    if (lastNavigated.current === key) return;
    lastNavigated.current = key;
    navigate(step.navigateTo);
  }, [step, i, navigate]);

  // Measure after paint, and keep tracking: the target moves when the page
  // scrolls, a tab opens, or a dialog pushes layout around.
  useLayoutEffect(() => {
    if (!active || active.minimised) return;
    let raf = 0;
    let settled = false;

    const measure = (scrollIntoView = false) => {
      const el = findAnchor(step?.anchor);
      if (!el) {
        setRect(null);
        return;
      }
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) {
        setRect(null);
        return;
      }
      setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
      if (scrollIntoView && !settled) {
        settled = true;
        const fullyVisible = r.top >= 80 && r.bottom <= window.innerHeight - 80;
        if (!fullyVisible) el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    };

    raf = requestAnimationFrame(() => measure(true));
    // Late mounts (a tab panel, a dialog) would otherwise measure as absent.
    const retries = [200, 500, 900].map((ms) => setTimeout(() => measure(true), ms));
    const track = () => measure(false);
    window.addEventListener("resize", track);
    window.addEventListener("scroll", track, true);
    const poll = setInterval(track, 400);

    return () => {
      cancelAnimationFrame(raf);
      retries.forEach(clearTimeout);
      clearInterval(poll);
      window.removeEventListener("resize", track);
      window.removeEventListener("scroll", track, true);
    };
  }, [step, active]);

  // Learn by doing: a "click" step completes when the real control is pressed.
  useEffect(() => {
    if (!wantsClick || !active || active.minimised) return;
    const el = findAnchor(step?.anchor);
    if (!el) return;
    const onClick = () => setTimeout(next, 260); // let the UI react first
    el.addEventListener("click", onClick);
    return () => el.removeEventListener("click", onClick);
  }, [wantsClick, step, active, next]);

  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") active.minimised ? stop() : minimise();
      else if (e.key === "ArrowRight") next();
      else if (e.key === "ArrowLeft") goToStep(i - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, i, next, goToStep, minimise, stop]);

  if (!active || !walkthrough || !step) return null;

  // ── Minimised: a resumable pill, so closing does not throw away progress ──
  if (active.minimised) {
    return createPortal(
      <div className="fixed bottom-4 right-4 z-[120] flex items-center gap-2 rounded-full border bg-background/95 py-1.5 pl-3 pr-1.5 shadow-lg backdrop-blur animate-in slide-in-from-bottom-2">
        <GraduationCap className="h-4 w-4 text-primary" />
        <div className="text-xs">
          <span className="font-medium">{walkthrough.title}</span>
          <span className="ml-1.5 text-muted-foreground">
            {i + 1}/{walkthrough.steps.length}
          </span>
        </div>
        <Button size="sm" className="h-6 px-2 text-xs" onClick={resume}>
          Resume
        </Button>
        <button
          onClick={stop}
          aria-label="End walkthrough"
          className="rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>,
      document.body,
    );
  }

  const spot = rect
    ? { top: rect.top - PAD, left: rect.left - PAD, width: rect.width + PAD * 2, height: rect.height + PAD * 2 }
    : null;

  const accent = step.caution ? "amber" : "primary";
  const ringColor = step.caution ? "rgb(245 158 11)" : "hsl(var(--primary))";

  // Place the card beside the target when there is room, otherwise above or
  // below it. Never let it cover the thing it is pointing at.
  let cardStyle: React.CSSProperties;
  let arrow: "up" | "down" | null = null;
  if (spot) {
    const below = spot.top + spot.height + GAP;
    const roomBelow = window.innerHeight - below > 260;
    const left = Math.max(GAP, Math.min(spot.left, window.innerWidth - CARD_W - GAP));
    if (roomBelow) {
      cardStyle = { top: below, left };
      arrow = "up";
    } else {
      cardStyle = { bottom: window.innerHeight - spot.top + GAP, left };
      arrow = "down";
    }
  } else {
    cardStyle = { top: "50%", left: "50%", transform: "translate(-50%, -50%)" };
  }

  const dim = "pointer-events-none absolute bg-slate-950/55 transition-all duration-300 ease-out";

  return createPortal(
    <div className="fixed inset-0 z-[110]">
      {/*
        Four panels around the target rather than one sheet over everything.
        The target keeps its own brightness and its own click handlers; there is
        simply nothing on top of it. When no anchor is found we dim the whole
        screen lightly so the card still reads.
      */}
      {spot ? (
        <>
          <div className={dim} style={{ top: 0, left: 0, right: 0, height: Math.max(0, spot.top) }} />
          <div className={dim} style={{ top: spot.top + spot.height, left: 0, right: 0, bottom: 0 }} />
          <div className={dim} style={{ top: spot.top, left: 0, width: Math.max(0, spot.left), height: spot.height }} />
          <div className={dim} style={{ top: spot.top, left: spot.left + spot.width, right: 0, height: spot.height }} />

          {/* Ring + pulse. Purely decorative, never over the target itself. */}
          <div
            key={`${i}-${nudge}`}
            className="pointer-events-none absolute rounded-lg transition-all duration-300 ease-out"
            style={{
              ...spot,
              boxShadow: `0 0 0 3px ${ringColor}, 0 0 0 8px ${ringColor}33, 0 0 28px 6px ${ringColor}55`,
            }}
          />
          <div
            key={`pulse-${i}-${nudge}`}
            className="pointer-events-none absolute rounded-lg motion-safe:animate-pulse"
            style={{
              ...spot,
              animationDuration: "1.8s",
              boxShadow: `0 0 0 6px ${ringColor}55`,
            }}
          />
        </>
      ) : (
        <div className="pointer-events-none absolute inset-0 bg-slate-950/35" />
      )}

      {/* ── Card ── */}
      <div
        style={cardStyle}
        className={cn(
          "pointer-events-auto absolute w-[min(420px,calc(100vw-2rem))] overflow-hidden rounded-xl border bg-background shadow-2xl",
          "duration-200 animate-in fade-in zoom-in-95",
          step.caution && "border-amber-500/50",
        )}
      >
        {/* progress */}
        <div className="h-1 w-full bg-muted">
          <div
            className={cn("h-full transition-all duration-300", step.caution ? "bg-amber-500" : "bg-primary")}
            style={{ width: `${((i + 1) / walkthrough.steps.length) * 100}%` }}
          />
        </div>

        <div className="p-4">
          <div className="mb-2 flex items-start gap-2.5">
            <div
              className={cn(
                "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                step.caution ? "bg-amber-500/15 text-amber-600" : "bg-primary/10 text-primary",
              )}
            >
              {arrow === "up" ? <ArrowUp className="h-4 w-4" /> : arrow === "down" ? <ArrowDown className="h-4 w-4" /> : <GraduationCap className="h-4 w-4" />}
            </div>
            <div className="min-w-0 flex-1">
              <button
                onClick={() => setShowSteps((v) => !v)}
                title="Show all steps"
                className="flex w-full min-w-0 items-center gap-1.5 text-left text-xs text-muted-foreground hover:text-foreground"
              >
                <List className="h-3 w-3 shrink-0" />
                <span className="truncate">{walkthrough.title}</span>
                <span className="shrink-0">· step {i + 1} of {walkthrough.steps.length}</span>
              </button>
              <p className="mt-0.5 text-base font-semibold leading-snug">{step.title}</p>
            </div>
            <div className="flex shrink-0 items-center gap-0.5">
              <button
                onClick={minimise}
                aria-label="Minimise walkthrough"
                title="Minimise — keeps your place"
                className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <Minus className="h-4 w-4" />
              </button>
              <button
                onClick={stop}
                aria-label="End walkthrough"
                className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Jump list — go straight to any part of the task. */}
          {showSteps && (
            <div className="mb-3 max-h-52 overflow-y-auto rounded-lg border bg-muted/40 p-1">
              {walkthrough.steps.map((s, n) => (
                <button
                  key={n}
                  onClick={() => { goToStep(n); setShowSteps(false); }}
                  className={cn(
                    "flex w-full items-start gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-background",
                    n === i && "bg-background font-medium",
                  )}
                >
                  <span
                    className={cn(
                      "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-xs",
                      n < i ? "bg-primary/15 text-primary" : n === i ? "bg-primary text-primary-foreground" : "bg-muted-foreground/20 text-muted-foreground",
                    )}
                  >
                    {n < i ? <Check className="h-2.5 w-2.5" /> : n + 1}
                  </span>
                  <span className="min-w-0 flex-1 leading-snug">{s.title}</span>
                </button>
              ))}
            </div>
          )}

          <p className="text-sm leading-relaxed text-foreground/80">{step.body}</p>

          {/* The cue: what to physically do, separated from the explanation. */}
          {wantsClick && (
            <button
              onClick={() => { setNudge((n) => n + 1); findAnchor(step.anchor)?.scrollIntoView({ behavior: "smooth", block: "center" }); }}
              className="mt-3 flex w-full items-center gap-2 rounded-lg border border-primary/40 bg-primary/10 px-3 py-2 text-left text-xs font-medium text-primary transition-colors hover:bg-primary/15"
            >
              <MousePointerClick className="h-4 w-4 shrink-0 motion-safe:animate-pulse" />
              <span className="flex-1">{step.cue ?? "Click the highlighted control to continue"}</span>
              <span className="text-xs font-normal opacity-70">show me</span>
            </button>
          )}

          {step.caution && (
            <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                <strong>Look, do not press.</strong> {step.cue ?? "This control commits a real action on a real record."}
              </span>
            </div>
          )}

          {!wantsClick && !step.caution && step.cue && (
            <div className="mt-3 flex items-start gap-2 rounded-lg border bg-muted/50 px-3 py-2 text-xs">
              <Eye className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <span>{step.cue}</span>
            </div>
          )}

          {!rect && step.anchor && (
            <p className="mt-2 text-xs italic text-muted-foreground">
              That control is not on screen right now — open the tab or screen it lives on and it
              will light up.
            </p>
          )}

          <div className="mt-4 flex items-center justify-between gap-3 border-t pt-3">
            <p className="min-w-0 flex-1 text-xs leading-snug text-muted-foreground">
              You are on the real page: safe clicks only - nothing is saved unless you save it.
            </p>
            <div className="flex shrink-0 items-center gap-1.5">
              {i > 0 && (
                <Button variant="outline" size="sm" className="h-7 px-2" onClick={() => goToStep(i - 1)} aria-label="Previous step">
                  <ChevronLeft className="h-3.5 w-3.5" />
                </Button>
              )}
              <Button
                size="sm"
                className="h-7"
                variant={wantsClick ? "outline" : "default"}
                onClick={next}
              >
                {isLast ? "Done" : wantsClick ? "Skip" : "Next"}
                {!isLast && <ChevronRight className="ml-1 h-3.5 w-3.5" />}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
