import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, CheckCircle2, Plus, Trash2, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DetailSheet } from "@/components/workspace/DetailSheet";
import { FilterBar } from "@/components/workspace/FilterBar";
import { BooksShell } from "@/components/books/BooksShell";
import { GeneralLedgerView, JournalBody } from "@/components/books/lineage";
import { LedgerCoverageNote, SageLedgerTable } from "@/components/books/sage-ledger";
import { lineTarget, useDrill } from "@/components/books/drill-context";
import {
  AccountPick, AccountSheet, act, Amount, CsvButton, DateRange, DrillLink, Empty, ErrorNote, Loading, SageTag, Section, sourceLink, StatusBadge,
  useBooks, useLines,
} from "@/components/books/kit";
import { books, Dict, fmtDate, monthStart, naira, newIdemKey, num, today, yearStart } from "@/lib/books-api";
import { askText, askConfirm } from "@/lib/ask";

export default function BooksLedger() {
  const [params, setParams] = useSearchParams();
  const [tab, setTab] = useState(params.get("tab") ?? "journals");
  useEffect(() => { const t = params.get("tab"); if (t && t !== tab) setTab(t); }, [params]);
  const open = (k: string, v: string | null) => { const p = new URLSearchParams(params); v ? p.set(k, v) : p.delete(k); setParams(p, { replace: true }); };
  return (
    <BooksShell title="Journals & Ledger"
                actions={<Button size="sm" onClick={() => open("new", "journal")}><Plus className="mr-1 h-4 w-4" />Journal entry</Button>}>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="journals">Journal entries</TabsTrigger>
          <TabsTrigger value="by-type">Journals by type</TabsTrigger>
          <TabsTrigger value="gl">General ledger</TabsTrigger>
          <TabsTrigger value="tb">Trial balance</TabsTrigger>
          <TabsTrigger value="coa">Chart of accounts</TabsTrigger>
        </TabsList>
        <TabsContent value="journals"><JournalList onOpen={(id) => open("journal", id)} /></TabsContent>
        <TabsContent value="by-type"><JournalsByType /></TabsContent>
        {/* the full General Ledger (every account, Sage's layout); one account's ledger when one is chosen */}
        <TabsContent value="gl">{params.get("account") ? <AccountLedger /> : <GeneralLedger onJournal={(id) => open("journal", id)} />}</TabsContent>
        <TabsContent value="tb"><TrialBalance /></TabsContent>
        <TabsContent value="coa"><ChartHistory onOpen={(a) => { const p = new URLSearchParams(params); p.set("tab", "gl"); p.set("account", a.id); setParams(p, { replace: true }); setTab("gl"); }} /></TabsContent>
      </Tabs>
      <JournalEditor open={params.get("new") === "journal" || !!params.get("edit")} editId={params.get("edit")}
                     onClose={(id) => { const p = new URLSearchParams(params); p.delete("new"); p.delete("edit"); if (id) p.set("journal", id); setParams(p, { replace: true }); }} />
      <JournalDetail id={params.get("journal")} onClose={() => open("journal", null)}
                     onEdit={(id) => { const p = new URLSearchParams(params); p.delete("journal"); p.set("edit", id); setParams(p, { replace: true }); }}
                     onOpen={(id) => open("journal", id)} />
    </BooksShell>
  );
}

const STATUSES = ["DRAFT", "SUBMITTED", "APPROVED", "POSTED", "REVERSED", "REJECTED"];

