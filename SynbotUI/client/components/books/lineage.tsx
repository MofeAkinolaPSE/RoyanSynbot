/**
 * Financial lineage viewer. One sheet, a stack of records: every reference in a
 * record opens the next one on top (with a breadcrumb back), so a user can walk
 *   Revenue -> patient / payer -> invoice -> hospital bill -> drug -> batch -> stock movement -> journal -> GL account
 * without leaving the page they started on.
 *
 * The same record views (<RecordView>) are used by the list pages' own detail
 * sheets, so an invoice / bill / receipt looks and links the same everywhere.
 * Opening (Sage cut-over) documents are badged; hospital documents link back to the bill.
 */
import { ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, ChevronLeft, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DetailSheet } from "@/components/workspace/DetailSheet";
import { books, Dict, fmtDate, naira, num, today, yearStart } from "@/lib/books-api";
import { askConfirm, askText } from "@/lib/ask";
import { DrillContext, DrillTarget, lineTarget, sourceTarget } from "./drill-context";
import { AccountPick, act, Amount, BankSelect, CsvButton, CustomerPick, DateRange, DrillLink, ErrorNote, Loading, sourceLink, StatusBadge, useBooks } from "./kit";

const TITLES: Record<string, string> = {
  journal: "Journal", account: "Account", invoice: "Invoice", receipt: "Receipt", creditnote: "Credit note",
  bill: "Supplier bill", payment: "Supplier payment", debitnote: "Debit note", voucher: "Voucher", customer: "Patient / payer",
  supplier: "Supplier", product: "Drug / item", batch: "Batch", adjustment: "Stock adjustment", loan: "Stock loan", asset: "Fixed asset",
  refund: "Refund", sagevoucher: "Sage entry", sageinvoice: "Sage invoice", sagereceipt: "Sage receipt", visit: "Hope visit",
  dataissue: "Data issue",
};

export function DrillProvider({ children }: { children: ReactNode }) {
  const [stack, setStack] = useState<DrillTarget[]>([]);
  const open = useCallback((t: DrillTarget) => setStack((s) => (s.length && s[s.length - 1].type === t.type && s[s.length - 1].id === t.id ? s : [...s, t])), []);
  const ctx = useMemo(() => ({ open }), [open]);
  const top = stack[stack.length - 1];
  return (
    <DrillContext.Provider value={ctx}>
      {children}
      <DetailSheet size="wide" open={!!top} onOpenChange={(o) => !o && setStack([])} title={top ? `${TITLES[top.type]}${top.label ? ` · ${top.label}` : ""}` : ""}
                   description={stack.length > 1 ? undefined : "Financial lineage: click any underlined reference to follow it."}>
        {stack.length > 1 && (
          <div className="mb-3 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
            <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setStack((s) => s.slice(0, -1))}><ChevronLeft className="h-4 w-4" />Back</Button>
            {stack.map((t, i) => (
              <button key={i} className={`hover:underline ${i === stack.length - 1 ? "font-semibold text-foreground" : ""}`} onClick={() => setStack((s) => s.slice(0, i + 1))}>
                {i > 0 && "› "}{TITLES[t.type]}{t.label ? ` ${t.label}` : ""}
              </button>
            ))}
          </div>
        )}
        {top && <RecordView key={`${top.type}:${top.id}`} t={top} />}
      </DetailSheet>
    </DrillContext.Provider>
  );
}

/** The detail view of any record; also used inside the list pages' own sheets. */
export function RecordView({ t }: { t: DrillTarget }) {
  switch (t.type as string) {
    case "journal": return <JournalBody id={t.id} />;
    case "account": return <AccountBody id={t.id} />;
    case "invoice": return <InvoiceBody id={t.id} />;
    case "receipt": return <ReceiptBody id={t.id} />;
    case "creditnote": return <CreditNoteBody id={t.id} />;
    case "bill": return <BillBody id={t.id} />;
    case "payment": return <PaymentBody id={t.id} />;
    case "debitnote": return <DebitNoteBody id={t.id} />;
    case "voucher": return <VoucherBody id={t.id} />;
    case "customer": return <CustomerBody id={t.id} />;
    case "supplier": return <SupplierBody id={t.id} />;
    case "product": return <ProductBody sku={t.id} />;
    case "batch": return <BatchBody id={t.id} />;
    case "adjustment": return <AdjustmentBody id={t.id} />;
    case "loan": return <LoanBody id={t.id} />;
    case "asset": return <AssetBody id={t.id} />;
    case "refund": return <RefundBody id={t.id} />;
    case "sagevoucher": return <SageVoucherBody id={t.id} />;
    case "sageinvoice": return <SageInvoiceBody id={t.id} />;
    case "sagereceipt": return <SageReceiptBody id={t.id} />;
    case "visit": return <VisitBody id={t.id} />;
    case "dataissue": return <DataIssueBody id={t.id} />;
    default: return null;
  }
}

// ---------------------------------------------------------------------------
// Building blocks
// ---------------------------------------------------------------------------

function Load<T = Dict>({ path, params, children }: { path: string; params?: Dict; children: (d: T) => ReactNode }) {
  const { data, isLoading, error } = useBooks<T>(["lineage", path, params], path, params);
  if (isLoading) return <Loading />;
  if (error) return <ErrorNote error={error} />;
  return <>{data ? children(data) : null}</>;
}

/** Key facts in a grid that uses the sheet's full width. */
export function Facts({ items, cols = 3 }: { items: [string, ReactNode][]; cols?: 2 | 3 | 4 }) {
  const shown = items.filter(([, v]) => v !== null && v !== undefined && v !== "" && v !== false);
  return (
    <div className={`grid grid-cols-2 gap-x-4 gap-y-3 rounded-lg bg-muted/40 p-3 text-sm ${cols === 3 ? "md:grid-cols-3" : cols === 4 ? "md:grid-cols-4" : ""}`}>
      {shown.map(([k, v]) => (
        <div key={k} className="min-w-0"><div className="text-xs uppercase tracking-wide text-muted-foreground">{k}</div><div className="truncate font-medium">{v}</div></div>
      ))}
    </div>
  );
}

