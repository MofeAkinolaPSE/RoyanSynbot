import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Wrench, ClipboardList, RefreshCw, Loader2, Plus, CheckCircle2,
  PlayCircle, AlertTriangle, FileText,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";

// Small, per-file helper duplication (matches Compliance.tsx's own
// statusBadge/severityBadge shape, extended for this schema's vocab).
function statusBadge(status: string) {
  const map: Record<string, string> = {
    scheduled:   "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30",
    in_progress: "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
    completed:   "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
    pending:     "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
  };
  const cls = map[status?.toLowerCase()] ?? "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30";
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold", cls)}>
      {status?.replace(/_/g, " ")}
    </span>
  );
}

function riskBadge(risk: string) {
  const map: Record<string, string> = {
    critical: "bg-red-600/25 text-red-700 dark:text-red-300 border-red-600/40",
    high:     "bg-orange-500/25 text-orange-700 dark:text-orange-300 border-orange-500/40",
    medium:   "bg-yellow-500/25 text-yellow-700 dark:text-yellow-300 border-yellow-500/40",
    low:      "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30",
  };
  const cls = map[risk?.toLowerCase()] ?? "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30";
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold capitalize", cls)}>
      {risk}
    </span>
  );
}

function formatDate(d?: string | null) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

const RISK_LEVELS = ["low", "medium", "high", "critical"];
const MAINTENANCE_TYPES = ["preventive", "corrective", "calibration", "emergency"];

const emptyAudit = { audit_title: "", department: "", scheduled_date: "", risk_level: "medium" };
const emptyMaintenance = {
  equipment_name: "", equipment_type: "", location: "",
  maintenance_type: "preventive", description: "", due_date: "",
};
const emptyAuditComplete = { findings: "", recommendations: "", score: "" };
const emptyMaintenanceComplete = { completion_notes: "", next_due_date: "" };

