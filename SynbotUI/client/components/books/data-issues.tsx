/**
 * Data issues (Close & Controls): everything Royan's data leaves unexplained - Sage history that no longer ties, the
 * months with no books after Sage's last export, pharmacy stock the books do not carry, payers billed in Hope with no
 * Sage account, Hope vs Sage gaps - each with its lineage and the ways to resolve it. Nothing is hidden; a decision
 * records who, when and why. "Check again" re-runs the detection (also done after every Sage load).
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { books, Dict, fmtDate } from "@/lib/books-api";
import { useDrill } from "./drill-context";
import { act, Amount, Empty, ErrorNote, Loading, Section, StatusBadge, useBooks } from "./kit";

const TONE: Record<string, string> = { HIGH: "bg-red-500/15 text-red-700", MEDIUM: "bg-amber-500/15 text-amber-700", LOW: "bg-muted text-muted-foreground" };

export function DataIssues() {
  const qc = useQueryClient();
  const drill = useDrill();
  const [status, setStatus] = useState("OPEN");
  const [busy, setBusy] = useState(false);
  const { data, isLoading, error } = useBooks<Dict>(["data-issues", status], "/data-issues", { status: status || undefined });
  const check = async () => {
    setBusy(true);
    const r = await act(() => books.post<Dict>("/data-issues/refresh", {}), "Checked");
    setBusy(false);
    if (r) qc.invalidateQueries({ queryKey: ["books"] });
  };
  const sm = data?.summary;
  return (
    <Section title={`Data issues${sm ? ` (${sm.open} open)` : ""}`}
             actions={<Button size="sm" variant="outline" disabled={busy} onClick={check}><RefreshCw className={`mr-1.5 h-4 w-4 ${busy ? "animate-spin" : ""}`} />Check again</Button>}>
      <p className="mb-3 text-sm text-muted-foreground">
        Where Sage, Hope, the books and the pharmacy's shelves disagree, the difference is listed here with what is behind it and what to do. An issue the data
        no longer shows closes itself; one that comes back reopens unless it was accepted. {sm?.last_checked && `Last checked ${new Date(sm.last_checked).toLocaleString("en-GB")}.`}
      </p>
      <div className="mb-3 flex flex-wrap gap-1">
        {[["OPEN", "Open"], ["ACCEPTED", "Accepted"], ["RESOLVED", "Resolved"], ["", "All"]].map(([v, l]) => (
          <Button key={v} size="sm" variant={status === v ? "default" : "outline"} onClick={() => setStatus(v)}>{l}</Button>))}
      </div>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (data.items.length === 0 ? <Empty>{status === "OPEN" ? "No open issues. Press Check again after loading new data." : "Nothing here."}</Empty> : (
        <Table>
          <TableHeader><TableRow><TableHead>Issue</TableHead><TableHead>Kind</TableHead><TableHead>Severity</TableHead><TableHead className="text-right">Amount</TableHead>
            <TableHead>Status</TableHead><TableHead>Since</TableHead></TableRow></TableHeader>
          <TableBody>{data.items.map((x: Dict) => (
            <TableRow key={x.id} className="cursor-pointer hover:bg-muted/50" onClick={() => drill?.open({ type: "dataissue", id: x.id, label: x.kind_label })}>
              <TableCell className="max-w-[520px]"><div className="text-sm font-medium">{x.title}</div><div className="truncate text-xs text-muted-foreground">{x.summary}</div></TableCell>
              <TableCell className="text-xs">{x.kind_label}</TableCell>
              <TableCell><span className={`rounded px-1.5 py-0.5 text-xs ${TONE[x.severity] ?? ""}`}>{x.severity.toLowerCase()}</span></TableCell>
              <TableCell className="text-right">{x.amount != null ? <Amount value={x.amount} /> : ""}</TableCell>
              <TableCell><StatusBadge status={x.status} />{x.resolution && <div className="text-xs text-muted-foreground">{x.resolution}</div>}</TableCell>
              <TableCell className="whitespace-nowrap text-xs">{fmtDate(x.first_seen)}</TableCell>
            </TableRow>))}</TableBody>
        </Table>
      ))}
    </Section>
  );
}

/** A banner for the Control Tower while Data issues are open. */
export function DataIssuesBanner() {
  const { data } = useBooks<Dict>(["data-issues", "OPEN"], "/data-issues", { status: "OPEN" });
  const n = data?.summary?.open ?? 0;
  if (!n) return null;
  const high = (data?.items ?? []).filter((x: Dict) => x.severity === "HIGH").length;
  return (
    <Link to="/finance/books/close?tab=data-issues"
          className="flex items-center gap-2 rounded-lg border border-amber-400 bg-amber-500/10 p-3 text-sm text-amber-900 hover:bg-amber-500/15 dark:text-amber-200">
      <AlertTriangle className="h-4 w-4" />
      <span><strong>{n} data issue{n === 1 ? "" : "s"} open</strong>{high ? ` (${high} high)` : ""} - differences between Sage, Hope, the books and the shelves. Open Close &amp; Controls › Data issues.</span>
    </Link>
  );
}
