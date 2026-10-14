/**
 * Patient Relations - the hospital's HMO and corporate accounts (reportGUide.md s7, CRM for a hospital).
 *
 * Who pays us, how much and for what, what they owe and how late, and the contact we have with them.
 * Billing is Hope's charge lines, what they owe is Credit Control's figure, receipts are their Roy Books /
 * Sage accounts - nothing about money is typed here. Follow-ups land on the owner's My Day.
 */
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, ArrowDownRight, ArrowUpRight, Banknote, Building2, CalendarClock, CheckCircle2, Handshake, Users } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/workspace/PageHeader";
import { KpiStrip } from "@/components/workspace/KpiStrip";
import { FilterBar } from "@/components/workspace/FilterBar";
import { DetailSheet } from "@/components/workspace/DetailSheet";
import { api } from "@/lib/api-client";
import { fmtDay, ReportButton } from "./ReportComposer";

type Dict = Record<string, any>;
const M = (v: any) => {
  const n = Number(v ?? 0);
  const a = Math.abs(n);
  return a >= 1e9 ? `₦${(n / 1e9).toFixed(2)}bn` : a >= 1e6 ? `₦${(n / 1e6).toFixed(1)}M` : a >= 1e3 ? `₦${(n / 1e3).toFixed(0)}k` : `₦${Math.round(n)}`;
};
const SEG: Record<string, { label: string; cls: string }> = {
  active: { label: "Active", cls: "border-emerald-500 text-emerald-600" },
  new: { label: "New", cls: "border-sky-500 text-sky-600" },
  lapsing: { label: "Lapsing", cls: "border-amber-400 text-amber-600" },
  lapsed: { label: "Lapsed", cls: "text-muted-foreground" },
  never_billed: { label: "Never billed", cls: "text-muted-foreground" },
};

