/**
 * Pharmacy quality control, on the pharmacy's live batches: expired stock to quarantine and dispose,
 * stock expiring in the next 90 days, batches missing the facts QC needs (expiry date, cost), and
 * medication incidents. Recalls are opened on the batch in Roy Books, which freezes it and traces
 * every patient who received it.
 *
 * Replaces a page from the pharma product (NAFDAC batch release, temperature logs) that called /qc/*
 * routes this hospital never had.
 */
import { useSearchParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CalendarClock, FileWarning, FlaskConical, Pill } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/workspace/PageHeader";
import { KpiStrip } from "@/components/workspace/KpiStrip";
import { ExpiredStockTab } from "@/components/pharmacy/ExpiredStockTab";
import { api } from "@/lib/api-client";
import { fmtDay } from "./ReportComposer";

type Dict = Record<string, any>;
const M = (v: any) => { const n = Number(v ?? 0); return Math.abs(n) >= 1e6 ? `₦${(n / 1e6).toFixed(1)}M` : `₦${Math.round(n).toLocaleString()}`; };

export default function QualityControl() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "expired";
  const setTab = (t: string) => { const p = new URLSearchParams(params); p.set("tab", t); setParams(p, { replace: true }); };
  const q = useQuery({ queryKey: ["quality", "pharmacy-qc"], queryFn: () => api.quality.pharmacyQc() });
  const d: Dict = q.data ?? {};
  return (
    <div className="flex flex-col gap-5">
      <PageHeader icon={FlaskConical} title="Pharmacy Quality Control"
        subtitle="Expiry, batch records and medication incidents, read from the pharmacy's live batches" />
      <KpiStrip items={[
        { label: "Expired, still on the shelf", value: M(d.expired?.value), icon: AlertTriangle, tone: d.expired?.batches ? "danger" : "default",
          sub: `${d.expired?.batches ?? 0} batches · ${d.expired?.products ?? 0} products`, onClick: () => setTab("expired") },
        { label: "Expiring within 90 days", value: M(d.expiring_90?.value), icon: CalendarClock, tone: d.expiring_90?.batches ? "warning" : "default",
          sub: `${d.expiring_90?.batches ?? 0} batches`, onClick: () => setTab("expiring") },
        { label: "Batches missing QC facts", value: (d.missing?.no_expiry ?? 0) + (d.missing?.no_cost ?? 0), icon: FileWarning,
          tone: d.missing?.no_expiry ? "warning" : "default", sub: `${d.missing?.no_expiry ?? 0} no expiry · ${d.missing?.no_cost ?? 0} no cost`, onClick: () => setTab("missing") },
        { label: "Medication incidents open", value: d.medication_incidents_open ?? 0, icon: Pill, tone: d.medication_incidents_open ? "warning" : "default",
          sub: `${(d.medication_incidents ?? []).length} recorded`, onClick: () => setTab("incidents") },
      ]} />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap">
          <TabsTrigger value="expired">Expired stock</TabsTrigger>
          <TabsTrigger value="expiring">Expiring soon</TabsTrigger>
          <TabsTrigger value="missing">Missing expiry / cost</TabsTrigger>
          <TabsTrigger value="incidents">Medication incidents</TabsTrigger>
          <TabsTrigger value="recalls">Recalls</TabsTrigger>
        </TabsList>
        <TabsContent value="expired" className="mt-4"><ExpiredStockTab /></TabsContent>
        <TabsContent value="expiring" className="mt-4">
          <div className="rounded-xl border bg-card">
            <Table>
              <TableHeader><TableRow><TableHead>Drug</TableHead><TableHead>Batch</TableHead><TableHead className="text-right">Quantity</TableHead>
                <TableHead className="text-right">Value</TableHead><TableHead>Expires</TableHead><TableHead>Supplier</TableHead></TableRow></TableHeader>
              <TableBody>
                {(d.expiring ?? []).length === 0 && <TableRow><TableCell colSpan={6} className="py-6 text-center text-sm text-muted-foreground">Nothing expires in the next 90 days.</TableCell></TableRow>}
                {(d.expiring ?? []).map((b: Dict) => (
                  <TableRow key={b.id}>
                    <TableCell className="font-medium">{b.drug}</TableCell><TableCell className="font-mono text-xs">{b.batch_number}</TableCell>
                    <TableCell className="text-right tabular-nums">{Number(b.quantity_on_hand).toLocaleString()}</TableCell>
                    <TableCell className="text-right tabular-nums">{M(b.value)}</TableCell>
                    <TableCell className={b.days_left <= 30 ? "text-red-600" : "text-amber-600"}>{fmtDay(b.expiry_date)} <span className="text-xs">({b.days_left} days)</span></TableCell>
                    <TableCell className="text-xs">{b.supplier ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
        <TabsContent value="missing" className="mt-4">
          <p className="mb-2 text-xs text-muted-foreground">A batch with no expiry date cannot be watched for expiry ("no expiry recorded" is not "does not expire"); a batch with no cost is left out of the stock value and the books' opening stock. Correct them on Pharmacy › Inventory.</p>
          <div className="rounded-xl border bg-card">
            <Table>
              <TableHeader><TableRow><TableHead>Drug</TableHead><TableHead>Batch</TableHead><TableHead className="text-right">Quantity</TableHead><TableHead>Missing</TableHead><TableHead>Received</TableHead></TableRow></TableHeader>
              <TableBody>
                {(d.missing_list ?? []).length === 0 && <TableRow><TableCell colSpan={5} className="py-6 text-center text-sm text-muted-foreground">Every batch on the shelf has an expiry date and a cost.</TableCell></TableRow>}
                {(d.missing_list ?? []).map((b: Dict) => (
                  <TableRow key={b.id}>
                    <TableCell className="font-medium">{b.drug}</TableCell><TableCell className="font-mono text-xs">{b.batch_number}</TableCell>
                    <TableCell className="text-right tabular-nums">{Number(b.quantity_on_hand).toLocaleString()}</TableCell>
                    <TableCell className="space-x-1">{b.no_expiry && <Badge variant="outline" className="border-amber-400 text-amber-600">expiry date</Badge>}{b.no_cost && <Badge variant="outline">unit cost</Badge>}</TableCell>
                    <TableCell className="text-xs">{fmtDay(b.received_at) || "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
        <TabsContent value="incidents" className="mt-4">
          <div className="rounded-xl border bg-card">
            <Table>
              <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>What happened</TableHead><TableHead>Ward</TableHead><TableHead>Severity</TableHead><TableHead>Status</TableHead><TableHead /></TableRow></TableHeader>
              <TableBody>
                {(d.medication_incidents ?? []).length === 0 && <TableRow><TableCell colSpan={6} className="py-6 text-center text-sm text-muted-foreground">No medication incidents recorded.</TableCell></TableRow>}
                {(d.medication_incidents ?? []).map((x: Dict) => (
                  <TableRow key={x.id}>
                    <TableCell className="text-xs">{fmtDay(x.date)}</TableCell><TableCell className="max-w-md text-sm">{x.description}</TableCell>
                    <TableCell className="text-xs">{x.ward ?? "—"}</TableCell><TableCell className="text-xs capitalize">{x.severity}</TableCell>
                    <TableCell><Badge variant="outline" className="capitalize">{String(x.status).replace(/_/g, " ")}</Badge></TableCell>
                    <TableCell className="text-right"><Link to={`/reports/new?type=incident&kind=incident&id=${x.id}`}><Button size="sm" variant="ghost">Report</Button></Link></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">Report a new medication incident on <Link className="text-primary hover:underline" to="/hospital/quality">Quality & Safety</Link> (category: medication error).</p>
        </TabsContent>
        <TabsContent value="recalls" className="mt-4">
          <div className="rounded-xl border bg-card p-4 text-sm">
            <p>A recall is opened on the batch in Roy Books: the batch is frozen so it cannot be dispensed, every patient who received it is traced, and returns are tracked until the recall is closed.</p>
            <Link to="/finance/books/stock?tab=recalls"><Button className="mt-3" size="sm" variant="outline">Open recalls in Roy Books</Button></Link>
            <p className="mt-2 text-xs text-muted-foreground">Batches enter the books with the pharmacy's opening stock at go-live; until then a recall is recorded as an incident.</p>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
