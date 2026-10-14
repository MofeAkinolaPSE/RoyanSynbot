/** Report library: every report written about a record, with its subject (reopens the record), type and status. */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Download, FileText, Plus } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/workspace/PageHeader";
import { FilterBar } from "@/components/workspace/FilterBar";
import { DetailSheet } from "@/components/workspace/DetailSheet";
import { Md } from "@/components/reports/Md";
import { api } from "@/lib/api-client";
import { fmtDay } from "./ReportComposer";

type Dict = Record<string, any>;
const STATUS: Record<string, string> = { draft: "border-amber-400 text-amber-600", complete: "", approved: "border-emerald-500 text-emerald-600" };

export default function ReportLibrary() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [type, setType] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const lib = useQuery({ queryKey: ["reports", "library"], queryFn: () => api.reports.library() });
  const one = useQuery({ queryKey: ["reports", "record", open], queryFn: () => api.reports.record(open!), enabled: !!open });
  const rows = lib.data?.reports ?? [];
  const types = useMemo(() => Array.from(new Map(rows.map((r: Dict) => [r.report_type, r.type_name])).entries()), [rows]);
  const shown = rows.filter((r: Dict) =>
    (!search || `${r.title} ${r.subject_label} ${r.created_by_name ?? ""}`.toLowerCase().includes(search.toLowerCase())) &&
    (!status || r.status === status) && (!type || r.report_type === type));
  const download = async (id: string) => { try { await api.reports.downloadRecord(id); } catch (e: any) { toast.error(e?.message || "Download failed"); } };

  return (
    <div className="flex flex-col gap-5">
      <PageHeader icon={FileText} title="Report library" subtitle="Every report written about a record - open one, download it, or reopen its record"
        actions={<Link to="/reports/new"><Button size="sm"><Plus className="mr-1.5 h-4 w-4" />Write a report</Button></Link>} />
      <FilterBar search={{ value: search, onChange: setSearch, placeholder: "Search title, record or author" }}
        selects={[
          { label: "Type", value: type, onChange: setType, placeholder: "All types", options: types.map(([k, n]) => ({ value: k as string, label: n as string })) },
          { label: "Status", value: status, onChange: setStatus, placeholder: "Any status",
            options: [{ value: "draft", label: "Draft (needs sign-off)" }, { value: "complete", label: "Complete" }, { value: "approved", label: "Approved" }] },
        ]} />
      <div className="rounded-xl border bg-card">
        {lib.isLoading ? <p className="p-6 text-sm text-muted-foreground">Loading...</p> : shown.length === 0 ? (
          <p className="p-6 text-sm text-muted-foreground">No reports yet. <Link to="/reports/new" className="text-primary hover:underline">Write the first one</Link>.</p>
        ) : (
          <Table>
            <TableHeader><TableRow><TableHead>Report</TableHead><TableHead>About</TableHead><TableHead>Written</TableHead><TableHead>Status</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>
              {shown.map((r: Dict) => (
                <TableRow key={r.id} className="cursor-pointer hover:bg-muted/40" onClick={() => setOpen(r.id)}>
                  <TableCell><div className="font-medium">{r.title}</div><div className="text-xs text-muted-foreground">{r.type_name}</div></TableCell>
                  <TableCell className="text-sm">
                    <Link onClick={(e) => e.stopPropagation()} className="hover:text-primary hover:underline"
                          to={`/reports/new?${new URLSearchParams({ type: r.report_type, kind: r.subject_kind, id: r.subject_id })}`}>{r.subject_label}</Link>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{fmtDay(r.created_at)}<div>{r.created_by_name}</div></TableCell>
                  <TableCell><Badge variant="outline" className={STATUS[r.status] ?? ""}>{r.status}</Badge>
                    {r.approved_by_name && <div className="mt-0.5 text-xs text-muted-foreground">by {r.approved_by_name}</div>}</TableCell>
                  <TableCell className="text-right"><Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); void download(r.id); }}><Download className="h-4 w-4" /></Button></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
      <DetailSheet open={!!open} onOpenChange={(o) => !o && setOpen(null)} title={one.data?.title ?? "Report"} icon={FileText}
        description={one.data ? `${one.data.type_name} · ${one.data.status}` : undefined}
        footer={open ? <Button variant="outline" onClick={() => download(open)}><Download className="mr-1.5 h-4 w-4" />Download Word</Button> : undefined}>
        {one.isLoading ? <p className="text-sm text-muted-foreground">Loading...</p> : one.data && <Md text={one.data.full_report} />}
      </DetailSheet>
    </div>
  );
}
