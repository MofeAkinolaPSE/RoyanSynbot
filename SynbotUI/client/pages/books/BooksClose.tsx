import { useSearchParams } from "react-router-dom";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Lock, RefreshCw, Unlock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DetailSheet } from "@/components/workspace/DetailSheet";
import { FilterBar } from "@/components/workspace/FilterBar";
import { BooksShell } from "@/components/books/BooksShell";
import { DataIssues } from "@/components/books/data-issues";
import { act, CsvButton, DateRange, Empty, ErrorNote, Loading, Section, StatusBadge, useBooks } from "@/components/books/kit";
import { books, BooksError, Dict, fmtDate, monthStart, today } from "@/lib/books-api";
import { askText, askConfirm } from "@/lib/ask";

export default function BooksClose() {
  const [params] = useSearchParams();
  const [tab, setTab] = useState(params.get("tab") ?? "periods");
  return (
    <BooksShell title="Close & Controls">
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap">
          <TabsTrigger value="data-issues">Data issues</TabsTrigger>
          <TabsTrigger value="periods">Periods & year end</TabsTrigger>
          <TabsTrigger value="controls">Integrity monitor</TabsTrigger>
          <TabsTrigger value="operations">Hospital postings</TabsTrigger>
          <TabsTrigger value="exceptions">Exceptions</TabsTrigger>
          <TabsTrigger value="audit">Audit trail</TabsTrigger>
        </TabsList>
        <TabsContent value="data-issues"><DataIssues /></TabsContent>
        <TabsContent value="periods"><Periods /></TabsContent>
        <TabsContent value="controls"><Controls /></TabsContent>
        <TabsContent value="operations"><Operations /></TabsContent>
        <TabsContent value="exceptions"><Exceptions /></TabsContent>
        <TabsContent value="audit"><Audit /></TabsContent>
      </Tabs>
    </BooksShell>
  );
}