export default function AuditsMaintenance() {
  const { toast } = useToast();
  const qc = useQueryClient();

  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [auditForm, setAuditForm] = useState({ ...emptyAudit });

  const [addTaskOpen, setAddTaskOpen] = useState(false);
  const [taskForm, setTaskForm] = useState({ ...emptyMaintenance });

  const [completeAuditId, setCompleteAuditId] = useState<string | null>(null);
  const [auditCompleteForm, setAuditCompleteForm] = useState({ ...emptyAuditComplete });

  const [completeTaskId, setCompleteTaskId] = useState<string | null>(null);
  const [taskCompleteForm, setTaskCompleteForm] = useState({ ...emptyMaintenanceComplete });

  const [maintFilter, setMaintFilter] = useState<"all" | "overdue" | "upcoming">("all");

  const { data: statsData } = useQuery({
    queryKey: ["facility-stats"],
    queryFn: () => api.facility.stats(),
  });

  const { data: auditsData, isFetching: auditsLoading, refetch: refetchAudits } = useQuery({
    queryKey: ["facility-audits"],
    queryFn: () => api.facility.listAudits(),
  });

  const { data: maintData, isFetching: maintLoading, refetch: refetchMaint } = useQuery({
    queryKey: ["facility-maintenance", maintFilter],
    queryFn: () => api.facility.listMaintenance(maintFilter),
  });

  const audits: any[] = auditsData?.audits ?? [];
  const tasks: any[] = maintData?.tasks ?? [];
  const auditsKpi = statsData?.audits ?? { total: 0, overdue: 0 };
  const maintKpi  = statsData?.maintenance ?? { total: 0, overdue: 0 };

  const scheduleMutation = useMutation({
    mutationFn: () => api.facility.createAudit(auditForm),
    onSuccess: () => {
      toast({ title: "Audit scheduled" });
      setScheduleOpen(false);
      setAuditForm({ ...emptyAudit });
      void qc.invalidateQueries({ queryKey: ["facility-audits"] });
      void qc.invalidateQueries({ queryKey: ["facility-stats"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const startMutation = useMutation({
    mutationFn: (id: string) => api.facility.startAudit(id),
    onSuccess: () => {
      toast({ title: "Audit started" });
      void qc.invalidateQueries({ queryKey: ["facility-audits"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const completeAuditMutation = useMutation({
    mutationFn: () => api.facility.completeAudit(completeAuditId!, {
      findings: auditCompleteForm.findings || undefined,
      recommendations: auditCompleteForm.recommendations || undefined,
      score: auditCompleteForm.score ? Number(auditCompleteForm.score) : undefined,
    }),
    onSuccess: () => {
      toast({ title: "Audit completed" });
      setCompleteAuditId(null);
      setAuditCompleteForm({ ...emptyAuditComplete });
      void qc.invalidateQueries({ queryKey: ["facility-audits"] });
      void qc.invalidateQueries({ queryKey: ["facility-stats"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const addTaskMutation = useMutation({
    mutationFn: () => api.facility.createMaintenance(taskForm),
    onSuccess: () => {
      toast({ title: "Maintenance task added" });
      setAddTaskOpen(false);
      setTaskForm({ ...emptyMaintenance });
      void qc.invalidateQueries({ queryKey: ["facility-maintenance"] });
      void qc.invalidateQueries({ queryKey: ["facility-stats"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const completeTaskMutation = useMutation({
    mutationFn: () => api.facility.completeMaintenance(completeTaskId!, {
      completion_notes: taskCompleteForm.completion_notes || undefined,
      next_due_date: taskCompleteForm.next_due_date || undefined,
    }),
    onSuccess: (res: any) => {
      toast({
        title: "Maintenance task completed",
        description: res?.next_task ? `Next occurrence scheduled for ${formatDate(res.next_task.due_date)}` : undefined,
      });
      setCompleteTaskId(null);
      setTaskCompleteForm({ ...emptyMaintenanceComplete });
      void qc.invalidateQueries({ queryKey: ["facility-maintenance"] });
      void qc.invalidateQueries({ queryKey: ["facility-stats"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const auditReportMutation = useMutation({
    mutationFn: (audit: any) => api.reports.generateDocx({
      report_type: "facility_audit",
      entity_id: audit.id,
      intent_text: `Generate a report for the facility audit: ${audit.audit_title}`,
    }),
    onSuccess: () => toast({ title: "Report downloaded" }),
    onError: (e: any) => toast({ title: "Report generation failed", description: e.message, variant: "destructive" }),
  });

  const maintCertMutation = useMutation({
    mutationFn: (task: any) => api.reports.generateDocx({
      report_type: "equipment_maintenance",
      entity_id: task.id,
      intent_text: `Generate a maintenance certificate for: ${task.equipment_name}`,
    }),
    onSuccess: () => toast({ title: "Certificate downloaded" }),
    onError: (e: any) => toast({ title: "Certificate generation failed", description: e.message, variant: "destructive" }),
  });

  return (
    <motion.div className="p-6 space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-emerald-500/20 rounded-lg">
            <Wrench className="w-6 h-6 text-emerald-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Audits &amp; Maintenance</h1>
            <p className="text-sm text-muted-foreground">Facility audits and equipment maintenance tracking</p>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap justify-end">
          <Button variant="outline" size="sm" className="border-border"
            onClick={() => { refetchAudits(); refetchMaint(); }}>
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button size="sm" variant="outline" className="border-blue-500/40 text-blue-700 dark:text-blue-400 hover:bg-blue-500/10"
            onClick={() => { setTaskForm({ ...emptyMaintenance }); setAddTaskOpen(true); }}>
            <Plus className="w-4 h-4 mr-1" /> Add Maintenance Task
          </Button>
          <Button size="sm" className="bg-emerald-700 hover:bg-emerald-800"
            onClick={() => { setAuditForm({ ...emptyAudit }); setScheduleOpen(true); }}>
            <Plus className="w-4 h-4 mr-1" /> Schedule Audit
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Total Audits",       value: auditsKpi.total,   color: "text-foreground",  bg: "bg-muted/30" },
          { label: "Audits Overdue",     value: auditsKpi.overdue, color: auditsKpi.overdue > 0 ? "text-red-700 dark:text-red-400" : "text-green-700 dark:text-green-400", bg: auditsKpi.overdue > 0 ? "bg-red-500/10" : "bg-green-500/10" },
          { label: "Maintenance Tasks",  value: maintKpi.total,    color: "text-foreground",  bg: "bg-muted/30" },
          { label: "Maintenance Overdue",value: maintKpi.overdue,  color: maintKpi.overdue > 0 ? "text-red-700 dark:text-red-400" : "text-green-700 dark:text-green-400", bg: maintKpi.overdue > 0 ? "bg-red-500/10" : "bg-green-500/10" },
        ].map(k => (
          <Card key={k.label} className={cn("border-border", k.bg)}>
            <CardContent className="pt-4 pb-3">
              <p className="text-xs text-muted-foreground uppercase tracking-wide">{k.label}</p>
              <p className={cn("text-2xl font-bold mt-1", k.color)}>{k.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Tabs */}
      <Tabs defaultValue="audits">
        <TabsList className="bg-muted border border-border">
          <TabsTrigger value="audits">Audits</TabsTrigger>
          <TabsTrigger value="maintenance">Maintenance</TabsTrigger>
        </TabsList>

        {/* Audits Tab */}
        <TabsContent value="audits" className="mt-4 space-y-4">
          <Card className="border-border bg-muted/30">
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  {["Title","Department","Scheduled","Risk","Status","Actions"].map(h => (
                    <TableHead key={h} className="text-muted-foreground text-xs">{h}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {auditsLoading
                  ? <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                      <Loader2 className="w-5 h-5 animate-spin inline mr-2" />Loading…
                    </TableCell></TableRow>
                  : audits.length === 0
                    ? <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No audits scheduled</TableCell></TableRow>
                    : audits.map((a: any) => (
                      <TableRow key={a.id} className="border-border hover:bg-muted">
                        <TableCell className="text-sm text-foreground font-medium">{a.audit_title}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{a.department}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {formatDate(a.scheduled_date)}
                          {a.is_overdue && <AlertTriangle className="inline w-3 h-3 ml-1 text-red-400" />}
                        </TableCell>
                        <TableCell>{riskBadge(a.risk_level)}</TableCell>
                        <TableCell>{statusBadge(a.status)}</TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            {a.status === "scheduled" && (
                              <Button size="sm" variant="outline" className="h-6 text-xs px-2 border-border"
                                disabled={startMutation.isPending}
                                onClick={() => startMutation.mutate(a.id)}>
                                <PlayCircle className="w-3 h-3 mr-1" /> Start
                              </Button>
                            )}
                            {a.status === "in_progress" && (
                              <Button size="sm" className="h-6 text-xs px-2 bg-green-700 hover:bg-green-600"
                                onClick={() => { setCompleteAuditId(a.id); setAuditCompleteForm({ ...emptyAuditComplete }); }}>
                                <CheckCircle2 className="w-3 h-3 mr-1" /> Complete
                              </Button>
                            )}
                            {a.status === "completed" && (
                              <Button size="sm" variant="outline" className="h-6 text-xs px-2 border-border"
                                disabled={auditReportMutation.isPending}
                                onClick={() => auditReportMutation.mutate(a)}>
                                {auditReportMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <FileText className="w-3 h-3 mr-1" />}
                                Report
                              </Button>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))
                }
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        {/* Maintenance Tab */}
        <TabsContent value="maintenance" className="mt-4 space-y-4">
          <div className="flex gap-2">
            {(["all","overdue","upcoming"] as const).map(f => (
              <button key={f} onClick={() => setMaintFilter(f)}
                className={cn("px-3 py-1 rounded-full text-xs border transition-colors capitalize",
                  maintFilter === f ? "bg-blue-700 border-blue-600 text-foreground" : "border-border text-muted-foreground hover:border-primary/50")}>
                {f}
              </button>
            ))}
          </div>
          <Card className="border-border bg-muted/30">
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  {["Equipment","Type","Task","Due","Status","Actions"].map(h => (
                    <TableHead key={h} className="text-muted-foreground text-xs">{h}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {maintLoading
                  ? <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                      <Loader2 className="w-5 h-5 animate-spin inline mr-2" />Loading…
                    </TableCell></TableRow>
                  : tasks.length === 0
                    ? <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No maintenance tasks</TableCell></TableRow>
                    : tasks.map((m: any) => (
                      <TableRow key={m.id} className="border-border hover:bg-muted">
                        <TableCell className="text-sm text-foreground font-medium">
                          {m.equipment_name}
                          {m.location ? <span className="text-xs text-muted-foreground"> · {m.location}</span> : null}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground capitalize">{m.maintenance_type}</TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-[200px] truncate">{m.description || "—"}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {formatDate(m.due_date)}
                          {m.is_overdue && <AlertTriangle className="inline w-3 h-3 ml-1 text-red-400" />}
                        </TableCell>
                        <TableCell>{statusBadge(m.status)}</TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            {m.status === "pending" && (
                              <Button size="sm" className="h-6 text-xs px-2 bg-green-700 hover:bg-green-600"
                                onClick={() => { setCompleteTaskId(m.id); setTaskCompleteForm({ ...emptyMaintenanceComplete }); }}>
                                <CheckCircle2 className="w-3 h-3 mr-1" /> Complete
                              </Button>
                            )}
                            {m.status === "completed" && (
                              <Button size="sm" variant="outline" className="h-6 text-xs px-2 border-border"
                                disabled={maintCertMutation.isPending}
                                onClick={() => maintCertMutation.mutate(m)}>
                                {maintCertMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <FileText className="w-3 h-3 mr-1" />}
                                Certificate
                              </Button>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))
                }
              </TableBody>
            </Table>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── Schedule Audit Dialog ─────────────────────────────────────────── */}
      <Dialog open={scheduleOpen} onOpenChange={setScheduleOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ClipboardList className="w-5 h-5 text-emerald-400" /> Schedule Audit
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Audit Title *</Label>
              <Input value={auditForm.audit_title}
                onChange={e => setAuditForm(p => ({ ...p, audit_title: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" placeholder="e.g. Fire Safety Audit — OPD" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Department *</Label>
              <Input value={auditForm.department}
                onChange={e => setAuditForm(p => ({ ...p, department: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Scheduled Date *</Label>
              <Input type="date" value={auditForm.scheduled_date}
                onChange={e => setAuditForm(p => ({ ...p, scheduled_date: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Risk Level</Label>
              <Select value={auditForm.risk_level} onValueChange={v => setAuditForm(p => ({ ...p, risk_level: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {RISK_LEVELS.map(r => <SelectItem key={r} value={r} className="capitalize">{r}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setScheduleOpen(false)}>Cancel</Button>
            <Button className="bg-emerald-700 hover:bg-emerald-800"
              disabled={scheduleMutation.isPending || !auditForm.audit_title || !auditForm.department || !auditForm.scheduled_date}
              onClick={() => scheduleMutation.mutate()}>
              {scheduleMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Schedule
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Complete Audit Dialog ─────────────────────────────────────────── */}
      <Dialog open={!!completeAuditId} onOpenChange={(o) => !o && setCompleteAuditId(null)}>
        <DialogContent className="bg-card border-border text-foreground max-w-lg">
          <DialogHeader>
            <DialogTitle>Complete Audit</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Findings</Label>
              <Textarea rows={3} value={auditCompleteForm.findings}
                onChange={e => setAuditCompleteForm(f => ({ ...f, findings: e.target.value }))}
                className="bg-background border-border text-foreground text-sm resize-none" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Recommendations</Label>
              <Textarea rows={3} value={auditCompleteForm.recommendations}
                onChange={e => setAuditCompleteForm(f => ({ ...f, recommendations: e.target.value }))}
                className="bg-background border-border text-foreground text-sm resize-none" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Score (0–100)</Label>
              <Input type="number" min={0} max={100} value={auditCompleteForm.score}
                onChange={e => setAuditCompleteForm(f => ({ ...f, score: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setCompleteAuditId(null)}>Cancel</Button>
            <Button className="bg-green-700 hover:bg-green-600"
              disabled={completeAuditMutation.isPending}
              onClick={() => completeAuditMutation.mutate()}>
              {completeAuditMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Complete Audit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Add Maintenance Task Dialog ───────────────────────────────────── */}
      <Dialog open={addTaskOpen} onOpenChange={setAddTaskOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Wrench className="w-5 h-5 text-blue-400" /> Add Maintenance Task
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Equipment Name *</Label>
              <Input value={taskForm.equipment_name}
                onChange={e => setTaskForm(p => ({ ...p, equipment_name: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" placeholder="e.g. Autoclave Unit 2" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Equipment Type</Label>
              <Input value={taskForm.equipment_type}
                onChange={e => setTaskForm(p => ({ ...p, equipment_type: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Location</Label>
              <Input value={taskForm.location}
                onChange={e => setTaskForm(p => ({ ...p, location: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Maintenance Type</Label>
              <Select value={taskForm.maintenance_type} onValueChange={v => setTaskForm(p => ({ ...p, maintenance_type: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {MAINTENANCE_TYPES.map(t => <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Due Date *</Label>
              <Input type="date" value={taskForm.due_date}
                onChange={e => setTaskForm(p => ({ ...p, due_date: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Description</Label>
              <Textarea rows={2} value={taskForm.description}
                onChange={e => setTaskForm(p => ({ ...p, description: e.target.value }))}
                className="bg-background border-border text-foreground text-sm resize-none" />
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setAddTaskOpen(false)}>Cancel</Button>
            <Button className="bg-blue-700 hover:bg-blue-800"
              disabled={addTaskMutation.isPending || !taskForm.equipment_name || !taskForm.due_date}
              onClick={() => addTaskMutation.mutate()}>
              {addTaskMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Add Task
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Complete Maintenance Task Dialog ──────────────────────────────── */}
      <Dialog open={!!completeTaskId} onOpenChange={(o) => !o && setCompleteTaskId(null)}>
        <DialogContent className="bg-card border-border text-foreground max-w-lg">
          <DialogHeader>
            <DialogTitle>Complete Maintenance Task</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Completion Notes</Label>
              <Textarea rows={3} value={taskCompleteForm.completion_notes}
                onChange={e => setTaskCompleteForm(f => ({ ...f, completion_notes: e.target.value }))}
                className="bg-background border-border text-foreground text-sm resize-none" placeholder="Work performed, observations…" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Next Due Date (optional — schedules the next occurrence automatically)</Label>
              <Input type="date" value={taskCompleteForm.next_due_date}
                onChange={e => setTaskCompleteForm(f => ({ ...f, next_due_date: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setCompleteTaskId(null)}>Cancel</Button>
            <Button className="bg-green-700 hover:bg-green-600"
              disabled={completeTaskMutation.isPending}
              onClick={() => completeTaskMutation.mutate()}>
              {completeTaskMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Mark Complete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
