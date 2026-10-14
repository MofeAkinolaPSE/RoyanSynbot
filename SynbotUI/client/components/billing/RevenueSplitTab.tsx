import { useQuery } from "@tanstack/react-query";
import { Loader2, Info, ShieldCheck, Wallet } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";

/**
 * Revenue by service line, split between payers and self-funding patients.
 *
 * "we should also be able to separate the HMO services so that we know what
 * services went to HMO and at what cost, what services went to private and at
 * what cost."
 *
 * The bar per row is deliberately a share, not a chart: the question is what
 * proportion of each service line a payer funds, and Radiology at 8% versus
 * Immunisation at 48% is legible instantly that way.
 */
const naira = (v: any) => `₦${Number(v ?? 0).toLocaleString()}`;

export function RevenueSplitTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["revenue-split"],
    queryFn: () => api.hospital.billing.revenueSplit(),
  });

  const rows: any[] = data?.categories ?? [];

  if (isLoading) {
    return (
      <div className="flex justify-center py-10">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border bg-card p-3">
          <p className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-muted-foreground">
            <ShieldCheck className="h-3.5 w-3.5" /> HMO / payer
          </p>
          <p className="mt-0.5 text-xl font-bold tabular-nums">{naira(data?.hmo_total)}</p>
          <p className="text-xs text-muted-foreground">{data?.hmo_share ?? 0}% of revenue</p>
        </div>
        <div className="rounded-lg border bg-card p-3">
          <p className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-muted-foreground">
            <Wallet className="h-3.5 w-3.5" /> Private / self-funded
          </p>
          <p className="mt-0.5 text-xl font-bold tabular-nums">{naira(data?.private_total)}</p>
          <p className="text-xs text-muted-foreground">
            {(100 - Number(data?.hmo_share ?? 0)).toFixed(1)}% of revenue
          </p>
        </div>
        <div className="rounded-lg border bg-card p-3">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Total</p>
          <p className="mt-0.5 text-xl font-bold tabular-nums">{naira(data?.grand_total)}</p>
          <p className="text-xs text-muted-foreground">{rows.length} service lines</p>
        </div>
      </div>

      {/* Stated rather than footnoted: the number is only as good as its basis. */}
      {data?.basis && (
        <p className="flex items-start gap-1.5 rounded-md border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {data.basis}
        </p>
      )}

      <div className="overflow-x-auto rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Service line</TableHead>
              <TableHead className="text-right">HMO</TableHead>
              <TableHead className="text-right">Private</TableHead>
              <TableHead className="text-right">Total</TableHead>
              <TableHead className="w-[150px]">Payer share</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                  No billed transactions in this period.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((r) => {
                const share = r.total_value > 0 ? (r.hmo_value / r.total_value) * 100 : 0;
                return (
                  <TableRow key={r.category}>
                    <TableCell className="text-sm font-medium">
                      {r.category}
                      <div className="text-xs text-muted-foreground">
                        {Number(r.total_count).toLocaleString()} transactions
                      </div>
                    </TableCell>
                    <TableCell className="text-right text-sm tabular-nums">
                      {naira(r.hmo_value)}
                    </TableCell>
                    <TableCell className="text-right text-sm tabular-nums">
                      {naira(r.private_value)}
                    </TableCell>
                    <TableCell className="text-right text-sm font-medium tabular-nums">
                      {naira(r.total_value)}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                          <div
                            className={cn("h-full rounded-full", share > 40 ? "bg-blue-500" : "bg-primary")}
                            style={{ width: `${Math.min(100, share)}%` }}
                          />
                        </div>
                        <span className="w-10 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
                          {share.toFixed(0)}%
                        </span>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
