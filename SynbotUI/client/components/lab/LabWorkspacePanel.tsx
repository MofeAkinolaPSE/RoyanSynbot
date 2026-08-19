import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  User, FlaskConical, TestTube, Droplets, SendHorizonal, ShieldCheck,
  History, Upload, Eye, ExternalLink, Loader2, XCircle, CheckCircle2,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import {
  StatusBadge, UrgencyBadge, WorkflowProgress, DetailRow, elapsed,
  SpecimenStatusBadge, SPECIMEN_TYPES,
} from "@/components/lab/lab-shared";

interface LabWorkspacePanelProps {
  order: {
    id: string | number;
    patient_id?: string | number;
    patient_mrn?: string;
    patient_name?: string;
    patient_gender?: string;
    patient_dob?: string;
    test_name?: string;
    loinc_code?: string;
    urgency?: string;
    status?: string;
    ordered_at?: string;
    sample_type?: string;
  };
  onClose: () => void;
  initialTab?: string;
}

const emptyCollect = { specimen_type: "", container: "", volume: "", specimen_label: "", collected_by: "", notes: "" };
const emptySendOut = { external_lab: "", notes: "" };
const emptyResultForm = { result_value: "", result_unit: "", reference_range: "", is_critical: false, notes: "" };

export function LabWorkspacePanel({ order: initialOrder, onClose, initialTab }: LabWorkspacePanelProps) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState(initialTab ?? "detail");

  const [collectForm, setCollectForm] = useState({ ...emptyCollect });
  const [sendOutForm, setSendOutForm] = useState({ ...emptySendOut });
  const [resultForm, setResultForm] = useState({ ...emptyResultForm });
  const [analyteValues, setAnalyteValues] = useState<Array<{ name: string; unit?: string; observed_value: string; comment: string }>>([]);
  const [resultMode, setResultMode] = useState<"view" | "edit" | "amend">("view");
  const [amendReason, setAmendReason] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);

  const orderId = String(initialOrder.id);

  const { data, isLoading } = useQuery({
    queryKey: ["lab-panel-order", orderId],
    queryFn: () => api.hospital.lab.getOrder(orderId),
    refetchInterval: 15_000,
  });
  const order: typeof initialOrder & Record<string, any> = { ...initialOrder, ...(data?.order ?? {}) };
  const result: any = data?.result ?? null;
  const specimens: any[] = data?.specimens ?? [];

  const { data: versionsData } = useQuery({
    queryKey: ["lab-panel-result-versions", orderId],
    queryFn: () => api.hospital.lab.getResultVersions(orderId),
    enabled: tab === "history",
  });
  const resultVersions: any[] = versionsData?.results ?? [];

  const { data: historyData } = useQuery({
    queryKey: ["lab-panel-patient-history", order.patient_id],
    queryFn: () => api.hospital.lab.patientHistory(order.patient_id!),
    enabled: tab === "history" && !!order.patient_id,
  });
  const patientHistory: any[] = (historyData?.history ?? []).filter((h: any) => String(h.id) !== orderId);

  const { data: templateData } = useQuery({
    queryKey: ["lab-panel-template", order.test_name],
    queryFn: () => api.hospital.lab.getTemplateForTest(order.test_name!),
    enabled: !!order.test_name && (tab === "result"),
    staleTime: 60_000,
  });
  const template: any = templateData?.template ?? null;

  // Sync the result form to whichever result row is being edited/amended
  useEffect(() => {
    if (resultMode === "view") return;
    if (template?.analytes?.length) {
      const existingAnalytes: any[] = result?.result_data?.analytes ?? [];
      setAnalyteValues(template.analytes.map((a: any) => {
        const prior = existingAnalytes.find((e: any) => e.name === a.name);
        return {
          name: a.name, unit: a.unit,
          observed_value: resultMode === "edit" ? (prior?.observed_value ?? "") : "",
          comment: resultMode === "edit" ? (prior?.comment ?? "") : "",
        };
      }));
    } else {
      setAnalyteValues([]);
    }
    if (resultMode === "edit" && result) {
      setResultForm({
        result_value: result.result_data?.value ?? "",
        result_unit: result.result_data?.unit ?? "",
        reference_range: result.reference_range ?? "",
        is_critical: !!result.is_critical,
        notes: result.notes ?? "",
      });
    } else if (resultMode === "amend") {
      setResultForm({ ...emptyResultForm });
      setAmendReason("");
    }
  }, [resultMode, template, result]);

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ["lab-panel-order", orderId] });
    void qc.invalidateQueries({ queryKey: ["lab-panel-result-versions", orderId] });
    void qc.invalidateQueries({ queryKey: ["lab-orders"] });
    void qc.invalidateQueries({ queryKey: ["lab-stats"] });
    void qc.invalidateQueries({ queryKey: ["lab-critical"] });
  };

  const collectMut = useMutation({
    mutationFn: () => api.hospital.lab.collect(orderId, {
      specimen_type: collectForm.specimen_type || undefined,
      container: collectForm.container || undefined,
      volume: collectForm.volume || undefined,
      specimen_label: collectForm.specimen_label || undefined,
      collected_by: collectForm.collected_by || undefined,
      notes: collectForm.notes || undefined,
    }),
    onSuccess: () => {
      toast({ title: "Specimen collected" });
      setCollectForm({ ...emptyCollect });
      invalidateAll();
    },
    onError: (e: any) => toast({ title: "Failed to collect specimen", description: e.message, variant: "destructive" }),
  });

  const receiveMut = useMutation({
    mutationFn: () => api.hospital.lab.receive(orderId, {}),
    onSuccess: () => { toast({ title: "Specimen received — processing started" }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Failed to receive specimen", description: e.message, variant: "destructive" }),
  });

  const rejectMut = useMutation({
    mutationFn: (reason: string) => api.hospital.lab.reject(orderId, { rejection_reason: reason }),
    onSuccess: () => { toast({ title: "Specimen rejected — order reopened for redraw" }); setTab("specimen"); invalidateAll(); },
    onError: (e: any) => toast({ title: "Failed to reject specimen", description: e.message, variant: "destructive" }),
  });

  const sendOutMut = useMutation({
    mutationFn: () => api.hospital.lab.sendOut(orderId, sendOutForm),
    onSuccess: () => { toast({ title: "Order sent out" }); setSendOutForm({ ...emptySendOut }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Failed to send out", description: e.message, variant: "destructive" }),
  });

  function buildResultPayload() {
    if (template?.analytes?.length) {
      return {
        analyte_values: analyteValues.map(a => ({
          name: a.name, observed_value: a.observed_value || undefined,
          unit: a.unit, comment: a.comment || undefined,
        })),
        notes: resultForm.notes || undefined,
      };
    }
    return {
      result_value: resultForm.result_value,
      result_unit: resultForm.result_unit,
      reference_range: resultForm.reference_range || undefined,
      is_critical: resultForm.is_critical,
      notes: resultForm.notes || undefined,
    };
  }

  const resultMut = useMutation({
    mutationFn: () => api.hospital.lab.recordResult(orderId, buildResultPayload()),
    onSuccess: () => {
      toast({ title: "Result saved" });
      setResultMode("view");
      invalidateAll();
    },
    onError: (e: any) => toast({ title: "Failed to save result", description: e.message, variant: "destructive" }),
  });

  const amendMut = useMutation({
    mutationFn: () => api.hospital.lab.amendResult(orderId, { ...buildResultPayload(), amendment_reason: amendReason }),
    onSuccess: () => {
      toast({ title: "Result amended" });
      setResultMode("view");
      invalidateAll();
    },
    onError: (e: any) => toast({ title: "Failed to amend result", description: e.message, variant: "destructive" }),
  });

  const verifyMut = useMutation({
    mutationFn: () => api.hospital.lab.verify(orderId, {}),
    onSuccess: () => { toast({ title: "Result verified and authenticated" }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Failed to verify", description: e.message, variant: "destructive" }),
  });

  async function handleUploadReport() {
    if (!uploadFile) return;
    setUploading(true);
    try {
      await api.hospital.lab.uploadReport(orderId, uploadFile);
      toast({ title: "Report uploaded" });
      setUploadFile(null);
      invalidateAll();
    } catch (e: any) {
      toast({ title: "Upload failed", description: e.message, variant: "destructive" });
    } finally {
      setUploading(false);
    }
  }

  const status = order.status;
  const canCollect   = status === "ordered";
  const canReceive   = status === "sample_collected";
  const canReject    = ["sample_collected", "processing"].includes(status ?? "");
  const canSendOut   = !["resulted", "sent_out", "cancelled"].includes(status ?? "") && !result;
  const canRecordResult = !result && ["processing", "sent_out"].includes(status ?? "");
  const canVerify    = !!result && !result.verified_at;
  const canAmend     = !!result && !!result.verified_at;
  const resultFormValid = template?.analytes?.length
    ? analyteValues.some(a => a.observed_value.trim())
    : !!resultForm.result_value.trim();

  return (
    <Sheet open onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className="w-[560px] sm:w-[640px] overflow-y-auto p-0 flex flex-col" side="right">
        {isLoading && !data ? (
          <LoadingSkeleton />
        ) : (
          <>
            {/* Header */}
            <SheetHeader className="px-5 pt-5 pb-4 border-b shrink-0">
              <div className="flex items-start gap-3">
                <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                  <FlaskConical className="h-5 w-5 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <SheetTitle className="text-base leading-tight">{order.test_name ?? "Lab Order"}</SheetTitle>
                  <div className="flex flex-wrap items-center gap-2 mt-1">
                    <span className="text-xs text-muted-foreground">{order.patient_name ?? `Patient ID ${order.patient_id}`}</span>
                    {order.patient_mrn && <Badge variant="outline" className="text-xs font-mono">{order.patient_mrn}</Badge>}
                    <UrgencyBadge urgency={order.urgency} />
                    <StatusBadge status={status} />
                    {result?.is_critical && (
                      <Badge variant="outline" className="text-xs text-red-700 dark:text-red-400 border-red-500/30 bg-red-500/10 animate-pulse">Critical</Badge>
                    )}
                  </div>
                  <p className="text-[13px] text-muted-foreground mt-1">Order #{order.id} · Ordered {elapsed(order.ordered_at)} ago</p>
                </div>
              </div>
            </SheetHeader>

            {/* Tabs */}
            <Tabs value={tab} onValueChange={setTab} className="flex-1 flex flex-col min-h-0">
              <TabsList className="mx-5 mt-3 bg-muted border border-border shrink-0 flex-wrap h-auto">
                <TabsTrigger value="detail">Detail</TabsTrigger>
                <TabsTrigger value="specimen">Specimen</TabsTrigger>
                <TabsTrigger value="result">Result</TabsTrigger>
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
                    <SectionLabel icon={<FlaskConical className="h-3.5 w-3.5" />} label="Order Details" />
                    <DetailRow label="Test"        value={order.test_name} />
                    <DetailRow label="LOINC Code"  value={order.loinc_code} mono />
                    <DetailRow label="Sample Type" value={order.sample_type} />
                    <DetailRow label="Ordered by"  value={order.ordered_by} mono />
                    <DetailRow label="Ordered at"  value={order.ordered_at
                      ? new Date(order.ordered_at).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
                      : undefined}
                    />
                    {status === "sent_out" && order.external_lab && (
                      <DetailRow label="Sent to" value={order.external_lab} accent="text-cyan-700 dark:text-cyan-400" />
                    )}
                  </section>
                  <Separator />
                  <section>
                    <SectionLabel icon={<ShieldCheck className="h-3.5 w-3.5" />} label="Workflow" />
                    <WorkflowProgress status={status} verified={!!result?.verified_at} />
                  </section>
                  {canSendOut && (
                    <>
                      <Separator />
                      <section className="space-y-2">
                        <SectionLabel icon={<SendHorizonal className="h-3.5 w-3.5" />} label="Send to External Lab" />
                        <Input placeholder="External lab name, e.g. MLSCN Lagos" value={sendOutForm.external_lab}
                          onChange={e => setSendOutForm(f => ({ ...f, external_lab: e.target.value }))} />
                        <Input placeholder="Notes (optional)" value={sendOutForm.notes}
                          onChange={e => setSendOutForm(f => ({ ...f, notes: e.target.value }))} />
                        <Button size="sm" variant="outline" className="w-full gap-1.5 text-cyan-700 dark:text-cyan-400 border-cyan-500/30"
                          disabled={!sendOutForm.external_lab.trim() || sendOutMut.isPending}
                          onClick={() => sendOutMut.mutate()}>
                          {sendOutMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <SendHorizonal className="h-3.5 w-3.5" />}
                          Send Out
                        </Button>
                      </section>
                    </>
                  )}
                </TabsContent>

                {/* ── Specimen ── */}
                <TabsContent value="specimen" className="mt-0 space-y-4">
                  <section className="space-y-2">
                    <SectionLabel icon={<TestTube className="h-3.5 w-3.5" />} label="Specimen History" />
                    {specimens.length === 0 ? (
                      <p className="text-xs text-muted-foreground">No specimen collected yet.</p>
                    ) : (
                      <div className="space-y-2">
                        {specimens.map((s: any) => (
                          <div key={s.id} className="rounded-md border p-2 text-xs space-y-1">
                            <div className="flex items-center justify-between">
                              <span className="font-medium capitalize">{s.specimen_type}{s.specimen_label ? ` · ${s.specimen_label}` : ""}</span>
                              <SpecimenStatusBadge status={s.status} />
                            </div>
                            <div className="text-muted-foreground">
                              {[s.container, s.volume].filter(Boolean).join(" · ") || "—"}
                            </div>
                            <div className="text-muted-foreground">
                              Collected by {s.collected_by ?? "—"} · {elapsed(s.collected_at)} ago
                              {s.received_at && ` · received ${elapsed(s.received_at)} ago`}
                            </div>
                            {s.rejection_reason && (
                              <p className="text-red-700 dark:text-red-400">Rejected: {s.rejection_reason}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </section>
                  {canCollect && (
                    <>
                      <Separator />
                      <section className="space-y-2">
                        <SectionLabel icon={<Droplets className="h-3.5 w-3.5" />} label="Collect Specimen" />
                        <div className="grid grid-cols-2 gap-2">
                          <Select value={collectForm.specimen_type} onValueChange={v => setCollectForm(f => ({ ...f, specimen_type: v }))}>
                            <SelectTrigger><SelectValue placeholder="Specimen type" /></SelectTrigger>
                            <SelectContent>
                              {SPECIMEN_TYPES.map(t => <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>)}
                            </SelectContent>
                          </Select>
                          <Input placeholder="Container" value={collectForm.container}
                            onChange={e => setCollectForm(f => ({ ...f, container: e.target.value }))} />
                          <Input placeholder="Volume, e.g. 5mL" value={collectForm.volume}
                            onChange={e => setCollectForm(f => ({ ...f, volume: e.target.value }))} />
                          <Input placeholder="Specimen label" value={collectForm.specimen_label}
                            onChange={e => setCollectForm(f => ({ ...f, specimen_label: e.target.value }))} />
                        </div>
                        <Input placeholder="Collected by (defaults to you)" value={collectForm.collected_by}
                          onChange={e => setCollectForm(f => ({ ...f, collected_by: e.target.value }))} />
                        <Textarea rows={2} placeholder="Notes (optional)" value={collectForm.notes}
                          onChange={e => setCollectForm(f => ({ ...f, notes: e.target.value }))} />
                        <Button size="sm" className="w-full gap-1.5" disabled={collectMut.isPending} onClick={() => collectMut.mutate()}>
                          {collectMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Droplets className="h-3.5 w-3.5" />}
                          Collect Specimen
                        </Button>
                      </section>
                    </>
                  )}
                </TabsContent>

                {/* ── Result ── */}
                <TabsContent value="result" className="mt-0 space-y-4">
                  {result && resultMode === "view" ? (
                    <section className="space-y-3">
                      {result.verified_at ? (
                        <div className="rounded-md border border-green-500/30 bg-green-500/5 p-3 space-y-1">
                          <div className="flex items-center gap-1.5 text-green-700 dark:text-green-400 text-sm font-medium">
                            <CheckCircle2 className="h-4 w-4" /> Verified & Authenticated
                          </div>
                          <p className="text-xs text-muted-foreground">
                            By {result.verified_by} · {new Date(result.verified_at).toLocaleString()}
                          </p>
                        </div>
                      ) : (
                        <div className="rounded-md border border-yellow-500/30 bg-yellow-500/5 p-2 text-xs text-yellow-700 dark:text-yellow-400">
                          Awaiting verification
                        </div>
                      )}
                      <div className="rounded-md border p-3 space-y-1 text-sm">
                        <p className="font-medium">{result.result_summary ?? "—"}</p>
                        {result.interpretation && (
                          <Badge variant="outline" className="text-xs capitalize">{result.interpretation}</Badge>
                        )}
                        {result.reference_range && (
                          <p className="text-xs text-muted-foreground">Reference: {result.reference_range}</p>
                        )}
                        {result.notes && <p className="text-xs text-muted-foreground">{result.notes}</p>}
                        <p className="text-[13px] text-muted-foreground">Resulted by {result.resulted_by} · {elapsed(result.resulted_at)} ago</p>
                      </div>

                      {!result.verified_at && (
                        <Button size="sm" variant="outline" className="w-full" onClick={() => setResultMode("edit")}>
                          Edit Result
                        </Button>
                      )}

                      {result.verified_at && (
                        <>
                          <Separator />
                          <section className="space-y-2">
                            <SectionLabel icon={<Upload className="h-3.5 w-3.5" />} label="Lab Report" />
                            {result.report_file_url ? (
                              <Button size="sm" variant="outline" className="w-full gap-1.5"
                                onClick={() => window.open(api.hospital.lab.reportUrl(result.report_file_url.split("/").pop()), "_blank")}>
                                <Eye className="h-3.5 w-3.5" /> View Report
                              </Button>
                            ) : (
                              <div className="space-y-2">
                                <Input type="file" accept=".pdf,.jpg,.jpeg,.png,.webp"
                                  onChange={e => setUploadFile(e.target.files?.[0] ?? null)} className="cursor-pointer text-xs" />
                                <Button size="sm" variant="outline" className="w-full gap-1.5"
                                  disabled={!uploadFile || uploading} onClick={handleUploadReport}>
                                  {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
                                  {uploading ? "Uploading…" : "Upload Report"}
                                </Button>
                              </div>
                            )}
                          </section>
                          <Separator />
                          <Button size="sm" variant="ghost" className="w-full text-orange-500" onClick={() => setResultMode("amend")}>
                            Amend Result…
                          </Button>
                        </>
                      )}
                    </section>
                  ) : (
                    <section className="space-y-3">
                      {resultMode === "amend" && (
                        <div className="rounded-md border border-orange-500/30 bg-orange-500/5 p-2 text-xs text-orange-500">
                          Amending a verified result — the prior result stays on record and this creates a new, unverified version.
                        </div>
                      )}
                      {template?.analytes?.length ? (
                        <div className="space-y-3">
                          <p className="text-xs text-muted-foreground">
                            Using template: <span className="font-medium text-foreground">{template.test_name}</span> (v{template.version})
                          </p>
                          {analyteValues.map((row, i) => (
                            <div key={row.name} className="grid grid-cols-[1fr_90px] gap-2 items-end border-b pb-2">
                              <div className="space-y-1">
                                <Label>{row.name}</Label>
                                <Input value={row.observed_value}
                                  onChange={e => setAnalyteValues(vs => vs.map((v, j) => j === i ? { ...v, observed_value: e.target.value } : v))}
                                  placeholder="Observed value" />
                              </div>
                              <div className="space-y-1">
                                <Label>Unit</Label>
                                <Input value={row.unit ?? ""} readOnly className="bg-muted" />
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="space-y-3">
                          <div className="grid grid-cols-2 gap-2">
                            <div className="space-y-1">
                              <Label>Result Value *</Label>
                              <Input value={resultForm.result_value}
                                onChange={e => setResultForm(f => ({ ...f, result_value: e.target.value }))}
                                placeholder="e.g. 14.2" />
                            </div>
                            <div className="space-y-1">
                              <Label>Unit</Label>
                              <Input value={resultForm.result_unit}
                                onChange={e => setResultForm(f => ({ ...f, result_unit: e.target.value }))}
                                placeholder="e.g. g/dL" />
                            </div>
                          </div>
                          <div className="space-y-1">
                            <Label>Reference Range</Label>
                            <Input value={resultForm.reference_range}
                              onChange={e => setResultForm(f => ({ ...f, reference_range: e.target.value }))}
                              placeholder="e.g. 12.0–16.0 g/dL" />
                          </div>
                          <div className="flex items-center gap-2">
                            <Checkbox id="panel-is-critical" checked={resultForm.is_critical}
                              onCheckedChange={v => setResultForm(f => ({ ...f, is_critical: !!v }))} />
                            <Label htmlFor="panel-is-critical" className="cursor-pointer text-red-700 dark:text-red-400">Mark as Critical Result</Label>
                          </div>
                        </div>
                      )}
                      <div className="space-y-1">
                        <Label>Notes</Label>
                        <Textarea rows={2} value={resultForm.notes}
                          onChange={e => setResultForm(f => ({ ...f, notes: e.target.value }))} placeholder="Clinical notes..." />
                      </div>
                      {resultMode === "amend" && (
                        <div className="space-y-1">
                          <Label>Amendment Reason *</Label>
                          <Textarea rows={2} value={amendReason} onChange={e => setAmendReason(e.target.value)}
                            placeholder="Why is this result being corrected?" />
                        </div>
                      )}
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" className="flex-1"
                          onClick={() => setResultMode("view")}>Cancel</Button>
                        <Button size="sm" className="flex-1 gap-1.5"
                          disabled={
                            !resultFormValid ||
                            (resultMode === "amend" ? !amendReason.trim() || amendMut.isPending : resultMut.isPending)
                          }
                          onClick={() => resultMode === "amend" ? amendMut.mutate() : resultMut.mutate()}>
                          {(resultMode === "amend" ? amendMut.isPending : resultMut.isPending) && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                          {resultMode === "amend" ? "Save Amendment" : "Save Result"}
                        </Button>
                      </div>
                    </section>
                  )}
                </TabsContent>

                {/* ── History ── */}
                <TabsContent value="history" className="mt-0 space-y-4">
                  <section className="space-y-2">
                    <SectionLabel icon={<History className="h-3.5 w-3.5" />} label="Amendment Trail — This Order" />
                    {resultVersions.length === 0 ? (
                      <p className="text-xs text-muted-foreground">No results recorded yet.</p>
                    ) : (
                      <div className="space-y-2">
                        {resultVersions.map((v: any) => (
                          <div key={v.id} className="rounded-md border p-2 text-xs space-y-0.5">
                            <div className="flex items-center justify-between">
                              <span className="font-medium">{v.result_summary ?? "—"}</span>
                              {v.verified_at
                                ? <Badge variant="outline" className="text-[12px] text-green-700 dark:text-green-400 border-green-500/30">verified</Badge>
                                : <Badge variant="outline" className="text-[12px] text-yellow-700 dark:text-yellow-400 border-yellow-500/30">unverified</Badge>}
                            </div>
                            <p className="text-muted-foreground">{elapsed(v.resulted_at)} ago by {v.resulted_by}</p>
                            {v.amendment_reason && <p className="text-orange-500">Amended: {v.amendment_reason}</p>}
                          </div>
                        ))}
                      </div>
                    )}
                  </section>
                  <Separator />
                  <section className="space-y-2">
                    <SectionLabel icon={<FlaskConical className="h-3.5 w-3.5" />} label="Patient's Other Lab Results" />
                    {patientHistory.length === 0 ? (
                      <p className="text-xs text-muted-foreground">No other resulted lab tests for this patient.</p>
                    ) : (
                      <ul className="text-xs text-muted-foreground space-y-1">
                        {patientHistory.slice(0, 8).map((h: any) => (
                          <li key={h.id} className="flex justify-between">
                            <span>{h.test_name}</span>
                            <span>{h.result_summary ?? "—"}</span>
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
              {canCollect && (
                <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setTab("specimen")}>
                  <Droplets className="h-3.5 w-3.5" /> Collect Specimen
                </Button>
              )}
              {canReceive && (
                <Button size="sm" variant="outline" className="gap-1.5" disabled={receiveMut.isPending} onClick={() => receiveMut.mutate()}>
                  {receiveMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <TestTube className="h-3.5 w-3.5" />} Receive Specimen
                </Button>
              )}
              {canReject && (
                <Button size="sm" variant="outline" className="gap-1.5 text-red-500 border-red-500/30 hover:bg-red-500/10"
                  disabled={rejectMut.isPending}
                  onClick={() => { const reason = window.prompt("Rejection reason:"); if (reason && reason.trim()) rejectMut.mutate(reason.trim()); }}>
                  <XCircle className="h-3.5 w-3.5" /> Reject Specimen
                </Button>
              )}
              {canSendOut && (
                <Button size="sm" variant="outline" className="gap-1.5 text-cyan-700 dark:text-cyan-400 border-cyan-500/30" onClick={() => setTab("detail")}>
                  <SendHorizonal className="h-3.5 w-3.5" /> Send Out
                </Button>
              )}
              {canRecordResult && (
                <Button size="sm" className="gap-1.5" onClick={() => { setTab("result"); setResultMode("edit"); }}>
                  <FlaskConical className="h-3.5 w-3.5" /> Record Result
                </Button>
              )}
              {canVerify && (
                <Button size="sm" className="gap-1.5 bg-green-600 hover:bg-green-700"
                  disabled={verifyMut.isPending}
                  onClick={() => { if (window.confirm("Verify and authenticate this result? Once verified it can only be corrected via an amendment.")) verifyMut.mutate(); }}>
                  {verifyMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />} Verify & Authenticate
                </Button>
              )}
              {canAmend && resultMode === "view" && (
                <Button size="sm" variant="outline" className="gap-1.5 text-orange-500 border-orange-500/30"
                  onClick={() => { setTab("result"); setResultMode("amend"); }}>
                  Amend Result
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

function SectionLabel({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <span className="text-muted-foreground">{icon}</span>
      <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{label}</span>
    </div>
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
