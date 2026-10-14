import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Droplets, ListChecks } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";

/**
 * Persistent clinical context while writing a note.
 *
 * Royan's legacy SOAP screen kept a context strip pinned bottom-left, visible
 * the whole time the doctor was typing — in the meeting screenshots it showed
 * "Para: G3,P0 / L.M.P - 25/3/2026 / GA AT BOOKING: 14w+2D" on one patient and
 * "Medical History: PUDx / Mother Diabetic / Surgical History: NIL" on another.
 * The point is that the things you must not forget stay on screen while you
 * write, rather than living behind a tab.
 *
 * What this shows is driven by what the migrated data ACTUALLY contains:
 *   - Active problems     24,788 across 22,555 patients — the real substitute
 *                         for the screenshot's "Medical History" line
 *   - Allergies           shown when present
 *   - Blood group/genotype from the patient record
 *   - Obstetric (G/P, LMP, GA) rendered ONLY when an ANC record exists
 *
 * Deliberately NOT shown: structured allergy reaction/onset. royan_allergies
 * is empty (0 rows) and no patient carries the text array either — Phase A
 * established Hope holds no per-patient allergy history at all. The 18,926-row
 * allergen catalog exists to power typeahead as staff START recording them.
 * Rendering an "Allergies: none recorded" chip on every patient would imply a
 * negative finding that nobody actually documented.
 */
export function PatientContextStrip({
  patientId,
  allergies,
  bloodGroup,
  genotype,
  obstetric,
  className,
}: {
  patientId?: string | number;
  allergies?: string[] | null;
  bloodGroup?: string | null;
  genotype?: string | null;
  /** Populated only for antenatal patients. */
  obstetric?: { gravida?: number | null; para?: number | null; lmp?: string | null; ga_weeks?: number | null } | null;
  className?: string;
}) {
  const { data } = useQuery({
    queryKey: ["context-problems", patientId],
    queryFn: () => api.hospital.clinical.listProblems(patientId!, "active"),
    enabled: !!patientId,
    staleTime: 120_000,
  });

  const problems: any[] = data?.problems ?? [];
  const hasAllergies = !!allergies?.length;
  const hasObstetric =
    !!obstetric && (obstetric.gravida != null || obstetric.para != null || obstetric.lmp || obstetric.ga_weeks != null);

  // Render nothing rather than an empty bar of dashes.
  if (!hasAllergies && !problems.length && !bloodGroup && !genotype && !hasObstetric) return null;

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border bg-muted/40 px-2.5 py-1.5 text-xs",
        className,
      )}
    >
      {hasAllergies && (
        <span className="flex items-center gap-1 font-medium text-red-600 dark:text-red-400">
          <AlertTriangle className="h-3 w-3 shrink-0" />
          Allergies: {allergies!.join(" · ")}
        </span>
      )}

      {(bloodGroup || genotype) && (
        <span className="flex items-center gap-1 text-muted-foreground">
          <Droplets className="h-3 w-3 shrink-0" />
          {[bloodGroup, genotype].filter(Boolean).join(" / ")}
        </span>
      )}

      {hasObstetric && (
        <span className="text-muted-foreground">
          {obstetric!.gravida != null || obstetric!.para != null
            ? `Para: G${obstetric!.gravida ?? "?"},P${obstetric!.para ?? "?"}`
            : null}
          {obstetric!.lmp ? ` · LMP ${new Date(obstetric!.lmp).toLocaleDateString()}` : ""}
          {obstetric!.ga_weeks != null ? ` · GA ${obstetric!.ga_weeks}w` : ""}
        </span>
      )}

      {problems.length > 0 && (
        <span className="flex min-w-0 items-center gap-1 text-muted-foreground">
          <ListChecks className="h-3 w-3 shrink-0" />
          <span className="truncate">
            {problems.slice(0, 3).map((p: any) => p.description).join(" · ")}
          </span>
          {problems.length > 3 && (
            <Badge variant="outline" className="shrink-0 text-xs">+{problems.length - 3}</Badge>
          )}
        </span>
      )}
    </div>
  );
}
