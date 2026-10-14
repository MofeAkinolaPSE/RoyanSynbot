import { Fragment, useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Amount, CsvButton } from "@/components/books/kit";
import { Dict, fmtDate } from "@/lib/books-api";

type Block = { id: string; code: string; name: string; rows: Dict[]; opening: number; debit: number; credit: number; ending: number; lines: number };

/** Split Sage's flat rows into one block per account / customer (Beginning Balance … Ending Balance). */
function toBlocks(rows: Dict[]): Block[] {
  const out: Block[] = [];
  let cur: Block | null = null;
  for (const r of rows) {
    if (!cur || (r.kind === "BEGIN" && r.party_id !== cur.id)) {
      cur = { id: String(r.party_id), code: r.account_id, name: r.account_description, rows: [], opening: Number(r.balance ?? 0),
              debit: 0, credit: 0, ending: 0, lines: 0 };
      out.push(cur);
    }
    cur.rows.push(r);
    if (r.kind === "LINE") { cur.debit += Number(r.debit ?? 0); cur.credit += Number(r.credit ?? 0); cur.lines += 1; }
    if (r.kind === "END") cur.ending = Number(r.balance ?? 0);
  }
  return out;
}

/** Sage 50's General Ledger / Customer Ledgers layout (template: financemeetings/Gl.xlsx), one foldable block per
 *  account or customer. Folded, a block is one line: ID, name, opening, the period's debits and credits, entries,
 *  ending balance. Opened, it is Sage's detail: month by month Beginning Balance, transactions, Current Period Change,
 *  then Ending Balance (the balance only on the beginning and ending rows, as Sage prints it). The CSV carries Sage's
 *  columns on every row, whatever is folded. */
