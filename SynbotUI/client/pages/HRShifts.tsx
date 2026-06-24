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
  Users, RefreshCw, Loader2, Plus, CalendarDays,
  Banknote, CheckCircle2, XCircle, Clock, Trash2,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";

const SHIFT_COLORS: Record<string, string> = {
  morning:   "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  afternoon: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  night:     "bg-blue-500/20 text-blue-400 border-blue-500/30",
  on_call:   "bg-sky-500/20 text-sky-400 border-sky-500/30",
  split:     "bg-primary/20 text-primary border-primary/30",
};

const LEAVE_STATUS_COLORS: Record<string, string> = {
  pending:  "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  approved: "bg-green-500/20 text-green-400 border-green-500/30",
  rejected: "bg-red-500/20 text-red-400 border-red-500/30",
  cancelled:"bg-slate-500/20 text-slate-400 border-slate-500/30",
};

const PAY_STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  paid:    "bg-green-500/20 text-green-400 border-green-500/30",
  reversed:"bg-red-500/20 text-red-400 border-red-500/30",
};

const emptyShift = {
  staff_id: "", staff_name: "", department: "", role: "",
  shift_type: "morning", shift_date: "", start_time: "", end_time: "", notes: "",
};

const emptyLeave = {
  staff_id: "", staff_name: "", department: "", leave_type: "annual",
  start_date: "", end_date: "", reason: "", handover_to: "",
};

