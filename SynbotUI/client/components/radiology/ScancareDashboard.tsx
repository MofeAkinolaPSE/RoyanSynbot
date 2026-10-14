import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { BookOpen, Loader2, ReceiptText, Wallet, ScanLine, Users, Timer, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { MODALITY_COLORS } from "@/components/radiology/radiology-shared";

const naira = (v: any) => `₦${Number(v ?? 0).toLocaleString("en-NG", { maximumFractionDigits: 0 })}`;
const monthStart = () => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10); };
const todayIso = () => new Date().toISOString().slice(0, 10);

function Kpi({ label, value, sub, icon, tone }: { label: string; value: React.ReactNode; sub?: React.ReactNode; icon: React.ReactNode; tone?: string }) {
  return (
    <Card>
      <CardContent className="pt-5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className={cn("text-2xl font-bold", tone)}>{value}</p>
            {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
          </div>
          <span className="text-muted-foreground">{icon}</span>
        </div>
      </CardContent>
    </Card>
  );
}

/** Scancare's own dashboard: its studies, queue and turnaround, and its money (billed, collected, owed, books). */
export function ScancareDashboard() {
  const navigate = useNavigate();
  const [from, setFrom] = useState(monthStart());
  const [to, setTo] = useState(todayIso());
  const [history, setHistory] = useState(false);
  const { data: d, isLoading } = useQuery({
    queryKey: ["scancare-overview", from, to, history],
    queryFn: () => api.hospital.radiology.scancareOverview({ date_from: from, date_to: to, include_history: history }),
    refetchInterval: 60_000,
  });
  if (isLoading || !d) return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;
  const w = d.work ?? {}, qu = d.queue ?? {}, m = d.money ?? {};
  const maxMod = Math.max(1, ...(d.modalities ?? []).map((r: any) => Number(r.studies)));
  const payerTotal = (d.payers ?? []).reduce((n: number, p: any) => n + Number(p.revenue ?? 0), 0);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-2">
        <div><p className="text-xs text-muted-foreground">From</p><Input type="date" className="h-8 w-40" value={from} onChange={(e) => setFrom(e.target.value)} /></div>
        <div><p className="text-xs text-muted-foreground">To</p><Input type="date" className="h-8 w-40" value={to} onChange={(e) => setTo(e.target.value)} /></div>
        <label className="flex items-center gap-1.5 pb-1.5 text-xs text-muted-foreground">
          <input type="checkbox" checked={history} onChange={(e) => setHistory(e.target.checked)} /> Include Hope history (study counts, to Jan 2026)
        </label>
        <div className="ml-auto flex gap-2">
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => navigate("/finance/books?company=SCN")}><BookOpen className="h-3.5 w-3.5" /> Scancare Books</Button>
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => navigate("/hospital/billing")}><ReceiptText className="h-3.5 w-3.5" /> Billing &amp; Cashier</Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Studies" value={Number(w.studies ?? 0).toLocaleString()} icon={<ScanLine className="h-4 w-4" />}
          sub={`${Number(w.walk_ins ?? 0).toLocaleString()} walk-in · ${Number(w.referrals ?? 0).toLocaleString()} referred by Royan`} />
        <Kpi label="Waiting / in progress now" value={`${qu.waiting ?? 0} / ${qu.in_progress ?? 0}`} icon={<Users className="h-4 w-4" />}
          sub={`${qu.stat_open ?? 0} STAT open · ${qu.over_24h ?? 0} waiting over 24h`} tone={(qu.over_24h ?? 0) > 0 ? "text-amber-600" : undefined} />
        <Kpi label="Average report time" value={w.avg_tat != null ? `${Math.round(Number(w.avg_tat))} min` : "—"} icon={<Timer className="h-4 w-4" />}
          sub={`${Number(w.reported ?? 0).toLocaleString()} reported · ${w.cancelled ?? 0} cancelled`} />
        <Kpi label="Not billed (last 30 days)" value={(d.unbilled ?? []).length} icon={<AlertTriangle className="h-4 w-4" />}
          sub="studies with no Scancare bill" tone={(d.unbilled ?? []).length ? "text-red-600" : undefined} />
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Billed" value={naira(m.billed)} icon={<ReceiptText className="h-4 w-4" />} sub={`${m.bills ?? 0} bills · HMO ${naira(m.hmo)}`} />
        <Kpi label="Collected" value={naira(m.collected)} icon={<Wallet className="h-4 w-4" />} sub="cash, card and transfer received" tone="text-green-700 dark:text-green-400" />
        <Kpi label="Outstanding (all dates)" value={naira(m.outstanding)} icon={<Wallet className="h-4 w-4" />}
          sub={`${m.outstanding_bills ?? 0} bills awaiting payment`} tone={Number(m.outstanding) > 0 ? "text-red-600" : undefined} />
        <Kpi label="In Scancare's books" value={d.books?.live ? naira(d.books.revenue) : "not set up"} icon={<BookOpen className="h-4 w-4" />}
          sub={d.books?.live ? `revenue · expenses ${naira(d.books.expenses)}` : "Setup › Companies"} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Studies by modality</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {(d.modalities ?? []).length === 0 && <p className="text-xs text-muted-foreground">No studies in this period.</p>}
            {(d.modalities ?? []).map((r: any) => (
              <div key={r.modality} className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <Badge variant="outline" className={cn("text-xs uppercase", MODALITY_COLORS[r.modality] ?? "")}>{r.modality}</Badge>
                  <span className="font-semibold">{Number(r.studies).toLocaleString()}{r.avg_tat != null ? ` · ${Math.round(Number(r.avg_tat))} min` : ""}</span>
                </div>
                <div className="h-1.5 rounded bg-muted"><div className="h-1.5 rounded bg-primary" style={{ width: `${(Number(r.studies) / maxMod) * 100}%` }} /></div>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Who pays</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {(d.payers ?? []).length === 0 && <p className="text-xs text-muted-foreground">No Scancare bills in this period.</p>}
            {(d.payers ?? []).map((p: any) => (
              <div key={p.payer} className="flex items-center justify-between text-sm">
                <span className="capitalize">{p.payer === "hmo" ? "HMO" : p.payer}</span>
                <span className="font-semibold">{naira(p.revenue)} <span className="text-xs font-normal text-muted-foreground">
                  {payerTotal ? `${Math.round((Number(p.revenue) / payerTotal) * 100)}%` : ""} · {p.bills} bills</span></span>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Top studies by revenue</CardTitle></CardHeader>
          <CardContent className="space-y-1.5">
            {(d.top_studies ?? []).length === 0 && <p className="text-xs text-muted-foreground">No Scancare bills in this period.</p>}
            {(d.top_studies ?? []).map((t: any) => (
              <div key={t.description} className="flex items-center justify-between gap-2 text-xs">
                <span className="truncate">{t.description}</span>
                <span className="shrink-0 font-semibold">{naira(t.revenue)} <span className="font-normal text-muted-foreground">× {t.studies}</span></span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

/** Studies done or booked without a Scancare bill: walk-in clients and referrals the doctor has not sent to the cashier. */
export function ScancareToBill() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const { data, isLoading } = useQuery({ queryKey: ["scancare-overview", "unbilled"], queryFn: () => api.hospital.radiology.scancareOverview() });
  const bill = useMutation({
    mutationFn: (id: number) => api.hospital.radiology.billStudy(id),
    onSuccess: (r: any) => {
      toast({ title: `Scancare bill ${r?.bill?.bill_number ?? ""} raised`, description: `${naira(r?.bill?.patient_balance)} to pay at the cashier` });
      void qc.invalidateQueries({ queryKey: ["scancare-overview"] });
      if (r?.bill?.id) window.open(`#/hospital/billing/${r.bill.id}/invoice`, "_blank");
    },
    onError: (e: any) => toast({ title: "Could not bill the study", description: e.message, variant: "destructive" }),
  });
  const rows: any[] = data?.unbilled ?? [];
  return (
    <Card>
      <CardContent className="p-0">
        {isLoading ? <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div> : (
          <Table>
            <TableHeader><TableRow>
              <TableHead>Order #</TableHead><TableHead>Client</TableHead><TableHead>Study</TableHead><TableHead>Source</TableHead><TableHead>Status</TableHead><TableHead />
            </TableRow></TableHeader>
            <TableBody>
              {rows.length === 0 && <TableRow><TableCell colSpan={6} className="py-10 text-center text-muted-foreground">Every study in the last 30 days is on a Scancare bill.</TableCell></TableRow>}
              {rows.map((o) => (
                <TableRow key={o.id}>
                  <TableCell className="font-mono text-xs">#{o.id}</TableCell>
                  <TableCell className="text-sm">{o.patient_name ?? `ID ${o.patient_id}`}<span className="block font-mono text-xs text-muted-foreground">{o.mrn}</span></TableCell>
                  <TableCell className="text-sm">{o.test_name ?? o.modality ?? "—"}</TableCell>
                  <TableCell className="text-xs">{o.encounter_id ? "Referred by Royan" : "Walk-in"}</TableCell>
                  <TableCell className="text-xs capitalize">{String(o.status ?? "").replace(/_/g, " ")}</TableCell>
                  <TableCell>
                    <Button size="sm" className="h-7 gap-1 text-xs" disabled={bill.isPending} onClick={() => bill.mutate(o.id)}>
                      <ReceiptText className="h-3 w-3" /> Bill study
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
