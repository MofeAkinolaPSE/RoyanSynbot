export const SHIFT_COLORS: Record<string, string> = {
  morning:   "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
  afternoon: "bg-orange-500/20 text-orange-700 dark:text-orange-400 border-orange-500/30",
  night:     "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  on_call:   "bg-sky-500/20 text-sky-700 dark:text-sky-400 border-sky-500/30",
};

export const LEAVE_STATUS_COLORS: Record<string, string> = {
  pending:   "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
  approved:  "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
  rejected:  "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30",
  cancelled: "bg-slate-500/20 text-slate-700 dark:text-slate-400 border-slate-500/30",
};

export const PAY_STATUS_COLORS: Record<string, string> = {
  draft:    "bg-slate-500/20 text-slate-700 dark:text-slate-400 border-slate-500/30",
  approved: "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
  paid:     "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
};

// Matches backend SHIFT_TYPE_ALLOWED / LEAVE_TYPE_ALLOWED / PAYROLL_STATUS_ALLOWED
// (src/constants.py) and the live DB CHECK constraints exactly — the previous
// frontend vocab ("split", "compassionate", "study", "pending"/"paid"/"reversed"
// for payroll) didn't match either and 422'd or 500'd on submission.
export const SHIFT_TYPES = ["morning", "afternoon", "night", "on_call"] as const;
export const LEAVE_TYPES = ["annual", "sick", "maternity", "paternity", "emergency", "unpaid"] as const;
export const PAYROLL_STATUSES = ["draft", "approved", "paid"] as const;

export const emptyShift = {
  staff_id: "", department: "",
  shift_type: "morning" as typeof SHIFT_TYPES[number],
  shift_date: "", start_time: "", end_time: "", notes: "",
};

export const emptyLeave = {
  staff_id: "", leave_type: "annual" as typeof LEAVE_TYPES[number],
  start_date: "", end_date: "", reason: "",
};

export const emptyPayroll = {
  staff_id: "",
  period_month: String(new Date().getMonth() + 1),
  period_year: String(new Date().getFullYear()),
  gross_salary: "", overtime_hours: "0", overtime_rate: "0",
  allowances: "0", deductions: "0", tax: "0", pension: "0",
  status: "draft" as typeof PAYROLL_STATUSES[number],
  payment_method: "bank_transfer", notes: "",
};
