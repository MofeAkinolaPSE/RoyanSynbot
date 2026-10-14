import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Loader2, DoorOpen, ClipboardCheck, HeartPulse, Stethoscope, FileText,
  FlaskConical, ScanLine, Pill, ReceiptText, Banknote, LogOut, AlertTriangle,
  ChevronRight,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { encounterStatusColor } from "@/lib/encounter-status";
import { PANEL_WIDTH } from "@/components/shared/panel-shared";
import { ViewReportButton } from "@/components/reports/ResultReport";

interface EncounterStoryPanelProps {
  encounterId: number;
  patientName?: string;
  onClose: () => void;
  /**
   * Open the record a timeline row refers to.
   *
   * The story panel deliberately does not open these itself: it is a Sheet, and
   * so is every workspace panel. Stacking two right-hand Sheets means two
   * competing focus traps. Instead the chart owns the panels and decides — it
   * closes the story, opens the record, and restores the story afterwards.
   */
  onOpenRecord?: (kind: StoryRecordKind, record: any) => void;
}

function fmtDateTime(ts?: string | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("en-NG", {
    day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

type StoryEvent = {
  at: string;
  icon: any;
  iconClass: string;
  title: string;
  meta?: string;
  detail?: React.ReactNode;
  /**
   * What this moment refers to, so the row can be opened.
   *
   * buildStory used to drop `o.id` / `n.id` / `b.id` while flattening, which
   * left the timeline readable but inert — there was nothing to open even if a
   * click handler existed.
   */
  open?: { kind: StoryRecordKind; record: any };
};

export type StoryRecordKind = "lab" | "radiology" | "note" | "vitals" | "bill" | "prescription";

// ── Building the story: every domain contributes its own moments (an order
// placed, a result returned, a drug dispensed) rather than one flat "visit
// happened" row — that's what turns a status summary into an actual
// narrative of the encounter. ──────────────────────────────────────────────
function buildStory(data: any): StoryEvent[] {
  const enc = data?.encounter ?? {};
  const events: StoryEvent[] = [];

  if (enc.created_at) {
    events.push({
      at: enc.created_at, icon: DoorOpen, iconClass: "text-slate-500",
      title: "Encounter opened",
      meta: [enc.department, enc.encounter_type?.replace(/_/g, " ")].filter(Boolean).join(" · "),
      detail: enc.chief_complaint ? <p>Chief complaint: {enc.chief_complaint}</p> : undefined,
    });
  }
  if (enc.triage_at) {
    events.push({
      at: enc.triage_at, icon: ClipboardCheck, iconClass: "text-amber-500",
      title: "Triaged",
      meta: enc.triage_level ? `Level: ${enc.triage_level.replace(/_/g, " ")}` : undefined,
      detail: enc.triage_notes ? <p>{enc.triage_notes}</p> : undefined,
    });
  }

  for (const v of data?.vitals ?? []) {
    const parts = [
      v.bp_systolic != null && v.bp_diastolic != null ? `BP ${v.bp_systolic}/${v.bp_diastolic}` : null,
      v.pulse != null ? `Pulse ${v.pulse}` : null,
      v.temperature != null ? `Temp ${v.temperature}°C` : null,
      v.spo2 != null ? `SpO2 ${v.spo2}%` : null,
      v.respiratory_rate != null ? `RR ${v.respiratory_rate}` : null,
      v.weight != null ? `Wt ${v.weight}kg` : null,
    ].filter(Boolean);
    events.push({
      at: v.recorded_at ?? v.created_at, icon: HeartPulse, iconClass: "text-sky-500",
      title: "Vitals recorded",
      meta: v.recorded_by ? `By ${v.recorded_by}` : undefined,
      open: { kind: "vitals", record: v },
      detail: parts.length > 0 ? <p className="text-xs">{parts.join(" · ")}</p> : undefined,
    });
  }

  if (enc.consultation_at) {
    const codes = Array.isArray(enc.diagnosis_codes) ? enc.diagnosis_codes : [];
    events.push({
      at: enc.consultation_at, icon: Stethoscope, iconClass: "text-primary",
      title: "Consultation started",
      meta: enc.consulting_doctor ? `Dr. ${enc.consulting_doctor}` : undefined,
      detail: (codes.length > 0 || enc.diagnosis_notes) ? (
        <div className="space-y-1">
          {codes.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {codes.map((c: string) => <Badge key={c} variant="outline" className="text-xs font-mono">{c}</Badge>)}
            </div>
          )}
          {enc.diagnosis_notes && <p>{enc.diagnosis_notes}</p>}
        </div>
      ) : undefined,
    });
  }

  for (const n of data?.notes ?? []) {
    const soap = [
      n.subjective && `S: ${n.subjective}`,
      n.objective && `O: ${n.objective}`,
      n.assessment && `A: ${n.assessment}`,
      n.plan && `P: ${n.plan}`,
    ].filter(Boolean).join("  ");
    events.push({
      at: n.created_at, icon: FileText, iconClass: "text-violet-500",
      title: n.note_title || (n.note_type ? `${n.note_type.replace(/_/g, " ")} note` : "Clinical note"),
      meta: n.author_name ? `By ${n.author_name}` : undefined,
      detail: (soap || n.content) ? <p className="whitespace-pre-wrap">{soap || n.content}</p> : undefined,
      open: { kind: "note", record: n },
    });
  }

  const resultsByOrder = new Map<number, any>();
  for (const r of data?.lab_results ?? []) resultsByOrder.set(r.lab_order_id, r);
  for (const o of data?.lab_orders ?? []) {
    events.push({
      at: o.ordered_at, icon: FlaskConical, iconClass: "text-purple-500",
      title: `Lab ordered: ${o.test_name}`,
      meta: [o.urgency, o.status?.replace(/_/g, " ")].filter(Boolean).join(" · "),
      open: { kind: "lab", record: o },
    });
    const res = resultsByOrder.get(o.id);
    if (res) {
      events.push({
        at: res.resulted_at, icon: FlaskConical, iconClass: res.is_critical ? "text-red-500" : "text-green-500",
        title: `Lab result: ${o.test_name}`,
        meta: res.interpretation ? res.interpretation.replace(/_/g, " ") : undefined,
        open: { kind: "lab", record: o },
        detail: (
          <div className="space-y-1">
            {res.is_critical && (
              <p className="flex items-center gap-1 text-red-600 font-medium"><AlertTriangle className="h-3 w-3" /> Critical result</p>
            )}
            {res.result_summary && <p>{res.result_summary}</p>}
            {res.reference_range && <p className="text-xs text-muted-foreground">Reference: {res.reference_range}</p>}
            <ViewReportButton kind="lab" orderIds={[o.id]} variant="ghost" className="-ml-2 h-7" />
          </div>
        ),
      });
    }
  }

  for (const o of data?.radiology_orders ?? []) {
    events.push({
      at: o.ordered_at, icon: ScanLine, iconClass: "text-indigo-500",
      title: `Radiology ordered: ${o.modality?.toUpperCase() ?? "Imaging"}${o.body_part ? ` — ${o.body_part}` : ""}`,
      meta: [o.urgency, o.status?.replace(/_/g, " ")].filter(Boolean).join(" · "),
      detail: o.clinical_indication ? <p>{o.clinical_indication}</p> : undefined,
      open: { kind: "radiology", record: o },
    });
    if (o.reported_at) {
      events.push({
        at: o.reported_at, icon: ScanLine, iconClass: "text-green-500",
        title: `Radiology report: ${o.modality?.toUpperCase() ?? "Imaging"}`,
        meta: o.radiologist_id ? `By ${o.radiologist_id}` : undefined,
        open: { kind: "radiology", record: o },
        detail: (
          <div className="space-y-1">
            {o.impression && <p><span className="text-muted-foreground">Impression: </span>{o.impression}</p>}
            {o.findings && <p><span className="text-muted-foreground">Findings: </span>{o.findings}</p>}
            <ViewReportButton kind="scan" orderIds={[o.id]} variant="ghost" className="-ml-2 h-7" />
          </div>
        ),
      });
    }
  }

  const dispensingByRx = new Map<number, any[]>();
  for (const d of data?.dispensing ?? []) {
    const list = dispensingByRx.get(d.prescription_id) ?? [];
    list.push(d);
    dispensingByRx.set(d.prescription_id, list);
  }
  for (const rx of data?.prescriptions ?? []) {
    events.push({
      at: rx.prescribed_at, icon: Pill, iconClass: "text-orange-500",
      title: `Prescribed: ${rx.drug_name}`,
      meta: [rx.dosage, rx.frequency, rx.route].filter(Boolean).join(" · "),
      detail: rx.special_instructions ? <p>{rx.special_instructions}</p> : undefined,
    });
    for (const d of dispensingByRx.get(rx.id) ?? []) {
      events.push({
        at: d.dispensed_at, icon: Pill, iconClass: "text-green-500",
        title: `Dispensed: ${d.drug_name}`,
        meta: `${d.quantity_dispensed ?? "—"} ${d.unit ?? ""}${d.dispensed_by ? ` · By ${d.dispensed_by}` : ""}`,
        detail: d.batch_number ? <p className="text-xs text-muted-foreground">Batch {d.batch_number}</p> : undefined,
      });
    }
  }

  const paymentsByBill = new Map<number, any[]>();
  for (const p of data?.payments ?? []) {
    const list = paymentsByBill.get(p.billing_id) ?? [];
    list.push(p);
    paymentsByBill.set(p.billing_id, list);
  }
  for (const b of data?.bills ?? []) {
    events.push({
      at: b.billed_at, icon: ReceiptText, iconClass: "text-gold",
      title: `Bill generated: ${b.bill_number ?? `#${b.id}`}`,
      meta: `₦${Number(b.subtotal ?? 0).toLocaleString()} · ${b.status?.replace(/_/g, " ")}`,
      open: { kind: "bill", record: b },
    });
    for (const p of paymentsByBill.get(b.id) ?? []) {
      events.push({
        at: p.received_at, icon: Banknote, iconClass: "text-green-500",
        title: `Payment received`,
        meta: `₦${Number(p.amount ?? 0).toLocaleString()} · ${p.payment_method?.replace(/_/g, " ")}${p.reference ? ` · Ref ${p.reference}` : ""}`,
      });
    }
  }

  if (enc.discharge_at) {
    events.push({
      at: enc.discharge_at, icon: LogOut, iconClass: "text-green-600",
      title: "Discharged",
      meta: enc.discharge_by ? `By ${enc.discharge_by}` : undefined,
      detail: enc.discharge_summary ? <p>{enc.discharge_summary}</p> : undefined,
    });
  }

  return events
    .filter(e => !!e.at)
    .sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());
}

export function EncounterStoryPanel({ encounterId, patientName, onClose, onOpenRecord }: EncounterStoryPanelProps) {
  const { data, isLoading } = useQuery({
    queryKey: ["encounter-story", encounterId],
    queryFn: () => api.hospital.queue.get(String(encounterId)),
  });

  const enc = data?.encounter;
  const story = useMemo(() => buildStory(data), [data]);

  return (
    <Sheet open onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className={cn(PANEL_WIDTH.wide, "overflow-y-auto p-0 flex flex-col")} side="right">
        <SheetHeader className="px-5 pt-5 pb-4 border-b shrink-0">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <SheetTitle className="text-base leading-tight">
                Encounter Story{patientName ? ` — ${patientName}` : ""}
              </SheetTitle>
              {enc && (
                <div className="flex flex-wrap items-center gap-2 mt-1.5">
                  <Badge variant="outline" className={cn("text-xs capitalize", encounterStatusColor(enc.status))}>
                    {enc.status?.replace(/_/g, " ")}
                  </Badge>
                  {enc.department && <span className="text-xs text-muted-foreground">{enc.department}</span>}
                  {enc.encounter_type && <span className="text-xs text-muted-foreground capitalize">· {enc.encounter_type.replace(/_/g, " ")}</span>}
                </div>
              )}
              {enc && (
                <p className="text-xs text-muted-foreground mt-1">
                  Opened {fmtDateTime(enc.created_at)}
                  {enc.discharge_at && ` · Discharged ${fmtDateTime(enc.discharge_at)}`}
                </p>
              )}
            </div>
          </div>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {isLoading ? (
            <div className="flex justify-center py-14"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
          ) : story.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-14">No recorded activity for this encounter yet.</p>
          ) : (
            <ol className="relative border-l border-border ml-2.5 space-y-5">
              {story.map((ev, i) => {
                const Icon = ev.icon;
                const canOpen = !!ev.open && !!onOpenRecord;
                const body = (
                  <>
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                      <p className="text-sm font-medium">{ev.title}</p>
                      <span className="text-xs text-muted-foreground whitespace-nowrap">{fmtDateTime(ev.at)}</span>
                    </div>
                    {ev.meta && <p className="text-xs text-muted-foreground mt-0.5">{ev.meta}</p>}
                    {ev.detail && <div className="text-xs text-foreground/90 mt-1 rounded-md bg-muted/40 px-2.5 py-1.5">{ev.detail}</div>}
                  </>
                );
                return (
                  <li key={i} className="ml-5">
                    <span className="absolute -left-[11px] flex h-6 w-6 items-center justify-center rounded-full border bg-background">
                      <Icon className={cn("h-3.5 w-3.5", ev.iconClass)} />
                    </span>
                    {canOpen ? (
                      <button
                        type="button"
                        onClick={() => onOpenRecord!(ev.open!.kind, ev.open!.record)}
                        className="group block w-full rounded-md -mx-2 px-2 py-1 text-left transition-colors hover:bg-muted/50"
                      >
                        {body}
                        <span className="mt-1 inline-flex items-center gap-1 text-xs text-primary opacity-0 transition-opacity group-hover:opacity-100">
                          Open record <ChevronRight className="h-3 w-3" />
                        </span>
                      </button>
                    ) : body}
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
