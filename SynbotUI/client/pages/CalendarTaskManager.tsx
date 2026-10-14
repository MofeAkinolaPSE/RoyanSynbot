/**
 * My Schedule - one person's own diary: the appointments booked to see them (doctors), the tasks
 * assigned to or created by them, and the events they attend. Nobody else's. The whole hospital's
 * diary is the Hospital Calendar; the full appointment book is Appointments.
 *
 * (Formerly the hospital-wide SchedulingCenter.)
 *
 * 3-panel layout:
 *   Left  (260px) : mini date picker + type filters + doctor/dept filters + quick actions
 *   Center (flex) : Day | Week | Month | Doctor views with colored appointment blocks
 *   Right  (320px): detail panel (slides in on item selection)
 *
 * Data sources:
 *   - /appointments/calendar  → appointments joined with slot + patient (new endpoint)
 *   - /tasks                  → royan_tasks with due_date
 *   - /calendar/events        → royan_calendar_events
 *   - /appointments/doctors   → distinct doctor list for filters
 */

import { PANEL_WIDTH } from "@/components/shared/panel-shared";
import { useState, useMemo, useCallback, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  format,
  startOfWeek,
  endOfWeek,
  startOfMonth,
  endOfMonth,
  addDays,
  addWeeks,
  subWeeks,
  addMonths,
  subMonths,
  isSameDay,
  isSameMonth,
  isToday,
  parseISO,
  eachDayOfInterval,
  getHours,
  getMinutes,
} from "date-fns";
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  Check,
  UserX,
  Bell,
  Stethoscope,
  LayoutGrid,
  CalendarDays,
  List,
  Filter,
  Phone,
  Mail,
  RefreshCw,
  Clock,
  User,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Calendar } from "@/components/ui/calendar";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api-client";
import { useRealtimeChannel } from "@/hooks/use-realtime-channel";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";

// ── Types ──────────────────────────────────────────────────────────────────

type ViewMode = "month" | "week" | "day" | "doctor";
type ItemKind = "appointment" | "task" | "event";

interface CalendarAppointment {
  id: number;
  patient_id: number;
  slot_id: number;
  status: string;
  reason?: string;
  notes?: string;
  booked_at: string;
  reminder_sent: boolean;
  doctor_name: string;
  department: string;
  slot_date: string;
  slot_time: string;
  duration_mins: number;
  patient_name?: string;
  patient_phone?: string;
  patient_email?: string;
}

interface CalendarTask {
  id: string;
  title: string;
  description?: string;
  status: string;
  priority: string;
  due_date?: string;
  assigned_to?: string;
}

interface CalendarEvent {
  id: string;
  title: string;
  event_type: string;
  start_time: string;
  end_time?: string;
  location?: string;
}

interface ScheduledItem {
  id: string;
  kind: ItemKind;
  title: string;
  start: Date;
  end?: Date;
  status: string;
  color: string;
  doctor?: string;
  department?: string;
  patientName?: string;
  durationMins?: number;
  raw: CalendarAppointment | CalendarTask | CalendarEvent;
}

// ── Constants ──────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  booked: "#17449E",
  confirmed: "#13A7E0",
  arrived: "#DD9933",
  completed: "#25D366",
  no_show: "#B22D00",
  cancelled: "#6B7280",
  rescheduled: "#6366F1",
  pending: "#F59E0B",
  in_progress: "#3B82F6",
  done: "#25D366",
  blocked: "#B22D00",
  meeting: "#113379",
  deadline: "#B22D00",
  reminder: "#DD9933",
  holiday: "#25D366",
  other: "#6B7280",
};

const HOUR_START = 7;
const HOUR_END = 21;
const PX_PER_HOUR = 80;
const MIN_BLOCK_HEIGHT = 20;
const TOTAL_GRID_HEIGHT = (HOUR_END - HOUR_START) * PX_PER_HOUR;

const DEPARTMENTS = [
  "A&E","OPD","Laboratory & Diagnostics","Pharmacy",
  "Billing & Finance","Administration","Maintenance & Facilities",
  "Maternity","Surgery","Inpatient Ward",
];

// ── Helpers ────────────────────────────────────────────────────────────────

function itemColor(status: string): string {
  return STATUS_COLORS[status] ?? "#6B7280";
}

function topPxForTime(timeStr: string): number {
  const [h, m] = timeStr.split(":").map(Number);
  return (h - HOUR_START) * PX_PER_HOUR + (m / 60) * PX_PER_HOUR;
}

function heightPxForDuration(mins: number): number {
  return Math.max(MIN_BLOCK_HEIGHT, (mins / 60) * PX_PER_HOUR);
}

// ── Component ──────────────────────────────────────────────────────────────

