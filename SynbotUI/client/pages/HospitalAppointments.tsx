import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
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
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import {
  CalendarDays, Clock, RefreshCw, Loader2, Plus, CheckCircle2,
  UserCheck, XCircle, CalendarPlus, List, LayoutGrid,
  ChevronLeft, ChevronRight, Stethoscope, MapPin, Zap, CalendarSearch,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { AlertBanner } from "@/components/AlertBanner";

// ─── Types ────────────────────────────────────────────────────────────────────
interface Appointment {
  id: string;
  patient_id?: string;
  slot_id?: string;
  appointment_type?: string;
  status?: string;
  ui_status?: string;
  notes?: string;
  slot?: {
    date?: string;
    start_time?: string;
    end_time?: string;
    provider_name?: string;
    department?: string;
  };
}

interface Slot {
  id: string;
  date?: string;
  start_time?: string;
  end_time?: string;
  provider_name?: string;
  department?: string;
  capacity?: number;
  booked_count?: number;
}

const APT_STATUS_COLORS: Record<string, string> = {
  scheduled:  "bg-blue-500/20 text-blue-400 border-blue-500/30",
  arrived:    "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  completed:  "bg-green-500/20 text-green-400 border-green-500/30",
  cancelled:  "bg-slate-500/20 text-slate-300 border-slate-500/30",
  no_show:    "bg-red-500/20 text-red-400 border-red-500/30",
};

const APT_BLOCK_COLORS: Record<string, string> = {
  scheduled:  "border-blue-500/40 bg-blue-500/10 hover:bg-blue-500/15",
  arrived:    "border-yellow-500/40 bg-yellow-500/10 hover:bg-yellow-500/15",
  completed:  "border-green-500/40 bg-green-500/10 hover:bg-green-500/15",
  cancelled:  "border-slate-500/30 bg-slate-500/5 opacity-50",
  no_show:    "border-red-500/30 bg-red-500/5 opacity-60",
};

function AptBadge({ status }: { status?: string }) {
  const s = status === "booked" || status === "confirmed" ? "scheduled" : (status ?? "scheduled");
  const cls = APT_STATUS_COLORS[s] ?? APT_STATUS_COLORS.scheduled;
  return <Badge variant="outline" className={cn("text-xs capitalize", cls)}>{s.replace(/_/g, " ")}</Badge>;
}

function normalizeStatus(s?: string) {
  if (s === "booked" || s === "confirmed") return "scheduled";
  return s ?? "scheduled";
}

// ─── Week helpers ──────────────────────────────────────────────────────────────
function getMondayOf(date: Date): Date {
  const d = new Date(date);
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  d.setHours(0, 0, 0, 0);
  return d;
}

function addDays(date: Date, n: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return d;
}

function toISO(d: Date): string {
  return d.toISOString().split("T")[0];
}

const WEEK_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// ─── Constants ─────────────────────────────────────────────────────────────────
const today = new Date().toISOString().split("T")[0];
const EMPTY_SLOT = { date: today, start_time: "08:00", end_time: "08:30", provider_name: "", department: "General OPD", capacity: 1 };
const EMPTY_BOOK = { patient_id: "", slot_id: "", slot_date: today, appointment_type: "consultation", notes: "" };

// ─── Component ────────────────────────────────────────────────────────────────
export default function HospitalAppointments() {
  const qc = useQueryClient();
  const { toast } = useToast();

  const [tab, setTab] = useState("today");
  const [viewMode, setViewMode] = useState<"list" | "calendar" | "day">("list");
  const [dayView, setDayView]             = useState(today);
  const [dateFilter, setDateFilter]       = useState(today);
  const [slotDate, setSlotDate]           = useState(today);
  const [weekStart, setWeekStart]         = useState(() => getMondayOf(new Date()));
  const [slotOpen, setSlotOpen]           = useState(false);
  const [bookOpen, setBookOpen]           = useState(false);
  const [cancelOpen, setCancelOpen]       = useState(false);
  const [detailOpen, setDetailOpen]       = useState(false);
  const [nextSlotOpen, setNextSlotOpen]   = useState(false);
  const [slotForm, setSlotForm]           = useState({ ...EMPTY_SLOT });
  const [bookForm, setBookForm]           = useState({ ...EMPTY_BOOK });
  const [cancelReason, setCancelReason]   = useState("");
  const [activeApt, setActiveApt]         = useState<Appointment | null>(null);

  // Week end date
  const weekEnd = addDays(weekStart, 6);
  const weekDays = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));

  // List view query
  const { data: aptData, isLoading: aptLoading, refetch: refetchApts, isFetching: aptFetching } = useQuery({
    queryKey: ["appointments", dateFilter],
    queryFn: () => api.hospital.appointments.list({ date: dateFilter }),
    staleTime: 30_000,
    enabled: viewMode === "list" || tab !== "today",
  });
  const appointments: Appointment[] = Array.isArray(aptData?.appointments) ? aptData.appointments : Array.isArray(aptData) ? aptData : [];

  // Calendar view query (full week)
  const { data: calData, isLoading: calLoading, refetch: refetchCal } = useQuery({
    queryKey: ["appointments-calendar", toISO(weekStart), toISO(weekEnd)],
    queryFn: () => api.hospital.appointments.calendar({
      date_from: toISO(weekStart),
      date_to: toISO(weekEnd),
    }),
    staleTime: 30_000,
    enabled: viewMode === "calendar",
  });
  const calApts: Appointment[] = Array.isArray(calData?.appointments) ? calData.appointments : [];

  // Group calendar appointments by date
  const aptsByDay = useMemo(() => {
    const map: Record<string, Appointment[]> = {};
    for (const apt of calApts) {
      const date = apt.slot?.date ?? "";
      if (!map[date]) map[date] = [];
      map[date].push(apt);
    }
    // Sort each day's appointments by start_time
    for (const date in map) {
      map[date].sort((a, b) => (a.slot?.start_time ?? "") < (b.slot?.start_time ?? "") ? -1 : 1);
    }
    return map;
  }, [calApts]);

  // Slots query
  const { data: slotsData, isLoading: slotsLoading, refetch: refetchSlots } = useQuery({
    queryKey: ["appointment-slots", slotDate],
    queryFn: () => api.hospital.appointments.listSlots({ date: slotDate }),
    enabled: tab === "slots",
    staleTime: 30_000,
  });
  const slots: Slot[] = Array.isArray(slotsData?.slots) ? slotsData.slots : Array.isArray(slotsData) ? slotsData : [];

  // Next available slot query (on-demand)
  const { data: nextSlotData, isLoading: nextSlotLoading, refetch: fetchNextSlot } = useQuery({
    queryKey: ["appointments-next-slot"],
    queryFn: () => api.hospital.appointments.nextSlot(),
    enabled: false,
    staleTime: 0,
  });

  // Available slots for the Book Appointment modal's slot picker
  const { data: bookSlotsData, isLoading: bookSlotsLoading } = useQuery({
    queryKey: ["appointment-slots", "book", bookForm.slot_date],
    queryFn: () => api.hospital.appointments.listSlots({ date: bookForm.slot_date }),
    enabled: bookOpen,
    staleTime: 15_000,
  });
  const bookSlots: Slot[] = Array.isArray(bookSlotsData?.slots) ? bookSlotsData.slots : Array.isArray(bookSlotsData) ? bookSlotsData : [];

  // Day view query
  const { data: dayData, isLoading: dayLoading } = useQuery({
    queryKey: ["appointments-day", dayView],
    queryFn: () => api.hospital.appointments.calendar({ date_from: dayView, date_to: dayView }),
    enabled: viewMode === "day",
    staleTime: 30_000,
  });
  const dayApts: Appointment[] = Array.isArray(dayData?.appointments) ? dayData.appointments : [];
  const dayAptsSorted = [...dayApts].sort((a, b) =>
    (a.slot?.start_time ?? "").localeCompare(b.slot?.start_time ?? ""),
  );

  // Counts
  const scheduled = appointments.filter(a => ["scheduled", "booked", "confirmed"].includes(a.status ?? "")).length;
  const arrived   = appointments.filter(a => a.status === "arrived").length;
  const completed = appointments.filter(a => a.status === "completed").length;

  // Mutations
  const arriveMut = useMutation({
    mutationFn: (apt: Appointment) => api.hospital.appointments.arrive(apt.id),
    onSuccess: () => { toast({ title: "Patient arrived" }); void qc.invalidateQueries({ queryKey: ["appointments"] }); },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const completeMut = useMutation({
    mutationFn: (apt: Appointment) => api.hospital.appointments.complete(apt.id),
    onSuccess: () => { toast({ title: "Appointment completed" }); void qc.invalidateQueries({ queryKey: ["appointments"] }); },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const cancelMut = useMutation({
    mutationFn: () => activeApt ? api.hospital.appointments.cancel(activeApt.id, { reason: cancelReason }) : Promise.reject(),
    onSuccess: () => {
      toast({ title: "Appointment cancelled" });
      setCancelOpen(false);
      setCancelReason("");
      setDetailOpen(false);
      void qc.invalidateQueries({ queryKey: ["appointments"] });
      void qc.invalidateQueries({ queryKey: ["appointments-calendar"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const createSlotMut = useMutation({
    mutationFn: () => api.hospital.appointments.createSlot(slotForm),
    onSuccess: () => {
      toast({ title: "Slot created" });
      setSlotOpen(false);
      setSlotForm({ ...EMPTY_SLOT });
      void qc.invalidateQueries({ queryKey: ["appointment-slots"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const bookMut = useMutation({
    mutationFn: () => {
      const { slot_date, ...payload } = bookForm;
      return api.hospital.appointments.book(payload);
    },
    onSuccess: () => {
      toast({ title: "Appointment booked" });
      setBookOpen(false);
      setBookForm({ ...EMPTY_BOOK });
      void qc.invalidateQueries({ queryKey: ["appointments"] });
      void qc.invalidateQueries({ queryKey: ["appointments-calendar"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const openDetail = (apt: Appointment) => {
    setActiveApt(apt);
    setDetailOpen(true);
  };

  const handleRefresh = () => {
    void refetchApts();
    void refetchCal();
    void refetchSlots();
  };

  return (
    <motion.div className="space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Appointments</h1>
          <p className="text-sm text-muted-foreground">Schedule, track, and manage patient appointments</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="gap-2"
            onClick={() => { setNextSlotOpen(true); void fetchNextSlot(); }}
            disabled={nextSlotLoading}>
            {nextSlotLoading
              ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
              : <CalendarSearch className="h-3.5 w-3.5" />}
            Next Slot
          </Button>
          <Button variant="outline" size="sm" onClick={handleRefresh} disabled={aptFetching || calLoading} className="gap-2">
            <RefreshCw className={cn("h-3.5 w-3.5", (aptFetching || calLoading) && "animate-spin")} /> Refresh
          </Button>
          <Button size="sm" onClick={() => setBookOpen(true)} className="gap-2">
            <CalendarPlus className="h-3.5 w-3.5" /> Book
          </Button>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "Scheduled",  value: scheduled,  icon: <Clock className="h-4 w-4" />,        color: "text-blue-400"  },
          { label: "Arrived",    value: arrived,    icon: <UserCheck className="h-4 w-4" />,     color: "text-yellow-400" },
          { label: "Completed",  value: completed,  icon: <CheckCircle2 className="h-4 w-4" />, color: "text-green-400" },
        ].map(k => (
          <Card key={k.label}>
            <CardContent className="pt-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">{k.label}</p>
                  <p className="text-2xl font-bold">{k.value}</p>
                </div>
                <span className={k.color}>{k.icon}</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="today">Appointments</TabsTrigger>
          <TabsTrigger value="slots">Slot Management</TabsTrigger>
        </TabsList>

        {/* Appointments tab */}
        <TabsContent value="today" className="space-y-4">
          {/* View toggle + date controls */}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            {viewMode === "list" ? (
              <div className="flex items-center gap-3">
                <Label className="shrink-0 text-sm">Date</Label>
                <Input type="date" value={dateFilter} onChange={e => setDateFilter(e.target.value)} className="w-44" />
              </div>
            ) : viewMode === "day" ? (
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" className="h-8 w-8 p-0"
                  onClick={() => setDayView(d => toISO(addDays(new Date(d + "T00:00:00"), -1)))}>
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Input type="date" value={dayView} onChange={e => setDayView(e.target.value)} className="w-40 text-sm" />
                <Button variant="outline" size="sm" className="h-8 w-8 p-0"
                  onClick={() => setDayView(d => toISO(addDays(new Date(d + "T00:00:00"), 1)))}>
                  <ChevronRight className="h-4 w-4" />
                </Button>
                <Button variant="ghost" size="sm" className="text-xs"
                  onClick={() => setDayView(today)}>
                  Today
                </Button>
              </div>
            ) : (
              /* Week navigation */
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" className="h-8 w-8 p-0"
                  onClick={() => setWeekStart(w => addDays(w, -7))}>
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="text-sm font-medium w-44 text-center">
                  {toISO(weekStart)} — {toISO(weekEnd)}
                </span>
                <Button variant="outline" size="sm" className="h-8 w-8 p-0"
                  onClick={() => setWeekStart(w => addDays(w, 7))}>
                  <ChevronRight className="h-4 w-4" />
                </Button>
                <Button variant="ghost" size="sm" className="text-xs"
                  onClick={() => setWeekStart(getMondayOf(new Date()))}>
                  Today
                </Button>
              </div>
            )}

            {/* List / Day / Calendar toggle */}
            <div className="flex rounded-lg border border-border p-0.5 gap-0.5">
              <Button
                variant={viewMode === "list" ? "secondary" : "ghost"}
                size="sm" className="h-7 gap-1.5 px-2 text-xs"
                onClick={() => setViewMode("list")}
              >
                <List className="h-3.5 w-3.5" /> List
              </Button>
              <Button
                variant={viewMode === "day" ? "secondary" : "ghost"}
                size="sm" className="h-7 gap-1.5 px-2 text-xs"
                onClick={() => setViewMode("day")}
              >
                <CalendarDays className="h-3.5 w-3.5" /> Day
              </Button>
              <Button
                variant={viewMode === "calendar" ? "secondary" : "ghost"}
                size="sm" className="h-7 gap-1.5 px-2 text-xs"
                onClick={() => setViewMode("calendar")}
              >
                <LayoutGrid className="h-3.5 w-3.5" /> Calendar
              </Button>
            </div>
          </div>

          {/* ── LIST VIEW ─────────────────────────────────────────────── */}
          {viewMode === "list" && (
            <Card>
              <CardContent className="p-0">
                {aptLoading ? (
                  <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Time</TableHead>
                        <TableHead>Patient</TableHead>
                        <TableHead>Provider</TableHead>
                        <TableHead>Department</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {appointments.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                            <CalendarDays className="mx-auto mb-2 h-6 w-6 opacity-30" />No appointments for {dateFilter}
                          </TableCell>
                        </TableRow>
                      ) : appointments.map(apt => (
                        <TableRow key={apt.id} className="cursor-pointer hover:bg-muted/30"
                          onClick={() => openDetail(apt)}>
                          <TableCell className="font-mono text-xs">{apt.slot?.start_time ?? "—"}</TableCell>
                          <TableCell className="font-mono text-xs">{apt.patient_id != null ? String(apt.patient_id).slice(0, 8) : "—"}</TableCell>
                          <TableCell className="text-sm">{apt.slot?.provider_name ?? "—"}</TableCell>
                          <TableCell className="text-xs">{apt.slot?.department ?? "—"}</TableCell>
                          <TableCell className="capitalize text-xs">{apt.appointment_type ?? "—"}</TableCell>
                          <TableCell><AptBadge status={apt.ui_status ?? apt.status} /></TableCell>
                          <TableCell onClick={e => e.stopPropagation()}>
                            <div className="flex gap-1">
                              {["scheduled", "booked", "confirmed"].includes(apt.status ?? "") && (
                                <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1"
                                  onClick={() => arriveMut.mutate(apt)} disabled={arriveMut.isPending}>
                                  <UserCheck className="h-3 w-3" /> Arrive
                                </Button>
                              )}
                              {apt.status === "arrived" && (
                                <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1 border-green-500/40 text-green-400 hover:bg-green-500/10"
                                  onClick={() => completeMut.mutate(apt)} disabled={completeMut.isPending}>
                                  <CheckCircle2 className="h-3 w-3" /> Complete
                                </Button>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          )}

          {/* ── DAY VIEW ──────────────────────────────────────────────── */}
          {viewMode === "day" && (
            <Card>
              <CardContent className="p-0">
                {dayLoading ? (
                  <div className="flex justify-center py-16">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                ) : dayAptsSorted.length === 0 ? (
                  <p className="py-12 text-center text-sm text-muted-foreground">
                    No appointments on {dayView}
                  </p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Time</TableHead>
                        <TableHead>Patient</TableHead>
                        <TableHead>Provider</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {dayAptsSorted.map(apt => {
                        const ns = normalizeStatus(apt.status ?? apt.ui_status);
                        return (
                          <TableRow
                            key={apt.id}
                            className="cursor-pointer hover:bg-muted/40"
                            onClick={() => openDetail(apt)}
                          >
                            <TableCell className="font-mono text-xs">
                              {apt.slot?.start_time?.slice(0, 5) ?? "—"}
                              {apt.slot?.end_time ? ` – ${apt.slot.end_time.slice(0, 5)}` : ""}
                            </TableCell>
                            <TableCell className="text-sm font-medium">
                              {apt.patient_name ?? apt.patient_mrn ?? `#${apt.patient_id}`}
                            </TableCell>
                            <TableCell className="text-xs text-muted-foreground">
                              {apt.slot?.provider_name ?? "—"}
                            </TableCell>
                            <TableCell className="text-xs capitalize">{apt.appointment_type ?? "—"}</TableCell>
                            <TableCell>
                              <Badge className={cn("text-[10px] capitalize", APT_STATUS_COLORS[ns] ?? "")}>
                                {ns}
                              </Badge>
                            </TableCell>
                            <TableCell onClick={e => e.stopPropagation()}>
                              <div className="flex gap-1">
                                {ns === "scheduled" && (
                                  <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1"
                                    onClick={() => arriveMut.mutate(apt)} disabled={arriveMut.isPending}>
                                    <UserCheck className="h-3 w-3" /> Arrive
                                  </Button>
                                )}
                                {ns === "arrived" && (
                                  <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1"
                                    onClick={() => completeMut.mutate(apt)} disabled={completeMut.isPending}>
                                    <CheckCircle2 className="h-3 w-3" /> Complete
                                  </Button>
                                )}
                                {(ns === "scheduled" || ns === "arrived") && (
                                  <Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-destructive"
                                    onClick={() => { setActiveApt(apt); setCancelOpen(true); }}>
                                    <XCircle className="h-3 w-3" />
                                  </Button>
                                )}
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

          {/* ── CALENDAR VIEW ─────────────────────────────────────────── */}
          {viewMode === "calendar" && (
            <div className="overflow-x-auto rounded-xl border border-border/60">
              {calLoading ? (
                <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
              ) : (
                <div className="grid min-w-[700px]" style={{ gridTemplateColumns: "repeat(7, 1fr)" }}>
                  {/* Day headers */}
                  {weekDays.map((day, i) => {
                    const iso = toISO(day);
                    const isToday = iso === today;
                    return (
                      <div key={iso}
                        className={cn(
                          "border-b border-border/60 px-2 py-3 text-center text-xs font-medium",
                          i < 6 && "border-r border-border/40",
                          isToday && "bg-primary/5",
                        )}>
                        <p className="text-muted-foreground">{WEEK_DAYS[i]}</p>
                        <p className={cn("text-lg font-bold mt-0.5", isToday && "text-primary")}>
                          {day.getDate()}
                        </p>
                        <p className="text-[10px] text-muted-foreground">
                          {day.toLocaleDateString("en-NG", { month: "short" })}
                        </p>
                      </div>
                    );
                  })}

                  {/* Day cells */}
                  {weekDays.map((day, i) => {
                    const iso = toISO(day);
                    const dayApts = aptsByDay[iso] ?? [];
                    const isToday = iso === today;
                    return (
                      <div key={iso}
                        className={cn(
                          "min-h-[160px] p-1.5 space-y-1",
                          i < 6 && "border-r border-border/40",
                          isToday && "bg-primary/5",
                        )}>
                        {dayApts.length === 0 ? (
                          <p className="py-4 text-center text-[11px] text-muted-foreground/40">—</p>
                        ) : dayApts.map(apt => {
                          const ns = normalizeStatus(apt.ui_status ?? apt.status);
                          const blockCls = APT_BLOCK_COLORS[ns] ?? APT_BLOCK_COLORS.scheduled;
                          return (
                            <button
                              key={apt.id}
                              onClick={() => openDetail(apt)}
                              className={cn(
                                "w-full rounded-md border px-2 py-1.5 text-left transition-colors text-[11px] leading-tight",
                                blockCls,
                              )}
                            >
                              <p className="font-semibold">{apt.slot?.start_time ?? "—"}</p>
                              <p className="truncate text-muted-foreground">{apt.slot?.provider_name ?? "—"}</p>
                              <p className="truncate capitalize opacity-70">{apt.appointment_type ?? ""}</p>
                            </button>
                          );
                        })}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </TabsContent>

        {/* Slots tab */}
        <TabsContent value="slots" className="space-y-4">
          <div className="mt-4 flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <Label className="shrink-0 text-sm">Date</Label>
              <Input type="date" value={slotDate} onChange={e => setSlotDate(e.target.value)} className="w-44" />
            </div>
            <Button size="sm" onClick={() => setSlotOpen(true)} className="gap-2">
              <Plus className="h-3.5 w-3.5" /> Add Slot
            </Button>
          </div>
          <Card>
            <CardContent className="p-0">
              {slotsLoading ? (
                <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Time</TableHead>
                      <TableHead>Provider</TableHead>
                      <TableHead>Department</TableHead>
                      <TableHead>Capacity</TableHead>
                      <TableHead>Booked</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {slots.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                          No slots for {slotDate}
                        </TableCell>
                      </TableRow>
                    ) : slots.map(s => (
                      <TableRow key={s.id}>
                        <TableCell className="font-mono text-xs">{s.start_time} – {s.end_time}</TableCell>
                        <TableCell className="text-sm">{s.provider_name}</TableCell>
                        <TableCell className="text-xs">{s.department}</TableCell>
                        <TableCell>{s.capacity}</TableCell>
                        <TableCell className={cn("text-sm font-semibold",
                          (s.booked_count ?? 0) >= (s.capacity ?? 1) ? "text-red-400" : "text-green-400")}>
                          {s.booked_count ?? 0}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── Appointment Detail Sheet ──────────────────────────────────── */}
      <Sheet open={detailOpen} onOpenChange={setDetailOpen}>
        <SheetContent className="w-80 space-y-4">
          <SheetHeader>
            <SheetTitle>Appointment Details</SheetTitle>
          </SheetHeader>
          {activeApt && (
            <>
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <AptBadge status={activeApt.ui_status ?? activeApt.status} />
                  <span className="text-xs text-muted-foreground capitalize">
                    {activeApt.appointment_type?.replace(/_/g, " ")}
                  </span>
                </div>

                <div className="space-y-2 text-sm">
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Clock className="h-3.5 w-3.5 shrink-0" />
                    {activeApt.slot?.start_time ?? "—"}
                    {activeApt.slot?.end_time && ` – ${activeApt.slot.end_time}`}
                  </div>
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Stethoscope className="h-3.5 w-3.5 shrink-0" />
                    {activeApt.slot?.provider_name ?? "—"}
                  </div>
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <MapPin className="h-3.5 w-3.5 shrink-0" />
                    {activeApt.slot?.department ?? "—"}
                  </div>
                  {activeApt.notes && (
                    <p className="text-xs text-muted-foreground border-t border-border/50 pt-2 mt-2">
                      {activeApt.notes}
                    </p>
                  )}
                </div>

                <p className="text-[11px] font-mono text-muted-foreground">
                  Patient: {activeApt.patient_id ?? "—"}
                </p>
              </div>

              <Separator />

              <div className="space-y-2">
                {["scheduled", "booked", "confirmed"].includes(activeApt.status ?? "") && (
                  <Button className="w-full gap-2" size="sm"
                    onClick={() => { arriveMut.mutate(activeApt); setDetailOpen(false); }}
                    disabled={arriveMut.isPending}>
                    <UserCheck className="h-3.5 w-3.5" /> Mark Arrived
                  </Button>
                )}
                {activeApt.status === "arrived" && (
                  <Button className="w-full gap-2 border-green-500/40 text-green-400 hover:bg-green-500/10"
                    variant="outline" size="sm"
                    onClick={() => { completeMut.mutate(activeApt); setDetailOpen(false); }}
                    disabled={completeMut.isPending}>
                    <CheckCircle2 className="h-3.5 w-3.5" /> Complete
                  </Button>
                )}
                {["scheduled", "booked", "confirmed", "arrived"].includes(activeApt.status ?? "") && (
                  <Button variant="outline" size="sm"
                    className="w-full gap-2 border-red-500/30 text-red-400 hover:bg-red-500/10"
                    onClick={() => { setCancelOpen(true); }}>
                    <XCircle className="h-3.5 w-3.5" /> Cancel Appointment
                  </Button>
                )}
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>

      {/* ── Book Appointment Dialog ────────────────────────────────────── */}
      <Dialog open={bookOpen} onOpenChange={setBookOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Book Appointment</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Patient MRN *</Label>
              <Input value={bookForm.patient_id} onChange={e => setBookForm(f => ({ ...f, patient_id: e.target.value }))} placeholder="e.g. RH2026000011" />
            </div>
            <div className="space-y-1">
              <Label>Date</Label>
              <Input
                type="date"
                value={bookForm.slot_date}
                onChange={e => setBookForm(f => ({ ...f, slot_date: e.target.value, slot_id: "" }))}
              />
            </div>
            <div className="space-y-1">
              <Label>Available Slot *</Label>
              <Select
                value={bookForm.slot_id}
                onValueChange={v => setBookForm(f => ({ ...f, slot_id: v }))}
                disabled={bookSlotsLoading || bookSlots.length === 0}
              >
                <SelectTrigger>
                  <SelectValue placeholder={
                    bookSlotsLoading ? "Loading slots..." : bookSlots.length === 0 ? "No slots available this date" : "Select a slot"
                  } />
                </SelectTrigger>
                <SelectContent>
                  {bookSlots.map(s => (
                    <SelectItem key={s.id} value={String(s.id)}>
                      {s.start_time?.slice(0, 5)}
                      {s.provider_name ? ` — ${s.provider_name}` : ""}
                      {s.department ? ` (${s.department})` : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Appointment Type</Label>
              <Select value={bookForm.appointment_type} onValueChange={v => setBookForm(f => ({ ...f, appointment_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["consultation", "follow_up", "procedure", "review", "antenatal", "vaccination"].map(t => (
                    <SelectItem key={t} value={t} className="capitalize">{t.replace(/_/g, " ")}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Notes</Label>
              <Textarea value={bookForm.notes} onChange={e => setBookForm(f => ({ ...f, notes: e.target.value }))} rows={2} placeholder="Reason for appointment..." />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBookOpen(false)}>Cancel</Button>
            <Button disabled={!bookForm.patient_id.trim() || !bookForm.slot_id.trim() || bookMut.isPending} onClick={() => bookMut.mutate()}>
              {bookMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}Book Appointment
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Create Slot Dialog ─────────────────────────────────────────── */}
      <Dialog open={slotOpen} onOpenChange={setSlotOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create Appointment Slot</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4 py-2">
            <div className="col-span-2 space-y-1">
              <Label>Date</Label>
              <Input type="date" value={slotForm.date} onChange={e => setSlotForm(f => ({ ...f, date: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>Start Time</Label>
              <Input type="time" value={slotForm.start_time} onChange={e => setSlotForm(f => ({ ...f, start_time: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>End Time</Label>
              <Input type="time" value={slotForm.end_time} onChange={e => setSlotForm(f => ({ ...f, end_time: e.target.value }))} />
            </div>
            <div className="space-y-1">
              <Label>Provider Name *</Label>
              <Input value={slotForm.provider_name} onChange={e => setSlotForm(f => ({ ...f, provider_name: e.target.value }))} placeholder="Dr. Name" />
            </div>
            <div className="space-y-1">
              <Label>Capacity</Label>
              <Input type="number" min={1} max={50} value={slotForm.capacity}
                onChange={e => setSlotForm(f => ({ ...f, capacity: parseInt(e.target.value) || 1 }))} />
            </div>
            <div className="col-span-2 space-y-1">
              <Label>Department</Label>
              <Input value={slotForm.department} onChange={e => setSlotForm(f => ({ ...f, department: e.target.value }))} placeholder="e.g. Cardiology" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSlotOpen(false)}>Cancel</Button>
            <Button disabled={!slotForm.provider_name.trim() || createSlotMut.isPending} onClick={() => createSlotMut.mutate()}>
              {createSlotMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}Create Slot
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Cancel Appointment Dialog ──────────────────────────────────── */}
      <Dialog open={cancelOpen} onOpenChange={setCancelOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Cancel Appointment</DialogTitle>
            <DialogDescription>Appointment {String(activeApt?.id ?? "").slice(0, 8)}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1">
              <Label>Reason</Label>
              <Textarea value={cancelReason} onChange={e => setCancelReason(e.target.value)}
                placeholder="Reason for cancellation..." rows={2} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelOpen(false)}>Back</Button>
            <Button variant="destructive" disabled={cancelMut.isPending} onClick={() => cancelMut.mutate()}>
              {cancelMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}Cancel Appointment
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Next Available Slot Dialog ─────────────────────────────────── */}
      <Dialog open={nextSlotOpen} onOpenChange={setNextSlotOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CalendarSearch className="h-4 w-4 text-primary" /> Next Available Slot
            </DialogTitle>
          </DialogHeader>
          <div className="py-2">
            {nextSlotLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : nextSlotData?.slot ? (
              <div className="rounded-lg border border-border/60 bg-muted/30 p-4 space-y-2">
                <p className="text-sm font-semibold">
                  {nextSlotData.slot.date} at {nextSlotData.slot.start_time?.slice(0, 5)}
                </p>
                {nextSlotData.slot.provider_name && (
                  <p className="text-xs text-muted-foreground flex items-center gap-1">
                    <Stethoscope className="h-3 w-3" /> {nextSlotData.slot.provider_name}
                  </p>
                )}
                {nextSlotData.slot.department && (
                  <p className="text-xs text-muted-foreground flex items-center gap-1">
                    <MapPin className="h-3 w-3" /> {nextSlotData.slot.department}
                  </p>
                )}
                <p className="text-xs text-muted-foreground">
                  Capacity: {nextSlotData.slot.capacity ?? "—"} • Booked: {nextSlotData.slot.booked_count ?? 0}
                </p>
              </div>
            ) : (
              <p className="text-sm text-center text-muted-foreground py-6">
                No available slots found
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setNextSlotOpen(false)}>Close</Button>
            {nextSlotData?.slot && (
              <Button onClick={() => {
                setBookForm(f => ({
                  ...f,
                  slot_id: String(nextSlotData.slot.id ?? ""),
                  slot_date: nextSlotData.slot.date ?? f.slot_date,
                }));
                setNextSlotOpen(false);
                setBookOpen(true);
              }}>
                Book this slot
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
