import { useQueries, useQuery } from "@tanstack/react-query";
import { AlertTriangle, FileText, FlaskConical, Loader2, NotebookPen } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";

const DONE = new Set(["resulted", "verified", "completed"]);

/** The visit's lab results, read first on a results review; "Write notes" takes the doctor to the SOAP note. */
export function EncounterResults({ encounterId, onWriteNotes }: { encounterId: number | string; onWriteNotes: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ["encounter-lab-orders", encounterId],
    queryFn: () => api.hospital.lab.listOrders({ encounter_id: Number(encounterId) }),
    refetchInterval: 30_000,
  });
  const orders: any[] = data?.orders ?? [];
  const details = useQueries({
    queries: orders.filter((o) => DONE.has(o.status)).map((o) => ({
      queryKey: ["lab-order", o.id],
      queryFn: () => api.hospital.lab.getOrder(o.id),
      staleTime: 30_000,
    })),
  });
  const resultFor = (id: any) => details.map((d) => d.data).find((d: any) => String(d?.order?.id) === String(id))?.result;
  const ready = orders.filter((o) => DONE.has(o.status)).length;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-muted/40 px-3 py-2">
        <p className="text-sm font-medium text-foreground">
          {isLoading ? "Loading results…" : orders.length === 0 ? "No lab tests on this visit." : `${ready} of ${orders.length} test${orders.length === 1 ? "" : "s"} back`}
        </p>
        <Button size="sm" className="gap-1.5" onClick={onWriteNotes}>
          <NotebookPen className="h-3.5 w-3.5" /> Write notes
        </Button>
      </div>
      {isLoading && <div className="flex justify-center py-6"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>}
      {orders.map((o) => {
        const r = resultFor(o.id);
        const analytes: any[] = r?.result_data?.analytes ?? [];
        const done = DONE.has(o.status);
        return (
          <div key={o.id} className={cn("rounded-md border p-3", r?.is_critical && "border-red-500 bg-red-50 dark:bg-red-500/10")}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
                <FlaskConical className="h-4 w-4 text-primary" /> {o.test_name}
                {r?.is_critical && <Badge variant="destructive" className="gap-1 text-xs"><AlertTriangle className="h-3 w-3" /> Critical</Badge>}
              </p>
              <Badge variant={done ? "default" : "outline"} className="text-xs capitalize">{done ? (r?.verified_at ? "verified" : "resulted") : String(o.status ?? "").replace(/_/g, " ")}</Badge>
            </div>
            {done && !r && <p className="mt-2 text-xs text-foreground/70">Loading result…</p>}
            {r && (
              <div className="mt-2 space-y-1.5 text-sm">
                {analytes.length > 0 ? (
                  <table className="w-full text-sm">
                    <thead><tr className="text-left text-xs text-foreground/70"><th className="py-0.5">Test</th><th>Result</th><th>Unit</th><th>Range / comment</th></tr></thead>
                    <tbody>
                      {analytes.map((a, i) => (
                        <tr key={i} className={cn("border-t", a.flag && a.flag !== "normal" && "font-semibold text-red-700 dark:text-red-400")}>
                          <td className="py-1">{a.name}</td><td>{a.observed_value ?? a.value ?? "—"}{a.flag && a.flag !== "normal" ? ` (${a.flag})` : ""}</td>
                          <td>{a.unit ?? ""}</td><td className="text-xs">{[a.reference_range, a.comment].filter(Boolean).join(" · ")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : r.result_data?.value != null ? (
                  <p><span className="font-semibold">{String(r.result_data.value)}</span> {r.result_data.unit ?? ""}{r.reference_range ? <span className="text-foreground/70"> · range {r.reference_range}</span> : null}</p>
                ) : null}
                {r.result_summary && <p><span className="font-medium">Summary:</span> {r.result_summary}</p>}
                {r.interpretation && <p><span className="font-medium">Interpretation:</span> {r.interpretation}</p>}
                {r.report_file_url && (
                  <a className="inline-flex items-center gap-1 text-xs font-medium text-primary underline" href={r.report_file_url} target="_blank" rel="noreferrer">
                    <FileText className="h-3.5 w-3.5" /> Open the lab report
                  </a>
                )}
                <p className="text-xs text-foreground/70">
                  {r.resulted_by_name ? `Resulted by ${r.resulted_by_name}` : ""}{r.verified_by_name ? ` · verified by ${r.verified_by_name}` : ""}
                  {r.resulted_at ? ` · ${new Date(r.resulted_at).toLocaleString("en-GB")}` : ""}
                </p>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
