import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
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
  Users, RefreshCw, Loader2, Plus, CalendarDays,
  Banknote, CheckCircle2, XCircle, Clock, Trash2,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { StaffPicker } from "@/components/shared/StaffPicker";
import { OnlineStaffCard } from "@/components/dashboard/OnlineStaffCard";
import {
  SHIFT_COLORS, LEAVE_STATUS_COLORS, PAY_STATUS_COLORS,
  SHIFT_TYPES, LEAVE_TYPES, PAYROLL_STATUSES,
  emptyShift, emptyLeave, emptyPayroll,
} from "@/components/hr/hr-shared";

const MONTHS = [
  "January","February","March","April","May","June",
  "July","August","September","October","November","December",
];

export default function HRShifts() {
  const { toast } = useToast();
  const qc = useQueryClient();

  const today = new Date().toISOString().split("T")[0];
  const [weekStart, setWeekStart] = useState(today);
  const [filterLeaveStatus, setFilterLeaveStatus] = useState("all");
  const [filterPayStatus, setFilterPayStatus] = useState("all");

  const [shiftOpen, setShiftOpen] = useState(false);
  const [shiftForm, setShiftForm] = useState({ ...emptyShift });

  const [leaveOpen, setLeaveOpen] = useState(false);
  const [leaveForm, setLeaveForm] = useState({ ...emptyLeave });

  const [payrollOpen, setPayrollOpen] = useState(false);
  const [payrollForm, setPayrollForm] = useState({ ...emptyPayroll });

  const [approveId, setApproveId] = useState<string | null>(null);
  const [approveAction, setApproveAction] = useState<"approved" | "rejected">("approved");
  const [approveOpen, setApproveOpen] = useState(false);

  // Queries
  const { data: statsData } = useQuery({
    queryKey: ["hr-stats"],
    queryFn: () => api.hr.stats(),
  });

  const { data: shiftsData, isLoading: shiftsLoading, refetch: refetchShifts } = useQuery({
    queryKey: ["hr-shifts", weekStart],
    queryFn: () => api.hr.listShifts({ week_start: weekStart }),
  });

  const { data: leaveData, isLoading: leaveLoading, refetch: refetchLeave } = useQuery({
    queryKey: ["hr-leave", filterLeaveStatus],
    queryFn: () => api.hr.listLeave({ status: filterLeaveStatus !== "all" ? filterLeaveStatus : undefined }),
  });

  const { data: payrollData, isLoading: payLoading, refetch: refetchPayroll } = useQuery({
    queryKey: ["hr-payroll", filterPayStatus],
    queryFn: () => api.hr.listPayroll({ status: filterPayStatus !== "all" ? filterPayStatus : undefined }),
  });

  const hrStats   = statsData?.shifts_today || { total: 0, on_duty: 0, by_type: {} };
  const leaveKpi  = statsData?.leave         || { pending: 0, approved: 0 };
  const payKpi    = statsData?.payroll        || { pending_amount: 0 };
  const shifts    = shiftsData?.shifts   || [];
  const leaves    = leaveData?.requests  || [];
  const payrolls  = payrollData?.records || [];

  function resetShiftForm() { setShiftForm({ ...emptyShift }); }
  function resetLeaveForm() { setLeaveForm({ ...emptyLeave }); }
  function resetPayrollForm() { setPayrollForm({ ...emptyPayroll }); }

  // Mutations
  const shiftMut = useMutation({
    mutationFn: () => api.hr.createShift({
      ...shiftForm,
    }),
    onSuccess: () => {
      toast({ title: "Shift scheduled" });
      setShiftOpen(false);
      resetShiftForm();
      qc.invalidateQueries({ queryKey: ["hr-shifts"] });
      qc.invalidateQueries({ queryKey: ["hr-stats"] });
    },
    onError: (e: any) => toast({ title: e?.message || "Failed to schedule shift", variant: "destructive" }),
  });

  const deleteShiftMut = useMutation({
    mutationFn: (id: string) => api.hr.deleteShift(id),
    onSuccess: () => {
      toast({ title: "Shift removed" });
      refetchShifts();
      qc.invalidateQueries({ queryKey: ["hr-stats"] });
    },
    onError: (e: any) => toast({ title: e?.message || "Failed to remove shift", variant: "destructive" }),
  });

  const leaveMut = useMutation({
    mutationFn: () => api.hr.submitLeave(leaveForm),
    onSuccess: () => {
      toast({ title: "Leave request submitted" });
      setLeaveOpen(false);
      resetLeaveForm();
      qc.invalidateQueries({ queryKey: ["hr-leave"] });
      qc.invalidateQueries({ queryKey: ["hr-stats"] });
    },
    onError: (e: any) => toast({ title: e?.message || "Failed to submit leave", variant: "destructive" }),
  });

  const leaveActionMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.hr.updateLeaveStatus(id, { status }),
    onSuccess: (_, v) => {
      toast({ title: `Leave ${v.status}` });
      setApproveOpen(false);
      qc.invalidateQueries({ queryKey: ["hr-leave"] });
      qc.invalidateQueries({ queryKey: ["hr-stats"] });
    },
    onError: (e: any) => toast({ title: e?.message || "Action failed", variant: "destructive" }),
  });

  const payrollMut = useMutation({
    mutationFn: () => api.hr.createPayroll({
      ...payrollForm,
      period_month:   Number(payrollForm.period_month),
      period_year:    Number(payrollForm.period_year),
      gross_salary:   Number(payrollForm.gross_salary),
      overtime_hours: Number(payrollForm.overtime_hours),
      overtime_rate:  Number(payrollForm.overtime_rate),
      allowances:     Number(payrollForm.allowances),
      deductions:     Number(payrollForm.deductions),
      tax:            Number(payrollForm.tax),
      pension:        Number(payrollForm.pension),
    }),
    onSuccess: () => {
      toast({ title: "Payroll record created" });
      setPayrollOpen(false);
      resetPayrollForm();
      qc.invalidateQueries({ queryKey: ["hr-payroll"] });
      qc.invalidateQueries({ queryKey: ["hr-stats"] });
    },
    onError: (e: any) => toast({ title: e?.message || "Failed to create payroll record", variant: "destructive" }),
  });

  const estimatedNet = payrollForm.gross_salary
    ? Math.max(0,
        Number(payrollForm.gross_salary)
        + (Number(payrollForm.overtime_hours || 0) * Number(payrollForm.overtime_rate || 0))
        + Number(payrollForm.allowances || 0)
        - Number(payrollForm.deductions || 0) - Number(payrollForm.tax || 0) - Number(payrollForm.pension || 0)
      )
    : null;

  return (
    <motion.div className="p-6 space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-500/20 rounded-lg">
            <Users className="w-6 h-6 text-blue-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">HR — Shifts & Leave</h1>
            <p className="text-sm text-muted-foreground">Staff scheduling, leave management, and payroll</p>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap justify-end">
          <Button variant="outline" size="sm" className="border-border"
            onClick={() => { refetchShifts(); refetchLeave(); refetchPayroll(); }}>
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          <Button size="sm" variant="outline" className="border-yellow-500/40 text-yellow-700 dark:text-yellow-400 hover:bg-yellow-500/10"
            onClick={() => { resetLeaveForm(); setLeaveOpen(true); }}>
            <CalendarDays className="w-4 h-4 mr-1" /> Leave Request
          </Button>
          <Button size="sm" variant="outline" className="border-green-500/40 text-green-700 dark:text-green-400 hover:bg-green-500/10"
            onClick={() => { resetPayrollForm(); setPayrollOpen(true); }}>
            <Banknote className="w-4 h-4 mr-1" /> Add Payroll
          </Button>
          <Button size="sm" className="bg-blue-700 hover:bg-blue-800"
            onClick={() => { resetShiftForm(); setShiftOpen(true); }}>
            <Plus className="w-4 h-4 mr-1" /> Add Shift
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <OnlineStaffCard />
        {[
          { label: "On Duty Today",   value: hrStats.on_duty,                   color: "text-blue-700",    bg: "bg-blue-50" },
          { label: "Total Shifts",    value: hrStats.total,                      color: "text-foreground",  bg: "bg-muted/30" },
          { label: "Pending Leave",   value: leaveKpi.pending,                  color: leaveKpi.pending > 0 ? "text-yellow-700" : "text-muted-foreground", bg: leaveKpi.pending > 0 ? "bg-yellow-50" : "bg-muted/30" },
          { label: "Pending Payroll", value: `₦${payKpi.pending_amount.toLocaleString()}`, color: "text-green-700 dark:text-green-400", bg: "bg-green-500/10" },
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
      <Tabs defaultValue="shifts">
        <TabsList className="bg-muted border border-border">
          <TabsTrigger value="shifts">Shift Roster</TabsTrigger>
          <TabsTrigger value="leave">Leave Requests</TabsTrigger>
          <TabsTrigger value="payroll">Payroll</TabsTrigger>
        </TabsList>

        {/* Shifts Tab */}
        <TabsContent value="shifts" className="mt-4 space-y-4">
          <div className="flex items-center gap-3">
            <Label className="text-muted-foreground text-sm">Week starting</Label>
            <Input type="date" value={weekStart}
              onChange={e => setWeekStart(e.target.value)}
              className="w-44 bg-background border-border text-foreground text-sm h-8" />
          </div>
          <Card className="border-border bg-muted/30">
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  {["Date","Staff","Department","Designation","Type","Time","Status","Action"].map(h => (
                    <TableHead key={h} className="text-muted-foreground text-xs">{h}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {shiftsLoading
                  ? <TableRow><TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                      <Loader2 className="w-5 h-5 animate-spin inline mr-2" />Loading…
                    </TableCell></TableRow>
                  : shifts.length === 0
                    ? <TableRow><TableCell colSpan={8} className="text-center py-8 text-muted-foreground">No shifts this week</TableCell></TableRow>
                    : shifts.map((s: any) => (
                      <TableRow key={s.id} className="border-border hover:bg-muted">
                        <TableCell className="text-xs text-muted-foreground">{s.shift_date}</TableCell>
                        <TableCell className="text-sm text-foreground">{s.staff_name || s.staff_id}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{s.department || "—"}</TableCell>
                        <TableCell className="text-xs text-muted-foreground capitalize">{s.designation || "—"}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cn("text-xs capitalize", SHIFT_COLORS[s.shift_type] || "")}>
                            {s.shift_type}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs font-mono text-muted-foreground">
                          {s.start_time && s.end_time ? `${s.start_time}–${s.end_time}` : s.start_time || "—"}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground capitalize">{s.status}</TableCell>
                        <TableCell>
                          {s.status === "scheduled" && (
                            <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-red-400 hover:text-red-300"
                              onClick={() => deleteShiftMut.mutate(s.id)} disabled={deleteShiftMut.isPending}
                              title="Remove shift">
                              <Trash2 className="w-3 h-3" />
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))
                }
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        {/* Leave Requests Tab */}
        <TabsContent value="leave" className="mt-4 space-y-4">
          <div className="flex gap-2 flex-wrap">
            {["all","pending","approved","rejected","cancelled"].map(s => (
              <button key={s} onClick={() => setFilterLeaveStatus(s)}
                className={cn("px-3 py-1 rounded-full text-xs border transition-colors",
                  filterLeaveStatus === s ? "bg-blue-700 border-blue-600 text-foreground" : "border-border text-muted-foreground hover:border-primary/50")}>
                {s === "all" ? "All" : s}
              </button>
            ))}
          </div>
          <Card className="border-border bg-muted/30">
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  {["Staff","Department","Type","Start","End","Days","Status","Actions"].map(h => (
                    <TableHead key={h} className="text-muted-foreground text-xs">{h}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {leaveLoading
                  ? <TableRow><TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                      <Loader2 className="w-5 h-5 animate-spin inline mr-2" />Loading…
                    </TableCell></TableRow>
                  : leaves.length === 0
                    ? <TableRow><TableCell colSpan={8} className="text-center py-8 text-muted-foreground">No leave requests</TableCell></TableRow>
                    : leaves.map((l: any) => (
                      <TableRow key={l.id} className="border-border hover:bg-muted">
                        <TableCell className="text-sm text-foreground">{l.staff_name || l.staff_id}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{l.department || "—"}</TableCell>
                        <TableCell className="text-xs text-muted-foreground capitalize">{l.leave_type}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{l.start_date}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{l.end_date}</TableCell>
                        <TableCell className="text-sm text-foreground font-medium">{l.days_count}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cn("text-xs capitalize", LEAVE_STATUS_COLORS[l.status] || "")}>
                            {l.status === "approved" ? <CheckCircle2 className="w-3 h-3 mr-1 inline" /> : null}
                            {l.status === "rejected" ? <XCircle className="w-3 h-3 mr-1 inline" /> : null}
                            {l.status === "pending" ? <Clock className="w-3 h-3 mr-1 inline" /> : null}
                            {l.status}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {l.status === "pending" && (
                            <div className="flex gap-1">
                              <Button size="sm" className="h-6 text-xs px-2 bg-green-700 hover:bg-green-600"
                                onClick={() => { setApproveId(l.id); setApproveAction("approved"); setApproveOpen(true); }}>
                                Approve
                              </Button>
                              <Button size="sm" className="h-6 text-xs px-2 bg-red-700 hover:bg-red-600"
                                onClick={() => { setApproveId(l.id); setApproveAction("rejected"); setApproveOpen(true); }}>
                                Reject
                              </Button>
                            </div>
                          )}
                        </TableCell>
                      </TableRow>
                    ))
                }
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        {/* Payroll Tab */}
        <TabsContent value="payroll" className="mt-4 space-y-4">
          <div className="flex gap-2">
            {["all", ...PAYROLL_STATUSES].map(s => (
              <button key={s} onClick={() => setFilterPayStatus(s)}
                className={cn("px-3 py-1 rounded-full text-xs border transition-colors capitalize",
                  filterPayStatus === s ? "bg-green-700 border-green-600 text-foreground" : "border-border text-muted-foreground hover:border-primary/50")}>
                {s === "all" ? "All" : s}
              </button>
            ))}
          </div>
          <Card className="border-border bg-muted/30">
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  {["Staff","Department","Period","Gross","Allowances","Deductions","Net Salary","Status"].map(h => (
                    <TableHead key={h} className="text-muted-foreground text-xs">{h}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {payLoading
                  ? <TableRow><TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                      <Loader2 className="w-5 h-5 animate-spin inline mr-2" />Loading…
                    </TableCell></TableRow>
                  : payrolls.length === 0
                    ? <TableRow><TableCell colSpan={8} className="text-center py-8 text-muted-foreground">No payroll records</TableCell></TableRow>
                    : payrolls.map((p: any) => (
                      <TableRow key={p.id} className="border-border hover:bg-muted">
                        <TableCell className="text-sm text-foreground">{p.staff_name || p.staff_id}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{p.department || "—"}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{MONTHS[(p.period_month || 1) - 1]?.slice(0, 3)} {p.period_year}</TableCell>
                        <TableCell className="text-sm">₦{Number(p.gross_salary).toLocaleString()}</TableCell>
                        <TableCell className="text-sm text-green-700 dark:text-green-400">+₦{Number(p.allowances || 0).toLocaleString()}</TableCell>
                        <TableCell className="text-sm text-red-700 dark:text-red-400">-₦{(Number(p.deductions || 0) + Number(p.tax || 0) + Number(p.pension || 0)).toLocaleString()}</TableCell>
                        <TableCell className="text-sm font-bold text-foreground">₦{Number(p.net_salary || 0).toLocaleString()}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cn("text-xs capitalize", PAY_STATUS_COLORS[p.status] || "")}>
                            {p.status}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))
                }
              </TableBody>
            </Table>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── Add Shift Dialog ──────────────────────────────────────────────── */}
      <Dialog open={shiftOpen} onOpenChange={(o) => { setShiftOpen(o); if (!o) resetShiftForm(); }}>
        <DialogContent className="bg-card border-border text-foreground max-w-lg">
          <DialogHeader>
            <DialogTitle>Schedule Shift</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Staff Member *</Label>
              <StaffPicker value={shiftForm.staff_id}
                onChange={(id, staff) => setShiftForm(p => ({ ...p, staff_id: id, department: staff?.department || p.department }))} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Department</Label>
              <Input value={shiftForm.department}
                onChange={e => setShiftForm(p => ({ ...p, department: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Shift Type</Label>
              <Select value={shiftForm.shift_type} onValueChange={v => setShiftForm(p => ({ ...p, shift_type: v as any }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {SHIFT_TYPES.map(t => <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Date *</Label>
              <Input type="date" value={shiftForm.shift_date}
                onChange={e => setShiftForm(p => ({ ...p, shift_date: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Start Time *</Label>
              <Input type="time" value={shiftForm.start_time}
                onChange={e => setShiftForm(p => ({ ...p, start_time: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">End Time *</Label>
              <Input type="time" value={shiftForm.end_time}
                onChange={e => setShiftForm(p => ({ ...p, end_time: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Notes</Label>
              <Textarea value={shiftForm.notes}
                onChange={e => setShiftForm(p => ({ ...p, notes: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-14 resize-none" />
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setShiftOpen(false)}>Cancel</Button>
            <Button className="bg-blue-700 hover:bg-blue-800"
              disabled={shiftMut.isPending || !shiftForm.staff_id || !shiftForm.shift_date || !shiftForm.start_time || !shiftForm.end_time}
              onClick={() => shiftMut.mutate()}>
              {shiftMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Schedule
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Leave Request Dialog ──────────────────────────────────────────── */}
      <Dialog open={leaveOpen} onOpenChange={(o) => { setLeaveOpen(o); if (!o) resetLeaveForm(); }}>
        <DialogContent className="bg-card border-border text-foreground max-w-lg">
          <DialogHeader>
            <DialogTitle>Submit Leave Request</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Staff Member *</Label>
              <StaffPicker value={leaveForm.staff_id}
                onChange={(id) => setLeaveForm(p => ({ ...p, staff_id: id }))} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Leave Type</Label>
              <Select value={leaveForm.leave_type} onValueChange={v => setLeaveForm(p => ({ ...p, leave_type: v as any }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {LEAVE_TYPES.map(t => <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1" />
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Start Date *</Label>
              <Input type="date" value={leaveForm.start_date}
                onChange={e => setLeaveForm(p => ({ ...p, start_date: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">End Date *</Label>
              <Input type="date" value={leaveForm.end_date}
                onChange={e => setLeaveForm(p => ({ ...p, end_date: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Reason</Label>
              <Textarea value={leaveForm.reason}
                onChange={e => setLeaveForm(p => ({ ...p, reason: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-16 resize-none" />
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setLeaveOpen(false)}>Cancel</Button>
            <Button className="bg-blue-700 hover:bg-blue-800"
              disabled={leaveMut.isPending || !leaveForm.staff_id || !leaveForm.start_date || !leaveForm.end_date}
              onClick={() => leaveMut.mutate()}>
              {leaveMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Submit Request
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Approve/Reject Leave Dialog ───────────────────────────────────── */}
      <Dialog open={approveOpen} onOpenChange={setApproveOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-sm">
          <DialogHeader>
            <DialogTitle className={cn(approveAction === "approved" ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400")}>
              {approveAction === "approved" ? "Approve" : "Reject"} Leave Request
            </DialogTitle>
            <DialogDescription className="text-muted-foreground">
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setApproveOpen(false)}>Cancel</Button>
            <Button className={approveAction === "approved" ? "bg-green-700 hover:bg-green-600" : "bg-red-700 hover:bg-red-600"}
              disabled={leaveActionMut.isPending}
              onClick={() => leaveActionMut.mutate({ id: approveId!, status: approveAction })}>
              {leaveActionMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Confirm {approveAction === "approved" ? "Approval" : "Rejection"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Add Payroll Dialog ────────────────────────────────────────────── */}
      <Dialog open={payrollOpen} onOpenChange={(o) => { setPayrollOpen(o); if (!o) resetPayrollForm(); }}>
        <DialogContent className="bg-card border-border text-foreground max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Create Payroll Record</DialogTitle>
            <DialogDescription className="text-muted-foreground">Net salary is auto-calculated</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Staff Member *</Label>
              <StaffPicker value={payrollForm.staff_id}
                onChange={(id, staff) => setPayrollForm(p => ({
                  ...p, staff_id: id,
                  gross_salary: p.gross_salary || (staff?.monthly_gross ? String(staff.monthly_gross) : p.gross_salary),
                }))} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Period Month *</Label>
              <Select value={payrollForm.period_month} onValueChange={v => setPayrollForm(p => ({ ...p, period_month: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {MONTHS.map((m, i) => <SelectItem key={m} value={String(i + 1)}>{m}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Period Year *</Label>
              <Input type="number" value={payrollForm.period_year}
                onChange={e => setPayrollForm(p => ({ ...p, period_year: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Gross Salary *</Label>
              <Input type="number" value={payrollForm.gross_salary}
                onChange={e => setPayrollForm(p => ({ ...p, gross_salary: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Payment Method</Label>
              <Select value={payrollForm.payment_method}
                onValueChange={v => setPayrollForm(p => ({ ...p, payment_method: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {["bank_transfer","cash","cheque"].map(m =>
                    <SelectItem key={m} value={m} className="capitalize">{m.replace("_"," ")}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Overtime Hours</Label>
              <Input type="number" value={payrollForm.overtime_hours}
                onChange={e => setPayrollForm(p => ({ ...p, overtime_hours: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Overtime Rate (₦/hr)</Label>
              <Input type="number" value={payrollForm.overtime_rate}
                onChange={e => setPayrollForm(p => ({ ...p, overtime_rate: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Allowances</Label>
              <Input type="number" value={payrollForm.allowances}
                onChange={e => setPayrollForm(p => ({ ...p, allowances: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Deductions</Label>
              <Input type="number" value={payrollForm.deductions}
                onChange={e => setPayrollForm(p => ({ ...p, deductions: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Tax (PAYE)</Label>
              <Input type="number" value={payrollForm.tax}
                onChange={e => setPayrollForm(p => ({ ...p, tax: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Pension</Label>
              <Input type="number" value={payrollForm.pension}
                onChange={e => setPayrollForm(p => ({ ...p, pension: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-8" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Status</Label>
              <Select value={payrollForm.status} onValueChange={v => setPayrollForm(p => ({ ...p, status: v as any }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {PAYROLL_STATUSES.map(s => <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Notes</Label>
              <Textarea value={payrollForm.notes}
                onChange={e => setPayrollForm(p => ({ ...p, notes: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-14 resize-none" />
            </div>
            {estimatedNet !== null && (
              <div className="col-span-2 p-3 rounded-lg bg-green-500/10 border border-green-500/20">
                <p className="text-xs text-muted-foreground">Estimated Net Salary</p>
                <p className="text-xl font-bold text-green-700 dark:text-green-400">₦{estimatedNet.toLocaleString()}</p>
              </div>
            )}
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setPayrollOpen(false)}>Cancel</Button>
            <Button className="bg-green-700 hover:bg-green-600"
              disabled={payrollMut.isPending || !payrollForm.staff_id || !payrollForm.gross_salary}
              onClick={() => payrollMut.mutate()}>
              {payrollMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Create Record
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
