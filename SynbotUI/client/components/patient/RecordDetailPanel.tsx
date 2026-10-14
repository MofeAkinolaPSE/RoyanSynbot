import { FileText, type LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  WorkspaceSheet, PanelHeaderIdentity, SectionLabel, DetailRow,
} from "@/components/shared/panel-shared";
import { cn } from "@/lib/utils";

/**
 * The detail view behind every clickable row on the patient chart.
 *
 * This replaces a 21-line centred Dialog that served sixteen different record
 * types by flattening each into label/value pairs. Two consequences of that
 * design were worth fixing rather than restyling:
 *
 *  - Long-form clinical prose (operative notes, SOAP sections, radiology
 *    findings) was squeezed into a right-aligned value cell, which is where a
 *    surgeon's operative note is least readable.
 *  - It shared no vocabulary with the workspace panels the rest of the app
 *    uses, so a record opened from the chart looked like a different product
 *    from the same record opened from a worklist.
 *
 * `rows` is kept so simple records stay a one-liner to build; `sections` and
 * `blocks` exist for records that have real structure.
 */

export type DetailBadge = {
  label: string;
  tone?: "default" | "success" | "warning" | "danger" | "info";
};

export type DetailSection = {
  label: string;
  icon?: React.ReactNode;
  rows: [string, any][];
};

export type RecordDetail = {
  title: string;
  subtitle?: string;
  icon?: LucideIcon;
  badges?: DetailBadge[];
  /** Flat rows, for records with no meaningful grouping. */
  rows?: [string, any][];
  /** Grouped rows, rendered as labelled sections with separators. */
  sections?: DetailSection[];
  /**
   * Long-form text — operative notes, findings, a SOAP section. Rendered full
   * width with wrapping preserved, never as a value cell.
   */
  blocks?: { label: string; text?: string | null }[];
  /** Footer actions, e.g. "Open full record". */
  actions?: React.ReactNode;
};

const TONE: Record<string, string> = {
  default: "",
  success: "border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-400",
  warning: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  danger:  "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400",
  info:    "border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-400",
};

export function RecordDetailPanel({
  detail,
  onClose,
  patientName,
}: {
  detail: RecordDetail | null;
  onClose: () => void;
  patientName?: string;
}) {
  if (!detail) return null;

  const Icon = detail.icon ?? FileText;
  const hasRows = (detail.rows ?? []).length > 0;
  const blocks = (detail.blocks ?? []).filter((b) => b.text);

  return (
    <WorkspaceSheet
      onClose={onClose}
      footer={detail.actions}
      header={
        <PanelHeaderIdentity
          icon={<Icon className="h-5 w-5 text-primary" />}
          title={detail.title}
          badges={
            detail.badges?.length ? (
              <>
                {detail.badges.map((b, i) => (
                  <Badge key={i} variant="outline" className={cn("text-xs capitalize", TONE[b.tone ?? "default"])}>
                    {b.label}
                  </Badge>
                ))}
              </>
            ) : undefined
          }
          subline={[patientName, detail.subtitle].filter(Boolean).join(" · ") || undefined}
        />
      }
    >
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {hasRows && (
          <section>
            {detail.rows!.map(([label, value], i) => (
              <DetailRow key={`${label}-${i}`} label={label} value={value} />
            ))}
          </section>
        )}

        {detail.sections?.map((sec, i) => (
          <div key={i}>
            {(hasRows || i > 0) && <Separator className="mb-4" />}
            <section>
              <SectionLabel icon={sec.icon} label={sec.label} />
              {sec.rows.map(([label, value], j) => (
                <DetailRow key={`${label}-${j}`} label={label} value={value} />
              ))}
            </section>
          </div>
        ))}

        {blocks.map((b, i) => (
          <div key={i}>
            <Separator className="mb-4" />
            <section>
              <SectionLabel icon={<FileText className="h-3.5 w-3.5" />} label={b.label} />
              {/* Full width, wrapping preserved — the whole point of not being
                  a right-aligned value cell. */}
              <p className="whitespace-pre-wrap rounded-md bg-muted/40 px-3 py-2 text-xs leading-relaxed">
                {b.text}
              </p>
            </section>
          </div>
        ))}

        {!hasRows && !detail.sections?.length && blocks.length === 0 && (
          <p className="text-sm italic text-muted-foreground">
            No further detail was recorded for this entry.
          </p>
        )}
      </div>
    </WorkspaceSheet>
  );
}
