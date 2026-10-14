/**
 * Monthly payroll run: HR record -> draft -> approved -> paid, each step landing in Roy Books
 * (backend/src/services/hr_hub.py payroll_*, fin/integrations.py PAYROLL / PAYROLL_PAYMENT).
 *
 * The draft is a starting point HR completes: gross from the person's HR record, overtime
 * from their approved timesheets. PAYE and pension depend on reliefs only HR knows, so they
 * start at 0 and are entered per person before approval.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BookOpenCheck, CheckCircle2, Loader2, Pencil, Trash2, Wallet, WandSparkles } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { DetailSheet } from "@/components/workspace/DetailSheet";
import { KpiStrip } from "@/components/workspace/KpiStrip";
import { useAuth } from "@/components/AuthProvider";
import { api } from "@/lib/api-client";
import { Dict, Empty } from "@/components/staff/ws-kit";
import { naira } from "@/components/hr/hr-panels";

const lastMonth = () => { const d = new Date(); d.setDate(0); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };
const monthLabel = (p: string) => new Date(`${p}-01T12:00:00`).toLocaleDateString("en-GB", { month: "long", year: "numeric" });

const STATUS_TONE: Record<string, string> = {
  draft: "bg-muted text-foreground", approved: "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300",
  paid: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
};
const BOOKS_TONE: Record<string, string> = { POSTED: "text-emerald-600", SKIPPED: "text-muted-foreground", FAILED: "text-red-600" };

function BooksCell({ b, label }: { b?: Dict | null; label: string }) {
  if (!b) return null;
  return <div className={`text-xs ${BOOKS_TONE[b.status] ?? ""}`} title={b.message ?? ""}>{label}: {b.status === "POSTED" ? "in the books" : b.status.toLowerCase()}</div>;
}

export function PayrollRunPanel() {
  const { roles } = useAuth();
  const canPrepare = roles.some((r) => ["admin", "hr"].includes(r));
  const canApprove = roles.some((r) => ["admin", "hr", "management"].includes(r));
  const canPay = roles.some((r) => ["admin", "hr", "finance"].includes(r));
  const [period, setPeriod] = useState(lastMonth());
  const q = useQuery({ queryKey: ["hr", "payroll-run", period], queryFn: () => api.hrHub.payrollRun(period) });
  const [busy, setBusy] = useState("");
  const [edit, setEdit] = useState<Dict | null>(null);
  const [pay, setPay] = useState<{ ids: string[] | "all" } | null>(null);
  const d = q.data;
  const rows: Dict[] = d?.records ?? [];

  const run = async (key: string, fn: () => Promise<any>, ok: (r: any) => string) => {
    setBusy(key);
    try { const r = await fn(); toast.success(ok(r)); q.refetch(); }
    catch (e: any) { toast.error(e?.message || "That did not work"); }
    finally { setBusy(""); }
  };
  // one record answers {status, message}; a whole month answers {STATUS: count}
  const booksNote = (r: any) => {
    const b = r?.books;
    if (!b) return "";
    if (!b.status) {
      if (b.FAILED) return ` - ${b.FAILED} could not post to Roy Books (see Close & Controls)`;
      return b.POSTED ? " - posted to Roy Books" : b.SKIPPED ? " - Roy Books not live yet, it will post at go-live" : "";
    }
    return b.status === "POSTED" ? " - posted to Roy Books" : b.status === "SKIPPED" ? " - Roy Books not live yet, it will post at go-live"
      : b.status === "FAILED" ? ` - not in the books: ${b.message}` : "";
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1"><Label className="text-xs">Payroll month</Label>
          <Input type="month" className="h-9 w-44" value={period} max={new Date().toISOString().slice(0, 7)} onChange={(e) => e.target.value && setPeriod(e.target.value)} /></div>
        <div className="ml-auto flex flex-wrap gap-2">
          {canPrepare && (
            <Button size="sm" variant="outline" disabled={!!busy} onClick={() => run("prep", () => api.hrHub.preparePayroll(period),
              (r) => r.prepared ? `${r.prepared} draft(s) prepared for ${monthLabel(period)}` : "Everyone with pay already has a record")}>
              {busy === "prep" ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <WandSparkles className="mr-1.5 h-4 w-4" />}Prepare from HR records
            </Button>)}
          {canApprove && (d?.totals?.draft ?? 0) > 0 && (
            <Button size="sm" disabled={!!busy} onClick={() => run("approve", () => api.hrHub.payrollBulk("approve", { period }),
              (r) => `${r.done} approved${booksNote(r)}`)}>
              {busy === "approve" ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-1.5 h-4 w-4" />}Approve all drafts
            </Button>)}
          {canPay && (d?.totals?.approved ?? 0) > 0 && (
            <Button size="sm" variant="secondary" disabled={!!busy} onClick={() => setPay({ ids: "all" })}>
              <Wallet className="mr-1.5 h-4 w-4" />Mark approved as paid
            </Button>)}
        </div>
      </div>

      {d && !d.books_live && (
        <div className="rounded-lg border border-amber-300/60 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
          <BookOpenCheck className="mr-1.5 inline h-3.5 w-3.5" />
          Roy Books is not live yet (no cut-over date), so approved and paid payroll is recorded here but not yet in the ledger.
          When Finance sets the cut-over and runs the go-live backfill, anything dated on or after it is posted automatically.
        </div>
      )}

      <KpiStrip items={[
        { label: "Salary cost", value: naira(d?.totals?.gross + d?.totals?.overtime), sub: d ? `gross ${naira(d.totals.gross)} + overtime ${naira(d.totals.overtime)}` : undefined },
        { label: "Net pay", value: naira(d?.totals?.net), sub: d ? `${rows.length} staff` : undefined },
        { label: "PAYE + pension", value: naira((d?.totals?.tax ?? 0) + (d?.totals?.pension ?? 0)), sub: "owed to the State IRS and the PFAs" },
        { label: "Status", value: d ? `${d.totals.paid} paid` : "–", sub: d ? `${d.totals.draft} draft · ${d.totals.approved} approved` : undefined,
          tone: !rows.length ? "default" : d.totals.draft + d.totals.approved > 0 ? "warning" : "success" },
      ]} />

      {d && (d.not_prepared > 0 || d.staff_without_pay > 0) && (
        <p className="text-xs text-muted-foreground">
          {d.not_prepared > 0 && <>{d.not_prepared} active staff with pay have no record for {monthLabel(period)} yet. </>}
          {d.staff_without_pay > 0 && <>{d.staff_without_pay} active staff have no monthly gross on their HR record, so payroll skips them - set it under Directory.</>}
        </p>
      )}

      {q.isLoading ? <Loader2 className="mx-auto h-5 w-5 animate-spin" /> : rows.length === 0 ? (
        <Empty>No payroll for {monthLabel(period)} yet.{canPrepare ? " Prepare it from the HR records." : ""}</Empty>
      ) : (
        <div className="overflow-x-auto rounded-xl border">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-left text-xs text-muted-foreground">
              <tr>{["Staff", "Gross", "Overtime", "Allowances", "PAYE", "Pension", "Other", "Net", "Status", ""].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((r) => (
                <tr key={r.id} className="align-top">
                  <td className="px-3 py-2"><div className="font-medium">{r.full_name}</div>
                    <div className="text-xs text-muted-foreground">{r.staff_number}{r.designation ? ` · ${r.designation}` : ""}</div></td>
                  <td className="px-3 py-2 tabular-nums">{naira(r.gross_salary)}</td>
                  <td className="px-3 py-2 tabular-nums">{Number(r.overtime_hours) ? <>{naira(Number(r.overtime_hours) * Number(r.overtime_rate))}<div className="text-xs text-muted-foreground">{Number(r.overtime_hours)}h</div></> : "–"}</td>
                  <td className="px-3 py-2 tabular-nums">{Number(r.allowances) ? naira(r.allowances) : "–"}</td>
                  <td className="px-3 py-2 tabular-nums">{Number(r.tax) ? naira(r.tax) : <span className="text-amber-600" title="PAYE not entered">0</span>}</td>
                  <td className="px-3 py-2 tabular-nums">{Number(r.pension) ? naira(r.pension) : <span className="text-amber-600" title="Pension not entered">0</span>}</td>
                  <td className="px-3 py-2 tabular-nums">{Number(r.deductions) ? naira(r.deductions) : "–"}</td>
                  <td className="px-3 py-2 font-semibold tabular-nums">{naira(r.net_salary)}</td>
                  <td className="px-3 py-2">
                    <span className={`rounded-md px-1.5 py-0.5 text-xs font-medium ${STATUS_TONE[r.status] ?? "bg-muted"}`}>{r.status}</span>
                    <BooksCell b={r.books_cost} label="Cost" /><BooksCell b={r.books_payment} label="Payment" />
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">
                    {r.status === "draft" && canPrepare && <Button size="icon" variant="ghost" className="h-7 w-7" title="Edit" onClick={() => setEdit({ ...r })}><Pencil className="h-3.5 w-3.5" /></Button>}
                    {r.status === "draft" && canApprove && <Button size="sm" variant="outline" className="h-7 px-2 text-xs" disabled={!!busy}
                      onClick={() => run(r.id, () => api.hrHub.payrollAction(r.id, "approve"), (x) => `Approved${booksNote(x)}`)}>Approve</Button>}
                    {r.status === "approved" && canPay && <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={() => setPay({ ids: [r.id] })}>Paid</Button>}
                    {r.status === "draft" && canPrepare && <Button size="icon" variant="ghost" className="h-7 w-7 text-muted-foreground" title="Remove draft" disabled={!!busy}
                      onClick={() => run(r.id, () => api.hrHub.payrollAction(r.id, "delete"), () => "Draft removed")}><Trash2 className="h-3.5 w-3.5" /></Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        Approving books the month's salary cost (Salaries Expense) against net pay, PAYE and pension owed; paying clears net pay against the bank.
        Posting rules: <Link className="text-primary hover:underline" to="/finance/books/setup">Roy Books › Setup</Link>. Anything that could not post is listed in <Link className="text-primary hover:underline" to="/finance/books/close">Close &amp; Controls</Link>.
      </p>

      <EditPayrollSheet rec={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); q.refetch(); }} />
      <PaySheet open={!!pay} banks={d?.banks ?? []} count={pay?.ids === "all" ? d?.totals?.approved ?? 0 : 1}
        onOpenChange={(v) => !v && setPay(null)}
        onPay={async (payload) => {
          if (!pay) return;
          await run("pay", () => pay.ids === "all" ? api.hrHub.payrollBulk("pay", { period, ...payload }) : api.hrHub.payrollAction(pay.ids[0], "pay", payload),
            (r) => `${r.done ?? 1} marked paid${booksNote(r)}`);
          setPay(null);
        }} />
    </div>
  );
}

function EditPayrollSheet({ rec, onClose, onSaved }: { rec: Dict | null; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<Dict>({});
  const [busy, setBusy] = useState(false);
  const r = rec ?? {};
  const v = (k: string) => (f[k] ?? r[k] ?? "") as string;
  const net = ["gross_salary", "allowances"].reduce((a, k) => a + Number(v(k) || 0), 0) + Number(v("overtime_hours") || 0) * Number(v("overtime_rate") || 0)
    - ["tax", "pension", "deductions"].reduce((a, k) => a + Number(v(k) || 0), 0);
  const save = async () => {
    setBusy(true);
    try {
      const payload: Dict = {};
      for (const k of ["gross_salary", "overtime_hours", "overtime_rate", "allowances", "tax", "pension", "deductions"]) if (k in f) payload[k] = Number(f[k] || 0);
      if ("notes" in f) payload.notes = f.notes;
      await api.hrHub.updatePayroll(r.id, payload);
      toast.success("Payroll record saved"); setF({}); onSaved();
    } catch (e: any) { toast.error(e?.message || "Could not save"); } finally { setBusy(false); }
  };
  const field = (k: string, label: string) => (
    <div className="space-y-1"><Label className="text-xs">{label}</Label>
      <Input type="number" min={0} step="0.01" value={v(k)} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></div>);
  return (
    <DetailSheet open={!!rec} onOpenChange={(o) => { if (!o) { setF({}); onClose(); } }} icon={Pencil} title={r.full_name ?? "Payroll"}
      description="Enter PAYE, pension and any allowances or deductions before approving."
      footer={<Button className="w-full" disabled={busy || net < 0} onClick={save}>{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save · net {naira(net)}</Button>}>
      <div className="grid grid-cols-2 gap-3">
        {field("gross_salary", "Gross salary")}{field("allowances", "Allowances")}
        {field("overtime_hours", "Overtime hours")}{field("overtime_rate", "Overtime rate / hour")}
        {field("tax", "PAYE")}{field("pension", "Pension (employee)")}
        {field("deductions", "Other deductions (loans, advances)")}
      </div>
      <div className="space-y-1"><Label className="text-xs">Notes</Label>
        <Textarea rows={3} value={v("notes")} onChange={(e) => setF({ ...f, notes: e.target.value })} /></div>
      {net < 0 && <p className="text-xs text-red-600">Deductions are more than the pay.</p>}
    </DetailSheet>
  );
}

function PaySheet({ open, onOpenChange, banks, count, onPay }: {
  open: boolean; onOpenChange: (v: boolean) => void; banks: Dict[]; count: number; onPay: (p: Dict) => Promise<void>;
}) {
  const [bank, setBank] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [method, setMethod] = useState("bank_transfer");
  const [busy, setBusy] = useState(false);
  return (
    <DetailSheet open={open} onOpenChange={onOpenChange} icon={Wallet} title={`Mark ${count} as paid`}
      description="Record how and when salaries left the bank. Roy Books clears net pay against this account."
      footer={<Button className="w-full" disabled={busy || !bank} onClick={async () => { setBusy(true); try { await onPay({ bank_account_id: bank, payment_date: date, payment_method: method }); } finally { setBusy(false); } }}>
        {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Mark paid</Button>}>
      <div className="space-y-1"><Label>Paid from</Label>
        <Select value={bank || undefined} onValueChange={setBank}><SelectTrigger><SelectValue placeholder="Bank or cash account" /></SelectTrigger>
          <SelectContent>{banks.map((b) => <SelectItem key={b.id} value={b.id}>{b.name}</SelectItem>)}</SelectContent></Select></div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1"><Label>Payment date</Label><Input type="date" value={date} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setDate(e.target.value)} /></div>
        <div className="space-y-1"><Label>Method</Label>
          <Select value={method} onValueChange={setMethod}><SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="bank_transfer">Bank transfer</SelectItem><SelectItem value="cash">Cash</SelectItem><SelectItem value="cheque">Cheque</SelectItem></SelectContent></Select></div>
      </div>
      {count > 1 && <Badge variant="outline">Applies to every approved record for the month</Badge>}
    </DetailSheet>
  );
}
