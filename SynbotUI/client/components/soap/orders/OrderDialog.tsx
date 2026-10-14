import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Loader2, Search } from "lucide-react";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import {
  FREQUENCY_OPTIONS, ROUTE_OPTIONS, DURATION_OPTIONS, UNIT_OPTIONS, unitForDoseForm,
} from "@/lib/clinical-options";
import type { DraftOrder } from "@/lib/soap-gate";
import { FieldLabel } from "../soap-shared";
import { HelpHint } from "@/components/help/HelpHint";

export type OrderKind = "medication" | "allergy" | "immunization" | "lab" | "radiology" | "procedure";

const URGENCY = ["routine", "urgent", "stat"] as const;
const SEVERITY = ["mild", "moderate", "severe"] as const;

const TITLES: Record<OrderKind, string> = {
  medication: "Prescribe medication",
  allergy: "Record allergy",
  immunization: "Record immunisation",
  lab: "Order laboratory test",
  radiology: "Order radiology",
  procedure: "Schedule procedure",
};

/**
 * One dialog for all six Plan order kinds. They share the same skeleton —
 * catalog search, a few structured fields, stage — so six near-identical
 * components would be six places to fix the same bug.
 *
 * Every kind is CATALOG-BACKED. The meeting was explicit that the system runs
 * on dropdowns: "You are not writing any of this, you just write the drug and
 * you look at the other options and then you leave it as it is."
 */