export function SageLedgerTable({ rows, idLabel = "Account ID", nameLabel = "Account Description", drLabel = "Debit Amt", crLabel = "Credit Amt",
  filename, onLine, startOpen = false }: {
  rows: Dict[]; idLabel?: string; nameLabel?: string; drLabel?: string; crLabel?: string; filename: string;
  onLine?: (r: Dict) => void; startOpen?: boolean; max?: number;
}) {
  const columns = [
    { key: "account_id", label: idLabel }, { key: "account_description", label: nameLabel }, { key: "date", label: "Date" },
    { key: "reference", label: "Reference" }, { key: "jrnl", label: "Jrnl" }, { key: "trans_description", label: "Trans Description" },
    { key: "debit", label: drLabel }, { key: "credit", label: crLabel }, { key: "balance", label: "Balance" },
  ];
  const blocks = useMemo(() => toBlocks(rows), [rows]);
  // a single account / customer opens straight away; a full ledger starts folded
  const [open, setOpen] = useState<Set<string>>(() => new Set(startOpen || blocks.length === 1 ? blocks.map((b) => b.id) : []));
  const toggle = (id: string) => setOpen((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">{blocks.length} {idLabel.startsWith("Account") ? "accounts" : "ledgers"} · click one to open it</span>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setOpen(new Set(blocks.map((b) => b.id)))}>Expand all</Button>
          <Button size="sm" variant="outline" onClick={() => setOpen(new Set())}>Collapse all</Button>
          <CsvButton filename={filename} rows={rows} columns={columns} />
        </div>
      </div>
      {/* all nine Sage columns, sized to fit the page so Debit, Credit and Balance are always in view; the account heading
          folds its block */}
      <Table className="table-fixed text-xs">
        <colgroup>
          <col className="w-7" /><col className="w-[70px]" /><col className="w-[150px]" /><col className="w-[86px]" /><col className="w-[96px]" />
          <col className="w-[46px]" /><col /><col className="w-[118px]" /><col className="w-[118px]" /><col className="w-[128px]" />
        </colgroup>
        <TableHeader><TableRow>
          <TableHead />
          {columns.map((c) => <TableHead key={c.key} className={["debit", "credit", "balance"].includes(c.key) ? "text-right" : ""}>{c.label}</TableHead>)}
        </TableRow></TableHeader>
        <TableBody>
          {blocks.map((b) => {
            const isOpen = open.has(b.id);
            return (
              <Fragment key={b.id}>
                {/* the account / customer heading: always shown, folds and unfolds the detail */}
                <TableRow className="cursor-pointer border-t-2 bg-muted/40 hover:bg-muted/60" onClick={() => toggle(b.id)}>
                  <TableCell>{isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</TableCell>
                  <TableCell className="font-mono font-semibold">{b.code}</TableCell>
                  <TableCell className="font-semibold">{b.name}</TableCell>
                  <TableCell colSpan={3} />
                  <TableCell className="text-muted-foreground">{isOpen ? "" : <>Opening <Amount value={b.opening} /> · {b.lines.toLocaleString()} entr{b.lines === 1 ? "y" : "ies"}</>}</TableCell>
                  <TableCell className="whitespace-nowrap text-right">{!isOpen && b.debit ? <Amount value={b.debit} /> : ""}</TableCell>
                  <TableCell className="whitespace-nowrap text-right">{!isOpen && b.credit ? <Amount value={b.credit} /> : ""}</TableCell>
                  <TableCell className="whitespace-nowrap text-right">{!isOpen ? <Amount value={b.ending} bold /> : ""}</TableCell>
                </TableRow>
                {isOpen && b.rows.map((r, i) => {
                  const begin = r.kind === "BEGIN", line = r.kind === "LINE", change = r.kind === "CHANGE", end = r.kind === "END";
                  return (
                    <TableRow key={i} onClick={line && onLine && r.journal_id ? () => onLine(r) : undefined}
                              className={begin ? "bg-muted/10" : end ? "font-semibold" : change ? "text-muted-foreground" : line && onLine && r.journal_id ? "cursor-pointer hover:bg-muted/50" : ""}>
                      <TableCell />
                      <TableCell className="font-mono text-muted-foreground">{b.code}</TableCell>
                      <TableCell className="truncate text-muted-foreground" title={b.name}>{b.name}</TableCell>
                      <TableCell className="whitespace-nowrap">{r.date ? fmtDate(r.date) : ""}</TableCell>
                      <TableCell className="truncate font-mono" title={r.reference}>{r.reference}</TableCell>
                      <TableCell>{r.jrnl}</TableCell>
                      <TableCell className={begin || change || end ? "italic" : ""}>{r.trans_description}</TableCell>
                      <TableCell className="whitespace-nowrap text-right">{r.debit != null ? <Amount value={r.debit} /> : ""}</TableCell>
                      <TableCell className="whitespace-nowrap text-right">{r.credit != null ? <Amount value={r.credit} /> : ""}</TableCell>
                      <TableCell className="whitespace-nowrap text-right">{r.balance != null ? <Amount value={r.balance} bold={end} /> : ""}</TableCell>
                    </TableRow>
                  );
                })}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

/** When a range has no entries: what the books hold and where the gap is, with a jump to data. */
export function LedgerCoverageNote({ onRange }: { onRange: (from: string, to: string) => void }) {
  const today = new Date().toISOString().slice(0, 10);
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm dark:border-amber-500/40 dark:bg-amber-500/10">
      <p className="font-medium">No entries in these dates.</p>
      <p className="mt-1 text-xs">
        The ledger holds Royan's Sage history from 2009 to 31 Dec 2024, and Roy Books from go-live (10 Oct 2026). 1 Jan 2025 to 9 Oct 2026
        is filled when finance uploads its reconciled trial balance or Sage export (Setup › Migration; see Setup › What data we have).
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => onRange("2024-12-01", "2024-12-31")}>Dec 2024 (Sage)</Button>
        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => onRange("2024-01-01", "2024-12-31")}>2024 (Sage)</Button>
        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => onRange("2026-10-01", today)}>Since go-live</Button>
      </div>
    </div>
  );
}
