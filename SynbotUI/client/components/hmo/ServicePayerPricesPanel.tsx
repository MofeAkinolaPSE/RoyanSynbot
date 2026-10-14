import { useQuery } from "@tanstack/react-query";
import { Loader2, Tags } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  WorkspaceSheet, PanelHeaderIdentity, DetailRow, SectionLabel,
} from "@/components/shared/panel-shared";
import { RecordTable, CellStack } from "@/components/patient/RecordTable";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";

/**
 * What each HMO actually pays for one service.
 *
 * Hope priced per payer. Migration 188 flattened that to a single representative
 * charge, so the catalogue could only ever show one number and every HMO quoted
 * identically. Migration 198 rebuilt the grid from the archived
 * pharmacy_tariff_amounts — 28,750 rates across 109 payers — and this is the
 * view that makes it visible.
 *
 * A service with no rates here is not broken: it means no payer has a
 * negotiated price and everyone is quoted the list price.
 */

const naira = (v: any) =>
  v == null ? "—" : `₦${Number(v).toLocaleString("en-NG", { minimumFractionDigits: 2 })}`;

export function ServicePayerPricesPanel({
  service,
  onClose,
}: {
  service: { id: number | string; name: string; category?: string; base_price?: number };
  onClose: () => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["service-payer-prices", service.id],
    queryFn: () => api.hospital.coverage.servicePayerPrices(service.id),
  });
  const prices: any[] = data?.prices ?? [];

  const list = Number(service.base_price ?? 0);
  const values = prices.map((p) => Number(p.price ?? 0)).filter((n) => n > 0).sort((a, b) => a - b);
  const min = values.length ? values[0] : null;
  const max = values.length ? values[values.length - 1] : null;
  const spread = min != null && max != null && max > min;

  // The modal price — what MOST payers actually pay. Reported because the
  // migrated grid has a long tail: for one drug 45 of 82 payers sit at ₦50
  // while a single payer sits at ₦1,500, likely a per-pack figure among
  // per-tablet ones. Min/max alone makes that look like a ₦1,495 negotiation.
  const counts = new Map<number, number>();
  for (const v of values) counts.set(v, (counts.get(v) ?? 0) + 1);
  let modal: number | null = null;
  let modalCount = 0;
  for (const [v, n] of counts) if (n > modalCount) { modal = v; modalCount = n; }

  // A ratio this wide is not a negotiation, it is a unit mismatch.
  const suspectSpread = min != null && max != null && min > 0 && max / min > 50;

  return (
    <WorkspaceSheet
      onClose={onClose}
      header={
        <PanelHeaderIdentity
          icon={<Tags className="h-5 w-5 text-primary" />}
          title={service.name}
          badges={
            <>
              {service.category && (
                <Badge variant="outline" className="text-xs capitalize">{service.category}</Badge>
              )}
              <Badge variant="outline" className="text-xs">
                {prices.length} negotiated {prices.length === 1 ? "rate" : "rates"}
              </Badge>
            </>
          }
          subline="Per-payer pricing"
        />
      }
    >
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        <section>
          <SectionLabel icon={<Tags className="h-3.5 w-3.5" />} label="Pricing" />
          <DetailRow
            label="List price"
            value={naira(list)}
            accent={list > 0 ? undefined : "text-amber-600"}
          />
          {list === 0 && (
            <p className="py-1 text-xs text-amber-600">
              No list price recorded. Any payer without a negotiated rate below will quote ₦0.
            </p>
          )}
          <DetailRow label="Lowest negotiated" value={min != null ? naira(min) : null} />
          <DetailRow label="Highest negotiated" value={max != null ? naira(max) : null} />
          {modal != null && modalCount > 1 && (
            <DetailRow
              label="Most common"
              value={`${naira(modal)} — ${modalCount} of ${values.length} payers`}
            />
          )}
          {spread && (
            <DetailRow
              label="Spread"
              value={`${naira(max! - min!)} between highest and lowest payer`}
            />
          )}
          {suspectSpread && (
            <p className="mt-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
              The highest rate is more than 50× the lowest. In the migrated data this
              usually means some payers were priced per pack and others per unit, not
              that one negotiated {Math.round(max! / min!)}× better. Check the outliers
              before billing from them.
            </p>
          )}
        </section>

        {isLoading ? (
          <div className="flex justify-center py-10">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <RecordTable
            rows={prices}
            rowKey={(p: any) => p.id}
            emptyIcon={<Tags className="h-6 w-6" />}
            emptyLabel="No payer has a negotiated rate for this service — all are quoted the list price"
            // Highlight anything a payer pays BELOW the list price, since that
            // is the margin question a finance lead actually opens this to ask.
            accent={(p: any) => (list > 0 && Number(p.price) < list ? "border-l-amber-500" : undefined)}
            columns={[
              {
                header: "Payer",
                cell: (p: any) => <CellStack primary={p.hmo_name ?? `HMO ${p.hmo_id}`} secondary={p.hmo_code} mono />,
              },
              {
                header: "Negotiated price",
                width: "w-[160px]",
                cell: (p: any) => <span className="tabular-nums font-medium">{naira(p.price)}</span>,
              },
              {
                header: "vs list",
                width: "w-[130px]",
                cell: (p: any) => {
                  if (!list) return <span className="text-muted-foreground">—</span>;
                  const diff = Number(p.price) - list;
                  if (diff === 0) return <span className="text-muted-foreground">same</span>;
                  return (
                    <span className={cn("tabular-nums", diff > 0 ? "text-green-600" : "text-amber-600")}>
                      {diff > 0 ? "+" : ""}{naira(diff)}
                    </span>
                  );
                },
              },
            ]}
          />
        )}
      </div>
    </WorkspaceSheet>
  );
}
