/**
 * Compliance - where the hospital stands against what regulators look at (HEFAMAA, NDPA), read from
 * the records that own it: the compliance score and exactly what is pulling it down, HEFAMAA
 * self-assessments, facility audits due or overdue, and whether the audit trail is intact.
 *
 * Replaces a page from the pharma product that called /compliance/* routes this hospital never had.
 */
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ClipboardCheck, FileSearch, ShieldCheck, Siren } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/workspace/PageHeader";
import { KpiStrip } from "@/components/workspace/KpiStrip";
import { api } from "@/lib/api-client";
import { fmtDay } from "./ReportComposer";

type Dict = Record<string, any>;

export default function Compliance() {
  const q = useQuery({ queryKey: ["quality", "compliance"], queryFn: () => api.quality.complianceOverview() });
  const d: Dict = q.data ?? {};
  const score = d.compliance_score;
  const tone = score == null ? "default" : score >= 85 ? "success" : score >= 70 ? "warning" : "danger";
  const log: Dict = d.audit_log ?? {};

  return (
    <div className="flex flex-col gap-5">
      <PageHeader icon={ShieldCheck} title="Compliance"
        subtitle="HEFAMAA and NDPA readiness, read live from incidents, audits, maintenance and the audit trail"
        actions={<Link to="/reports/new?type=monthly"><Button size="sm" variant="outline">Monthly report</Button></Link>} />
      <KpiStrip items={[
        { label: "Compliance score", value: score ?? "—", icon: ShieldCheck, tone, sub: "100 less what is overdue or open today" },
        { label: "Audits overdue / due in 30 days", value: `${d.audits?.overdue ?? 0} / ${d.audits?.due_30 ?? 0}`, icon: ClipboardCheck,
          tone: d.audits?.overdue ? "danger" : "default", sub: d.audits?.avg_score != null ? `completed audits average ${d.audits.avg_score}` : "no completed audit scores" },
        { label: "Serious incidents open", value: d.incidents?.open_serious ?? 0, icon: Siren, tone: d.incidents?.open_serious ? "danger" : "default",
          sub: `${d.incidents?.open ?? 0} incidents open in all` },
        { label: "Audit trail, last 7 days", value: (log.actions_7d ?? 0).toLocaleString(), icon: FileSearch,
          tone: log.actions_7d ? "success" : "warning",
          sub: log.last ? `${log.people_7d ?? 0} people · last ${fmtDay(log.last)} (NDPA accountability)` : "no actions recorded yet" },
      ]} />

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-xl border bg-card p-4">
          <h3 className="mb-1 text-sm font-semibold">What is pulling the score down</h3>
          <p className="mb-3 text-xs text-muted-foreground">Each overdue or open item takes points off. Clear these to raise it.</p>
          <div className="divide-y">
            {(d.deductions ?? []).map((x: Dict) => (
              <Link key={x.item} to={x.link} className="flex items-center justify-between py-2 text-sm hover:text-primary">
                <span>{x.item} <span className="text-xs text-muted-foreground">({x.each} each)</span></span>
                <span className={`tabular-nums ${x.points ? "font-semibold text-red-600" : "text-muted-foreground"}`}>{x.count} · −{x.points}</span>
              </Link>
            ))}
          </div>
        </section>
        <section className="rounded-xl border bg-card p-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold">HEFAMAA self-assessments</h3>
            <Link to="/hospital/quality" className="text-xs text-primary hover:underline">Quality & Safety</Link>
          </div>
          {(d.hefamaa_list ?? []).length === 0 ? <p className="text-sm text-muted-foreground">No HEFAMAA assessment recorded yet. Record one on Quality & Safety.</p> : (
            <Table>
              <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Department</TableHead><TableHead className="text-right">Score</TableHead><TableHead>Follow-up</TableHead></TableRow></TableHeader>
              <TableBody>{d.hefamaa_list.map((h: Dict) => (
                <TableRow key={h.id}><TableCell className="text-xs">{fmtDay(h.assessment_date)}</TableCell><TableCell className="text-sm">{h.department ?? "Hospital-wide"}</TableCell>
                  <TableCell className={`text-right tabular-nums ${h.overall_score < 70 ? "text-red-600" : ""}`}>{h.overall_score ?? "—"}</TableCell>
                  <TableCell className="text-xs">{fmtDay(h.follow_up_date) || "—"}</TableCell></TableRow>
              ))}</TableBody>
            </Table>
          )}
        </section>
      </div>

      <section className="rounded-xl border bg-card p-4">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold">Facility audits - open, and completed in the last six months</h3>
          <Link to="/hospital/audits-maintenance" className="text-xs text-primary hover:underline">Audits & Maintenance</Link>
        </div>
        {(d.audit_list ?? []).length === 0 ? <p className="text-sm text-muted-foreground">No audits scheduled.</p> : (
          <Table>
            <TableHeader><TableRow><TableHead>Audit</TableHead><TableHead>Department</TableHead><TableHead>Date</TableHead><TableHead>Risk</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Score</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>{d.audit_list.map((a: Dict) => (
              <TableRow key={a.id}>
                <TableCell className="font-medium">{a.audit_title}</TableCell><TableCell className="text-sm">{a.department}</TableCell>
                <TableCell className={`text-xs ${a.overdue ? "text-red-600" : ""}`}>{fmtDay(a.scheduled_date)}{a.overdue ? " · overdue" : ""}</TableCell>
                <TableCell className="text-xs capitalize">{a.risk_level}</TableCell>
                <TableCell><Badge variant="outline" className="capitalize">{String(a.status).replace(/_/g, " ")}</Badge></TableCell>
                <TableCell className="text-right tabular-nums">{a.score ?? "—"}</TableCell>
                <TableCell className="text-right">{a.status === "completed" && <Link to={`/reports/new?type=audit&kind=audit&id=${a.id}`}><Button size="sm" variant="ghost">Report</Button></Link>}</TableCell>
              </TableRow>
            ))}</TableBody>
          </Table>
        )}
      </section>
      <p className="text-xs text-muted-foreground">NDPA: patient data is reached only through role-checked pages, every action is written to the <Link className="text-primary hover:underline" to="/admin/audit-log">audit log</Link>, and clinical notes cannot be edited or deleted.</p>
    </div>
  );
}