export function OrderDialog({
  kind,
  open,
  onOpenChange,
  onStage,
  patientSex,
  allergies,
}: {
  kind: OrderKind;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onStage: (order: DraftOrder) => void;
  patientSex?: string | null;
  allergies?: string[] | null;
}) {
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<any | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  /**
   * Prefill from the catalog entry rather than making the clinician retype what
   * the formulary already knows. Everything stays editable — these are the
   * usual values for the drug, not a prescription.
   */
  const pick = (r: any) => {
    setPicked(r);
    if (kind !== "medication") return;
    setForm((f) => ({
      ...f,
      dosage: f.dosage ?? (r.strength ? `${r.strength}` : ""),
      dose_form: f.dose_form ?? (r.form ?? ""),
      // royan_drug_formulary.route is a text[] of the routes this drug allows.
      // A single permitted route can be filled in; more than one is a choice
      // only the prescriber can make.
      route: f.route ?? (Array.isArray(r.route) && r.route.length === 1 ? r.route[0] : ""),
      unit: f.unit ?? (r.unit ?? unitForDoseForm(r.form) ?? ""),
    }));
  };

  const search = useQuery({
    queryKey: ["order-catalog", kind, query],
    queryFn: () => {
      switch (kind) {
        case "medication": return api.hospital.clinical.searchDrugs(query);
        case "allergy": return api.hospital.clinical.searchAllergens(query);
        case "lab": return api.hospital.lab.searchCatalog(query);
        case "radiology": return api.hospital.clinical.searchRadiologyCatalog(query);
        case "procedure": return api.hospital.clinical.searchSurgeryCatalog(query);
        case "immunization": return api.hospital.mch.listVaccineSchedule();
        default: return Promise.resolve({});
      }
    },
    // Vaccine schedule is a fixed 38-row list — always load it. Everything
    // else waits for 2 characters, matching the repo's existing convention.
    enabled: open && (kind === "immunization" || query.trim().length >= 2),
    staleTime: 300_000,
  });

  const results: any[] = useMemo(() => {
    const d: any = search.data ?? {};
    return d.drugs ?? d.allergens ?? d.tests ?? d.procedures ?? d.schedule ?? d.vaccines ?? [];
  }, [search.data]);

  const nameOf = (r: any) =>
    r.generic_name ?? r.name ?? r.test_name ?? r.vaccine_name ?? r.description ?? "";

  // A drug whose name matches a recorded allergy — surfaced, never blocked;
  // the clinician may still have a reason to prescribe it.
  const allergyConflict = useMemo(() => {
    if (kind !== "medication" || !picked || !allergies?.length) return null;
    const n = nameOf(picked).toLowerCase();
    return allergies.find((a) => a && n.includes(a.toLowerCase().split(/\s+/)[0])) ?? null;
  }, [kind, picked, allergies]);

  const label = useMemo(() => {
    if (!picked) return "";
    const n = nameOf(picked);
    switch (kind) {
      case "medication":
        return [n, form.dosage, form.route, form.frequency, form.duration && `x${form.duration}`]
          .filter(Boolean).join(" ");
      case "allergy":
        return [n, form.severity && `(${form.severity})`].filter(Boolean).join(" ");
      case "immunization":
        return [n, form.dose_number && `dose ${form.dose_number}`].filter(Boolean).join(" ");
      case "lab":
      case "radiology":
        return [n, form.urgency && form.urgency !== "routine" && `(${form.urgency})`].filter(Boolean).join(" ");
      case "procedure":
        return [n, form.scheduled_date].filter(Boolean).join(" · ");
    }
  }, [picked, form, kind]);

  // Routes this drug permits, per the formulary; the full list when it says
  // nothing, so an unlisted drug is never un-prescribable.
  const allowedRoutes = useMemo(() => {
    const allowed: string[] = Array.isArray(picked?.route) ? picked.route : [];
    if (allowed.length === 0) return ROUTE_OPTIONS;
    const narrowed = ROUTE_OPTIONS.filter((o) => allowed.includes(o.value));
    return narrowed.length > 0 ? narrowed : ROUTE_OPTIONS;
  }, [picked]);

  const canStage = !!picked && (kind !== "medication" || !!form.dosage);

  const stage = () => {
    if (!picked) return;
    onStage({
      tempId: `${kind}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      kind,
      label,
      payload: { ...form, catalog_id: picked.id, name: nameOf(picked) },
    });
    setPicked(null);
    setForm({});
    setQuery("");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] flex-col sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{TITLES[kind]}</DialogTitle>
          <DialogDescription>
            {kind === "immunization"
              ? "Pick from the vaccination schedule."
              : "Search the catalog, then set the details."}
          </DialogDescription>
        </DialogHeader>

        {!picked ? (
          <>
            {kind !== "immunization" && (
              <div className="relative shrink-0">
                <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  autoFocus
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Type at least 2 characters…"
                  className="h-8 pl-7 text-xs"
                />
              </div>
            )}
            <ScrollArea className="min-h-0 flex-1 rounded-md border">
              {search.isLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              ) : results.length === 0 ? (
                <p className="p-4 text-xs italic text-muted-foreground">
                  {kind !== "immunization" && query.trim().length < 2
                    ? "Start typing to search."
                    : "Nothing found in the catalog."}
                </p>
              ) : (
                <div className="p-1">
                  {results.map((r: any, i: number) => (
                    <button
                      key={r.id ?? i}
                      type="button"
                      onClick={() => pick(r)}
                      className="flex w-full flex-col items-start rounded px-2 py-1.5 text-left text-xs hover:bg-muted"
                    >
                      <span className="font-medium">{nameOf(r)}</span>
                      <span className="text-xs text-muted-foreground">
                        {[r.code, r.category, r.concept_type, r.age_milestone, r.category_name, r.strength]
                          .filter(Boolean).join(" · ")}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </ScrollArea>
          </>
        ) : (
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
            <div className="flex items-center gap-2 rounded-md border bg-muted/40 px-2 py-1.5">
              <span className="min-w-0 flex-1 truncate text-sm font-medium">{nameOf(picked)}</span>
              <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={() => setPicked(null)}>
                Change
              </Button>
            </div>

            {allergyConflict && (
              <p className="flex items-start gap-1.5 rounded-md border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-700 dark:text-red-400">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  This patient has a recorded allergy to <strong>{allergyConflict}</strong>. Confirm before prescribing.
                </span>
                <HelpHint id="pharmacy-allergy-warning" className="ml-auto" side="left" align="start" />
              </p>
            )}

            {kind === "medication" && (
              <div className="grid grid-cols-2 gap-2">
                <div className="col-span-2">
                  <FieldLabel required>Dosage</FieldLabel>
                  <Input value={form.dosage ?? ""} onChange={(e) => set("dosage", e.target.value)} placeholder="e.g. 500mg" className="h-8 text-xs" />
                </div>
                <div>
                  <FieldLabel>Route</FieldLabel>
                  <PickOne
                    value={form.route}
                    onChange={(v) => set("route", v)}
                    /* Narrowed to the routes this drug is licensed for when the
                       formulary lists them — offering IV for an oral-only tablet
                       is an error the catalog can prevent. */
                    options={allowedRoutes}
                  />
                </div>
                <div>
                  <FieldLabel>Frequency</FieldLabel>
                  <PickOne value={form.frequency} onChange={(v) => set("frequency", v)} options={FREQUENCY_OPTIONS} />
                </div>
                <div>
                  <FieldLabel>Duration</FieldLabel>
                  <PickOne value={form.duration} onChange={(v) => set("duration", v)} options={DURATION_OPTIONS} />
                </div>
                <div>
                  <FieldLabel>Quantity</FieldLabel>
                  <Input type="number" value={form.quantity ?? ""} onChange={(e) => set("quantity", e.target.value)} className="h-8 text-xs" />
                </div>
                <div>
                  <FieldLabel>Unit</FieldLabel>
                  <PickOne value={form.unit} onChange={(v) => set("unit", v)} options={UNIT_OPTIONS} />
                </div>
              </div>
            )}

            {kind === "allergy" && (
              <div className="space-y-2">
                <div>
                  <FieldLabel>Severity</FieldLabel>
                  <PickOne value={form.severity} onChange={(v) => set("severity", v)} options={SEVERITY} />
                </div>
                <div>
                  <FieldLabel>Reaction</FieldLabel>
                  <Input value={form.reaction ?? ""} onChange={(e) => set("reaction", e.target.value)} placeholder="e.g. rash, angioedema" className="h-8 text-xs" />
                </div>
              </div>
            )}

            {kind === "immunization" && (
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <FieldLabel>Dose number</FieldLabel>
                  <Input type="number" value={form.dose_number ?? ""} onChange={(e) => set("dose_number", e.target.value)} className="h-8 text-xs" />
                </div>
                <div>
                  <FieldLabel>Batch number</FieldLabel>
                  <Input value={form.batch_number ?? ""} onChange={(e) => set("batch_number", e.target.value)} className="h-8 text-xs" />
                </div>
              </div>
            )}

            {(kind === "lab" || kind === "radiology") && (
              <div className="space-y-2">
                <div>
                  <FieldLabel>Urgency</FieldLabel>
                  <PickOne value={form.urgency ?? "routine"} onChange={(v) => set("urgency", v)} options={URGENCY} />
                </div>
                <div>
                  <FieldLabel>Clinical indication</FieldLabel>
                  <Textarea rows={2} value={form.clinical_indication ?? ""} onChange={(e) => set("clinical_indication", e.target.value)} className="text-xs" />
                </div>
              </div>
            )}

            {kind === "procedure" && (
              <div className="space-y-2">
                <div>
                  <FieldLabel>Scheduled date</FieldLabel>
                  <Input type="date" value={form.scheduled_date ?? ""} onChange={(e) => set("scheduled_date", e.target.value)} className="h-8 text-xs" />
                </div>
                <div>
                  <FieldLabel>Notes</FieldLabel>
                  <Textarea rows={2} value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} className="text-xs" />
                </div>
              </div>
            )}

            {label && (
              <p className="rounded-md border bg-muted/30 px-2 py-1.5 text-xs text-muted-foreground">
                Will appear in the note as: <span className="text-foreground">{label}</span>
              </p>
            )}
          </div>
        )}

        <DialogFooter className="shrink-0">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button size="sm" onClick={stage} disabled={!canStage}>Add to plan</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type PickOption = string | { value: string; label: string };

/**
 * Accepts both option shapes deliberately: the local `as const` tuples
 * (URGENCY, SEVERITY) are plain strings, while the shared lists in
 * lib/clinical-options.ts are {value,label} objects. Normalising here is what
 * lets every call site drop its cast — and a cast is exactly what previously
 * hid an object being rendered as a React child, which throws at runtime.
 */
function PickOne({
  value, onChange, options,
}: { value?: string; onChange: (v: string) => void; options: readonly PickOption[] }) {
  const items = options.map((o) =>
    typeof o === "string" ? { value: o, label: o } : o,
  );
  return (
    <Select value={value ?? ""} onValueChange={onChange}>
      <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="Select…" /></SelectTrigger>
      <SelectContent>
        {items.map((o) => (
          <SelectItem key={o.value} value={o.value} className="text-xs capitalize">{o.label}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
