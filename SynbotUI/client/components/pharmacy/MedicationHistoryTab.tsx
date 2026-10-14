import { useQuery } from "@tanstack/react-query";
import { Loader2, Pill, AlertTriangle, Info } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { SectionLabel, DetailRow } from "@/components/shared/panel-shared";
import { api } from "@/lib/api-client";

/**
 * One patient's complete medication history.
 *
 * "pharmacy can view the complete dosage regimen. So for a particular patient,
 * you can see the entire history just by clicking on that patient."
 *
 * The regimen is built from what was DISPENSED, not what was prescribed.
 * royan_prescriptions.drug_name concatenates a whole prescription into one
 * string — 62.8% contain commas and 20.5% are truncated with "+ 2 more" — so
 * grouping on it reports combinations as drugs and loses a fifth of everything.
 * Dispensing carries one drug per row, and is what the patient actually
 * received.
 *
 * Prescribed and collected are shown separately because the gap between them
 * matters: a drug prescribed and never collected is a patient who did not take
 * it.
 */
const fmtDate = (v: any) => (v ? new Date(v).toLocaleDateString() : "—");

export function MedicationHistoryTab({ patientId }: { patientId: number | string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["medication-history", patientId],
    queryFn: () => api.hospital.pharmacy.medicationHistory(patientId),
    enabled: !!patientId,
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-10">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const c = data?.counts ?? {};
  const regimen: any[] = data?.regimen ?? [];
  const rx: any[] = data?.prescriptions ?? [];

  if (!regimen.length && !rx.length) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">
        No medication recorded for this patient.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Badge variant="outline" className="gap-1"><Pill className="h-3 w-3" />{c.distinct_drugs ?? 0} drugs</Badge>
        <Badge variant="outline">{c.prescriptions ?? 0} prescriptions</Badge>
        <Badge variant="outline">{c.dispensing ?? 0} dispensed</Badge>
        {Number(c.never_collected) > 0 && (
          <Badge variant="outline" className="border-amber-500/40 text-amber-700 dark:text-amber-400">
            {c.never_collected} never collected
          </Badge>
        )}
      </div>

      <section>
        <SectionLabel icon={<Pill className="h-3.5 w-3.5" />} label="Regimen — what this patient has actually received" />
        {regimen.length === 0 ? (
          <p className="py-3 text-center text-xs text-muted-foreground">
            Nothing has been dispensed to this patient.
          </p>
        ) : (
          <ul className="space-y-1">
            {regimen.map((g) => (
              <li
                key={g.drug_name}
                className="flex items-start justify-between gap-2 border-b border-border/30 py-1.5 last:border-0"
              >
                <div className="min-w-0">
                  <p className="text-xs font-medium">{g.drug_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {g.times_dispensed}× · {Number(g.total_quantity).toLocaleString()} units total
                  </p>
                </div>
                <div className="shrink-0 text-right text-xs text-muted-foreground">
                  <div>last {fmtDate(g.last_dispensed)}</div>
                  <div>since {fmtDate(g.first_dispensed)}</div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <Separator />

      <section>
        <SectionLabel icon={<Pill className="h-3.5 w-3.5" />} label="Prescriptions" />
        {Number(c.prescriptions_truncated) > 0 && (
          <p className="mb-2 flex items-start gap-1.5 rounded-md border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {c.prescriptions_truncated} of these were recorded in the old system as a
            single line ending "+ N more", so the full drug list was never carried
            across. The regimen above is built from what was dispensed and is not
            affected.
          </p>
        )}
        <ul className="space-y-1">
          {rx.slice(0, 20).map((r) => (
            <li
              key={r.id}
              className="flex items-start justify-between gap-2 border-b border-border/30 py-1.5 last:border-0"
            >
              <div className="min-w-0">
                <p className="text-xs font-medium">{r.drug_name}</p>
                <p className="text-xs text-muted-foreground">
                  {[r.dosage, r.frequency, r.route, r.duration].filter(Boolean).join(" · ") || "—"}
                  {r.prescribed_by_name ? ` · ${r.prescribed_by_name}` : ""}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <div className="text-xs text-muted-foreground">{fmtDate(r.prescribed_at)}</div>
                {r.collected ? (
                  <Badge variant="outline" className="text-xs">collected</Badge>
                ) : (
                  <Badge
                    variant="outline"
                    className="gap-0.5 border-amber-500/40 text-xs text-amber-700 dark:text-amber-400"
                  >
                    <AlertTriangle className="h-2.5 w-2.5" /> not collected
                  </Badge>
                )}
              </div>
            </li>
          ))}
        </ul>
        {rx.length > 20 && (
          <p className="mt-1 text-xs text-muted-foreground">Showing 20 of {rx.length}.</p>
        )}
      </section>
    </div>
  );
}
