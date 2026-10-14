import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Plus, Search, Star } from "lucide-react";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import type { DiagnosisEntry } from "@/lib/soap-gate";

/**
 * Diagnosis search — a direct rebuild of Royan's legacy "Diagnosis Search"
 * modal (see the meeting screenshots): patient header, search by DESCRIPTION
 * or by ICD-10 code, a "most common" quick-pick list, multi-select, and an
 * Apply Selection action.
 *
 * There is deliberately NO free-text code entry. "No doctor will add code.
 * They don't know it. The diagnosis will automatically generate the code."
 * The clinician searches words; the code is read-only output.
 *
 * Two sources, matching the legacy screen:
 *   - royan_diagnosis_catalog (198) = Royan's curated "MOST COMMON DIAGNOSES"
 *   - royan_icd10_codes    (12,542) = the full ICD-10 book, searched on demand
 */
export function DiagnosisPicker({
  open,
  onOpenChange,
  existing,
  onApply,
  patientName,
  patientMeta,
  suggestFrom,
}: {
  /** The note so far (complaint, history, examination, assessment): diagnoses are suggested from it. */
  suggestFrom?: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  existing: DiagnosisEntry[];
  onApply: (added: DiagnosisEntry[]) => void;
  patientName?: string;
  patientMeta?: string;
}) {
  const [descQuery, setDescQuery] = useState("");
  const [codeQuery, setCodeQuery] = useState("");
  const [selected, setSelected] = useState<Record<string, DiagnosisEntry>>({});

  // Curated shortlist — shown before any search, like the legacy screen.
  const { data: commonData, isLoading: loadingCommon } = useQuery({
    queryKey: ["diagnosis-catalog"],
    queryFn: () => api.hospital.clinical.searchDiagnosisCatalog(),
    enabled: open,
    staleTime: 300_000,
  });

  const activeQuery = descQuery.trim() || codeQuery.trim();
  const { data: icdData, isLoading: loadingIcd } = useQuery({
    queryKey: ["icd10-search", activeQuery],
    queryFn: () => api.hospital.clinical.searchIcd10(activeQuery),
    enabled: open && activeQuery.length >= 2,
    staleTime: 120_000,
  });

  // Pre-filled from the doctor's own words: suggestions to tick, never applied on their own.
  const suggestText = (suggestFrom ?? "").trim();
  const { data: suggestData, isLoading: loadingSuggest } = useQuery({
    queryKey: ["icd10-suggest", suggestText],
    queryFn: () => api.hospital.clinical.suggestIcd10(suggestText),
    enabled: open && suggestText.length >= 4,
    staleTime: 60_000,
  });
  const suggestions: DiagnosisEntry[] = (suggestData?.codes ?? []).map((c: any) => ({ icd_code: c.code, description: c.description }));

  const existingCodes = new Set(existing.map((d) => d.icd_code));

  const rows: DiagnosisEntry[] =
    activeQuery.length >= 2
      ? (icdData?.codes ?? []).map((c: any) => ({ icd_code: c.code, description: c.description }))
      : (commonData?.diagnoses ?? []).map((d: any) => ({
          icd_code: d.icd_code,
          description: d.description,
        }));

  const isLoading = activeQuery.length >= 2 ? loadingIcd : loadingCommon;
  const selectedList = Object.values(selected);

  const toggle = (d: DiagnosisEntry) => {
    if (existingCodes.has(d.icd_code)) return;
    setSelected((s) => {
      const next = { ...s };
      if (next[d.icd_code]) delete next[d.icd_code];
      else next[d.icd_code] = d;
      return next;
    });
  };

  const apply = () => {
    if (selectedList.length) onApply(selectedList);
    setSelected({});
    setDescQuery("");
    setCodeQuery("");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] flex-col sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Diagnosis search</DialogTitle>
          <DialogDescription>
            Search by description — the ICD-10 code is filled in for you.
          </DialogDescription>
        </DialogHeader>

        {patientName && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border bg-muted/30 px-3 py-1.5 text-xs">
            <span className="font-medium">{patientName}</span>
            {patientMeta && <span className="text-muted-foreground">{patientMeta}</span>}
          </div>
        )}

        <div className="grid shrink-0 grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Search by description
            </label>
            <div className="relative">
              <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={descQuery}
                onChange={(e) => { setDescQuery(e.target.value); if (e.target.value) setCodeQuery(""); }}
                placeholder="e.g. 20 weeks gestation of pregnancy"
                className="h-8 pl-7 text-xs"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
              or search by ICD-10 code
            </label>
            <Input
              value={codeQuery}
              onChange={(e) => { setCodeQuery(e.target.value); if (e.target.value) setDescQuery(""); }}
              placeholder="e.g. B50"
              className="h-8 font-mono text-xs"
            />
          </div>
        </div>

        {activeQuery.length < 2 && suggestText.length >= 4 && (
          <div className="shrink-0 rounded-md border border-primary/30 bg-primary/5">
            <div className="border-b border-primary/20 px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-primary">
              Suggested from your note{suggestData?.words?.length ? ` (${suggestData.words.slice(0, 6).join(", ")})` : ""}
            </div>
            {loadingSuggest ? (
              <div className="flex items-center justify-center py-3"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>
            ) : suggestions.length === 0 ? (
              <p className="px-3 py-2 text-xs text-foreground/70">No match from the note yet - search below.</p>
            ) : (
              <div className="max-h-44 overflow-y-auto">
                {suggestions.map((d) => {
                  const already = existingCodes.has(d.icd_code);
                  return (
                    <button key={d.icd_code} type="button" disabled={already} onClick={() => toggle(d)}
                            className={cn("flex w-full items-center gap-2 border-b px-3 py-1.5 text-left text-sm last:border-0",
                              already ? "opacity-50" : "hover:bg-primary/10")}>
                      <Checkbox checked={already || !!selected[d.icd_code]} disabled={already} />
                      <span className="flex-1 font-medium text-foreground">{d.description}</span>
                      <Badge variant="outline" className="font-mono text-xs">{d.icd_code}</Badge>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}

        <div className="flex min-h-0 flex-1 flex-col rounded-md border">
          <div className="border-b bg-muted/40 px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {activeQuery.length >= 2 ? "Search results" : "Most common diagnoses"}
          </div>
          <ScrollArea className="min-h-0 flex-1">
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : rows.length === 0 ? (
              <p className="p-4 text-xs italic text-muted-foreground">
                {activeQuery.length >= 2 ? "No diagnoses match that search." : "No catalog entries available."}
              </p>
            ) : (
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-background">
                  <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="w-8 px-2 py-1" />
                    <th className="px-2 py-1">Diagnosis</th>
                    <th className="w-24 px-2 py-1">ICD-10</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((d) => {
                    const already = existingCodes.has(d.icd_code);
                    return (
                      <tr
                        key={d.icd_code}
                        className={cn(
                          "border-b last:border-0",
                          already ? "opacity-50" : "cursor-pointer hover:bg-muted/50",
                        )}
                        onClick={() => toggle(d)}
                      >
                        <td className="px-2 py-1.5">
                          <Checkbox checked={already || !!selected[d.icd_code]} disabled={already} />
                        </td>
                        <td className="px-2 py-1.5">
                          {d.description}
                          {already && <span className="ml-1 text-xs text-muted-foreground">(added)</span>}
                        </td>
                        <td className="px-2 py-1.5">
                          <Badge variant="outline" className="font-mono text-xs">{d.icd_code}</Badge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </ScrollArea>
        </div>

        <DialogFooter className="shrink-0 gap-2 sm:justify-between">
          <span className="text-xs text-muted-foreground">
            {selectedList.length > 0 ? `${selectedList.length} selected` : "Select one or more diagnoses"}
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button size="sm" onClick={apply} disabled={!selectedList.length}>
              <Plus className="mr-1 h-3.5 w-3.5" />
              Apply selection
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
