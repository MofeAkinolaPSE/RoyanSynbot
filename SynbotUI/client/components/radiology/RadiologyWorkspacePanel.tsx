import { useEffect, useState } from "react";
import { handlePayFirst } from "@/lib/pay-first";
import { useAuth } from "@/components/AuthProvider";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  User, ScanLine, FileText, CalendarClock, Play, ShieldCheck,
  History, ExternalLink, Loader2, CheckCircle2,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { ViewReportButton } from "@/components/reports/ResultReport";
import { useToast } from "@/hooks/use-toast";
import { SectionLabel, PANEL_WIDTH } from "@/components/shared/panel-shared";
import { cn } from "@/lib/utils";
import {
  StatusBadge, UrgencyBadge, ModalityBadge, WorkflowProgress, DetailRow, elapsed,
} from "@/components/radiology/radiology-shared";

interface RadiologyWorkspacePanelProps {
  order: {
    id: string | number;
    patient_id?: string | number;
    patient_mrn?: string;
    patient_name?: string;
    patient_gender?: string;
    patient_dob?: string;
    modality?: string;
    body_part?: string;
    clinical_indication?: string;
    urgency?: string;
    status?: string;
    ordered_at?: string;
  };
  onClose: () => void;
  initialTab?: string;
}

const emptyReportForm = { report: "", impression: "", findings: "", radiologist_id: "" };