function JournalList({ onOpen }: { onOpen: (id: string) => void }) {
  const drill = useDrill();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [type, setType] = useState("");
  const [range, setRange] = useState({ from: monthStart(), to: today() });
  const { data, isLoading, error } = useBooks<any>(["journals", search, status, type, range], "/journals",
    { search, status: status || undefined, journal_type: type || undefined, from: range.from, to: range.to, limit: 300 });
  return (
    <Section title={`Journal entries${data ? ` (${data.total})` : ""}`} actions={<CsvButton filename="journal-entries.csv" rows={data?.items} />}>
      <p className="mb-2 text-xs text-muted-foreground">Every journal - Roy Books' own postings and, tagged Sage, the general-journal entries from Sage's years. For the books of original entry (Sales, Cash Receipts, ...) open Journals by type.</p>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div className="flex-1"><FilterBar search={{ value: search, onChange: setSearch, placeholder: "Journal no., description, source ref" }}
          selects={[
            { label: "Status", value: status, onChange: setStatus, options: STATUSES.map((s) => ({ value: s, label: s.toLowerCase() })) },
            { label: "Type", value: type, onChange: setType, options: ["MANUAL", "SYSTEM", "OPENING", "CLOSING", "REVERSAL", "ADJUSTMENT"].map((s) => ({ value: s, label: s.toLowerCase() })) },
          ]} /></div>
        <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
      </div>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (data.items.length === 0 ? <Empty>No journals match.</Empty> : (
        <Table>
          <TableHeader><TableRow><TableHead>Journal</TableHead><TableHead>Date</TableHead><TableHead>Type</TableHead><TableHead>Description</TableHead><TableHead>Source</TableHead><TableHead className="text-right">Amount</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
          <TableBody>{data.items.map((j: Dict) => (
            <TableRow key={j.id ?? j.voucher} className="cursor-pointer hover:bg-muted/50"
                      onClick={() => (j.origin === "SAGE" ? drill?.open({ type: "sagevoucher", id: j.voucher, label: j.journal_number }) : onOpen(j.id))}>
              <TableCell className="font-mono text-xs">{j.journal_number}{j.origin === "SAGE" && <SageTag />}</TableCell><TableCell className="whitespace-nowrap">{fmtDate(j.journal_date)}</TableCell>
              <TableCell className="text-xs">{j.journal_type.toLowerCase()}</TableCell>
              <TableCell className="max-w-[280px] truncate text-xs">{j.description}</TableCell>
              <TableCell className="font-mono text-xs">{j.source_ref}</TableCell>
              <TableCell className="text-right"><Amount value={j.total_debit} /></TableCell><TableCell><StatusBadge status={j.status} /></TableCell>
            </TableRow>
          ))}</TableBody>
        </Table>
      ))}
    </Section>
  );
}

type JLine = { account: Dict | null; debit: string; credit: string; description: string };
const blankJ = (): JLine => ({ account: null, debit: "", credit: "", description: "" });

