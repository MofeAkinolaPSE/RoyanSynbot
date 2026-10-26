/**
 * Executive overview - the Medical Director / CEO / CFO control centre (reportGUide.md s11).
 *
 * One page read live from the modules that own each figure: Roy Books (income statement, cash,
 * controls, stock), what HMOs and corporates owe, HMO vs private billing, patients and beds,
 * pharmacy, quality & safety, people. Nothing here is typed in or estimated, every block says
 * the date its data reaches, and every figure opens the page where it is dealt with.
 */
import { ReactNode, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  AlertOctagon, AlertTriangle, ArrowDownRight, ArrowUpRight, Banknote, BedDouble, BookOpen, Boxes, Building2, ChevronRight,
  ClipboardCheck, HeartPulse, Info, Landmark, Loader2, Pill, RefreshCw, ShieldCheck, TrendingUp, Users, Wallet,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api-client";
import { ShowMeHow } from "@/components/tour/ShowMeHow";
import { useRealtimeChannel } from "@/hooks/use-realtime-channel";

type Dict = Record<string, any>;

const M = (v: any, dp = 1) => {
  const n = Number(v ?? 0);
  if (!Number.isFinite(n)) return "—";
  const a = Math.abs(n);
  if (a >= 1e9) return `₦${(n / 1e9).toFixed(2)}bn`;
  if (a >= 1e6) return `₦${(n / 1e6).toFixed(dp)}M`;
  if (a >= 1e3) return `₦${(n / 1e3).toFixed(0)}k`;
  return `₦${n.toFixed(0)}`;
};
const pct = (v: any) => (v === null || v === undefined ? "—" : `${Number(v).toFixed(1)}%`);
const n0 = (v: any) => (v === null || v === undefined ? "—" : Number(v).toLocaleString());
const d8 = (v?: string | null) => (v ? new Date(String(v).slice(0, 10) + "T12:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "—");
const monthName = (p: string) => new Date(p + "-15").toLocaleDateString("en-GB", { month: "short", year: "2-digit" });

function Delta({ v, suffix = "" }: { v: number | null | undefined; suffix?: string }) {
  if (v === null || v === undefined || !Number.isFinite(v)) return null;
  const up = v >= 0;
  return (
    <span className={`inline-flex items-center text-xs font-medium ${up ? "text-emerald-600" : "text-red-600"}`}>
      {up ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}{Math.abs(v).toFixed(1)}%{suffix}
    </span>
  );
}

const TONE: Record<string, string> = { danger: "text-red-600", warning: "text-amber-600", good: "text-emerald-600" };

/** A headline figure: label with its period, one value, one line of context. Opens the page that owns it. */
function Tile({ label, value, sub, to, tone, icon: Icon }: { label: string; value: ReactNode; sub?: ReactNode; to?: string; tone?: string; icon?: any }) {
  const nav = useNavigate();
  return (
    <button onClick={() => to && nav(to)} disabled={!to}
            className={`group flex flex-col rounded-xl border bg-card p-4 text-left shadow-sm transition-all ${to ? "hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-md" : "cursor-default"}`}>
      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>{label}</span>{Icon && <Icon className="h-4 w-4 shrink-0 opacity-70" />}
      </div>
      <div className={`mt-1.5 text-2xl font-bold tabular-nums tracking-tight ${tone ? TONE[tone] : ""}`}>{value}</div>
      {sub && <div className="mt-1 text-xs leading-snug text-muted-foreground">{sub}</div>}
    </button>
  );
}

function Panel({ title, to, linkLabel, icon: Icon, children, className = "", note }: { title: ReactNode; to?: string; linkLabel?: string; icon?: any; children: ReactNode; className?: string; note?: ReactNode }) {
  return (
    <section className={`rounded-xl border bg-card p-4 shadow-sm ${className}`}>
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold">{Icon && <Icon className="h-4 w-4 text-primary" />}{title}</h3>
          {note && <p className="mt-0.5 text-xs text-muted-foreground">{note}</p>}
        </div>
        {to && <Link to={to} className="flex shrink-0 items-center text-xs text-primary hover:underline">{linkLabel ?? "Open"}<ChevronRight className="h-3 w-3" /></Link>}
      </div>
      {children}
    </section>
  );
}

function Row({ label, value, tone, to }: { label: ReactNode; value: ReactNode; tone?: string; to?: string }) {
  const inner = (
    <div className={`flex items-center justify-between gap-3 py-1.5 text-sm ${to ? "hover:text-primary" : ""}`}>
      <span className="text-muted-foreground">{label}</span><span className={`text-right font-medium tabular-nums ${tone ? TONE[tone] : ""}`}>{value}</span>
    </div>
  );
  return to ? <Link to={to}>{inner}</Link> : inner;
}

function Unavailable({ what }: { what: string }) {
  return <p className="text-sm text-muted-foreground">{what} could not be read just now - the rest of the page is unaffected.</p>;
}

function Bar100({ parts }: { parts: { label: string; value: number; cls: string }[] }) {
  const total = parts.reduce((s, p) => s + Math.max(0, p.value), 0) || 1;
  return (
    <div>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-muted">
        {parts.map((p) => <div key={p.label} className={p.cls} style={{ width: `${(Math.max(0, p.value) / total) * 100}%` }} title={`${p.label}: ${M(p.value)}`} />)}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
        {parts.map((p) => <span key={p.label} className="inline-flex items-center gap-1"><span className={`h-2 w-2 rounded-full ${p.cls}`} />{p.label} {M(p.value)}</span>)}
      </div>
    </div>
  );
}

const LEVEL: Record<string, { icon: any; cls: string }> = {
  critical: { icon: AlertOctagon, cls: "text-red-600" },
  action: { icon: AlertTriangle, cls: "text-amber-600" },
  info: { icon: Info, cls: "text-sky-600" },
};

export default function Executive() {
  const qc = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const q = useQuery({ queryKey: ["executive-overview"], queryFn: () => api.dashboard.executive(), refetchInterval: 300_000 });
  const refresh = async () => {
    setRefreshing(true);
    try { qc.setQueryData(["executive-overview"], await api.dashboard.executive(true)); } finally { setRefreshing(false); }
  };
  // Another user's change elsewhere invalidates the page; the server cache still bounds the cost.
  const stale = () => { void qc.invalidateQueries({ queryKey: ["executive-overview"] }); };
  useRealtimeChannel("finance_updates", stale);
  useRealtimeChannel("workspace_updates", stale);
  useRealtimeChannel("alerts_updates", stale);
  useRealtimeChannel("inventory_updates", stale);

  if (q.isLoading) return <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;
  const d: Dict | undefined = q.data;
  if (!d) return <p className="p-6 text-sm text-destructive">The executive overview could not be loaded{(q.error as any)?.message ? `: ${(q.error as any).message}` : ""}.</p>;

  const f: Dict = d.finance ?? {}, debt: Dict = d.debtors ?? {}, bill: Dict = d.billing ?? {}, pat: Dict = d.patients ?? {};
  const ph: Dict = d.pharmacy ?? {}, ql: Dict = d.quality ?? {}, p: Dict = d.people ?? {};
  const st: Dict = f.stock ?? {}, ctl: Dict = f.controls ?? {}, ap: Dict = f.payables ?? {};
  const attention: Dict[] = d.attention ?? [];
  const critical = attention.filter((a) => a.level === "critical").length;
  const trend = (bill.months ?? []).map((t: Dict) => ({ ...t, label: monthName(t.period) }));
  const last: Dict | null = bill.last_month ?? null;
  const lastVsLy = last && last.last_year ? ((last.total - last.last_year) / last.last_year) * 100 : null;
  const stockValue = st.in_books ? st.books_value : st.shelf_value;

  return (
    <div className="flex flex-col gap-5">
      {/* header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight">Executive overview</h1>
            <ShowMeHow only={["journey-hospital"]} label="Follow a patient through Royan" />
          </div>
          <p className="text-sm text-muted-foreground">
            The Royan Hospital on one page, read live from Roy Books and every department · updated{" "}
            {new Date(d.generated_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}
          </p>
        </div>
        <Link to="/reports/new?type=executive&kind=current&id=now" className="ml-auto"><Button size="sm" variant="outline">Executive report</Button></Link>
        <Button size="sm" variant="outline" onClick={refresh} disabled={refreshing}>
          <RefreshCw className={`mr-1.5 h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />Refresh
        </Button>
      </div>

      {f && !f.live && (
        <div className="flex gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm dark:border-amber-500/40 dark:bg-amber-500/10">
          <BookOpen className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
          <div>
            <div className="font-semibold">Roy Books is not live yet: the ledger ends {d8(f.books_to)}, hospital billing (Hope) ends {d8(f.hope_to)}</div>
            <div className="text-muted-foreground">
              Profit, cash and the income statement below are for {f.period?.label}. Billing and what HMOs owe run to {d8(bill.as_of)}.
              Nothing after those dates is missing trade - it is not loaded yet. Today's patients, beds, pharmacy, quality and staff are live.{" "}
              <Link to="/finance/books/setup" className="text-primary hover:underline">Roy Books setup</Link>
            </div>
          </div>
        </div>
      )}

      {/* 1. money */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Tile label={`Billed, 12 months to ${d8(bill.as_of)}`} icon={TrendingUp} to={`/finance/books/reports?r=payer-mix`}
              value={M(bill.billed_12m)} sub={<>{pct(bill.hmo_share_pct)} to HMOs & corporates · {n0(bill.visits_12m)} visits</>} />
        <Tile label={`Revenue in the books, ${f.period?.label ?? ""}`} icon={Landmark} to="/finance/books/statements"
              value={M(f.revenue)} sub={<><Delta v={f.revenue_growth_pct} /> vs same point a year earlier ({M(f.revenue_prior)})</>} />
        <Tile label={`Net profit, ${f.period?.label ?? ""}`} icon={Building2} to="/finance/books/statements"
              tone={f.net_profit < 0 ? "danger" : "good"} value={M(f.net_profit)}
              sub={`${pct(f.net_margin_pct)} of revenue · gross margin ${pct(f.gross_margin_pct)}`} />
        <Tile label={`Cash & bank at ${d8(f.cash_on)}`} icon={Wallet} to="/finance/books/banking"
              value={M(f.cash)} sub={`${(f.banks ?? []).length} accounts holding money`} />
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {/* Since go-live: the HMO pays the whole bill (the patient only signs the claims form), so HMOs owe Royan until
            they settle their monthly claims. The pre-go-live Hope balance is shown apart - it waits for the 2025
            Sage receipts and is not money known to be overdue. */}
        <Tile label={`HMOs & corporates owe us since go-live (at ${d8(debt.as_of)})`} icon={Banknote} to="/finance/ar"
              tone={debt.over_90_pct >= 30 ? "warning" : undefined} value={M(debt.total)}
              sub={`${debt.total ? `${pct(debt.over_90_pct)} over 90 days · ` : ""}${n0(debt.payers)} payers · patients owe ${M(debt.patients_owe ?? 0)}${debt.legacy?.total ? ` · pre-go-live HMO balance ${M(debt.legacy.total)} to reconcile` : ""}`} />
        <Tile label="We owe suppliers" icon={Building2} to="/finance/books/purchases"
              tone={ap.overdue > 0 ? "warning" : undefined}
              value={ap.tracked ? M(ap.total) : "—"}
              sub={ap.tracked ? (ap.overdue ? `${M(ap.overdue)} past due` : "nothing past due") : "supplier balances start in Roy Books at go-live"} />
        <Tile label={st.in_books ? "Pharmacy stock (books, cost)" : "Pharmacy stock on the shelves (cost)"} icon={Boxes} to="/finance/books/stock"
              tone={st.expired_value > 0 ? "warning" : undefined} value={M(stockValue)}
              sub={st.expired_value > 0 ? `${M(st.expired_value)} already expired · ${M(st.expiring_90_value)} more within 90 days` : `${n0(st.shelf_products)} products in stock`} />
        <Tile label="Beds occupied now" icon={BedDouble} to="/hospital/wards"
              value={pat.beds_total ? `${n0(pat.beds_occupied)} / ${n0(pat.beds_total)}` : "—"}
              sub={`${pct(pat.occupancy_pct)} occupancy · ${n0(pat.admissions_pending)} admissions waiting`} />
      </div>

      {/* 2. attention + billing trend */}
      <div className="grid gap-4 xl:grid-cols-5">
        <Panel title={<>Needs your attention{critical ? <span className="ml-1 text-red-600">· {critical} critical</span> : null}</>} icon={AlertTriangle} className="xl:col-span-2">
          {attention.length === 0 ? <p className="text-sm text-muted-foreground">Nothing needs escalating.</p> : (
            <ul className="space-y-0.5">
              {(showAll ? attention : attention.slice(0, 7)).map((a, i) => {
                const L = LEVEL[a.level] ?? LEVEL.info;
                return (
                  <li key={i}>
                    <Link to={a.link} className="flex gap-2.5 rounded-lg px-2 py-2 hover:bg-muted/50">
                      <L.icon className={`mt-0.5 h-4 w-4 shrink-0 ${L.cls}`} />
                      <span className="min-w-0">
                        <span className="block text-sm font-medium">{a.title}</span>
                        {a.detail && <span className="block text-xs text-muted-foreground">{a.detail}</span>}
                      </span>
                    </Link>
                  </li>
                );
              })}
              {attention.length > 7 && (
                <li><button onClick={() => setShowAll((v) => !v)} className="px-2 py-1 text-xs text-primary hover:underline">
                  {showAll ? "Show fewer" : `Show all ${attention.length}`}
                </button></li>
              )}
            </ul>
          )}
        </Panel>
        <Panel title="Billed by month - private and HMO, with the same month a year earlier" icon={TrendingUp}
               to="/finance/books/reports?r=payer-mix" linkLabel="HMO vs private report" className="xl:col-span-3"
               note={`Hope charge lines, billed less discount, to ${d8(bill.as_of)}${bill.last_month_partial ? " (last month is part of a month)" : ""}`}>
          {!d.billing ? <Unavailable what="Billing" /> : (
            <>
              <div className="mb-2 grid grid-cols-3 gap-2 text-center">
                <div className="rounded-lg bg-muted/40 p-2">
                  <div className="text-xs text-muted-foreground">{last ? monthName(last.period) : "—"}{bill.last_month_partial ? " (part)" : ""}</div>
                  <div className="font-semibold">{M(last?.total)}</div>
                  <div className="text-xs">{lastVsLy !== null && !bill.last_month_partial ? <Delta v={lastVsLy} suffix=" vs a year earlier" /> : <span className="text-muted-foreground">{n0(last?.visits)} visits</span>}</div>
                </div>
                <div className="rounded-lg bg-muted/40 p-2">
                  <div className="text-xs text-muted-foreground">Private patients, 12 months</div>
                  <div className="font-semibold">{M(bill.private_12m)}</div>
                </div>
                <div className="rounded-lg bg-muted/40 p-2">
                  <div className="text-xs text-muted-foreground">HMOs & corporates, 12 months</div>
                  <div className="font-semibold">{M(bill.hmo_12m)}</div>
                </div>
              </div>
              <div className="h-60">
                <ResponsiveContainer>
                  <ComposedChart data={trend} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-muted" />
                    <XAxis dataKey="label" fontSize={10} tickLine={false} axisLine={false} />
                    <YAxis fontSize={10} tickLine={false} axisLine={false} width={44} tickFormatter={(v) => `${Math.round(v / 1e6)}M`} />
                    <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} formatter={(v: any, n: string) => [M(v), n]} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Bar dataKey="private" name="Private" stackId="b" fill="hsl(var(--primary))" />
                    <Bar dataKey="hmo" name="HMO" stackId="b" fill="#0ea5e9" />
                    <Bar dataKey="corporate" name="Corporate" stackId="b" fill="#a78bfa" />
                    <Bar dataKey="staff" name="Staff schemes" stackId="b" fill="#94a3b8" radius={[3, 3, 0, 0]} />
                    <Line dataKey="last_year" name="Same month a year earlier" stroke="#f59e0b" strokeWidth={2} strokeDasharray="4 3" dot={false} connectNulls />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </Panel>
      </div>

      {/* 3. money detail */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="What HMOs and corporates owe since go-live, by age" icon={Banknote} to="/finance/ar" linkLabel="Credit control"
               note={`At ${d8(debt.as_of)} · ${debt.source ?? ""}`}>
          {!d.debtors ? <Unavailable what="Debtors" /> : (
            <>
              <Bar100 parts={[
                { label: "0–30", value: debt.buckets?.["0_30"] ?? 0, cls: "bg-emerald-500" },
                { label: "31–60", value: debt.buckets?.["31_60"] ?? 0, cls: "bg-lime-500" },
                { label: "61–90", value: debt.buckets?.["61_90"] ?? 0, cls: "bg-amber-500" },
                { label: "90+", value: debt.buckets?.["91_plus"] ?? 0, cls: "bg-red-500" },
              ]} />
              <div className="mt-3 divide-y border-t">
                {(debt.top ?? []).length === 0 && <p className="py-2 text-sm text-foreground/75">No HMO or corporate claims open since go-live.</p>}
                {(debt.top ?? []).slice(0, 6).map((r: Dict) => (
                  <Row key={`${r.payer_id}-${r.name}`} label={<span className="block max-w-[200px] truncate">{r.name}</span>} value={M(r.owed)} to="/finance/ar" />
                ))}
              </div>
              {debt.legacy?.total > 0 && (
                <div className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-2.5 text-xs dark:border-amber-500/40 dark:bg-amber-500/10">
                  <p className="font-semibold">Pre-go-live HMO balance to reconcile: {M(debt.legacy.total)} ({n0(debt.legacy.payers)} HMOs)</p>
                  <p className="mt-0.5">Hope's HMO billing to {d8(debt.legacy.billed_to)} less the HMO payments in Sage, which are loaded only to {d8(debt.legacy.receipts_to)}.
                    Payments after that are not loaded yet, so this is not money known to be overdue.</p>
                </div>
              )}
            </>
          )}
        </Panel>
        <Panel title="Cash by account" icon={Wallet} to="/finance/books/banking" linkLabel="Banking" note={`At ${d8(f.cash_on)}, from the ledger`}>
          {!d.finance ? <Unavailable what="Roy Books" /> : (
            <>
              <div className="max-h-64 divide-y overflow-y-auto pr-1">
                {(f.banks ?? []).map((b: Dict) => <Row key={b.code} label={<span className="block max-w-[200px] truncate">{b.name}</span>} value={M(b.balance, 2)} tone={b.balance < 0 ? "danger" : undefined} />)}
              </div>
              <div className="mt-2 flex justify-between border-t pt-2 text-sm font-semibold"><span>Total</span><span>{M(f.cash, 2)}</span></div>
            </>
          )}
        </Panel>
        <Panel title="Books & controls" icon={ClipboardCheck} to="/finance/books/close" linkLabel="Close & controls">
          <Row label="Roy Books live" value={f.live ? `yes, since ${d8(f.cutover)}` : "not yet"} tone={f.live ? "good" : "warning"} to="/finance/books/setup" />
          <Row label="Ledger reaches" value={d8(f.books_to)} tone={f.missing_months ? "warning" : undefined} />
          <Row label="Months with no books" value={f.missing_months || "none"} tone={f.missing_months ? "warning" : undefined} />
          <Row label="Hospital transactions not posted" value={f.live ? n0(ctl.failed_postings) : "posting starts at go-live"} tone={ctl.failed_postings ? "danger" : undefined} to="/finance/books/close" />
          <Row label="Bank accounts reconciled" value={`${n0(ctl.reconciled)} of ${n0(ctl.bank_accounts_holding)}`} to="/finance/books/banking" />
          <Row label="Last reconciliation" value={ctl.last_reconciled ? d8(ctl.last_reconciled) : "never"} />
          <Row label="Drafts not yet posted" value={n0(ctl.drafts)} to="/finance/books" />
          <Row label="Stock: books less shelves" value={st.in_books ? M(st.difference) : "opens from the shelves at go-live"} tone={st.in_books && Math.abs(st.difference) >= 1 ? "danger" : undefined} to="/finance/books/stock" />
        </Panel>
      </div>

      {/* 4. who pays */}
      <Panel title={`HMOs and corporates billed most, 12 months to ${d8(bill.as_of)}`} icon={Building2} to="/finance/books/reports?r=hmo-monthly-bill" linkLabel="HMO monthly bills">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-muted-foreground">
              <th className="pb-1 font-medium">Payer</th><th className="pb-1 font-medium">Type</th><th className="pb-1 text-right font-medium">Billed</th>
              <th className="pb-1 text-right font-medium">Share of all billing</th><th className="pb-1 text-right font-medium">Patients</th>
            </tr></thead>
            <tbody className="divide-y">
              {(bill.top_payers ?? []).map((x: Dict) => (
                <tr key={x.id}>
                  <td className="max-w-[260px] truncate py-1.5">{x.name}</td>
                  <td className="py-1.5 text-xs text-muted-foreground">{x.payer_type === "CORPORATE" ? "Corporate" : "HMO"}</td>
                  <td className="py-1.5 text-right tabular-nums">{M(x.billed)}</td>
                  <td className="py-1.5 text-right tabular-nums">{pct(x.share_pct)}</td>
                  <td className="py-1.5 text-right tabular-nums">{n0(x.patients)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* 5. departments */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Panel title="Patients today" icon={HeartPulse} to="/hospital/queue" linkLabel="Queue & flow" note="Live, recorded in this system">
          {!d.patients ? <Unavailable what="Patient flow" /> : (
            <>
              <Row label="Waiting now" value={n0(pat.patients_waiting)} to="/hospital/queue?status=waiting" />
              <Row label="With a doctor now" value={n0(pat.active_consultations)} to="/hospital/queue?status=consulting" />
              <Row label="Seen and discharged today" value={n0(pat.patients_seen_today)} />
              <Row label="Average wait to triage" value={pat.avg_wait_minutes ? `${Number(pat.avg_wait_minutes).toFixed(0)} min` : "none recorded today"}
                   tone={pat.avg_wait_minutes > 60 ? "danger" : pat.avg_wait_minutes > 30 ? "warning" : undefined} />
              <Row label="Appointments today" value={n0(pat.appointments_today)} to="/hospital/appointments" />
              <Row label="Lab orders in progress" value={n0(pat.lab_orders_pending)} to="/hospital/lab" />
              <Row label="Prescriptions to dispense" value={n0(pat.prescriptions_pending)} to="/hospital/pharmacy" />
              <Row label="Beds occupied" value={`${n0(pat.beds_occupied)} of ${n0(pat.beds_total)}`} to="/hospital/wards" />
              <Row label="Patients on record" value={`${n0(pat.patients_registered)}${pat.patients_new_30d ? ` · ${n0(pat.patients_new_30d)} new in 30 days` : ""}`} to="/hospital/patients" />
            </>
          )}
        </Panel>
        <Panel title="Pharmacy & stock" icon={Pill} to="/hospital/pharmacy/inventory" linkLabel="Pharmacy inventory">
          {!d.pharmacy && !st.shelf_value ? <Unavailable what="Pharmacy" /> : (
            <>
              <Row label="Stock on the shelves (cost)" value={M(st.shelf_value)} to="/finance/books/stock" />
              <Row label="Products in stock" value={n0(st.shelf_products)} />
              <Row label="At critical stock" value={n0(ph.critical)} tone={ph.critical ? "danger" : undefined} />
              <Row label="Running low (warning)" value={n0(ph.tiers?.WARNING)} tone={ph.tiers?.WARNING ? "warning" : undefined} />
              <Row label="Expired, still on the shelf" value={`${M(st.expired_value)} · ${n0(st.expired_products)} products`} tone={st.expired_value ? "danger" : undefined} />
              <Row label="Expiring within 90 days" value={M(st.expiring_90_value)} tone={st.expiring_90_value ? "warning" : undefined} />
              <Row label="Batches with no expiry recorded" value={n0(st.shelf_no_expiry_batches)} tone={st.shelf_no_expiry_batches ? "warning" : undefined} />
              <Row label="Batches with no cost recorded" value={n0(st.shelf_uncosted_batches)} tone={st.shelf_uncosted_batches ? "warning" : undefined} />
              <Row label="Reorders open" value={n0(ph.replenishment_open)} />
            </>
          )}
        </Panel>
        <Panel title="Quality & safety" icon={ShieldCheck} to="/hospital/quality" linkLabel="Quality & safety">
          {!d.quality ? <Unavailable what="Quality" /> : (
            <>
              <div className="mb-2 flex items-center gap-3">
                <div className={`text-3xl font-bold ${ql.compliance_score >= 85 ? "text-emerald-600" : ql.compliance_score >= 70 ? "text-amber-600" : "text-red-600"}`}>{ql.compliance_score}</div>
                <div className="text-xs text-muted-foreground" title="100 less 8 per overdue audit, 4 per overdue maintenance job, 3 per open incident (+3 if open over 14 days), 5 per open serious incident">
                  compliance score<br />from what is overdue or open today
                </div>
              </div>
              <Row label="Incidents open" value={`${n0(ql.incidents?.open)}${ql.incidents?.open_over_14d ? ` (${ql.incidents.open_over_14d} over 14 days)` : ""}`} tone={ql.incidents?.open ? "warning" : undefined} to="/hospital/quality" />
              <Row label="Serious incidents open" value={n0(ql.incidents?.open_serious)} tone={ql.incidents?.open_serious ? "danger" : undefined} to="/hospital/quality" />
              <Row label="Reported, last 30 days" value={n0(ql.incidents?.reported_30d)} />
              <Row label="Hospital-acquired infections, 30 days" value={n0(ql.infection?.hai_30d)} tone={ql.infection?.hai_30d ? "warning" : undefined} />
              <Row label="Audits overdue / next 30 days" value={`${n0(ql.audits?.overdue)} / ${n0(ql.audits?.due_30)}`} tone={ql.audits?.overdue ? "danger" : undefined} to="/hospital/audits-maintenance" />
              <Row label="Maintenance overdue" value={n0(ql.maintenance?.overdue)} tone={ql.maintenance?.overdue ? "warning" : undefined} to="/hospital/audits-maintenance" />
              <Row label="HEFAMAA self-assessment" value={ql.hefamaa?.avg_score != null ? `${ql.hefamaa.avg_score}% avg · ${n0(ql.hefamaa.assessments)} done` : "none recorded"} />
            </>
          )}
        </Panel>
        <Panel title="People & work" icon={Users} to="/hr" linkLabel="HR">
          {!d.people ? <Unavailable what="HR" /> : (
            <>
              <Row label="Staff" value={n0(p.headcount)} to="/hr?tab=directory" />
              <Row label="Online / on the clock now" value={`${n0(p.online)} / ${n0(p.on_clock)}`} to="/workspace?tab=team" />
              <Row label="Rostered today / on leave today" value={`${n0(p.rostered_today)} / ${n0(p.on_leave_today)}`} to="/hr?tab=shifts" />
              <Row label="Hours this week" value={`${Number(p.hours_week ?? 0).toFixed(1)}h · ${n0(p.people_with_hours)} people`} to="/hr" />
              <Row label="Timesheets / leave to decide" value={`${n0(p.pending_timesheets)} / ${n0(p.pending_leave)}`} to="/hr?tab=timesheets" />
              <Row label="Open tasks (overdue)" value={`${n0(p.open_tasks)} (${n0(p.overdue_tasks)})`} tone={p.overdue_tasks ? "warning" : undefined} to="/workspace?tab=team" />
              <Row label="Requests open (late)" value={`${n0(p.open_requests)} (${n0(p.overdue_requests)})`} />
              <Row label="Staff with no salary recorded" value={n0(p.no_salary)} tone={p.no_salary ? "warning" : undefined} to="/hr?tab=directory" />
              <Row label="Payroll, last month" value={p.payroll_last_month ? `${M(p.payroll_last_month.cost)} · ${n0(p.payroll_last_month.records)} staff` : "not prepared"} to="/hr?tab=payroll" />
            </>
          )}
        </Panel>
      </div>

      <p className="text-xs text-muted-foreground">
        Every figure is read from the module that owns it - nothing on this page is typed in or estimated. Profit and cash: the Roy Books
        ledger (Sage history plus the books). Billing and HMO debt: Hope's charge lines less receipts in Sage until go-live, then the books.
        Stock: the pharmacy's live batches at cost, reconciled to the books after go-live. Built in {d.build_seconds}s; refreshed every 5 minutes.
        {(d.unavailable ?? []).length > 0 && <span className="text-amber-600"> Not available just now: {d.unavailable.join(", ")}.</span>}
      </p>
    </div>
  );
}