const emptyPayroll = {
  staff_id: "", staff_name: "", department: "",
  pay_period_start: "", pay_period_end: "",
  basic_salary: "", allowances: "0", overtime_pay: "0",
  deductions: "0", tax: "0", pension: "0",
  payment_method: "bank_transfer", notes: "",
};

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

  const [approveId, setApproveId] = useState<number | null>(null);
  const [approveAction, setApproveAction] = useState<"approved" | "rejected">("approved");
  const [approveNotes, setApproveNotes] = useState("");
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
    queryFn: () => api.hr.listPayroll({ payment_status: filterPayStatus !== "all" ? filterPayStatus : undefined }),
  });

  const hrStats   = statsData?.shifts_today || { total: 0, on_duty: 0, by_type: {} };
  const leaveKpi  = statsData?.leave         || { pending: 0, approved: 0 };
  const payKpi    = statsData?.payroll        || { pending_amount: 0 };
  const shifts    = shiftsData?.shifts   || [];
  const leaves    = leaveData?.requests  || [];
  const payrolls  = payrollData?.records || [];

  // Mutations
  const shiftMut = useMutation({
    mutationFn: () => api.hr.createShift(shiftForm),
    onSuccess: () => {
      toast({ title: "Shift scheduled" });
      setShiftOpen(false);
      setShiftForm({ ...emptyShift });
      qc.invalidateQueries({ queryKey: ["hr-shifts"] });
      qc.invalidateQueries({ queryKey: ["hr-stats"] });
    },
    onError: () => toast({ title: "Failed to schedule shift", variant: "destructive" }),
  });

  const deleteShiftMut = useMutation({
    mutationFn: (id: number) => api.hr.deleteShift(id),
    onSuccess: () => { toast({ title: "Shift cancelled" }); refetchShifts(); },
  });

  const leaveMut = useMutation({
    mutationFn: () => api.hr.submitLeave(leaveForm),
    onSuccess: () => {
      toast({ title: "Leave request submitted" });
      setLeaveOpen(false);
      setLeaveForm({ ...emptyLeave });
      qc.invalidateQueries({ queryKey: ["hr-leave"] });
      qc.invalidateQueries({ queryKey: ["hr-stats"] });
    },
    onError: () => toast({ title: "Failed to submit leave", variant: "destructive" }),
  });

  const leaveActionMut = useMutation({
    mutationFn: ({ id, status, notes }: { id: number; status: string; notes: string }) =>
      api.hr.updateLeaveStatus(id, { status, notes: notes || undefined }),
    onSuccess: (_, v) => {
      toast({ title: `Leave ${v.status}` });
      setApproveOpen(false);
      setApproveNotes("");
      qc.invalidateQueries({ queryKey: ["hr-leave"] });
      qc.invalidateQueries({ queryKey: ["hr-stats"] });
    },
    onError: (e: any) => toast({ title: e?.message || "Action failed", variant: "destructive" }),
  });

  const payrollMut = useMutation({
    mutationFn: () => api.hr.createPayroll({
      ...payrollForm,
      basic_salary:  Number(payrollForm.basic_salary),
      allowances:    Number(payrollForm.allowances),
      overtime_pay:  Number(payrollForm.overtime_pay),
      deductions:    Number(payrollForm.deductions),
      tax:           Number(payrollForm.tax),
      pension:       Number(payrollForm.pension),
    }),
    onSuccess: () => {
      toast({ title: "Payroll record created" });
      setPayrollOpen(false);
      setPayrollForm({ ...emptyPayroll });
      qc.invalidateQueries({ queryKey: ["hr-payroll"] });
      qc.invalidateQueries({ queryKey: ["hr-stats"] });
    },
    onError: () => toast({ title: "Failed to create payroll record", variant: "destructive" }),
  });

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
          <Button size="sm" variant="outline" className="border-yellow-500/40 text-yellow-400 hover:bg-yellow-500/10"
            onClick={() => setLeaveOpen(true)}>
            <CalendarDays className="w-4 h-4 mr-1" /> Leave Request
          </Button>
          <Button size="sm" variant="outline" className="border-green-500/40 text-green-400 hover:bg-green-500/10"
            onClick={() => setPayrollOpen(true)}>
            <Banknote className="w-4 h-4 mr-1" /> Add Payroll
          </Button>
          <Button size="sm" className="bg-blue-700 hover:bg-blue-800"
            onClick={() => setShiftOpen(true)}>
            <Plus className="w-4 h-4 mr-1" /> Add Shift
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "On Duty Today",   value: hrStats.on_duty,                   color: "text-blue-700",    bg: "bg-blue-50" },
          { label: "Total Shifts",    value: hrStats.total,                      color: "text-foreground",  bg: "bg-muted/30" },
          { label: "Pending Leave",   value: leaveKpi.pending,                  color: leaveKpi.pending > 0 ? "text-yellow-700" : "text-muted-foreground", bg: leaveKpi.pending > 0 ? "bg-yellow-50" : "bg-muted/30" },
          { label: "Pending Payroll", value: `₦${payKpi.pending_amount.toLocaleString()}`, color: "text-green-400", bg: "bg-green-500/10" },
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
                  {["Date","Staff","Department","Role","Type","Time","Status","Action"].map(h => (
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
                        <TableCell className="text-xs text-muted-foreground capitalize">{s.role || "—"}</TableCell>
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
                              onClick={() => deleteShiftMut.mutate(s.id)}>
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
            {["all","pending","paid","reversed"].map(s => (
              <button key={s} onClick={() => setFilterPayStatus(s)}
                className={cn("px-3 py-1 rounded-full text-xs border transition-colors",
                  filterPayStatus === s ? "bg-green-700 border-green-600 text-foreground" : "border-border text-muted-foreground hover:border-primary/50")}>
                {s === "all" ? "All" : s}
              </button>
            ))}
          </div>
          <Card className="border-border bg-muted/30">
            <Table>
              <TableHeader>
                <TableRow className="border-border">
                  {["Staff","Department","Period","Basic","Allowances","Deductions","Net Pay","Status"].map(h => (
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
                        <TableCell className="text-xs text-muted-foreground">{p.pay_period_start} – {p.pay_period_end}</TableCell>
                        <TableCell className="text-sm">₦{Number(p.basic_salary).toLocaleString()}</TableCell>
                        <TableCell className="text-sm text-green-400">+₦{Number(p.allowances || 0).toLocaleString()}</TableCell>
                        <TableCell className="text-sm text-red-400">-₦{(Number(p.deductions || 0) + Number(p.tax || 0) + Number(p.pension || 0)).toLocaleString()}</TableCell>
                        <TableCell className="text-sm font-bold text-foreground">₦{Number(p.net_pay || 0).toLocaleString()}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cn("text-xs capitalize", PAY_STATUS_COLORS[p.payment_status] || "")}>
                            {p.payment_status}
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
      <Dialog open={shiftOpen} onOpenChange={setShiftOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-lg">
          <DialogHeader>
            <DialogTitle>Schedule Shift</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            {[
              { key: "staff_id",   label: "Staff ID *" },
              { key: "staff_name", label: "Staff Name" },
              { key: "department", label: "Department" },
              { key: "role",       label: "Role" },
              { key: "shift_date", label: "Date *",       type: "date" },
              { key: "start_time", label: "Start Time",   type: "time" },
              { key: "end_time",   label: "End Time",     type: "time" },
            ].map(f => (
              <div key={f.key} className="space-y-1">
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Input type={f.type || "text"} value={(shiftForm as any)[f.key] || ""}
                  onChange={e => setShiftForm(p => ({ ...p, [f.key]: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-8" />
              </div>
            ))}
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Shift Type</Label>
              <Select value={shiftForm.shift_type} onValueChange={v => setShiftForm(p => ({ ...p, shift_type: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {["morning","afternoon","night","on_call","split"].map(t =>
                    <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>)}
                </SelectContent>
              </Select>
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
              disabled={shiftMut.isPending || !shiftForm.staff_id || !shiftForm.shift_date}
              onClick={() => shiftMut.mutate()}>
              {shiftMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Schedule
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Leave Request Dialog ──────────────────────────────────────────── */}
      <Dialog open={leaveOpen} onOpenChange={setLeaveOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-lg">
          <DialogHeader>
            <DialogTitle>Submit Leave Request</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            {[
              { key: "staff_id",   label: "Staff ID *" },
              { key: "staff_name", label: "Staff Name" },
              { key: "department", label: "Department" },
              { key: "handover_to",label: "Handover To (staff ID)" },
              { key: "start_date", label: "Start Date *", type: "date" },
              { key: "end_date",   label: "End Date *",   type: "date" },
            ].map(f => (
              <div key={f.key} className="space-y-1">
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Input type={f.type || "text"} value={(leaveForm as any)[f.key] || ""}
                  onChange={e => setLeaveForm(p => ({ ...p, [f.key]: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-8" />
              </div>
            ))}
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Leave Type</Label>
              <Select value={leaveForm.leave_type} onValueChange={v => setLeaveForm(p => ({ ...p, leave_type: v }))}>
                <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-popover border-border">
                  {["annual","sick","maternity","paternity","compassionate","study","unpaid"].map(t =>
                    <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>)}
                </SelectContent>
              </Select>
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
            <DialogTitle className={cn(approveAction === "approved" ? "text-green-400" : "text-red-400")}>
              {approveAction === "approved" ? "Approve" : "Reject"} Leave #{approveId}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-2 mt-2">
            <Label className="text-xs text-muted-foreground">Notes (optional)</Label>
            <Textarea value={approveNotes}
              onChange={e => setApproveNotes(e.target.value)}
              className="bg-background border-border text-foreground text-sm h-16 resize-none" />
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setApproveOpen(false)}>Cancel</Button>
            <Button className={approveAction === "approved" ? "bg-green-700 hover:bg-green-600" : "bg-red-700 hover:bg-red-600"}
              disabled={leaveActionMut.isPending}
              onClick={() => leaveActionMut.mutate({ id: approveId!, status: approveAction, notes: approveNotes })}>
              {leaveActionMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Confirm {approveAction === "approved" ? "Approval" : "Rejection"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Add Payroll Dialog ────────────────────────────────────────────── */}
      <Dialog open={payrollOpen} onOpenChange={setPayrollOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Create Payroll Record</DialogTitle>
            <DialogDescription className="text-muted-foreground">Net pay is auto-calculated</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            {[
              { key: "staff_id",         label: "Staff ID *" },
              { key: "staff_name",       label: "Staff Name" },
              { key: "department",       label: "Department" },
              { key: "pay_period_start", label: "Period Start *", type: "date" },
              { key: "pay_period_end",   label: "Period End *",   type: "date" },
              { key: "basic_salary",     label: "Basic Salary *", type: "number" },
              { key: "allowances",       label: "Allowances",     type: "number" },
              { key: "overtime_pay",     label: "Overtime",       type: "number" },
              { key: "deductions",       label: "Deductions",     type: "number" },
              { key: "tax",              label: "Tax (PAYE)",     type: "number" },
              { key: "pension",          label: "Pension",        type: "number" },
            ].map(f => (
              <div key={f.key} className="space-y-1">
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Input type={f.type || "text"} value={(payrollForm as any)[f.key] || ""}
                  onChange={e => setPayrollForm(p => ({ ...p, [f.key]: e.target.value }))}
                  className="bg-background border-border text-foreground text-sm h-8" />
              </div>
            ))}
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
            <div className="col-span-2 space-y-1">
              <Label className="text-xs text-muted-foreground">Notes</Label>
              <Textarea value={payrollForm.notes}
                onChange={e => setPayrollForm(p => ({ ...p, notes: e.target.value }))}
                className="bg-background border-border text-foreground text-sm h-14 resize-none" />
            </div>
            {payrollForm.basic_salary && (
              <div className="col-span-2 p-3 rounded-lg bg-green-500/10 border border-green-500/20">
                <p className="text-xs text-muted-foreground">Estimated Net Pay</p>
                <p className="text-xl font-bold text-green-400">
                  ₦{Math.max(0,
                    Number(payrollForm.basic_salary) + Number(payrollForm.allowances || 0) + Number(payrollForm.overtime_pay || 0)
                    - Number(payrollForm.deductions || 0) - Number(payrollForm.tax || 0) - Number(payrollForm.pension || 0)
                  ).toLocaleString()}
                </p>
              </div>
            )}
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setPayrollOpen(false)}>Cancel</Button>
            <Button className="bg-green-700 hover:bg-green-600"
              disabled={payrollMut.isPending || !payrollForm.staff_id || !payrollForm.basic_salary}
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