function CheckList({ items }: { items: Dict[] }) {
  return (
    <ul className="space-y-2">
      {items.map((c) => (
        <li key={c.code} className="flex items-start gap-2 text-sm">
          {c.status === "PASS" ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
            : <AlertTriangle className={`mt-0.5 h-4 w-4 shrink-0 ${c.blocking ? "text-red-600" : "text-amber-500"}`} />}
          <div>
            <span className="font-medium">{c.title}.</span> <span className="text-muted-foreground">{c.message}</span>
            {c.status === "FAIL" && <span className={`ml-1 text-xs font-semibold uppercase ${c.blocking ? "text-red-600" : "text-amber-600"}`}>{c.blocking ? "blocks close" : "warning"}</span>}
            {c.status === "FAIL" && Object.keys(c.details ?? {}).length > 0 && (
              <details className="mt-1 text-xs"><summary className="cursor-pointer text-muted-foreground">details</summary>
                <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-muted p-2">{JSON.stringify(c.details, null, 2)}</pre></details>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

function Periods() {
  const qc = useQueryClient();
  const { data: years, isLoading, error, refetch } = useBooks<Dict[]>(["periods"], "/periods");
  const [period, setPeriod] = useState<Dict | null>(null);
  const done = () => { refetch(); qc.invalidateQueries({ queryKey: ["books"] }); };
  const reopen = async (p: Dict) => {
    const reason = await askText(`Why is ${p.name} being reopened?`);
    if (reason && (await act(() => books.post(`/periods/${p.id}/reopen`, { reason }), `${p.name} reopened`))) done();
  };
  const closeYear = async (y: Dict) => {
    if (!await askConfirm(`Close ${y.name}? Income and expense balances will be moved to retained earnings and the next year opened. All its periods must be closed first.`)) return;
    if (await act(() => books.post(`/fiscal-years/${y.id}/close`, {}), `${y.name} closed`)) done();
  };
  const addYear = async () => {
    const last = years?.[0];
    const start = await askText("First day of the new fiscal year (YYYY-MM-DD)", last ? nextDay(last.end_date) : `${new Date().getFullYear()}-01-01`);
    if (start && (await act(() => books.post("/fiscal-years", { start_date: start }), "Fiscal year created"))) done();
  };
  return (
    <div className="space-y-4">
      {isLoading && <Loading />}<ErrorNote error={error} />
      {(years ?? []).map((y) => (
        <Section key={y.id} title={<span className="flex items-center gap-2">{y.name} <StatusBadge status={y.status} /></span>}
                 actions={y.status === "OPEN" ? <Button size="sm" variant="outline" onClick={() => closeYear(y)}>Year-end close</Button> : undefined}>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            {y.periods.map((p: Dict) => (
              <button key={p.id} onClick={() => setPeriod(p)} className={`rounded-lg border p-2 text-left text-sm hover:bg-muted/50 ${p.start_date <= today() && today() <= p.end_date ? "ring-2 ring-primary" : ""}`}>
                <div className="flex items-center justify-between font-medium">{p.name}{p.status === "OPEN" ? <Unlock className="h-3.5 w-3.5 text-emerald-600" /> : <Lock className="h-3.5 w-3.5 text-muted-foreground" />}</div>
                <div className="text-xs text-muted-foreground">{p.status.toLowerCase()}{p.closed_by ? ` by ${p.closed_by}` : ""}</div>
              </button>
            ))}
          </div>
        </Section>
      ))}
      <Button size="sm" variant="outline" onClick={addYear}>Add fiscal year</Button>
      <PeriodSheet period={period} onClose={() => setPeriod(null)} onReopen={reopen} onDone={done} />
    </div>
  );
}

function PeriodSheet({ period, onClose, onReopen, onDone }: { period: Dict | null; onClose: () => void; onReopen: (p: Dict) => void; onDone: () => void }) {
  const { data, isLoading, error, refetch } = useBooks<Dict>(["checklist", period?.id], `/periods/${period?.id}/checklist`, undefined, !!period && period.status === "OPEN");
  const [blocked, setBlocked] = useState<Dict | null>(null);
  const close = async (accept = false) => {
    setBlocked(null);
    try {
      await books.post(`/periods/${period?.id}/close`, { accept_warnings: accept });
      onDone(); onClose();
    } catch (e) {
      const err = e as BooksError;
      if (err.code === "CLOSE_BLOCKED") setBlocked({ message: err.message, ...(err.details ?? {}) }); else act(async () => { throw e; });
      refetch();
    }
  };
  const fails = (data?.checklist ?? []).filter((c: Dict) => c.status === "FAIL");
  const blocking = fails.filter((c: Dict) => c.blocking).length;
  return (
    <DetailSheet size="wide" open={!!period} onOpenChange={(o) => { if (!o) { setBlocked(null); onClose(); } }} title={period ? `Period ${period.name}` : ""}
                 description={period ? `${fmtDate(period.start_date)} – ${fmtDate(period.end_date)}` : ""}
                 footer={period?.status === "OPEN" ? <div className="flex gap-2">
                   {blocked && !blocked.blocking && blocked.warnings > 0 && <Button variant="outline" onClick={() => close(true)}>Accept warnings & close</Button>}
                   <Button disabled={blocking > 0} onClick={() => close(false)}><Lock className="mr-1 h-4 w-4" />Close period</Button></div>
                   : period ? <Button variant="outline" onClick={() => onReopen(period)}><Unlock className="mr-1 h-4 w-4" />Reopen</Button> : undefined}>
      {period?.status !== "OPEN" ? (
        <p className="text-sm text-muted-foreground">Closed {period?.closed_at ? new Date(period.closed_at).toLocaleString("en-GB") : ""} by {period?.closed_by}. No posting can land in this period until it is reopened (with a reason, recorded in the audit trail).</p>
      ) : (
        <div className="space-y-3">
          {isLoading && <Loading />}<ErrorNote error={error} />
          {blocked && <div className="rounded-lg border border-amber-400 bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">{blocked.message}: {blocked.blocking} blocking, {blocked.warnings} warning(s).</div>}
          <p className="text-sm text-muted-foreground">Close checklist — blocking items must be resolved; warnings can be accepted.</p>
          {data && <CheckList items={data.checklist} />}
        </div>
      )}
    </DetailSheet>
  );
}

function Controls() {
  const [asOf, setAsOf] = useState(today());
  const { data, isLoading, error, refetch, isFetching } = useBooks<Dict>(["controls", asOf], "/controls/run", { as_of: asOf });
  const { data: history } = useBooks<Dict[]>(["control-history"], "/controls/history");
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Section className="lg:col-span-2" title="Integrity monitor" actions={<Button size="sm" variant="outline" onClick={() => refetch()}><RefreshCw className={`mr-1 h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />Run now</Button>}>
        <DateRange single to={asOf} onChange={(_, t) => setAsOf(t)} />
        {isLoading && <Loading label="Running checks…" />}<ErrorNote error={error} />
        {data && <div className="mt-3"><CheckList items={data.results} /></div>}
      </Section>
      <Section title="Recent runs">
        {(history ?? []).length === 0 ? <Empty>No runs yet.</Empty> : (
          <Table><TableBody>{history!.map((h) => (
            <TableRow key={h.id}><TableCell className="text-xs">{new Date(h.run_at).toLocaleString("en-GB")}</TableCell><TableCell className="text-xs">as of {fmtDate(h.as_of)}</TableCell>
              <TableCell className={`text-right text-xs font-semibold ${h.fail_count ? "text-amber-600" : "text-emerald-600"}`}>{h.fail_count ? `${h.fail_count} failing` : "all pass"}</TableCell></TableRow>
          ))}</TableBody></Table>
        )}
      </Section>
    </div>
  );
}

const SOURCE_LABEL: Record<string, string> = {
  BILL: "Hospital bill", BILL_DISCOUNT: "Bill discount", PAYMENT: "Cashier payment", BILL_WAIVER: "Bill waiver",
  BILL_WRITEOFF: "Bill write-off", BILL_ADJUSTMENT: "Bill correction", DISPENSING: "Drug dispensed",
  DISPENSE_RETURN: "Drug returned", PHARMACY_RECEIPT: "Pharmacy stock received", PHARMACY_ADJUST: "Pharmacy adjustment",
};

/** Hospital operations -> Roy Books: what reached the books, what failed, what never tried. */
function Operations() {
  const qc = useQueryClient();
  const [status, setStatus] = useState("FAILED");
  const { data, isLoading, error, refetch } = useBooks<Dict[]>(["source-postings", status], "/integrations/source-postings", { status: status || undefined });
  const [range, setRange] = useState({ from: monthStart(), to: today() });
  const [result, setResult] = useState<Dict | null>(null);
  const { data: unposted, refetch: refetchUnposted } = useBooks<Dict[]>(["ops-unposted"], "/integrations/unposted");
  const { data: settings } = useBooks<Dict>(["settings"], "/settings");
  const refresh = () => { refetch(); refetchUnposted(); qc.invalidateQueries({ queryKey: ["books"] }); };
  const exclude = async (type: string, id: string, ref: string) => {
    const reason = await askText(`Keep ${ref} out of the books permanently? Give a reason (e.g. "test transaction").`);
    if (reason && (await act(() => books.post(`/integrations/${type}/${encodeURIComponent(id)}/exclude`, { reason }), `${ref} excluded from the books`))) refresh();
  };
  const retry = async (type: string, id: string) => {
    const r = await act(() => books.post<Dict>(`/integrations/${type}/${encodeURIComponent(id)}/post`, {}));
    if (r) {
      if (r.status === "FAILED") act(async () => { throw new Error(r.message); });
      else act(async () => r, r.status === "POSTED" ? (r.message ?? "Posted") : r.message);
      refresh();
    }
  };
  const backfill = async () => {
    const r = await act(() => books.post<Dict>("/integrations/backfill", range), "Backfill finished");
    if (r) { setResult(r); refresh(); }
  };
  return (
    <div className="space-y-4">
      {settings && !settings.cutover_date && (
        <div className="rounded-lg border border-amber-400 bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">
          Roy Books is <strong>not live yet</strong>: no cut-over date is set (Setup › Settings). Bills, payments and dispensing are recorded by the
          hospital as usual and reach the books from the cut-over date, once the Sage opening balances are loaded.
        </div>
      )}
      {settings && settings.cutover_date && !settings.auto_post_operations && (
        <div className="rounded-lg border border-amber-400 bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">
          Automatic posting of hospital bills, payments and dispensing is <strong>paused</strong> (Setup › Settings). They are not reaching the books until it is switched back on — then run Backfill.
        </div>
      )}
      <Section title={`Since go-live, not in the books (${unposted?.length ?? 0})`}>
        <p className="mb-3 text-sm text-muted-foreground">Bills, payments and dispenses that were never attempted (e.g. while posting was paused). Post them, or exclude a test so it never reaches the books.</p>
        {(unposted ?? []).length === 0 ? <Empty>Nothing waiting.</Empty> : (
          <Table>
            <TableHeader><TableRow><TableHead>What</TableHead><TableHead>Reference</TableHead><TableHead>Date</TableHead><TableHead className="text-right">Amount</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>{unposted!.map((u) => (
              <TableRow key={`${u.source_type}:${u.source_id}`}><TableCell className="text-xs">{u.label}</TableCell><TableCell className="font-mono text-xs">{u.source_ref}</TableCell>
                <TableCell className="whitespace-nowrap">{fmtDate(u.doc_date)}</TableCell>
                <TableCell className="text-right text-xs">{Number(u.amount ?? 0).toLocaleString("en-NG", { minimumFractionDigits: 2 })}</TableCell>
                <TableCell className="whitespace-nowrap"><Button size="sm" variant="outline" onClick={() => retry(u.source_type, u.source_id)}>Post</Button>
                  <Button size="sm" variant="ghost" onClick={() => exclude(u.source_type, u.source_id, u.source_ref)}>Exclude</Button></TableCell></TableRow>
            ))}</TableBody>
          </Table>
        )}
      </Section>
      <Section title="Hospital operations → Roy Books" actions={<select className="h-8 rounded-md border bg-background px-2 text-xs" value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="FAILED">Failed</option><option value="POSTED">Posted</option><option value="SKIPPED">Skipped</option><option value="">All</option></select>}>
        <p className="mb-3 text-sm text-muted-foreground">Every bill, cashier payment, approved discount, waiver, correction, dispense and pharmacy stock movement posts to the books by itself,
          without ever holding up the ward, the cashier or the pharmacy. Failures (closed period, missing posting rule, drug with no cost) are listed here to fix and retry.</p>
        {isLoading && <Loading />}<ErrorNote error={error} />
        {data && (data.length === 0 ? <Empty>{status === "FAILED" ? "No failed postings." : "Nothing here."}</Empty> : (
          <Table>
            <TableHeader><TableRow><TableHead>What</TableHead><TableHead>Reference</TableHead><TableHead>Status</TableHead><TableHead>Message</TableHead><TableHead className="text-right">Attempts</TableHead><TableHead>Updated</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>{data.map((p) => (
              <TableRow key={p.id}><TableCell className="text-xs">{SOURCE_LABEL[p.source_type] ?? p.source_type}</TableCell>
                <TableCell className="font-mono text-xs">{p.source_ref ?? p.source_id}</TableCell><TableCell><StatusBadge status={p.status} /></TableCell>
                <TableCell className="max-w-[320px] text-xs">{p.message}</TableCell><TableCell className="text-right">{p.attempts}</TableCell>
                <TableCell className="text-xs">{new Date(p.updated_at).toLocaleString("en-GB")}</TableCell>
                <TableCell className="whitespace-nowrap">{p.status === "FAILED" && <><Button size="sm" variant="outline" onClick={() => retry(p.source_type, p.source_id)}>Retry</Button>
                  <Button size="sm" variant="ghost" onClick={() => exclude(p.source_type, p.source_id, p.source_ref ?? p.source_id)}>Exclude</Button></>}</TableCell></TableRow>
            ))}</TableBody>
          </Table>
        ))}
      </Section>
      <Section title="Backfill a date range">
        <div className="flex flex-wrap items-end gap-3">
          <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
          <Button size="sm" onClick={backfill}>Post bills, payments & dispenses in range</Button>
        </div>
        {result && <p className="mt-2 text-sm">{result.processed} processed · {Object.entries(result.summary ?? {}).map(([k, v]) => `${v} ${k.toLowerCase()}`).join(" · ")}</p>}
        {result?.failed?.length > 0 && <ul className="mt-2 max-h-40 overflow-auto text-xs text-red-600">{result.failed.map((f: Dict, i: number) => <li key={i}>{f.source}: {f.message}</li>)}</ul>}
      </Section>
    </div>
  );
}

function Exceptions() {
  const qc = useQueryClient();
  const [status, setStatus] = useState("");
  const { data, isLoading, error } = useBooks<Dict[]>(["validation-events", status], "/validation-events", { status: status || undefined });
  return (
    <Section title="Validation exceptions & overrides" actions={<><select className="h-8 rounded-md border bg-background px-2 text-xs" value={status} onChange={(e) => setStatus(e.target.value)}>
      <option value="">All</option><option value="OPEN">Open</option><option value="ACCEPTED">Accepted (overridden)</option><option value="RESOLVED">Resolved</option></select>
      <CsvButton filename="validation-events.csv" rows={data} /></>}>
      <p className="mb-3 text-sm text-muted-foreground">Credit-limit overrides, duplicate cheque/reference confirmations and other warnings a user chose to proceed past — with who and why.</p>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (data.length === 0 ? <Empty>No exceptions recorded.</Empty> : (
        <Table>
          <TableHeader><TableRow><TableHead>When</TableHead><TableHead>Check</TableHead><TableHead>Document</TableHead><TableHead>Message</TableHead><TableHead>By</TableHead><TableHead>Status</TableHead><TableHead /></TableRow></TableHeader>
          <TableBody>{data.map((v) => (
            <TableRow key={v.id}><TableCell className="whitespace-nowrap text-xs">{new Date(v.created_at).toLocaleString("en-GB")}</TableCell>
              <TableCell className="text-xs">{v.check_code.replace(/_/g, " ").toLowerCase()}</TableCell><TableCell className="font-mono text-xs">{v.entity_ref}</TableCell>
              <TableCell className="max-w-[320px] text-xs">{v.message}{v.resolution_note ? ` — ${v.resolution_note}` : ""}</TableCell><TableCell className="text-xs">{v.created_by}</TableCell>
              <TableCell><StatusBadge status={v.status === "ACCEPTED" ? "APPROVED" : v.status} /></TableCell>
              <TableCell>{v.status !== "RESOLVED" && <Button size="sm" variant="outline" className="h-7 text-xs" onClick={async () => {
                const note = await askText(`How was this resolved?\n${v.message}`);
                if (note && note.trim() && (await act(() => books.post(`/validation-events/${v.id}/resolve`, { note: note.trim() }), "Resolved"))) qc.invalidateQueries({ queryKey: ["books"] });
              }}>Resolve</Button>}</TableCell></TableRow>
          ))}</TableBody>
        </Table>
      ))}
    </Section>
  );
}

function Audit() {
  const [search, setSearch] = useState("");
  const [actor, setActor] = useState("");
  const [type, setType] = useState("");
  const [range, setRange] = useState({ from: monthStart(), to: today() });
  const [row, setRow] = useState<Dict | null>(null);
  const { data, isLoading, error } = useBooks<any>(["audit", search, actor, type, range], "/audit",
    { search: search || undefined, actor: actor || undefined, entity_type: type || undefined, from: range.from, to: range.to, limit: 300 });
  return (
    <Section title={`Audit trail${data ? ` (${data.total})` : ""}`} actions={<CsvButton filename="audit-trail.csv" rows={data?.items} />}>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div className="flex-1"><FilterBar search={{ value: search, onChange: setSearch, placeholder: "Document ref, action, reason" }}
          selects={[{ label: "Record", value: type, onChange: setType, options: ["journal", "sales_invoice", "customer_receipt", "supplier_bill", "supplier_payment", "stock_adjustment", "period", "account", "settings", "mapping", "migration_batch"].map((t) => ({ value: t, label: t.replace(/_/g, " ") })) }]} /></div>
        <Input className="h-9 w-40" placeholder="User" value={actor} onChange={(e) => setActor(e.target.value)} />
        <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
      </div>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (data.items.length === 0 ? <Empty>No audit events match.</Empty> : (
        <Table>
          <TableHeader><TableRow><TableHead>When</TableHead><TableHead>User</TableHead><TableHead>Action</TableHead><TableHead>Record</TableHead><TableHead>Reason</TableHead></TableRow></TableHeader>
          <TableBody>{data.items.map((a: Dict) => (
            <TableRow key={a.id} className="cursor-pointer hover:bg-muted/50" onClick={() => setRow(a)}>
              <TableCell className="whitespace-nowrap text-xs">{new Date(a.created_at).toLocaleString("en-GB")}</TableCell><TableCell className="text-xs">{a.actor_name}</TableCell>
              <TableCell className="text-xs">{a.action.replace(/_/g, " ").toLowerCase()}</TableCell>
              <TableCell className="text-xs">{a.entity_type?.replace(/_/g, " ")} <span className="font-mono">{a.entity_ref}</span></TableCell>
              <TableCell className="max-w-[240px] truncate text-xs">{a.reason}</TableCell>
            </TableRow>
          ))}</TableBody>
        </Table>
      ))}
      <DetailSheet size="wide" open={!!row} onOpenChange={(o) => !o && setRow(null)} title={row ? row.action.replace(/_/g, " ").toLowerCase() : ""} description={row ? `${row.actor_name} · ${new Date(row.created_at).toLocaleString("en-GB")}` : ""}>
        {row && <pre className="whitespace-pre-wrap rounded bg-muted p-3 text-xs">{JSON.stringify({ record: `${row.entity_type} ${row.entity_ref ?? row.entity_id}`, reason: row.reason, before: row.before_state, after: row.after_state, metadata: row.metadata }, null, 2)}</pre>}
      </DetailSheet>
    </Section>
  );
}

function nextDay(d: string) {
  const x = new Date(`${d}T00:00:00`);
  x.setDate(x.getDate() + 1);
  return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`;
}