function H({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return <div className="mb-1 mt-4 flex items-center justify-between gap-2"><span className="text-xs font-semibold uppercase text-muted-foreground">{children}</span>{right}</div>;
}

/** Search box for long lists inside a sheet. */
export function useListFilter<T extends Dict>(rows: T[] | undefined, placeholder = "Search") {
  const [s, setS] = useState("");
  const list = useMemo(() => {
    const r = rows ?? [];
    if (!s.trim()) return r;
    const needle = s.toLowerCase();
    return r.filter((x) => Object.values(x).some((v) => v != null && typeof v !== "object" && String(v).toLowerCase().includes(needle)));
  }, [rows, s]);
  const box = (rows?.length ?? 0) > 6 ? (
    <div className="relative w-56"><Search className="absolute left-2 top-2 h-3.5 w-3.5 text-muted-foreground" />
      <Input className="h-7 pl-7 text-xs" placeholder={placeholder} value={s} onChange={(e) => setS(e.target.value)} /></div>
  ) : null;
  return [list, box] as const;
}

const J = ({ id, n }: { id?: string; n?: string }) => (id ? <DrillLink to={{ type: "journal", id, label: n }}>{n ?? "journal"}</DrillLink> : <span className="text-muted-foreground">—</span>);
const Cust = ({ id, name }: { id?: any; name?: string }) => (id ? <DrillLink to={{ type: "customer", id: String(id), label: name }}>{name ?? `#${id}`}</DrillLink> : <>{name ?? "—"}</>);
const Sup = ({ id, name }: { id?: any; name?: string }) => (id ? <DrillLink to={{ type: "supplier", id: String(id), label: name }}>{name ?? "supplier"}</DrillLink> : <>{name ?? "—"}</>);
const Prod = ({ sku, children }: { sku?: string; children?: ReactNode }) => (sku ? <DrillLink to={{ type: "product", id: sku, label: sku }}>{children ?? sku}</DrillLink> : <>{children}</>);
const Bat = ({ id, n }: { id?: string; n?: string }) => (id ? <DrillLink to={{ type: "batch", id, label: n }}>{n ?? "batch"}</DrillLink> : <>{n ?? ""}</>);
const PARTY: Record<string, string> = { PATIENT: "Patient", HMO: "HMO / insurer", CORPORATE: "Corporate", OTHER: "Other" };

function PageLink({ to }: { to: string | null }) {
  return to ? <Link className="inline-flex items-center text-xs text-muted-foreground hover:underline" to={to}>open in its page <ArrowUpRight className="h-3 w-3" /></Link> : null;
}

function Totals({ rows }: { rows: [string, any, boolean?][] }) {
  return (
    <div className="grid grid-cols-1 gap-x-8 gap-y-1 rounded-lg border p-3 text-sm sm:grid-cols-2">
      {rows.filter(([, v]) => v !== undefined && v !== null).map(([k, v, bold]) => (
        <div key={k} className={`flex justify-between gap-2 ${bold ? "font-semibold" : ""}`}><span className="text-muted-foreground">{k}</span><Amount value={v} /></div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Ledger
// ---------------------------------------------------------------------------

export function JournalBody({ id }: { id: string }) {
  return <Load path={`/journals/${id}`}>{(j) => <JournalContent j={j} />}</Load>;
}

function JournalContent({ j }: { j: Dict }) {
  const qc = useQueryClient();
  const [lines, box] = useListFilter<Dict>(j.lines.map((l: Dict) => ({ ...l, _acc: `${l.account_code} ${l.account_name}` })), "Search account, description, item");
  const manual = !j.source_type || j.source_type === "MANUAL_JOURNAL";
  const deletable = j.status === "POSTED" && ["MANUAL", "ADJUSTMENT"].includes(j.journal_type) && !j.reversed_by_id;
  const del = async () => {
    const reason = await askText(`Delete ${j.journal_number}?\nThe exact reversal is posted on the same date, so every report returns to how it was. Both stay in Journal entries and the audit trail. Why is it being deleted?`);
    if (!reason) return;
    if (await act(() => books.post(`/journals/${j.id}/delete`, { reason }), "Entry deleted")) qc.invalidateQueries({ queryKey: ["books"] });
  };
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-center gap-2"><StatusBadge status={j.status} /><Badge variant="outline">{j.journal_type.toLowerCase()}</Badge>
        <span className="text-muted-foreground">{fmtDate(j.journal_date)} · {j.period_name}</span>
        {deletable && <Button size="sm" variant="outline" className="ml-auto" onClick={del}>Delete entry</Button>}</div>
      <Facts items={[["Journal", j.journal_number], ["Narration", j.description],
        ["Source", !manual && j.source_ref ? <DrillLink to={sourceTarget(j.source_type, j.source_id)}>{j.source_type?.replace(/_/g, " ").toLowerCase()} {j.source_ref}</DrillLink> : manual ? "manual journal" : null],
        ["Created by", j.created_by], ["Posted by", j.posted_by], ["Lines", j.lines.length]]} />
      <H right={box}>Lines</H>
      <Table>
        <TableHeader><TableRow><TableHead>Account</TableHead><TableHead className="text-right">Debit</TableHead><TableHead className="text-right">Credit</TableHead></TableRow></TableHeader>
        <TableBody>
          {lines.map((l: Dict) => (
            <TableRow key={l.id}>
              <TableCell><DrillLink to={{ type: "account", id: l.account_id, label: l.account_code }}>{l.account_code} · {l.account_name}</DrillLink>
                <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                  {l.description && <span>{l.description}</span>}
                  {l.customer_id && <Cust id={l.customer_id} name={`account #${l.customer_id}`} />}
                  {l.supplier_id && <Sup id={l.supplier_id} />}
                  <Prod sku={l.product_sku} />
                </div></TableCell>
              <TableCell className="text-right"><Amount value={l.debit} blankZero /></TableCell><TableCell className="text-right"><Amount value={l.credit} blankZero /></TableCell>
            </TableRow>
          ))}
          <TableRow className="font-semibold"><TableCell>Total{lines.length !== j.lines.length ? ` (all ${j.lines.length} lines)` : ""}</TableCell><TableCell className="text-right"><Amount value={j.total_debit} /></TableCell><TableCell className="text-right"><Amount value={j.total_credit} /></TableCell></TableRow>
        </TableBody>
      </Table>
      {j.reversal_of_id && <DrillLink to={{ type: "journal", id: j.reversal_of_id }}>This reverses another journal — open it</DrillLink>}
      {j.reversed_by_id && <DrillLink to={{ type: "journal", id: j.reversed_by_id }}>Reversed — open the reversal</DrillLink>}
      {j.audit?.length > 0 && (<><H>Audit trail</H>
        <ul className="space-y-1 text-xs">{j.audit.map((a: Dict, i: number) => (
          <li key={i}><span className="text-muted-foreground">{new Date(a.created_at).toLocaleString("en-GB")}</span> · {a.action.replace(/_/g, " ").toLowerCase()} by {a.actor_name}{a.reason ? ` — ${a.reason}` : ""}</li>))}</ul></>)}
    </div>
  );
}

function AccountBody({ id }: { id: string }) {
  const [range, setRange] = useState({ from: yearStart(), to: today() });
  const [showVoided, setShowVoided] = useState(false);
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  useEffect(() => { const t = setTimeout(() => setSearch(typed.trim()), 400); return () => clearTimeout(t); }, [typed]);
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-end gap-3">
        <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
        <div className="relative w-72"><Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input className="h-9 pl-8" placeholder="Search reference, description, amount" value={typed} onChange={(e) => setTyped(e.target.value)} /></div>
      </div>
      <Load path={`/accounts/${id}/ledger`} params={{ ...range, search: search || undefined, include_voided: showVoided || undefined }}>
        {(d) => <GeneralLedgerView d={d} showVoided={showVoided} onShowVoided={setShowVoided} />}</Load>
    </div>
  );
}

/** One account the way Sage prints its General Ledger: per month a Beginning Balance, each transaction with its running
 *  balance, and the period change; Sage history and Roy Books in one table, every line opening its record. */
export function GeneralLedgerView({ d, showVoided, onShowVoided }: { d: Dict; showVoided?: boolean; onShowVoided?: (on: boolean) => void }) {
  const lines = d.months.flatMap((m: Dict) => m.lines);
  return (
    <>
      {onShowVoided && (Number(d.voided_hidden) > 0 || showVoided) && (
        <div className="rounded-md border bg-muted/40 px-3 py-2 text-xs">
          {showVoided ? "Voided entries are shown struck through; each cancels out against its reversal." :
            `${d.voided_hidden} voided entr${Number(d.voided_hidden) === 1 ? "y is" : "ies are"} hidden here (a voided document and its reversal cancel out; the balances already allow for them).`}{" "}
          <button className="font-medium text-primary underline" onClick={() => onShowVoided(!showVoided)}>{showVoided ? "Hide them" : "Show them"}</button>
        </div>
      )}
      <Facts cols={4} items={[["Account", `${d.account.code} · ${d.account.name}`], ["Type", `${d.account.subtype.replace(/_/g, " ").toLowerCase()}`],
        ["Beginning balance", <Amount value={d.opening} />], ["Ending balance", <Amount value={d.closing} bold />]]} />
      <H right={<CsvButton filename={`general-ledger-${d.account.code}.csv`} rows={lines} />}>{d.search ? `Lines matching "${d.search}" (${d.lines_shown})` : `General Ledger (${d.lines_shown} lines)`}</H>
      <Table>
        <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Reference</TableHead><TableHead>Jrnl</TableHead><TableHead>Trans Description</TableHead>
          <TableHead className="text-right">Debit Amt</TableHead><TableHead className="text-right">Credit Amt</TableHead><TableHead className="text-right">Balance</TableHead></TableRow></TableHeader>
        <TableBody>{d.months.map((m: Dict) => [
          <TableRow key={`${m.month}-b`} className="bg-muted/40"><TableCell className="whitespace-nowrap text-xs">{fmtDate(`${m.month}-01`)}</TableCell>
            <TableCell /><TableCell /><TableCell className="text-xs font-medium">Beginning Balance</TableCell><TableCell /><TableCell />
            <TableCell className="text-right"><Amount value={m.beginning} /></TableCell></TableRow>,
          ...m.lines.map((l: Dict) => (
            <TableRow key={l.line_id} className={l.voided ? "text-muted-foreground line-through decoration-muted-foreground/50" : undefined}
                      title={l.voided ? "Voided - this entry and its reversal cancel out" : undefined}>
              <TableCell className="whitespace-nowrap text-xs">{fmtDate(l.date)}{l.voided && <span className="ml-1 no-underline">(void)</span>}</TableCell>
              <TableCell><DrillLink to={lineTarget(l)}><span className="font-mono text-xs">{l.reference || l.journal_number}</span></DrillLink></TableCell>
              <TableCell className="text-xs">{l.jrnl}{l.origin === "SAGE" ? <span className="ml-1 text-muted-foreground">Sage</span> : null}</TableCell>
              <TableCell className="max-w-[340px] truncate text-xs">{l.description}</TableCell>
              <TableCell className="text-right"><Amount value={l.debit} blankZero /></TableCell><TableCell className="text-right"><Amount value={l.credit} blankZero /></TableCell>
              <TableCell className="text-right"><Amount value={l.balance} /></TableCell>
            </TableRow>)),
          <TableRow key={`${m.month}-c`} className="text-xs text-muted-foreground"><TableCell /><TableCell /><TableCell /><TableCell>Current Period Change</TableCell>
            <TableCell className="text-right"><Amount value={m.debit} blankZero /></TableCell><TableCell className="text-right"><Amount value={m.credit} blankZero /></TableCell>
            <TableCell className="text-right"><Amount value={m.change} /></TableCell></TableRow>,
        ])}</TableBody>
      </Table>
      {d.truncated && <p className="text-xs text-muted-foreground">Showing the first {d.lines_shown.toLocaleString()} lines - narrow the dates or search.</p>}
    </>
  );
}

function AccountContent({ d }: { d: Dict }) {
  const [rows, box] = useListFilter<Dict>(d.rows, "Search reference, description");
  return (
    <>
      <Facts cols={4} items={[["Account", `${d.account.code} · ${d.account.name}`], ["Type", `${d.account.subtype.replace(/_/g, " ").toLowerCase()}`],
        ["Opening", <Amount value={d.opening} />], ["Closing", <Amount value={d.closing} bold />]]} />
      <H right={<div className="flex gap-2">{box}<CsvButton filename={`ledger-${d.account.code}.csv`} rows={d.rows} /></div>}>Ledger lines ({d.count})</H>
      <Table>
        <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Reference</TableHead><TableHead className="text-right">Dr</TableHead><TableHead className="text-right">Cr</TableHead><TableHead className="text-right">Balance</TableHead></TableRow></TableHeader>
        <TableBody>{rows.map((r: Dict) => (
          <TableRow key={r.line_id}>
            <TableCell className="whitespace-nowrap">{fmtDate(r.journal_date)}</TableCell>
            <TableCell><DrillLink to={sourceTarget(r.source_type, r.source_id) ?? { type: "journal", id: r.journal_id }}><span className="font-mono text-xs">{r.source_ref || r.journal_number}</span></DrillLink>
              <div className="max-w-[260px] truncate text-xs text-muted-foreground">{r.description}</div>
              <div className="text-xs"><J id={r.journal_id} n={r.journal_number} /></div></TableCell>
            <TableCell className="text-right"><Amount value={r.debit} blankZero /></TableCell><TableCell className="text-right"><Amount value={r.credit} blankZero /></TableCell>
            <TableCell className="text-right"><Amount value={r.running_balance} /></TableCell>
          </TableRow>
        ))}</TableBody>
      </Table>
      {d.count > d.rows.length && <p className="text-xs text-muted-foreground">Showing {d.rows.length} of {d.count} lines.</p>}
    </>
  );
}

// ---------------------------------------------------------------------------
// Sales documents
// ---------------------------------------------------------------------------

export function InvoiceBody({ id }: { id: string }) {
  return (
    <Load path={`/sales/invoices/${id}`}>{(i) => (
      <div className="space-y-3 text-sm">
        <div className="flex flex-wrap items-center gap-2"><StatusBadge status={i.status} /><span className="font-mono">{i.invoice_number}</span>
          {Number(i.balance_due) > 0 && ["POSTED", "PARTIALLY_PAID"].includes(i.status) && <RecordReceipt invoice={i} />}
          {i.is_opening && <Badge variant="outline">opening balance from Sage</Badge>}
          {i.source_type === "BILLING" && <Badge variant="outline">patient's share of a hospital bill</Badge>}
          {i.source_type === "BILLING_HMO" && <Badge variant="outline">HMO's share of a hospital bill</Badge>}</div>
        <Facts items={[["Billed to", <Cust id={i.customer_id} name={i.customer_name} />], ["Type", PARTY[i.party_type]], ["MRN", i.mrn],
          ["Invoice date", fmtDate(i.invoice_date)], ["Due", fmtDate(i.due_date)], ["Bill / reference", i.reference],
          ["Journal", i.journal_id ? <J id={i.journal_id} n={i.journal_number} /> : i.is_opening ? "in the opening balances" : null],
          ["Credit override", i.credit_override_reason]]} />
        {i.hospital_bill && (
          <div className="rounded-lg border p-2 text-xs">
            <div className="mb-1 font-semibold">Hospital bill {i.hospital_bill.bill_number}</div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground">
              <span>raised {fmtDate(i.hospital_bill.billed_at)}</span><span>encounter #{i.hospital_bill.encounter_id}</span>
              <span>bill total {naira(i.hospital_bill.subtotal)}</span>
              {Number(i.hospital_bill.hmo_covered) > 0 && <span>HMO covers {naira(i.hospital_bill.hmo_covered)}</span>}
              {Number(i.hospital_bill.discount) > 0 && <span>discount {naira(i.hospital_bill.discount)} ({i.hospital_bill.discount_status})</span>}
              <span>cashier status: {i.hospital_bill.status}</span>
            </div>
            <Link className="mt-1 inline-flex items-center text-xs hover:underline" to={`/hospital/billing/${i.hospital_bill.id}/invoice`}>open the printed bill <ArrowUpRight className="h-3 w-3" /></Link>
          </div>
        )}
        {i.lines?.length > 0 && (<><H>What was billed</H>
          <Table>
            <TableHeader><TableRow><TableHead>Service / item</TableHead><TableHead className="text-right">Qty</TableHead><TableHead className="text-right">Price</TableHead><TableHead className="text-right">Amount</TableHead><TableHead className="text-right">Cost</TableHead></TableRow></TableHeader>
            <TableBody>{i.lines.map((l: Dict) => (
              <TableRow key={l.id}>
                <TableCell><div>{l.sku ? <Prod sku={l.sku} /> : l.description}</div><div className="text-xs text-muted-foreground">{l.sku && l.description}{l.batch_id && <> · batch <Bat id={l.batch_id} n={l.batch_number} /></>}{l.category && ` · ${l.category}`} → {l.account_code} {l.account_name}</div></TableCell>
                <TableCell className="text-right">{num(l.quantity)}</TableCell>
                <TableCell className="text-right"><Amount value={l.unit_price} />{Number(l.discount_amount) > 0 && <div className="text-xs text-muted-foreground">−{naira(l.discount_amount)}</div>}</TableCell>
                <TableCell className="text-right"><Amount value={l.line_total} /></TableCell><TableCell className="text-right"><Amount value={l.cost_amount} blankZero /></TableCell>
              </TableRow>
            ))}</TableBody>
          </Table></>)}
        <Totals rows={[["Subtotal", i.subtotal], ["Discounts", Number(i.discount_total) ? -Number(i.discount_total) : undefined], ["Charges", Number(i.charge_total) ? i.charge_total : undefined],
          ["Tax", Number(i.tax_total) ? i.tax_total : undefined], ["Total", i.total, true], ["Paid / credited", -Number(i.amount_settled)], ["Balance due", i.balance_due, true]]} />
        {i.allocations?.length > 0 && (<><H>Paid / credited by</H>
          {i.allocations.map((a: Dict) => (
            <div key={a.id} className="flex justify-between text-xs"><DrillLink to={{ type: a.source_type === "CREDIT_NOTE" ? "creditnote" : "receipt", id: a.source_id, label: a.source_number }}>{a.source_number}</DrillLink>
              <span>{fmtDate(a.allocation_date)} · <Amount value={a.amount} />{a.reversed ? " (reversed)" : ""}</span></div>
          ))}</>)}
        {i.credit_notes?.length > 0 && (<><H>Credit notes (discounts, waivers, corrections)</H>
          {i.credit_notes.map((n: Dict) => (
            <div key={n.id} className="flex justify-between text-xs"><DrillLink to={{ type: "creditnote", id: n.id, label: n.credit_note_number }}>{n.credit_note_number}</DrillLink>
              <span className="truncate px-2 text-muted-foreground">{n.reason}</span><Amount value={n.total} /></div>))}</>)}
        {i.void_reason && <p className="text-xs text-red-600">Voided: {i.void_reason}</p>}
        <PageLink to={sourceLink("SALES_INVOICE", id)} />
      </div>
    )}</Load>
  );
}

export function ReceiptBody({ id }: { id: string }) {
  return (
    <Load path={`/receivables/receipts/${id}`}>{(r) => (
      <div className="space-y-3 text-sm">
        <div className="flex items-center gap-2"><StatusBadge status={r.status} /><span className="font-mono">{r.receipt_number}</span></div>
        <Facts items={[["From", <Cust id={r.customer_id} name={r.customer_name} />], ["Date", fmtDate(r.receipt_date)], ["Method", `${r.method?.toLowerCase()}`],
          ["Cheque / ref", r.reference], ["Into", r.bank_account_name], ["Journal", <J id={r.journal_id} n={r.journal_number} />]]} />
        <Totals rows={[["Received", r.amount, true], ["WHT deducted", Number(r.wht_amount) ? r.wht_amount : undefined], ["Applied", r.amount_allocated], ["On account", r.unapplied, true]]} />
        {r.allocations?.length > 0 && (<><H>Applied to invoices</H>{r.allocations.map((a: Dict) => (
          <div key={a.id} className="flex justify-between text-xs"><DrillLink to={{ type: "invoice", id: a.invoice_id, label: a.invoice_number }}>{a.invoice_number}</DrillLink>
            <span>{fmtDate(a.allocation_date)} · <Amount value={a.amount} />{a.reversed ? " (reversed)" : ""}</span></div>))}</>)}
        {r.void_reason && <p className="text-xs text-red-600">Voided: {r.void_reason}</p>}
        <PageLink to={sourceLink("CUSTOMER_RECEIPT", id)} />
      </div>
    )}</Load>
  );
}

export function CreditNoteBody({ id }: { id: string }) {
  return (
    <Load path={`/sales/credit-notes/${id}`}>{(n) => {
      const opening = !n.journal_id && String(n.credit_note_number).startsWith("OB-");
      return (
        <div className="space-y-3 text-sm">
          <div className="flex flex-wrap items-center gap-2"><StatusBadge status={n.status} /><span className="font-mono">{n.credit_note_number}</span>{opening && <Badge variant="outline">opening balance from Sage</Badge>}
            {n.source_type && <Badge variant="outline">{String(n.source_type).replace(/_/g, " ").toLowerCase()}</Badge>}</div>
          <Facts items={[["Patient / payer", <Cust id={n.customer_id} name={n.customer_name} />], ["Date", fmtDate(n.note_date)],
            ["Against invoice", n.invoice_id ? <DrillLink to={{ type: "invoice", id: n.invoice_id, label: n.invoice_number }}>{n.invoice_number}</DrillLink> : "none (on account)"],
            ["Reason", n.reason], ["Returned to stock", n.lines?.some((l: Dict) => l.inventory_txn_id) ? "yes" : null],
            ["Journal", n.journal_id ? <J id={n.journal_id} n={n.journal_number} /> : opening ? "in the opening balances" : null]]} />
          <Totals rows={[["Credit total", n.total, true], ["Applied to invoices", n.amount_settled], ["Unapplied (on account)", n.unapplied ?? Number(n.total) - Number(n.amount_settled || 0), true]]} />
          {n.lines?.length > 0 && (<><H>Lines</H><Table><TableBody>{n.lines.map((l: Dict) => (
            <TableRow key={l.id}><TableCell>{l.sku ? <Prod sku={l.sku} /> : l.description}</TableCell>
              <TableCell className="text-right">{num(l.quantity)}</TableCell><TableCell className="text-right"><Amount value={l.line_total} /></TableCell></TableRow>))}</TableBody></Table></>)}
          {n.allocations?.length > 0 && (<><H>Applied to</H>{n.allocations.map((a: Dict) => (
            <div key={a.id} className="flex justify-between text-xs"><DrillLink to={{ type: "invoice", id: a.invoice_id, label: a.invoice_number }}>{a.invoice_number}</DrillLink><Amount value={a.amount} /></div>))}</>)}
          {opening && <p className="text-xs text-muted-foreground">A credit that was open in Sage at cut-over. Apply it to this debtor's invoices from Receivables › Credit notes, or it stays on their account.</p>}
          <PageLink to={sourceLink("CREDIT_NOTE", id)} />
        </div>
      );
    }}</Load>
  );
}

export function RefundBody({ id }: { id: string }) {
  return (
    <Load path={`/receivables/refunds/${id}`}>{(r) => (
      <div className="space-y-3 text-sm">
        <div className="flex items-center gap-2"><StatusBadge status={r.status} /><span className="font-mono">{r.refund_number}</span></div>
        <Facts items={[["Paid to", <Cust id={r.customer_id} name={r.customer_name} />], ["Date", fmtDate(r.refund_date)], ["Paid from", r.bank_account_name],
          ["Out of", <DrillLink to={{ type: r.credit_type === "RECEIPT" ? "receipt" : "creditnote", id: r.credit_id, label: r.credit_number }}>{r.credit_number}</DrillLink>],
          ["Reason", r.reason], ["Journal", <J id={r.journal_id} n={r.journal_number} />]]} />
        <Totals rows={[["Refunded", r.amount, true]]} />
      </div>
    )}</Load>
  );
}

// ---------------------------------------------------------------------------
// Royan's Sage 50 history (2009 -> 2024): read-only records with full lineage
// ---------------------------------------------------------------------------

const SAGE_BADGE = <Badge variant="outline">Sage 50 history — before Roy Books</Badge>;

function SageLines({ lines }: { lines: Dict[] }) {
  const [list, box] = useListFilter<Dict>(lines, "Search account, description");
  if (!lines?.length) return null;
  return (
    <>
      <H right={box}>Ledger lines (as posted in Sage)</H>
      <Table>
        <TableHeader><TableRow><TableHead>Account</TableHead><TableHead>Description</TableHead><TableHead className="text-right">Debit</TableHead><TableHead className="text-right">Credit</TableHead></TableRow></TableHeader>
        <TableBody>{list.map((l: Dict) => (
          <TableRow key={l.id}>
            <TableCell>{l.account_id ? <DrillLink to={{ type: "account", id: l.account_id, label: l.account_code }}>{l.account_code} · {l.account_name}</DrillLink> : l.account_code}</TableCell>
            <TableCell className="text-xs">{l.description}{l.customer_id && <> · <Cust id={l.customer_id} name={l.customer_name} /></>}</TableCell>
            <TableCell className="text-right"><Amount value={l.debit} blankZero /></TableCell><TableCell className="text-right"><Amount value={l.credit} blankZero /></TableCell>
          </TableRow>))}</TableBody>
      </Table>
    </>
  );
}

export function SageVoucherBody({ id }: { id: string }) {
  return (
    <Load path="/sage/vouchers" params={{ key: id }}>{(v) => (
      <div className="space-y-3 text-sm">
        <div className="flex flex-wrap items-center gap-2">{SAGE_BADGE}<Badge variant="outline">{v.journal}</Badge></div>
        <Facts items={[["Date", fmtDate(v.date)], ["Reference", v.reference || "—"], ["Journal", v.jrnl],
          ["Patient / payer", v.customer_id ? <Cust id={v.customer_id} name={v.customer_name} /> : null],
          ["Total", <Amount value={v.total_debit} bold />], ["Lines", v.lines.length]]} />
        {v.invoices?.length > 0 && (<><H>Invoice</H>{v.invoices.map((i: Dict) => (
          <div key={i.id} className="flex justify-between text-xs"><DrillLink to={{ type: "sageinvoice", id: String(i.id), label: i.invoice_number }}>Invoice {i.invoice_number} · {i.customer_name}</DrillLink><Amount value={i.amount} /></div>))}</>)}
        {v.receipts?.length > 0 && (<><H>Receipts</H>{v.receipts.map((r: Dict) => (
          <div key={r.id} className="flex justify-between text-xs"><DrillLink to={{ type: "sagereceipt", id: String(r.id), label: r.reference }}>{r.reference} · {r.payer}</DrillLink><Amount value={r.amount} /></div>))}</>)}
        <SageLines lines={v.lines} />
      </div>
    )}</Load>
  );
}

export function SageInvoiceBody({ id }: { id: string }) {
  return (
    <Load path={`/sage/invoices/${id}`}>{(i) => (
      <div className="space-y-3 text-sm">
        <div className="flex flex-wrap items-center gap-2">{SAGE_BADGE}<span className="font-mono">{i.invoice_number ?? "(no number)"}</span></div>
        <Facts items={[["Billed to", i.customer_id ? <Cust id={i.customer_id} name={i.customer_name} /> : i.customer_name], ["Type", i.party_type?.toLowerCase()],
          ["Date", fmtDate(i.invoice_date)], ["Quote no.", i.quote_number], ["Sage register row", i.row_no]]} />
        <Totals rows={[["Invoiced", i.amount, true], ["Received (matched receipts)", i.amount_received], ["Not matched to a receipt", i.balance, true]]} />
        {i.receipts?.length > 0 && (<><H>Paid by</H>{i.receipts.map((r: Dict, n: number) => (
          <div key={n} className="flex justify-between text-xs"><DrillLink to={{ type: "sagereceipt", id: String(r.id), label: r.reference }}>{r.reference}</DrillLink>
            <span className="truncate px-2 text-muted-foreground">{fmtDate(r.receipt_date)} · into {r.bank_account_id ? <DrillLink to={{ type: "account", id: r.bank_account_id, label: r.bank_account_code }}>{r.bank_account_name}</DrillLink> : r.bank_account_code}</span>
            <Amount value={r.amount} /></div>))}</>)}
        {i.voucher && <DrillLink to={{ type: "sagevoucher", id: i.voucher, label: i.invoice_number }}>Open the sales-journal entry</DrillLink>}
        <SageLines lines={i.lines} />
        {!i.lines?.length && <p className="text-xs text-muted-foreground">Sage's register lists this invoice but its sales-journal lines carry no reference to match it.</p>}
      </div>
    )}</Load>
  );
}

export function SageReceiptBody({ id }: { id: string }) {
  return (
    <Load path={`/sage/receipts/${id}`}>{(r) => (
      <div className="space-y-3 text-sm">
        <div className="flex flex-wrap items-center gap-2">{SAGE_BADGE}<span className="font-mono">{r.reference}</span></div>
        <Facts items={[["From", r.customer_id ? <Cust id={r.customer_id} name={r.payer} /> : r.payer], ["Date", fmtDate(r.receipt_date)],
          ["Into", r.bank_account_id ? <DrillLink to={{ type: "account", id: r.bank_account_id, label: r.bank_account_code }}>{r.bank_account_code} · {r.bank_account_name}</DrillLink> : r.bank_account_code],
          ["Amount", <Amount value={r.amount} bold />]]} />
        {r.invoices?.length > 0 && (<><H>Invoices settled</H>{r.invoices.map((i: Dict, n: number) => (
          <div key={n} className="flex justify-between text-xs">
            {i.invoice_id ? <DrillLink to={{ type: "sageinvoice", id: String(i.invoice_id), label: i.invoice_number }}>Invoice {i.invoice_number}</DrillLink> : <span>Invoice {i.invoice_number} (not in the register)</span>}
            <span className="text-muted-foreground">{i.invoice_date ? fmtDate(i.invoice_date) : ""}</span><Amount value={i.amount} /></div>))}</>)}
        {r.voucher && <DrillLink to={{ type: "sagevoucher", id: r.voucher, label: r.reference }}>Open the cash-receipts entry</DrillLink>}
        <SageLines lines={r.lines} />
      </div>
    )}</Load>
  );
}

const PAYER_TYPE: Record<string, string> = { PRIVATE: "Private", HMO: "HMO", CORPORATE: "Corporate / retainership", STAFF: "Staff scheme", INTERNAL: "Paid by Royan" };

/** One Hope visit: the patient, who paid, and every charge line (service, pharmacy, lab, radiology, ward). */
export function VisitBody({ id }: { id: string }) {
  return (
    <Load path={`/hope/visits/${id}`}>{(v) => (
      <div className="space-y-3 text-sm">
        <div className="flex flex-wrap items-center gap-2"><Badge variant="outline">Hope</Badge><span className="font-mono">Visit {v.visit_id}</span>
          <Badge variant={v.payer_type === "PRIVATE" ? "secondary" : "default"}>{PAYER_TYPE[v.payer_type] ?? v.payer_type}</Badge></div>
        <Facts items={[["Patient", v.patient ?? "—"], ["MRN", v.mrn ?? "—"], ["Payer", v.customer_id ? <Cust id={v.customer_id} name={v.payer} /> : v.payer],
          ["Dates", v.from === v.to ? fmtDate(v.from) : `${fmtDate(v.from)} – ${fmtDate(v.to)}`], ["Billed", <Amount value={Number(v.totals.gross) - Number(v.totals.discount)} bold />],
          ["Paid at till", <Amount value={v.totals.paid} />], ["Left for the payer", <Amount value={v.totals.outstanding} />]]} />
        <H>Charge lines</H>
        <Table>
          <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Dept</TableHead><TableHead>Service</TableHead><TableHead className="text-right">Qty</TableHead>
            <TableHead className="text-right">Gross</TableHead><TableHead className="text-right">Discount</TableHead><TableHead className="text-right">Paid</TableHead><TableHead className="text-right">Left</TableHead></TableRow></TableHeader>
          <TableBody>{v.lines.map((l: Dict) => (
            <TableRow key={`${l.source}:${l.hope_id}`}>
              <TableCell className="whitespace-nowrap text-xs">{fmtDate(l.charge_date)}</TableCell><TableCell className="text-xs">{l.source.toLowerCase()}</TableCell>
              <TableCell className="text-xs">{l.service ?? l.category}{l.reference ? <span className="text-muted-foreground"> · {l.reference}</span> : null}</TableCell>
              <TableCell className="text-right text-xs">{num(l.quantity)}</TableCell><TableCell className="text-right"><Amount value={l.gross} /></TableCell>
              <TableCell className="text-right"><Amount value={l.discount} blankZero /></TableCell><TableCell className="text-right"><Amount value={l.paid} blankZero /></TableCell>
              <TableCell className="text-right"><Amount value={l.outstanding} blankZero /></TableCell>
            </TableRow>))}</TableBody>
        </Table>
        <p className="text-xs text-muted-foreground">From the Hope extract (January 2026). Pharmacy sales are often settled on the patient's final bill, so a pharmacy line can show nothing paid even when the patient paid.</p>
      </div>
    )}</Load>
  );
}

function SageCustomerHistory({ s }: { s: Dict }) {
  const [inv, invBox] = useListFilter<Dict>(s.invoices, "Search invoices");
  const [rec, recBox] = useListFilter<Dict>(s.receipts, "Search receipts");
  if (!s.invoices?.length && !s.receipts?.length) return <p className="text-xs text-muted-foreground">No Sage history for this account.</p>;
  return (
    <div className="space-y-2">
      <Facts cols={4} items={[["Sage IDs", s.codes.map((c: Dict) => c.sage_code).join(", ")], ["Invoiced in Sage", <Amount value={s.invoiced_total} />],
        ["Received in Sage", <Amount value={s.received_total} />], ["Years", s.by_year.length]]} />
      <H>By year</H>
      <Table><TableHeader><TableRow><TableHead>Year</TableHead><TableHead className="text-right">Invoices</TableHead><TableHead className="text-right">Invoiced</TableHead><TableHead className="text-right">Received</TableHead></TableRow></TableHeader>
        <TableBody>{s.by_year.map((y: Dict) => (
          <TableRow key={y.y}><TableCell>{y.y}</TableCell><TableCell className="text-right">{num(y.invoices)}</TableCell>
            <TableCell className="text-right"><Amount value={y.invoiced} /></TableCell><TableCell className="text-right"><Amount value={y.received} /></TableCell></TableRow>))}</TableBody></Table>
      <H right={invBox}>Sage invoices</H>
      <Table><TableBody>{inv.slice(0, 300).map((i: Dict) => (
        <TableRow key={i.id}><TableCell><DrillLink to={{ type: "sageinvoice", id: String(i.id), label: i.invoice_number }}>{i.invoice_number ?? "—"}</DrillLink></TableCell>
          <TableCell className="whitespace-nowrap text-xs">{fmtDate(i.invoice_date)}</TableCell><TableCell className="text-right"><Amount value={i.amount} /></TableCell>
          <TableCell className="text-right text-xs text-muted-foreground"><Amount value={i.amount_received} blankZero /></TableCell></TableRow>))}</TableBody></Table>
      <H right={recBox}>Sage receipts</H>
      <Table><TableBody>{rec.slice(0, 300).map((r: Dict) => (
        <TableRow key={r.id}><TableCell><DrillLink to={{ type: "sagereceipt", id: String(r.id), label: r.reference }}>{r.reference}</DrillLink></TableCell>
          <TableCell className="whitespace-nowrap text-xs">{fmtDate(r.receipt_date)} · {r.bank_account_name}</TableCell><TableCell className="text-right"><Amount value={r.amount} /></TableCell></TableRow>))}</TableBody></Table>
      {(s.invoices.length > 300 || s.receipts.length > 300) && <p className="text-xs text-muted-foreground">Showing the latest 300 of each; use Report Center › Transaction History for the full list.</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Purchasing & banking documents
// ---------------------------------------------------------------------------

export function BillBody({ id }: { id: string }) {
  return (
    <Load path={`/payables/bills/${id}`}>{(b) => (
      <div className="space-y-3 text-sm">
        <div className="flex flex-wrap items-center gap-2"><StatusBadge status={b.status} /><span className="font-mono">{b.bill_number}</span>{b.is_opening && <Badge variant="outline">opening balance from Sage</Badge>}
          {Number(b.balance_due) > 0 && ["POSTED", "PARTIALLY_PAID"].includes(b.status) &&
            <Link className="ml-auto" to={`/finance/books/purchases?new=payment&supplier=${b.supplier_id}&pay=${b.id}`}><Button size="sm">Pay this bill</Button></Link>}</div>
        <Facts items={[["Supplier", <Sup id={b.supplier_id} name={b.supplier_name} />], ["Supplier invoice", b.supplier_invoice_number], ["Bill date", fmtDate(b.bill_date)],
          ["Due", fmtDate(b.due_date)], ["Journal", b.journal_id ? <J id={b.journal_id} n={b.journal_number} /> : b.is_opening ? "in the opening balances" : null], ["Notes", b.notes]]} />
        {b.lines?.length > 0 && (<><H>What was bought</H><Table>
          <TableHeader><TableRow><TableHead>Item / account</TableHead><TableHead className="text-right">Qty</TableHead><TableHead className="text-right">Unit cost</TableHead><TableHead className="text-right">Amount</TableHead></TableRow></TableHeader>
          <TableBody>{b.lines.map((l: Dict) => (
            <TableRow key={l.id}><TableCell><div>{l.sku ? <Prod sku={l.sku} /> : l.description}</div><div className="text-xs text-muted-foreground">{l.batch_id && <>batch <Bat id={l.batch_id} n={l.batch_number} /> </>}{l.expiry_date && `exp ${fmtDate(l.expiry_date)} · `}{l.account_code} {l.account_name}</div></TableCell>
              <TableCell className="text-right">{num(l.quantity)}</TableCell><TableCell className="text-right"><Amount value={l.unit_cost} /></TableCell><TableCell className="text-right"><Amount value={l.line_total} /></TableCell></TableRow>))}</TableBody></Table></>)}
        <Totals rows={[["Total", b.total, true], ["Paid / returned", b.amount_settled], ["Still owed", b.balance_due, true]]} />
        {b.allocations?.length > 0 && (<><H>Paid / returned by</H>{b.allocations.map((a: Dict) => (
          <div key={a.id} className="flex justify-between text-xs"><DrillLink to={{ type: a.source_type === "DEBIT_NOTE" ? "debitnote" : "payment", id: a.source_id, label: a.source_number }}>{a.source_number}</DrillLink><Amount value={a.amount} /></div>))}</>)}
        {b.void_reason && <p className="text-xs text-red-600">Voided: {b.void_reason}</p>}
        <PageLink to={sourceLink("SUPPLIER_BILL", id)} />
      </div>
    )}</Load>
  );
}

export function PaymentBody({ id }: { id: string }) {
  return (
    <Load path={`/payables/payments/${id}`}>{(p) => (
      <div className="space-y-3 text-sm">
        <div className="flex items-center gap-2"><StatusBadge status={p.status} /><span className="font-mono">{p.payment_number}</span></div>
        <Facts items={[["Paid to", <Sup id={p.supplier_id} name={p.supplier_name} />], ["Date", fmtDate(p.payment_date)], ["Method", p.method?.toLowerCase()],
          ["Cheque / ref", p.reference], ["From", p.bank_account_name], ["Journal", <J id={p.journal_id} n={p.journal_number} />]]} />
        <Totals rows={[["Paid", p.amount, true], ["WHT withheld", Number(p.wht_amount) ? p.wht_amount : undefined], ["Applied", p.amount_allocated], ["Unapplied", p.unapplied, true]]} />
        {p.allocations?.length > 0 && (<><H>Settled bills</H>{p.allocations.map((a: Dict) => (
          <div key={a.id} className="flex justify-between text-xs"><DrillLink to={{ type: "bill", id: a.bill_id, label: a.bill_number }}>{a.bill_number} {a.supplier_invoice_number && `(${a.supplier_invoice_number})`}</DrillLink><Amount value={a.amount} /></div>))}</>)}
        {p.void_reason && <p className="text-xs text-red-600">Voided: {p.void_reason}</p>}
      </div>
    )}</Load>
  );
}

export function DebitNoteBody({ id }: { id: string }) {
  return (
    <Load path={`/payables/debit-notes/${id}`}>{(d) => (
      <div className="space-y-3 text-sm">
        <Facts items={[["Number", d.debit_note_number], ["Supplier", <Sup id={d.supplier_id} name={d.supplier_name} />], ["Date", fmtDate(d.note_date)],
          ["Against bill", d.bill_id ? <DrillLink to={{ type: "bill", id: d.bill_id, label: d.bill_number }}>{d.bill_number}</DrillLink> : "none"], ["Reason", d.reason],
          ["Journal", <J id={d.journal_id} n={d.journal_number} />]]} />
        <Totals rows={[["Total", d.total, true], ["Applied", d.amount_settled]]} />
        {(d.lines ?? []).length > 0 && <Table><TableBody>{d.lines.map((l: Dict) => (
          <TableRow key={l.id}><TableCell><Prod sku={l.sku} /> {l.batch_id && <Bat id={l.batch_id} />}</TableCell><TableCell className="text-right">{num(l.quantity)}</TableCell><TableCell className="text-right"><Amount value={l.line_total} /></TableCell></TableRow>))}</TableBody></Table>}
      </div>
    )}</Load>
  );
}

export function VoucherBody({ id }: { id: string }) {
  return (
    <Load path={`/banking/vouchers/${id}`}>{(v) => (
      <div className="space-y-3 text-sm">
        <div className="flex items-center gap-2"><StatusBadge status={v.status} /><span className="font-mono">{v.voucher_number}</span><Badge variant="outline">{v.kind.toLowerCase()}</Badge></div>
        <Facts items={[["Date", fmtDate(v.voucher_date)], ["Account", `${v.bank_account_name}${v.to_bank_account_name ? ` → ${v.to_bank_account_name}` : ""}`], ["Payee", v.payee],
          ["Reference", v.reference], ["Amount", <Amount value={v.amount} bold />], ["Journal", <J id={v.journal_id} n={v.journal_number} />]]} />
        {(v.lines ?? []).length > 0 && (<><H>What it was for</H><Table><TableBody>{v.lines.map((l: Dict) => (
          <TableRow key={l.id}><TableCell><DrillLink to={{ type: "account", id: l.account_id, label: l.account_code }}>{l.account_code} · {l.account_name}</DrillLink><div className="text-xs text-muted-foreground">{l.description}</div></TableCell>
            <TableCell className="text-right"><Amount value={l.amount} /></TableCell></TableRow>))}</TableBody></Table></>)}
        {v.void_reason && <p className="text-xs text-red-600">Voided: {v.void_reason}</p>}
      </div>
    )}</Load>
  );
}

// ---------------------------------------------------------------------------
// Parties
// ---------------------------------------------------------------------------

function CustomerBody({ id }: { id: string }) {
  return <Load path={`/customers/${id}/overview`}>{(d) => <CustomerContent d={d} />}</Load>;
}

function CustomerContent({ d }: { d: Dict }) {
  const [invoices, invBox] = useListFilter<Dict>(d.invoices, "Search invoices");
  const [products, prodBox] = useListFilter<Dict>(d.products ?? [], "Search items");
  const c = d.customer;
  return (
    <div className="space-y-3 text-sm">
      <Facts items={[["Name", c.name], ["Type", PARTY[c.party_type] ?? c.party_type], [c.party_type === "PATIENT" ? "MRN" : "Code", c.mrn ?? c.customer_code],
        ["Owes now", <Amount value={d.balance} bold />], ["Overdue", <Amount value={d.overdue} />],
        ["Credit limit", Number(c.credit_limit) ? naira(c.credit_limit) : "none"], ["Terms", c.payment_terms_days ? `${c.payment_terms_days} days` : "at the till"],
        ["Phone", c.contact_details?.phone], ["Email", c.contact_details?.email]]} />
      {c.patient_id && <Link className="inline-flex items-center text-xs hover:underline" to={`/hospital/patients/${encodeURIComponent(c.mrn ?? "")}`}>open the patient record <ArrowUpRight className="h-3 w-3" /></Link>}
      {d.bills_not_in_books?.length > 0 && (
        <div className="rounded-lg border border-sky-300 bg-sky-50 p-2 text-xs dark:bg-sky-500/10">
          <strong>{d.bills_not_in_books.length} hospital bill(s) not in the books yet</strong> — they post automatically once Roy Books is live; failures are retried from Close & Controls:{" "}
          {d.bills_not_in_books.map((f: Dict) => `${f.bill_number} (${f.posting_status ? f.posting_status.toLowerCase() : "not attempted"})`).join(", ")}
        </div>
      )}
      <Tabs defaultValue="open">
        <TabsList className="flex-wrap">
          <TabsTrigger value="open">Invoices ({d.invoices.length})</TabsTrigger>
          <TabsTrigger value="products">Services & drugs</TabsTrigger>
          <TabsTrigger value="receipts">Receipts ({d.receipts.length})</TabsTrigger>
          {d.refunds?.length > 0 && <TabsTrigger value="refunds">Refunds ({d.refunds.length})</TabsTrigger>}
          {(d.sage?.invoices?.length > 0 || d.sage?.receipts?.length > 0) && <TabsTrigger value="sage">Sage history ({d.sage.invoices.length + d.sage.receipts.length})</TabsTrigger>}
          {d.loans.length > 0 && <TabsTrigger value="loans">On loan ({d.loans.length})</TabsTrigger>}
        </TabsList>
        <TabsContent value="open">
          <H right={invBox}>Invoices (incl. open items from Sage)</H>
          <Table><TableBody>{invoices.map((i: Dict) => (
            <TableRow key={i.id}><TableCell><DrillLink to={{ type: "invoice", id: i.id, label: i.invoice_number }}>{i.invoice_number}</DrillLink>{i.is_opening && <span className="ml-1 text-xs text-muted-foreground">opening</span>}</TableCell>
              <TableCell className="whitespace-nowrap text-xs">{fmtDate(i.invoice_date)}</TableCell><TableCell className="text-right"><Amount value={i.total} /></TableCell>
              <TableCell className="text-right"><Amount value={i.balance} blankZero /></TableCell><TableCell><StatusBadge status={i.status} /></TableCell></TableRow>))}</TableBody></Table>
        </TabsContent>
        <TabsContent value="products">
          <H right={prodBox}>Stock items billed</H>
          {products.length === 0 ? <p className="text-xs text-muted-foreground">No stock items billed directly — services are itemised on each invoice, and drugs dispensed appear under the drug's movements.</p> : (
          <Table><TableHeader><TableRow><TableHead>Item</TableHead><TableHead className="text-right">Qty</TableHead><TableHead className="text-right">Amount</TableHead><TableHead>Last</TableHead></TableRow></TableHeader>
            <TableBody>{products.map((p: Dict, i: number) => (
              <TableRow key={i}><TableCell><Prod sku={p.sku}>{p.sku ?? p.name}</Prod><div className="text-xs text-muted-foreground">{p.name}</div></TableCell>
                <TableCell className="text-right">{num(p.quantity)}</TableCell><TableCell className="text-right"><Amount value={p.amount} /></TableCell><TableCell className="whitespace-nowrap text-xs">{fmtDate(p.last_date)}</TableCell></TableRow>))}</TableBody></Table>)}
        </TabsContent>
        <TabsContent value="receipts">
          <Table><TableBody>{d.receipts.map((r: Dict) => (
            <TableRow key={r.id}><TableCell><DrillLink to={{ type: "receipt", id: r.id, label: r.receipt_number }}>{r.receipt_number}</DrillLink></TableCell>
              <TableCell className="text-xs">{fmtDate(r.receipt_date)} · {r.method?.toLowerCase()} {r.reference}</TableCell><TableCell className="text-right"><Amount value={r.amount} /></TableCell></TableRow>))}</TableBody></Table>
        </TabsContent>
        <TabsContent value="refunds">
          <Table><TableBody>{(d.refunds ?? []).map((r: Dict) => (
            <TableRow key={r.id}><TableCell><DrillLink to={{ type: "refund", id: r.id, label: r.refund_number }}>{r.refund_number}</DrillLink></TableCell>
              <TableCell className="text-xs">{fmtDate(r.refund_date)} · {r.reason}</TableCell><TableCell className="text-right"><Amount value={r.amount} /></TableCell></TableRow>))}</TableBody></Table>
        </TabsContent>
        <TabsContent value="loans">
          {d.loans.map((l: Dict) => (
            <div key={l.id} className="flex justify-between text-xs"><DrillLink to={{ type: "loan", id: l.id, label: l.loan_number }}>{l.loan_number} · {l.sku}</DrillLink><span>{num(l.outstanding)} still out</span></div>))}
        </TabsContent>
        <TabsContent value="sage">{d.sage && <SageCustomerHistory s={d.sage} />}</TabsContent>
      </Tabs>
    </div>
  );
}

function SupplierBody({ id }: { id: string }) {
  return <Load path={`/suppliers/${id}/overview`}>{(d) => <SupplierContent d={d} />}</Load>;
}

function SupplierContent({ d }: { d: Dict }) {
  const [bills, box] = useListFilter<Dict>(d.bills, "Search bills");
  const [history, histBox] = useListFilter<Dict>(d.history_products ?? [], "Search items");
  return (
    <div className="space-y-3 text-sm">
      <Facts items={[["Supplier", d.supplier.name], ["Code", d.supplier.supplier_code], ["We owe", <Amount value={d.balance} bold />], ["Overdue", <Amount value={d.overdue} />],
        ["Terms", d.supplier.payment_terms], ["Phone", d.supplier.phone]]} />
      <Tabs defaultValue="bills">
        <TabsList className="flex-wrap"><TabsTrigger value="bills">Bills ({d.bills.length})</TabsTrigger><TabsTrigger value="products">What we buy ({(d.products ?? []).length})</TabsTrigger>
          <TabsTrigger value="history">Purchase history ({history.length})</TabsTrigger><TabsTrigger value="payments">Payments ({d.payments.length})</TabsTrigger>
          {d.sage_payments?.lines?.length > 0 && <TabsTrigger value="sagepay">Paid in Sage ({d.sage_payments.lines.length})</TabsTrigger>}</TabsList>
        <TabsContent value="bills">
          <H right={box}>Bills</H>
          <Table><TableBody>{bills.map((b: Dict) => (
            <TableRow key={b.id}><TableCell><DrillLink to={{ type: "bill", id: b.id, label: b.bill_number }}>{b.bill_number}</DrillLink><div className="text-xs text-muted-foreground">{b.supplier_invoice_number}</div></TableCell>
              <TableCell className="whitespace-nowrap text-xs">{fmtDate(b.bill_date)}</TableCell><TableCell className="text-right"><Amount value={b.total} /></TableCell>
              <TableCell className="text-right"><Amount value={b.balance} blankZero /></TableCell></TableRow>))}</TableBody></Table>
        </TabsContent>
        <TabsContent value="products">
          <Table><TableBody>{(d.products ?? []).map((p: Dict, i: number) => (
            <TableRow key={i}><TableCell><Prod sku={p.sku}>{p.sku ?? p.name}</Prod><div className="text-xs text-muted-foreground">{p.name}</div></TableCell>
              <TableCell className="text-right">{num(p.quantity)}</TableCell><TableCell className="text-right"><Amount value={p.amount} /></TableCell><TableCell className="whitespace-nowrap text-xs">{fmtDate(p.last_date)}</TableCell></TableRow>))}</TableBody></Table>
        </TabsContent>
        <TabsContent value="history">
          <H right={histBox}>Received from this supplier (Hope purchase orders, before Roy Books)</H>
          <Table><TableHeader><TableRow><TableHead>Item</TableHead><TableHead className="text-right">Orders</TableHead><TableHead className="text-right">Qty</TableHead><TableHead className="text-right">Value</TableHead><TableHead>Last</TableHead></TableRow></TableHeader>
            <TableBody>{history.map((p: Dict, i: number) => (
              <TableRow key={i}><TableCell><Prod sku={p.sku}>{p.sku ?? p.name}</Prod><div className="text-xs text-muted-foreground">{p.name}</div></TableCell>
                <TableCell className="text-right">{num(p.orders)}</TableCell><TableCell className="text-right">{num(p.quantity)}</TableCell><TableCell className="text-right"><Amount value={p.amount} /></TableCell>
                <TableCell className="whitespace-nowrap text-xs">{fmtDate(p.last_date)}</TableCell></TableRow>))}</TableBody></Table>
        </TabsContent>
        <TabsContent value="sagepay">
          {d.sage_payments && (<>
            <p className="text-xs text-muted-foreground">Royan's Sage kept no supplier ledger; these are cash-disbursement lines whose payee matches "{d.sage_payments.matched_on}". Total <Amount value={d.sage_payments.total} />.</p>
            <Table><TableBody>{d.sage_payments.lines.map((l: Dict, i: number) => (
              <TableRow key={i}><TableCell className="whitespace-nowrap text-xs">{fmtDate(l.txn_date)}</TableCell>
                <TableCell className="text-xs"><DrillLink to={{ type: "sagevoucher", id: l.voucher }}>{l.description}</DrillLink></TableCell>
                <TableCell className="text-xs"><DrillLink to={{ type: "account", id: l.account_id, label: l.account_code }}>{l.account_code} {l.account_name}</DrillLink></TableCell>
                <TableCell className="text-right"><Amount value={l.debit} /></TableCell></TableRow>))}</TableBody></Table></>)}
        </TabsContent>
        <TabsContent value="payments">
          <Table><TableBody>{d.payments.map((p: Dict) => (
            <TableRow key={p.id}><TableCell><DrillLink to={{ type: "payment", id: p.id, label: p.payment_number }}>{p.payment_number}</DrillLink></TableCell><TableCell className="text-xs">{fmtDate(p.payment_date)} · {p.reference}</TableCell>
              <TableCell className="text-right"><Amount value={p.amount} /></TableCell></TableRow>))}</TableBody></Table>
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stock: product -> batch -> movement -> document -> journal
// ---------------------------------------------------------------------------

function Movements({ rows, showSku }: { rows: Dict[]; showSku?: boolean }) {
  const [list, box] = useListFilter<Dict>(rows, "Search movements");
  return (
    <>
      {box && <div className="mb-2 flex justify-end">{box}</div>}
      <Table>
        <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Movement</TableHead><TableHead>Patient / supplier</TableHead><TableHead className="text-right">Qty</TableHead><TableHead className="text-right">Cost</TableHead></TableRow></TableHeader>
        <TableBody>{list.map((m) => (
          <TableRow key={m.id}>
            <TableCell className="whitespace-nowrap text-xs">{fmtDate(m.txn_date)}</TableCell>
            <TableCell className="text-xs"><div>{m.txn_type.replace(/_/g, " ").toLowerCase()} <DrillLink to={sourceTarget(m.source_type, m.source_id)}>{m.reference}</DrillLink></div>
              <div className="text-muted-foreground">{showSku && <><Prod sku={m.sku} /> </>}{m.batch_number && <>batch <Bat id={m.batch_id} n={m.batch_number} /></>}{m.journal_id && <> · <J id={m.journal_id} n={m.journal_number ?? "journal"} /></>}</div></TableCell>
            <TableCell className="text-xs">{m.customer_id ? <Cust id={m.customer_id} name={m.customer_name} /> : m.supplier_id ? <Sup id={m.supplier_id} name={m.supplier_name} /> : m.reason}</TableCell>
            <TableCell className={`text-right ${Number(m.quantity) < 0 ? "text-red-600" : ""}`}>{num(m.quantity)}</TableCell>
            <TableCell className="text-right"><Amount value={m.total_cost} /></TableCell>
          </TableRow>
        ))}</TableBody>
      </Table>
    </>
  );
}

function ProductBody({ sku }: { sku: string }) {
  const [range, setRange] = useState({ from: `${new Date().getFullYear() - 1}-01-01`, to: today() });
  return (
    <Load path={`/products/${encodeURIComponent(sku)}/movements`} params={range}>{(d) => <ProductContent d={d} range={range} setRange={setRange} />}</Load>
  );
}

function ProductContent({ d, range, setRange }: { d: Dict; range: { from: string; to: string }; setRange: (r: { from: string; to: string }) => void }) {
  const got: Record<string, Dict> = {};
  d.movements.filter((m: Dict) => m.txn_type === "SALE" && m.customer_id).forEach((m: Dict) => {
    const b = (got[m.customer_id] ??= { customer_id: m.customer_id, customer_name: m.customer_name, quantity: 0, last_date: m.txn_date });
    b.quantity += -Number(m.quantity);
    if (m.txn_date > b.last_date) b.last_date = m.txn_date;
  });
  const [receivers, recBox] = useListFilter<Dict>(Object.values(got), "Search patients");
  const [purchases, purBox] = useListFilter<Dict>(d.purchase_history ?? [], "Search supplier, batch");
  const p = d.product;
  return (
    <div className="space-y-3 text-sm">
      <Facts cols={4} items={[["Item", p.sku], ["Description", p.name], ["On hand", num(d.on_hand.quantity)], ["Stock value", <Amount value={d.on_hand.value} />],
        ["List price", p.standard_price ? naira(p.standard_price) : null], ["Unit", p.uom], ["Reorder at", p.reorder_level != null ? num(p.reorder_level) : null], ["Status", p.status?.toLowerCase()]]} />
      <Tabs defaultValue="movements">
        <TabsList className="flex-wrap">
          <TabsTrigger value="movements">Stock movements</TabsTrigger>
          <TabsTrigger value="batches">Batches ({d.batches.length})</TabsTrigger>
          <TabsTrigger value="receivers">Who received it ({receivers.length})</TabsTrigger>
          <TabsTrigger value="purchases">Purchase history ({(d.purchase_history ?? []).length})</TabsTrigger>
        </TabsList>
        <TabsContent value="movements">
          <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
          {d.movements.length === 0 ? <p className="text-xs text-muted-foreground">None in this range.</p> : <Movements rows={d.movements} />}
        </TabsContent>
        <TabsContent value="batches">
          {d.batches.length === 0 ? <p className="text-xs text-muted-foreground">No batches.</p> : (
            <Table><TableHeader><TableRow><TableHead>Batch</TableHead><TableHead>Expiry</TableHead><TableHead>Status</TableHead><TableHead className="text-right">On hand</TableHead><TableHead className="text-right">Value</TableHead></TableRow></TableHeader>
              <TableBody>{d.batches.map((b: Dict) => (
                <TableRow key={b.id}><TableCell><Bat id={b.id} n={b.batch_number} /></TableCell><TableCell className={`text-xs ${b.expiry_date && b.expiry_date < today() ? "text-red-600" : ""}`}>{fmtDate(b.expiry_date)}</TableCell>
                  <TableCell><StatusBadge status={b.status} /></TableCell><TableCell className="text-right">{num(b.on_hand)}</TableCell><TableCell className="text-right"><Amount value={b.value} /></TableCell></TableRow>))}</TableBody></Table>)}
        </TabsContent>
        <TabsContent value="receivers">
          <H right={recBox}>Patients dispensed this item (in this date range)</H>
          {receivers.length === 0 ? <p className="text-xs text-muted-foreground">Nobody in this range.</p> : (
            <Table><TableHeader><TableRow><TableHead>Patient</TableHead><TableHead className="text-right">Qty</TableHead><TableHead>Last</TableHead></TableRow></TableHeader>
              <TableBody>{receivers.map((b, i) => (
                <TableRow key={i}><TableCell><Cust id={b.customer_id} name={b.customer_name} /></TableCell><TableCell className="text-right">{num(b.quantity)}</TableCell>
                  <TableCell className="whitespace-nowrap text-xs">{fmtDate(b.last_date)}</TableCell></TableRow>))}</TableBody></Table>)}
        </TabsContent>
        <TabsContent value="purchases">
          <H right={purBox}>Goods received (Hope purchase orders, before Roy Books)</H>
          {purchases.length === 0 ? <p className="text-xs text-muted-foreground">No purchase history for this item.</p> : (
            <Table><TableHeader><TableRow><TableHead>Received</TableHead><TableHead>Supplier</TableHead><TableHead>PO / GRN</TableHead><TableHead>Batch</TableHead><TableHead className="text-right">Qty</TableHead><TableHead className="text-right">Unit cost</TableHead><TableHead className="text-right">Amount</TableHead></TableRow></TableHeader>
              <TableBody>{purchases.map((h: Dict, i: number) => (
                <TableRow key={i}><TableCell className="whitespace-nowrap text-xs">{fmtDate(h.received_date)}</TableCell>
                  <TableCell className="text-xs"><Sup id={h.supplier_id} name={h.supplier_name} /></TableCell>
                  <TableCell className="text-xs">{h.po_number}{h.grn_number ? ` · ${h.grn_number}` : ""}</TableCell>
                  <TableCell className="text-xs">{h.batch_number}{h.expiry_date ? ` (exp ${fmtDate(h.expiry_date)})` : ""}</TableCell>
                  <TableCell className="text-right">{num(h.quantity)}</TableCell><TableCell className="text-right"><Amount value={h.unit_cost} /></TableCell>
                  <TableCell className="text-right"><Amount value={h.amount} /></TableCell></TableRow>))}</TableBody></Table>)}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function BatchBody({ id }: { id: string }) {
  return (
    <Load path={`/inventory/batches/${id}/trace`}>{(d) => (
      <div className="space-y-3 text-sm">
        <Facts cols={3} items={[["Product", <Prod sku={d.batch.sku} />], ["Batch", d.batch.batch_number], ["Expiry", fmtDate(d.batch.expiry_date)], ["Status", <StatusBadge status={d.batch.status} />],
          ["On hand", num(d.on_hand?.quantity)], ["Value", <Amount value={d.on_hand?.value} />]]} />
        <H>Who received this batch (the recall list)</H>
        {d.customers.length === 0 ? <p className="text-xs text-muted-foreground">Nobody has been dispensed or sold this batch in Roy Books yet.</p> : d.customers.map((c: Dict) => (
          <div key={c.customer_id} className="flex justify-between text-xs"><Cust id={c.customer_id} name={c.customer_name} /><span>{num(c.quantity_sold)} sold{Number(c.quantity_on_loan) ? `, ${num(c.quantity_on_loan)} on loan` : ""}</span></div>))}
        <H>Movements</H>
        <Movements rows={d.movements.map((m: Dict) => ({ ...m, batch_number: undefined }))} />
      </div>
    )}</Load>
  );
}

function AdjustmentBody({ id }: { id: string }) {
  return (
    <Load path={`/inventory/adjustments/${id}`}>{(a) => (
      <div className="space-y-3 text-sm">
        <Facts items={[["Number", a.adjustment_number], ["Date", fmtDate(a.adjustment_date)], ["Reason", a.reason_code.replace(/_/g, " ").toLowerCase()], ["Status", <StatusBadge status={a.status} />],
          ["Raised by", a.created_by], ["Approved by", a.posted_by], ["Value", <Amount value={a.total_value} />], ["Journal", <J id={a.journal_id} />]]} />
        <Table><TableBody>{a.lines.map((l: Dict) => (
          <TableRow key={l.id}><TableCell><Prod sku={l.sku} /> {l.batch_id && <Bat id={l.batch_id} n={l.batch_number} />}<div className="text-xs text-muted-foreground">{l.reason}</div></TableCell>
            <TableCell className="text-right">{num(l.quantity)}</TableCell><TableCell className="text-right"><Amount value={l.value} blankZero /></TableCell></TableRow>))}</TableBody></Table>
      </div>
    )}</Load>
  );
}

function LoanBody({ id }: { id: string }) {
  return (
    <Load path={`/inventory/loans/${encodeURIComponent(id)}`}>{(l) => (
      <div className="space-y-3 text-sm">
        <Facts items={[["Loan", l.loan_number], ["Lent to", <Cust id={l.customer_id} name={l.customer_name} />], ["Product", <Prod sku={l.sku} />],
          ["Batch", <Bat id={l.batch_id} n={l.batch_number} />], ["Lent", num(l.quantity)], ["Still out", num(l.outstanding)], ["Date", fmtDate(l.loan_date)],
          ["Due back", fmtDate(l.expected_return_date)], ["Status", <StatusBadge status={l.status} />]]} />
        {l.returns?.length > 0 && (<><H>Returns</H>{l.returns.map((r: Dict) => (
          <div key={r.id} className="flex justify-between text-xs"><span>{fmtDate(r.return_date)} · batch <Bat id={r.batch_id} n={r.batch_number} /></span><span>{num(r.quantity)}</span></div>))}</>)}
      </div>
    )}</Load>
  );
}

function AssetBody({ id }: { id: string }) {
  return (
    <Load path={`/assets/${id}`}>{(a) => (
      <div className="space-y-3 text-sm">
        <Facts items={[["Asset", `${a.asset_code} · ${a.name}`], ["Category", a.category_name], ["Acquired", fmtDate(a.acquisition_date)], ["Status", <StatusBadge status={a.status} />],
          ["Cost", <Amount value={a.cost} />], ["Net book value", <Amount value={a.net_book_value} bold />],
          ["Acquisition journal", <J id={a.acquisition_journal_id} />], ["Disposal journal", a.disposal_journal_id ? <J id={a.disposal_journal_id} /> : null]]} />
      </div>
    )}</Load>
  );
}


/** Record a receipt from the invoice it pays: customer and invoice already chosen, amount defaults to the balance. */
function RecordReceipt({ invoice }: { invoice: Dict }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ amount: String(invoice.balance_due), receipt_date: today(), method: "TRANSFER", reference: "", bank_account_id: "" });
  const save = async () => {
    const amt = Number(f.amount || 0);
    if (amt <= 0 || !f.bank_account_id) return;
    if (amt > Number(invoice.balance_due) && !(await askConfirm(`Receive ${naira(amt)} against a balance of ${naira(invoice.balance_due)}?\nThe extra stays on the customer's account as credit.`))) return;
    const r = await act(() => books.post("/receivables/receipts", {
      customer_id: invoice.customer_id, receipt_date: f.receipt_date, method: f.method, bank_account_id: f.bank_account_id, amount: f.amount,
      reference: f.reference || undefined, allocations: [{ invoice_id: invoice.id, amount: String(Math.min(amt, Number(invoice.balance_due))) }],
    }), "Receipt recorded");
    if (r) { setOpen(false); qc.invalidateQueries({ queryKey: ["books"] }); }
  };
  if (!open) return <Button size="sm" className="ml-auto" onClick={() => setOpen(true)}>Record receipt</Button>;
  return (
    <div className="mt-2 w-full space-y-2 rounded-lg border p-3">
      <div className="text-xs font-semibold uppercase text-muted-foreground">Receipt against {invoice.invoice_number} · balance {naira(invoice.balance_due)}</div>
      <div className="grid gap-2 sm:grid-cols-3">
        <label className="space-y-1 text-xs">Amount<Input className="h-9 border" placeholder="0.00" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></label>
        <label className="space-y-1 text-xs">Date<Input type="date" className="h-9 border" value={f.receipt_date} onChange={(e) => setF({ ...f, receipt_date: e.target.value })} /></label>
        <label className="space-y-1 text-xs">Method<select className="h-9 w-full rounded-md border bg-background px-2 text-sm" value={f.method} onChange={(e) => setF({ ...f, method: e.target.value })}>
          {["TRANSFER", "CASH", "CARD", "CHEQUE"].map((m) => <option key={m} value={m}>{m.toLowerCase()}</option>)}</select></label>
        <label className="space-y-1 text-xs">Cheque / transfer ref<Input className="h-9 border" value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} /></label>
        <div className="sm:col-span-2"><BankSelect label="Received into" value={f.bank_account_id} onChange={(v) => setF({ ...f, bank_account_id: v })} /></div>
      </div>
      <div className="flex gap-2"><Button size="sm" disabled={!f.bank_account_id || !(Number(f.amount) > 0)} onClick={save}>Confirm receipt</Button>
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button></div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Data issues
// ---------------------------------------------------------------------------

const SEVERITY_TONE: Record<string, string> = { HIGH: "bg-red-500/15 text-red-700", MEDIUM: "bg-amber-500/15 text-amber-700", LOW: "bg-muted text-muted-foreground" };

export function DataIssueBody({ id }: { id: string }) {
  return <Load path={`/data-issues/${id}`}>{(x) => <DataIssueContent x={x} />}</Load>;
}

function DataIssueContent({ x }: { x: Dict }) {
  const qc = useQueryClient();
  const [mode, setMode] = useState<string | null>(null);
  const [cust, setCust] = useState<Dict | null>(null);
  const [lines, setLines] = useState<{ account: Dict | null; debit: string; credit: string }[]>([{ account: null, debit: "", credit: "" }, { account: null, debit: "", credit: "" }]);
  const run = async (action: string, body: Dict = {}) => {
    if (await act(() => books.post(`/data-issues/${x.id}/${action}`, body), "Saved")) { setMode(null); qc.invalidateQueries({ queryKey: ["books"] }); }
  };
  const choose = async (action: string) => {
    if (action === "accept") { const note = await askText("Why is this accepted as it is?\nThe reason and your name are kept with the issue."); if (note) run("accept", { note }); return; }
    if (action === "reopen") { const note = await askText("Why reopen it?"); if (note !== null) run("reopen", { note }); return; }
    setMode(action);
  };
  const d = x.detail ?? {};
  const batches: Dict[] = d.batches ?? [];
  const dr = lines.reduce((s, l) => s + Number(l.debit || 0), 0), cr = lines.reduce((s, l) => s + Number(l.credit || 0), 0);
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-center gap-2"><StatusBadge status={x.status} />
        <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${SEVERITY_TONE[x.severity] ?? ""}`}>{x.severity.toLowerCase()}</span>
        <span className="text-muted-foreground">{x.kind_label}</span>
        <div className="ml-auto flex flex-wrap gap-2">{x.options.map((o: Dict) => <Button key={o.action} size="sm" variant={o.action === "accept" || o.action === "reopen" ? "outline" : "default"} onClick={() => choose(o.action)}>{o.label}</Button>)}</div></div>
      <div className="text-base font-semibold">{x.title}</div>
      <p>{x.summary}</p>
      <Facts items={[["Amount", x.amount != null ? <Amount value={x.amount} /> : null], ["Quantity", x.quantity != null ? num(x.quantity) : null], ["As of", fmtDate(x.as_of)],
        ["First seen", new Date(x.first_seen).toLocaleString("en-GB")], ["Last checked", new Date(x.last_seen).toLocaleString("en-GB")],
        ["Resolution", x.resolution ? `${x.resolution}${x.resolved_by ? ` by ${x.resolved_by}` : ""}` : null], ["Note", x.resolution_note]]} />
      {x.links?.length > 0 && <div className="flex flex-wrap gap-3">{x.links.map((l: Dict) => <Link key={l.to} to={l.to} className="inline-flex items-center text-xs text-primary hover:underline">{l.label} <ArrowUpRight className="h-3 w-3" /></Link>)}</div>}
      {mode === "link_account" && (
        <div className="space-y-2 rounded-lg border p-3"><div className="text-xs font-semibold uppercase text-muted-foreground">The payer's account in Roy Books / Sage</div>
          <div className="w-80"><CustomerPick label="Account" value={cust} onChange={setCust} /></div>
          <div className="flex gap-2"><Button size="sm" disabled={!cust} onClick={() => run("link_account", { customer_id: cust?.id })}>Link</Button><Button size="sm" variant="ghost" onClick={() => setMode(null)}>Cancel</Button></div></div>)}
      {mode === "post_correction" && (
        <div className="space-y-2 rounded-lg border p-3"><div className="text-xs font-semibold uppercase text-muted-foreground">Correcting journal (numbered FIX-, dated {fmtDate(x.as_of) || "the last Sage day"})</div>
          {lines.map((l, n) => (
            <div key={n} className="grid gap-2 sm:grid-cols-[1fr_140px_140px]">
              <AccountPick label={n === 0 ? "Account" : ""} value={l.account} onChange={(a) => setLines(lines.map((x2, k) => (k === n ? { ...x2, account: a } : x2)))} />
              <Input className="h-9 self-end border" placeholder="Debit 0.00" value={l.debit} onChange={(e) => setLines(lines.map((x2, k) => (k === n ? { ...x2, debit: e.target.value, credit: "" } : x2)))} />
              <Input className="h-9 self-end border" placeholder="Credit 0.00" value={l.credit} onChange={(e) => setLines(lines.map((x2, k) => (k === n ? { ...x2, credit: e.target.value, debit: "" } : x2)))} />
            </div>))}
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="ghost" onClick={() => setLines([...lines, { account: null, debit: "", credit: "" }])}>Add line</Button>
            <span className={`text-xs ${dr === cr && dr > 0 ? "text-emerald-700" : "text-amber-700"}`}>Debits {naira(dr)} · credits {naira(cr)}</span>
            <Button size="sm" className="ml-auto" disabled={dr !== cr || dr <= 0 || lines.some((l) => (Number(l.debit) || Number(l.credit)) && !l.account)} onClick={async () => {
              const note = await askText("What is this correction for?"); if (!note) return;
              run("post_correction", { note, lines: lines.filter((l) => l.account && (Number(l.debit) || Number(l.credit))).map((l) => ({ account_id: l.account!.id, debit: l.debit || undefined, credit: l.credit || undefined })) });
            }}>Post correction</Button>
            <Button size="sm" variant="ghost" onClick={() => setMode(null)}>Cancel</Button>
          </div></div>)}
      {batches.length > 0 && (<><H>Batches</H>
        <Table><TableHeader><TableRow><TableHead>Product</TableHead><TableHead>Batch</TableHead><TableHead>Expiry</TableHead><TableHead className="text-right">On the shelf</TableHead><TableHead className="text-right">Value</TableHead></TableRow></TableHeader>
          <TableBody>{batches.slice(0, 300).map((b: Dict) => (
            <TableRow key={b.id}><TableCell className="text-xs">{b.product}</TableCell><TableCell className="text-xs">{b.batch_number}</TableCell><TableCell className="whitespace-nowrap text-xs">{fmtDate(b.expiry_date)}</TableCell>
              <TableCell className="text-right text-xs">{num(b.quantity_on_hand)}</TableCell><TableCell className="text-right"><Amount value={b.value} blankZero /></TableCell></TableRow>))}</TableBody></Table></>)}
      {x.actions?.length > 0 && (<><H>Decisions</H>
        <ul className="space-y-1 text-xs">{x.actions.map((a: Dict) => (
          <li key={a.id}><span className="text-muted-foreground">{new Date(a.created_at).toLocaleString("en-GB")}</span> · {a.action.replace(/_/g, " ")} by {a.created_by}
            {a.note ? ` — ${a.note}` : ""}{a.journal_id && <> · <J id={a.journal_id} n={a.journal_number ?? a.reference} /></>}</li>))}</ul></>)}
    </div>
  );
}
