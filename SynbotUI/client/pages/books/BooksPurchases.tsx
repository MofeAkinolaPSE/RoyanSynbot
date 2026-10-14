import { useEffect, useMemo, useState } from "react";
import { currentCompany } from "@/components/books/BooksShell";
import { WhtPicker } from "@/components/books/wht";
import { useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { DrillLink, SageTag } from "@/components/books/kit";
import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { DetailSheet } from "@/components/workspace/DetailSheet";
import { FilterBar } from "@/components/workspace/FilterBar";
import { PaymentWindow } from "@/components/books/payment-window";
import { useDrill } from "@/components/books/drill-context";
import { BooksShell } from "@/components/books/BooksShell";
import { RecordView } from "@/components/books/lineage";
import {
  AccountPick, act, Amount, BankSelect, CsvButton, DateRange, Empty, ErrorNote, JournalSheet, Loading, ProductPick,
  Section, StatusBadge, SupplierPick, useBooks, useLines,
} from "@/components/books/kit";
import { books, BooksError, Dict, fmtDate, naira, newIdemKey, num, today, yearStart } from "@/lib/books-api";
import { askText } from "@/lib/ask";

export default function BooksPurchases() {
  const [params, setParams] = useSearchParams();
  const [tab, setTab] = useState(params.get("tab") ?? "bills");
  const open = (k: string, v: string | null) => { const p = new URLSearchParams(params); v ? p.set(k, v) : p.delete(k); setParams(p, { replace: true }); };
  return (
    <BooksShell title="Purchases & Payables"
                actions={<>
                  <Button size="sm" onClick={() => open("new", "bill")}><Plus className="mr-1 h-4 w-4" />Supplier bill</Button>
                  <Button size="sm" variant="outline" onClick={() => open("new", "payment")}>Pay supplier</Button>
                  <Button size="sm" variant="outline" onClick={() => open("new", "oneoff")}>One-off payment</Button>
                  <Button size="sm" variant="outline" onClick={() => open("new", "debitnote")}>Return to supplier</Button>
                </>}>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap">
          <TabsTrigger value="bills">Bills</TabsTrigger>
          <TabsTrigger value="ledgers">Supplier ledgers</TabsTrigger>
          {currentCompany() !== "SCN" && <TabsTrigger value="history">Purchase history (Hope)</TabsTrigger>}
          <TabsTrigger value="payments">Payments</TabsTrigger>
          <TabsTrigger value="debit">Returns / debit notes</TabsTrigger>
          <TabsTrigger value="aging">Aged payables</TabsTrigger>
          <TabsTrigger value="statement">Supplier statement</TabsTrigger>
        </TabsList>
        <TabsContent value="bills"><BillList onOpen={(id) => open("bill", id)} /></TabsContent>
        <TabsContent value="history"><HopePurchases /></TabsContent>
        <TabsContent value="ledgers"><SupplierLedgers onPay={(sid) => { const p = new URLSearchParams(params); p.set("new", "payment"); p.set("supplier", sid); setParams(p, { replace: true }); }} /></TabsContent>
        <TabsContent value="payments"><PaymentList onOpen={(id) => open("payment", id)} /></TabsContent>
        <TabsContent value="debit"><DebitNoteList onOpen={(id) => open("debitnote", id)} /></TabsContent>
        <TabsContent value="aging"><AgedPayables /></TabsContent>
        <TabsContent value="statement"><SupplierStatement /></TabsContent>
      </Tabs>
      <BillForm open={params.get("new") === "bill"} onClose={(id) => { open("new", null); if (id) open("bill", id); }} />
      {/* Sage's Payments window: a supplier's bills, or anyone ("Pay to the order of"), coded to expense or fixed-asset accounts */}
      <PaymentWindow open={params.get("new") === "payment" || params.get("new") === "oneoff"} oneOff={params.get("new") === "oneoff"}
                     onClose={() => { const p = new URLSearchParams(params); ["new", "supplier", "pay"].forEach((k) => p.delete(k)); setParams(p, { replace: true }); }} />
      <DebitNoteForm open={params.get("new") === "debitnote"} onClose={() => open("new", null)} />
      <DocDetail kind="bill" id={params.get("bill")} onClose={() => open("bill", null)} />
      <DocDetail kind="payment" id={params.get("payment")} onClose={() => open("payment", null)} />
      <DocDetail kind="debitnote" id={params.get("debitnote")} onClose={() => open("debitnote", null)} />
    </BooksShell>
  );
}

function BillList({ onOpen }: { onOpen: (id: string) => void }) {
  const [search, setSearch] = useState("");
  const [openOnly, setOpenOnly] = useState("");
  const [range, setRange] = useState({ from: yearStart(), to: today() });
  const { data, isLoading, error } = useBooks<any>(["bills", search, openOnly, range], "/payables/bills",
    { search, open_only: openOnly === "open", from: range.from, to: range.to, limit: 300 });
  return (
    <Section title={`Supplier bills${data ? ` (${data.total})` : ""}`} actions={<CsvButton filename="bills.csv" rows={data?.items} />}>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div className="flex-1"><FilterBar search={{ value: search, onChange: setSearch, placeholder: "Bill no., supplier, supplier invoice no." }}
          selects={[{ label: "Show", value: openOnly, onChange: setOpenOnly, options: [{ value: "open", label: "Unpaid only" }] }]} /></div>
        <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
      </div>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (data.items.length === 0 ? <Empty>No bills in this period.</Empty> : (
        <Table>
          <TableHeader><TableRow><TableHead>Bill</TableHead><TableHead>Supplier inv.</TableHead><TableHead>Date</TableHead><TableHead>Supplier</TableHead><TableHead>Due</TableHead><TableHead className="text-right">Total</TableHead><TableHead className="text-right">Balance</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
          <TableBody>{data.items.map((b: Dict) => (
            <TableRow key={b.id} className="cursor-pointer hover:bg-muted/50" onClick={() => onOpen(b.id)}>
              <TableCell className="font-mono text-xs">{b.bill_number}{b.is_opening && <span className="ml-1 text-xs text-muted-foreground">opening</span>}</TableCell>
              <TableCell className="text-xs">{b.supplier_invoice_number}</TableCell>
              <TableCell className="whitespace-nowrap">{fmtDate(b.bill_date)}</TableCell>
              <TableCell className="max-w-[220px] truncate"><DrillLink to={{ type: "supplier", id: String(b.supplier_id ?? ""), label: b.supplier_name }}>{b.supplier_name}</DrillLink></TableCell>
              <TableCell className={b.due_date < today() && Number(b.balance_due) > 0 ? "text-red-600" : ""}>{fmtDate(b.due_date)}</TableCell>
              <TableCell className="text-right"><Amount value={b.total} /></TableCell>
              <TableCell className="text-right"><Amount value={b.balance_due} /></TableCell>
              <TableCell><StatusBadge status={b.status} /></TableCell>
            </TableRow>
          ))}</TableBody>
        </Table>
      ))}
    </Section>
  );
}

