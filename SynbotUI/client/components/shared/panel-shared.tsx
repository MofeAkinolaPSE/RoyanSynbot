import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

/**
 * The house workspace-panel vocabulary, in one place.
 *
 * `DetailRow` was copy-pasted into 10 domain files and `SectionLabel` into 11,
 * which is how they drifted: seven DetailRow copies guarded with `!value`,
 * which silently hides a numeric 0 — so "Balance: 0" or "Doses given: 0"
 * rendered as nothing at all. The version here takes the union of every call
 * site's props and uses the explicit guard, so a real zero shows.
 */

// ─────────────────────────────────────────────────────────── detail rows ────

export function DetailRow({
  label,
  value,
  mono = false,
  accent,
}: {
  label: string;
  /** number is accepted deliberately — see the 0 note above. */
  value?: string | number | null;
  mono?: boolean;
  /** Extra classes for the value, e.g. "text-red-500 font-semibold". */
  accent?: string;
}) {
  // Explicit rather than `!value`: 0 is a real, displayable value.
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="flex items-start justify-between gap-3 py-1 border-b border-border/30 last:border-0">
      <span className="text-xs text-muted-foreground shrink-0">{label}</span>
      <span className={cn("text-xs text-right font-medium", mono && "font-mono", accent)}>
        {value}
      </span>
    </div>
  );
}

export function SectionLabel({
  icon,
  label,
}: {
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <span className="text-muted-foreground">{icon}</span>
      <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        {label}
      </span>
    </div>
  );
}

// ──────────────────────────────────────────────────────────── panel shell ────

/**
 * Panel width. Every workspace panel shares one value so they cannot drift
 * apart, and so widening them is a single edit rather than fourteen.
 *
 * `wide` exists for panels that hold a full clinical document — a SOAP note
 * read at 560px forces horizontal cramping that makes clinicians scroll to
 * read a sentence.
 */
export const PANEL_WIDTH = {
  /** Compact summary panels that sit alongside a page, not over it. */
  narrow: "w-full sm:w-[50vw] sm:min-w-[560px] sm:max-w-none",
  default: "w-full sm:w-[55vw] sm:min-w-[640px] sm:max-w-none",
  /**
   * For panels holding a full clinical document. The consultation SOAP note is
   * the reason this exists: at the old 560px it wrapped so hard that clinicians
   * scrolled to read a single sentence.
   */
  wide: "w-full sm:w-[70vw] sm:min-w-[760px] sm:max-w-none",
} as const;

/**
 * The standard right-hand workspace sheet: fixed header, scrolling body,
 * optional sticky footer for actions.
 *
 * Panels keep owning their own header content (identity strips differ per
 * domain); this owns the geometry and the scroll behaviour, which is what
 * actually drifted between copies.
 */
export function WorkspaceSheet({
  open = true,
  onClose,
  header,
  footer,
  width = "default",
  children,
  className,
}: {
  open?: boolean;
  onClose: () => void;
  header: React.ReactNode;
  footer?: React.ReactNode;
  width?: keyof typeof PANEL_WIDTH;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Sheet open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent
        side="right"
        className={cn(PANEL_WIDTH[width], "overflow-y-auto p-0 flex flex-col", className)}
      >
        <SheetHeader className="px-5 pt-5 pb-4 border-b shrink-0">{header}</SheetHeader>
        <div className="flex-1 min-h-0 flex flex-col">{children}</div>
        {footer && (
          <>
            <Separator className="shrink-0" />
            <div className="px-5 py-3 flex flex-wrap gap-2 shrink-0">{footer}</div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

/**
 * The identity block every panel header opens with: round icon chip, title,
 * then whatever badges and sub-line the domain wants.
 */
export function PanelHeaderIdentity({
  icon,
  title,
  badges,
  subline,
  actions,
}: {
  icon: React.ReactNode;
  title: React.ReactNode;
  badges?: React.ReactNode;
  subline?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-3">
      <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <SheetTitle className="text-base leading-tight">{title}</SheetTitle>
        {badges && <div className="flex flex-wrap items-center gap-2 mt-1">{badges}</div>}
        {subline && <p className="text-xs text-muted-foreground mt-1">{subline}</p>}
      </div>
      {actions && <div className="shrink-0">{actions}</div>}
    </div>
  );
}