function JournalEditor({ open, editId, onClose }: { open: boolean; editId: string | null; onClose: (id?: string) => void }) {
  const qc = useQueryClient();
  const [date, setDate] = useState(today());
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [idem, setIdem] = useState(newIdemKey);
  const L = useLines<JLine>(blankJ, [blankJ(), blankJ()]);
  const { data: existing } = useBooks<Dict>(["journal", editId], `/journals/${editId}`, undefined, !!editId);
  useEffect(() => {
    if (existing && editId) {
      setDate(existing.journal_date); setDescription(existing.description ?? "");
      L.setLines(existing.lines.map((l: Dict) => ({ account: { id: l.account_id, code: l.account_code, name: l.account_name },
        debit: Number(l.debit) ? String(l.debit) : "", credit: Number(l.credit) ? String(l.credit) : "", description: l.description ?? "" })));
    }
  }, [existing, editId]);
  useEffect(() => { if (!open) { L.setLines([blankJ(), blankJ()]); setDescription(""); setDate(today()); setIdem(newIdemKey()); } }, [open]);
  const dr = L.lines.reduce((s, l) => s + Number(l.debit || 0), 0);
  const cr = L.lines.reduce((s, l) => s + Number(l.credit || 0), 0);
  const diff = Math.round((dr - cr) * 100) / 100;
  const save = async () => {
    setBusy(true);
    const body = { journal_date: date, description, lines: L.lines.filter((l) => l.account).map((l) => ({ account_id: l.account?.id, debit: l.debit || 0, credit: l.credit || 0, description: l.description || undefined })) };
    const j = await act(() => (editId ? books.put(`/journals/${editId}`, body) : books.post("/journals", body, idem)), "Journal saved as draft");
    setBusy(false);
    if (j) { qc.invalidateQueries({ queryKey: ["books"] }); onClose(j.id); }
  };
  return (
    <DetailSheet size="wide" open={open} onOpenChange={(o) => !o && onClose()} title={editId ? "Edit draft journal" : "New journal entry"}
                 description="Saved as a draft. Submit it for approval; once approved it is posted. Control accounts (debtors, creditors, stock) are fed by their own modules."
                 footer={<div className="flex w-full items-center justify-between text-sm">
                   <span>Dr {naira(dr)} · Cr {naira(cr)} {diff !== 0 ? <span className="text-red-600">· out by {naira(diff)}</span> : dr > 0 && <span className="text-emerald-600">· balanced</span>}</span>
                   <Button disabled={busy || dr === 0 || diff !== 0 || !description.trim()} onClick={save}>{busy ? "Saving…" : "Save draft"}</Button></div>}>
      <div className="space-y-3">
        <div className="grid grid-cols-[160px_1fr] gap-3">
          <div className="space-y-1"><Label className="text-xs">Date</Label><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></div>
          <div className="space-y-1"><Label className="text-xs">Narration</Label><Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Why this entry is being made" /></div>
        </div>
        {L.lines.map((l, i) => (
          <div key={i} className="grid grid-cols-[1fr_110px_110px_32px] items-end gap-2">
            <div className="space-y-1">
              <AccountPick label={i === 0 ? "Account" : undefined} value={l.account} onChange={(a) => L.update(i, { account: a })} />
              <Input className="h-7 text-xs" placeholder="Line description (optional)" value={l.description} onChange={(e) => L.update(i, { description: e.target.value })} />
            </div>
            <Input className="h-9" type="number" placeholder="Debit" value={l.debit} onChange={(e) => L.update(i, { debit: e.target.value, credit: e.target.value ? "" : l.credit })} />
            <Input className="h-9" type="number" placeholder="Credit" value={l.credit} onChange={(e) => L.update(i, { credit: e.target.value, debit: e.target.value ? "" : l.debit })} />
            <Button size="icon" variant="ghost" onClick={() => L.remove(i)}><Trash2 className="h-4 w-4" /></Button>
          </div>
        ))}
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={L.add}><Plus className="mr-1 h-4 w-4" />Add line</Button>
          {diff !== 0 && <Button size="sm" variant="ghost" onClick={() => L.setLines([...L.lines, { ...blankJ(), debit: diff < 0 ? String(-diff) : "", credit: diff > 0 ? String(diff) : "" }])}>Add balancing line</Button>}
        </div>
      </div>
    </DetailSheet>
  );
}