export default function PatientRelations() {
  const [params, setParams] = useSearchParams();
  const payer = params.get("payer");
  const setPayer = (id: string | null) => { const p = new URLSearchParams(params); id ? p.set("payer", id) : p.delete("payer"); setParams(p, { replace: true }); };
  const [search, setSearch] = useState("");
  const [show, setShow] = useState("billing");
  const [type, setType] = useState("");
  const ov = useQuery({ queryKey: ["relations", "overview"], queryFn: () => api.relations.overview() });
  const dir = useQuery({ queryKey: ["relations", "payers"], queryFn: () => api.relations.payers() });
  const o: Dict = ov.data ?? {};
  const rows: Dict[] = useMemo(() => (dir.data?.payers ?? []).filter((p: Dict) =>
    (!search || p.name.toLowerCase().includes(search.toLowerCase())) && (!type || p.payer_type === type) &&
    (show === "" || (show === "billing" ? p.billed_12m > 0 : show === "risk" ? p.at_risk : show === "owes" ? p.owed > 0
      : show === "follow" ? p.follow_ups_due > 0 : p.segment === show))), [dir.data, search, show, type]);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader icon={Handshake} title="Patient Relations"
        subtitle={`HMO and corporate accounts · billing to ${fmtDay(o.as_of) || "…"} · what they owe is Credit Control's figure`} />
      <KpiStrip items={[
        { label: "Active payers (billed in 90 days)", value: o.active ?? "—", icon: Building2, sub: `${o.counts?.lapsing ?? 0} lapsing · ${o.counts?.lapsed ?? 0} lapsed`, onClick: () => setShow("active") },
        { label: "Billed to them, 12 months", value: M(o.billed_12m), icon: Users, sub: o.top10_share_pct != null ? `top 10 are ${o.top10_share_pct}%` : undefined, onClick: () => setShow("billing") },
        { label: "They owe us", value: M(o.owed), icon: Banknote, tone: o.owed_over_90 > 0 ? "warning" : "default", sub: `${M(o.owed_over_90)} over 90 days`, onClick: () => setShow("owes") },
        { label: "At risk / follow-ups due", value: `${o.at_risk ?? 0} / ${o.follow_ups_due ?? 0}`, icon: AlertTriangle,
          tone: o.at_risk || o.follow_ups_due ? "warning" : "default", sub: `${o.contacts_7d ?? 0} contacts logged this week`, onClick: () => setShow(o.follow_ups_due ? "follow" : "risk") },
      ]} />
      <FilterBar search={{ value: search, onChange: setSearch, placeholder: "Search HMO or company" }}
        selects={[
          { label: "Show", value: show, onChange: setShow, placeholder: "All payers", options: [
            { value: "billing", label: "Billed in 12 months" }, { value: "risk", label: "At risk" }, { value: "owes", label: "Owe us" },
            { value: "follow", label: "Follow-up due" }, ...Object.entries(SEG).map(([k, v]) => ({ value: k, label: v.label }))] },
          { label: "Type", value: type, onChange: setType, placeholder: "HMOs and corporates", options: [{ value: "HMO", label: "HMOs" }, { value: "CORPORATE", label: "Corporate / retainership" }] },
        ]} />
      <div className="rounded-xl border bg-card">
        {dir.isLoading ? <p className="p-6 text-sm text-muted-foreground">Loading payers...</p> : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow><TableHead>Payer</TableHead><TableHead>Segment</TableHead><TableHead className="text-right">Billed, 12 months</TableHead>
                <TableHead className="text-right">vs year before</TableHead><TableHead className="text-right">Patients</TableHead><TableHead className="text-right">Owes</TableHead>
                <TableHead>Last bill</TableHead><TableHead>Follow-up</TableHead></TableRow></TableHeader>
              <TableBody>
                {rows.length === 0 && <TableRow><TableCell colSpan={8} className="py-6 text-center text-sm text-muted-foreground">No payers in this view.</TableCell></TableRow>}
                {rows.map((p) => (
                  <TableRow key={p.id} className="cursor-pointer hover:bg-muted/40" onClick={() => setPayer(String(p.id))}>
                    <TableCell><div className="font-medium">{p.name}</div><div className="text-xs text-muted-foreground">{p.payer_type === "HMO" ? "HMO" : "Corporate"}
                      {p.at_risk && <span className="text-amber-600"> · {p.risk_reasons.join("; ")}</span>}</div></TableCell>
                    <TableCell><Badge variant="outline" className={SEG[p.segment]?.cls}>{SEG[p.segment]?.label ?? p.segment}</Badge></TableCell>
                    <TableCell className="text-right tabular-nums">{M(p.billed_12m)}</TableCell>
                    <TableCell className="text-right">{p.change_pct == null ? <span className="text-xs text-muted-foreground">—</span> : (
                      <span className={`inline-flex items-center text-xs ${p.change_pct >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                        {p.change_pct >= 0 ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}{Math.abs(p.change_pct)}%</span>)}</TableCell>
                    <TableCell className="text-right tabular-nums">{p.patients_12m || "—"}</TableCell>
                    <TableCell className={`text-right tabular-nums ${p.owed_over_90 > 0 ? "text-amber-600" : ""}`}>{p.owed ? M(p.owed) : "—"}</TableCell>
                    <TableCell className="text-xs">{fmtDay(p.last_bill) || "never"}</TableCell>
                    <TableCell className="text-xs">{p.follow_ups_due ? <span className="text-red-600">{p.follow_ups_due} due</span> : p.next_follow_up ? fmtDay(p.next_follow_up) : "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
      <PayerSheet id={payer} onClose={() => setPayer(null)} />
    </div>
  );
}

function PayerSheet({ id, onClose }: { id: string | null; onClose: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["relations", "payer", id], queryFn: () => api.relations.payer(id!), enabled: !!id });
  const d: Dict | undefined = q.data;
  const [kind, setKind] = useState("call");
  const [summary, setSummary] = useState("");
  const [follow, setFollow] = useState("");
  const done = () => { void qc.invalidateQueries({ queryKey: ["relations"] }); };
  const log = useMutation({
    mutationFn: () => api.relations.logContact(id!, { kind, summary, follow_up_on: follow || undefined }),
    onSuccess: () => { toast.success(follow ? "Logged - the follow-up is on your My Day when due" : "Contact logged"); setSummary(""); setFollow(""); done(); },
    onError: (e: any) => toast.error(e?.message || "Could not log the contact"),
  });
  const complete = useMutation({
    mutationFn: (cid: string) => api.relations.done(cid),
    onSuccess: () => { toast.success("Follow-up done"); done(); }, onError: (e: any) => toast.error(e?.message || "Could not update"),
  });
  const months = (d?.months ?? []).map((m: Dict) => ({ ...m, label: new Date(m.period + "-15").toLocaleDateString("en-GB", { month: "short", year: "2-digit" }) }));
  const b = d?.account?.buckets ?? {};
  return (
    <DetailSheet open={!!id} onOpenChange={(o) => !o && onClose()} title={d?.payer?.name ?? "Payer"} icon={Building2}
      description={d ? `${d.payer.payer_type === "HMO" ? "HMO" : "Corporate"} · billing to ${fmtDay(d.as_of)}` : undefined}
      footer={id ? <ReportButton type="hmo_account" kind="payer" id={id} label="Write account report" /> : undefined}>
      {q.isLoading || !d ? <p className="text-sm text-muted-foreground">Loading...</p> : (
        <Tabs defaultValue="billing">
          <TabsList className="flex-wrap"><TabsTrigger value="billing">Billing</TabsTrigger><TabsTrigger value="services">Services</TabsTrigger>
            <TabsTrigger value="account">Account (Roy Books)</TabsTrigger><TabsTrigger value="contacts">Contacts{d.contacts.length ? ` (${d.contacts.length})` : ""}</TabsTrigger></TabsList>
          <TabsContent value="billing" className="space-y-3">
            <div className="grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded-lg bg-muted/40 p-2"><div className="text-muted-foreground">Billed since {fmtDay(d.totals.first_bill)}</div><div className="font-semibold">{M(d.totals.billed_all)}</div></div>
              <div className="rounded-lg bg-muted/40 p-2"><div className="text-muted-foreground">Patients</div><div className="font-semibold">{d.totals.patients_all.toLocaleString()}</div></div>
              <div className="rounded-lg bg-muted/40 p-2"><div className="text-muted-foreground">Last bill</div><div className="font-semibold">{fmtDay(d.totals.last_bill)}</div></div>
            </div>
            <div className="h-48">
              <ResponsiveContainer>
                <BarChart data={months} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-muted" />
                  <XAxis dataKey="label" fontSize={10} tickLine={false} axisLine={false} />
                  <YAxis fontSize={10} tickLine={false} axisLine={false} width={40} tickFormatter={(v) => M(v)} />
                  <Tooltip formatter={(v: any) => [M(v), "Billed"]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                  <Bar dataKey="billed" fill="hsl(var(--primary))" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            {d.gaps.length > 0 && <ul className="space-y-1 text-xs text-amber-600">{d.gaps.map((g: string) => <li key={g} className="flex gap-1.5"><AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />{g}</li>)}</ul>}
          </TabsContent>
          <TabsContent value="services">
            <p className="mb-2 text-xs text-muted-foreground">Last 12 months of billing</p>
            <Table><TableHeader><TableRow><TableHead>Department</TableHead><TableHead className="text-right">Billed</TableHead><TableHead className="text-right">Patients</TableHead></TableRow></TableHeader>
              <TableBody>{d.departments.map((s: Dict) => <TableRow key={s.department}><TableCell>{s.department}</TableCell><TableCell className="text-right">{M(s.billed)}</TableCell><TableCell className="text-right">{s.patients}</TableCell></TableRow>)}</TableBody></Table>
            <div className="mt-3 text-xs font-semibold text-muted-foreground">Services billed most</div>
            <ul className="mt-1 divide-y text-sm">{d.top_services.map((s: Dict) => <li key={s.service} className="flex justify-between gap-2 py-1"><span className="truncate">{s.service}</span><span className="shrink-0 tabular-nums">{M(s.billed)}</span></li>)}</ul>
          </TabsContent>
          <TabsContent value="account" className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-muted-foreground">Owed now</span><span className="font-semibold">{M(d.account.owed)}</span></div>
            {["0_30", "31_60", "61_90", "91_plus"].map((k) => (
              <div key={k} className="flex justify-between text-xs"><span className="text-muted-foreground">{k === "91_plus" ? "Over 90 days" : `${k.replace("_", "–")} days`}</span><span className={k === "91_plus" && b[k] ? "text-amber-600" : ""}>{M(b[k])}</span></div>
            ))}
            <div className="flex justify-between"><span className="text-muted-foreground">Received on their accounts</span><span>{M(d.totals.received)}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Oldest unpaid month</span><span>{fmtDay(d.account.oldest_open) || "—"}</span></div>
            <p className="text-xs text-muted-foreground">{d.account.source}</p>
            <div className="border-t pt-2 text-xs"><div className="mb-1 font-medium">Accounts in Roy Books / Sage</div>
              {d.account.accounts.length === 0 ? <span className="text-amber-600">none linked</span> : d.account.accounts.map((a: Dict) => <div key={a.customer_id}>{a.name} <span className="text-muted-foreground">{a.customer_code}</span></div>)}
              <Link to="/finance/ar" className="mt-1 inline-block text-primary hover:underline">Open Credit Control</Link></div>
          </TabsContent>
          <TabsContent value="contacts" className="space-y-3">
            <div className="space-y-2 rounded-lg border p-3">
              <div className="flex gap-2">
                <select className="h-9 rounded-md border bg-background px-2 text-sm" value={kind} onChange={(e) => setKind(e.target.value)}>
                  {["call", "visit", "email", "meeting", "note"].map((k) => <option key={k} value={k}>{k[0].toUpperCase() + k.slice(1)}</option>)}
                </select>
                <div className="flex-1"><Input type="date" value={follow} min={new Date().toISOString().slice(0, 10)} onChange={(e) => setFollow(e.target.value)} title="Follow-up date (optional)" /></div>
              </div>
              <Textarea rows={2} value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="What was discussed or agreed" />
              <div className="flex items-center justify-between"><Label className="text-xs font-normal text-muted-foreground">A follow-up date puts it on your My Day.</Label>
                <Button size="sm" disabled={!summary.trim() || log.isPending} onClick={() => log.mutate()}>Log</Button></div>
            </div>
            {d.contacts.length === 0 ? <p className="text-sm text-muted-foreground">No contact recorded yet.</p> : (
              <ul className="space-y-2">{d.contacts.map((c: Dict) => (
                <li key={c.id} className="rounded-lg border p-2.5 text-sm">
                  <div className="flex justify-between text-xs text-muted-foreground"><span className="capitalize">{c.kind} · {c.by_name ?? "staff"}</span><span>{fmtDay(c.created_at)}</span></div>
                  <p className="mt-1 whitespace-pre-wrap">{c.summary}</p>
                  {c.follow_up_on && (
                    <div className="mt-1.5 flex items-center justify-between text-xs">
                      <span className={!c.follow_up_done_at && c.follow_up_on <= new Date().toISOString().slice(0, 10) ? "text-red-600" : "text-muted-foreground"}>
                        <CalendarClock className="mr-1 inline h-3 w-3" />Follow up {fmtDay(c.follow_up_on)}{c.follow_up_done_at ? " - done" : ""}</span>
                      {!c.follow_up_done_at && <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={() => complete.mutate(c.id)}><CheckCircle2 className="mr-1 h-3 w-3" />Done</Button>}
                    </div>
                  )}
                </li>
              ))}</ul>
            )}
          </TabsContent>
        </Tabs>
      )}
    </DetailSheet>
  );
}