const SchedulingCenter = () => {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [viewMode, setViewMode] = useState<ViewMode>("week");
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedItem, setSelectedItem] = useState<ScheduledItem | null>(null);
  const [showAppts, setShowAppts] = useState(true);
  const [showTasks, setShowTasks] = useState(true);
  const [showEvents, setShowEvents] = useState(true);
  const [filterDoctor, setFilterDoctor] = useState("all");
  const [filterDept, setFilterDept] = useState("all");
  const [showApptDialog, setShowApptDialog] = useState(false);
  const [newApptDate, setNewApptDate] = useState("");
  const [newApptSlotId, setNewApptSlotId] = useState("");
  const [newApptReason, setNewApptReason] = useState("");
  const [apptPatientQuery, setApptPatientQuery] = useState("");
  const [apptDebouncedQuery, setApptDebouncedQuery] = useState("");
  const apptSearchDebounceRef = useRef<ReturnType<typeof setTimeout>>();
  const [selectedApptPatient, setSelectedApptPatient] = useState<any | null>(null);
  const [showTaskDialog, setShowTaskDialog] = useState(false);
  const [newTask, setNewTask] = useState({ title: "", description: "", priority: "medium", due_date: "" });

  const dateRange = useMemo(() => {
    if (viewMode === "month") {
      return { from: format(startOfMonth(currentDate), "yyyy-MM-dd"), to: format(endOfMonth(currentDate), "yyyy-MM-dd") };
    }
    if (viewMode === "day") {
      const d = format(currentDate, "yyyy-MM-dd");
      return { from: d, to: d };
    }
    const wStart = startOfWeek(currentDate, { weekStartsOn: 1 });
    const wEnd = endOfWeek(currentDate, { weekStartsOn: 1 });
    return { from: format(wStart, "yyyy-MM-dd"), to: format(wEnd, "yyyy-MM-dd") };
  }, [viewMode, currentDate]);

  const { data: calData, isFetching: calFetching } = useQuery({
    queryKey: ["sched-appointments", dateRange.from, dateRange.to],
    // mine: the appointments booked into my own slots (empty for anyone who is not a doctor)
    queryFn: () => api.hospital.appointments.calendar({ date_from: dateRange.from, date_to: dateRange.to, mine: true }),
    staleTime: 30_000,
  });

  const { data: tasksData } = useQuery({
    queryKey: ["sched-tasks"],
    queryFn: () => api.tasks.list(undefined, true),
    staleTime: 60_000,
  });

  const { data: eventsData } = useQuery({
    queryKey: ["sched-events", format(currentDate, "yyyy-MM")],
    queryFn: () => api.calendar.list(format(currentDate, "yyyy-MM"), true),
    staleTime: 60_000,
  });

  const { data: doctorsData } = useQuery({
    queryKey: ["appt-doctors"],
    queryFn: () => (api.hospital.appointments as any).doctors(),
    staleTime: 300_000,
  });

  const { data: apptPatientSearchData, isFetching: apptPatientSearching } = useQuery({
    queryKey: ["sched-patient-search", apptDebouncedQuery],
    queryFn: () => api.hospital.patients.search(apptDebouncedQuery),
    enabled: showApptDialog && !selectedApptPatient && apptDebouncedQuery.length >= 2,
  });
  const apptPatientResults: any[] = Array.isArray(apptPatientSearchData) ? apptPatientSearchData : (apptPatientSearchData?.patients ?? []);

  const { data: newApptSlotsData, isFetching: newApptSlotsLoading } = useQuery({
    queryKey: ["sched-new-appt-slots", newApptDate],
    queryFn: () => api.hospital.appointments.listSlots({ date: newApptDate }),
    enabled: showApptDialog && !!newApptDate,
  });
  const newApptSlots: any[] = Array.isArray(newApptSlotsData?.slots) ? newApptSlotsData.slots : [];

  function handleApptPatientQueryChange(val: string) {
    setApptPatientQuery(val);
    if (apptSearchDebounceRef.current) clearTimeout(apptSearchDebounceRef.current);
    apptSearchDebounceRef.current = setTimeout(() => setApptDebouncedQuery(val), 400);
  }

  function resetNewApptForm() {
    setNewApptDate(format(new Date(), "yyyy-MM-dd"));
    setNewApptSlotId("");
    setNewApptReason("");
    setApptPatientQuery("");
    setApptDebouncedQuery("");
    setSelectedApptPatient(null);
  }

  useRealtimeChannel("calendar_tasks", (msg: any) => {
    if (msg?.event?.startsWith("calendar_event_")) queryClient.invalidateQueries({ queryKey: ["sched-events"] });
    if (msg?.event?.startsWith("task_")) queryClient.invalidateQueries({ queryKey: ["sched-tasks"] });
  });
  useRealtimeChannel("staff_updates", () => {
    queryClient.invalidateQueries({ queryKey: ["sched-tasks"] });
  });

  const appointments: CalendarAppointment[] = (calData as any)?.appointments ?? [];
  const tasks: CalendarTask[] = (tasksData as any)?.tasks ?? [];
  const events: CalendarEvent[] = (eventsData as any)?.events ?? [];
  const doctors: { doctor_name: string; department: string }[] = (doctorsData as any)?.doctors ?? [];

  const allItems = useMemo((): ScheduledItem[] => {
    const items: ScheduledItem[] = [];
    if (showAppts) {
      for (const appt of appointments) {
        if (!appt.slot_date || !appt.slot_time) continue;
        const timeStr = appt.slot_time.substring(0, 5);
        const start = new Date(`${appt.slot_date}T${timeStr}:00`);
        const end = new Date(start.getTime() + (appt.duration_mins || 15) * 60_000);
        items.push({ id: String(appt.id), kind: "appointment", title: appt.patient_name || `Appointment #${appt.id}`, start, end, status: appt.status, color: itemColor(appt.status), doctor: appt.doctor_name, department: appt.department, patientName: appt.patient_name, durationMins: appt.duration_mins || 15, raw: appt });
      }
    }
    if (showTasks) {
      for (const task of tasks) {
        if (!task.due_date) continue;
        const start = parseISO(task.due_date);
        items.push({ id: task.id, kind: "task", title: task.title, start, status: task.status, color: itemColor(task.status), raw: task });
      }
    }
    if (showEvents) {
      for (const ev of events) {
        if (!ev.start_time) continue;
        const start = parseISO(ev.start_time);
        const end = ev.end_time ? parseISO(ev.end_time) : undefined;
        items.push({ id: ev.id, kind: "event", title: ev.title, start, end, status: ev.event_type, color: itemColor(ev.event_type), raw: ev });
      }
    }
    return items.sort((a, b) => a.start.getTime() - b.start.getTime());
  }, [appointments, tasks, events, showAppts, showTasks, showEvents]);

  const itemsForDate = useCallback((d: Date): ScheduledItem[] => allItems.filter(item => isSameDay(item.start, d)), [allItems]);

  // The Appointments page (HospitalAppointments.tsx) keeps its own separate
  // React Query cache for the same underlying data ("appointments",
  // "appointments-day", "appointments-calendar", "appointment-slots") — a
  // booking or status change made here left that page showing stale data
  // until its own staleTime expired, since the two pages never shared a
  // query key. Invalidate both sets so either page stays in sync with
  // changes made on the other.
  const invalidateAppts = () => {
    queryClient.invalidateQueries({ queryKey: ["sched-appointments"] });
    queryClient.invalidateQueries({ queryKey: ["appointments"] });
    queryClient.invalidateQueries({ queryKey: ["appointments-day"] });
    queryClient.invalidateQueries({ queryKey: ["appointments-calendar"] });
    queryClient.invalidateQueries({ queryKey: ["appointment-slots"] });
  };

  // An appointment booked/arrived/completed/cancelled anywhere else in the
  // app (front desk, patient profile, the queue on discharge) used to only
  // show up here after a manual refresh — nothing pushed a live update to
  // this page at all.
  useRealtimeChannel("appointment_updates", () => {
    invalidateAppts();
  });

  const arriveMutation = useMutation({
    mutationFn: (id: string) => api.hospital.appointments.arrive(id),
    onSuccess: (data: any) => {
      invalidateAppts();
      void queryClient.invalidateQueries({ queryKey: ["clinical-queue"] });
      toast({
        title: "Patient marked as arrived",
        description: data?.queue_number
          ? `Now on the queue as ${data.queue_number}`
          : data?.already_active ? "Already on the queue from an earlier visit today" : undefined,
      });
      setSelectedItem(null);
    },
    onError: () => toast({ title: "Failed to update", variant: "destructive" }),
  });
  const completeMutation = useMutation({ mutationFn: (id: string) => api.hospital.appointments.complete(id), onSuccess: () => { invalidateAppts(); toast({ title: "Appointment completed" }); setSelectedItem(null); }, onError: () => toast({ title: "Failed to update", variant: "destructive" }) });
  const cancelMutation = useMutation({ mutationFn: (id: string) => api.hospital.appointments.cancel(id, {}), onSuccess: () => { invalidateAppts(); toast({ title: "Appointment cancelled" }); setSelectedItem(null); }, onError: () => toast({ title: "Failed to cancel", variant: "destructive" }) });
  const noShowMutation = useMutation({ mutationFn: (id: string) => api.hospital.appointments.noShow(id), onSuccess: () => { invalidateAppts(); toast({ title: "Marked as no-show" }); setSelectedItem(null); }, onError: () => toast({ title: "Failed to update", variant: "destructive" }) });
  const remindMutation = useMutation({
    mutationFn: (id: string) => (api.hospital.appointments as any).remind(id),
    onSuccess: (data: any) => {
      if (data?.sent) { toast({ title: "Reminder sent", description: `Via ${(data.channels || []).join(", ")}` }); }
      else { toast({ title: "Reminder not sent", description: data?.reason ?? "No contact details on file", variant: "destructive" }); }
    },
  });
  const createTaskMutation = useMutation({
    mutationFn: (data: any) => api.tasks.create(data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["sched-tasks"] }); toast({ title: "Task created" }); setShowTaskDialog(false); setNewTask({ title: "", description: "", priority: "medium", due_date: "" }); },
    onError: () => toast({ title: "Failed to create task", variant: "destructive" }),
  });

  const navigate = (dir: 1 | -1) => {
    setCurrentDate(d => {
      if (viewMode === "month") return dir === 1 ? addMonths(d, 1) : subMonths(d, 1);
      if (viewMode === "week" || viewMode === "doctor") return dir === 1 ? addWeeks(d, 1) : subWeeks(d, 1);
      return addDays(d, dir);
    });
  };

  const rangeLabel = useMemo(() => {
    if (viewMode === "month") return format(currentDate, "MMMM yyyy");
    if (viewMode === "day") return format(currentDate, "EEEE, MMMM d, yyyy");
    const wStart = startOfWeek(currentDate, { weekStartsOn: 1 });
    const wEnd = endOfWeek(currentDate, { weekStartsOn: 1 });
    if (format(wStart, "MMM yyyy") === format(wEnd, "MMM yyyy")) return `${format(wStart, "d")} – ${format(wEnd, "d MMM yyyy")}`;
    return `${format(wStart, "d MMM")} – ${format(wEnd, "d MMM yyyy")}`;
  }, [viewMode, currentDate]);

  // ── Month View ─────────────────────────────────────────────────────────
  const MonthView = () => {
    const days = eachDayOfInterval({ start: startOfWeek(startOfMonth(currentDate), { weekStartsOn: 1 }), end: endOfWeek(endOfMonth(currentDate), { weekStartsOn: 1 }) });
    return (
      <div className="flex flex-col flex-1 overflow-auto">
        <div className="grid grid-cols-7 border-b shrink-0">
          {["Mon","Tue","Wed","Thu","Fri","Sat","Sun"].map(d => <div key={d} className="py-2 text-center text-xs font-medium text-muted-foreground">{d}</div>)}
        </div>
        <div className="grid grid-cols-7 flex-1">
          {days.map(day => {
            const dayItems = itemsForDate(day);
            return (
              <div key={day.toISOString()} onClick={() => { setCurrentDate(day); setViewMode("day"); }} className={cn("min-h-[88px] border-b border-r p-1 cursor-pointer hover:bg-accent/20 transition-colors", !isSameMonth(day, currentDate) && "opacity-40 bg-muted/20")}>
                <div className={cn("mb-1 flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium", isToday(day) && "bg-[#17449E] text-white")}>
                  {format(day, "d")}
                </div>
                <div className="space-y-px">
                  {dayItems.slice(0, 3).map(item => (
                    <div key={item.id} onClick={e => { e.stopPropagation(); setSelectedItem(item); }} className="truncate rounded px-1 py-px text-xs text-white font-medium cursor-pointer hover:opacity-90" style={{ backgroundColor: item.color }}>
                      {item.kind === "appointment" ? `${format(item.start, "HH:mm")} ${item.title}` : item.title}
                    </div>
                  ))}
                  {dayItems.length > 3 && <div className="pl-1 text-xs text-muted-foreground">+{dayItems.length - 3} more</div>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  // ── Week View ──────────────────────────────────────────────────────────
  const WeekView = () => {
    const wStart = startOfWeek(currentDate, { weekStartsOn: 1 });
    const weekDays = Array.from({ length: 7 }, (_, i) => addDays(wStart, i));
    const hours = Array.from({ length: HOUR_END - HOUR_START }, (_, i) => HOUR_START + i);
    return (
      <div className="flex-1 overflow-auto">
        <div className="sticky top-0 z-10 grid bg-background border-b" style={{ gridTemplateColumns: "3.5rem repeat(7, 1fr)" }}>
          <div className="border-r" />
          {weekDays.map(d => (
            <div key={d.toISOString()} className={cn("py-2 text-center text-xs border-l", isToday(d) && "bg-blue-50 dark:bg-blue-950/30")}>
              <div className="text-muted-foreground">{format(d, "EEE")}</div>
              <div className={cn("mx-auto mt-1 flex h-7 w-7 items-center justify-center rounded-full text-sm font-semibold", isToday(d) && "bg-[#17449E] text-white")}>{format(d, "d")}</div>
            </div>
          ))}
        </div>
        <div className="grid" style={{ gridTemplateColumns: "3.5rem repeat(7, 1fr)" }}>
          <div className="border-r">
            {hours.map(h => <div key={h} className="border-b text-right pr-2 text-xs text-muted-foreground pt-1" style={{ height: `${PX_PER_HOUR}px` }}>{String(h).padStart(2,"0")}:00</div>)}
          </div>
          {weekDays.map(d => {
            const dayAppts = itemsForDate(d).filter(i => i.kind === "appointment");
            const dayOthers = itemsForDate(d).filter(i => i.kind !== "appointment");
            return (
              <div key={d.toISOString()} className={cn("relative border-l", isToday(d) && "bg-blue-50/20 dark:bg-blue-950/10")} style={{ height: `${TOTAL_GRID_HEIGHT}px` }}>
                {hours.map(h => <div key={h} className="absolute left-0 right-0 border-b border-border/40" style={{ top: `${(h - HOUR_START) * PX_PER_HOUR}px` }} />)}
                {dayAppts.map(item => {
                  const appt = item.raw as CalendarAppointment;
                  const top = topPxForTime(appt.slot_time);
                  const height = heightPxForDuration(item.durationMins ?? 15);
                  if (top < 0 || top >= TOTAL_GRID_HEIGHT) return null;
                  return (
                    <div key={item.id} onClick={() => setSelectedItem(item)} className="absolute left-0.5 right-0.5 rounded px-1.5 py-0.5 text-xs text-white font-medium overflow-hidden cursor-pointer hover:opacity-90 z-10 border border-white/20" style={{ top: `${top}px`, height: `${height}px`, backgroundColor: item.color }}>
                      <div className="truncate font-semibold">{format(item.start, "HH:mm")} {item.title}</div>
                      {height > 28 && item.doctor && <div className="truncate opacity-80">{item.doctor}</div>}
                    </div>
                  );
                })}
                {dayOthers.slice(0, 2).map((item, idx) => (
                  <div key={item.id} onClick={() => setSelectedItem(item)} className="absolute left-0.5 right-0.5 rounded px-1 text-xs text-white font-medium cursor-pointer overflow-hidden z-10" style={{ top: `${idx * 15}px`, height: "13px", backgroundColor: item.color, opacity: 0.85 }}>
                    <div className="truncate">{item.title}</div>
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  // ── Day View ───────────────────────────────────────────────────────────
  const DayView = () => {
    const dayItems = itemsForDate(currentDate);
    const hours = Array.from({ length: HOUR_END - HOUR_START }, (_, i) => HOUR_START + i);
    return (
      <div className="flex-1 overflow-auto">
        <div className="border-b px-4 py-3">
          <h2 className="text-base font-semibold">{format(currentDate, "EEEE, MMMM d, yyyy")}</h2>
          <p className="text-xs text-muted-foreground mt-0.5">{dayItems.length} item{dayItems.length !== 1 ? "s" : ""} scheduled</p>
        </div>
        <div className="grid" style={{ gridTemplateColumns: "3.5rem 1fr" }}>
          <div className="border-r">
            {hours.map(h => <div key={h} className="border-b text-right pr-2 text-xs text-muted-foreground pt-1" style={{ height: `${PX_PER_HOUR}px` }}>{String(h).padStart(2,"0")}:00</div>)}
          </div>
          <div className="relative" style={{ height: `${TOTAL_GRID_HEIGHT}px` }}>
            {hours.map(h => <div key={h} className="absolute left-0 right-0 border-b border-border/40" style={{ top: `${(h - HOUR_START) * PX_PER_HOUR}px` }} />)}
            {dayItems.filter(i => i.kind === "appointment").map(item => {
              const appt = item.raw as CalendarAppointment;
              const top = topPxForTime(appt.slot_time);
              const height = heightPxForDuration(item.durationMins ?? 15);
              if (top < 0 || top >= TOTAL_GRID_HEIGHT) return null;
              return (
                <div key={item.id} onClick={() => setSelectedItem(item)} className="absolute left-1 right-1 rounded-md px-3 py-1 text-white cursor-pointer hover:opacity-90 z-10 border border-white/20" style={{ top: `${top}px`, height: `${Math.max(height, 36)}px`, backgroundColor: item.color }}>
                  <div className="text-sm font-semibold truncate">{format(item.start, "HH:mm")} — {item.title}</div>
                  {height >= 36 && <div className="text-xs opacity-85 truncate">{item.doctor} · {item.department} · {item.durationMins}min</div>}
                </div>
              );
            })}
            {dayItems.filter(i => i.kind !== "appointment").map((item, idx) => (
              <div key={item.id} onClick={() => setSelectedItem(item)} className="absolute left-1 right-1 rounded px-2 py-0.5 text-xs text-white font-medium cursor-pointer hover:opacity-90" style={{ top: `${idx * 18}px`, height: "16px", backgroundColor: item.color }}>
                <div className="truncate">{item.title}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  };

  // ── Doctor View ────────────────────────────────────────────────────────
  const DoctorView = () => {
    const dayAppts = itemsForDate(currentDate).filter(i => i.kind === "appointment");
    const uniqueDoctors = [...new Set(dayAppts.map(i => i.doctor).filter((d): d is string => Boolean(d)))];
    const hours = Array.from({ length: HOUR_END - HOUR_START }, (_, i) => HOUR_START + i);
    if (uniqueDoctors.length === 0) return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 text-muted-foreground">
        <Stethoscope className="h-10 w-10 opacity-30" />
        <div className="text-center"><p className="font-medium">No appointments for {format(currentDate, "MMMM d")}</p></div>
      </div>
    );
    const cols = `3.5rem repeat(${uniqueDoctors.length}, 1fr)`;
    return (
      <div className="flex-1 overflow-auto">
        <div className="sticky top-0 z-10 grid bg-background border-b" style={{ gridTemplateColumns: cols }}>
          <div className="border-r" />
          {uniqueDoctors.map(doc => {
            const count = dayAppts.filter(i => i.doctor === doc).length;
            return <div key={doc} className="py-2 text-center text-xs border-l px-1"><div className="font-semibold text-sm truncate">{doc}</div><div className="text-muted-foreground">{count} appt{count !== 1 ? "s" : ""}</div></div>;
          })}
        </div>
        <div className="grid" style={{ gridTemplateColumns: cols }}>
          <div className="border-r">
            {hours.map(h => <div key={h} className="border-b text-right pr-2 text-xs text-muted-foreground pt-1" style={{ height: `${PX_PER_HOUR}px` }}>{String(h).padStart(2,"0")}:00</div>)}
          </div>
          {uniqueDoctors.map(doc => {
            const docAppts = dayAppts.filter(i => i.doctor === doc);
            return (
              <div key={doc} className="relative border-l" style={{ height: `${TOTAL_GRID_HEIGHT}px` }}>
                {hours.map(h => <div key={h} className="absolute left-0 right-0 border-b border-border/40" style={{ top: `${(h - HOUR_START) * PX_PER_HOUR}px` }} />)}
                {docAppts.map(item => {
                  const appt = item.raw as CalendarAppointment;
                  const top = topPxForTime(appt.slot_time);
                  const height = heightPxForDuration(item.durationMins ?? 15);
                  if (top < 0 || top >= TOTAL_GRID_HEIGHT) return null;
                  return (
                    <div key={item.id} onClick={() => setSelectedItem(item)} className="absolute left-0.5 right-0.5 rounded px-1.5 py-0.5 text-xs text-white font-medium cursor-pointer hover:opacity-90 border border-white/20 overflow-hidden z-10" style={{ top: `${top}px`, height: `${height}px`, backgroundColor: item.color }}>
                      <div className="truncate font-semibold">{format(item.start, "HH:mm")}</div>
                      <div className="truncate">{item.patientName ?? "Patient"}</div>
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  // ── Detail Panel ───────────────────────────────────────────────────────
  const DetailPanel = () => {
    if (!selectedItem) return null;
    const item = selectedItem;
    const isAppt = item.kind === "appointment";
    const raw = item.raw as CalendarAppointment;
    const rawTask = item.raw as CalendarTask;
    const rawEvent = item.raw as CalendarEvent;
    const canArrive = isAppt && ["booked", "confirmed"].includes(item.status);
    const canComplete = isAppt && ["arrived", "confirmed", "booked"].includes(item.status);
    const canNoShow = isAppt && ["booked", "confirmed", "arrived"].includes(item.status);
    const canCancel = isAppt && !["completed", "cancelled", "no_show"].includes(item.status);
    return (
      <Sheet open={!!selectedItem} onOpenChange={(o) => { if (!o) setSelectedItem(null); }}>
        <SheetContent className={cn(PANEL_WIDTH.narrow, "space-y-4")}>
          <SheetHeader>
            <div className="flex items-center gap-2">
              <div className="h-3 w-3 rounded-full" style={{ backgroundColor: item.color }} />
              <SheetTitle className="capitalize">{item.kind}</SheetTitle>
            </div>
          </SheetHeader>
          <div className="space-y-4">
          <div>
            <h3 className="font-semibold text-base leading-tight">{item.title}</h3>
            <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {format(item.start, "EEE, MMM d · HH:mm")}
              {item.end && ` – ${format(item.end, "HH:mm")}`}
            </p>
          </div>
          {isAppt && (
            <>
              <div className="space-y-2 text-sm">
                {raw.doctor_name && <div className="flex items-start gap-2"><Stethoscope className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" /><span>{raw.doctor_name}</span></div>}
                {raw.department && <div className="flex items-start gap-2"><LayoutGrid className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" /><span>{raw.department}</span></div>}
                {raw.patient_name && <div className="flex items-start gap-2"><User className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" /><span>{raw.patient_name}</span></div>}
                {raw.patient_phone && <div className="flex items-start gap-2"><Phone className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" /><span className="text-xs">{raw.patient_phone}</span></div>}
                {raw.patient_email && <div className="flex items-start gap-2"><Mail className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" /><span className="text-xs break-all">{raw.patient_email}</span></div>}
                {raw.reason && <div className="rounded-md bg-muted/50 p-2 text-xs"><span className="font-medium">Reason: </span>{raw.reason}</div>}
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <Badge className="text-white capitalize" style={{ backgroundColor: item.color }}>{item.status.replace("_", " ")}</Badge>
                {raw.reminder_sent && <Badge variant="outline" className="text-xs gap-1"><Bell className="h-3 w-3" />Reminded</Badge>}
                <span className="text-xs text-muted-foreground">{raw.duration_mins ?? 15} min</span>
              </div>
              <div className="space-y-2">
                {canArrive && <Button size="sm" className="w-full text-white" style={{ backgroundColor: STATUS_COLORS.arrived }} disabled={arriveMutation.isPending} onClick={() => arriveMutation.mutate(item.id)}><Check className="mr-2 h-4 w-4" />Mark Arrived</Button>}
                {canComplete && <Button size="sm" className="w-full text-white" style={{ backgroundColor: STATUS_COLORS.completed }} disabled={completeMutation.isPending} onClick={() => completeMutation.mutate(item.id)}><Check className="mr-2 h-4 w-4" />Mark Completed</Button>}
              </div>
              <div className="flex flex-col gap-2 border-t pt-3">
                <Button size="sm" variant="outline" className="w-full" disabled={remindMutation.isPending} onClick={() => remindMutation.mutate(item.id)}>
                  <Bell className="mr-2 h-4 w-4" />{remindMutation.isPending ? "Sending…" : "Send Reminder"}
                </Button>
                {canNoShow && <Button size="sm" variant="outline" className="w-full text-orange-500 border-orange-500/40 hover:bg-orange-500/10" disabled={noShowMutation.isPending} onClick={() => noShowMutation.mutate(item.id)}><UserX className="mr-2 h-4 w-4" />Mark No Show</Button>}
                {canCancel && <Button size="sm" variant="outline" className="w-full text-destructive border-destructive/50 hover:bg-destructive/10" disabled={cancelMutation.isPending} onClick={() => cancelMutation.mutate(item.id)}>Cancel Appointment</Button>}
              </div>
            </>
          )}
          {item.kind === "task" && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge className="text-white capitalize" style={{ backgroundColor: item.color }}>{item.status.replace("_", " ")}</Badge>
                <Badge variant="outline" className="capitalize text-xs">{rawTask.priority}</Badge>
              </div>
              {rawTask.description && <p className="text-sm text-muted-foreground">{rawTask.description}</p>}
              {rawTask.assigned_to && <div className="flex items-center gap-2 text-sm"><User className="h-4 w-4 text-muted-foreground" /><span>{rawTask.assigned_to}</span></div>}
            </div>
          )}
          {item.kind === "event" && (
            <div className="space-y-2">
              <Badge variant="outline" className="capitalize text-xs">{rawEvent.event_type}</Badge>
              {rawEvent.location && <p className="text-sm text-muted-foreground">📍 {rawEvent.location}</p>}
            </div>
          )}
          </div>
        </SheetContent>
      </Sheet>
    );
  };

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <motion.div className="flex h-[calc(100vh-64px)] overflow-hidden bg-background" {...motionTransitions}>

      {/* LEFT PANEL */}
      <div className="w-72 shrink-0 border-r flex flex-col overflow-y-auto bg-sidebar/40">
        <div className="p-2 border-b">
          {/* Compact day cells overridden here rather than in components/ui/calendar.tsx,
              which StaffDashboard also renders at full width. 7 x 32px = 224px
              fits the 248px this panel now offers. */}
          <Calendar
            mode="single"
            selected={currentDate}
            onSelect={d => { if (d) { setCurrentDate(d); setViewMode("day"); } }}
            className="rounded-md p-2"
            classNames={{
              day: "h-8 w-8 text-center text-sm p-0 relative focus-within:relative focus-within:z-20",
              day_button: "h-8 w-8 p-0 font-normal aria-selected:opacity-100",
              weekday: "text-muted-foreground rounded-md w-8 font-normal text-xs",
            }}
          />
        </div>
        <div className="p-3 border-b space-y-3">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <Filter className="h-3 w-3" />Filters
          </div>
          <div className="space-y-2">
            {[
              { key: "appts", label: "Appointments", color: "#17449E", value: showAppts, setter: setShowAppts },
              { key: "tasks", label: "Tasks", color: "#F59E0B", value: showTasks, setter: setShowTasks },
              { key: "events", label: "Events", color: "#113379", value: showEvents, setter: setShowEvents },
            ].map(f => (
              <label key={f.key} className="flex items-center gap-2 cursor-pointer">
                <Checkbox checked={f.value} onCheckedChange={v => f.setter(Boolean(v))} />
                <span className="flex items-center gap-1.5 text-sm">
                  <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ backgroundColor: f.color }} />{f.label}
                </span>
              </label>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            Only your own appointments, tasks and events. The whole hospital's diary is the{" "}
            <a href="#/calendar" className="text-primary hover:underline">Hospital Calendar</a>.
          </p>
        </div>
        <div className="p-3 border-b">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Status</div>
          <div className="space-y-1">
            {[["booked","Booked"],["confirmed","Confirmed"],["arrived","Arrived"],["completed","Completed"],["no_show","No Show"]].map(([k,l]) => (
              <div key={k} className="flex items-center gap-2 text-xs"><span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: STATUS_COLORS[k] }} />{l}</div>
            ))}
          </div>
        </div>
        <div className="p-3 space-y-2 mt-auto">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1">Quick Actions</div>
          <Button size="sm" className="w-full text-white" style={{ backgroundColor: "#17449E" }} onClick={() => { resetNewApptForm(); setShowApptDialog(true); }}>
            <Plus className="mr-2 h-4 w-4" />New Appointment
          </Button>
          <Button size="sm" variant="outline" className="w-full" onClick={() => setShowTaskDialog(true)}>
            <Plus className="mr-2 h-4 w-4" />Schedule Task
          </Button>
        </div>
      </div>

      {/* CENTER */}
      <div className="flex-1 min-w-0 flex flex-col">
        <div className="flex items-center justify-between border-b px-4 py-2 shrink-0 gap-4">
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => navigate(-1)}><ChevronLeft className="h-4 w-4" /></Button>
            <Button variant="ghost" size="sm" className="text-xs px-2" onClick={() => setCurrentDate(new Date())}>Today</Button>
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => navigate(1)}><ChevronRight className="h-4 w-4" /></Button>
            <h2 className="text-sm font-semibold ml-2 whitespace-nowrap">{rangeLabel}</h2>
            {calFetching && <RefreshCw className="h-3 w-3 animate-spin text-muted-foreground ml-1" />}
          </div>
          <div className="flex items-center rounded-md border overflow-hidden shrink-0">
            {([
              { key: "month" as ViewMode, label: "Month", Icon: LayoutGrid },
              { key: "week" as ViewMode, label: "Week", Icon: CalendarDays },
              { key: "day" as ViewMode, label: "Day", Icon: List },
              { key: "doctor" as ViewMode, label: "Doctor", Icon: Stethoscope },
            ]).map(({ key, label, Icon }) => (
              <button key={key} onClick={() => setViewMode(key)} className={cn("flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors", viewMode === key ? "bg-[#17449E] text-white" : "text-muted-foreground hover:bg-muted")}>
                <Icon className="h-3.5 w-3.5" />{label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex-1 overflow-hidden flex flex-col">
          {viewMode === "month" && <MonthView />}
          {viewMode === "week" && <WeekView />}
          {viewMode === "day" && <DayView />}
          {viewMode === "doctor" && <DoctorView />}
        </div>
      </div>

      {/* RIGHT DETAIL PANEL */}
      {selectedItem && <DetailPanel />}

      {/* TASK DIALOG */}
      <Dialog open={showTaskDialog} onOpenChange={setShowTaskDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Schedule Task</DialogTitle><DialogDescription>Create a task or operational activity</DialogDescription></DialogHeader>
          <div className="space-y-3">
            <Input placeholder="Task title *" value={newTask.title} onChange={e => setNewTask(p => ({ ...p, title: e.target.value }))} />
            <Textarea placeholder="Description (optional)" rows={2} value={newTask.description} onChange={e => setNewTask(p => ({ ...p, description: e.target.value }))} />
            <div className="grid grid-cols-2 gap-2">
              <Select value={newTask.priority} onValueChange={v => setNewTask(p => ({ ...p, priority: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{["low","medium","high","urgent"].map(p => <SelectItem key={p} value={p} className="capitalize">{p}</SelectItem>)}</SelectContent>
              </Select>
              <Input type="date" value={newTask.due_date} onChange={e => setNewTask(p => ({ ...p, due_date: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowTaskDialog(false)}>Cancel</Button>
            <Button disabled={!newTask.title.trim() || createTaskMutation.isPending} onClick={() => createTaskMutation.mutate({ title: newTask.title, description: newTask.description || undefined, priority: newTask.priority, due_date: newTask.due_date || undefined, source: "manual" })} style={{ backgroundColor: "#17449E" }} className="text-white">
              {createTaskMutation.isPending ? "Creating…" : "Create Task"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* APPOINTMENT DIALOG */}
      <Dialog open={showApptDialog} onOpenChange={(o) => { setShowApptDialog(o); if (!o) resetNewApptForm(); }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New Appointment</DialogTitle><DialogDescription>Book a patient into an available slot</DialogDescription></DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label className="text-xs">Patient *</Label>
              {!selectedApptPatient ? (
                <>
                  <Input placeholder="Search patient by name, phone, or HMO ID…" value={apptPatientQuery}
                    onChange={e => handleApptPatientQueryChange(e.target.value)} />
                  {apptPatientSearching && <p className="text-xs text-muted-foreground">Searching…</p>}
                  {apptPatientResults.length > 0 && (
                    <div className="space-y-1.5 max-h-40 overflow-y-auto">
                      {apptPatientResults.map((p: any) => (
                        <button key={p.id}
                          className="w-full text-left rounded-md border px-3 py-2 text-xs hover:bg-muted/40 transition-colors"
                          onClick={() => setSelectedApptPatient(p)}>
                          <p className="font-medium text-sm">{p.first_name} {p.last_name}</p>
                          <p className="text-muted-foreground">MRN: {p.mrn} · {p.gender ?? "—"} · {p.phone ?? "—"}</p>
                        </button>
                      ))}
                    </div>
                  )}
                  {apptDebouncedQuery.length >= 2 && !apptPatientSearching && apptPatientResults.length === 0 && (
                    <p className="text-xs text-muted-foreground">No patients found.</p>
                  )}
                </>
              ) : (
                <div className="rounded-md border border-primary/40 bg-primary/5 px-3 py-2 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">{selectedApptPatient.first_name} {selectedApptPatient.last_name}</p>
                    <p className="text-xs text-muted-foreground font-mono">{selectedApptPatient.mrn}</p>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => setSelectedApptPatient(null)}>Change</Button>
                </div>
              )}
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Date</Label>
              <Input type="date" value={newApptDate} onChange={e => { setNewApptDate(e.target.value); setNewApptSlotId(""); }} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Available Slot *</Label>
              <Select value={newApptSlotId} onValueChange={setNewApptSlotId} disabled={newApptSlotsLoading || newApptSlots.length === 0}>
                <SelectTrigger>
                  <SelectValue placeholder={newApptSlotsLoading ? "Loading slots…" : newApptSlots.length === 0 ? "No slots available this date" : "Select a slot"} />
                </SelectTrigger>
                <SelectContent>
                  {newApptSlots.map((s: any) => (
                    <SelectItem key={s.id} value={String(s.id)}>
                      {s.start_time?.slice(0, 5)}{s.provider_name ? ` — ${s.provider_name}` : ""}{s.department ? ` (${s.department})` : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Reason for visit</Label>
              <Input placeholder="Reason for visit" value={newApptReason} onChange={e => setNewApptReason(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowApptDialog(false)}>Cancel</Button>
            <Button disabled={!selectedApptPatient || !newApptSlotId} style={{ backgroundColor: "#17449E" }} className="text-white" onClick={async () => {
              try {
                await api.hospital.appointments.book({ patient_id: selectedApptPatient.id, slot_id: parseInt(newApptSlotId), reason: newApptReason || undefined });
                invalidateAppts();
                toast({ title: "Appointment booked successfully" });
                setShowApptDialog(false);
                resetNewApptForm();
              } catch (err: any) {
                toast({ title: "Booking failed", description: err?.message ?? "Unknown error", variant: "destructive" });
              }
            }}>Book Appointment</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </motion.div>
  );
};

export default SchedulingCenter;
