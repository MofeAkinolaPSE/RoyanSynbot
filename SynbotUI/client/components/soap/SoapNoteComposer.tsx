import { useEffect, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, FileSignature, Loader2, RotateCcw, Stethoscope, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { useSoapDraft } from "@/hooks/use-soap-draft";
import { signBlockedReason, type DiagnosisEntry } from "@/lib/soap-gate";
import { composeNotePayload } from "@/lib/soap-format";
import { SOAP_SECTIONS, FieldLabel } from "./soap-shared";
import { SoapProgressStepper } from "./SoapProgressStepper";
import { SoapSectionShell } from "./SoapSectionShell";
import { SoapTemplateButton } from "./pickers/SoapTemplateButton";
import { DiagnosisPicker } from "./pickers/DiagnosisPicker";
import { PlanOrderBar } from "./orders/PlanOrderBar";
import { PatientContextStrip } from "./PatientContextStrip";
import { SmartPhraseTextarea } from "./SmartPhraseTextarea";
import { ShowMeHow } from "@/components/tour/ShowMeHow";
import { HelpHint } from "@/components/help/HelpHint";

/**
 * Doctor SOAP note composer.
 *
 * CONTAINER-AGNOSTIC BY DESIGN — renders no Sheet, no Dialog, no Tabs, and
 * invalidates no queries. That is precisely what lets the same component serve
 * both existing note UIs (the OPD panel's Notes tab and the PatientProfile
 * dialog) without either one's container or cache keys leaking into the other.
 * Callers do their own invalidation in onSigned.
 *
 * Wave 2 scope: discrete fields + strict S->O->A->P gating + draft persistence
 * + sign. The per-section template pickers, diagnosis search and the six Plan
 * order dialogs arrive in Wave 3; the seams for them are marked below.
 */
export interface SoapNoteComposerProps {
  encounterId: string | number;
  patientId?: string | number;
  patientSex?: string | null;
  /** Shown in the diagnosis modal header, mirroring the legacy screen. */
  patientName?: string | null;
  patientMeta?: string | null;
  /** Surfaced on the medication dialog as a prescribing warning. */
  allergies?: string[] | null;
  bloodGroup?: string | null;
  genotype?: string | null;
  /** Antenatal patients only; the context strip hides it when absent. */
  obstetric?: { gravida?: number | null; para?: number | null; lmp?: string | null; ga_weeks?: number | null } | null;
  latestVitalsId?: number | null;
  department?: string;
  /** Caller invalidates its own queries here. */
  onSigned?: (note: unknown) => void;
  /** Lets the container guard its close affordance. */
  onDirtyChange?: (dirty: boolean) => void;
  className?: string;
}

export function SoapNoteComposer({
  encounterId,
  patientId,
  patientSex,
  patientName,
  patientMeta,
  allergies,
  bloodGroup,
  genotype,
  obstetric,
  latestVitalsId,
  onSigned,
  onDirtyChange,
  className,
}: SoapNoteComposerProps) {
  const { toast } = useToast();
  const {
    draft,
    dispatch,
    gate,
    isDirty,
    pendingRestore,
    restorePending,
    discardPending,
    clearDraft,
  } = useSoapDraft(encounterId);

  const [expanded, setExpanded] = useState<"s" | "o" | "a" | "p">("s");
  const [dxOpen, setDxOpen] = useState(false);

  // Follow the gate forward as sections complete, but never fight a manual
  // selection of an already-unlocked section.
  useEffect(() => {
    if (gate.focus && gate[expanded].status === "complete") setExpanded(gate.focus);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gate.focus]);

  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  const blockedReason = useMemo(() => signBlockedReason(draft), [draft]);

  /**
   * Submit staged orders AFTER the note is safely stored. Each is independent;
   * one failure must not abort the rest, and none of them can cost the
   * clinician their note. Returns the labels that failed so the user is told
   * exactly what did not go through rather than getting a generic error.
   */
  const submitOrders = async (): Promise<string[]> => {
    const failed: string[] = [];
    const pid = patientId != null ? Number(patientId) : undefined;
    const eid = Number(encounterId);

    for (const o of draft.plan.orders) {
      const p: any = o.payload ?? {};
      try {
        switch (o.kind) {
          case "lab":
            await api.hospital.lab.placeOrder({
              patient_id: pid, encounter_id: eid,
              test_name: p.name, urgency: p.urgency || "routine",
              notes: p.clinical_indication || undefined,
            });
            break;
          case "radiology":
            await api.hospital.radiology.createOrder({
              patient_id: pid, encounter_id: eid,
              test_name: p.name, modality: p.modality || "other",
              urgency: p.urgency || "routine",
              clinical_indication: p.clinical_indication || undefined,
            });
            break;
          case "medication":
            await api.hospital.pharmacy.createRx({
              patient_id: pid, encounter_id: eid,
              drug_name: p.name, dosage: p.dosage,
              route: p.route || undefined, frequency: p.frequency || undefined,
              duration: p.duration || undefined,
              quantity: p.quantity ? Number(p.quantity) : undefined,
            });
            break;
          case "allergy":
            if (pid != null) {
              await api.hospital.pharmacy.addAllergy(pid, {
                allergen: p.name, severity: p.severity || undefined,
                reaction: p.reaction || undefined,
              });
            }
            break;
          case "immunization":
            if (pid != null) {
              await api.hospital.mch.logImmunisation(pid, {
                vaccine_name: p.name,
                dose_number: p.dose_number ? Number(p.dose_number) : undefined,
                batch_number: p.batch_number || undefined,
              });
            }
            break;
          case "procedure":
            await api.hospital.theatre.scheduleCase({
              patient_id: pid, encounter_id: eid,
              procedure_name: p.name,
              scheduled_date: p.scheduled_date || undefined,
              notes: p.notes || undefined,
            });
            break;
        }
      } catch {
        failed.push(o.label);
      }
    }
    return failed;
  };

  const signMut = useMutation({
    mutationFn: async () => {
      // Note FIRST — it is the legal record. A failing order POST must never
      // cost the clinician their documentation.
      const payload = composeNotePayload(draft);
      const res = await api.hospital.queue.addNote(String(encounterId), {
        ...payload,
        vitals_id: latestVitalsId ?? undefined,
      });
      const failedOrders = await submitOrders();
      return { ...(res as any), failedOrders };
    },
    onSuccess: (res: any) => {
      // Note first, orders second — the note is the legal record, and a failed
      // order POST must never cost the clinician their documentation.
      // (Order fan-out lands with the Plan dialogs in Wave 3.)
      clearDraft();

      // The backend signs only when the acting user maps to a royan_staff row
      // (queue_clinical.py resolves royan_staff.user_id from the JWT `sub`).
      // An unlinked account gets a SAVED-BUT-UNSIGNED note. Never let that pass
      // silently under a button labelled "Sign note" — an unsigned note is not
      // the medico-legal record the clinician believes they just created.
      const signed = !!res?.note?.signed_at;
      const failed: string[] = res?.failedOrders ?? [];

      if (!signed) {
        toast({
          title: "Note saved — NOT signed",
          description:
            "Your account is not linked to a staff record, so the note could not be signed. Ask an administrator to link it, then add a signed addendum.",
          variant: "destructive",
        });
      } else if (failed.length) {
        // The note is safe; say precisely which orders are not.
        toast({
          title: `Note signed — ${failed.length} order${failed.length > 1 ? "s" : ""} failed`,
          description: `Re-enter from the Orders tab: ${failed.join("; ")}`,
          variant: "destructive",
        });
      } else {
        toast({ title: "Note signed", description: "Saved and locked to the patient record." });
      }
      onSigned?.(res);
    },
    onError: (err: any) =>
      toast({
        title: "Could not sign note",
        description: err?.message ?? "Please try again.",
        variant: "destructive",
      }),
  });

  const applyDiagnoses = (added: DiagnosisEntry[]) => {
    for (const d of added) dispatch({ type: "addDiagnosis", diagnosis: d });
  };

  const sectionSummary = {
    s: draft.subjective.chief_complaint,
    o: draft.objective.general || Object.values(draft.objective.systems)[0] || "",
    a: draft.assessment.diagnoses.map((d) => d.description).join(", "),
    p: draft.plan.text,
  } as const;

  return (
    <div className={cn("space-y-3", className)}>
      {/* Recovered draft — offered, never silently restored. Quietly
          resurrecting text into a medico-legal document the clinician did not
          knowingly reopen is not acceptable. */}
      {pendingRestore && (
        <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs">
          <RotateCcw className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
          <div className="flex-1">
            <p className="font-medium text-amber-800 dark:text-amber-300">
              Unsaved note from {new Date(pendingRestore.savedAt).toLocaleString()}
            </p>
            <p className="text-amber-700/80 dark:text-amber-400/80">
              This encounter has an unsigned draft. Restore it or start fresh.
            </p>
          </div>
          <div className="flex shrink-0 gap-1">
            <Button size="sm" variant="outline" className="h-6 px-2 text-xs" onClick={restorePending}>
              Restore
            </Button>
            <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={discardPending}>
              Discard
            </Button>
          </div>
        </div>
      )}

      {/* Stays visible for the whole note, mirroring the pinned context strip
          on Royan's legacy SOAP screen. */}
      <PatientContextStrip
        patientId={patientId}
        allergies={allergies}
        bloodGroup={bloodGroup}
        genotype={genotype}
        obstetric={obstetric}
      />

      <div className="flex items-center gap-2">
        <div data-tour-id="soap-stepper" className="min-w-0 flex-1">
          <SoapProgressStepper gate={gate} onJump={setExpanded} />
        </div>
        <ShowMeHow only={["soap-note", "note-addendum", "personal-template"]} label="Help" />
      </div>

      {/* ── S ─────────────────────────────────────────────────────────────── */}
      <SoapSectionShell
        letter="S"
        title={SOAP_SECTIONS[0].title}
        hint={SOAP_SECTIONS[0].hint}
        state={gate.s}
        summary={sectionSummary.s}
        expanded={expanded === "s"}
        onToggle={() => setExpanded("s")}
        templateSlot={
          <span data-tour-id="soap-template-subjective">
          <SoapTemplateButton
            sources={["note", "exam-hpi"]}
            /* Only 11 chief_complaint and 11 review_of_systems phrases exist
               across all 528 templates, vs 2,883 subjective. Pooling all three
               keeps the picker useful; a CC-only list would look broken. */
            contextTypes={["subjective", "chief_complaint", "review_of_systems"]}
            patientSex={patientSex}
            onInsert={(t) => dispatch({ type: "appendTo", field: "hpc", text: t })}
            currentText={draft.subjective.hpc}
          />
          </span>
        }
      >
        <div>
          <FieldLabel required>Chief complaint</FieldLabel>
          <Input
            data-tour-id="soap-chief-complaint"
            value={draft.subjective.chief_complaint}
            onChange={(e) => dispatch({ type: "setChiefComplaint", value: e.target.value })}
            placeholder="e.g. Headache for 3 days"
          />
        </div>
        <div>
          <FieldLabel>History of presenting complaint</FieldLabel>
          <SmartPhraseTextarea
            rows={4}
            value={draft.subjective.hpc}
            onChange={(v) => dispatch({ type: "setHpc", value: v })}
            placeholder="Onset, duration, character, aggravating and relieving factors, associated symptoms…"
          />
        </div>
        <div>
          <div className="mb-1 flex items-center justify-between">
            <FieldLabel className="mb-0">Review of systems</FieldLabel>
            <SoapTemplateButton
              sources={["exam-ros"]}
              patientSex={patientSex}
              label="ROS"
              onInsert={(t) => dispatch({ type: "appendTo", field: "ros", text: t })}
            />
          </div>
          <SmartPhraseTextarea
            rows={3}
            value={draft.subjective.ros}
            onChange={(v) => dispatch({ type: "setRos", value: v })}
            placeholder="Optional — systems reviewed and their findings"
          />
        </div>
      </SoapSectionShell>

      {/* ── O ─────────────────────────────────────────────────────────────── */}
      <SoapSectionShell
        letter="O"
        title={SOAP_SECTIONS[1].title}
        hint={SOAP_SECTIONS[1].hint}
        state={gate.o}
        summary={sectionSummary.o}
        expanded={expanded === "o"}
        onToggle={() => setExpanded("o")}
        templateSlot={
          <SoapTemplateButton
            sources={["exam-pe", "note"]}
            contextTypes={["objective"]}
            patientSex={patientSex}
            onInsert={(t) => dispatch({ type: "appendTo", field: "general", text: t })}
            currentText={draft.objective.general}
          />
        }
      >
        <div>
          {/* General first, then systemic — the order the MD described:
              "General examination, no pallor, no jaundice... Then chest,
              respiratory system, cardiovascular system." */}
          <FieldLabel>General examination</FieldLabel>
          <SmartPhraseTextarea
            data-tour-id="soap-objective-general"
            rows={3}
            value={draft.objective.general}
            onChange={(v) => dispatch({ type: "setGeneral", value: v })}
            placeholder="e.g. No pallor, no jaundice, afebrile, not in respiratory distress"
          />
        </div>
        <div>
          <div className="mb-1 flex items-center justify-between">
            <FieldLabel className="mb-0">Systemic examination</FieldLabel>
            <SoapTemplateButton
              sources={["exam-pe"]}
              patientSex={patientSex}
              label="Findings"
              onInsert={(t) =>
                dispatch({
                  type: "setSystem",
                  system: "Systemic",
                  value: draft.objective.systems.Systemic
                    ? `${draft.objective.systems.Systemic}\n${t}`
                    : t,
                })
              }
            />
          </div>
          <Textarea
            rows={4}
            value={draft.objective.systems.Systemic ?? ""}
            onChange={(e) => dispatch({ type: "setSystem", system: "Systemic", value: e.target.value })}
            placeholder="Chest, cardiovascular, abdomen, neurological…"
          />
        </div>
      </SoapSectionShell>

      {/* ── A ─────────────────────────────────────────────────────────────── */}
      <SoapSectionShell
        letter="A"
        title={SOAP_SECTIONS[2].title}
        hint={SOAP_SECTIONS[2].hint}
        state={gate.a}
        summary={sectionSummary.a}
        expanded={expanded === "a"}
        onToggle={() => setExpanded("a")}
        templateSlot={
          <SoapTemplateButton
            sources={["note"]}
            contextTypes={["assessment"]}
            onInsert={(t) => dispatch({ type: "appendTo", field: "assessmentText", text: t })}
            currentText={draft.assessment.text}
          />
        }
      >
        <div>
          <div className="mb-1 flex items-center justify-between">
            <FieldLabel className="mb-0" required>Diagnoses</FieldLabel>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-6 gap-1 px-2 text-xs"
              data-tour-id="soap-add-diagnosis"
              onClick={() => setDxOpen(true)}
            >
              <Stethoscope className="h-3 w-3" />
              Add diagnosis
            </Button>
            <HelpHint id="diagnosis-code-readonly" />
          </div>
          {draft.assessment.diagnoses.length > 0 && (
            <div className="mb-2 space-y-1">
              {draft.assessment.diagnoses.map((d: DiagnosisEntry) => (
                <div
                  key={d.icd_code}
                  className="flex items-center gap-2 rounded-md border bg-muted/40 px-2 py-1 text-xs"
                >
                  <Badge
                    variant="outline"
                    className={cn("font-mono text-xs", d.is_primary && "border-blue-500/40 text-blue-600")}
                  >
                    {d.icd_code}
                  </Badge>
                  <span className="min-w-0 flex-1 truncate">{d.description}</span>
                  {d.is_primary ? (
                    <span className="shrink-0 text-xs text-muted-foreground">primary</span>
                  ) : (
                    <button
                      type="button"
                      className="shrink-0 text-xs text-muted-foreground hover:text-foreground"
                      onClick={() => dispatch({ type: "setPrimaryDiagnosis", icdCode: d.icd_code })}
                    >
                      make primary
                    </button>
                  )}
                  <button
                    type="button"
                    aria-label={`Remove ${d.icd_code}`}
                    onClick={() => dispatch({ type: "removeDiagnosis", icdCode: d.icd_code })}
                    className="shrink-0 text-muted-foreground hover:text-destructive"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}

          {draft.assessment.diagnoses.length === 0 && (
            <p className="rounded-md border border-dashed px-2 py-3 text-center text-xs text-muted-foreground">
              No diagnosis yet — the note cannot be signed until one is added.
            </p>
          )}
        </div>
        <div>
          <FieldLabel>Assessment notes</FieldLabel>
          <Textarea
            rows={3}
            value={draft.assessment.text}
            onChange={(e) => dispatch({ type: "setAssessmentText", value: e.target.value })}
            placeholder="Clinical reasoning, differentials…"
          />
        </div>
      </SoapSectionShell>

      {/* ── P ─────────────────────────────────────────────────────────────── */}
      <div data-tour-id="soap-plan-section">
      <SoapSectionShell
        letter="P"
        title={SOAP_SECTIONS[3].title}
        hint={SOAP_SECTIONS[3].hint}
        state={gate.p}
        summary={sectionSummary.p}
        expanded={expanded === "p"}
        onToggle={() => setExpanded("p")}
        templateSlot={
          <SoapTemplateButton
            sources={["note"]}
            contextTypes={["plan"]}
            onInsert={(t) => dispatch({ type: "appendTo", field: "planText", text: t })}
            currentText={draft.plan.text}
          />
        }
      >
        <div data-tour-id="soap-order-bar">
        <PlanOrderBar
          orders={draft.plan.orders}
          onAdd={(o) => dispatch({ type: "addOrder", order: o })}
          onRemove={(id) => dispatch({ type: "removeOrder", tempId: id })}
          patientSex={patientSex}
          allergies={allergies}
        />
        </div>
        <div>
          <FieldLabel>Plan</FieldLabel>
          <SmartPhraseTextarea
            rows={4}
            value={draft.plan.text}
            onChange={(v) => dispatch({ type: "setPlanText", value: v })}
            placeholder="Investigations, treatment, follow-up…"
          />
        </div>
      </SoapSectionShell>
      </div>

      <Separator />

      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          {blockedReason ? (
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-500" />
              <span className="truncate">{blockedReason}</span>
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">
              Signing locks this note. Corrections are added as a separate addendum.
            </p>
          )}
        </div>
        <HelpHint id="note-signed-lock" className="mr-1.5" side="top" align="end" />
        <Button
          data-tour-id="soap-sign-button"
          onClick={() => signMut.mutate()}
          disabled={!gate.canSign || signMut.isPending}
          size="sm"
        >
          {signMut.isPending ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <FileSignature className="mr-1.5 h-3.5 w-3.5" />
          )}
          Sign note
        </Button>
      </div>

      <DiagnosisPicker
        open={dxOpen}
        onOpenChange={setDxOpen}
        existing={draft.assessment.diagnoses}
        onApply={applyDiagnoses}
        suggestFrom={[draft.subjective.chief_complaint, draft.subjective.hpc, draft.assessment.text]
          .filter(Boolean).join(". ")}
        patientName={patientName ?? undefined}
        patientMeta={patientMeta ?? undefined}
      />
    </div>
  );
}

export default SoapNoteComposer;