function JournalDetail({ id, onClose, onEdit, onOpen }: { id: string | null; onClose: () => void; onEdit: (id: string) => void; onOpen: (id: string) => void }) {
  const qc = useQueryClient();
  const { data: j, isLoading, error, refetch } = useBooks<Dict>(["journal", id], `/journals/${id}`, undefined, !!id);
  const [check, setCheck] = useState<Dict | null>(null);
  useEffect(() => setCheck(null), [id]);
  const done = () => { refetch(); qc.invalidateQueries({ queryKey: ["books"] }); };
  const run = async (action: string, body: Dict = {}, ok?: string) => { if (await act(() => books.post(`/journals/${id}/${action}`, body), ok)) done(); };
  const reverse = async () => {
    const reason = await askText("Reason for reversing this journal?");
    if (!reason) return;
    const date = await askText("Reversal date (YYYY-MM-DD)", today());
    const r = await act(() => books.post(`/journals/${id}/reverse`, { reason, reversal_date: date || undefined }), "Reversal posted");
    if (r) { done(); if (r.id && r.id !== id) onOpen(r.id); }
  };
  const del = async () => { if (await askConfirm("Delete this draft?") && (await act(() => books.del(`/journals/${id}`), "Draft deleted"))) { qc.invalidateQueries({ queryKey: ["books"] }); onClose(); } };
  const link = j ? sourceLink(j.source_type, j.source_id) : null;
  const manual = j && (!j.source_type || j.source_type === "MANUAL_JOURNAL");
  return (
    <DetailSheet size="wide" open={!!id} onOpenChange={(o) => !o && onClose()} title={j ? `Journal ${j.journal_number}` : "Journal"} description={j?.description}
                 footer={j && manual ? (
                   <div className="flex flex-wrap gap-2">
                     {j.status === "DRAFT" && <>
                       <Button size="sm" variant="outline" onClick={() => onEdit(j.id)}>Edit</Button>
                       <Button size="sm" variant="outline" onClick={async () => setCheck(await act(() => books.post(`/journals/${id}/validate`, {})) ?? null)}>Check</Button>
                       <Button size="sm" variant="ghost" onClick={del}>Delete</Button>
                       <Button size="sm" onClick={() => run("submit", {}, "Submitted for approval")}>Submit for approval</Button>
                       <Button size="sm" variant="secondary" onClick={() => run("post", {}, "Posted")}>Post now</Button></>}
                     {j.status === "SUBMITTED" && <>
                       <Button size="sm" variant="outline" onClick={async () => { const reason = await askText("Reason for rejecting?"); if (reason) run("reject", { reason }, "Rejected"); }}>Reject</Button>
                       <Button size="sm" onClick={async () => run("approve", { comment: await askText("Approval comment (optional)") ?? undefined }, "Approved")}>Approve</Button></>}
                     {j.status === "APPROVED" && <Button size="sm" onClick={() => run("post", {}, "Posted")}>Post</Button>}
                     {j.status === "POSTED" && !j.reversed_by_id && <Button size="sm" variant="destructive" onClick={reverse}>Reverse</Button>}
                   </div>) : j?.status === "POSTED" && !j.reversed_by_id && j.journal_type !== "OPENING" ? (
                   <Button size="sm" variant="destructive" onClick={reverse}>Reverse</Button>) : undefined}>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {check && (
        <div className={`mb-3 rounded-md border p-2 text-xs ${check.valid ? "border-emerald-400 text-emerald-700" : "border-red-400 text-red-700"}`}>
          {check.valid ? <span className="flex items-center gap-1"><CheckCircle2 className="h-4 w-4" />Ready to post.</span>
            : <ul className="space-y-1">{check.issues.map((x: Dict, i: number) => <li key={i} className="flex gap-1"><XCircle className="h-4 w-4 shrink-0" />{x.message}</li>)}</ul>}
        </div>
      )}
      {j && link && <Link className="mb-2 inline-flex items-center text-xs text-primary hover:underline" to={link}>open the source document's page <ArrowUpRight className="h-3 w-3" /></Link>}
      {id && <JournalBody key={`${id}:${j?.status}`} id={id} />}
    </DetailSheet>
  );
}

function TrialBalance() {
  const [range, setRange] = useState({ from: yearStart(), to: today() });
  const [zero, setZero] = useState(false);
  const [account, setAccount] = useState<Dict | null>(null);
  const { data, isLoading, error } = useBooks<any>(["tb", range, zero], "/trial-balance", { ...range, include_zero: zero });
  return (
    <Section title="Trial balance" actions={<CsvButton filename={`trial-balance-${range.to}.csv`} rows={data?.rows.map((r: Dict) => ({ code: r.code, name: r.name, type: r.account_type, opening: r.opening, debit: r.period_debit, credit: r.period_credit, closing_debit: r.closing_debit, closing_credit: r.closing_credit }))} />}>
      <div className="mb-3 flex flex-wrap items-end gap-4">
        <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
        <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={zero} onChange={(e) => setZero(e.target.checked)} />include zero accounts</label>
        {data && <span className={`text-sm font-medium ${data.balanced ? "text-emerald-600" : "text-red-600"}`}>{data.balanced ? "✓ Balanced" : "✗ Out of balance"}</span>}
      </div>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (
        <Table>
          <TableHeader><TableRow><TableHead>Code</TableHead><TableHead>Account</TableHead><TableHead className="text-right">Opening</TableHead><TableHead className="text-right">Debit</TableHead><TableHead className="text-right">Credit</TableHead><TableHead className="text-right">Closing Dr</TableHead><TableHead className="text-right">Closing Cr</TableHead></TableRow></TableHeader>
          <TableBody>
            {data.rows.map((r: Dict) => (
              <TableRow key={r.account_id} className="cursor-pointer hover:bg-muted/50" onClick={() => setAccount({ id: r.account_id, code: r.code, name: r.name })}>
                <TableCell className="font-mono text-xs">{r.code}</TableCell><TableCell className="max-w-[260px] truncate">{r.name}</TableCell>
                <TableCell className="text-right"><Amount value={r.opening} blankZero /></TableCell>
                <TableCell className="text-right"><Amount value={r.period_debit} blankZero /></TableCell><TableCell className="text-right"><Amount value={r.period_credit} blankZero /></TableCell>
                <TableCell className="text-right"><Amount value={r.closing_debit} blankZero /></TableCell><TableCell className="text-right"><Amount value={r.closing_credit} blankZero /></TableCell>
              </TableRow>
            ))}
            <TableRow className="font-semibold"><TableCell colSpan={2}>Totals</TableCell><TableCell />
              <TableCell className="text-right"><Amount value={data.totals.period_debit} /></TableCell><TableCell className="text-right"><Amount value={data.totals.period_credit} /></TableCell>
              <TableCell className="text-right"><Amount value={data.totals.closing_debit} /></TableCell><TableCell className="text-right"><Amount value={data.totals.closing_credit} /></TableCell></TableRow>
          </TableBody>
        </Table>
      )}
      <AccountSheet account={account} from={range.from} to={range.to} onClose={() => setAccount(null)} />
    </Section>
  );
}

