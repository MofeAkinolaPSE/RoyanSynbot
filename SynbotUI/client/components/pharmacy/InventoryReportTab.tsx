import { useQuery } from "@tanstack/react-query";
import { Loader2, Boxes, AlertTriangle, TrendingDown, Info } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api-client";

/**
 * The inventory report: what stock is worth, what expires, what never moves.
 *
 * "we need to create an inventory report and add whatever metrics that we think
 * we can also add to make our inventory a lot better."
 *
 * Reports POSITION rather than movement. Only two dispensing events fall in the
 * last 90 days because the 618,452 migrated records predate go-live, so a
 * movement report would read as an empty pharmacy. What is actionable today is
 * the ₦50.7m on the shelf.
 *
 * Dead stock is the metric worth adding — stock held but never dispensed is
 * money on a shelf, and nothing in the app surfaced it before.
 */
const naira = (v: any) => `₦${Number(v ?? 0).toLocaleString()}`;

export function InventoryReportTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["inventory-report"],
    queryFn: () => api.hospital.pharmacy.inventory.report(),
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-10">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const t = data?.totals ?? {};
  const e = data?.expiry_exposure ?? {};
  const dead = data?.dead_stock ?? {};
  const noExpiry = Number(data?.batches_without_expiry ?? 0);
  const allMissingExpiry = noExpiry > 0 && noExpiry === Number(t.batches);

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border bg-card p-3">
          <p className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-muted-foreground">
            <Boxes className="h-3.5 w-3.5" /> Stock on hand
          </p>
          <p className="mt-0.5 text-xl font-bold tabular-nums">{naira(t.stock_value)}</p>
          <p className="text-xs text-muted-foreground">{t.batches ?? 0} batches · {t.drugs ?? 0} drugs</p>
        </div>
        <div className="rounded-lg border bg-card p-3">
          <p className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-muted-foreground">
            <TrendingDown className="h-3.5 w-3.5" /> Never dispensed
          </p>
          <p className="mt-0.5 text-xl font-bold tabular-nums">
            {dead.known ? naira(dead.value) : "—"}
          </p>
          <p className="text-xs text-muted-foreground">
            {dead.known ? `${dead.count} drugs held but never used` : "could not be calculated"}
          </p>
        </div>
        <div className="rounded-lg border bg-card p-3">
          <p className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-muted-foreground">
            <AlertTriangle className="h-3.5 w-3.5" /> Expiring in 90 days
          </p>
          <p className="mt-0.5 text-xl font-bold tabular-nums">
            {allMissingExpiry ? "unknown" : naira(Number(e.within_30 ?? 0) + Number(e.within_90 ?? 0))}
          </p>
          <p className="text-xs text-muted-foreground">
            {allMissingExpiry ? "no expiry dates recorded" : `${naira(e.expired)} already expired`}
          </p>
        </div>
      </div>

      {/* "Nothing expires soon" and "we don't know when anything expires" look
          identical on a dashboard. They are not the same fact. */}
      {allMissingExpiry && (
        <p className="flex items-start gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          None of the {noExpiry} batches in stock has an expiry date recorded, so
          expiry exposure cannot be calculated. This reads as "nothing expiring"
          but means "not known" — worth capturing expiry dates as stock is received.
        </p>
      )}

      {dead.known && (dead.drugs ?? []).length > 0 && (
        <section>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Held but never dispensed
          </p>
          <div className="overflow-x-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Drug</TableHead>
                  <TableHead className="text-right">Quantity</TableHead>
                  <TableHead className="text-right">Value</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {dead.drugs.map((d: any) => (
                  <TableRow key={d.formulary_id}>
                    <TableCell className="text-sm">{d.drug_name}</TableCell>
                    <TableCell className="text-right text-sm tabular-nums">
                      {Number(d.quantity).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right text-sm tabular-nums">{naira(d.value)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </section>
      )}

      <section>
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Highest value on hand
        </p>
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Drug</TableHead>
                <TableHead>Batches</TableHead>
                <TableHead className="text-right">Quantity</TableHead>
                <TableHead className="text-right">Value</TableHead>
                <TableHead>Moves?</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data?.top_by_value ?? []).map((d: any) => (
                <TableRow key={d.formulary_id}>
                  <TableCell className="text-sm">{d.drug_name}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{d.batches}</TableCell>
                  <TableCell className="text-right text-sm tabular-nums">
                    {Number(d.quantity).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right text-sm font-medium tabular-nums">{naira(d.value)}</TableCell>
                  <TableCell>
                    {d.ever_dispensed ? (
                      <Badge variant="outline" className="text-xs">dispensed</Badge>
                    ) : (
                      <Badge variant="outline" className="border-amber-500/40 text-xs text-amber-700 dark:text-amber-400">
                        never
                      </Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>
    </div>
  );
}