function PaymentList({ onOpen }: { onOpen: (id: string) => void }) {
  const drill = useDrill();
  const [search, setSearch] = useState("");
  const [range, setRange] = useState({ from: yearStart(), to: today() });
  const { data, isLoading, error } = useBooks<any>(["spayments", search, range], "/payables/payments", { search, from: range.from, to: range.to, limit: 300 });
  return (
    <Section title={`Supplier payments${data ? ` (${data.total})` : ""}`} actions={<CsvButton filename="supplier-payments.csv" rows={data?.items} />}>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div className="flex-1"><FilterBar search={{ value: search, onChange: setSearch, placeholder: "Payment no., supplier, cheque ref" }} /></div>
        <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
      </div>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (data.items.length === 0 ? <Empty>No payments in this period.</Empty> : (
        <Table>
          <TableHeader><TableRow><TableHead>Payment</TableHead><TableHead>Date</TableHead><TableHead>Supplier</TableHead><TableHead>Method</TableHead><TableHead>From</TableHead><TableHead className="text-right">Paid</TableHead><TableHead className="text-right">WHT</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
          <TableBody>{data.items.map((p: Dict) => (
            <TableRow key={p.id ?? p.voucher} className="cursor-pointer hover:bg-muted/50"
                      onClick={() => (p.origin === "SAGE" ? drill?.open({ type: "sagevoucher", id: p.voucher, label: p.payment_number }) : onOpen(p.id))}>
              <TableCell className="font-mono text-xs">{p.payment_number}{p.origin === "SAGE" && <SageTag />}</TableCell><TableCell className="whitespace-nowrap">{fmtDate(p.payment_date)}</TableCell>
              <TableCell className="max-w-[220px] truncate">{p.supplier_id ? <DrillLink to={{ type: "supplier", id: String(p.supplier_id), label: p.supplier_name }}>{p.supplier_name}</DrillLink> : <span className="text-xs">{p.supplier_name}</span>}</TableCell><TableCell className="text-xs">{p.method.toLowerCase()} {p.reference}</TableCell>
              <TableCell className="text-xs">{p.bank_account_name}</TableCell><TableCell className="text-right"><Amount value={p.amount} /></TableCell>
              <TableCell className="text-right"><Amount value={p.wht_amount} blankZero /></TableCell><TableCell><StatusBadge status={p.status} /></TableCell>
            </TableRow>
          ))}</TableBody>
        </Table>
      ))}
    </Section>
  );
}

function DebitNoteList({ onOpen }: { onOpen: (id: string) => void }) {
  const { data, isLoading, error } = useBooks<any>(["debitnotes"], "/payables/debit-notes", { limit: 300 });
  return (
    <Section title="Returns outward / debit notes">
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (data.items.length === 0 ? <Empty>No supplier returns yet.</Empty> : (
        <Table>
          <TableHeader><TableRow><TableHead>Number</TableHead><TableHead>Date</TableHead><TableHead>Supplier</TableHead><TableHead>Against</TableHead><TableHead>Reason</TableHead><TableHead className="text-right">Total</TableHead></TableRow></TableHeader>
          <TableBody>{data.items.map((d: Dict) => (
            <TableRow key={d.id} className="cursor-pointer hover:bg-muted/50" onClick={() => onOpen(d.id)}>
              <TableCell className="font-mono text-xs">{d.debit_note_number}</TableCell><TableCell className="whitespace-nowrap">{fmtDate(d.note_date)}</TableCell>
              <TableCell>{d.supplier_name}</TableCell><TableCell className="font-mono text-xs">{d.bill_number ?? "—"}</TableCell>
              <TableCell className="max-w-[240px] truncate text-xs">{d.reason}</TableCell><TableCell className="text-right"><Amount value={d.total} /></TableCell>
            </TableRow>
          ))}</TableBody>
        </Table>
      ))}
    </Section>
  );
}

type BLine = { line_type: string; product: Dict | null; account: Dict | null; description: string; quantity: string; unit_cost: string; line_total: string; batch_number: string; expiry_date: string };
const blankBLine = (): BLine => ({ line_type: "ITEM", product: null, account: null, description: "", quantity: "", unit_cost: "", line_total: "", batch_number: "", expiry_date: "" });
const bLineTotal = (l: BLine) => (l.line_total ? Number(l.line_total) : Number(l.quantity || 0) * Number(l.unit_cost || 0));

