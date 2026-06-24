import { useState } from "react";
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
  Bell, CheckCircle2, XCircle, Clock, Copy, FileText, Trash2,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";

const CHANNEL_COLORS: Record<string, string> = {
  sms:       "bg-blue-500/20 text-blue-400 border-blue-500/30",
  whatsapp:  "bg-green-500/20 text-green-400 border-green-500/30",
  email:     "bg-purple-500/20 text-purple-400 border-purple-500/30",
};

const MSG_STATUS_COLORS: Record<string, string> = {
  sent:      "bg-green-500/20 text-green-400 border-green-500/30",
  delivered: "bg-teal-500/20 text-teal-400 border-teal-500/30",
  failed:    "bg-red-500/20 text-red-400 border-red-500/30",
  queued:    "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
};

const TELE_STATUS_COLORS: Record<string, string> = {
  scheduled:  "bg-blue-500/20 text-blue-400 border-blue-500/30",
  active:     "bg-green-500/20 text-green-400 border-green-500/30",
  completed:  "bg-slate-500/20 text-slate-300 border-slate-500/30",
  cancelled:  "bg-red-500/20 text-red-400 border-red-500/30",
  no_show:    "bg-orange-500/20 text-orange-400 border-orange-500/30",
};

const TELE_TRANSITIONS: Record<string, string> = {
  scheduled: "active",
  active: "completed",
};
const TELE_NEXT_LABEL: Record<string, string> = {
  scheduled: "Start Session",
  active:    "End Session",
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

  // Join link dialog
  const [joinOpen, setJoinOpen] = useState(false);
  const [joinData, setJoinData] = useState<any>(null);

  // Filter state
  const [logChannel, setLogChannel] = useState("all");
  const [logStatus, setLogStatus] = useState("all");
  const [teleStatus, setTeleStatus] = useState("all");

  // ── Queries ──────────────────────────────────────────────────────────────

  const { data: notifStats } = useQuery({
    queryKey: ["notif-stats"],
    queryFn: () => api.notifications.stats(),
  });

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

  const sendMut = useMutation({
    mutationFn: () => api.notifications.send({
      ...sendForm,
      patient_id: sendForm.patient_id ? Number(sendForm.patient_id) : undefined,
    }),
    onSuccess: (d) => {
      toast({ title: `Message ${d.status}` });
      setSendOpen(false);
      setSendForm({ channel: "sms", recipient: "", message: "", patient_id: "" });
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

  const teleMut = useMutation({
    mutationFn: () => api.telemedicine.createSession({
      ...teleForm,
      patient_id:       Number(teleForm.patient_id),
      encounter_id:     teleForm.encounter_id ? Number(teleForm.encounter_id) : undefined,
      duration_minutes: Number(teleForm.duration_minutes),
    }),
    onSuccess: () => {
      toast({ title: "Telemedicine session scheduled" });
      setTeleOpen(false);
      setTeleForm({ patient_id: "", encounter_id: "", doctor_id: "", scheduled_date: "", scheduled_time: "", duration_minutes: "30", visit_type: "consultation", chief_complaint: "", notes: "" });
      qc.invalidateQueries({ queryKey: ["tele-sessions"] });
      qc.invalidateQueries({ queryKey: ["tele-stats"] });
    },
    onError: () => toast({ title: "Failed to schedule session", variant: "destructive" }),
  });

  const teleStatusMut = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      api.telemedicine.advanceStatus(id, { status }),
    onSuccess: (_, v) => {
      toast({ title: `Session ${v.status}` });
      qc.invalidateQueries({ queryKey: ["tele-sessions"] });
      qc.invalidateQueries({ queryKey: ["tele-stats"] });
    },
    onError: (e: any) => toast({ title: e?.message || "Status change failed", variant: "destructive" }),
  });

  async function handleJoinLinks(id: number) {
    const d = await api.telemedicine.getJoinLinks(id);
    setJoinData(d);
    setJoinOpen(true);
  }

  function copyLink(link: string) {
    navigator.clipboard.writeText(link);
    toast({ title: "Link copied" });
  }

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
          <Button size="sm" variant="outline" className="border-green-500/40 text-green-400 hover:bg-green-500/10"
            onClick={() => setReminderOpen(true)}>
            <Bell className="w-4 h-4 mr-1" /> Reminders
          </Button>
          <Button size="sm" variant="outline" className="border-blue-500/40 text-blue-400 hover:bg-blue-500/10"
            onClick={() => setBulkOpen(true)}>
            <Send className="w-4 h-4 mr-1" /> Bulk SMS
          </Button>
          <Button size="sm" className="bg-blue-600 hover:bg-blue-700"
            onClick={() => setSendOpen(true)}>
            <Plus className="w-4 h-4 mr-1" /> Send Message
          </Button>
          <Button size="sm" className="bg-blue-700 hover:bg-blue-800"
            onClick={() => setTeleOpen(true)}>
            <Video className="w-4 h-4 mr-1" /> New Session
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: "Total Sent",       value: ns.total,                 color: "text-foreground",  bg: "bg-muted/30" },
          { label: "Sent Today",       value: ns.sent_today,            color: "text-blue-400",    bg: "bg-blue-500/10" },
          { label: "Delivery Rate",    value: `${ns.delivery_rate_pct}%`, color: ns.delivery_rate_pct >= 90 ? "text-green-400" : "text-yellow-400", bg: "bg-background" },
          { label: "Tele Sessions",    value: ts.total,                 color: "text-blue-400",    bg: "bg-blue-500/10" },
          { label: "Scheduled",        value: ts.scheduled,             color: "text-sky-400",     bg: "bg-sky-500/10" },
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
              { label: "Scheduled",       value: ts.scheduled,               color: "text-blue-400" },
              { label: "Completed",       value: ts.completed,               color: "text-green-400" },
              { label: "Avg Duration",    value: `${ts.avg_duration_minutes}m`, color: "text-sky-400" },
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
                  <TableHead className="text-muted-foreground text-xs">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sessionsLoading
                  ? <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                      <Loader2 className="w-5 h-5 animate-spin inline mr-2" />Loading…
                    </TableCell></TableRow>
                  : sessions.length === 0
                    ? <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground">No sessions found</TableCell></TableRow>
                    : sessions.map((s: any) => {
                        const nextStatus = TELE_TRANSITIONS[s.status];
                        const nextLabel  = TELE_NEXT_LABEL[s.status];
                        return (
                          <TableRow key={s.id} className="border-border hover:bg-muted">
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
                            <TableCell>
                              <div className="flex gap-1">
                                <Button size="sm" variant="outline" className="h-6 text-xs px-2 border-border"
                                  onClick={() => handleJoinLinks(s.id)}>
                                  <Video className="w-3 h-3 mr-1" /> Join
                                </Button>
                                {nextStatus && nextLabel && (
                                  <Button size="sm" className="h-6 text-xs px-2 bg-blue-700 hover:bg-blue-800"
                                    disabled={teleStatusMut.isPending}
                                    onClick={() => teleStatusMut.mutate({ id: s.id, status: nextStatus })}>
                                    {nextLabel}
                                  </Button>
                                )}
                              </div>
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
      <Dialog open={sendOpen} onOpenChange={setSendOpen}>
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
              <Label className="text-xs text-muted-foreground">Recipient Phone *</Label>
              <Input value={sendForm.recipient}
                onChange={e => setSendForm(p => ({ ...p, recipient: e.target.value }))}
                placeholder="+234..."
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Patient ID (optional)</Label>
              <Input type="number" value={sendForm.patient_id}
                onChange={e => setSendForm(p => ({ ...p, patient_id: e.target.value }))}
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
      <Dialog open={teleOpen} onOpenChange={setTeleOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Video className="w-5 h-5 text-blue-400" />
              Schedule Telemedicine Session
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            {[
              { key: "patient_id",   label: "Patient ID *",    type: "number" },
              { key: "encounter_id", label: "Encounter ID",    type: "number" },
              { key: "doctor_id",    label: "Doctor ID *",     type: "text" },
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
              disabled={teleMut.isPending || !teleForm.patient_id || !teleForm.doctor_id || !teleForm.scheduled_date}
              onClick={() => teleMut.mutate()}>
              {teleMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Schedule Session
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Join Links Dialog ───────────────────────────────────────────────── */}
      <Dialog open={joinOpen} onOpenChange={setJoinOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Video className="w-5 h-5 text-green-400" />
              Join Links — Session #{joinData?.session_id}
            </DialogTitle>
            {joinData && (
              <DialogDescription className="text-muted-foreground">
                {joinData.scheduled_date} {joinData.scheduled_time}
              </DialogDescription>
            )}
          </DialogHeader>
          {joinData && (
            <div className="space-y-3 mt-2">
              {[
                { label: "Doctor Link (Host)", key: "doctor_link", color: "text-purple-400" },
                { label: "Patient Link (Guest)", key: "patient_link", color: "text-blue-400" },
              ].map(item => (
                <div key={item.key} className="space-y-1">
                  <Label className="text-xs text-muted-foreground">{item.label}</Label>
                  <div className="flex gap-2">
                    <Input readOnly value={joinData[item.key] || ""}
                      className="bg-background border-border text-xs font-mono flex-1 h-8" />
                    <Button size="sm" variant="outline" className="h-8 border-border px-2"
                      onClick={() => copyLink(joinData[item.key])}>
                      <Copy className="w-3 h-3" />
                    </Button>
                    <Button size="sm" className="h-8 bg-green-700 hover:bg-green-600 px-2"
                      onClick={() => window.open(joinData[item.key], "_blank")}>
                      <Video className="w-3 h-3" />
                    </Button>
                  </div>
                </div>
              ))}
              <p className="text-xs text-muted-foreground mt-2">
                Powered by Jitsi Meet. No download required — opens in browser.
              </p>
            </div>
          )}
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setJoinOpen(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
