import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, FileCheck2, Trash2, Upload } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { act, Amount, Empty, ErrorNote, Loading, Section, StatusBadge, useBooks } from "@/components/books/kit";
import { books, Dict, fmtDate } from "@/lib/books-api";
import { askConfirm } from "@/lib/ask";

/** Finance uploads each new set of Sage exports (2025, 2026 ...): upload -> check (a full dry run that must tie to the
 *  trial balance and balance sheet) -> load. Reports not uploaded come from the last set that loaded. */
export function SageUploads() {
  const qc = useQueryClient();
  const { data, isLoading, error, refetch } = useBooks<Dict>(["sage-uploads"], "/sage/uploads");
  const [files, setFiles] = useState<File[]>([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const upload = async () => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    if (note) fd.append("note", note);
    setBusy(true);
    const r = await act(() => books.upload<Dict>("/sage/uploads", fd), "Uploaded — run the check next");
    setBusy(false);
    if (r) { setFiles([]); setNote(""); refetch(); setOpen(r.id); }
  };
  return (
    <div className="space-y-4">
      <Section title="Upload Sage exports">
        <div className="space-y-3 text-sm">
          <p className="text-muted-foreground">
            Roy Books holds Royan's Sage history to <b>{fmtDate(data?.history_as_of) || "—"}</b>. When Finance has brought 2025 (or 2026) up to date in Sage,
            export the same reports as before (Excel) and upload them here — any file names. Nothing changes until the set is checked and loaded:
            the check rebuilds the whole history and must reproduce Sage's trial balance and balance sheet to the kobo.
          </p>
          <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
            <li>Needed every time (covering every year, not just the new one): General Ledger, Invoice Register, Cash Receipts Journal, GL Trial Balance and Balance Sheet at the year end, Chart of Accounts, Customer List, Vendor List.</li>
            <li>Useful: General Journal (cross-check), Cash Flow, GL Account Summary, Aged Receivables, Account Reconciliation, Items Sold to Customers, Vendor Ledgers.</li>
            <li>A report you don't upload is taken from the last set loaded. Once the books are live, Sage history is kept only up to the go-live date.</li>
          </ul>
          <div className="flex flex-wrap items-end gap-2">
            <Input type="file" multiple accept=".xlsx,.xlsm" className="h-9 w-80 text-xs" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
            <Input className="h-9 w-72" placeholder="Note (e.g. Sage exports to 31 Dec 2025)" value={note} onChange={(e) => setNote(e.target.value)} />
            <Button size="sm" disabled={busy || !files.length} onClick={upload}><Upload className="mr-1 h-4 w-4" />{busy ? "Uploading…" : `Upload ${files.length || ""} file${files.length === 1 ? "" : "s"}`}</Button>
          </div>
        </div>
      </Section>
      <Section title="Uploads">
        {isLoading && <Loading />}<ErrorNote error={error} />
        {data && (data.uploads.length === 0 ? <Empty>No uploads yet. The 2009–2024 history was loaded from the original exports.</Empty> : (
          <Table>
            <TableHeader><TableRow><TableHead>Uploaded</TableHead><TableHead>By</TableHead><TableHead>Note</TableHead><TableHead>Reports</TableHead><TableHead>As at</TableHead><TableHead>Ties</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
            <TableBody>{data.uploads.map((u: Dict) => (
              <TableRow key={u.id} className="cursor-pointer hover:bg-muted/50" onClick={() => setOpen(u.id)}>
                <TableCell className="whitespace-nowrap text-xs">{new Date(u.created_at).toLocaleString("en-GB")}</TableCell>
                <TableCell className="text-xs">{u.created_by}</TableCell><TableCell className="text-xs">{u.note}</TableCell>
                <TableCell className="text-xs">{Object.keys(u.files?.uploaded ?? {}).length}</TableCell>
                <TableCell className="whitespace-nowrap text-xs">{fmtDate(u.as_of)}</TableCell>
                <TableCell>{u.ties === "true" ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : u.ties === "false" ? <AlertTriangle className="h-4 w-4 text-amber-600" /> : ""}</TableCell>
                <TableCell><StatusBadge status={u.status} /></TableCell>
              </TableRow>
            ))}</TableBody>
          </Table>
        ))}
      </Section>
      {open && <UploadDetail id={open} onClose={() => setOpen(null)} onChanged={() => { refetch(); qc.invalidateQueries({ queryKey: ["books"] }); }} />}
    </div>
  );
}

function UploadDetail({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const { data: u, isLoading, error, refetch } = useBooks<Dict>(["sage-upload", id], `/sage/uploads/${id}`);
  const [busy, setBusy] = useState<string | null>(null);
  const step = async (what: "check" | "load") => {
    if (what === "load" && !await askConfirm("Load this set? Roy Books' Sage history, its customers and the opening balances are rebuilt from it.")) return;
    setBusy(what);
    const r = await act(() => books.post<Dict>(`/sage/uploads/${id}/${what}`, {}), what === "check" ? "Check finished" : "Loaded");
    setBusy(null);
    if (r) { refetch(); onChanged(); }
  };
  const discard = async () => {
    if (!await askConfirm("Discard this upload? The files are deleted.")) return;
    if (await act(() => books.del(`/sage/uploads/${id}`), "Discarded")) { onChanged(); onClose(); }
  };
  const res = u?.load_result ?? u?.check_result;
  const tie = res?.tie_out;
  return (
    <Section title="Upload" actions={<Button size="sm" variant="ghost" onClick={onClose}>Close</Button>}>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {u && (
        <div className="space-y-4 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={u.status} />
            {u.note && <span className="text-muted-foreground">{u.note}</span>}
            <div className="ml-auto flex gap-2">
              {u.status !== "LOADED" && <Button size="sm" variant="outline" disabled={!!busy || u.missing_required?.length > 0} onClick={() => step("check")}><FileCheck2 className="mr-1 h-4 w-4" />{busy === "check" ? "Checking… (a few minutes)" : "Check"}</Button>}
              {u.status === "CHECKED" && tie?.ties && <Button size="sm" disabled={!!busy} onClick={() => step("load")}>{busy === "load" ? "Loading…" : "Load into Roy Books"}</Button>}
              {u.status !== "LOADED" && <Button size="sm" variant="ghost" onClick={discard}><Trash2 className="h-4 w-4" /></Button>}
            </div>
          </div>
          {u.missing_required?.length > 0 && <p className="text-destructive">Missing: {u.missing_required.join(", ")}. Upload them (or load an earlier set that has them).</p>}
          {u.warnings?.map((w: string) => <p key={w} className="flex items-center gap-1 text-amber-700"><AlertTriangle className="h-4 w-4" />{w}</p>)}
          {u.files?.unrecognised?.length > 0 && <p className="text-xs text-muted-foreground">Not used: {u.files.unrecognised.join("; ")}</p>}
          <Table>
            <TableHeader><TableRow><TableHead>Report</TableHead><TableHead>From</TableHead><TableHead>File</TableHead><TableHead className="text-right">Rows</TableHead><TableHead>Dates</TableHead></TableRow></TableHeader>
            <TableBody>{u.plan.map((p: Dict) => (
              <TableRow key={p.kind}>
                <TableCell className="text-xs font-medium">{p.title}{p.required ? " *" : ""}</TableCell>
                <TableCell>{p.source === "uploaded" ? <Badge>uploaded</Badge> : p.source === "last set" ? <Badge variant="outline">last set</Badge> : <Badge variant={p.required ? "destructive" : "secondary"}>missing</Badge>}</TableCell>
                <TableCell className="max-w-[240px] truncate text-xs">{p.file}</TableCell>
                <TableCell className="text-right text-xs">{p.rows?.toLocaleString()}</TableCell>
                <TableCell className="whitespace-nowrap text-xs">{p.from ? `${fmtDate(p.from)} – ${fmtDate(p.to)}` : ""}</TableCell>
              </TableRow>
            ))}</TableBody>
          </Table>
          {res?.error && <p className="text-destructive">{res.error.message}</p>}
          {tie && (
            <div className="space-y-2 rounded-lg border p-3">
              <div className="font-medium">{res.dry_run ? "Check" : "Load"} result — history to {fmtDate(res.as_of)}</div>
              <p className={tie.ties ? "text-emerald-700" : "text-amber-700"}>
                {tie.ties ? `Ties: all ${tie.accounts_checked} accounts reproduce Sage's trial balance.` : `${tie.issues.length} account(s) do not tie — the set cannot be loaded until they do.`}
              </p>
              {res.statements && <p className="text-xs">Balance sheet total assets <Amount value={res.statements.roy_total_assets} /> (Sage <Amount value={res.statements.sage_total_assets} />) · {res.statements.year} net income <Amount value={res.statements.roy_net_income} /> (Sage <Amount value={res.statements.sage_net_income} />)</p>}
              <p className="text-xs text-muted-foreground">
                {res.general_ledger?.lines?.toLocaleString()} ledger lines · {res.invoices?.invoices?.toLocaleString()} invoices · {res.receipts?.receipts?.toLocaleString()} receipts
                {res.chart_and_opening?.COA?.accounts_added?.length ? ` · new accounts: ${res.chart_and_opening.COA.accounts_added.join(", ")}` : ""}
                {typeof res.chart_and_opening?.TRIAL_BALANCE === "string" ? ` · ${res.chart_and_opening.TRIAL_BALANCE}` : res.chart_and_opening?.TRIAL_BALANCE?.journal ? ` · opening balances now ${res.chart_and_opening.TRIAL_BALANCE.journal}` : ""}
                {res.general_journal_check ? ` · General Journal ${res.general_journal_check.agrees ? "agrees with" : "differs from"} the ledger` : ""}
              </p>
              {!tie.ties && (
                <Table>
                  <TableHeader><TableRow><TableHead>Account</TableHead><TableHead className="text-right">Sage TB</TableHead><TableHead className="text-right">History</TableHead></TableRow></TableHeader>
                  <TableBody>{tie.issues.slice(0, 30).map((i: Dict) => (
                    <TableRow key={i.account}><TableCell className="text-xs">{i.account}</TableCell><TableCell className="text-right"><Amount value={i.sage_tb} /></TableCell>
                      <TableCell className="text-right"><Amount value={i.history ?? Object.entries(i).find(([k]) => k.startsWith("history_"))?.[1]} /></TableCell></TableRow>
                  ))}</TableBody>
                </Table>
              )}
            </div>
          )}
        </div>
      )}
    </Section>
  );
}

const PAYER_TYPES: [string, string][] = [["PRIVATE", "Private"], ["HMO", "HMO"], ["CORPORATE", "Corporate / retainership"], ["STAFF", "Staff scheme"], ["INTERNAL", "Paid by Royan"]];

/** Hope's payers ("tariff standards"), how each is counted in the HMO / private reports, and its Sage account(s). */
export function HopePayers() {
  const { data, isLoading, error, refetch } = useBooks<Dict[]>(["hope-payers"], "/hope/payers");
  const [filter, setFilter] = useState("");
  const rows = (data ?? []).filter((p) => !filter || `${p.name} ${p.sage_code ?? ""}`.toLowerCase().includes(filter.toLowerCase()));
  const retype = async (p: Dict, t: string) => {
    if (await act(() => books.patch(`/hope/payers/${p.tariff_id}`, { payer_type: t }), `${p.name} is now counted as ${t.toLowerCase()}`)) refetch();
  };
  return (
    <Section title="Payers (from Hope)" actions={<Input className="h-8 w-56" placeholder="Find a payer" value={filter} onChange={(e) => setFilter(e.target.value)} />}>
      <p className="mb-3 text-sm text-muted-foreground">
        Every charge in Hope was priced for the patient's payer. This list decides how each payer is counted in the HMO vs private reports, the HMO
        bills and Credit Control. Types were set from the names — change any that are wrong; your choice is kept when Hope data is reloaded.
      </p>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (
        <Table>
          <TableHeader><TableRow><TableHead>Payer</TableHead><TableHead>Counted as</TableHead><TableHead>Sage account(s)</TableHead><TableHead className="text-right">Charge lines</TableHead><TableHead>Last used</TableHead></TableRow></TableHeader>
          <TableBody>{rows.map((p) => (
            <TableRow key={p.tariff_id}>
              <TableCell className="text-sm">{p.name}{p.typed_by !== "rule" && <Badge variant="outline" className="ml-2">set by {p.typed_by}</Badge>}</TableCell>
              <TableCell><select className="h-8 rounded-md border bg-background px-2 text-xs" value={p.payer_type} onChange={(e) => retype(p, e.target.value)}>
                {PAYER_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></TableCell>
              <TableCell className="text-xs">{p.sage_code ?? <span className="text-muted-foreground">none linked</span>}</TableCell>
              <TableCell className="text-right text-xs">{Number(p.lines).toLocaleString()}</TableCell>
              <TableCell className="whitespace-nowrap text-xs">{fmtDate(p.last_used)}</TableCell>
            </TableRow>
          ))}</TableBody>
        </Table>
      )}
    </Section>
  );
}