function BillForm({ open, onClose }: { open: boolean; onClose: (id?: string) => void }) {
  const qc = useQueryClient();
  const [supplier, setSupplier] = useState<Dict | null>(null);
  const [f, setF] = useState({ supplier_invoice_number: "", bill_date: today(), due_date: "", notes: "" });
  const [busy, setBusy] = useState(false);
  const [idem] = useState(newIdemKey);
  const L = useLines<BLine>(blankBLine);
  useEffect(() => { if (!open) { setSupplier(null); L.reset(); setF({ supplier_invoice_number: "", bill_date: today(), due_date: "", notes: "" }); } }, [open]);
  const total = L.lines.reduce((s, l) => s + bLineTotal(l), 0);
  const submit = async () => {
    setBusy(true);
    const b = await act(() => books.post("/payables/bills", {
      supplier_id: supplier?.id, ...f, due_date: f.due_date || undefined,
      lines: L.lines.map((l) => ({ line_type: l.line_type, sku: l.product?.sku, account_id: l.account?.id, description: l.description || undefined,
        quantity: l.quantity || 1, unit_cost: l.unit_cost || 0, line_total: l.line_total || undefined, batch_number: l.batch_number || undefined,
        expiry_date: l.expiry_date || undefined })),
    }, idem), "Bill posted");
    setBusy(false);
    if (b) { qc.invalidateQueries({ queryKey: ["books"] }); onClose(b.id); }
  };
  return (
    <DetailSheet size="wide" open={open} onOpenChange={(o) => !o && onClose()} title="Record supplier bill"
                 description="Stock not yet received: use stock lines (received into inventory with batch & expiry). Stock the pharmacy has ALREADY received sits in Goods Received Not Invoiced: enter it as an expense line to account 21100 so it is not counted twice."
                 footer={<div className="flex w-full items-center justify-between"><span className="text-sm">Total <strong>{naira(total)}</strong></span>
                   <Button disabled={busy || !supplier || !f.supplier_invoice_number || total <= 0} onClick={submit}>{busy ? "Posting…" : "Post bill"}</Button></div>}>
      <div className="space-y-3">
        <SupplierPick value={supplier} onChange={setSupplier} />
        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1"><Label className="text-xs">Supplier invoice no.</Label><Input value={f.supplier_invoice_number} onChange={(e) => setF({ ...f, supplier_invoice_number: e.target.value })} /></div>
          <div className="space-y-1"><Label className="text-xs">Invoice date</Label><Input type="date" value={f.bill_date} onChange={(e) => setF({ ...f, bill_date: e.target.value })} /></div>
          <div className="space-y-1"><Label className="text-xs">Due (default: supplier terms)</Label><Input type="date" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} /></div>
        </div>
        {L.lines.map((l, i) => (
          <div key={i} className="space-y-2 rounded-lg border p-2">
            <div className="flex items-center gap-2">
              <select className="h-8 rounded-md border bg-background px-2 text-xs" value={l.line_type} onChange={(e) => L.update(i, { line_type: e.target.value })}>
                <option value="ITEM">Stock received</option><option value="EXPENSE">Expense / service</option><option value="ASSET">Fixed asset</option>
              </select>
              <div className="flex-1">{l.line_type === "ITEM" ? <ProductPick value={l.product} onChange={(p) => L.update(i, { product: p })} />
                : <AccountPick value={l.account} onChange={(a) => L.update(i, { account: a })} accountType={l.line_type === "ASSET" ? "ASSET" : undefined} />}</div>
              <Button size="icon" variant="ghost" onClick={() => L.remove(i)}><Trash2 className="h-4 w-4" /></Button>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <Input className="h-8" type="number" placeholder="Qty" value={l.quantity} onChange={(e) => L.update(i, { quantity: e.target.value })} />
              <Input className="h-8" type="number" placeholder="Unit cost" value={l.unit_cost} onChange={(e) => L.update(i, { unit_cost: e.target.value })} />
              <Input className="h-8" type="number" placeholder="Line total (as on invoice)" value={l.line_total} onChange={(e) => L.update(i, { line_total: e.target.value })} />
            </div>
            {l.line_type === "ITEM" ? (
              <div className="grid grid-cols-2 gap-2">
                <Input className="h-8" placeholder="Batch / lot number" value={l.batch_number} onChange={(e) => L.update(i, { batch_number: e.target.value })} />
                <Input className="h-8" type="date" title="Expiry date" value={l.expiry_date} onChange={(e) => L.update(i, { expiry_date: e.target.value })} />
              </div>
            ) : <Input className="h-8" placeholder="Description" value={l.description} onChange={(e) => L.update(i, { description: e.target.value })} />}
            <div className="text-right text-xs text-muted-foreground">Line {naira(bLineTotal(l))}</div>
          </div>
        ))}
        <Button size="sm" variant="outline" onClick={L.add}><Plus className="mr-1 h-4 w-4" />Add line</Button>
        <div className="space-y-1"><Label className="text-xs">Notes</Label><Textarea rows={2} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></div>
      </div>
    </DetailSheet>
  );
}