function GeneralLedger({ onJournal }: { onJournal: (id: string) => void }) {
  // Sage 50's General Ledger, as finance prints it (financemeetings/Gl.xlsx): by Account ID, month by month.
  const [range, setRange] = useState({ from: monthStart(), to: today() });
  const [accounts, setAccounts] = useState<Dict[]>([]);
  const [adding, setAdding] = useState<Dict | null>(null);
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  useEffect(() => { const t = setTimeout(() => setSearch(typed.trim()), 400); return () => clearTimeout(t); }, [typed]);
  useEffect(() => { if (adding) { setAccounts((a) => (a.some((x) => x.id === adding.id) ? a : [...a, adding])); setAdding(null); } }, [adding]);
  const { data, isLoading, error } = useBooks<Dict>(["sage-gl", range, accounts.map((a) => a.id), search], "/ledgers/sage-gl",
    { ...range, account_ids: accounts.map((a) => a.id).join(",") || undefined, search: search || undefined });
  return (
    <Section title={<>General Ledger {data && <span className="text-sm font-normal text-muted-foreground">· {num(data.accounts)} accounts · {num(data.lines)} transactions</span>}</>}>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
        <div className="w-72"><AccountPick label="Only these accounts" value={null} onChange={setAdding} /></div>
        {accounts.map((a) => <Badge key={a.id} variant="secondary" className="cursor-pointer" onClick={() => setAccounts(accounts.filter((x) => x.id !== a.id))}>{a.code} ✕</Badge>)}
        <Input className="h-9 w-80" placeholder="Filter: account, name, reference, description or amount" value={typed} onChange={(e) => setTyped(e.target.value)} />
      </div>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && Number(data.lines) === 0 && !search && <div className="mb-3"><LedgerCoverageNote onRange={(f, t) => setRange({ from: f, to: t })} /></div>}
      {data && data.rows.length > 0 && (
        <SageLedgerTable rows={data.rows} filename={`general-ledger-${range.from}-${range.to}.csv`} onLine={(r) => onJournal(r.journal_id)} />
      )}
    </Section>
  );
}


/** The eight books of original entry, in Sage's column layout, for any period - Sage's years and Roy Books in one table.
 *  The list of journals comes from the backend (never typed twice). */
