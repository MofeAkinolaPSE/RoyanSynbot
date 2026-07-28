import { useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { useRealtimeChannel } from "@/hooks/use-realtime-channel";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Stethoscope, CalendarCheck, FlaskConical, Clock, User, ArrowRight, Loader2,
  CheckCircle2, Video, FileText, PhoneCall, Play,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { api } from "@/lib/api-client";
import { authClient } from "@/lib/auth-client";
import { AlertBanner } from "@/components/AlertBanner";
import { InlineWarning } from "@/components/InlineWarning";
import { cn } from "@/lib/utils";

function getJwtEmail(): string | null {
  const token = authClient.getAccessToken();
  if (!token) return null;
  try {
    const parts = token.split(".");
    if (parts.length < 2) return null;
    const p = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
    return p.email || p.sub || null;
  } catch {
    return null;
  }
}

function toISO(d: Date): string {
  return d.toISOString().split("T")[0];
}

const STATUS_COLORS: Record<string, string> = {
  patient_registered: "bg-blue-100 text-blue-700",
  triaged: "bg-yellow-100 text-yellow-700",
  consulting: "bg-green-100 text-green-700",
  lab_ordered: "bg-purple-100 text-purple-700",
  pharmacy_dispensing: "bg-orange-100 text-orange-700",
  billing_pending: "bg-red-100 text-red-700",
  discharged: "bg-slate-100 text-slate-600",
};

const LAB_STATUS_COLORS: Record<string, string> = {
  ordered: "bg-yellow-100 text-yellow-700",
  sample_collected: "bg-blue-100 text-blue-700",
  processing: "bg-purple-100 text-purple-700",
  resulted: "bg-green-100 text-green-700",
  cancelled: "bg-slate-100 text-slate-500",
};

export default function DoctorDashboard() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const navigate = useNavigate();
  const today = toISO(new Date());
  // Display/telemedicine identity — telemedicine sessions are still keyed by
  // whatever free-text "Doctor ID" was typed when the session was scheduled
  // (see DigitalEngagement.tsx), so this stays as email/sub for now.
  const doctorId = getJwtEmail() ?? authClient.getSubject() ?? "";

  // Encounters and appointments, however, key off the doctor's actual
  // royan_staff.id (the doctor_id FK both tables use) — not email — so we
  // need our own staff row, fetched via /staff/me.
  const { data: meData } = useQuery({
    queryKey: ["staff-me"],
    queryFn: () => api.staff.getMe(),
    staleTime: 5 * 60_000,
  });
  const doctorStaffId: string = meData?.data?.id ?? "";

  const { data: calData, isLoading: calLoading } = useQuery({
    queryKey: ["doctor-apts", today, doctorStaffId],
    queryFn: () =>
      api.hospital.appointments.calendar({ date_from: today, date_to: today, doctor_id: doctorStaffId }),
    enabled: !!doctorStaffId,
  });

  const { data: encData, isLoading: encLoading } = useQuery({
    queryKey: ["doctor-encounters", doctorStaffId],
    queryFn: () => api.hospital.queue.list({ doctor: doctorStaffId } as any),
    enabled: !!doctorStaffId,
    refetchInterval: 30_000,
  });

  // All patients ready for doctor (across departments)
  const { data: readyData } = useQuery({
    queryKey: ["doctor-ready-queue"],
    queryFn: () => api.hospital.queue.list({ status: "nurse_assessment" } as any),
    refetchInterval: 30_000,
    staleTime: 10_000,
  });
  const readyForDoctor: any[] = Array.isArray(readyData?.encounters) ? readyData.encounters : [];

  // Real-time: re-fetch queue on any encounter event
  useRealtimeChannel("encounter_updates", () => {
    void qc.invalidateQueries({ queryKey: ["doctor-ready-queue"] });
    void qc.invalidateQueries({ queryKey: ["doctor-encounters", doctorStaffId] });
  });

  // Call Patient
  const callMut = useMutation({
    mutationFn: (enc: any) => api.hospital.queue.callPatient(enc.id),
    onSuccess: (_, enc) => {
      toast({ title: `${enc.patient_name ?? "Patient"} called` });
      void qc.invalidateQueries({ queryKey: ["doctor-ready-queue"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  // Begin Consultation → consult API then navigate to CPRS
  const consultMut = useMutation({
    mutationFn: (enc: any) => api.hospital.queue.consult(enc.id, { doctor_id: doctorStaffId || undefined }),
    onSuccess: (_, enc) => {
      toast({ title: "Consultation started" });
      void qc.invalidateQueries({ queryKey: ["doctor-ready-queue"] });
      if (enc.mrn) navigate(`/hospital/patients/${enc.mrn}`);
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const { data: labData, isLoading: labLoading } = useQuery({
    queryKey: ["doctor-lab-pending"],
    queryFn: () => api.hospital.lab.listOrders({ status: "ordered" }),
    staleTime: 60_000,
  });

  const { data: teleData } = useQuery({
    queryKey: ["doctor-tele-today", today, doctorId],
    queryFn: () => api.telemedicine.listSessions({ doctor_id: doctorId, date: today }),
    enabled: !!doctorId,
    staleTime: 60_000,
  });

  const { data: consultData } = useQuery({
    queryKey: ["doctor-consults", doctorId],
    queryFn: () => api.specialist.listNotes({ limit: 10 }),
    staleTime: 60_000,
  });

  const todayApts = useMemo(() => {
    const list = Array.isArray(calData?.appointments) ? calData.appointments : [];
    return [...list].sort((a, b) => (a.slot?.start_time ?? "").localeCompare(b.slot?.start_time ?? ""));
  }, [calData]);

  const activeEncounters = useMemo(() => {
    const list = Array.isArray(encData?.encounters) ? encData.encounters : [];
    return list.filter((e: any) =>
      ["consulting", "lab_ordered", "pharmacy_dispensing"].includes(e.status),
    );
  }, [encData]);

  const pendingLabs = useMemo(() => {
    const list = Array.isArray(labData?.orders) ? labData.orders : [];
    return list.filter((o: any) => ["ordered", "sample_collected", "processing"].includes(o.status));
  }, [labData]);

  const resultedLabs = useMemo(() => {
    const list = Array.isArray(labData?.orders) ? labData.orders : [];
    return list.filter((o: any) => o.status === "resulted");
  }, [labData]);

  const teleSessions: any[] = Array.isArray(teleData?.sessions) ? teleData.sessions : [];
  const consultNotes: any[] = Array.isArray(consultData?.notes) ? consultData.notes : [];

  const kpis = [
    { label: "Today's Appointments", value: todayApts.length, icon: CalendarCheck, color: "text-blue-600" },
    { label: "Active Encounters", value: activeEncounters.length, icon: Stethoscope, color: "text-green-600" },
    { label: "Pending Lab Orders", value: pendingLabs.length, icon: FlaskConical, color: "text-orange-600" },
    { label: "Results to Review", value: resultedLabs.length, icon: CheckCircle2, color: resultedLabs.length > 0 ? "text-red-600" : "text-slate-600" },
    { label: "Completed Today", value: todayApts.filter((a: any) => a.status === "completed").length, icon: Clock, color: "text-slate-600" },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={motionTransitions.standard}
      className="pw-page-surface space-y-6"
    >
      <div>
        <h1 className="text-2xl font-bold">My Dashboard</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          {doctorId ? `Signed in as ${doctorId}` : "Doctor view"} — {new Date().toLocaleDateString("en-NG", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
        </p>
      </div>

      <AlertBanner />

      {/* KPIs */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
        {kpis.map(({ label, value, icon: Icon, color }) => (
          <Card key={label} className="shadow-elevation-1">
            <CardContent className="p-4 flex items-center gap-3">
              <div className={cn("rounded-lg bg-muted p-2", color)}>
                <Icon className="h-5 w-5" />
              </div>
              <div>
                <p className="text-2xl font-bold">{value}</p>
                <p className="text-xs text-muted-foreground">{label}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* ── Ready for Consultation ─────────────────────────────────────── */}
      {(readyForDoctor.length > 0 || true) && (
        <Card className={readyForDoctor.length > 0 ? "border-blue-500/30" : undefined}>
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <Stethoscope className={readyForDoctor.length > 0 ? "h-4 w-4 text-blue-500" : "h-4 w-4 text-muted-foreground"} />
              Ready for Consultation
              {readyForDoctor.length > 0 && (
                <span className="rounded-full bg-blue-500/20 text-blue-400 text-[10px] font-semibold px-2 py-0.5">
                  {readyForDoctor.length}
                </span>
              )}
            </CardTitle>
            <Button variant="ghost" size="sm" asChild className="h-7 text-xs gap-1">
              <Link to="/hospital/queue">Full Queue <ArrowRight className="h-3 w-3" /></Link>
            </Button>
          </CardHeader>
          <CardContent className="p-0">
            {readyForDoctor.length === 0 ? (
              <p className="px-4 py-6 text-sm text-center text-muted-foreground">No patients ready — vitals pending</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-20">Queue #</TableHead>
                    <TableHead>Patient</TableHead>
                    <TableHead className="hidden md:table-cell">Complaint</TableHead>
                    <TableHead className="w-14">Wait</TableHead>
                    <TableHead className="w-44">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {readyForDoctor.map((enc: any) => {
                    const wait = (() => {
                      if (!enc.created_at) return "—";
                      const mins = Math.round((Date.now() - new Date(enc.created_at).getTime()) / 60000);
                      return mins < 60 ? `${mins}m` : `${Math.floor(mins / 60)}h ${mins % 60}m`;
                    })();
                    return (
                      <TableRow key={enc.id} className="hover:bg-muted/30">
                        <TableCell className="font-mono text-xs font-bold text-primary">
                          {enc.queue_number ?? String(enc.id).slice(0, 6)}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-col gap-0.5">
                            <span className="text-sm font-medium">
                              {enc.patient_name ?? <span className="text-muted-foreground italic text-xs">Unknown</span>}
                            </span>
                            {enc.mrn && <span className="font-mono text-[10px] text-muted-foreground">{enc.mrn}</span>}
                          </div>
                        </TableCell>
                        <TableCell className="hidden md:table-cell text-xs text-muted-foreground max-w-[160px] truncate">
                          {enc.chief_complaint ?? "—"}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          <Clock className="inline h-3 w-3 mr-1" />{wait}
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-1.5">
                            <Button size="sm" variant="outline"
                              className="h-7 px-2 text-xs gap-1 border-cyan-500/40 text-cyan-400 hover:bg-cyan-500/10"
                              onClick={() => callMut.mutate(enc)}
                              disabled={callMut.isPending}>
                              <PhoneCall className="h-3 w-3" /> Call
                            </Button>
                            <Button size="sm"
                              className="h-7 px-2 text-xs gap-1 bg-blue-600 hover:bg-blue-700"
                              onClick={() => consultMut.mutate(enc)}
                              disabled={consultMut.isPending}>
                              {consultMut.isPending
                                ? <Loader2 className="h-3 w-3 animate-spin" />
                                : <Play className="h-3 w-3" />}
                              Begin
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Today's Appointments */}
        <Card className="shadow-elevation-1">
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <CalendarCheck className="h-4 w-4 text-blue-500" />
              Today's Appointments
            </CardTitle>
            <Button variant="ghost" size="sm" asChild className="h-7 text-xs gap-1">
              <Link to="/hospital/appointments">
                View all <ArrowRight className="h-3 w-3" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent className="p-0">
            {calLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : todayApts.length === 0 ? (
              <p className="px-4 py-6 text-sm text-center text-muted-foreground">No appointments today</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Patient</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {todayApts.map((apt: any) => (
                    <TableRow key={apt.id}>
                      <TableCell className="text-xs font-mono">
                        {apt.slot?.start_time?.slice(0, 5) ?? "—"}
                      </TableCell>
                      <TableCell className="text-sm">
                        {apt.patient_name ?? apt.patient_mrn ?? `#${apt.patient_id}`}
                      </TableCell>
                      <TableCell className="text-xs capitalize">{apt.appointment_type ?? "—"}</TableCell>
                      <TableCell>
                        <Badge
                          className={cn(
                            "text-[10px] capitalize",
                            apt.status === "arrived" ? "bg-yellow-100 text-yellow-700" :
                            apt.status === "completed" ? "bg-green-100 text-green-700" :
                            apt.status === "cancelled" ? "bg-slate-100 text-slate-500" :
                            "bg-blue-100 text-blue-700",
                          )}
                        >
                          {apt.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {(apt.patient_mrn ?? apt.mrn) && (
                          <Button variant="outline" size="sm" asChild className="h-6 px-2 text-xs border-primary/40 text-primary hover:bg-primary/10">
                            <Link to={`/hospital/patients/${apt.patient_mrn ?? apt.mrn}`}>CPRS</Link>
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        {/* Active Encounters */}
        <Card className="shadow-elevation-1">
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <Stethoscope className="h-4 w-4 text-green-500" />
              My Active Encounters
            </CardTitle>
            <Button variant="ghost" size="sm" asChild className="h-7 text-xs gap-1">
              <Link to="/hospital/queue">
                Queue <ArrowRight className="h-3 w-3" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent className="p-0">
            {encLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : activeEncounters.length === 0 ? (
              <p className="px-4 py-6 text-sm text-center text-muted-foreground">No active encounters</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Patient</TableHead>
                    <TableHead>Dept</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {activeEncounters.map((enc: any) => (
                    <TableRow key={enc.id}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <User className="h-3.5 w-3.5 text-muted-foreground" />
                          <span className="text-sm">
                            {enc.patient_name ?? enc.mrn ?? `#${enc.patient_id}`}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">{enc.department ?? "—"}</TableCell>
                      <TableCell>
                        <Badge className={cn("text-[10px] capitalize", STATUS_COLORS[enc.status] ?? "")}>
                          {enc.status?.replace(/_/g, " ")}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {enc.mrn && (
                          <Button variant="outline" size="sm" asChild className="h-6 px-2 text-xs border-primary/40 text-primary hover:bg-primary/10">
                            <Link to={`/hospital/patients/${enc.mrn}`}>CPRS</Link>
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        {/* Pending Lab Orders */}
        <Card className="shadow-elevation-1 lg:col-span-2">
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <FlaskConical className="h-4 w-4 text-purple-500" />
              Pending Lab Orders
            </CardTitle>
            <Button variant="ghost" size="sm" asChild className="h-7 text-xs gap-1">
              <Link to="/hospital/lab">
                Lab module <ArrowRight className="h-3 w-3" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent className="p-0">
            {labLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : pendingLabs.length === 0 ? (
              <p className="px-4 py-6 text-sm text-center text-muted-foreground">No pending lab orders</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Order #</TableHead>
                    <TableHead>Patient</TableHead>
                    <TableHead>Test</TableHead>
                    <TableHead>Urgency</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Ordered</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pendingLabs.slice(0, 15).map((order: any) => (
                    <TableRow key={order.id} className={order.urgency === "stat" ? "bg-red-50/40 dark:bg-red-950/20" : ""}>
                      <TableCell className="text-xs font-mono">#{order.id}</TableCell>
                      <TableCell className="text-sm">
                        {order.patient_name ?? order.patient_mrn ?? `#${order.patient_id}`}
                      </TableCell>
                      <TableCell className="text-sm">
                        {order.test_name}
                        {order.urgency === "stat" && (
                          <InlineWarning message="STAT" severity="critical" className="ml-2" />
                        )}
                      </TableCell>
                      <TableCell>
                        <span className={cn(
                          "text-xs font-medium capitalize",
                          order.urgency === "stat" ? "text-destructive" :
                          order.urgency === "urgent" ? "text-yellow-600" : "text-muted-foreground",
                        )}>
                          {order.urgency}
                        </span>
                      </TableCell>
                      <TableCell>
                        <Badge className={cn("text-[10px] capitalize", LAB_STATUS_COLORS[order.status] ?? "")}>
                          {order.status?.replace(/_/g, " ")}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {order.ordered_at ? new Date(order.ordered_at).toLocaleDateString("en-NG") : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Action Inbox ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">

        {/* Lab Results to Review */}
        <Card className="shadow-elevation-1">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <CheckCircle2 className={cn("h-4 w-4", resultedLabs.length > 0 ? "text-red-500" : "text-muted-foreground")} />
              Lab Results to Review
              {resultedLabs.length > 0 && (
                <span className="ml-auto rounded-full bg-red-100 text-red-700 text-[10px] font-semibold px-2 py-0.5">{resultedLabs.length}</span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {resultedLabs.length === 0 ? (
              <p className="px-4 py-5 text-sm text-center text-muted-foreground">No new results</p>
            ) : (
              <ul className="divide-y divide-border">
                {resultedLabs.slice(0, 8).map((o: any) => (
                  <li key={o.id} className="flex items-center justify-between gap-2 px-4 py-2.5 hover:bg-muted/40 transition-colors">
                    <div className="min-w-0">
                      <p className="text-xs font-medium truncate">{o.test_name}</p>
                      <p className="text-[10px] text-muted-foreground">Patient #{o.patient_id} · {o.result_summary ?? "—"}</p>
                    </div>
                    {o.patient_mrn && (
                      <Button variant="ghost" size="sm" asChild className="h-6 px-2 text-xs shrink-0 text-primary">
                        <Link to={`/hospital/patients/${o.patient_mrn}`}>CPRS</Link>
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Today's Telemedicine */}
        <Card className="shadow-elevation-1">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Video className="h-4 w-4 text-blue-500" />
              Today's Video Consults
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {teleSessions.length === 0 ? (
              <p className="px-4 py-5 text-sm text-center text-muted-foreground">No sessions today</p>
            ) : (
              <ul className="divide-y divide-border">
                {teleSessions.slice(0, 6).map((s: any) => (
                  <li key={s.id} className="flex items-center justify-between gap-2 px-4 py-2.5">
                    <div>
                      <p className="text-xs font-medium">Patient #{s.patient_id}</p>
                      <p className="text-[10px] text-muted-foreground font-mono">{s.scheduled_time ?? "—"}</p>
                    </div>
                    {["scheduled","active"].includes(s.status) && (
                      <Button size="sm" variant="outline" asChild className="h-6 px-2 text-xs gap-1">
                        <a href={s.doctor_link ?? "#"} target="_blank" rel="noreferrer">
                          <Video className="h-3 w-3" /> Join
                        </a>
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Pending Consult Requests */}
        <Card className="shadow-elevation-1">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <FileText className="h-4 w-4 text-purple-500" />
              Specialist Consults
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {consultNotes.length === 0 ? (
              <p className="px-4 py-5 text-sm text-center text-muted-foreground">No pending consults</p>
            ) : (
              <ul className="divide-y divide-border">
                {consultNotes.slice(0, 6).map((n: any) => (
                  <li key={n.id} className="flex items-center justify-between gap-2 px-4 py-2.5 hover:bg-muted/40 transition-colors">
                    <div className="min-w-0">
                      <p className="text-xs font-medium capitalize truncate">{n.specialty ?? "Specialist"}</p>
                      <p className="text-[10px] text-muted-foreground">Patient #{n.patient_id}</p>
                    </div>
                    {n.patient_mrn && (
                      <Button variant="ghost" size="sm" asChild className="h-6 px-2 text-xs shrink-0 text-primary">
                        <Link to={`/hospital/patients/${n.patient_mrn}`}>CPRS</Link>
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

      </div>
    </motion.div>
  );
}