function PaymentForm({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [supplier, setSupplier] = useState<Dict | null>(null);
  const [f, setF] = useState({ payment_date: today(), method: "TRANSFER", bank_account_id: "", amount: "", wht_amount: "", reference: "", notes: "" });
  const [alloc, setAlloc] = useState<Record<string, string>>({});
  const [dupe, setDupe] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [idem] = useState(newIdemKey);
  useEffect(() => { if (!open) { setSupplier(null); setAlloc({}); setDupe(null); } }, [open]);
  const { data: items } = useBooks<Dict[]>(["ap-open", supplier?.id], "/payables/open-items", { supplier_id: supplier?.id }, !!supplier);
  const bills = useMemo(() => (items ?? []).filter((i) => i.doc_type === "BILL" && Number(i.open_amount) > 0).sort((a, b) => (a.due_date < b.due_date ? -1 : 1)), [items]);
  const available = Number(f.amount || 0) + Number(f.wht_amount || 0);
  const allocated = Object.values(alloc).reduce((s, v) => s + Number(v || 0), 0);
  // Paying bills: the amount follows the bills ticked, less the WHT withheld for FIRS.
  useEffect(() => {
    const w = Number(f.wht_amount || 0);
    if (allocated > 0 && (w > 0 || !f.amount)) setF((x) => ({ ...x, amount: (allocated - w).toFixed(2) }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allocated, f.wht_amount]);
  const submit = async (confirm = false) => {
    setBusy(true);
    try {
      await books.post("/payables/payments", { ...f, supplier_id: supplier?.id, confirm_duplicate: confirm,
        allocations: Object.entries(alloc).filter(([, v]) => Number(v) > 0).map(([bill_id, amount]) => ({ bill_id, amount })) }, idem + (confirm ? "c" : ""));
      qc.invalidateQueries({ queryKey: ["books"] });
      onClose();
    } catch (e) {
      const err = e as BooksError;
      if (err.code === "DUPLICATE_REFERENCE") setDupe(err.message); else act(async () => { throw e; });
    } finally { setBusy(false); }
  };
  return (
    <DetailSheet size="wide" open={open} onOpenChange={(o) => !o && onClose()} title="Pay supplier"
                 description="WHT withheld is owed to FIRS; the supplier's bill is settled for the full amount."
                 footer={<div className="flex w-full items-center justify-between"><span className="text-xs">Settles {naira(allocated)} of {naira(available)}</span>
                   <Button disabled={busy || !supplier || !f.bank_account_id || Number(f.amount) <= 0 || allocated > available + 0.001} onClick={() => submit(false)}>{busy ? "Posting…" : "Post payment"}</Button></div>}>
      <div className="space-y-3">
        <SupplierPick value={supplier} onChange={(s) => { setSupplier(s); setAlloc({}); }} />
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1"><Label className="text-xs">Date</Label><Input type="date" value={f.payment_date} onChange={(e) => setF({ ...f, payment_date: e.target.value })} /></div>
          <div className="space-y-1"><Label className="text-xs">Method</Label><select className="h-9 w-full rounded-md border bg-background px-2 text-sm" value={f.method} onChange={(e) => setF({ ...f, method: e.target.value })}>
            {["TRANSFER", "CHEQUE", "CASH", "OTHER"].map((m) => <option key={m} value={m}>{m.toLowerCase()}</option>)}</select></div>
        </div>
        <BankSelect value={f.bank_account_id} onChange={(v) => setF({ ...f, bank_account_id: v })} label="Paid from" />
        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1"><Label className="text-xs">Amount paid</Label><Input type="number" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></div>
          <WhtPicker label="WHT withheld (owed to FIRS)" gross={allocated} value={f.wht_amount} onChange={(v) => setF((x) => ({ ...x, wht_amount: v }))} />
          <div className="space-y-1"><Label className="text-xs">Cheque / transfer ref</Label><Input value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} /></div>
        </div>
        {dupe && (
          <div className="space-y-2 rounded-lg border border-amber-400 bg-amber-50 p-3 text-sm dark:bg-amber-500/10">
            <div className="flex items-center gap-2 font-medium text-amber-800 dark:text-amber-300"><AlertTriangle className="h-4 w-4" />{dupe}</div>
            <div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => setDupe(null)}>Fix the reference</Button><Button size="sm" onClick={() => submit(true)}>It is genuine — post anyway</Button></div>
          </div>
        )}
        {supplier && (bills.length === 0 ? <Empty>No unpaid bills for this supplier.</Empty> : (
          <Table>
            <TableHeader><TableRow><TableHead>Bill</TableHead><TableHead>Supplier inv.</TableHead><TableHead>Due</TableHead><TableHead className="text-right">Open</TableHead><TableHead className="w-32">Settle</TableHead></TableRow></TableHeader>
            <TableBody>{bills.map((b) => (
              <TableRow key={b.doc_id}><TableCell className="font-mono text-xs">{b.doc_number}</TableCell><TableCell className="text-xs">{b.supplier_ref}</TableCell>
                <TableCell className="text-xs">{fmtDate(b.due_date)}</TableCell><TableCell className="text-right"><Amount value={b.open_amount} /></TableCell>
                <TableCell><Input className="h-8" type="number" value={alloc[b.doc_id] ?? ""} onChange={(e) => setAlloc({ ...alloc, [b.doc_id]: e.target.value })} /></TableCell></TableRow>
            ))}</TableBody>
          </Table>
        ))}
      </div>
    </DetailSheet>
  );
}

const RETURN_REASONS = ["Expired / short expiry", "Damaged in transit", "Wrong item supplied", "Excess quantity supplied",
  "Quality / recall", "Price dispute"];

/** Return to supplier: pick the supplier bill and its lines load with what can still go back; or return items not
 *  tied to a bill. Stock leaves at its book cost and the supplier owes us (or we owe them less) by what they credit. */
function DebitNoteForm({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [, setParams] = useSearchParams();
  const [supplier, setSupplier] = useState<Dict | null>(null);
  const [billId, setBillId] = useState("");
  const [reason, setReason] = useState(RETURN_REASONS[0]);
  const [other, setOther] = useState("");
  const [date, setDate] = useState(today());
  const [busy, setBusy] = useState(false);
  const [ret, setRet] = useState<Record<string, { qty: string; credit: string }>>({});
  const L = useLines<BLine>(blankBLine);
  const { data: bills } = useBooks<any>(["dn-bills", supplier?.id], "/payables/bills", { supplier_id: supplier?.id, limit: 200 }, !!supplier);
  const { data: bill } = useBooks<Dict>(["dn-bill", billId], `/payables/bills/${billId}`, undefined, !!billId);
  useEffect(() => { if (!open) { setSupplier(null); setBillId(""); setReason(RETURN_REASONS[0]); setOther(""); setRet({}); L.reset(); } }, [open]);
  useEffect(() => setRet({}), [billId]);
  const itemLines: Dict[] = (bill?.lines ?? []).filter((l: Dict) => l.line_type === "ITEM");
  const why = reason === "Other" ? other.trim() : reason;
  const fromBill = itemLines.filter((l) => Number(ret[l.id]?.qty || 0) > 0).map((l) => ({
    line_type: "ITEM", sku: l.sku, batch_id: l.batch_id || undefined, quantity: ret[l.id].qty,
    line_total: ret[l.id].credit || (Number(ret[l.id].qty) * Number(l.unit_cost || 0)).toFixed(2),
  }));
  const manual = L.lines.filter((l) => l.product).map((l) => ({ line_type: "ITEM", sku: l.product?.sku, quantity: l.quantity,
    batch_number: l.batch_number || undefined, line_total: l.line_total || undefined }));
  const lines = billId ? fromBill : manual;
  const overs = itemLines.filter((l) => Number(ret[l.id]?.qty || 0) > Number(l.returnable));
  const total = billId ? fromBill.reduce((n, l) => n + Number(l.line_total || 0), 0) : null;
  const submit = async () => {
    setBusy(true);
    let created: Dict | null = null;
    const ok = await act(async () => { created = await books.post<Dict>("/payables/debit-notes", { supplier_id: supplier?.id, bill_id: billId || undefined,
      note_date: date, reason: why, lines }); return created; }, "Return posted");
    setBusy(false);
    if (ok) {
      qc.invalidateQueries({ queryKey: ["books"] });
      const id = (created as Dict | null)?.id;
      // close the form and open the posted return in one step (two separate URL updates would race)
      if (id) setParams((p) => { p.delete("new"); p.set("debitnote", String(id)); return p; });
      else onClose();
    }
  };
  return (
    <DetailSheet size="wide" open={open} onOpenChange={(o) => !o && onClose()} title="Return to supplier (return outward)"
                 description="Stock leaves at its book cost; the supplier balance goes down by what they credit you. A return against an unpaid bill is applied to that bill."
                 footer={<div className="flex w-full items-center justify-between">
                   <span className="text-xs text-muted-foreground">{total !== null ? `Credit ${naira(total)}` : ""}</span>
                   <Button disabled={busy || !supplier || !why || lines.length === 0 || overs.length > 0} onClick={submit}>{busy ? "Posting…" : "Post return"}</Button></div>}>
      <div className="space-y-3">
        <SupplierPick value={supplier} onChange={(v) => { setSupplier(v); setBillId(""); }} />
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1"><Label className="text-xs">Supplier bill the goods came on</Label>
            <select className="h-9 w-full rounded-md border bg-background px-2 text-sm" value={billId} onChange={(e) => setBillId(e.target.value)} disabled={!supplier}>
              <option value="">— not tied to a bill (enter items) —</option>
              {(bills?.items ?? []).filter((b: Dict) => b.status !== "VOID").map((b: Dict) => (
                <option key={b.id} value={b.id}>{b.bill_number} · {b.supplier_invoice_number ?? "—"} · {fmtDate(b.bill_date)} · {naira(b.total)}</option>))}
            </select></div>
          <div className="space-y-1"><Label className="text-xs">Return date</Label><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1"><Label className="text-xs">Reason</Label>
            <select className="h-9 w-full rounded-md border bg-background px-2 text-sm" value={reason} onChange={(e) => setReason(e.target.value)}>
              {RETURN_REASONS.map((r) => <option key={r}>{r}</option>)}<option value="Other">Other…</option>
            </select></div>
          {reason === "Other" && <div className="space-y-1"><Label className="text-xs">Describe</Label><Input value={other} onChange={(e) => setOther(e.target.value)} /></div>}
        </div>

        {billId ? (
          !bill ? <Loading /> : itemLines.length === 0 ? <Empty>This bill has no stock lines to return (it is for services or expenses).</Empty> : (
            <Table>
              <TableHeader><TableRow>
                <TableHead>Item</TableHead><TableHead>Batch · expiry</TableHead><TableHead className="text-right">Bought</TableHead>
                <TableHead className="text-right">Returned</TableHead><TableHead className="text-right">Unit cost</TableHead>
                <TableHead className="w-24">Return qty</TableHead><TableHead className="w-32">Credit ₦</TableHead>
              </TableRow></TableHeader>
              <TableBody>{itemLines.map((l) => {
                const r = ret[l.id] ?? { qty: "", credit: "" };
                const over = Number(r.qty || 0) > Number(l.returnable);
                return (
                  <TableRow key={l.id}>
                    <TableCell className="max-w-[220px] truncate">{l.description || l.sku}<span className="block font-mono text-xs text-muted-foreground">{l.sku}</span></TableCell>
                    <TableCell className="text-xs">{l.batch_number ?? "—"}{l.expiry_date ? ` · ${fmtDate(l.expiry_date)}` : ""}</TableCell>
                    <TableCell className="text-right">{num(l.quantity)}</TableCell>
                    <TableCell className="text-right text-muted-foreground">{num(l.returned)}</TableCell>
                    <TableCell className="text-right"><Amount value={l.unit_cost} /></TableCell>
                    <TableCell><Input className={`h-8 ${over ? "border-red-500" : ""}`} type="number" min="0" max={Number(l.returnable)} placeholder={`≤ ${num(l.returnable)}`}
                      value={r.qty} disabled={Number(l.returnable) <= 0} onChange={(e) => setRet({ ...ret, [l.id]: { ...r, qty: e.target.value } })} /></TableCell>
                    <TableCell><Input className="h-8" type="number" placeholder={r.qty ? (Number(r.qty) * Number(l.unit_cost || 0)).toFixed(2) : "at cost"}
                      value={r.credit} onChange={(e) => setRet({ ...ret, [l.id]: { ...r, credit: e.target.value } })} /></TableCell>
                  </TableRow>
                );
              })}</TableBody>
            </Table>
          )
        ) : (
          <>
            {L.lines.map((l, i) => (
              <div key={i} className="grid grid-cols-[1fr_70px_100px_120px_32px] items-end gap-2">
                <ProductPick label={i === 0 ? "Product" : undefined} value={l.product} onChange={(p) => L.update(i, { product: p })} />
                <Input className="h-9" type="number" placeholder="Qty" value={l.quantity} onChange={(e) => L.update(i, { quantity: e.target.value })} />
                <Input className="h-9" placeholder="Batch" value={l.batch_number} onChange={(e) => L.update(i, { batch_number: e.target.value })} />
                <Input className="h-9" type="number" placeholder="Credit ₦ (blank = cost)" value={l.line_total} onChange={(e) => L.update(i, { line_total: e.target.value })} />
                <Button size="icon" variant="ghost" onClick={() => L.remove(i)}><Trash2 className="h-4 w-4" /></Button>
              </div>
            ))}
            <Button size="sm" variant="outline" onClick={L.add}><Plus className="mr-1 h-4 w-4" />Add line</Button>
          </>
        )}
        {overs.length > 0 && <p className="text-xs text-red-600">More than was bought (less what is already returned) cannot go back on this bill.</p>}
      </div>
    </DetailSheet>
  );
}

/** A supplier credit not yet used: apply it to the supplier's open bills. */
function ApplyCredit({ dn, onDone }: { dn: Dict; onDone: () => void }) {
  const available = Number(dn.total ?? 0) - Number(dn.amount_settled ?? 0);
  const { data: bills } = useBooks<any>(["dn-open-bills", dn.supplier_id], "/payables/bills", { supplier_id: dn.supplier_id, open_only: true, limit: 200 }, available > 0);
  const [alloc, setAlloc] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  if (available <= 0.001 || dn.status === "VOID") return null;
  const used = Object.values(alloc).reduce((n, v) => n + Number(v || 0), 0);
  const open = (bills?.items ?? []).filter((b: Dict) => ["POSTED", "PARTIALLY_PAID"].includes(b.status));
  const save = async () => {
    setBusy(true);
    const ok = await act(() => books.post(`/payables/debit-notes/${dn.id}/allocate`, {
      allocations: Object.entries(alloc).filter(([, v]) => Number(v) > 0).map(([bill_id, amount]) => ({ bill_id, amount })) }), "Credit applied");
    setBusy(false);
    if (ok) { setAlloc({}); onDone(); }
  };
  return (
    <Section title={<>Apply this credit <span className="text-sm font-normal text-muted-foreground">· {naira(available)} unused</span></>} className="mb-4"
             actions={<Button size="sm" disabled={busy || used <= 0 || used > available + 0.001} onClick={save}>{busy ? "Applying…" : `Apply ${naira(used)}`}</Button>}>
      {open.length === 0 ? <Empty>This supplier has no open bills; the credit stays on their account.</Empty> : (
        <Table>
          <TableHeader><TableRow><TableHead>Bill</TableHead><TableHead>Date</TableHead><TableHead className="text-right">Outstanding</TableHead><TableHead className="w-36">Apply ₦</TableHead></TableRow></TableHeader>
          <TableBody>{open.map((b: Dict) => (
            <TableRow key={b.id}><TableCell className="font-mono text-xs">{b.bill_number}</TableCell><TableCell>{fmtDate(b.bill_date)}</TableCell>
              <TableCell className="text-right"><Amount value={b.balance_due ?? (Number(b.total) - Number(b.amount_settled))} /></TableCell>
              <TableCell><Input className="h-8" type="number" value={alloc[b.id] ?? ""} onChange={(e) => setAlloc({ ...alloc, [b.id]: e.target.value })} /></TableCell></TableRow>
          ))}</TableBody>
        </Table>
      )}
    </Section>
  );
}

function DocDetail({ kind, id, onClose }: { kind: "bill" | "payment" | "debitnote"; id: string | null; onClose: () => void }) {
  const qc = useQueryClient();
  const path = { bill: "/payables/bills/", payment: "/payables/payments/", debitnote: "/payables/debit-notes/" }[kind] + id;
  const { data: d, refetch } = useBooks<Dict>([kind, id], path, undefined, !!id);
  const [v, setV] = useState(0);
  const voidIt = async () => {
    const reason = await askText(`Why is this ${kind === "bill" ? "bill" : "payment"} being voided?`);
    if (reason && (await act(() => books.post(`${path}/void`, { reason }), "Voided"))) { refetch(); setV((x) => x + 1); qc.invalidateQueries({ queryKey: ["books"] }); }
  };
  const title = d ? (kind === "bill" ? `Bill ${d.bill_number}` : kind === "payment" ? `Payment ${d.payment_number}` : `Debit note ${d.debit_note_number}`) : "";
  const canVoid = d && kind !== "debitnote" && d.status !== "VOID" && !d.is_opening;
  return (
    <DetailSheet size="wide" open={!!id} onOpenChange={(o) => !o && onClose()} title={title} description={d?.supplier_name}
                 footer={canVoid ? <Button size="sm" variant="destructive" onClick={voidIt}>Void</Button> : undefined}>
      {kind === "debitnote" && d && <ApplyCredit dn={d} onDone={() => { refetch(); setV((x) => x + 1); qc.invalidateQueries({ queryKey: ["books"] }); }} />}
      {id && <RecordView key={`${id}:${v}`} t={{ type: kind, id }} />}
    </DetailSheet>
  );
}

function Row({ k, v, bold }: { k: string; v: any; bold?: boolean }) {
  return <div className={`flex justify-between ${bold ? "font-semibold" : ""}`}><span className="text-muted-foreground">{k}</span><Amount value={v} /></div>;
}

function AgedPayables() {
  const [asOf, setAsOf] = useState(today());
  const { data, isLoading, error } = useBooks<any>(["aged-ap", asOf], "/reports/aged-payables", { as_of: asOf });
  return (
    <Section title="Aged payables (by due date)" actions={<CsvButton filename={`aged-payables-${asOf}.csv`} rows={data?.rows.map((r: Dict) => ({ supplier: r.supplier_name, ...Object.fromEntries(data.buckets.map((b: string, i: number) => [b, r.buckets[i]])), total: r.total }))} />}>
      <DateRange single to={asOf} onChange={(_, t) => setAsOf(t)} />
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (
        <Table className="mt-3">
          <TableHeader><TableRow><TableHead>Supplier</TableHead>{data.buckets.map((b: string) => <TableHead key={b} className="text-right">{b}</TableHead>)}<TableHead className="text-right">Total</TableHead></TableRow></TableHeader>
          <TableBody>
            {data.rows.map((r: Dict) => (
              <TableRow key={r.supplier_id}><TableCell><DrillLink to={{ type: "supplier", id: String(r.supplier_id), label: r.supplier_name }}>{r.supplier_name}</DrillLink></TableCell>{r.buckets.map((v: string, i: number) => <TableCell key={i} className="text-right"><Amount value={v} blankZero /></TableCell>)}<TableCell className="text-right font-semibold"><Amount value={r.total} /></TableCell></TableRow>
            ))}
            <TableRow className="font-semibold"><TableCell>Total</TableCell>{data.bucket_totals.map((v: string, i: number) => <TableCell key={i} className="text-right"><Amount value={v} /></TableCell>)}<TableCell className="text-right"><Amount value={data.total} /></TableCell></TableRow>
          </TableBody>
        </Table>
      )}
    </Section>
  );
}

function SupplierStatement() {
  const [supplier, setSupplier] = useState<Dict | null>(null);
  const [range, setRange] = useState({ from: yearStart(), to: today() });
  const { data, isLoading, error } = useBooks<any>(["sstatement", supplier?.id, range], `/reports/supplier-statement/${supplier?.id}`, range, !!supplier);
  return (
    <Section title="Supplier statement" actions={<CsvButton filename="supplier-statement.csv" rows={data?.rows} />}>
      <div className="mb-3 grid gap-3 md:grid-cols-[1fr_auto]"><SupplierPick value={supplier} onChange={setSupplier} />
        <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} /></div>
      {!supplier && <Empty>Choose a supplier to reconcile against their statement.</Empty>}
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (
        <div className="space-y-2 text-sm">
          <div className="flex justify-between"><span>Brought forward</span><Amount value={data.opening_balance} bold /></div>
          <Table>
            <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Document</TableHead><TableHead>Details</TableHead><TableHead className="text-right">Paid / returned</TableHead><TableHead className="text-right">Billed</TableHead><TableHead className="text-right">We owe</TableHead></TableRow></TableHeader>
            <TableBody>{data.rows.map((r: Dict, i: number) => (
              <TableRow key={i}><TableCell className="whitespace-nowrap">{fmtDate(r.date)}</TableCell><TableCell className="font-mono text-xs">{r.number}</TableCell><TableCell className="text-xs">{r.type}</TableCell>
                <TableCell className="text-right"><Amount value={r.debit} blankZero /></TableCell><TableCell className="text-right"><Amount value={r.credit} blankZero /></TableCell><TableCell className="text-right"><Amount value={r.balance} /></TableCell></TableRow>
            ))}</TableBody>
          </Table>
          <div className="flex justify-between font-semibold"><span>Balance owed</span><Amount value={data.closing_balance} /></div>
        </div>
      )}
    </Section>
  );
}


