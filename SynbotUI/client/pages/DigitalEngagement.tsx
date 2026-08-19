import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  MessageSquare, RefreshCw, Loader2, Plus, Send, Video,
  Bell, CheckCircle2, XCircle, FileText, Trash2,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { TelemedicineSessionPanel } from "@/components/engagement/TelemedicineSessionPanel";
import { TELE_STATUS_COLORS } from "@/components/engagement/engagement-shared";

const CHANNEL_COLORS: Record<string, string> = {
  sms:       "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  whatsapp:  "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
  email:     "bg-purple-500/20 text-purple-700 dark:text-purple-400 border-purple-500/30",
};

const MSG_STATUS_COLORS: Record<string, string> = {
  sent:      "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
  delivered: "bg-teal-500/20 text-teal-700 dark:text-teal-400 border-teal-500/30",
  failed:    "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30",
  queued:    "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
};

export default function DigitalEngagement() {
  const { toast } = useToast();
  const qc = useQueryClient();

  // Send SMS
  const [sendOpen, setSendOpen] = useState(false);
  const [sendForm, setSendForm] = useState({ channel: "sms", recipient: "", message: "", patient_id: "" });

  // Bulk SMS
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkForm, setBulkForm] = useState({ channel: "sms", recipients: "", message: "", campaign_name: "" });

  // Appointment reminder trigger
  const [reminderOpen, setReminderOpen] = useState(false);
  const [reminderForm, setReminderForm] = useState({ days_ahead: 1, message_template: "" });

  // Template dialogs
  const [tmplOpen, setTmplOpen] = useState(false);
  const [tmplForm, setTmplForm] = useState({ name: "", channel: "sms", body: "", variables: "", category: "general" });

  // Telemedicine session create
  const [teleOpen, setTeleOpen] = useState(false);
  const [teleForm, setTeleForm] = useState({
    patient_id: "", encounter_id: "", doctor_id: "",
    scheduled_date: "", scheduled_time: "",
    duration_minutes: "30", visit_type: "consultation",
    chief_complaint: "", notes: "",
  });

  // Telemedicine session detail panel
  const [selectedSession, setSelectedSession] = useState<any | null>(null);

  // Filter state
  const [logChannel, setLogChannel] = useState("all");
  const [logStatus, setLogStatus] = useState("all");
  const [teleStatus, setTeleStatus] = useState("all");

  // Patient search — New Telemedicine Session dialog
  const [telePatientQuery, setTelePatientQuery] = useState("");
  const [telePatientDebounced, setTelePatientDebounced] = useState("");
  const telePatientDebounceRef = useRef<ReturnType<typeof setTimeout>>();
  const [selectedTelePatient, setSelectedTelePatient] = useState<any | null>(null);

  function handleTelePatientQueryChange(val: string) {
    setTelePatientQuery(val);
    if (telePatientDebounceRef.current) clearTimeout(telePatientDebounceRef.current);
    telePatientDebounceRef.current = setTimeout(() => setTelePatientDebounced(val), 400);
  }

  // Patient search — Send Message dialog (optional patient link + phone auto-fill)
  const [sendPatientQuery, setSendPatientQuery] = useState("");
  const [sendPatientDebounced, setSendPatientDebounced] = useState("");
  const sendPatientDebounceRef = useRef<ReturnType<typeof setTimeout>>();
  const [selectedSendPatient, setSelectedSendPatient] = useState<any | null>(null);

  function handleSendPatientQueryChange(val: string) {
    setSendPatientQuery(val);
    if (sendPatientDebounceRef.current) clearTimeout(sendPatientDebounceRef.current);
    sendPatientDebounceRef.current = setTimeout(() => setSendPatientDebounced(val), 400);
  }

  // ── Queries ──────────────────────────────────────────────────────────────

  const { data: notifStats } = useQuery({
    queryKey: ["notif-stats"],
    queryFn: () => api.notifications.stats(),
  });

  const { data: doctorsData } = useQuery({
    queryKey: ["appt-doctors"],
    queryFn: () => (api.hospital.appointments as any).doctors(),
    staleTime: 300_000,
  });
  const doctors: { doctor_name: string; department: string }[] = doctorsData?.doctors ?? [];

  const { data: telePatientSearchData, isFetching: telePatientSearching } = useQuery({
    queryKey: ["engagement-tele-patient-search", telePatientDebounced],
    queryFn: () => api.hospital.patients.search(telePatientDebounced),
    enabled: teleOpen && !selectedTelePatient && telePatientDebounced.length >= 2,
  });
  const telePatientResults: any[] = Array.isArray(telePatientSearchData) ? telePatientSearchData : (telePatientSearchData?.patients ?? []);

  const { data: sendPatientSearchData, isFetching: sendPatientSearching } = useQuery({
    queryKey: ["engagement-send-patient-search", sendPatientDebounced],
    queryFn: () => api.hospital.patients.search(sendPatientDebounced),
    enabled: sendOpen && !selectedSendPatient && sendPatientDebounced.length >= 2,
  });
  const sendPatientResults: any[] = Array.isArray(sendPatientSearchData) ? sendPatientSearchData : (sendPatientSearchData?.patients ?? []);

  const { data: teleStats } = useQuery({
    queryKey: ["tele-stats"],
    queryFn: () => api.telemedicine.stats(),
  });

  const { data: logsData, isLoading: logsLoading, refetch: refetchLogs } = useQuery({
    queryKey: ["notif-logs", logChannel, logStatus],
    queryFn: () => api.notifications.listLogs({
      channel: logChannel !== "all" ? logChannel : undefined,
      status:  logStatus  !== "all" ? logStatus  : undefined,
    }),
  });

  const { data: templatesData, refetch: refetchTemplates } = useQuery({
    queryKey: ["sms-templates"],
    queryFn: () => api.notifications.listTemplates(),
  });

  const { data: sessionsData, isLoading: sessionsLoading, refetch: refetchSessions } = useQuery({
    queryKey: ["tele-sessions", teleStatus],
    queryFn: () => api.telemedicine.listSessions({
      status: teleStatus !== "all" ? teleStatus : undefined,
    }),
  });

  const ns   = notifStats  || { total: 0, sent_today: 0, delivery_rate_pct: 0, by_channel: {}, by_status: {} };
  const ts   = teleStats   || { total: 0, scheduled: 0, completed: 0, avg_duration_minutes: 0 };
  const logs = logsData?.logs || [];
  const templates = templatesData?.templates || [];
  const sessions  = sessionsData?.sessions   || [];

  // ── Mutations ────────────────────────────────────────────────────────────

  function resetSendForm() {
    setSendForm({ channel: "sms", recipient: "", message: "", patient_id: "" });
    setSendPatientQuery("");
    setSendPatientDebounced("");
    setSelectedSendPatient(null);
  }

  const sendMut = useMutation({
    mutationFn: () => api.notifications.send({
      ...sendForm,
      patient_id: selectedSendPatient ? Number(selectedSendPatient.id) : undefined,
    }),
    onSuccess: (d) => {
      toast({ title: `Message ${d.status}` });
      setSendOpen(false);
      resetSendForm();
      qc.invalidateQueries({ queryKey: ["notif-logs"] });
      qc.invalidateQueries({ queryKey: ["notif-stats"] });
    },
    onError: () => toast({ title: "Send failed", variant: "destructive" }),
  });

  const bulkMut = useMutation({
    mutationFn: () => api.notifications.bulkSend({
      ...bulkForm,
      recipients: bulkForm.recipients.split(/[\n,]+/).map(s => s.trim()).filter(Boolean),
    }),
    onSuccess: (d) => {
      toast({ title: `Bulk sent: ${d.sent} / ${d.total}` });
      setBulkOpen(false);
      setBulkForm({ channel: "sms", recipients: "", message: "", campaign_name: "" });
      qc.invalidateQueries({ queryKey: ["notif-logs"] });
      qc.invalidateQueries({ queryKey: ["notif-stats"] });
    },
    onError: () => toast({ title: "Bulk send failed", variant: "destructive" }),
  });

  const reminderMut = useMutation({
    mutationFn: () => api.notifications.appointmentReminder({
      days_ahead: reminderForm.days_ahead,
      message_template: reminderForm.message_template || undefined,
    }),
    onSuccess: (d) => {
      toast({ title: `Reminders sent: ${d.sent} (${d.skipped} skipped)` });
      setReminderOpen(false);
      qc.invalidateQueries({ queryKey: ["notif-logs"] });
    },
    onError: () => toast({ title: "Failed to send reminders", variant: "destructive" }),
  });

  const tmplMut = useMutation({
    mutationFn: () => api.notifications.createTemplate(tmplForm),
    onSuccess: () => {
      toast({ title: "Template saved" });
      setTmplOpen(false);
      setTmplForm({ name: "", channel: "sms", body: "", variables: "", category: "general" });
      refetchTemplates();
    },
    onError: () => toast({ title: "Failed to save template", variant: "destructive" }),
  });

  const deleteTmplMut = useMutation({
    mutationFn: (id: number) => api.notifications.deleteTemplate(id),
    onSuccess: () => { toast({ title: "Template deleted" }); refetchTemplates(); },
  });

  function resetTeleForm() {
    setTeleForm({ patient_id: "", encounter_id: "", doctor_id: "", scheduled_date: "", scheduled_time: "", duration_minutes: "30", visit_type: "consultation", chief_complaint: "", notes: "" });
    setTelePatientQuery("");
    setTelePatientDebounced("");
    setSelectedTelePatient(null);
  }

  const teleMut = useMutation({
    mutationFn: () => api.telemedicine.createSession({
      ...teleForm,
      patient_id:       Number(selectedTelePatient.id),
      encounter_id:     teleForm.encounter_id ? Number(teleForm.encounter_id) : undefined,
      duration_minutes: Number(teleForm.duration_minutes),
    }),
    onSuccess: () => {
      toast({ title: "Telemedicine session scheduled" });
      setTeleOpen(false);
      resetTeleForm();
      qc.invalidateQueries({ queryKey: ["tele-sessions"] });
      qc.invalidateQueries({ queryKey: ["tele-stats"] });
    },
    onError: () => toast({ title: "Failed to schedule session", variant: "destructive" }),
  });

  return (
    <motion.div className="p-6 space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-500/20 rounded-lg">
            <MessageSquare className="w-6 h-6 text-blue-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Digital Engagement</h1>
            <p className="text-sm text-muted-foreground">SMS, WhatsApp, appointment reminders, and telemedicine</p>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap justify-end">
          <Button variant="outline" size="sm" className="border-border"
            onClick={() => { refetchLogs(); refetchSessions(); }}>
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button size="sm" variant="outline" className="border-green-500/40 text-green-700 dark:text-green-400 hover:bg-green-500/10"
            onClick={() => setReminderOpen(true)}>
            <Bell className="w-4 h-4 mr-1" /> Reminders
          </Button>
          <Button size="sm" variant="outline" className="border-blue-500/40 text-blue-700 dark:text-blue-400 hover:bg-blue-500/10"
            onClick={() => setBulkOpen(true)}>
            <Send className="w-4 h-4 mr-1" /> Bulk SMS
          </Button>
          <Button size="sm" className="bg-blue-600 hover:bg-blue-700"
            onClick={() => { resetSendForm(); setSendOpen(true); }}>
            <Plus className="w-4 h-4 mr-1" /> Send Message
          </Button>
          <Button size="sm" className="bg-blue-700 hover:bg-blue-800"
            onClick={() => { resetTeleForm(); setTeleOpen(true); }}>
            <Video className="w-4 h-4 mr-1" /> New Session
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: "Total Sent",       value: ns.total,                 color: "text-foreground",  bg: "bg-muted/30" },
          { label: "Sent Today",       value: ns.sent_today,            color: "text-blue-700 dark:text-blue-400",    bg: "bg-blue-500/10" },
          { label: "Delivery Rate",    value: `${ns.delivery_rate_pct}%`, color: ns.delivery_rate_pct >= 90 ? "text-green-700 dark:text-green-400" : "text-yellow-700 dark:text-yellow-400", bg: "bg-background" },
          { label: "Tele Sessions",    value: ts.total,                 color: "text-blue-700 dark:text-blue-400",    bg: "bg-blue-500/10" },
          { label: "Scheduled",        value: ts.scheduled,             color: "text-sky-700 dark:text-sky-400",     bg: "bg-sky-500/10" },
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
      <Tabs defaultValue="logs">
        <TabsList className="bg-muted border border-border">
          <TabsTrigger value="logs">Message Logs</TabsTrigger>
          <TabsTrigger value="templates">Templates</TabsTrigger>
          <TabsTrigger value="telemedicine">Telemedicine</TabsTrigger>
        </TabsList>

        {/* Message Logs Tab */}
        <TabsContent value="logs" className="mt-4 space-y-4">
          <div className="flex gap-2 flex-wrap">
            {["all", "sms", "whatsapp", "email"].map(c => (
              <button key={c}
                onClick={() => setLogChannel(c)}
                className={cn(
                  "px-3 py-1 rounded-full text-xs border transition-colors",
                  logChannel === c ? "bg-blue-600 border-blue-500 text-foreground" : "border-border text-muted-foreground hover:border-primary/50"
                )}>
                {c === "all" ? "All Channels" : c.charAt(0).toUpperCase() + c.slice(1)}
              </button>
            ))}
            <div className="ml-2 flex gap-2">
              {["all", "sent", "delivered", "failed", "queued"].map(s => (
                <button key={s}
                  onClick={() => setLogStatus(s)}
                  className={cn(
                    "px-3 py-1 rounded-full text-xs border transition-colors",
                    logStatus === s ? "bg-indigo-600 border-indigo-500 text-foreground" : "border-border text-muted-foreground hover:border-primary/50"
                  )}>
                  {s === "all" ? "All Statuses" : s}
                </button>
              ))}
            </div>
          </div>

          <Card className="border-border bg-muted/30">
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  <TableHead className="text-muted-foreground text-xs">Timestamp</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Channel</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Recipient</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Message</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Status</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Campaign</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logsLoading
                  ? <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                      <Loader2 className="w-5 h-5 animate-spin inline mr-2" />Loading…
                    </TableCell></TableRow>
                  : logs.length === 0
                    ? <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No messages logged yet</TableCell></TableRow>
                    : logs.map((l: any) => (
                      <TableRow key={l.id} className="border-border hover:bg-muted">
                        <TableCell className="text-xs text-muted-foreground font-mono">
                          {l.sent_at ? new Date(l.sent_at).toLocaleString() : "—"}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cn("text-xs uppercase", CHANNEL_COLORS[l.channel] || "")}>
                            {l.channel}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs font-mono text-muted-foreground">{l.recipient}</TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-[200px] truncate">{l.message}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cn("text-xs", MSG_STATUS_COLORS[l.status] || "")}>
                            {l.status === "sent" ? <CheckCircle2 className="w-3 h-3 mr-1 inline" /> : null}
                            {l.status === "failed" ? <XCircle className="w-3 h-3 mr-1 inline" /> : null}
                            {l.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">{l.campaign_name || "—"}</TableCell>
                      </TableRow>
                    ))
                }
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        {/* Templates Tab */}
        <TabsContent value="templates" className="mt-4 space-y-4">
          <div className="flex justify-end">
            <Button size="sm" className="bg-blue-600 hover:bg-blue-700"
              onClick={() => setTmplOpen(true)}>
              <Plus className="w-4 h-4 mr-1" /> New Template
            </Button>
          </div>
          <Card className="border-border bg-muted/30">
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  <TableHead className="text-muted-foreground text-xs">Name</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Channel</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Category</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Variables</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Body</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {templates.length === 0
                  ? <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No templates yet</TableCell></TableRow>
                  : templates.map((t: any) => (
                    <TableRow key={t.id} className="border-border hover:bg-muted">
                      <TableCell className="text-sm font-medium text-foreground">{t.name}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={cn("text-xs uppercase", CHANNEL_COLORS[t.channel] || "")}>
                          {t.channel}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground capitalize">{t.category || "—"}</TableCell>
                      <TableCell className="text-xs font-mono text-muted-foreground">{t.variables || "—"}</TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-[220px] truncate">{t.body}</TableCell>
                      <TableCell>
                        <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-red-400 hover:text-red-300"
                          onClick={() => deleteTmplMut.mutate(t.id)}>
                          <Trash2 className="w-3 h-3" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                }
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        {/* Telemedicine Tab */}
        <TabsContent value="telemedicine" className="mt-4 space-y-4">
          {/* Tele KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: "Total",           value: ts.total,                   color: "text-foreground" },
              { label: "Scheduled",       value: ts.scheduled,               color: "text-blue-700 dark:text-blue-400" },
              { label: "Completed",       value: ts.completed,               color: "text-green-700 dark:text-green-400" },
              { label: "Avg Duration",    value: `${ts.avg_duration_minutes}m`, color: "text-sky-700 dark:text-sky-400" },
            ].map(k => (
              <Card key={k.label} className="border-border bg-muted/30">
                <CardContent className="pt-3 pb-2">
                  <p className="text-xs text-muted-foreground uppercase tracking-wide">{k.label}</p>
                  <p className={cn("text-xl font-bold mt-1", k.color)}>{k.value}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Status filter pills */}
          <div className="flex gap-2 flex-wrap">
            {["all", "scheduled", "active", "completed", "cancelled", "no_show"].map(s => (
              <button key={s}
                onClick={() => setTeleStatus(s)}
                className={cn(
                  "px-3 py-1 rounded-full text-xs border transition-colors",
                  teleStatus === s ? "bg-blue-700 border-blue-600 text-foreground" : "border-border text-muted-foreground hover:border-primary/50"
                )}>
                {s === "all" ? "All" : s.replace("_", " ")}
              </button>
            ))}
          </div>

          <Card className="border-border bg-muted/30">
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  <TableHead className="text-muted-foreground text-xs">ID</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Patient</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Doctor</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Date / Time</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Type</TableHead>
                  <TableHead className="text-muted-foreground text-xs">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sessionsLoading
                  ? <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                      <Loader2 className="w-5 h-5 animate-spin inline mr-2" />Loading…
                    </TableCell></TableRow>
                  : sessions.length === 0
                    ? <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No sessions found</TableCell></TableRow>
                    : sessions.map((s: any) => {
                        return (
                          <TableRow key={s.id} className="border-border hover:bg-muted cursor-pointer" onClick={() => setSelectedSession(s)}>
                            <TableCell className="font-mono text-xs text-muted-foreground">{s.id}</TableCell>
                            <TableCell className="text-sm text-foreground">{s.patient_id}</TableCell>
                            <TableCell className="text-sm text-muted-foreground">{s.doctor_id}</TableCell>
                            <TableCell className="text-xs text-muted-foreground">
                              {s.scheduled_date} {s.scheduled_time && <span className="font-mono">{s.scheduled_time}</span>}
                            </TableCell>
                            <TableCell className="text-xs text-muted-foreground capitalize">{s.visit_type?.replace("_", " ")}</TableCell>
                            <TableCell>
                              <Badge variant="outline" className={cn("text-xs", TELE_STATUS_COLORS[s.status] || "")}>
                                {s.status.replace("_", " ")}
                              </Badge>
                            </TableCell>
                          </TableRow>
                        );
                      })
                }
              </TableBody>
            </Table>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── Send Message Dialog ─────────────────────────────────────────────── */}
      <Dialog open={sendOpen} onOpenChange={(o) => { setSendOpen(o); if (!o) resetSendForm(); }}>
        <DialogContent className="bg-card border-border text-foreground max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Send className="w-5 h-5 text-blue-400" />
              Send Message
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Channel</Label>
              <Select value={sendForm.channel}
                onValueChange={v => setSendForm(p => ({ ...p, channel: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {["sms", "whatsapp"].map(c => <SelectItem key={c} value={c} className="capitalize">{c.charAt(0).toUpperCase() + c.slice(1)}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Link to Patient (optional)</Label>
              {!selectedSendPatient ? (
                <>
                  <Input placeholder="Search patient by name, phone, or HMO ID…" value={sendPatientQuery}
                    onChange={e => handleSendPatientQueryChange(e.target.value)}
                    className="bg-background border-border text-foreground text-sm h-8" />
                  {sendPatientSearching && <p className="text-xs text-muted-foreground">Searching…</p>}
                  {sendPatientResults.length > 0 && (
                    <div className="space-y-1.5 max-h-36 overflow-y-auto">
                      {sendPatientResults.map((p: any) => (
                        <button key={p.id} type="button"
                          className="w-full text-left rounded-md border px-3 py-2 text-xs hover:bg-muted/40 transition-colors"
                          onClick={() => {
                            setSelectedSendPatient(p);
                            if (p.phone) setSendForm(f => ({ ...f, recipient: p.phone }));
                          }}>
                          <p className="font-medium text-sm">{p.first_name} {p.last_name}</p>
                          <p className="text-muted-foreground">MRN: {p.mrn} · {p.phone ?? "no phone on file"}</p>
                        </button>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <div className="rounded-md border border-primary/40 bg-primary/5 px-3 py-2 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">{selectedSendPatient.first_name} {selectedSendPatient.last_name}</p>
                    <p className="text-xs text-muted-foreground font-mono">{selectedSendPatient.mrn}</p>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => setSelectedSendPatient(null)}>Change</Button>
                </div>
              )}
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Recipient Phone *</Label>
              <Input value={sendForm.recipient}
                onChange={e => setSendForm(p => ({ ...p, recipient: e.target.value }))}
                placeholder="+234..."
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Message *</Label>
              <Textarea value={sendForm.message}
                onChange={e => setSendForm(p => ({ ...p, message: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-24 resize-none"
                placeholder="Type your message…" />
              <p className="text-xs text-muted-foreground text-right">{sendForm.message.length}/160</p>
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setSendOpen(false)}>Cancel</Button>
            <Button className="bg-blue-600 hover:bg-blue-700"
              disabled={sendMut.isPending || !sendForm.recipient || !sendForm.message}
              onClick={() => sendMut.mutate()}>
              {sendMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Send className="w-4 h-4 mr-2" />}
              Send
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Bulk Send Dialog ─────────────────────────────────────────────────── */}
      <Dialog open={bulkOpen} onOpenChange={setBulkOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Send className="w-5 h-5 text-blue-400" />
              Bulk SMS
            </DialogTitle>
            <DialogDescription className="text-muted-foreground">Send the same message to multiple recipients</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Channel</Label>
                <Select value={bulkForm.channel}
                  onValueChange={v => setBulkForm(p => ({ ...p, channel: v }))}>
                  <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover border-border">
                    {["sms", "whatsapp"].map(c => <SelectItem key={c} value={c} className="capitalize">{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Campaign Name</Label>
                <Input value={bulkForm.campaign_name}
                  onChange={e => setBulkForm(p => ({ ...p, campaign_name: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-8" />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Recipients (one per line or comma-separated) *</Label>
              <Textarea value={bulkForm.recipients}
                onChange={e => setBulkForm(p => ({ ...p, recipients: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-24 resize-none font-mono"
                placeholder="+2348012345678&#10;+2348098765432&#10;..." />
              <p className="text-xs text-muted-foreground">
                {bulkForm.recipients.split(/[\n,]+/).filter(s => s.trim()).length} recipients
              </p>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Message *</Label>
              <Textarea value={bulkForm.message}
                onChange={e => setBulkForm(p => ({ ...p, message: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-20 resize-none" />
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setBulkOpen(false)}>Cancel</Button>
            <Button className="bg-blue-700 hover:bg-blue-800"
              disabled={bulkMut.isPending || !bulkForm.recipients || !bulkForm.message}
              onClick={() => bulkMut.mutate()}>
              {bulkMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Send to All
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Appointment Reminder Dialog ─────────────────────────────────────── */}
      <Dialog open={reminderOpen} onOpenChange={setReminderOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Bell className="w-5 h-5 text-green-400" />
              Send Appointment Reminders
            </DialogTitle>
            <DialogDescription className="text-muted-foreground">
              Sends SMS to all confirmed appointments N days from today
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Days Ahead (0 = today)</Label>
              <Input type="number" min={0} max={7}
                value={reminderForm.days_ahead}
                onChange={e => setReminderForm(p => ({ ...p, days_ahead: Number(e.target.value) }))}
                className="bg-background border-border text-foreground text-sm h-8 w-24" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Custom Message Template (optional)</Label>
              <Textarea
                value={reminderForm.message_template}
                onChange={e => setReminderForm(p => ({ ...p, message_template: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-20 resize-none"
                placeholder="Use {name}, {date}, {time}, {department} as variables…" />
              <p className="text-xs text-muted-foreground">Leave blank to use the default reminder template</p>
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setReminderOpen(false)}>Cancel</Button>
            <Button className="bg-green-600 hover:bg-green-700"
              disabled={reminderMut.isPending}
              onClick={() => reminderMut.mutate()}>
              {reminderMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Send Reminders
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── New Template Dialog ─────────────────────────────────────────────── */}
      <Dialog open={tmplOpen} onOpenChange={setTmplOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-muted-foreground" />
              New SMS Template
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Template Name *</Label>
                <Input value={tmplForm.name}
                  onChange={e => setTmplForm(p => ({ ...p, name: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-8" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Channel</Label>
                <Select value={tmplForm.channel}
                  onValueChange={v => setTmplForm(p => ({ ...p, channel: v }))}>
                  <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover border-border">
                    {["sms", "whatsapp", "email"].map(c => <SelectItem key={c} value={c} className="capitalize">{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Category</Label>
                <Select value={tmplForm.category}
                  onValueChange={v => setTmplForm(p => ({ ...p, category: v }))}>
                  <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover border-border">
                    {["general", "appointment", "discharge", "result", "reminder"].map(c => <SelectItem key={c} value={c} className="capitalize">{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">Variables (comma-separated)</Label>
                <Input value={tmplForm.variables}
                  onChange={e => setTmplForm(p => ({ ...p, variables: e.target.value }))}
                  placeholder="name,date,time"
                  className="bg-background border-border text-foreground text-sm h-8" />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Message Body *</Label>
              <Textarea value={tmplForm.body}
                onChange={e => setTmplForm(p => ({ ...p, body: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-24 resize-none"
                placeholder="Dear {name}, your appointment is on {date} at {time}…" />
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setTmplOpen(false)}>Cancel</Button>
            <Button className="bg-blue-600 hover:bg-blue-700"
              disabled={tmplMut.isPending || !tmplForm.name || !tmplForm.body}
              onClick={() => tmplMut.mutate()}>
              {tmplMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Save Template
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── New Telemedicine Session Dialog ─────────────────────────────────── */}
      <Dialog open={teleOpen} onOpenChange={(o) => { setTeleOpen(o); if (!o) resetTeleForm(); }}>
        <DialogContent className="bg-card border-border text-foreground max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Video className="w-5 h-5 text-blue-400" />
              Schedule Telemedicine Session
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Patient *</Label>
              {!selectedTelePatient ? (
                <>
                  <Input placeholder="Search patient by name, phone, or HMO ID…" value={telePatientQuery}
                    onChange={e => handleTelePatientQueryChange(e.target.value)}
                    className="bg-background border-border text-foreground text-sm h-8" />
                  {telePatientSearching && <p className="text-xs text-muted-foreground">Searching…</p>}
                  {telePatientResults.length > 0 && (
                    <div className="space-y-1.5 max-h-36 overflow-y-auto">
                      {telePatientResults.map((p: any) => (
                        <button key={p.id} type="button"
                          className="w-full text-left rounded-md border px-3 py-2 text-xs hover:bg-muted/40 transition-colors"
                          onClick={() => setSelectedTelePatient(p)}>
                          <p className="font-medium text-sm">{p.first_name} {p.last_name}</p>
                          <p className="text-muted-foreground">MRN: {p.mrn}</p>
                        </button>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <div className="rounded-md border border-primary/40 bg-primary/5 px-3 py-2 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">{selectedTelePatient.first_name} {selectedTelePatient.last_name}</p>
                    <p className="text-xs text-muted-foreground font-mono">{selectedTelePatient.mrn}</p>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => setSelectedTelePatient(null)}>Change</Button>
                </div>
              )}
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Doctor *</Label>
              <Select value={teleForm.doctor_id} onValueChange={v => setTeleForm(p => ({ ...p, doctor_id: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue placeholder="Select doctor" /></SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {doctors.map(d => <SelectItem key={d.doctor_name} value={d.doctor_name}>{d.doctor_name}{d.department ? ` (${d.department})` : ""}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {[
              { key: "encounter_id", label: "Encounter ID",    type: "number" },
              { key: "duration_minutes", label: "Duration (min)", type: "number" },
              { key: "scheduled_date",   label: "Date *",      type: "date" },
              { key: "scheduled_time",   label: "Time *",      type: "time" },
            ].map(f => (
              <div key={f.key} className="space-y-1">
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Input type={f.type}
                  value={(teleForm as any)[f.key] || ""}
                  onChange={e => setTeleForm(p => ({ ...p, [f.key]: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-8" />
              </div>
            ))}
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Visit Type</Label>
              <Select value={teleForm.visit_type}
                onValueChange={v => setTeleForm(p => ({ ...p, visit_type: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {["consultation", "follow_up", "review", "urgent"].map(t => <SelectItem key={t} value={t} className="capitalize">{t.replace("_", " ")}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Chief Complaint</Label>
              <Input value={teleForm.chief_complaint}
                onChange={e => setTeleForm(p => ({ ...p, chief_complaint: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Notes</Label>
              <Textarea value={teleForm.notes}
                onChange={e => setTeleForm(p => ({ ...p, notes: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-16 resize-none" />
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setTeleOpen(false)}>Cancel</Button>
            <Button className="bg-blue-700 hover:bg-blue-800"
              disabled={teleMut.isPending || !selectedTelePatient || !teleForm.doctor_id || !teleForm.scheduled_date}
              onClick={() => teleMut.mutate()}>
              {teleMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Schedule Session
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {selectedSession && (
        <TelemedicineSessionPanel session={selectedSession} onClose={() => setSelectedSession(null)} />
      )}
    </motion.div>
  );
}