function JournalsByType() {
  const [params, setParams] = useSearchParams();
  const key = params.get("kind") ?? "sales";
  const [range, setRange] = useState({ from: monthStart(), to: today() });
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  useEffect(() => { const t = setTimeout(() => setSearch(typed.trim()), 400); return () => clearTimeout(t); }, [typed]);
  const { data: list } = useBooks<Dict[]>(["journal-list"], "/ledger/journals");
  const { data, isLoading, error } = useBooks<Dict>(["journal-by-type", key, range, search], `/ledger/journal/${key}`,
    { ...range, search: search || undefined });
  const setKey = (k: string) => { const p = new URLSearchParams(params); p.set("kind", k); setParams(p, { replace: true }); };
  const cell = (c: Dict, r: Dict) => {
    const v = r[c.key];
    if (c.type === "money") return <Amount value={v} blankZero />;
    if (c.type === "date") return fmtDate(v);
    if (c.link === "account") return <DrillLink to={{ type: "account", id: r.account_id, label: r.account }}>{v}</DrillLink>;
    if (c.link === "line") return <DrillLink to={lineTarget(r)}><span className="font-mono text-xs">{v || r.journal_number}</span></DrillLink>;
    return v ?? "";
  };
  return (
    <Section title={data?.title ?? "Journals by type"} actions={<CsvButton filename={`${key}-${range.from}-${range.to}.csv`} rows={data?.rows} />}>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div className="flex flex-wrap gap-1">{(list ?? []).map((j) => (
          <Button key={j.key} size="sm" variant={j.key === key ? "default" : "outline"} onClick={() => setKey(j.key)}>{j.title.replace(" Journal", "")}</Button>))}</div>
        <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
        <Input className="h-9 w-64 border" placeholder="Search description, reference, amount" value={typed} onChange={(e) => setTyped(e.target.value)} />
      </div>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (data.rows.length === 0 ? <Empty>No {data.title.toLowerCase()} entries in this period.</Empty> : (
        <>
          <Table>
            <TableHeader><TableRow>{data.columns.map((c: Dict) => <TableHead key={c.key} className={c.type === "money" ? "text-right" : ""}>{c.label}</TableHead>)}</TableRow></TableHeader>
            <TableBody>
              {data.rows.slice(0, 3000).map((r: Dict) => (
                <TableRow key={r.line_id}>{data.columns.map((c: Dict) => (
                  <TableCell key={c.key} className={`${c.type === "money" ? "text-right" : ""} ${c.type === "date" ? "whitespace-nowrap" : ""} text-xs`}>
                    {cell(c, r)}{c.key === "description" && r.origin === "SAGE" ? <SageTag /> : null}</TableCell>))}</TableRow>))}
              <TableRow className="font-semibold">{data.columns.map((c: Dict, i: number) => (
                <TableCell key={c.key} className={c.type === "money" ? "text-right" : ""}>{i === 0 ? "Total" : c.key === "debit" ? <Amount value={data.total_debit} /> : c.key === "credit" ? <Amount value={data.total_credit} /> : ""}</TableCell>))}</TableRow>
            </TableBody>
          </Table>
          <p className="mt-2 text-xs text-muted-foreground">{data.rows.length.toLocaleString()} lines{data.rows.length > 3000 ? " - showing the first 3,000; narrow the dates or search" : ""}.
            {Number(data.total_debit) === Number(data.total_credit) ? " Debits equal credits." : " Debits and credits differ in this selection (an entry crosses its dates or the search)."}</p>
        </>
      ))}
    </Section>
  );
}