/** Every supplier is a ledger: billed, paid (with WHT withheld), returned, and what is still owed. */
function SupplierLedgers({ onPay }: { onPay: (supplierId: string) => void }) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [history, setHistory] = useState<Dict | null>(null);
  const { data, isLoading, error } = useBooks<Dict>(["supplier-ledgers", search, status], "/ledgers/suppliers", { search: search || undefined, status: status || undefined });
  const rows: Dict[] = data?.rows ?? [];
  const label: Record<string, string> = { OWED: "We owe", PAID: "Settled", IN_CREDIT: "They owe us" };
  return (
    <Section title="Supplier ledgers" actions={<CsvButton filename="supplier-ledgers.csv" rows={rows} />}>
      <div className="mb-3 flex flex-wrap gap-2">
        <Input className="h-9 max-w-xs" placeholder="Supplier" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="h-9 rounded-md border bg-background px-2 text-sm" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="OWED">We owe</option><option value="PAID">Settled</option><option value="IN_CREDIT">They owe us</option><option value="">All suppliers</option>
        </select>
      </div>
      {isLoading && <Loading />}<ErrorNote error={error} />
      <DetailSheet size="wide" open={!!history} onOpenChange={(o) => !o && setHistory(null)} title={history ? `${history.name} · purchases before go-live` : ""}
                   description="Hope's goods-received records for this supplier.">
        {history && <HopePurchases supplierId={history.id} />}
      </DetailSheet>
      {data && (rows.length === 0 ? <Empty>No suppliers match. Supplier bills from the pharmacy and Purchases appear here.</Empty> : (
        <Table>
          <TableHeader><TableRow>
            <TableHead>Supplier</TableHead><TableHead className="text-right">Billed</TableHead><TableHead className="text-right">Paid</TableHead>
            <TableHead className="text-right">WHT</TableHead><TableHead className="text-right">Returned</TableHead><TableHead className="text-right">Balance</TableHead><TableHead>Status</TableHead>
            <TableHead className="text-right">Bought before go-live (Hope)</TableHead><TableHead />
          </TableRow></TableHeader>
          <TableBody>{rows.map((r) => (
            <TableRow key={r.id}>
              <TableCell><DrillLink to={{ type: "supplier", id: r.id, label: r.name }}>{r.name}</DrillLink><span className="block text-xs text-muted-foreground">{r.bills} bill(s){r.last_activity ? ` · last ${fmtDate(r.last_activity)}` : ""}</span></TableCell>
              <TableCell className="text-right"><Amount value={r.billed} /></TableCell><TableCell className="text-right"><Amount value={r.paid} blankZero /></TableCell>
              <TableCell className="text-right"><Amount value={r.wht} blankZero /></TableCell><TableCell className="text-right"><Amount value={r.returned} blankZero /></TableCell>
              <TableCell className={`text-right font-semibold ${r.status === "OWED" ? "text-red-600" : ""}`}><Amount value={r.balance} /></TableCell>
              <TableCell className="text-xs">{label[r.status]}</TableCell>
              <TableCell className="text-right">{Number(r.hope_purchased) > 0 ? (
                <button className="underline-offset-2 hover:underline" onClick={() => setHistory(r)}><Amount value={r.hope_purchased} /><span className="block text-xs text-muted-foreground">{r.hope_grns} deliveries</span></button>
              ) : "—"}</TableCell>
              <TableCell>{r.status === "OWED" && <Button size="sm" className="h-7 text-xs" onClick={() => onPay(r.id)}>Pay</Button>}</TableCell>
            </TableRow>
          ))}</TableBody>
        </Table>
      ))}
    </Section>
  );
}


