import { useEffect, useMemo, useState } from "react";
import { currentCompany } from "@/components/books/BooksShell";
import { LedgerCoverageNote, SageLedgerTable } from "@/components/books/sage-ledger";
import { WhtPicker } from "@/components/books/wht";
import { useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { DrillLink, SageTag } from "@/components/books/kit";
import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { DetailSheet } from "@/components/workspace/DetailSheet";
import { FilterBar } from "@/components/workspace/FilterBar";
import { useDrill } from "@/components/books/drill-context";
import { BooksShell } from "@/components/books/BooksShell";
import { RecordView, RefundBody } from "@/components/books/lineage";
import {
  act, Amount, BankSelect, CsvButton, CustomerPick, DateRange, Empty, ErrorNote, JournalSheet, Loading, ProductPick,
  Section, StatusBadge, useBooks, useLines,
} from "@/components/books/kit";
import { books, BooksError, Dict, fmtDate, naira, newIdemKey, num, today, yearStart, monthStart } from "@/lib/books-api";
import { askText } from "@/lib/ask";

export default function BooksSales() {
  const [params, setParams] = useSearchParams();
  // The invoice register is the one invoice list (Sage's invoices and Roy Books' own); old ?tab=invoices links land on it.
  const [tab, setTab] = useState(params.get("tab") === "invoices" ? "register" : params.get("tab") ?? "register");
  const receiveFrom = (customerId: string) => { const p = new URLSearchParams(params); p.set("new", "receipt"); p.set("customer", customerId); setParams(p, { replace: true }); };
  const open = (k: string, v: string | null) => { const p = new URLSearchParams(params); v ? p.set(k, v) : p.delete(k); setParams(p, { replace: true }); };
  return (
    <BooksShell title="Receivables — Patients, HMOs & Corporates"
                actions={<>
                  <Button size="sm" variant="outline" onClick={() => open("new", "invoice")}><Plus className="mr-1 h-4 w-4" />Manual invoice</Button>
                  <Button size="sm" onClick={() => open("new", "receipt")}>Record receipt</Button>
                  <Button size="sm" variant="outline" onClick={() => open("new", "creditnote")}>Credit note</Button>
                  <Button size="sm" variant="outline" onClick={() => open("new", "refund")}>Refund</Button>
                </>}>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap">
          <TabsTrigger value="register">Invoice register</TabsTrigger>
          <TabsTrigger value="ledgers">Customer ledgers</TabsTrigger>
          <TabsTrigger value="receipts">Receipts</TabsTrigger>
          <TabsTrigger value="credit">Credit notes</TabsTrigger>
          <TabsTrigger value="refunds">Refunds</TabsTrigger>
          <TabsTrigger value="aging">Aged receivables</TabsTrigger>
          <TabsTrigger value="statement">Statement of account</TabsTrigger>
        </TabsList>
        <TabsContent value="register"><InvoiceRegister onOpen={(id) => open("invoice", id)} /></TabsContent>
        <TabsContent value="ledgers"><CustomerLedgers onReceive={receiveFrom} /></TabsContent>
        <TabsContent value="receipts"><ReceiptList onOpen={(id) => open("receipt", id)} /></TabsContent>
        <TabsContent value="credit"><CreditNoteList onOpen={(id) => open("creditnote", id)} /></TabsContent>
        <TabsContent value="refunds"><RefundList onOpen={(id) => open("refund", id)} /></TabsContent>
        <TabsContent value="aging"><AgedReceivables /><PayerAgingHistory /></TabsContent>
        <TabsContent value="statement"><CustomerStatement /></TabsContent>
      </Tabs>
      <InvoiceForm open={params.get("new") === "invoice"} onClose={(id) => { open("new", null); if (id) open("invoice", id); }} />
      <ReceiptForm open={params.get("new") === "receipt"} onClose={() => { const p = new URLSearchParams(params); p.delete("new"); p.delete("customer"); setParams(p, { replace: true }); }} />
      <CreditNoteForm open={params.get("new") === "creditnote"} onClose={() => open("new", null)} />
      <InvoiceDetail id={params.get("invoice")} onClose={() => open("invoice", null)} />
      <ReceiptDetail id={params.get("receipt")} onClose={() => open("receipt", null)} />
      <CreditNoteDetail id={params.get("creditnote")} onClose={() => open("creditnote", null)} />
      <RefundForm open={params.get("new") === "refund"} onClose={() => open("new", null)} />
      <DetailSheet size="wide" open={!!params.get("refund")} onOpenChange={(o) => !o && open("refund", null)} title="Refund">
        {params.get("refund") && <RefundBody id={params.get("refund")!} />}
      </DetailSheet>
    </BooksShell>
  );
}

// ---------------------------------------------------------------------------
// Lists
// ---------------------------------------------------------------------------

function InvoiceList({ onOpen }: { onOpen: (id: string) => void }) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [range, setRange] = useState({ from: yearStart(), to: today() });
  const { data, isLoading, error } = useBooks<any>(["invoices", search, status, range], "/sales/invoices",
    { search, status, from: range.from, to: range.to, limit: 300 });
  return (
    <Section title={`Invoices${data ? ` (${data.total})` : ""}`} actions={<CsvButton filename="invoices.csv" rows={data?.items} />}>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div className="flex-1"><FilterBar search={{ value: search, onChange: setSearch, placeholder: "Invoice / bill no., patient, HMO" }}
          selects={[{ label: "Status", value: status, onChange: setStatus, options: ["DRAFT", "POSTED", "PARTIALLY_PAID", "PAID", "VOID"].map((s) => ({ value: s, label: s.replace("_", " ").toLowerCase() })) }]} /></div>
        <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
      </div>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (data.items.length === 0 ? <Empty>No invoices in this period.</Empty> : (
        <Table>
          <TableHeader><TableRow><TableHead>Invoice</TableHead><TableHead>Date</TableHead><TableHead>Patient / payer</TableHead><TableHead>Due</TableHead><TableHead className="text-right">Total</TableHead><TableHead className="text-right">Balance</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
          <TableBody>
            {data.items.map((i: Dict) => (
              <TableRow key={i.id} className="cursor-pointer hover:bg-muted/50" onClick={() => onOpen(i.id)}>
                <TableCell className="font-mono text-xs">{i.invoice_number}{i.source_type === "BILLING" && <span className="ml-1 text-xs text-muted-foreground">bill</span>}{i.source_type === "BILLING_HMO" && <span className="ml-1 text-xs text-muted-foreground">HMO share</span>}{i.is_opening && <span className="ml-1 text-xs text-muted-foreground">opening</span>}</TableCell>
                <TableCell className="whitespace-nowrap">{fmtDate(i.invoice_date)}</TableCell>
                <TableCell className="max-w-[240px] truncate"><DrillLink to={{ type: "customer", id: String(i.customer_id ?? ""), label: i.customer_name }}>{i.customer_name}</DrillLink></TableCell>
                <TableCell className={i.due_date < today() && Number(i.balance_due) > 0 ? "text-red-600" : ""}>{fmtDate(i.due_date)}</TableCell>
                <TableCell className="text-right"><Amount value={i.total} /></TableCell>
                <TableCell className="text-right"><Amount value={i.balance_due} /></TableCell>
                <TableCell><StatusBadge status={i.status} /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ))}
    </Section>
  );
}

function ReceiptList({ onOpen }: { onOpen: (id: string) => void }) {
  const drill = useDrill();
  const [search, setSearch] = useState("");
  const [range, setRange] = useState({ from: yearStart(), to: today() });
  const { data, isLoading, error } = useBooks<any>(["receipts", search, range], "/receivables/receipts", { search, from: range.from, to: range.to, limit: 300 });
  return (
    <Section title={`Receipts${data ? ` (${data.total})` : ""}`} actions={<CsvButton filename="receipts.csv" rows={data?.items} />}>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div className="flex-1"><FilterBar search={{ value: search, onChange: setSearch, placeholder: "Receipt no., patient / payer, transfer ref" }} /></div>
        <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
      </div>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (data.items.length === 0 ? <Empty>No receipts in this period.</Empty> : (
        <Table>
          <TableHeader><TableRow><TableHead>Receipt</TableHead><TableHead>Date</TableHead><TableHead>From</TableHead><TableHead>Method</TableHead><TableHead>Into</TableHead><TableHead className="text-right">Amount</TableHead><TableHead className="text-right">Unapplied</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
          <TableBody>
            {data.items.map((r: Dict) => (
              <TableRow key={`${r.origin}-${r.id}`} className="cursor-pointer hover:bg-muted/50"
                        onClick={() => (r.origin === "SAGE" ? drill?.open({ type: "sagereceipt", id: String(r.id), label: r.receipt_number }) : onOpen(r.id))}>
                <TableCell className="font-mono text-xs">{r.receipt_number}{r.origin === "SAGE" && <SageTag />}</TableCell>
                <TableCell className="whitespace-nowrap">{fmtDate(r.receipt_date)}</TableCell>
                <TableCell className="max-w-[220px] truncate"><DrillLink to={{ type: "customer", id: String(r.customer_id ?? ""), label: r.customer_name }}>{r.customer_name}</DrillLink></TableCell>
                <TableCell className="text-xs">{r.method.toLowerCase()} {r.reference}</TableCell>
                <TableCell className="text-xs">{r.bank_account_name}</TableCell>
                <TableCell className="text-right"><Amount value={Number(r.amount) + Number(r.wht_amount)} /></TableCell>
                <TableCell className="text-right"><Amount value={r.unapplied} blankZero /></TableCell>
                <TableCell><StatusBadge status={r.status} /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ))}
    </Section>
  );
}

function CreditNoteList({ onOpen }: { onOpen: (id: string) => void }) {
  const { data, isLoading, error } = useBooks<any>(["creditnotes"], "/sales/credit-notes", { limit: 300 });
  return (
    <Section title="Credit notes (discounts, waivers, corrections, returns)" actions={<CsvButton filename="credit-notes.csv" rows={data?.items} />}>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (data.items.length === 0 ? <Empty>No credit notes yet.</Empty> : (
        <Table>
          <TableHeader><TableRow><TableHead>Number</TableHead><TableHead>Date</TableHead><TableHead>Patient / payer</TableHead><TableHead>Against</TableHead><TableHead>Reason</TableHead><TableHead className="text-right">Total</TableHead><TableHead>Stock back</TableHead></TableRow></TableHeader>
          <TableBody>
            {data.items.map((n: Dict) => (
              <TableRow key={n.id} className="cursor-pointer hover:bg-muted/50" onClick={() => onOpen(n.id)}>
                <TableCell className="font-mono text-xs">{n.credit_note_number}</TableCell>
                <TableCell className="whitespace-nowrap">{fmtDate(n.note_date)}</TableCell>
                <TableCell className="max-w-[200px] truncate"><DrillLink to={{ type: "customer", id: String(n.customer_id ?? ""), label: n.customer_name }}>{n.customer_name}</DrillLink></TableCell>
                <TableCell className="font-mono text-xs">{n.invoice_number ?? "—"}</TableCell>
                <TableCell className="max-w-[220px] truncate text-xs">{n.reason}</TableCell>
                <TableCell className="text-right"><Amount value={n.total} /></TableCell>
                <TableCell>{n.return_to_stock ? "yes" : ""}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ))}
    </Section>
  );
}

// ---------------------------------------------------------------------------
// Invoice form & detail
// ---------------------------------------------------------------------------

type Line = { line_type: string; product: Dict | null; description: string; quantity: string; unit_price: string; discount_amount: string; batch_number: string; expiry?: string };
const blankLine = (): Line => ({ line_type: "ITEM", product: null, description: "", quantity: "1", unit_price: "", discount_amount: "", batch_number: "" });

/** Debtor position shown while raising an invoice or receipt: exposure vs limit, terms, and any hospital
 *  bills not yet in the books (those post themselves - don't key them again). */
function CustomerPanel({ customer }: { customer: Dict | null }) {
  const { data: d } = useBooks<Dict>(["cust-overview", customer?.id], `/customers/${customer?.id}/overview`, undefined, !!customer);
  if (!customer || !d) return null;
  const c = d.customer;
  const limit = Number(c.credit_limit || 0);
  const used = limit ? Math.round((Number(d.exposure) / limit) * 100) : null;
  return (
    <div className="space-y-2 rounded-lg bg-muted/40 p-3 text-xs">
      <div className="flex flex-wrap gap-x-6 gap-y-1">
        <span>Owes <strong><Amount value={d.balance} /></strong></span>
        <span>Overdue <strong><Amount value={d.overdue} /></strong></span>
        <span>Credit limit <strong>{limit ? naira(limit) : "none"}</strong>{used != null && <span className={used > 90 ? " text-red-600" : used > 70 ? " text-amber-600" : ""}> · {used}% used</span>}</span>
        <span>Terms <strong>{c.payment_terms_days ? `${c.payment_terms_days} days` : "on receipt"}</strong></span>
      </div>
      {c.party_type === "PATIENT" && (
        <div className="flex items-start gap-1 text-sky-700 dark:text-sky-300"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>Patient services are billed at <strong>Billing & Cashier</strong> and reach the books by themselves. Use a manual invoice only for charges that never go through a hospital bill.</span></div>
      )}
      {d.bills_not_in_books?.length > 0 && (
        <div className="flex items-start gap-1 text-amber-700 dark:text-amber-300"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{d.bills_not_in_books.length} hospital bill(s) for this patient are not in the books yet ({d.bills_not_in_books.map((f: Dict) => f.bill_number).join(", ")}).
            They post automatically (or from Close & Controls) — don't raise them again here.</span></div>
      )}
    </div>
  );
}

function lineTotal(l: Line) {
  const gross = Number(l.quantity || 0) * Number(l.unit_price || 0);
  if (l.line_type === "DISCOUNT") return -Number(l.unit_price || 0);
  if (l.line_type === "CHARGE") return Number(l.unit_price || 0);
  return gross - lineDiscount(l);
}

/** A line discount typed as an amount or as a rate ("10%"). */
function lineDiscount(l: Line) {
  const d = String(l.discount_amount || "").trim();
  const gross = Number(l.quantity || 0) * Number(l.unit_price || 0);
  return d.endsWith("%") ? Math.round(gross * Number(d.slice(0, -1))) / 100 : Number(d || 0);
}

function InvoiceForm({ open, onClose }: { open: boolean; onClose: (createdId?: string) => void }) {
  const qc = useQueryClient();
  const [customer, setCustomer] = useState<Dict | null>(null);
  const [date, setDate] = useState(today());
  const [reference, setReference] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [credit, setCredit] = useState<Dict | null>(null);
  const [override, setOverride] = useState("");
  const [idem] = useState(newIdemKey);
  const L = useLines<Line>(blankLine);
  const total = L.lines.reduce((s, l) => s + lineTotal(l), 0);
  useEffect(() => { if (!open) { setCustomer(null); L.reset(); setCredit(null); setOverride(""); setReference(""); setNotes(""); } }, [open]);

  const payload = (post: boolean) => ({
    customer_id: customer?.id, invoice_date: date, reference, notes, post,
    override_credit: !!override, override_reason: override || undefined,
    lines: L.lines.filter((l) => l.line_type !== "ITEM" || l.product).map((l) => ({
      line_type: l.line_type, sku: l.product?.sku, description: l.description || undefined,
      quantity: l.line_type === "CHARGE" || l.line_type === "DISCOUNT" ? 1 : l.quantity,
      unit_price: l.unit_price || 0, discount_amount: lineDiscount(l) || 0, batch_number: l.batch_number || undefined,
    })),
  });
  const submit = async (post: boolean) => {
    if (!customer) return;
    setBusy(true);
    try {
      const inv = await books.post("/sales/invoices", payload(post), idem + (post ? "p" : "d"));
      qc.invalidateQueries({ queryKey: ["books"] });
      onClose(inv.id);
    } catch (e) {
      const err = e as BooksError;
      if (err.code === "CREDIT_LIMIT_EXCEEDED") setCredit(err.details ?? {});
      else act(async () => { throw e; });
    } finally {
      setBusy(false);
    }
  };
  return (
    <DetailSheet size="wide" open={open} onOpenChange={(o) => !o && onClose()} title="New sales invoice"
                 description="Posting records AR, revenue, discounts, delivery income, cost of sales and stock in one step."
                 footer={<div className="flex w-full items-center justify-between gap-2">
                   <span className="text-sm">Total <strong>{naira(total)}</strong></span>
                   <div className="flex gap-2">
                     <Button variant="outline" disabled={busy || !customer} onClick={() => submit(false)}>Save draft</Button>
                     <Button disabled={busy || !customer || total <= 0} onClick={() => submit(true)}>{busy ? "Posting…" : "Post invoice"}</Button>
                   </div>
                 </div>}>
      <div className="space-y-3">
        <CustomerPick value={customer} onChange={setCustomer} />
        <CustomerPanel customer={customer} />
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1"><Label className="text-xs">Invoice date</Label><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></div>
          <div className="space-y-1"><Label className="text-xs">Reference (e.g. HMO authorisation, company PO)</Label><Input value={reference} onChange={(e) => setReference(e.target.value)} /></div>
        </div>
        <div className="space-y-2">
          {L.lines.map((l, i) => (
            <div key={i} className="space-y-2 rounded-lg border p-2">
              <div className="flex items-center gap-2">
                <select className="h-8 rounded-md border bg-background px-2 text-xs" value={l.line_type} onChange={(e) => L.update(i, { line_type: e.target.value })}>
                  <option value="ITEM">Stock item</option><option value="SERVICE">Service</option><option value="CHARGE">Delivery / charge</option><option value="DISCOUNT">Invoice discount</option>
                </select>
                <div className="flex-1">{l.line_type === "ITEM"
                  ? <ProductPick value={l.product} customerId={customer?.id}
                                 onChange={(p) => L.update(i, { product: p, unit_price: p?.suggested_price ? String(p.suggested_price) : l.unit_price,
                                                                batch_number: p?.next_batch ?? "", expiry: p?.next_expiry ?? undefined })} />
                  : <Input className="h-8" placeholder={l.line_type === "CHARGE" ? "e.g. Delivery charge" : "Description"} value={l.description} onChange={(e) => L.update(i, { description: e.target.value })} />}</div>
                <Button size="icon" variant="ghost" onClick={() => L.remove(i)}><Trash2 className="h-4 w-4" /></Button>
              </div>
              <div className="grid grid-cols-4 gap-2">
                {(l.line_type === "ITEM" || l.line_type === "SERVICE") && <Input className="h-8" type="number" placeholder="Qty" value={l.quantity} onChange={(e) => L.update(i, { quantity: e.target.value })} />}
                <Input className="h-8" type="number" placeholder={l.line_type === "DISCOUNT" || l.line_type === "CHARGE" ? "Amount" : "Unit price"} value={l.unit_price} onChange={(e) => L.update(i, { unit_price: e.target.value })} />
                {(l.line_type === "ITEM" || l.line_type === "SERVICE") && <Input className="h-8" placeholder="Discount ₦ or %" title="Type an amount, or a rate like 10% - it is worked out on quantity × price"
                  value={l.discount_amount} onChange={(e) => L.update(i, { discount_amount: e.target.value })}
                  onBlur={(e) => { const v = e.target.value.trim(); if (v.endsWith("%")) L.update(i, { discount_amount: (Math.round(Number(l.quantity || 0) * Number(l.unit_price || 0) * Number(v.slice(0, -1))) / 100).toFixed(2) }); }} />}
                {l.line_type === "ITEM" && <Input className="h-8" placeholder="Batch (optional)" value={l.batch_number} onChange={(e) => L.update(i, { batch_number: e.target.value })} />}
              </div>
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>{l.product ? `on hand ${num(l.product.on_hand)}${l.batch_number ? ` · batch ${l.batch_number}` : ""}${l.expiry ? ` · exp ${fmtDate(l.expiry)}` : ""}${Number(l.quantity) > Number(l.product.on_hand) ? " · more than in stock" : ""}` : ""}</span>
                <span>Line {naira(lineTotal(l))}</span></div>
            </div>
          ))}
          <Button size="sm" variant="outline" onClick={L.add}><Plus className="mr-1 h-4 w-4" />Add line</Button>
        </div>
        <div className="space-y-1"><Label className="text-xs">Notes</Label><Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
        {credit && (
          <div className="space-y-2 rounded-lg border border-amber-400 bg-amber-50 p-3 text-sm dark:bg-amber-500/10">
            <div className="flex items-center gap-2 font-medium text-amber-800 dark:text-amber-300"><AlertTriangle className="h-4 w-4" />Credit limit would be exceeded by {naira(credit.excess)}</div>
            <div className="text-xs">Limit {naira(credit.credit_limit)} · owing now {naira(credit.current_exposure)} · after this invoice {naira(credit.projected_exposure)}</div>
            <Input placeholder="Reason to continue (recorded for audit)" value={override} onChange={(e) => setOverride(e.target.value)} />
            <p className="text-xs text-muted-foreground">Enter a reason and post again to continue, or cancel.</p>
          </div>
        )}
      </div>
    </DetailSheet>
  );
}

function InvoiceDetail({ id, onClose }: { id: string | null; onClose: () => void }) {
  const qc = useQueryClient();
  const { data: inv, refetch } = useBooks<Dict>(["invoice", id], `/sales/invoices/${id}`, undefined, !!id);
  const [override, setOverride] = useState("");
  const [v, setV] = useState(0);
  const refresh = () => { refetch(); setV((x) => x + 1); qc.invalidateQueries({ queryKey: ["books"] }); };
  const post = async () => {
    try {
      await books.post(`/sales/invoices/${id}/post`, override ? { override_credit: true, override_reason: override } : {});
      refresh();
    } catch (e) {
      const err = e as BooksError;
      if (err.code === "CREDIT_LIMIT_EXCEEDED") act(async () => { throw new Error(`${err.message}. Enter a reason below and post again.`); });
      else act(async () => { throw e; });
    }
  };
  const voidIt = async () => {
    const reason = await askText("Why is this invoice being voided? (stock and all postings will be reversed)");
    if (reason && (await act(() => books.post(`/sales/invoices/${id}/void`, { reason }), "Invoice voided"))) refresh();
  };
  const canVoid = inv && ["DRAFT", "POSTED"].includes(inv.status) && !inv.is_opening && Number(inv.amount_settled) === 0;
  return (
    <DetailSheet size="wide" open={!!id} onOpenChange={(o) => !o && onClose()} title={inv ? `Invoice ${inv.invoice_number}` : "Invoice"} description={inv?.customer_name}
                 footer={inv && (inv.status === "DRAFT" || canVoid) ? (
                   <div className="flex w-full flex-wrap items-center justify-end gap-2">
                     {inv.status === "DRAFT" && (<><Input className="h-9 w-64" placeholder="Credit override reason (if needed)" value={override} onChange={(e) => setOverride(e.target.value)} />
                       <Button size="sm" onClick={post}>Post invoice</Button></>)}
                     {canVoid && <Button size="sm" variant="destructive" onClick={voidIt}>Void</Button>}
                   </div>) : undefined}>
      {id && <RecordView key={`${id}:${v}`} t={{ type: "invoice", id }} />}
    </DetailSheet>
  );
}

function Row({ k, v, bold }: { k: string; v: any; bold?: boolean }) {
  return <div className={`flex justify-between ${bold ? "font-semibold" : ""}`}><span className="text-muted-foreground">{k}</span><Amount value={v} /></div>;
}

// ---------------------------------------------------------------------------
// Receipts
// ---------------------------------------------------------------------------

function ReceiptForm({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [customer, setCustomer] = useState<Dict | null>(null);
  const [f, setF] = useState({ receipt_date: today(), method: "TRANSFER", bank_account_id: "", amount: "", wht_amount: "", reference: "", notes: "" });
  const [alloc, setAlloc] = useState<Record<string, string>>({});
  const [dupe, setDupe] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [idem] = useState(newIdemKey);
  useEffect(() => { if (!open) { setCustomer(null); setAlloc({}); setDupe(null); setF({ ...f, amount: "", wht_amount: "", reference: "", notes: "" }); } }, [open]);
  const [sp] = useSearchParams();
  const preId = open ? sp.get("customer") : null;
  const { data: pre } = useBooks<Dict>(["receipt-customer", preId], `/customers/${preId}/overview`, undefined, !!preId && !customer);
  useEffect(() => { if (pre?.customer && !customer) setCustomer(pre.customer); }, [pre]);
  const { data: items } = useBooks<Dict[]>(["openitems", customer?.id], "/receivables/open-items", { customer_id: customer?.id }, !!customer);
  const invoices = useMemo(() => (items ?? []).filter((i) => i.doc_type === "INVOICE" && Number(i.open_amount) > 0).sort((a, b) => (a.due_date < b.due_date ? -1 : 1)), [items]);
  const available = Number(f.amount || 0) + Number(f.wht_amount || 0);
  const allocated = Object.values(alloc).reduce((s, v) => s + Number(v || 0), 0);
  // The amount follows what is being settled: ticking invoices fills it, and WHT the customer deducted comes off it.
  useEffect(() => {
    const w = Number(f.wht_amount || 0);
    if (allocated > 0 && (w > 0 || !f.amount)) setF((x) => ({ ...x, amount: (allocated - w).toFixed(2) }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allocated, f.wht_amount]);
  const autoAllocate = () => {
    let left = available;
    const next: Record<string, string> = {};
    for (const i of invoices) { if (left <= 0) break; const take = Math.min(left, Number(i.open_amount)); next[i.doc_id] = take.toFixed(2); left -= take; }
    setAlloc(next);
  };
  const submit = async (confirmDuplicate = false) => {
    setBusy(true);
    try {
      await books.post("/receivables/receipts", {
        ...f, customer_id: customer?.id, confirm_duplicate: confirmDuplicate,
        allocations: Object.entries(alloc).filter(([, v]) => Number(v) > 0).map(([invoice_id, amount]) => ({ invoice_id, amount })),
      }, idem + (confirmDuplicate ? "c" : ""));
      qc.invalidateQueries({ queryKey: ["books"] });
      onClose();
    } catch (e) {
      const err = e as BooksError;
      if (err.code === "DUPLICATE_REFERENCE") setDupe(err.message);
      else act(async () => { throw e; });
    } finally { setBusy(false); }
  };
  return (
    <DetailSheet size="wide" open={open} onOpenChange={(o) => !o && onClose()} title="Record receipt"
                 description="Money in from a patient, an HMO remittance or a company. Anything not applied stays on their account (e.g. a deposit)."
                 footer={<div className="flex w-full items-center justify-between"><span className="text-xs">Applied {naira(allocated)} of {naira(available)}{available - allocated > 0 ? ` · ${naira(available - allocated)} on account` : ""}</span>
                   <Button disabled={busy || !customer || !f.bank_account_id || Number(f.amount) <= 0 || allocated > available + 0.001} onClick={() => submit(false)}>{busy ? "Posting…" : "Post receipt"}</Button></div>}>
      <div className="space-y-3">
        <CustomerPick value={customer} onChange={(c) => { setCustomer(c); setAlloc({}); }} />
        <CustomerPanel customer={customer} />
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1"><Label className="text-xs">Date</Label><Input type="date" value={f.receipt_date} onChange={(e) => setF({ ...f, receipt_date: e.target.value })} /></div>
          <div className="space-y-1"><Label className="text-xs">Method</Label>
            <select className="h-9 w-full rounded-md border bg-background px-2 text-sm" value={f.method} onChange={(e) => setF({ ...f, method: e.target.value })}>
              {["TRANSFER", "CHEQUE", "CASH", "POS", "OTHER"].map((m) => <option key={m} value={m}>{m.toLowerCase()}</option>)}
            </select></div>
        </div>
        <BankSelect value={f.bank_account_id} onChange={(v) => setF({ ...f, bank_account_id: v })} label="Received into" />
        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1"><Label className="text-xs">Amount received</Label><Input type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></div>
          <WhtPicker label="WHT deducted by the customer" gross={allocated} value={f.wht_amount} onChange={(v) => setF((x) => ({ ...x, wht_amount: v }))} />
          <div className="space-y-1"><Label className="text-xs">Cheque / transfer ref</Label><Input value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} /></div>
        </div>
        {dupe && (
          <div className="space-y-2 rounded-lg border border-amber-400 bg-amber-50 p-3 text-sm dark:bg-amber-500/10">
            <div className="flex items-center gap-2 font-medium text-amber-800 dark:text-amber-300"><AlertTriangle className="h-4 w-4" />Possible duplicate: {dupe}</div>
            <div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => setDupe(null)}>Fix the reference</Button><Button size="sm" onClick={() => submit(true)}>It is genuine — post anyway</Button></div>
          </div>
        )}
        {customer && (
          <div className="space-y-2">
            <div className="flex items-center justify-between"><Label className="text-xs">Apply to invoices (oldest due first)</Label><Button size="sm" variant="outline" onClick={autoAllocate} disabled={!available}>Auto-apply</Button></div>
            {invoices.length === 0 ? <Empty>No open invoices — the receipt will sit on their account as a deposit / credit.</Empty> : (
              <Table>
                <TableHeader><TableRow><TableHead>Invoice</TableHead><TableHead>Due</TableHead><TableHead className="text-right">Open</TableHead><TableHead className="w-32">Apply</TableHead></TableRow></TableHeader>
                <TableBody>
                  {invoices.map((i) => (
                    <TableRow key={i.doc_id}>
                      <TableCell className="font-mono text-xs">{i.doc_number}</TableCell>
                      <TableCell className="text-xs">{fmtDate(i.due_date)}</TableCell>
                      <TableCell className="text-right"><Amount value={i.open_amount} /></TableCell>
                      <TableCell><Input className="h-8" type="number" value={alloc[i.doc_id] ?? ""} onChange={(e) => setAlloc({ ...alloc, [i.doc_id]: e.target.value })} /></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        )}
        <div className="space-y-1"><Label className="text-xs">Notes</Label><Textarea rows={2} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></div>
      </div>
    </DetailSheet>
  );
}

function ReceiptDetail({ id, onClose }: { id: string | null; onClose: () => void }) {
  const qc = useQueryClient();
  const { data: r, refetch } = useBooks<Dict>(["receipt", id], `/receivables/receipts/${id}`, undefined, !!id);
  const [v, setV] = useState(0);
  const voidIt = async () => {
    const reason = await askText("Why is this receipt being voided? (e.g. cheque bounced)");
    if (reason && (await act(() => books.post(`/receivables/receipts/${id}/void`, { reason }), "Receipt voided"))) { refetch(); setV((x) => x + 1); qc.invalidateQueries({ queryKey: ["books"] }); }
  };
  return (
    <DetailSheet size="wide" open={!!id} onOpenChange={(o) => !o && onClose()} title={r ? `Receipt ${r.receipt_number}` : "Receipt"} description={r?.customer_name}
                 footer={r?.status === "POSTED" ? <Button size="sm" variant="destructive" onClick={voidIt}>Void receipt</Button> : undefined}>
      {id && <RecordView key={`${id}:${v}`} t={{ type: "receipt", id }} />}
    </DetailSheet>
  );
}

// ---------------------------------------------------------------------------
// Credit notes
// ---------------------------------------------------------------------------

function CreditNoteForm({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [customer, setCustomer] = useState<Dict | null>(null);
  const [invoiceId, setInvoiceId] = useState("");
  const [reason, setReason] = useState("");
  const [date, setDate] = useState(today());
  const [toStock, setToStock] = useState(true);
  const [busy, setBusy] = useState(false);
  const L = useLines<Line>(blankLine);
  const { data: invs } = useBooks<any>(["cn-invoices", customer?.id], "/sales/invoices", { customer_id: customer?.id, limit: 100 }, !!customer);
  useEffect(() => { if (!open) { setCustomer(null); setInvoiceId(""); setReason(""); L.reset(); } }, [open]);
  const total = L.lines.reduce((s, l) => s + lineTotal(l), 0);
  const submit = async () => {
    setBusy(true);
    const ok = await act(() => books.post("/sales/credit-notes", {
      customer_id: customer?.id, invoice_id: invoiceId || undefined, note_date: date, reason, return_to_stock: toStock,
      lines: L.lines.filter((l) => l.line_type !== "ITEM" || l.product).map((l) => ({ line_type: l.line_type, sku: l.product?.sku, description: l.description || undefined,
        quantity: l.line_type === "ITEM" || l.line_type === "SERVICE" ? l.quantity : 1, unit_price: l.unit_price || 0, batch_number: l.batch_number || undefined })),
    }), "Credit note posted");
    setBusy(false);
    if (ok) { qc.invalidateQueries({ queryKey: ["books"] }); onClose(); }
  };
  return (
    <DetailSheet size="wide" open={open} onOpenChange={(o) => !o && onClose()} title="Credit note / return inward"
                 description="Reduces what the patient / payer owes (e.g. an HMO disallowance agreed with Finance); returned items come back into stock at the cost they left with."
                 footer={<div className="flex w-full items-center justify-between"><span className="text-sm">Total <strong>{naira(total)}</strong></span>
                   <Button disabled={busy || !customer || !reason || total <= 0} onClick={submit}>{busy ? "Posting…" : "Post credit note"}</Button></div>}>
      <div className="space-y-3">
        <CustomerPick value={customer} onChange={setCustomer} />
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1"><Label className="text-xs">Against invoice (optional)</Label>
            <select className="h-9 w-full rounded-md border bg-background px-2 text-sm" value={invoiceId} onChange={(e) => setInvoiceId(e.target.value)}>
              <option value="">— none —</option>
              {(invs?.items ?? []).filter((i: Dict) => i.status !== "VOID").map((i: Dict) => <option key={i.id} value={i.id}>{i.invoice_number} · {naira(i.balance_due)} open</option>)}
            </select></div>
          <div className="space-y-1"><Label className="text-xs">Date</Label><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></div>
        </div>
        <div className="space-y-1"><Label className="text-xs">Reason</Label><Input placeholder="e.g. HMO disallowed part of the claim" value={reason} onChange={(e) => setReason(e.target.value)} /></div>
        <div className="flex items-center gap-2"><Switch checked={toStock} onCheckedChange={setToStock} /><span className="text-sm">Goods returned to stock</span></div>
        {L.lines.map((l, i) => (
          <div key={i} className="grid grid-cols-[1fr_80px_110px_110px_32px] items-end gap-2">
            <ProductPick label={i === 0 ? "Product" : undefined} value={l.product} onChange={(p) => L.update(i, { product: p })} />
            <Input className="h-9" type="number" placeholder="Qty" value={l.quantity} onChange={(e) => L.update(i, { quantity: e.target.value })} />
            <Input className="h-9" type="number" placeholder="Unit price" value={l.unit_price} onChange={(e) => L.update(i, { unit_price: e.target.value })} />
            <Input className="h-9" placeholder="Batch" value={l.batch_number} onChange={(e) => L.update(i, { batch_number: e.target.value })} />
            <Button size="icon" variant="ghost" onClick={() => L.remove(i)}><Trash2 className="h-4 w-4" /></Button>
          </div>
        ))}
        <Button size="sm" variant="outline" onClick={L.add}><Plus className="mr-1 h-4 w-4" />Add line</Button>
      </div>
    </DetailSheet>
  );
}

function CreditNoteDetail({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { data: n } = useBooks<Dict>(["creditnote", id], `/sales/credit-notes/${id}`, undefined, !!id);
  return (
    <DetailSheet size="wide" open={!!id} onOpenChange={(o) => !o && onClose()} title={n ? `Credit note ${n.credit_note_number}` : "Credit note"} description={n?.customer_name}>
      {id && <RecordView t={{ type: "creditnote", id }} />}
    </DetailSheet>
  );
}

// ---------------------------------------------------------------------------
// Aged receivables & statement
// ---------------------------------------------------------------------------

function AgedReceivables() {
  const [asOf, setAsOf] = useState(today());
  const [basis, setBasis] = useState("due_date");
  const [party, setParty] = useState("");
  const [open, setOpen] = useState<Dict | null>(null);
  const { data, isLoading, error } = useBooks<any>(["aged-ar", asOf, basis, party], "/reports/aged-receivables", { as_of: asOf, basis, party_type: party || undefined });
  return (
    <Section title="Aged receivables" actions={<CsvButton filename={`aged-receivables-${asOf}.csv`} rows={data?.rows.map((r: Dict) => ({ debtor: r.customer_name, type: r.party_type, code: r.customer_code, ...Object.fromEntries(data.buckets.map((b: string, i: number) => [b, r.buckets[i]])), total: r.total }))} />}>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <DateRange single to={asOf} onChange={(_, t) => setAsOf(t)} />
        <div className="space-y-1"><Label className="text-xs">Age by</Label><select className="h-9 rounded-md border bg-background px-2 text-sm" value={basis} onChange={(e) => setBasis(e.target.value)}><option value="due_date">Due date (as Sage)</option><option value="invoice_date">Invoice date</option></select></div>
        <div className="space-y-1"><Label className="text-xs">Who owes</Label><select className="h-9 rounded-md border bg-background px-2 text-sm" value={party} onChange={(e) => setParty(e.target.value)}>
          <option value="">Everyone</option><option value="HMO">HMOs & insurers</option><option value="PATIENT">Patients</option><option value="CORPORATE">Corporates</option><option value="OTHER">Other</option></select></div>
      </div>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (
        <Table>
          <TableHeader><TableRow><TableHead>Patient / payer</TableHead>{data.buckets.map((b: string) => <TableHead key={b} className="text-right">{b}</TableHead>)}<TableHead className="text-right">Total</TableHead><TableHead className="text-right">Limit</TableHead></TableRow></TableHeader>
          <TableBody>
            {data.rows.map((r: Dict) => (
              <TableRow key={r.customer_id} className="cursor-pointer hover:bg-muted/50" onClick={() => setOpen(r)}>
                <TableCell className="max-w-[240px] truncate"><DrillLink to={{ type: "customer", id: String(r.customer_id ?? ""), label: r.customer_name }}>{r.customer_name}</DrillLink></TableCell>
                {r.buckets.map((v: string, i: number) => <TableCell key={i} className="text-right"><Amount value={v} blankZero /></TableCell>)}
                <TableCell className="text-right font-semibold"><Amount value={r.total} /></TableCell>
                <TableCell className={`text-right text-xs ${r.credit_limit && Number(r.total) > Number(r.credit_limit) ? "text-red-600" : "text-muted-foreground"}`}>{r.credit_limit ? naira(r.credit_limit) : ""}</TableCell>
              </TableRow>
            ))}
            <TableRow className="font-semibold"><TableCell>Total</TableCell>{data.bucket_totals.map((v: string, i: number) => <TableCell key={i} className="text-right"><Amount value={v} /></TableCell>)}<TableCell className="text-right"><Amount value={data.total} /></TableCell><TableCell /></TableRow>
          </TableBody>
        </Table>
      )}
      <DetailSheet size="wide" open={!!open} onOpenChange={(o) => !o && setOpen(null)} title={open?.customer_name ?? ""} description="Open items making up this balance">
        {open && (
          <Table>
            <TableHeader><TableRow><TableHead>Document</TableHead><TableHead>Due</TableHead><TableHead>Bucket</TableHead><TableHead className="text-right">Open</TableHead></TableRow></TableHeader>
            <TableBody>{open.items.map((it: Dict, i: number) => (
              <TableRow key={i}><TableCell className="font-mono text-xs">{it.doc_number}<div className="text-xs text-muted-foreground">{it.doc_type.replace("_", " ").toLowerCase()}</div></TableCell><TableCell className="text-xs">{fmtDate(it.due_date)}</TableCell><TableCell className="text-xs">{it.bucket}</TableCell><TableCell className="text-right"><Amount value={it.open_amount} /></TableCell></TableRow>
            ))}</TableBody>
          </Table>
        )}
      </DetailSheet>
    </Section>
  );
}

function CustomerStatement() {
  const [customer, setCustomer] = useState<Dict | null>(null);
  const [sp] = useSearchParams();
  const preId = sp.get("customer");
  const { data: pre } = useBooks<Dict>(["statement-customer", preId], `/customers/${preId}/overview`, undefined, !!preId && !customer);
  useEffect(() => { if (pre?.customer && !customer) setCustomer(pre.customer); }, [pre]);
  const [range, setRange] = useState({ from: yearStart(), to: today() });
  const { data, isLoading, error } = useBooks<any>(["statement", customer?.id, range], `/reports/customer-statement/${customer?.id}`, range, !!customer);
  return (
    <Section title="Statement of account" actions={<>
      <CsvButton filename={`statement-${customer?.name ?? ""}.csv`} rows={data?.rows} />
      <Button size="sm" variant="outline" disabled={!data} onClick={() => window.print()}>Print</Button></>}>
      <div className="mb-3 grid gap-3 md:grid-cols-[1fr_auto]">
        <CustomerPick value={customer} onChange={setCustomer} />
        <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
      </div>
      {!customer && <Empty>Choose a patient, HMO or company to see their statement of account.</Empty>}
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (
        <div className="space-y-3 text-sm">
          <div className="flex justify-between"><span>Balance brought forward {fmtDate(range.from)}</span><Amount value={data.opening_balance} bold /></div>
          <Table>
            <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Document</TableHead><TableHead>Details</TableHead><TableHead className="text-right">Debit</TableHead><TableHead className="text-right">Credit</TableHead><TableHead className="text-right">Balance</TableHead></TableRow></TableHeader>
            <TableBody>{data.rows.map((r: Dict, i: number) => (
              <TableRow key={i}><TableCell className="whitespace-nowrap">{fmtDate(r.date)}</TableCell><TableCell className="font-mono text-xs">{r.number}</TableCell><TableCell className="text-xs">{r.type}{r.is_opening ? " (opening)" : ""}</TableCell>
                <TableCell className="text-right"><Amount value={r.debit} blankZero /></TableCell><TableCell className="text-right"><Amount value={r.credit} blankZero /></TableCell><TableCell className="text-right"><Amount value={r.balance} /></TableCell></TableRow>
            ))}</TableBody>
          </Table>
          <div className="flex justify-between font-semibold"><span>Balance due {fmtDate(range.to)}</span><Amount value={data.closing_balance} /></div>
          <div className="grid grid-cols-5 gap-2 text-xs">{data.aging.buckets.map((b: string, i: number) => <div key={b} className="rounded border p-2"><div className="text-muted-foreground">{b} days</div><Amount value={data.aging.amounts[i]} /></div>)}</div>
        </div>
      )}
    </Section>
  );
}

// ---------------------------------------------------------------------------
// Refunds (money paid back out of a patient's / payer's credit)
// ---------------------------------------------------------------------------

function RefundList({ onOpen }: { onOpen: (id: string) => void }) {
  const { data, isLoading, error } = useBooks<any>(["refunds"], "/receivables/refunds", { limit: 300 });
  return (
    <Section title="Refunds" actions={<CsvButton filename="refunds.csv" rows={data?.items} />}>
      <p className="mb-3 text-sm text-muted-foreground">Refunds recorded with the correction pen at Billing post here by themselves. Record one here only for money paid back outside a bill.</p>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (data.items.length === 0 ? <Empty>No refunds yet.</Empty> : (
        <Table>
          <TableHeader><TableRow><TableHead>Number</TableHead><TableHead>Date</TableHead><TableHead>Paid to</TableHead><TableHead>From</TableHead><TableHead>Reason</TableHead><TableHead className="text-right">Amount</TableHead></TableRow></TableHeader>
          <TableBody>{data.items.map((r: Dict) => (
            <TableRow key={r.id} className="cursor-pointer hover:bg-muted/50" onClick={() => onOpen(r.id)}>
              <TableCell className="font-mono text-xs">{r.refund_number}</TableCell><TableCell className="whitespace-nowrap">{fmtDate(r.refund_date)}</TableCell>
              <TableCell className="max-w-[200px] truncate"><DrillLink to={{ type: "customer", id: String(r.customer_id ?? ""), label: r.customer_name }}>{r.customer_name}</DrillLink></TableCell>
              <TableCell className="text-xs">{r.bank_account_name}</TableCell><TableCell className="max-w-[240px] truncate text-xs">{r.reason}</TableCell>
              <TableCell className="text-right"><Amount value={r.amount} /></TableCell></TableRow>))}</TableBody>
        </Table>
      ))}
    </Section>
  );
}

function RefundForm({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [customer, setCustomer] = useState<Dict | null>(null);
  const [credit, setCredit] = useState("");
  const [f, setF] = useState({ amount: "", reason: "", bank_account_id: "", refund_date: today() });
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!open) { setCustomer(null); setCredit(""); setF({ amount: "", reason: "", bank_account_id: "", refund_date: today() }); } }, [open]);
  const { data: items } = useBooks<Dict[]>(["openitems-refund", customer?.id], "/receivables/open-items", { customer_id: customer?.id }, !!customer);
  const credits = (items ?? []).filter((i) => Number(i.open_amount) < 0 && (i.doc_type === "RECEIPT" || i.doc_type === "CREDIT_NOTE"));
  const chosen = credits.find((c) => `${c.doc_type}:${c.doc_id}` === credit);
  const submit = async () => {
    if (!chosen) return;
    setBusy(true);
    const r = await act(() => books.post("/receivables/refunds", { customer_id: customer?.id, credit_type: chosen.doc_type, credit_id: chosen.doc_id, ...f }, newIdemKey()), "Refund posted");
    setBusy(false);
    if (r) { qc.invalidateQueries({ queryKey: ["books"] }); onClose(); }
  };
  return (
    <DetailSheet size="wide" open={open} onOpenChange={(o) => !o && onClose()} title="Refund" description="Pay money back out of a patient's or payer's unapplied credit (an overpayment, or a credit note)."
                 footer={<Button disabled={busy || !chosen || !f.bank_account_id || !f.reason || Number(f.amount) <= 0 || Number(f.amount) > -Number(chosen?.open_amount ?? 0)} onClick={submit}>{busy ? "Posting…" : "Post refund"}</Button>}>
      <div className="space-y-4">
        <CustomerPick value={customer} onChange={(c) => { setCustomer(c); setCredit(""); }} />
        {customer && (credits.length === 0 ? <Empty>No unapplied credit to refund.</Empty> : (
          <div className="space-y-1"><Label className="text-xs">Refund out of</Label>
            <select className="h-9 w-full rounded-md border bg-background px-2 text-sm" value={credit} onChange={(e) => { setCredit(e.target.value); const c = credits.find((x) => `${x.doc_type}:${x.doc_id}` === e.target.value); if (c) setF({ ...f, amount: String(-Number(c.open_amount)) }); }}>
              <option value="">Choose…</option>
              {credits.map((c) => <option key={`${c.doc_type}:${c.doc_id}`} value={`${c.doc_type}:${c.doc_id}`}>{c.doc_number} · {c.doc_type.replace("_", " ").toLowerCase()} · {naira(-Number(c.open_amount))} available</option>)}
            </select></div>))}
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1"><Label className="text-xs">Amount</Label><Input type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></div>
          <div className="space-y-1"><Label className="text-xs">Date</Label><Input type="date" value={f.refund_date} onChange={(e) => setF({ ...f, refund_date: e.target.value })} /></div>
        </div>
        <BankSelect value={f.bank_account_id} onChange={(v) => setF({ ...f, bank_account_id: v })} label="Paid from" />
        <div className="space-y-1"><Label className="text-xs">Reason</Label><Input placeholder="e.g. Blood not used, overpayment" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></div>
      </div>
    </DetailSheet>
  );
}


const REG_STATUS: Record<string, string> = { open: "Open", paid: "Paid", credit: "Credit memos", void: "Void", draft: "Draft" };

/** Every invoice ever raised - Sage's (2010 to its last export) and Roy Books' own (hospital bills posted to the books,
 *  HMO shares, invoices raised here, drafts and voids) - newest first. The strip answers the morning question: the last
 *  invoice raised and the next number. Each row opens the right record. */
function InvoiceRegister({ onOpen }: { onOpen: (id: string) => void }) {
  const drill = useDrill();
  const [params] = useSearchParams();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState(params.get("status") ?? "");
  const [range, setRange] = useState({ from: monthStart(), to: today() });
  const { data, isLoading, error } = useBooks<any>(["invoice-register", search, status, range], "/sales/invoice-register",
    { search: search || undefined, status: status || undefined, from: range.from, to: range.to, limit: 1000 });
  const last = data?.last_invoice;
  return (
    <Section title={`Invoice register${data ? ` (${data.total})` : ""}`} actions={<CsvButton filename={`invoice-register-${range.from}-${range.to}.csv`} rows={data?.items} />}>
      {data && (
        <div className="mb-3 flex flex-wrap items-center gap-x-6 gap-y-1 rounded-lg border bg-muted/40 p-3 text-sm">
          <span>Last invoice raised: {last ? <><strong className="font-mono">{last.number}</strong> on {fmtDate(last.date)} · {last.customer}{last.source === "sage" ? " (in Sage)" : ""}</> : "none yet"}</span>
          <span>Next invoice: <strong className="font-mono">{data.next_invoice_number}</strong> <span className="text-xs text-muted-foreground">(numbered automatically; hospital bills keep their bill numbers)</span></span>
          <span className="ml-auto">Invoiced <Amount value={data.invoiced} /> · still open <Amount value={data.still_open} /> ({data.open_count})</span>
        </div>
      )}
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div className="flex-1"><FilterBar search={{ value: search, onChange: setSearch, placeholder: "Invoice no., patient / payer" }}
          selects={[{ label: "Status", value: status, onChange: setStatus, options: Object.entries(REG_STATUS).map(([value, label]) => ({ value, label })) }]} /></div>
        <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
      </div>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (data.items.length === 0 ? <Empty>No invoices in this period.</Empty> : (
        <Table>
          <TableHeader><TableRow><TableHead>Invoice</TableHead><TableHead>Date</TableHead><TableHead>Patient / payer</TableHead><TableHead className="text-right">Amount</TableHead>
            <TableHead className="text-right">Paid / credited</TableHead><TableHead className="text-right">Balance</TableHead><TableHead>Status</TableHead><TableHead>Raised in</TableHead></TableRow></TableHeader>
          <TableBody>{data.items.map((r: Dict) => (
            <TableRow key={`${r.link}-${r.id}`} className="cursor-pointer hover:bg-muted/50"
                      onClick={() => (r.link === "sageinvoice" ? drill?.open({ type: "sageinvoice", id: r.id, label: r.number }) : onOpen(r.id))}>
              <TableCell className="font-mono text-xs">{r.number}</TableCell><TableCell className="whitespace-nowrap">{fmtDate(r.date)}</TableCell>
              <TableCell className="max-w-[240px] truncate">{r.customer_id ? <DrillLink to={{ type: "customer", id: String(r.customer_id), label: r.customer }}>{r.customer}</DrillLink> : r.customer}</TableCell>
              <TableCell className="text-right"><Amount value={r.amount} /></TableCell><TableCell className="text-right"><Amount value={r.paid} blankZero /></TableCell>
              <TableCell className="text-right"><Amount value={r.balance} blankZero /></TableCell>
              <TableCell><span className={`rounded px-1.5 py-0.5 text-xs ${r.status === "void" ? "bg-red-500/15 text-red-700" : r.status === "open" ? "bg-amber-500/15 text-amber-700" : "bg-muted"}`}>{r.status}</span></TableCell>
              <TableCell className="text-xs">{r.raised_in}</TableCell>
            </TableRow>))}</TableBody>
        </Table>
      ))}
    </Section>
  );
}


/** Every customer is a ledger: the books since go-live (audited), each patient's Hope history, and HMOs / companies
 *  before go-live (Hope billing less Sage receipts). The three are never added together. */
function CustomerLedgers({ onReceive }: { onReceive: (customerId: string) => void }) {
  const [source, setSource] = useState("books");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [type, setType] = useState("");
  const [patient, setPatient] = useState<Dict | null>(null);
  const [payer, setPayer] = useState<Dict | null>(null);
  const [ledgerOf, setLedgerOf] = useState<Dict | null>(null);
  const [view, setView] = useState<"summary" | "sage">("summary");
  const { data, isLoading, error } = useBooks<Dict>(["customer-ledgers", source, search, status, type], "/ledgers/customers",
    { source, search: search || undefined, status: status || undefined, party_type: type || undefined });
  const rows: Dict[] = data?.rows ?? [];
  const label: Record<string, string> = { OWING: "Owing", PAID: "Paid in full", IN_CREDIT: "In credit" };
  // Hope's history and the pre-go-live HMO balances are Royan Hospital's; Scancare's books show their own ledgers only
  const SOURCES: [string, string][] = currentCompany() === "SCN" ? [["books", "Scancare customers"]]
    : [["books", "Roy Books (since go-live)"], ["hope", "Patients · Hope history"], ["payers", "HMOs & companies · before go-live"]];
  return (
    <Section title={<>Customer ledgers {source === "books" && data && <span className="text-sm font-normal text-muted-foreground">· {naira(data.owing)} owed to us{Number(data.in_credit) > 0 ? ` · ${naira(data.in_credit)} held in credit` : ""}</span>}</>}
             actions={<CsvButton filename={`customer-ledgers-${source}.csv`} rows={rows} />}>
      <div className="mb-3 flex flex-wrap gap-1">
        {SOURCES.map(([k, l]) => (
          <button key={k} onClick={() => { setSource(k); setStatus(k === "books" ? "" : "OWING"); }}
                  className={`rounded-full border px-3 py-1 text-xs ${source === k ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted"}`}>{l}</button>
        ))}
      </div>
      {source === "books" && (
        <div className="mb-3 flex gap-1">
          {([["summary", "Summary"], ["sage", "Customer Ledgers (Sage layout, A-Z)"]] as const).map(([k, l]) => (
            <Button key={k} size="sm" variant={view === k ? "default" : "outline"} className="h-7 text-xs" onClick={() => setView(k)}>{l}</Button>
          ))}
        </div>
      )}
      {source === "books" && view === "sage" ? <CustomerLedgerSage search={search} type={type} onJournal={undefined} /> : <>
      {data?.note && <p className="mb-3 text-xs text-muted-foreground">{data.note}</p>}
      <div className="mb-3 flex flex-wrap gap-2">
        <Input className="h-9 max-w-xs" placeholder={source === "payers" ? "HMO or company" : "Patient, MRN, HMO or company"} value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="h-9 rounded-md border bg-background px-2 text-sm" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Everyone</option><option value="OWING">Owing</option><option value="PAID">Paid in full</option><option value="IN_CREDIT">In credit</option>
        </select>
        {source !== "hope" && (
          <select className="h-9 rounded-md border bg-background px-2 text-sm" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">Patients, HMOs & companies</option>{source === "books" && <option value="PATIENT">Patients</option>}<option value="HMO">HMOs</option><option value="CORPORATE">Companies</option>
          </select>
        )}
      </div>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (rows.length === 0 ? (
        <Empty>{source === "books" ? "No customer has a document in Roy Books yet. Every bill raised and receipt taken from go-live adds a ledger here; for earlier years use the other two views." : "No customers match."}</Empty>
      ) : (
        <Table>
          <TableHeader><TableRow>
            <TableHead>Customer</TableHead><TableHead className="text-right">{source === "books" ? "Invoiced" : "Billed"}</TableHead><TableHead className="text-right">Received</TableHead>
            {source === "books" && <TableHead className="text-right">Credited</TableHead>}<TableHead className="text-right">Balance</TableHead><TableHead>Status</TableHead>
            {source !== "payers" && <TableHead>Last activity</TableHead>}<TableHead />
          </TableRow></TableHeader>
          <TableBody>{rows.map((r, n) => (
            <TableRow key={`${r.id ?? r.patient_id ?? r.payer_id}-${n}`} className={source !== "books" ? "cursor-pointer hover:bg-muted/50" : ""}
                      onClick={() => source === "hope" ? setPatient(r) : source === "payers" ? setPayer(r) : undefined}>
              <TableCell>{source === "books" ? <DrillLink to={{ type: "customer", id: String(r.id), label: r.name }}>{r.name}</DrillLink> : <span className="font-medium">{r.name}</span>}
                <span className="block text-xs text-muted-foreground">{String(r.party_type ?? "").toLowerCase()}{r.mrn ? ` · ${r.mrn}` : ""}{r.invoices ? ` · ${r.invoices} bill(s)` : ""}</span></TableCell>
              <TableCell className="text-right"><Amount value={r.invoiced} /></TableCell>
              <TableCell className="text-right"><Amount value={r.received} blankZero /></TableCell>
              {source === "books" && <TableCell className="text-right"><Amount value={r.credited} blankZero /></TableCell>}
              <TableCell className={`text-right font-semibold ${r.status === "OWING" ? "text-red-600" : r.status === "IN_CREDIT" ? "text-blue-600" : "text-green-600"}`}><Amount value={r.balance} /></TableCell>
              <TableCell className="text-xs">{label[r.status]}</TableCell>
              {source !== "payers" && <TableCell className="whitespace-nowrap text-xs">{r.last_activity ? fmtDate(r.last_activity) : "—"}</TableCell>}
              <TableCell onClick={(e) => e.stopPropagation()} className="whitespace-nowrap">
                {source === "books" && <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setLedgerOf(r)}>Ledger</Button>}
                {source === "books" && r.status === "OWING" && <Button size="sm" className="ml-1 h-7 text-xs" onClick={() => onReceive(String(r.id))}>Receive</Button>}
              </TableCell>
            </TableRow>
          ))}</TableBody>
        </Table>
      ))}
      </>}
      <DetailSheet size="wide" open={!!patient} onOpenChange={(o) => !o && setPatient(null)} title={patient ? `${patient.name} · ledger` : ""}
                   description="Every bill (sales, SJ) and receipt (cash receipts, CRJ) as Hope and the hospital recorded them, in Sage's ledger layout.">
        {patient && <PartyLedger params={{ patient_id: patient.patient_id }} name={patient.name} from="2016-01-01" />}
      </DetailSheet>
      <DetailSheet size="wide" open={!!ledgerOf} onOpenChange={(o) => !o && setLedgerOf(null)} title={ledgerOf ? `${ledgerOf.name} · ledger` : ""}
                   description="Receivables ledger in Sage's layout: Sage's years and Roy Books.">
        {ledgerOf && <PartyLedger params={{ customer_id: ledgerOf.id }} name={ledgerOf.name} from="2010-01-01" />}
      </DetailSheet>
      <DetailSheet open={!!payer} onOpenChange={(o) => !o && setPayer(null)} title={payer?.name ?? ""} description={data?.note}>
        {payer && (
          <div className="space-y-3 text-sm">
            <div className="grid grid-cols-3 gap-2">
              <div><p className="text-xs text-muted-foreground">Billed (Hope)</p><p className="font-semibold"><Amount value={payer.invoiced} /></p></div>
              <div><p className="text-xs text-muted-foreground">Received (Sage)</p><p className="font-semibold"><Amount value={payer.received} /></p></div>
              <div><p className="text-xs text-muted-foreground">Balance</p><p className="font-semibold"><Amount value={payer.balance} /></p></div>
            </div>
            <Table>
              <TableHeader><TableRow><TableHead>Age</TableHead><TableHead className="text-right">Still open</TableHead></TableRow></TableHeader>
              <TableBody>{(data?.age_labels ?? []).map((l: string, i: number) => (
                <TableRow key={l}><TableCell>{l} days</TableCell><TableCell className="text-right"><Amount value={payer.buckets?.[i]} blankZero /></TableCell></TableRow>
              ))}</TableBody>
            </Table>
            {Number(payer.unapplied) > 0 && <p className="text-xs text-muted-foreground">{naira(payer.unapplied)} received beyond what Hope billed (capitation, advances or receipts for pre-Hope years).</p>}
            {payer.oldest_open && <p className="text-xs text-muted-foreground">Oldest open month: {fmtDate(payer.oldest_open)}.</p>}
          </div>
        )}
      </DetailSheet>
    </Section>
  );
}

/** HMOs and companies before go-live (Hope billing less Sage receipts), aged - shown under the books' own aging. */
function PayerAgingHistory() {
  const { data, isLoading, error } = useBooks<Dict>(["payer-aging"], "/ledgers/payer-aging");
  if (isLoading) return <Loading />;
  if (error) return <ErrorNote error={error} />;
  if (!data || !(data.rows ?? []).length) return null;
  return (
    <Section title={<>Before go-live: HMOs & companies <span className="text-sm font-normal text-muted-foreground">· {naira(data.total)} open at {fmtDate(data.as_of)} ({data.source})</span></>}
             actions={<CsvButton filename="payer-aging-before-go-live.csv" rows={data.rows} />} className="mt-4">
      <Table>
        <TableHeader><TableRow><TableHead>Payer</TableHead>{data.labels.map((l: string) => <TableHead key={l} className="text-right">{l}</TableHead>)}<TableHead className="text-right">Total</TableHead></TableRow></TableHeader>
        <TableBody>
          {data.rows.map((r: Dict) => (
            <TableRow key={r.payer_id}><TableCell className="max-w-[220px] truncate">{r.hmo}<span className="block text-xs text-muted-foreground">{String(r.payer_type ?? "").toLowerCase()}</span></TableCell>
              {r.buckets.map((v: string, i: number) => <TableCell key={i} className="text-right"><Amount value={v} blankZero /></TableCell>)}
              <TableCell className="text-right font-semibold"><Amount value={r.owed} /></TableCell></TableRow>
          ))}
          <TableRow className="font-semibold"><TableCell>Total</TableCell>{data.totals.map((v: string, i: number) => <TableCell key={i} className="text-right"><Amount value={v} /></TableCell>)}<TableCell className="text-right"><Amount value={data.total} /></TableCell></TableRow>
        </TableBody>
      </Table>
    </Section>
  );
}


/** One customer's (or patient's) ledger in Sage's layout, for any dates. */
function PartyLedger({ params, name, from }: { params: Dict; name: string; from: string }) {
  const [range, setRange] = useState({ from, to: today() });
  const [journal, setJournal] = useState<string | null>(null);
  const { data, isLoading, error } = useBooks<Dict>(["party-gl", params, range], "/ledgers/customer-gl", { ...params, ...range });
  return (
    <div className="space-y-3">
      <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (data.rows.length === 0 ? <Empty>No entries for {name} in these dates.</Empty> : (
        <SageLedgerTable rows={data.rows} idLabel="Customer ID" nameLabel="Customer" filename={`ledger-${name}.csv`}
                         onLine={(r) => r.journal_id && setJournal(r.journal_id)} />
      ))}
      <JournalSheet id={journal} onClose={() => setJournal(null)} />
    </div>
  );
}

/** Customer Ledgers for everyone, A-Z, in Sage's layout (receivables lines from Sage's years and Roy Books). */
function CustomerLedgerSage({ search, type }: { search: string; type: string; onJournal?: (id: string) => void }) {
  const [range, setRange] = useState({ from: "2024-12-01", to: "2024-12-31" });
  const [journal, setJournal] = useState<string | null>(null);
  const { data, isLoading, error } = useBooks<Dict>(["customer-gl", range, search, type], "/ledgers/customer-gl",
    { ...range, search: search || undefined, party_type: type || undefined });
  return (
    <div className="space-y-3">
      <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && data.rows.length === 0 && <LedgerCoverageNote onRange={(f, t) => setRange({ from: f, to: t })} />}
      {data && data.rows.length > 0 && (
        <>
          <p className="text-xs text-muted-foreground">{data.customers} customers with a balance or entries, A-Z.</p>
          <SageLedgerTable rows={data.rows} idLabel="Customer ID" nameLabel="Customer" filename={`customer-ledgers-${range.from}-${range.to}.csv`}
                           onLine={(r) => r.journal_id && setJournal(r.journal_id)} />
        </>
      )}
      <JournalSheet id={journal} onClose={() => setJournal(null)} />
    </div>
  );
}