/** One account in Sage's General Ledger layout: monthly beginning balance, every transaction, period change. */
function AccountLedger() {
  const [params, setParams] = useSearchParams();
  const [account, setAccount] = useState<Dict | null>(null);
  const id = account?.id ?? params.get("account");
  const [range, setRange] = useState({ from: yearStart(), to: today() });
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  useEffect(() => { const t = setTimeout(() => setSearch(typed.trim()), 400); return () => clearTimeout(t); }, [typed]);
  const [showVoided, setShowVoided] = useState(false);
  const { data, isLoading, error } = useBooks<Dict>(["account-ledger", id, range, search, showVoided], `/accounts/${id}/ledger`,
    { ...range, search: search || undefined, include_voided: showVoided || undefined }, !!id);
  return (
    <Section title="General ledger · one account" actions={<Button size="sm" variant="outline" onClick={() => {
      const p = new URLSearchParams(params); p.delete("account"); setParams(p, { replace: true }); }}>← All accounts</Button>}>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div className="w-80"><AccountPick label="Account" value={account} onChange={(a) => { setAccount(a); const p = new URLSearchParams(params); a ? p.set("account", a.id) : p.delete("account"); setParams(p, { replace: true }); }} /></div>
        <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
        <Input className="h-9 w-64 border" placeholder="Search reference, description, amount" value={typed} onChange={(e) => setTyped(e.target.value)} />
      </div>
      {!id && <Empty>Choose an account. Any range from 2010 works: Sage's years and Roy Books in one ledger.</Empty>}
      {id && isLoading && <Loading />}<ErrorNote error={error} />
      {data && <GeneralLedgerView d={data} showVoided={showVoided} onShowVoided={setShowVoided} />}
    </Section>
  );
}

/** The chart of accounts with its history: balance at any date from the whole ledger, entries, first and last entry. */
function ChartHistory({ onOpen }: { onOpen: (a: Dict) => void }) {
  const [asOf, setAsOf] = useState(today());
  const [search, setSearch] = useState("");
  const [used, setUsed] = useState("used");
  const { data, isLoading, error } = useBooks<Dict[]>(["coa-history", asOf, used], "/accounts", { history: true, as_of: asOf, used: used || undefined });
  const rows = (data ?? []).filter((a) => !search || `${a.code} ${a.name} ${a.legacy_code ?? ""}`.toLowerCase().includes(search.toLowerCase()));
  return (
    <Section title={`Chart of accounts${data ? ` (${rows.length})` : ""}`} actions={<CsvButton filename={`chart-of-accounts-${asOf}.csv`} rows={rows} />}>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <DateRange single to={asOf} onChange={(_, t) => setAsOf(t)} />
        <Input className="h-9 w-64 border" placeholder="Code or name" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="h-9 rounded-md border bg-background px-2 text-sm" value={used} onChange={(e) => setUsed(e.target.value)}>
          <option value="used">Used accounts</option><option value="unused">Never used</option><option value="">All accounts</option></select>
        <Link to="/finance/books/setup?tab=accounts" className="ml-auto inline-flex items-center text-xs text-muted-foreground hover:underline">New account / edit <ArrowUpRight className="h-3 w-3" /></Link>
      </div>
      <p className="mb-2 text-xs text-muted-foreground">Balances are from the whole ledger - Sage's years and Roy Books - at the date chosen (income and expense as year to date). Click a balance for every line behind it.</p>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (
        <Table>
          <TableHeader><TableRow><TableHead>Code</TableHead><TableHead>Name</TableHead><TableHead>Type</TableHead><TableHead>Status</TableHead>
            <TableHead className="text-right">Balance</TableHead><TableHead className="text-right">Entries</TableHead><TableHead>First entry</TableHead><TableHead>Last entry</TableHead></TableRow></TableHeader>
          <TableBody>{rows.map((a) => (
            <TableRow key={a.id}>
              <TableCell className="font-mono text-xs">{a.code}</TableCell>
              <TableCell className="text-sm">{a.name}{a.warning && <div className="text-xs text-amber-700">{a.warning}</div>}</TableCell>
              <TableCell className="text-xs">{String(a.subtype).replace(/_/g, " ").toLowerCase()}</TableCell>
              <TableCell><StatusBadge status={a.status} /></TableCell>
              <TableCell className="text-right"><button className="hover:underline" onClick={() => onOpen(a)}><Amount value={a.balance} /></button></TableCell>
              <TableCell className="text-right text-xs">{Number(a.entries).toLocaleString()}</TableCell>
              <TableCell className="whitespace-nowrap text-xs">{fmtDate(a.first_entry)}</TableCell><TableCell className="whitespace-nowrap text-xs">{fmtDate(a.last_entry)}</TableCell>
            </TableRow>))}</TableBody>
        </Table>
      )}
    </Section>
  );
}