/** Hope's goods-received records (2016-2026): what was bought from whom, on which supplier invoice. Royan's Sage paid
 *  suppliers from the cash book without a purchases journal, so this is the purchase history before go-live. */
function HopePurchases({ supplierId }: { supplierId?: string }) {
  const [range, setRange] = useState({ from: "2025-01-01", to: today() });
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const { data, isLoading, error } = useBooks<Dict>(["hope-purchases", range, search, supplierId], "/hope/purchases",
    { ...range, search: search || undefined, supplier_id: supplierId });
  const { data: po } = useBooks<Dict>(["hope-purchase", open], `/hope/purchases/${open}`, undefined, open != null);
  const rows: Dict[] = data?.rows ?? [];
  return (
    <Section title={<>Purchase history (Hope) <span className="text-sm font-normal text-muted-foreground">· {num(data?.count)} deliveries · {naira(data?.value)} in this period</span></>}
             actions={<CsvButton filename="hope-purchases.csv" rows={rows} />}>
      <p className="mb-3 text-xs text-muted-foreground">Goods received in Hope, 2016 to April 2026. Royan's Sage paid suppliers straight from the cash book, so purchases by supplier before go-live live here, not in the purchases journal. From go-live, supplier bills are entered under Bills.</p>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
        {!supplierId && <Input className="h-9 w-64" placeholder="Supplier, invoice, PO or GRN" value={search} onChange={(e) => setSearch(e.target.value)} />}
      </div>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (rows.length === 0 ? <Empty>No deliveries in this period.</Empty> : (
        <Table>
          <TableHeader><TableRow><TableHead>Received</TableHead><TableHead>Supplier</TableHead><TableHead>Supplier invoice</TableHead><TableHead>PO / GRN</TableHead>
            <TableHead>Store</TableHead><TableHead className="text-right">Items</TableHead><TableHead className="text-right">Amount</TableHead></TableRow></TableHeader>
          <TableBody>{rows.map((r) => (
            <TableRow key={r.hope_id} className="cursor-pointer hover:bg-muted/50" onClick={() => setOpen(r.hope_id)}>
              <TableCell className="whitespace-nowrap">{fmtDate(r.received_date ?? r.order_date)}</TableCell>
              <TableCell className="max-w-[200px] truncate">{r.supplier_name}</TableCell>
              <TableCell className="font-mono text-xs">{r.supplier_invoice ?? "—"}</TableCell>
              <TableCell className="font-mono text-xs">{r.po_number}{r.grn_number ? ` · ${r.grn_number}` : ""}</TableCell>
              <TableCell className="text-xs">{r.store ?? "—"}</TableCell>
              <TableCell className="text-right">{r.items}</TableCell>
              <TableCell className="text-right"><Amount value={r.net_amount} /></TableCell>
            </TableRow>
          ))}</TableBody>
        </Table>
      ))}
      <DetailSheet size="wide" open={open != null} onOpenChange={(o) => !o && setOpen(null)} title={po ? `${po.po_number} · ${po.supplier_name}` : "Purchase"}
                   description={po ? `Supplier invoice ${po.supplier_invoice ?? "—"} · received ${fmtDate(po.received_date)} · ${po.status ?? ""}` : undefined}>
        {po && (
          <Table>
            <TableHeader><TableRow><TableHead>Item</TableHead><TableHead>Batch</TableHead><TableHead>Expiry</TableHead><TableHead className="text-right">Qty</TableHead>
              <TableHead className="text-right">Free</TableHead><TableHead className="text-right">Unit price</TableHead><TableHead className="text-right">Amount</TableHead></TableRow></TableHeader>
            <TableBody>
              {(po.lines ?? []).map((l: Dict) => (
                <TableRow key={l.hope_id}><TableCell className="max-w-[240px] truncate">{l.product_name}</TableCell><TableCell className="font-mono text-xs">{l.batch_number ?? "—"}</TableCell>
                  <TableCell>{l.expiry_date ? fmtDate(l.expiry_date) : "—"}</TableCell><TableCell className="text-right">{num(l.quantity)}</TableCell>
                  <TableCell className="text-right">{Number(l.free_quantity) ? num(l.free_quantity) : ""}</TableCell>
                  <TableCell className="text-right"><Amount value={l.unit_price} /></TableCell><TableCell className="text-right"><Amount value={l.amount} /></TableCell></TableRow>
              ))}
              <TableRow className="font-semibold"><TableCell colSpan={6}>Total{Number(po.discount) ? ` (discount ${naira(po.discount)})` : ""}</TableCell><TableCell className="text-right"><Amount value={po.net_amount} /></TableCell></TableRow>
            </TableBody>
          </Table>
        )}
      </DetailSheet>
    </Section>
  );
}
