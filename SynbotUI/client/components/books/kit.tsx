/**
 * Roy Books shared UI kit: money display, status badges, pickers, and the
 * drill-down sheets that give every figure its lineage
 * (statement -> account -> ledger lines -> journal -> source document).
 */
import { ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowUpRight, Download, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DetailSheet } from "@/components/workspace/DetailSheet";
import { books, BooksError, Dict, downloadCsv, fmtDate, naira, num, today } from "@/lib/books-api";
import { DrillTarget, sourceTarget, useDrill } from "./drill-context";

/** A figure or reference that opens the record behind it (financial lineage). */
export function DrillLink({ to, children, className = "" }: { to: DrillTarget | null; children: ReactNode; className?: string }) {
  const drill = useDrill();
  if (!to || !to.id || !drill) return <>{children}</>;
  return (
    <button type="button" className={`text-left text-primary underline-offset-2 hover:underline ${className}`}
            onClick={(e) => { e.stopPropagation(); drill.open(to); }}>
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Queries & errors
// ---------------------------------------------------------------------------

export function useBooks<T = any>(key: unknown[], path: string, params?: Dict, enabled = true) {
  return useQuery<T>({
    queryKey: ["books", path, ...key, params],
    queryFn: () => books.get<T>(path, params),
    enabled,
    staleTime: 0,
  });
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** Run a mutation with a toast; returns the result or undefined on failure. */
export async function act<T>(fn: () => Promise<T>, ok?: string): Promise<T | undefined> {
  try {
    const r = await fn();
    if (ok) toast.success(ok);
    return r;
  } catch (e) {
    const err = e as BooksError;
    toast.error(err.message ?? "Something went wrong", { description: err.code });
    return undefined;
  }
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {errorMessage(error)}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin" /> {label}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Display
// ---------------------------------------------------------------------------

export function Amount({ value, className = "", bold = false, blankZero = false }: { value: any; className?: string; bold?: boolean; blankZero?: boolean }) {
  const n = Number(value);
  return (
    <span className={`tabular-nums whitespace-nowrap ${n < 0 ? "text-red-600 dark:text-red-400" : ""} ${bold ? "font-semibold" : ""} ${className}`}>
      {naira(value, { blankZero })}
    </span>
  );
}

const STATUS_TONE: Record<string, string> = {
  POSTED: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  PAID: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  RECONCILED: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  COMPLETED: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  LOADED: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  RETURNED: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  PASS: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  OPEN: "bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-300",
  ACTIVE: "bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-300",
  AVAILABLE: "bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-300",
  PARTIALLY_PAID: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  PARTIALLY_RETURNED: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  SUBMITTED: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  APPROVED: "bg-indigo-100 text-indigo-800 dark:bg-indigo-500/15 dark:text-indigo-300",
  STAGED: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  DRAFT: "bg-slate-100 text-slate-700 dark:bg-slate-500/15 dark:text-slate-300",
  FAIL: "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300",
  FAILED: "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300",
  VOID: "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300",
  REVERSED: "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300",
  REJECTED: "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300",
  RECALLED: "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300",
  CLOSED: "bg-slate-200 text-slate-700 dark:bg-slate-500/20 dark:text-slate-300",
  INACTIVE: "bg-slate-200 text-slate-700 dark:bg-slate-500/20 dark:text-slate-300",
};

export function StatusBadge({ status }: { status?: string }) {
  if (!status) return null;
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_TONE[status] ?? "bg-muted text-muted-foreground"}`}>
      {status.replace(/_/g, " ").toLowerCase()}
    </span>
  );
}

export function Section({ title, actions, children, className = "" }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <Card className={className}>
      {(title || actions) && (
        <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-3">
          {title ? <CardTitle className="text-base">{title}</CardTitle> : <span />}
          {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
        </CardHeader>
      )}
      <CardContent className={title || actions ? "" : "pt-6"}>{children}</CardContent>
    </Card>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "good" | "warn" | "bad" }) {
  const t = tone === "good" ? "text-emerald-700 dark:text-emerald-300" : tone === "warn" ? "text-amber-700 dark:text-amber-300" : tone === "bad" ? "text-red-700 dark:text-red-300" : "";
  return (
    <Card>
      <CardContent className="pt-4 pb-3">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className={`mt-1 whitespace-nowrap text-[clamp(0.9rem,1.05vw,1.125rem)] font-bold tabular-nums ${t}`}>{value}</div>
        {sub && <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>}
      </CardContent>
    </Card>
  );
}

/** A date box that keeps what is being typed and reports only a complete date. Browsers report "" while the year is
 *  half-typed (e.g. changing 2026 to 2023 key by key); passing that up made every page fall back to today. */
function DateBox({ value, onDate }: { value?: string; onDate: (d: string) => void }) {
  const [text, setText] = useState(value ?? "");
  useEffect(() => { setText(value ?? ""); }, [value]);
  const valid = (d: string) => /^\d{4}-\d{2}-\d{2}$/.test(d) && Number(d.slice(0, 4)) >= 2000 && Number(d.slice(0, 4)) <= 2100 && !isNaN(Date.parse(d));
  return (
    <Input type="date" className="h-9 w-40" value={text}
           onChange={(e) => { setText(e.target.value); if (valid(e.target.value)) onDate(e.target.value); }}
           onBlur={() => { if (!valid(text)) setText(value ?? ""); }} />
  );
}

export function DateRange({ from, to, onChange, single }: { from?: string; to: string; onChange: (f: string | undefined, t: string) => void; single?: boolean }) {
  return (
    <div className="flex flex-wrap items-end gap-2">
      {!single && (
        <div className="space-y-1">
          <Label className="text-xs">From</Label>
          <DateBox value={from} onDate={(d) => onChange(d, to)} />
        </div>
      )}
      <div className="space-y-1">
        <Label className="text-xs">{single ? "As of" : "To"}</Label>
        <DateBox value={to} onDate={(d) => onChange(from, d)} />
      </div>
      {!single && (
        <div className="flex gap-1 pb-0.5">
          {[["This month", 0], ["This year", 1], ["Last year", 2], ["All", 3]].map(([label, k]) => (
            <Button key={String(label)} type="button" size="sm" variant="ghost" className="h-8 px-2 text-xs" onClick={() => {
              const now = new Date(); const y = now.getFullYear(); const iso = (d: Date) => d.toISOString().slice(0, 10);
              const t = iso(now);
              if (k === 0) onChange(`${t.slice(0, 7)}-01`, t);
              else if (k === 1) onChange(`${y}-01-01`, t);
              else if (k === 2) onChange(`${y - 1}-01-01`, `${y - 1}-12-31`);
              else onChange("2010-01-01", t);
            }}>{label}</Button>
          ))}
        </div>
      )}
    </div>
  );
}

/** CSV of what is on screen. Without `columns` it exports the table(s) shown next to the button - the same headings,
 *  rows and text the user sees (amounts as plain numbers) - never the raw record with internal fields. With `columns`,
 *  those fields of `rows` (Report Center, statements: their own on-screen column list). */
export function CsvButton({ filename, rows, columns }: { filename: string; rows: Dict[] | undefined; columns?: { key: string; label: string }[] }) {
  const click = (e: { currentTarget: HTMLElement }) => {
    if (columns && rows) return downloadCsv(filename, rows, columns);
    const out = tablesNear(e.currentTarget);
    if (out.length) return downloadRows(filename, out);
    if (rows) downloadCsv(filename, rows, columns);
  };
  return (
    <Button size="sm" variant="outline" disabled={!rows?.length} onClick={click}>
      <Download className="mr-1.5 h-4 w-4" /> CSV
    </Button>
  );
}

/** The visible table(s) in the nearest container around `el`, as rows of cell text. */
export function tablesNear(el: HTMLElement): string[][] {
  let scope: HTMLElement | null = el.parentElement;
  while (scope && !scope.querySelector("table")) scope = scope.parentElement;
  if (!scope) return [];
  const cell = (c: Element) => {
    const t = ((c as HTMLElement).innerText ?? c.textContent ?? "").replace(/\s*\n+\s*/g, " · ").trim();
    // ₦1,234.56 -> 1234.56 and (₦1,234.56) or -₦1,234.56 -> -1234.56, so the sheet can add them up
    const m = t.match(/^(\()?([-−])?₦\s?([\d,]+(?:\.\d+)?)\)?$/);
    if (m) return `${m[1] || m[2] ? "-" : ""}${m[3].replace(/,/g, "")}`;
    return t;
  };
  const out: string[][] = [];
  scope.querySelectorAll("table").forEach((table, i) => {
    if (table.closest("[hidden]")) return;
    if (i > 0) out.push([]);
    table.querySelectorAll("tr").forEach((tr) => {
      const cells = Array.from(tr.querySelectorAll("th,td")).map(cell);
      if (cells.some((c) => c !== "")) out.push(cells);
    });
  });
  return out;
}

export function downloadRows(filename: string, rows: string[][]) {
  const esc = (s: string) => (/[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
  // the byte-order mark makes Excel read ₦ and accents as UTF-8
  const url = URL.createObjectURL(new Blob(["﻿" + rows.map((r) => r.map(esc).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

/** Marks a row that comes from the Sage years (listed beside Roy Books' own documents). */
export function SageTag() {
  return <span className="ml-1 rounded bg-muted px-1 py-0.5 align-middle text-xs font-medium text-muted-foreground">Sage</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">{children}</div>;
}

// ---------------------------------------------------------------------------
// Pickers (server search; the backend decides what is valid)
// ---------------------------------------------------------------------------

function useDebounced<T>(value: T, ms = 250) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function SearchPick<T extends Dict>({ path, label, value, onChange, render, sub, placeholder, params }: {
  path: string;
  label?: string;
  value: T | null;
  onChange: (v: T | null) => void;
  render: (v: T) => string;
  sub?: (v: T) => string | undefined;
  placeholder?: string;
  params?: Dict;
}) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const dq = useDebounced(q);
  const { data, isFetching } = useBooks<T[]>(["pick", dq], path, { search: dq, ...(params ?? {}) }, open);
  if (value) {
    return (
      <div className="space-y-1">
        {label && <Label className="text-xs">{label}</Label>}
        <div className="flex h-9 items-center justify-between rounded-md border bg-muted/40 px-3 text-sm">
          <span className="truncate">{render(value)}</span>
          <button type="button" className="text-muted-foreground hover:text-foreground" onClick={() => onChange(null)} aria-label="Clear">
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
    );
  }
  const items = Array.isArray(data) ? data : (data as any)?.items ?? [];
  return (
    <div className="relative space-y-1">
      {label && <Label className="text-xs">{label}</Label>}
      <Input className="h-9" placeholder={placeholder ?? "Search…"} value={q} onFocus={() => setOpen(true)}
             onBlur={() => setTimeout(() => setOpen(false), 150)} onChange={(e) => setQ(e.target.value)} />
      {open && (
        <div className="absolute z-50 mt-1 max-h-64 w-full overflow-auto rounded-md border bg-popover shadow-md">
          {isFetching && <div className="p-2 text-xs text-muted-foreground">Searching…</div>}
          {!isFetching && items.length === 0 && <div className="p-2 text-xs text-muted-foreground">No matches</div>}
          {items.map((it: T, i: number) => (
            <button key={i} type="button" className="block w-full px-3 py-1.5 text-left text-sm hover:bg-accent"
                    onMouseDown={(e) => { e.preventDefault(); onChange(it); setQ(""); setOpen(false); }}>
              <div className="truncate">{render(it)}</div>
              {sub && sub(it) && <div className="truncate text-xs text-muted-foreground">{sub(it)}</div>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export const AccountPick = (p: { label?: string; value: Dict | null; onChange: (v: Dict | null) => void; accountType?: string }) => (
  <SearchPick path="/accounts" label={p.label} value={p.value} onChange={p.onChange} placeholder="Code or name"
              params={{ account_type: p.accountType, include_inactive: false }}
              render={(a) => `${a.code} · ${a.name}`} sub={(a) => a.subtype?.replace(/_/g, " ").toLowerCase()} />
);
const PARTY_LABEL: Record<string, string> = { PATIENT: "patient", HMO: "HMO", CORPORATE: "corporate", OTHER: "other" };
/** Patients (name / MRN), HMOs and corporate debtors. A patient or HMO that has never owed anything has
 *  no AR account yet; choosing one opens it (POST /parties/ensure) so the form always gets a real id. */
export const CustomerPick = (p: { label?: string; value: Dict | null; onChange: (v: Dict | null) => void }) => {
  const choose = async (c: Dict | null) => {
    if (!c || c.id) return p.onChange(c);
    try {
      p.onChange(await books.post<Dict>("/parties/ensure", { patient_id: c.patient_id, hmo_id: c.hmo_id }));
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };
  return (
    <SearchPick path="/customers" label={p.label ?? "Patient / payer"} value={p.value} onChange={choose} placeholder="Patient name or MRN, HMO, company"
                render={(c) => c.name}
                sub={(c) => [PARTY_LABEL[c.party_type] ?? c.party_type, c.mrn ?? c.customer_code, Number(c.credit_limit) ? `limit ${naira(c.credit_limit)}` : "",
                             !c.id ? "no account yet" : ""].filter(Boolean).join(" · ")} />
  );
};
export const SupplierPick = (p: { label?: string; value: Dict | null; onChange: (v: Dict | null) => void }) => (
  <SearchPick path="/suppliers" label={p.label ?? "Supplier"} value={p.value} onChange={p.onChange} placeholder="Supplier name"
              render={(s) => s.name} sub={(s) => [s.supplier_code, s.payment_terms].filter(Boolean).join(" · ")} />
);
/** Drug / item search with the prefills the forms need: stock on hand, the batch to issue next
 *  (earliest expiry first) and the price this debtor last paid (else the pharmacy's list price). */
export const ProductPick = (p: { label?: string; value: Dict | null; onChange: (v: Dict | null) => void; customerId?: string | number }) => (
  <SearchPick path="/products" label={p.label} value={p.value} onChange={p.onChange} placeholder="SKU or product"
              params={{ customer_id: p.customerId || undefined, limit: 25 }}
              render={(x) => `${x.sku}${x.suggested_price ? ` · ${naira(x.suggested_price)}` : ""}`}
              sub={(x) => [x.name, `on hand ${num(x.on_hand)}`, x.next_batch ? `next batch ${x.next_batch}${x.next_expiry ? ` exp ${fmtDate(x.next_expiry)}` : ""}` : null,
                           x.customer_last_price ? `last charged ${naira(x.customer_last_price)} on ${fmtDate(x.customer_last_date)}` : null].filter(Boolean).join(" · ")} />
);
export const BatchPick = (p: { label?: string; value: Dict | null; onChange: (v: Dict | null) => void }) => (
  <SearchPick path="/inventory/batch-search" label={p.label ?? "Batch"} value={p.value} onChange={p.onChange} placeholder="Batch no. or SKU"
              render={(b) => `${b.sku} · ${b.batch_number}`} sub={(b) => `expires ${fmtDate(b.expiry_date)} · ${b.status.toLowerCase()}`} />
);

export function BankSelect({ value, onChange, label = "Bank / cash account", kinds }: { value: string; onChange: (v: string) => void; label?: string; kinds?: string[] }) {
  const { data } = useBooks<Dict[]>(["banks"], "/banking/accounts");
  const rows = (data ?? []).filter((b) => b.status === "ACTIVE" && (!kinds || kinds.includes(b.kind)));
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <select className="h-9 w-full rounded-md border bg-background px-2 text-sm" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Choose…</option>
        {rows.map((b) => (
          <option key={b.id} value={b.id}>{b.name} ({b.gl_code}) · {naira(b.book_balance)}</option>
        ))}
      </select>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Drill-down: journal & account activity sheets
// ---------------------------------------------------------------------------

const SOURCE_ROUTE: Record<string, (id: string) => string> = {
  SALES_INVOICE: (id) => `/finance/books/sales?invoice=${id}`,
  CUSTOMER_RECEIPT: (id) => `/finance/books/sales?receipt=${id}`,
  CREDIT_NOTE: (id) => `/finance/books/sales?creditnote=${id}`,
  CUSTOMER_REFUND: (id) => `/finance/books/sales?refund=${id}`,
  SUPPLIER_BILL: (id) => `/finance/books/purchases?bill=${id}`,
  SUPPLIER_PAYMENT: (id) => `/finance/books/purchases?payment=${id}`,
  DEBIT_NOTE: (id) => `/finance/books/purchases?debitnote=${id}`,
  CASH_VOUCHER: (id) => `/finance/books/banking?voucher=${id}`,
  STOCK_ADJUSTMENT: (id) => `/finance/books/stock?adjustment=${id}`,
  STOCK_LOAN: (id) => `/finance/books/stock?loan=${id}`,
  FIXED_ASSET: (id) => `/finance/books/assets?asset=${id}`,
  FIXED_ASSET_DISPOSAL: (id) => `/finance/books/assets?asset=${id}`,
};

export function sourceLink(sourceType?: string, sourceId?: string) {
  if (!sourceType || !sourceId) return null;
  const f = SOURCE_ROUTE[sourceType];
  return f ? f(sourceId) : null;
}

export function JournalSheet({ id, onClose }: { id: string | null; onClose: () => void }) {
  const drill = useDrill();
  useEffect(() => {
    if (id && drill) { drill.open({ type: "journal", id }); onClose(); }
  }, [id, drill]);
  const { data: j, isLoading, error } = useBooks<Dict>(["journal", id], `/journals/${id}`, undefined, !!id && !drill);
  const link = j ? sourceLink(j.source_type, j.source_id) : null;
  const src = j ? sourceTarget(j.source_type, j.source_id) : null;
  return (
    <DetailSheet size="wide" open={!!id && !drill} onOpenChange={(o) => !o && onClose()} title={j ? `Journal ${j.journal_number}` : "Journal"}
                 description={j?.description}>
      {isLoading && <Loading />}
      <ErrorNote error={error} />
      {j && (
        <div className="space-y-4 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={j.status} />
            <Badge variant="outline">{j.journal_type.toLowerCase()}</Badge>
            <span className="text-muted-foreground">{fmtDate(j.journal_date)} · {j.period_name}</span>
          </div>
          {j.source_ref && (
            <div className="rounded-md bg-muted/50 p-2 text-xs">
              Source: <strong>{j.source_type?.replace(/_/g, " ").toLowerCase()}</strong>{" "}
              <DrillLink to={src}>{j.source_ref}</DrillLink>
              {link && <Link className="ml-2 inline-flex items-center text-muted-foreground hover:underline" to={link}>go to page <ArrowUpRight className="h-3 w-3" /></Link>}
            </div>
          )}
          <Table>
            <TableHeader><TableRow><TableHead>Account</TableHead><TableHead className="text-right">Debit</TableHead><TableHead className="text-right">Credit</TableHead></TableRow></TableHeader>
            <TableBody>
              {j.lines.map((l: Dict) => (
                <TableRow key={l.id}>
                  <TableCell>
                    <div className="font-medium"><DrillLink to={{ type: "account", id: l.account_id, label: `${l.account_code} ${l.account_name}` }}>{l.account_code} · {l.account_name}</DrillLink></div>
                    {l.description && <div className="text-xs text-muted-foreground">{l.description}</div>}
                    <div className="flex flex-wrap gap-2 text-xs">
                      {l.customer_id && <DrillLink to={{ type: "customer", id: String(l.customer_id) }}>customer #{l.customer_id}</DrillLink>}
                      {l.supplier_id && <DrillLink to={{ type: "supplier", id: l.supplier_id }}>supplier</DrillLink>}
                      {l.product_sku && <DrillLink to={{ type: "product", id: l.product_sku }}>{l.product_sku}</DrillLink>}
                    </div>
                  </TableCell>
                  <TableCell className="text-right"><Amount value={l.debit} blankZero /></TableCell>
                  <TableCell className="text-right"><Amount value={l.credit} blankZero /></TableCell>
                </TableRow>
              ))}
              <TableRow className="font-semibold"><TableCell>Total</TableCell><TableCell className="text-right"><Amount value={j.total_debit} /></TableCell><TableCell className="text-right"><Amount value={j.total_credit} /></TableCell></TableRow>
            </TableBody>
          </Table>
          {j.audit?.length > 0 && (
            <div>
              <div className="mb-1 text-xs font-semibold uppercase text-muted-foreground">Audit trail</div>
              <ul className="space-y-1 text-xs">
                {j.audit.map((a: Dict, i: number) => (
                  <li key={i}><span className="text-muted-foreground">{new Date(a.created_at).toLocaleString("en-GB")}</span> · {a.action.replace(/_/g, " ").toLowerCase()} by {a.actor_name}{a.reason ? ` — ${a.reason}` : ""}</li>
                ))}
              </ul>
            </div>
          )}
          {j.reversal_of_id && <p className="text-xs text-muted-foreground">This journal reverses another journal.</p>}
        </div>
      )}
    </DetailSheet>
  );
}

export function AccountSheet({ account, from, to, onClose }: { account: Dict | null; from: string; to: string; onClose: () => void }) {
  const [journal, setJournal] = useState<string | null>(null);
  const [range, setRange] = useState({ from, to });
  useEffect(() => setRange({ from, to }), [from, to, account?.id]);
  const { data, isLoading, error } = useBooks<Dict>(["activity", account?.id, range], `/accounts/${account?.id}/activity`,
    { from: range.from, to: range.to, limit: 2000 }, !!account);
  const [search, setSearch] = useState("");
  const rows: Dict[] = (data?.rows ?? []).filter((r: Dict) => !search || `${r.source_ref ?? ""} ${r.journal_number} ${r.description ?? ""}`.toLowerCase().includes(search.toLowerCase()));
  return (
    <>
      <DetailSheet size="wide" open={!!account} onOpenChange={(o) => !o && onClose()} title={account ? `${account.code ?? ""} ${account.name ?? ""}` : ""}
                   description="Ledger lines behind this balance. Click a line to open its journal.">
        <div className="space-y-3 text-sm">
          <DateRange from={range.from} to={range.to} onChange={(f, t) => setRange({ from: f ?? range.from, to: t })} />
          {isLoading && <Loading />}
          <ErrorNote error={error} />
          {data && (
            <>
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div>Opening<div className="font-semibold"><Amount value={data.opening} /></div></div>
                <div>Movement<div className="font-semibold"><Amount value={Number(data.total_debit) - Number(data.total_credit)} /></div></div>
                <div>Closing<div className="font-semibold"><Amount value={data.closing} /></div></div>
              </div>
              {Number(data.count) === 0 && (
                <div className="rounded-md border bg-muted/40 px-3 py-2 text-xs">
                  {Number(data.all_entries) === 0 ? "This account has no entries in any year." : <>
                    No entries between these dates. The account has {Number(data.all_entries).toLocaleString()} entries from {fmtDate(data.first_activity)} to {fmtDate(data.last_activity)}.{" "}
                    <button className="font-medium text-primary underline" onClick={() => setRange({ from: `${String(data.last_activity).slice(0, 4)}-01-01`, to: String(data.last_activity).slice(0, 10) })}>
                      Show {String(data.last_activity).slice(0, 4)}
                    </button>{" · "}
                    <button className="font-medium text-primary underline" onClick={() => setRange({ from: String(data.first_activity).slice(0, 10), to: today() })}>Show all years</button>
                  </>}
                </div>
              )}
              <div className="flex items-center justify-between gap-2"><Input className="h-8 w-60 text-xs" placeholder="Search reference, description" value={search} onChange={(e) => setSearch(e.target.value)} />
                <CsvButton filename={`ledger-${account?.code}.csv`} rows={data.rows} /></div>
              <Table>
                <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Ref</TableHead><TableHead className="text-right">Dr</TableHead><TableHead className="text-right">Cr</TableHead><TableHead className="text-right">Balance</TableHead></TableRow></TableHeader>
                <TableBody>
                  {rows.map((r: Dict) => (
                    <TableRow key={r.line_id} className="cursor-pointer hover:bg-muted/50" onClick={() => setJournal(r.journal_id)}>
                      <TableCell className="whitespace-nowrap">{fmtDate(r.journal_date)}</TableCell>
                      <TableCell><div className="font-mono text-xs"><DrillLink to={sourceTarget(r.source_type, r.source_id)}>{r.source_ref || r.journal_number}</DrillLink></div><div className="max-w-[220px] truncate text-xs text-muted-foreground">{r.description}</div></TableCell>
                      <TableCell className="text-right"><Amount value={r.debit} blankZero /></TableCell>
                      <TableCell className="text-right"><Amount value={r.credit} blankZero /></TableCell>
                      <TableCell className="text-right"><Amount value={r.running_balance} /></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {data.count > data.rows.length && <p className="text-xs text-muted-foreground">Showing {data.rows.length} of {data.count} lines.</p>}
            </>
          )}
        </div>
      </DetailSheet>
      <JournalSheet id={journal} onClose={() => setJournal(null)} />
    </>
  );
}

// ---------------------------------------------------------------------------
// Line editor used by invoices, bills, vouchers, journals
// ---------------------------------------------------------------------------

export function useLines<T extends Dict>(blank: () => T, initial?: T[]) {
  const [lines, setLines] = useState<T[]>(initial ?? [blank()]);
  return {
    lines,
    setLines,
    add: () => setLines((l) => [...l, blank()]),
    remove: (i: number) => setLines((l) => (l.length > 1 ? l.filter((_, j) => j !== i) : l)),
    update: (i: number, patch: Partial<T>) => setLines((l) => l.map((x, j) => (j === i ? { ...x, ...patch } : x))),
    reset: () => setLines([blank()]),
  };
}