export function RadiologyWorkspacePanel({ order: initialOrder, onClose, initialTab }: RadiologyWorkspacePanelProps) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState(initialTab ?? "detail");

  const [scheduledAt, setScheduledAt] = useState("");
  const [reportForm, setReportForm] = useState({ ...emptyReportForm });
  const [reportMode, setReportMode] = useState<"view" | "edit" | "amend">("view");
  const [amendReason, setAmendReason] = useState("");
  const [templateId, setTemplateId] = useState("");

  const orderId = String(initialOrder.id);
  const { roles: payFirstRoles } = useAuth();

  const { data, isLoading } = useQuery({
    queryKey: ["radiology-panel-order", orderId],
    queryFn: () => api.hospital.radiology.getOrder(orderId),
    refetchInterval: 15_000,
  });
  const order: typeof initialOrder & Record<string, any> = { ...initialOrder, ...(data?.order ?? {}) };
  const reportHistory: any[] = order.report_history ?? [];

  const { data: historyData } = useQuery({
    queryKey: ["radiology-panel-patient-history", order.patient_id],
    queryFn: () => api.hospital.radiology.patientHistory(order.patient_id!),
    enabled: tab === "history" && !!order.patient_id,
  });
  const patientHistory: any[] = (historyData?.history ?? []).filter((h: any) => String(h.id) !== orderId);

  const { data: templatesData } = useQuery({
    queryKey: ["radiology-panel-templates", order.modality],
    queryFn: () => api.hospital.radiology.listTemplates({ modality: order.modality }),
    enabled: !!order.modality && tab === "report" && reportMode !== "view",
    staleTime: 60_000,
  });
  const templates: any[] = templatesData?.templates ?? [];

  // A new report starts from Scancare's standard wording for this study (its latest normal report of the same type,
  // measurements blanked to ___, this order's indication) - the radiologist fills the blanks and changes what differs.
  const writingNew = tab === "report" && !order.report && reportMode !== "amend";
  const { data: prefill } = useQuery({
    queryKey: ["radiology-report-template", orderId],
    queryFn: () => api.hospital.radiology.reportTemplate(orderId),
    enabled: writingNew || reportMode !== "view",
    staleTime: 300_000,
  });
  const applyPrefill = () => prefill && setReportForm((f) => ({ ...f, report: prefill.report ?? "", impression: prefill.impression ?? "" }));
  useEffect(() => {
    if (writingNew && prefill?.report && !reportForm.report.trim() && !reportForm.impression.trim()) applyPrefill();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefill, writingNew]);
  const blanks = (reportForm.report.match(/___/g) ?? []).length + (reportForm.impression.match(/___/g) ?? []).length;
  const phrases: { section: string; text: string }[] = prefill?.phrases ?? [];
  const confirmBlanks = () => blanks === 0 ||
    window.confirm(`${blanks} measurement blank${blanks === 1 ? "" : "s"} (___) not filled in. Save the report anyway?`);

  useEffect(() => {
    if (reportMode === "edit") {
      setReportForm({
        report: order.report ?? "",
        impression: order.impression ?? "",
        findings: order.findings ?? "",
        radiologist_id: order.radiologist_id ?? "",
      });
    } else if (reportMode === "amend") {
      // an amendment corrects the report: start from what was written, not an empty box
      setReportForm({ report: order.report ?? "", impression: order.impression ?? "", findings: order.findings ?? "",
        radiologist_id: order.radiologist_id ?? "" });
      setAmendReason("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportMode]);

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ["radiology-panel-order", orderId] });
    void qc.invalidateQueries({ queryKey: ["radiology-orders"] });
    void qc.invalidateQueries({ queryKey: ["radiology-stats"] });
  };

  const scheduleMut = useMutation({
    mutationFn: () => api.hospital.radiology.advanceStatus(orderId, {
      status: "scheduled",
      scheduled_at: scheduledAt || undefined,
    }),
    onSuccess: () => { toast({ title: "Exam scheduled" }); setScheduledAt(""); invalidateAll(); },
    onError: (e: any) => toast({ title: "Failed to schedule", description: e.message, variant: "destructive" }),
  });

  const startMut = useMutation({
    mutationFn: () => api.hospital.radiology.advanceStatus(orderId, { status: "in_progress" }),
    onSuccess: () => { toast({ title: "Scan started" }); invalidateAll(); },
    onError: async (e: any) => {
      if (await handlePayFirst(e, "radiology_order", orderId, payFirstRoles, toast)) return;
      toast({ title: "Failed to start scan", description: e.message, variant: "destructive" });
    },
  });

  const reportMut = useMutation({
    mutationFn: () => api.hospital.radiology.submitReport(orderId, {
      report: reportForm.report,
      impression: reportForm.impression || undefined,
      findings: reportForm.findings || undefined,
      radiologist_id: reportForm.radiologist_id || undefined,
    }),
    onSuccess: () => { toast({ title: "Report saved" }); setReportMode("view"); invalidateAll(); },
    onError: (e: any) => toast({ title: "Failed to save report", description: e.message, variant: "destructive" }),
  });

  const verifyMut = useMutation({
    mutationFn: () => api.hospital.radiology.verify(orderId, {}),
    onSuccess: () => { toast({ title: "Report verified and finalized" }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Failed to verify", description: e.message, variant: "destructive" }),
  });

  const amendMut = useMutation({
    mutationFn: () => api.hospital.radiology.amendReport(orderId, {
      report: reportForm.report,
      impression: reportForm.impression || undefined,
      findings: reportForm.findings || undefined,
      radiologist_id: reportForm.radiologist_id || undefined,
      amendment_reason: amendReason,
    }),
    onSuccess: () => { toast({ title: "Report amended" }); setReportMode("view"); invalidateAll(); },
    onError: (e: any) => toast({ title: "Failed to amend report", description: e.message, variant: "destructive" }),
  });

  const status = order.status;
  const canSchedule    = status === "ordered";
  const canStart       = ["ordered", "scheduled"].includes(status ?? "");
  const canReport      = status === "in_progress";
  const canEditReport  = status === "reported" && !order.verified_at;
  const canVerify      = status === "reported" && !order.verified_at && !!order.report;
  const canAmend       = status === "reported" && !!order.verified_at;
  const reportFormValid = !!reportForm.report.trim();

  return (
    <Sheet open onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className={cn(PANEL_WIDTH.default, "overflow-y-auto p-0 flex flex-col")} side="right">
        {isLoading && !data ? (
          <LoadingSkeleton />
        ) : (
          <>
            {/* Header */}
            <SheetHeader className="px-5 pt-5 pb-4 border-b shrink-0">
              <div className="flex items-start gap-3">
                <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                  <ScanLine className="h-5 w-5 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <SheetTitle className="text-base leading-tight">
                    {order.modality ? order.modality.toUpperCase() : "Imaging Order"}{order.body_part ? ` — ${order.body_part}` : ""}
                  </SheetTitle>
                  <div className="flex flex-wrap items-center gap-2 mt-1">
                    <span className="text-xs text-muted-foreground">{order.patient_name ?? `Patient ID ${order.patient_id}`}</span>
                    {order.patient_mrn && <Badge variant="outline" className="text-xs font-mono">{order.patient_mrn}</Badge>}
                    <UrgencyBadge urgency={order.urgency} />
                    <StatusBadge status={status} />
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">Order #{order.id} · Ordered {elapsed(order.ordered_at)} ago</p>
                </div>
              </div>
            </SheetHeader>

            {/* Tabs */}
            <Tabs value={tab} onValueChange={setTab} className="flex-1 flex flex-col min-h-0">
              <TabsList className="mx-5 mt-3 bg-muted border border-border shrink-0 flex-wrap h-auto">
                <TabsTrigger value="detail">Detail</TabsTrigger>
                <TabsTrigger value="report">Report</TabsTrigger>
                <TabsTrigger value="history">History</TabsTrigger>
              </TabsList>

              <div className="flex-1 overflow-y-auto px-5 py-4">
                {/* ── Detail ── */}
                <TabsContent value="detail" className="mt-0 space-y-4">
                  <section>
                    <SectionLabel icon={<User className="h-3.5 w-3.5" />} label="Patient" />
                    <DetailRow label="Name"   value={order.patient_name} />
                    <DetailRow label="MRN"    value={order.patient_mrn} mono />
                    <DetailRow label="Gender" value={order.patient_gender} />
                    <DetailRow label="DOB"    value={order.patient_dob} />
                  </section>
                  <Separator />
                  <section>
                    <SectionLabel icon={<ScanLine className="h-3.5 w-3.5" />} label="Order Details" />
                    <div className="flex items-center gap-2 py-1">
                      <ModalityBadge modality={order.modality} />
                    </div>
                    <DetailRow label="Body Part"          value={order.body_part} />
                    <DetailRow label="Clinical Indication" value={order.clinical_indication} />
                    <DetailRow label="Ordered by"         value={order.ordered_by} mono />
                    <DetailRow label="Ordered at"         value={order.ordered_at
                      ? new Date(order.ordered_at).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
                      : undefined}
                    />
                    <DetailRow label="PACS Study UID"     value={order.pacs_study_uid} mono />
                  </section>
                  <Separator />
                  <section>
                    <SectionLabel icon={<ShieldCheck className="h-3.5 w-3.5" />} label="Workflow" />
                    <WorkflowProgress status={status} verified={!!order.verified_at} />
                  </section>
                  {canSchedule && (
                    <>
                      <Separator />
                      <section className="space-y-2">
                        <SectionLabel icon={<CalendarClock className="h-3.5 w-3.5" />} label="Schedule Exam" />
                        <Input type="datetime-local" value={scheduledAt}
                          onChange={e => setScheduledAt(e.target.value)} />
                        <p className="text-xs text-muted-foreground">Leave blank to schedule for now.</p>
                        <Button size="sm" variant="outline" className="w-full gap-1.5"
                          disabled={scheduleMut.isPending} onClick={() => scheduleMut.mutate()}>
                          {scheduleMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CalendarClock className="h-3.5 w-3.5" />}
                          Schedule
                        </Button>
                      </section>
                    </>
                  )}
                </TabsContent>

                {/* ── Report ── */}
                <TabsContent value="report" className="mt-0 space-y-4">
                  {order.report && reportMode === "view" ? (
                    <section className="space-y-3">
                      {order.verified_at ? (
                        <div className="rounded-md border border-green-500/30 bg-green-500/5 p-3 space-y-1">
                          <div className="flex items-center gap-1.5 text-green-700 dark:text-green-400 text-sm font-medium">
                            <CheckCircle2 className="h-4 w-4" /> Verified & Finalized
                          </div>
                          <p className="text-xs text-muted-foreground">
                            By {order.verified_by_name ?? order.verified_by} · {new Date(order.verified_at).toLocaleString()}
                          </p>
                        </div>
                      ) : (
                        <div className="rounded-md border border-yellow-500/30 bg-yellow-500/5 p-2 text-xs text-yellow-700 dark:text-yellow-400">
                          Awaiting verification
                        </div>
                      )}
                      {order.amendment_reason && (
                        <div className="rounded-md border border-orange-500/30 bg-orange-500/5 p-2 text-xs text-orange-500">
                          Amended: {order.amendment_reason}
                        </div>
                      )}
                      <div className="rounded-md border p-3 space-y-2 text-sm">
                        <div>
                          <p className="text-xs text-muted-foreground mb-0.5">Report</p>
                          <p className="whitespace-pre-wrap">{order.report}</p>
                        </div>
                        {order.impression && (
                          <div>
                            <p className="text-xs text-muted-foreground mb-0.5">Impression</p>
                            <p className="font-medium">{order.impression}</p>
                          </div>
                        )}
                        {order.findings && (
                          <div>
                            <p className="text-xs text-muted-foreground mb-0.5">Findings</p>
                            <p className="whitespace-pre-wrap text-xs">{order.findings}</p>
                          </div>
                        )}
                        <p className="text-xs text-muted-foreground">
                          Reported by {order.radiologist_id} · {elapsed(order.reported_at)} ago
                          {order.tat_minutes != null && ` · TAT ${order.tat_minutes}m`}
                        </p>
                      </div>

                      <ViewReportButton kind="scan" orderIds={[order.id]} className="w-full" label="View report (print)" />

                      {!order.verified_at && (
                        <Button size="sm" variant="outline" className="w-full" onClick={() => setReportMode("edit")}>
                          Edit Report
                        </Button>
                      )}
                      {!!order.verified_at && (
                        <Button size="sm" variant="ghost" className="w-full text-orange-500" onClick={() => setReportMode("amend")}>
                          Amend Report…
                        </Button>
                      )}
                    </section>
                  ) : (
                    <section className="space-y-3">
                      {reportMode === "amend" && (
                        <div className="rounded-md border border-orange-500/30 bg-orange-500/5 p-2 text-xs text-orange-500">
                          Amending a verified report — the prior report stays on record and this creates a new, unverified version.
                        </div>
                      )}
                      <div className="space-y-1">
                        <Label>Radiologist</Label>
                        <Input value={reportForm.radiologist_id}
                          onChange={e => setReportForm(f => ({ ...f, radiologist_id: e.target.value }))}
                          placeholder="Radiologist name / ID" />
                      </div>
                      {templates.length > 0 && (
                        <div className="space-y-1">
                          <Label>Load Template</Label>
                          <div className="flex gap-2">
                            <Select value={templateId} onValueChange={setTemplateId}>
                              <SelectTrigger className="flex-1"><SelectValue placeholder="Choose a canned-findings template…" /></SelectTrigger>
                              <SelectContent>
                                {templates.map((t: any) => <SelectItem key={t.id} value={String(t.id)}>{t.variant_name}</SelectItem>)}
                              </SelectContent>
                            </Select>
                            <Button type="button" size="sm" variant="outline" disabled={!templateId}
                              onClick={() => {
                                const t = templates.find((x: any) => String(x.id) === templateId);
                                if (t) setReportForm(f => ({ ...f, report: t.template_text }));
                              }}>
                              <FileText className="h-3.5 w-3.5 mr-1" /> Load
                            </Button>
                          </div>
                        </div>
                      )}
                      {prefill?.based_on && (
                        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-primary/30 bg-primary/5 p-2 text-xs">
                          <span>Pre-filled from {prefill.based_on}. Fill in the <b>___</b> blanks and change anything that differs for this patient.</span>
                          <Button type="button" size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={applyPrefill}>Reset to standard</Button>
                        </div>
                      )}
                      {phrases.length > 0 && (
                        <div className="space-y-1">
                          <Label>Common phrases for this study (click to add)</Label>
                          <div className="flex flex-wrap gap-1.5">
                            {phrases.slice(0, 16).map((ph, i) => (
                              <button key={i} type="button" title={ph.text}
                                className="max-w-full truncate rounded-full border px-2.5 py-0.5 text-xs hover:bg-muted"
                                onClick={() => setReportForm((f) => ({ ...f, report: (f.report ? f.report.replace(/\s*$/, "\n") : "") + ph.text }))}>
                                <span className="font-semibold">{ph.section}:</span> {ph.text.length > 70 ? ph.text.slice(0, 70) + "\u2026" : ph.text}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                      <div className="space-y-1">
                        <Label>Report *{blanks > 0 && <span className="ml-2 font-normal text-amber-700 dark:text-amber-400">{blanks} blank{blanks === 1 ? "" : "s"} to fill</span>}</Label>
                        <Textarea rows={14} value={reportForm.report} data-tour-id="radiology-report-text"
                          onChange={e => setReportForm(f => ({ ...f, report: e.target.value }))}
                          placeholder="Detailed radiological findings..." className="font-mono text-sm" />
                      </div>
                      <div className="space-y-1">
                        <Label>Impression / Conclusion</Label>
                        <Textarea rows={3} value={reportForm.impression}
                          onChange={e => setReportForm(f => ({ ...f, impression: e.target.value }))}
                          placeholder="Brief impression and clinical recommendation..." />
                      </div>
                      <div className="space-y-1">
                        <Label>Structured Findings</Label>
                        <Textarea rows={2} value={reportForm.findings}
                          onChange={e => setReportForm(f => ({ ...f, findings: e.target.value }))}
                          placeholder="Optional structured findings..." />
                      </div>
                      {reportMode === "amend" && (
                        <div className="space-y-1">
                          <Label>Amendment Reason *</Label>
                          <Textarea rows={2} value={amendReason} onChange={e => setAmendReason(e.target.value)}
                            placeholder="Why is this report being corrected?" />
                        </div>
                      )}
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" className="flex-1" onClick={() => setReportMode("view")}>Cancel</Button>
                        <Button size="sm" className="flex-1 gap-1.5"
                          disabled={
                            !reportFormValid ||
                            (reportMode === "amend" ? !amendReason.trim() || amendMut.isPending : reportMut.isPending)
                          }
                          onClick={() => { if (!confirmBlanks()) return; reportMode === "amend" ? amendMut.mutate() : reportMut.mutate(); }}>
                          {(reportMode === "amend" ? amendMut.isPending : reportMut.isPending) && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                          {reportMode === "amend" ? "Save Amendment" : "Save Report"}
                        </Button>
                      </div>
                    </section>
                  )}
                </TabsContent>

                {/* ── History ── */}
                <TabsContent value="history" className="mt-0 space-y-4">
                  <section className="space-y-2">
                    <SectionLabel icon={<History className="h-3.5 w-3.5" />} label="Amendment Trail — This Order" />
                    {reportHistory.length === 0 ? (
                      <p className="text-xs text-muted-foreground">No amendments — current report is the original.</p>
                    ) : (
                      <div className="space-y-2">
                        {reportHistory.map((v: any, i: number) => (
                          <div key={i} className="rounded-md border p-2 text-xs space-y-0.5">
                            <div className="flex items-center justify-between">
                              <span className="font-medium">{v.impression ?? v.report?.slice(0, 60) ?? "—"}</span>
                              {v.verified_at
                                ? <Badge variant="outline" className="text-xs text-green-700 dark:text-green-400 border-green-500/30">was verified</Badge>
                                : <Badge variant="outline" className="text-xs text-yellow-700 dark:text-yellow-400 border-yellow-500/30">unverified</Badge>}
                            </div>
                            <p className="text-muted-foreground">{elapsed(v.superseded_at)} ago, by {v.radiologist_id}</p>
                            {v.amendment_reason && <p className="text-orange-500">Amended: {v.amendment_reason}</p>}
                          </div>
                        ))}
                      </div>
                    )}
                  </section>
                  <Separator />
                  <section className="space-y-2">
                    <SectionLabel icon={<ScanLine className="h-3.5 w-3.5" />} label="Patient's Other Imaging Studies" />
                    {patientHistory.length === 0 ? (
                      <p className="text-xs text-muted-foreground">No other imaging studies for this patient.</p>
                    ) : (
                      <ul className="text-xs text-muted-foreground space-y-1">
                        {patientHistory.slice(0, 8).map((h: any) => (
                          <li key={h.id} className="flex justify-between">
                            <span>{h.modality?.toUpperCase()} {h.body_part ? `— ${h.body_part}` : ""}</span>
                            <span>{h.impression ?? h.status}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>
                </TabsContent>
              </div>
            </Tabs>

            {/* Footer action bar */}
            <Separator className="shrink-0" />
            <div className="px-5 py-3 flex flex-wrap gap-2 shrink-0">
              {canSchedule && (
                <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setTab("detail")}>
                  <CalendarClock className="h-3.5 w-3.5" /> Schedule
                </Button>
              )}
              {canStart && (
                <Button size="sm" variant="outline" className="gap-1.5" disabled={startMut.isPending} onClick={() => startMut.mutate()}>
                  {startMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />} Start Scan
                </Button>
              )}
              {canReport && (
                <Button size="sm" className="gap-1.5" onClick={() => { setTab("report"); setReportMode("edit"); }}>
                  <FileText className="h-3.5 w-3.5" /> Submit Report
                </Button>
              )}
              {canEditReport && reportMode === "view" && (
                <Button size="sm" variant="outline" className="gap-1.5" onClick={() => { setTab("report"); setReportMode("edit"); }}>
                  <FileText className="h-3.5 w-3.5" /> Edit Report
                </Button>
              )}
              {canVerify && (
                <Button size="sm" className="gap-1.5 bg-green-600 hover:bg-green-700" data-tour-id="radiology-verify-button"
                  disabled={verifyMut.isPending}
                  onClick={() => { if (window.confirm("Verify and finalize this report? Once verified it can only be corrected via an amendment.")) verifyMut.mutate(); }}>
                  {verifyMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />} Verify & Finalize
                </Button>
              )}
              {canAmend && reportMode === "view" && (
                <Button size="sm" variant="outline" className="gap-1.5 text-orange-500 border-orange-500/30"
                  onClick={() => { setTab("report"); setReportMode("amend"); }}>
                  Amend Report
                </Button>
              )}
              <Button size="sm" variant="ghost" className="gap-1.5 ml-auto"
                disabled={!order.patient_mrn}
                onClick={() => { if (order.patient_mrn) { navigate(`/hospital/patients/${order.patient_mrn}`); onClose(); } }}>
                <ExternalLink className="h-3.5 w-3.5" /> Open Patient Record
              </Button>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function LoadingSkeleton() {
  return (
    <div className="p-5 space-y-4">
      <div className="flex items-center gap-3">
        <Skeleton className="h-10 w-10 rounded-full" />
        <div className="space-y-2 flex-1"><Skeleton className="h-4 w-40" /><Skeleton className="h-3 w-28" /></div>
      </div>
      <Skeleton className="h-16 w-full" />
      <Skeleton className="h-20 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}
