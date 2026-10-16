import {
  InventoryDashboardData,
  WorkforceDashboardData,
  ExecutiveBriefing,
  Alert,
  StaffMember,
  OpsKpis,
  OpsForecast,
  ExecutiveSummaryResponse,
  ArTrendsResponse,
  HrSummaryResponse,
  RiskSignalsResponse,
  RecommendationsResponse,
  AnomaliesResponse,
  ProcurementAnalysis,
  ProcurementShipment,
  SupplierScorecardRow,
} from "@shared/dashboard-types";
import { authClient } from "@/lib/auth-client";
import { apiUrl } from "@/lib/api-base";

/** A doctor-authored note template: each phrase belongs to one SOAP section. */
export type NoteTemplateWrite = {
  name: string;
  category?: string | null;
  is_shared: boolean;
  phrases: { context_type: string; text: string }[];
};

export type ApiErrorKind ="session" | "permission" | "validation" | "not_found" | "transport" | "server" | "unknown";

export class ApiError extends Error {
  status: number;
  code?: string;
  kind: ApiErrorKind;
  detail?: unknown;

  constructor(message: string, status: number, kind: ApiErrorKind, code?: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.kind = kind;
    this.code = code;
    this.detail = detail;
  }
}

function classifyApiErrorKind(status: number): ApiErrorKind {
  if (status === 401) return "session";
  if (status === 403) return "permission";
  if (status === 404) return "not_found";
  if (status === 400 || status === 422) return "validation";
  if (status >= 500) return "server";
  if (status === 0) return "transport";
  return "unknown";
}

async function toApiError(res: Response, fallbackMessage: string): Promise<ApiError> {
  let detail: any = null;
  try {
    detail = await res.json();
  } catch {
    detail = null;
  }

  const detailPayload = detail?.detail ?? detail?.error ?? detail;

  // FastAPI's own request-validation errors (missing/invalid field, before the
  // route handler even runs) shape `detail` as an ARRAY of {loc, msg, type}
  // objects, not a string — the single-string case below never matches it,
  // so this was silently falling through to the generic fallback message
  // and hiding the actual reason (e.g. "Discharge Summary is required")
  // from the user entirely.
  let message: string | undefined;
  if (typeof detailPayload === "string") {
    message = detailPayload;
  } else if (Array.isArray(detailPayload)) {
    message = detailPayload
      .map((e: any) => {
        const field = Array.isArray(e?.loc) ? e.loc[e.loc.length - 1] : undefined;
        return field && e?.msg ? `${field}: ${e.msg}` : e?.msg;
      })
      .filter(Boolean)
      .join("; ");
  } else if (detailPayload?.message) {
    message = detailPayload.message;
  }
  message = message || res.statusText || fallbackMessage;

  const code = typeof detailPayload === "object" && !Array.isArray(detailPayload) ? detailPayload?.code : undefined;

  return new ApiError(message, res.status, classifyApiErrorKind(res.status), code, detailPayload);
}

function redirectToLoginIfNeeded() {
  if (typeof window === "undefined") return;
  if (window.location.hash !== "#/login") {
    window.location.hash = "#/login";
  }
}

async function getBearerToken(): Promise<string> {
  let token = authClient.getAccessToken();
  if (!token) {
    const refreshed = await authClient.refresh();
    if (!refreshed) {
      const reason = authClient.getLastAuthError();
      throw new ApiError(
        reason ? `No active session (${reason})` : "No active session",
        401,
        "session",
      );
    }
    token = authClient.getAccessToken();
  }
  if (!token) {
    const reason = authClient.getLastAuthError();
    throw new ApiError(
      reason ? `Session expired (${reason})` : "Session expired",
      401,
      "session",
    );
  }
  return token;
}

async function fetchJson<T>(endpoint: string): Promise<T> {
  let token = await getBearerToken();
  let res = await fetch(apiUrl(endpoint), {
    cache: "no-store",
    headers: {
      "Authorization": `Bearer ${token}`
    }
  });

  if (res.status === 401) {
    const refreshed = await authClient.refresh();
    if (!refreshed) {
      redirectToLoginIfNeeded();
      throw new ApiError("Session expired", 401, "session");
    }
    token = await getBearerToken();
    res = await fetch(apiUrl(endpoint), { cache: "no-store", headers: { "Authorization": `Bearer ${token}` } });
  }

  if (!res.ok) {
    const apiError = await toApiError(res, `Request failed for ${endpoint}`);
    console.error(`API Error ${endpoint}:`, apiError.message);
    throw apiError;
  }
  return res.json().then(d => d.data ?? d);
}

async function fetchRaw<T = any>(endpoint: string): Promise<T> {
  let token = await getBearerToken();
  let res = await fetch(apiUrl(endpoint), { cache: "no-store", headers: { "Authorization": `Bearer ${token}` } });

  if (res.status === 401) {
    const refreshed = await authClient.refresh();
    if (!refreshed) {
      redirectToLoginIfNeeded();
      throw new ApiError("Session expired", 401, "session");
    }
    token = await getBearerToken();
    res = await fetch(apiUrl(endpoint), { cache: "no-store", headers: { "Authorization": `Bearer ${token}` } });
  }

  if (!res.ok) {
    const apiError = await toApiError(res, `Request failed for ${endpoint}`);
    console.error(`API Error ${endpoint}:`, apiError.message);
    throw apiError;
  }
  return res.json();
}

async function sendJson<T>(
  endpoint: string,
  // DELETE was omitted from this union even though seven call sites use it
  // (soft-deletes for problems, allergies, care plans, templates…). The calls
  // worked — the method string is passed straight through to fetch — but the
  // mismatch surfaced only once tsc was re-enabled.
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  body: Record<string, any>,
): Promise<T> {
  let token = await getBearerToken();
  let res = await fetch(apiUrl(endpoint), {
    method,
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (res.status === 401) {
    const refreshed = await authClient.refresh();
    if (!refreshed) {
      redirectToLoginIfNeeded();
      throw new ApiError("Session expired", 401, "session");
    }
    token = await getBearerToken();
    res = await fetch(apiUrl(endpoint), {
      method,
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
  }

  if (!res.ok) {
    const apiError = await toApiError(res, `Request failed for ${method} ${endpoint}`);
    console.error(`API Error ${method} ${endpoint}:`, apiError.message);
    throw apiError;
  }

  return res.json();
}

/** Like sendJson, but for endpoints that stream a file (e.g. .docx) instead of
 * JSON — returns the raw blob plus the filename from Content-Disposition. */
async function sendJsonForDownload(
  endpoint: string,
  method: "POST" | "PUT" | "PATCH",
  body: Record<string, any>,
): Promise<{ blob: Blob; filename: string }> {
  let token = await getBearerToken();
  const doFetch = () => fetch(apiUrl(endpoint), {
    method,
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  let res = await doFetch();

  if (res.status === 401) {
    const refreshed = await authClient.refresh();
    if (!refreshed) {
      redirectToLoginIfNeeded();
      throw new ApiError("Session expired", 401, "session");
    }
    token = await getBearerToken();
    res = await doFetch();
  }

  if (!res.ok) {
    const apiError = await toApiError(res, `Request failed for ${method} ${endpoint}`);
    console.error(`API Error ${method} ${endpoint}:`, apiError.message);
    throw apiError;
  }

  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : "download";
  const blob = await res.blob();
  return { blob, filename };
}

/** GET a file (e.g. a .docx) with the session token and save it in the browser. */
async function downloadGet(endpoint: string): Promise<void> {
  let token = await getBearerToken();
  const doFetch = () => fetch(apiUrl(endpoint), { headers: { Authorization: `Bearer ${token}` } });
  let res = await doFetch();
  if (res.status === 401) {
    const refreshed = await authClient.refresh();
    if (!refreshed) {
      redirectToLoginIfNeeded();
      throw new ApiError("Session expired", 401, "session");
    }
    token = await getBearerToken();
    res = await doFetch();
  }
  if (!res.ok) throw await toApiError(res, `Download failed for ${endpoint}`);
  const match = (res.headers.get("Content-Disposition") || "").match(/filename="?([^"]+)"?/);
  triggerBlobDownload(await res.blob(), match ? match[1] : "download");
}

function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function fetchPublicJson<T>(endpoint: string): Promise<T> {
  const res = await fetch(apiUrl(endpoint), { cache: "no-store" });
  if (!res.ok) {
    const apiError = await toApiError(res, `Request failed for ${endpoint}`);
    console.error(`API Error ${endpoint}:`, apiError.message);
    throw apiError;
  }
  return res.json().then(d => d.data ?? d);
}

async function sendPublicJson<T>(
  endpoint: string,
  method: "POST" | "PUT" | "PATCH",
  body: Record<string, any>,
): Promise<T> {
  const res = await fetch(apiUrl(endpoint), {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const apiError = await toApiError(res, `Request failed for ${method} ${endpoint}`);
    console.error(`API Error ${method} ${endpoint}:`, apiError.message);
    throw apiError;
  }
  return res.json();
}

async function sendFormData<T>(
  endpoint: string,
  method: "POST" | "PUT" | "PATCH",
  body: FormData,
): Promise<T> {
  let token = await getBearerToken();
  let res = await fetch(apiUrl(endpoint), {
    method,
    headers: {
      "Authorization": `Bearer ${token}`,
    },
    body,
  });

  if (res.status === 401) {
    const refreshed = await authClient.refresh();
    if (!refreshed) {
      redirectToLoginIfNeeded();
      throw new ApiError("Session expired", 401, "session");
    }
    token = await getBearerToken();
    res = await fetch(apiUrl(endpoint), {
      method,
      headers: {
        "Authorization": `Bearer ${token}`,
      },
      body,
    });
  }

  if (!res.ok) {
    const apiError = await toApiError(res, `Request failed for ${method} ${endpoint}`);
    console.error(`API Error ${method} ${endpoint}:`, apiError.message);
    throw apiError;
  }

  return res.json();
}

async function sendDelete<T>(endpoint: string): Promise<T> {
  let token = await getBearerToken();
  let res = await fetch(apiUrl(endpoint), {
    method: "DELETE",
    headers: {
      "Authorization": `Bearer ${token}`,
    },
  });

  if (res.status === 401) {
    const refreshed = await authClient.refresh();
    if (!refreshed) {
      redirectToLoginIfNeeded();
      throw new ApiError("Session expired", 401, "session");
    }
    token = await getBearerToken();
    res = await fetch(apiUrl(endpoint), {
      method: "DELETE",
      headers: {
        "Authorization": `Bearer ${token}`,
      },
    });
  }

  if (!res.ok) {
    const apiError = await toApiError(res, `Request failed for DELETE ${endpoint}`);
    console.error(`API Error DELETE ${endpoint}:`, apiError.message);
    throw apiError;
  }

  return res.json();
}

export const api = {
  dashboard: {
    inventory: () => fetchJson<InventoryDashboardData>("/dashboard/inventory"),
    workforce: () => fetchJson<WorkforceDashboardData>("/dashboard/workforce"),
    crm: () => fetchJson<any>("/dashboard/crm"),
    alerts: () => fetchJson<Alert[]>("/dashboard/alerts"),
    briefing: () => fetchJson<ExecutiveBriefing>("/dashboard/executive-briefing"),
    finance: () => fetchJson<any>("/dashboard/finance"),
    hospitalStatus: () => fetchJson<any>("/dashboard/hospital-status"),
    /** Executive overview, composed from each module's hub service (services/executive.py). */
    executive: (refresh = false) => fetchRaw<any>(`/dashboard/executive${refresh ? "?refresh=true" : ""}`),
  },
  mdm: {
    departments: () =>
      fetchJson<{ entity_type: string; records: Array<{ id: number; code: string; name: string; short_name?: string }>; count: number }>(
        "/api/v1/mdm/department",
      ),
  },
  roles: {
    list: () => fetchPublicJson<{ roles: string[] }>("/roles"),
  },
  realtime: {
    // Exchanges the caller's JWT (sent properly, in a header) for a
    // short-lived, single-use ticket so the raw access token never has to
    // travel in a WebSocket URL (and therefore never lands in proxy logs).
    getWsTicket: () => sendJson<{ ticket: string; expires_in: number }>("/realtime/ws-ticket", "POST", {}),
  },
  presence: {
    summary: () => fetchRaw<{ count: number; staff: any[] }>("/realtime/presence/summary"),
  },
  capability: {
    proposals: (limit = 50) =>
      fetchJson<{ proposals: any[]; count: number }>(`/capability/proposals?limit=${limit}`),
    signals: (limit = 100) =>
      fetchJson<{ signals: any[]; count: number }>(`/capability/signals?limit=${limit}`),
    discover: () =>
      sendJson<{ signals_ingested: number; proposals_created: number; proposals: string[] }>("/capability/discover", "POST", {}),
    updateProposalStatus: (id: string, payload: { status: string; notes?: string }) =>
      sendJson<{ updated: boolean; proposal_id: string; old_status: string; new_status: string }>(`/capability/proposals/${id}/status`, "PATCH", payload),
  },
  publicDepartments: {
    list: () => fetchPublicJson<{ records: Array<{ id: number; code: string; name: string; short_name?: string }> }>("/departments"),
  },
  registrations: {
    submit: (payload: {
      email: string;
      password: string;
      full_name: string;
      role: string;
      department: string;
      designation?: string;
      phone?: string;
      kyc_details?: Record<string, string>;
    }) => sendPublicJson<{ status: string; registration_id: string }>("/register", "POST", payload),
    // fetchRaw, not fetchJson — fetchJson unwraps `{data: [...]}` down to the
    // bare array, and AdminRegistrations.tsx reads `.data` off the *result*
    // (expecting the wrapper), so fetchJson here silently made the pending
    // list always resolve to []. See the same landmine fixed in staff.getMe().
    list: (status: string = "pending") => fetchRaw<{ data: any[] }>(`/staff/registrations?status=${status}`),
    detail: (id: string) => fetchRaw<{ data: any }>(`/staff/registrations/${encodeURIComponent(id)}`),
    /** HR records this person may already have (same email / same name), so approval links rather than duplicates. */
    hrMatches: (id: string) => fetchRaw<{ data: any[] }>(`/staff/registrations/${encodeURIComponent(id)}/hr-matches`),
    approve: (id: string, payload: { department_id_override?: number; approval_reason: string; attestation_text: string; link_staff_id?: string; create_new?: boolean }) =>
      sendJson<{ status: string; mode: string; staff_id: string; user_id: string; filled: string[] }>(`/staff/registrations/${encodeURIComponent(id)}/approve`, "POST", payload),
    reject: (id: string, payload: { reason: string }) =>
      sendJson<{ status: string }>(`/staff/registrations/${encodeURIComponent(id)}/reject`, "POST", payload),
  },
  staff: {
    // fetchJson unwraps to `d.data ?? d` — wrong here, since this response
    // carries profile_complete as a SIBLING of `data`, not inside it. Whenever
    // a staff row already exists, fetchJson would silently discard
    // profile_complete and return just the raw profile row, making
    // `res.profile_complete` always undefined and re-triggering ProfileSetup
    // (and, downstream, the tour) on every reload. fetchRaw returns the
    // response body untouched.
    getMe: () => fetchRaw<{ data: any; profile_complete: boolean }>("/staff/me"),
    ensureProfile: (payload: Record<string, any>) =>
      sendJson<{ data: any; profile_complete: boolean }>("/staff/me/ensure-profile", "POST", payload),
    updateProfile: (payload: Record<string, any>) =>
      sendJson<{ data: any; profile_complete: boolean }>("/staff/me/profile", "PATCH", payload),
    updateTourState: (payload: Record<string, any>) =>
      sendJson<{ data: any }>("/staff/me/tour", "PATCH", payload),
    list: (dept?: string) => fetchJson<StaffMember[]>(`/staff${dept ? `?department=${dept}` : ""}`),
    snapshot: () => fetchJson<StaffMember[]>(`/staff/snapshot`),
    // Server-side shift state, so a shift survives a device change and can
    // legitimately span days.
    clockStatus: () => fetchRaw<any>('/staff/clock/status'),
    clockIn: (note?: string) => sendJson<any>('/staff/clock/in', 'POST', { note }),
    clockOut: (note?: string) => sendJson<any>('/staff/clock/out', 'POST', { note }),
    clockCancel: () => sendJson<any>('/staff/clock/cancel', 'POST', {}),
    timesheets: (department?: string, limit: number = 50) =>
      fetchJson<any[]>(`/timesheets${department ? `?department=${encodeURIComponent(department)}&limit=${limit}` : `?limit=${limit}`}`),
    submitTimesheet: (payload: {
      staff_id: string;
      date: string;
      hours_worked: number;
      department: string;
      activity_note?: string;
    }) => sendJson<{ success: boolean; data: any }>("/timesheets", "POST", payload),
    create: (payload: { full_name: string; email: string; department: string; role?: string }) =>
      sendJson<{ success: boolean; data: any }>("/staff", "POST", payload),
    dashboard: (userId: string) => fetchRaw<any>(`/staff/${encodeURIComponent(userId)}/dashboard`),
    createTask: (userId: string, payload: Record<string, any>) =>
      sendJson<any>(`/staff/${encodeURIComponent(userId)}/tasks`, "POST", payload),
    updateTask: (userId: string, taskId: string, payload: Record<string, any>) =>
      sendJson<any>(`/staff/${encodeURIComponent(userId)}/tasks/${encodeURIComponent(taskId)}`, "PUT", payload),
  },
  sage: {
    /** @deprecated use importJobs() */
    history: () => fetchJson<any[]>("/sage/history"),
    importJobs: (limit = 20) =>
      fetchJson<{ data: any[] }>(`/imports/jobs?limit=${limit}&domain=sage`),
    supportedTypes: () =>
      Promise.resolve({ file_types: ["customers", "ar", "ap", "gl", "inventory", "staff"] }),
  },
  audit: {
    logs: () => fetchJson<any[]>("/audit/logs"),
    // SDIL — Data intelligence / relationship integrity audit
    integrity: () => fetchRaw<any>('/audit/integrity'),
    run: () => sendJson<any>('/audit/run', 'POST', {}),
  },
  workflow: {
     pending: () => fetchJson<any[]>("/workflow/pending"),
     approve: (
      intentId: string,
      approved: boolean,
      approverNote?: string | null,
      approvalReason?: string | null,
      attestationText?: string | null,
    ) =>
      sendJson<any>("/workflow/approve", "POST", {
        intent_id: intentId,
        approved,
        approver_note: approverNote ?? null,
        approval_reason: approvalReason ?? null,
        attestation_text: attestationText ?? null,
      }),
  },
  users: {
    list: async (limit: number = 100) => {
      const payload = await fetchRaw<{ users?: any[] }>(`/users?limit=${limit}`);
      return Array.isArray(payload?.users) ? payload.users : [];
    },
    /** Lightweight user list for task/project assignment dropdowns.
     *  Accessible by admin, management, manager, hr, finance. */
    directory: () => fetchRaw<Array<{ id: string; email: string; display_name?: string; roles: string[] }>>("/users/directory"),
    /** The role catalogue (what each role opens) and the HR units, for User Access. */
    roles: () => fetchRaw<{ roles: Array<{ key: string; label: string; team: string; about: string }>; units: string[] }>("/users/roles"),
    create: (payload: {
      email: string;
      password: string;
      roles: string[];
      approval_reason: string;
      attestation_text: string;
      full_name?: string;
      unit?: string;
      job_title?: string;
    }) => sendJson<any>("/users", "POST", payload),
    resetPassword: (
      userId: string,
      payload: {
        password: string;
        approval_reason: string;
        attestation_text: string;
      },
    ) => sendJson<any>(`/users/${userId}/password`, "PUT", payload),
    setStatus: (
      userId: string,
      payload: {
        is_active: boolean;
        approval_reason: string;
        attestation_text: string;
      },
    ) => sendJson<any>(`/users/${userId}/status`, "PATCH", payload),
    setRoles: (userId: string, roles: string[], reason: string) =>
      sendJson<any>(`/users/${userId}/roles`, "PATCH", { roles, reason }),
  },
  imports: {
    sage: (payload: FormData, asyncMode: boolean = false) =>
      sendFormData<any>(`/sage/import${asyncMode ? "?async_mode=true" : ""}`, "POST", payload),
    /**
     * Upload a single Sage CSV file for one document type.
     * POST /sage/import/csv  { file_type, file }
     */
    importCsv: (fileType: string, file: File) => {
      const fd = new FormData();
      fd.append("file_type", fileType);
      fd.append("file", file);
      return sendFormData<{
        file_type: string;
        target_table: string;
        batch_id: string;
        rows_parsed: number;
        rows_inserted: number;
        validation_error_count: number;
        validation_errors: string[];
        status: string;
        imported_at: string;
      }>("/sage/import/csv", "POST", fd);
    },
    hr: (payload: FormData, asyncMode: boolean = false) =>
      sendFormData<any>(`/hr/import${asyncMode ? "?async_mode=true" : ""}`, "POST", payload),
    ops: (payload: FormData, asyncMode: boolean = false) =>
      sendFormData<any>(`/ops/import${asyncMode ? "?async_mode=true" : ""}`, "POST", payload),
    crm: (payload: FormData, asyncMode: boolean = false) =>
      sendFormData<any>(`/crm/import${asyncMode ? "?async_mode=true" : ""}`, "POST", payload),
  },
  finance: {
    gl: () => fetchJson<any[]>("/analytics/gl"),
    trend: () => fetchJson<any>("/analytics/trend"),
    transactions: () => fetchJson<any[]>("/analytics/transactions"),
    profitability: () => fetchJson<any>("/analytics/profitability"),
    arAging: () => fetchRaw<any>("/reports/ar_aging"),
    arAgingCustomers: (bucket: string) =>
      fetchRaw<any>(`/reports/ar_aging/customers?bucket=${encodeURIComponent(bucket)}`),

    // --- Tier-1 Finance Module (from 078 requirements) ---

    /** Unified AR aging: buckets + per-customer rows + triggered alerts */
    arAgingDetail: (bucket?: string) => {
      const q = bucket ? `?bucket=${encodeURIComponent(bucket)}` : "";
      return fetchRaw<any>(`/finance/ar/aging${q}`);
    },

    /** List active alert rules + unacknowledged events */
    listArAlerts: () => fetchRaw<any>("/finance/ar/alerts"),
    /** Create a new threshold alert rule */
    createArAlert: (payload: {
      threshold_amount: number;
      days_overdue_min?: number;
      customer_id?: string;
      description?: string;
      notify_emails?: string[];
    }) => sendJson<any>("/finance/ar/alerts", "POST", payload),
    /** Deactivate an alert rule */
    deleteArAlert: (ruleId: string) => sendDelete<any>(`/finance/ar/alerts/${encodeURIComponent(ruleId)}`),
    /** Acknowledge (dismiss) a triggered alert event */
    ackAlertEvent: (eventId: string) => sendJson<any>(`/finance/ar/alerts/${encodeURIComponent(eventId)}/ack`, "POST", {}),

    /** Invoice-to-payment matching */
    matchInvoices: (payload: { period?: string }) =>
      sendJson<any>("/finance/ar/match", "POST", payload),

    /** P&L from GL journal entries */
    pl: (period?: string) => {
      const q = period ? `?period=${encodeURIComponent(period)}` : "";
      return fetchRaw<any>(`/finance/reports/pl${q}`);
    },
    /** P&L as audit-stamped PDF — returns URL for direct browser download */
    plPdfUrl: (period?: string) => {
      const q = period ? `?period=${encodeURIComponent(period)}` : "";
      return `/finance/reports/pl/pdf${q}`;
    },

    /** Audit export log */
    exportLog: (limit = 50) => fetchRaw<any>(`/finance/exports/log?limit=${limit}`),

    /** Tier-2: 12-week rolling cash flow forecast */
    cashflowForecast: (weeks = 12) => fetchRaw<any>(`/finance/forecast/cashflow?weeks=${weeks}`),

    /** Tier-2: Payroll summary + period variance */
    payrollSummary: (period?: string) => {
      const q = period ? `?period=${encodeURIComponent(period)}` : "";
      return fetchRaw<any>(`/finance/payroll/summary${q}`);
    },

    /** Tier-2: Payroll PDF download URL (caller fetches with auth header) */
    payrollPdfUrl: (period?: string) => {
      const q = period ? `?period=${encodeURIComponent(period)}` : "";
      return `/finance/payroll/pdf${q}`;
    },

    // -----------------------------------------------------------------------
    // Tier 3 — Vendor Payment Approval Workflow
    // -----------------------------------------------------------------------

    /** List vendor payment requests. Optional status filter. */
    listVendorPayments: (status?: string, limit = 50, offset = 0) => {
      const p = new URLSearchParams({ limit: String(limit), offset: String(offset) });
      if (status) p.set("status", status);
      return fetchRaw<any>(`/finance/vendor/payments?${p}`);
    },

    /** Create a new vendor payment request. */
    createVendorPayment: (payload: {
      vendor_id: string;
      vendor_name?: string;
      amount: number;
      currency?: string;
      payment_date?: string;
      reference?: string;
      description?: string;
    }) => sendJson<any>("/finance/vendor/payments", "POST", payload),

    /** Approve a pending vendor payment. */
    approveVendorPayment: (id: string, note?: string) =>
      sendJson<any>(`/finance/vendor/payments/${id}/approve`, "PATCH", { note: note ?? null }),

    /** Reject a vendor payment. */
    rejectVendorPayment: (id: string, note?: string) =>
      sendJson<any>(`/finance/vendor/payments/${id}/reject`, "PATCH", { note: note ?? null }),

    /** Mark an approved vendor payment as paid. */
    markVendorPaymentPaid: (id: string) =>
      sendJson<any>(`/finance/vendor/payments/${id}/mark-paid`, "PATCH", {}),

    /** Cancel (soft-delete) a pending vendor payment. */
    cancelVendorPayment: (id: string) =>
      sendDelete<any>(`/finance/vendor/payments/${id}`),

    // -----------------------------------------------------------------------
    // Tier 3 — Credit Risk Scoring
    // -----------------------------------------------------------------------

    /** Get credit risk scores for all customers. */
    creditRiskScores: () => fetchRaw<any>("/finance/credit/risk"),

    // -----------------------------------------------------------------------
    // Tier 3 — Budget vs. Actual
    // -----------------------------------------------------------------------

    /** List budget targets, optional period/department filters. */
    listBudgetTargets: (period?: string, department?: string) => {
      const p = new URLSearchParams();
      if (period) p.set("period", period);
      if (department) p.set("department", department);
      return fetchRaw<any>(`/finance/budget/targets${p.toString() ? "?" + p : ""}`);
    },

    /** Upsert a budget target. */
    upsertBudgetTarget: (payload: {
      department: string;
      category?: string;
      period: string;
      budgeted_amount: number;
      note?: string;
    }) => sendJson<any>("/finance/budget/targets", "POST", payload),

    /** Delete a budget target by ID. */
    deleteBudgetTarget: (id: string) => sendDelete<any>(`/finance/budget/targets/${id}`),

    /** Get budget vs. actual variance for a period. */
    budgetVariance: (period?: string) => {
      const q = period ? `?period=${encodeURIComponent(period)}` : "";
      return fetchRaw<any>(`/finance/budget/variance${q}`);
    },

    /** Per-department revenue, broken down by payer type (HMO/Staff/Private). */
    departmentSummary: (params?: { date_from?: string; date_to?: string; department?: string }) => {
      const q = new URLSearchParams();
      if (params?.date_from) q.set("date_from", params.date_from);
      if (params?.date_to) q.set("date_to", params.date_to);
      if (params?.department) q.set("department", params.department);
      const s = q.toString();
      return fetchRaw<any>(`/finance/department-summary${s ? "?" + s : ""}`);
    },

    /** Patients segregated per HMO for a given month, with billing totals. */
    hmoMonthlySegregation: (month?: string) => {
      const q = month ? `?month=${encodeURIComponent(month)}` : "";
      return fetchRaw<any>(`/finance/hmo/monthly-segregation${q}`);
    },

    /** Full itemized billing detail for one encounter (HMO drill-down popup). */
    hmoEncounterDetail: (encounterId: number | string) =>
      fetchRaw<any>(`/finance/hmo/encounter-detail/${encounterId}`),
  },
  intelligence: {
    executiveSummary: () => fetchRaw<ExecutiveSummaryResponse>("/intelligence/executive_summary"),
    riskSignals: () => fetchRaw<RiskSignalsResponse>("/intelligence/risk_signals"),
    recommendations: () => fetchRaw<RecommendationsResponse>("/intelligence/recommendations"),
    anomalies: () => fetchRaw<AnomaliesResponse>("/intelligence/anomalies"),
  },
  analytics: {
    arTrends: (periods: number = 6) => fetchRaw<ArTrendsResponse>(`/analytics/ar_trends?periods=${periods}`),
  },
  crm: {
    riskScores: () => fetchRaw<any>("/crm/risk_scores"),
  },
  threads: {
    list: () => fetchRaw<any[]>("/threads"),
    listChannels: () => fetchRaw<any[]>("/threads/channels"),
    createChannel: (payload: {
      title: string;
      channel_key: string;
      member_ids?: string[];
      context_type?: string;
      context_id?: string;
    }) => sendJson<any>("/threads/channels", "POST", payload),
    listMessages: (threadId: string, limit: number = 100, offset: number = 0) =>
      fetchRaw<any[]>(`/threads/${encodeURIComponent(threadId)}/messages?limit=${limit}&offset=${offset}`),
    postMessage: (threadId: string, payload: { content: string; metadata?: Record<string, any> }) =>
      sendJson<any>(`/threads/${encodeURIComponent(threadId)}/messages`, "POST", payload),
    addMember: (threadId: string, payload: { user_id: string; role?: string }) =>
      sendJson<any>(`/threads/${encodeURIComponent(threadId)}/members`, "POST", payload),
    removeMember: (threadId: string, userId: string) =>
      sendDelete<any>(`/threads/${encodeURIComponent(threadId)}/members/${encodeURIComponent(userId)}`),
    setPresence: (threadId: string, status: "online" | "away" | "offline") =>
      sendJson<any>(`/threads/${encodeURIComponent(threadId)}/presence`, "POST", { status }),
    getPresence: (threadId: string) => fetchRaw<any[]>(`/threads/${encodeURIComponent(threadId)}/presence`),
    markRead: (threadId: string, last_read_message_id?: string) =>
      sendJson<any>(`/threads/${encodeURIComponent(threadId)}/read`, "POST", { last_read_message_id }),
    unreadSummary: () => fetchRaw<{ items: any[] }>("/threads/unread/summary"),
  },
  leadFinder: {
    sourceProspects: (payload: {
      industry?: string;
      region?: string;
      source?: string;
      limit?: number;
      seed_companies?: Array<Record<string, any>>;
    }) => sendJson<any>("/crm/lead-finder/prospects/source", "POST", payload),
    scoreIngestProspect: (
      prospectId: string,
      payload: {
        expected_value?: number;
        urgency?: "low" | "medium" | "high";
        fit_signals?: Record<string, any>;
        source?: string;
        assigned_rep?: string;
        stage?: string;
      },
    ) => sendJson<any>(`/crm/lead-finder/prospects/${encodeURIComponent(prospectId)}/score-ingest`, "POST", payload),
    assignLead: (payload: {
      lead_id: number;
      rep_user_id: string;
      follow_up_type?: string;
      follow_up_hours?: number;
      notes?: string;
    }) => sendJson<any>("/crm/lead-finder/assign", "POST", payload),
    pipeline: (limit: number = 100) => fetchRaw<any>(`/crm/lead-finder/pipeline?limit=${limit}`),

    /** Google Places-powered location search (mock fallback when no API key) */
    searchByLocation: (payload: {
      location: string;
      business_type?: string;
      radius_m?: number;
      limit?: number;
      industry?: string;
      region?: string;
    }) => sendJson<any>("/crm/lead-finder/search", "POST", payload),

    /** Download all prospects as CSV — returns a fetch Response (caller handles blob) */
    exportProspects: (limit: number = 1000) =>
      fetchRaw<any>(`/crm/lead-finder/export?limit=${limit}`),
  },
  events: {
    trace: (eventId: string) => fetchRaw<any>(`/events/${encodeURIComponent(eventId)}/trace`),
  },
  kg: {
    nodes: (params?: { node_type?: string; search?: string; limit?: number }) => {
      const q = new URLSearchParams();
      if (params?.node_type) q.set("node_type", params.node_type);
      if (params?.search) q.set("search", params.search);
      q.set("limit", String(params?.limit ?? 100));
      return fetchRaw<{ count: number; nodes: any[] }>(`/kg/nodes?${q.toString()}`);
    },
    subgraph: (nodeId: number, params?: { depth?: number; limit?: number }) => {
      const q = new URLSearchParams();
      if (params?.depth != null) q.set("depth", String(params.depth));
      if (params?.limit != null) q.set("limit", String(params.limit));
      const query = q.toString();
      return fetchRaw<any>(`/kg/subgraph/${nodeId}${query ? `?${query}` : ""}`);
    },
    reason: (payload: {
      source_node_id: number;
      target_node_id: number;
      max_depth?: number;
      edge_types?: string[];
      limit?: number;
    }) => sendJson<any>("/kg/reason", "POST", payload),
  },
  leads: {
    // Create a lead via existing backend `/submit_lead`
    create: (payload: Record<string, any>) => sendJson<any>("/submit_lead", "POST", payload),
    // Try to fetch a lead by id (backend route optional)
    get: (leadId: number) => fetchJson<any>(`/leads/${leadId}`),
    // Admin list (backend may expose `/admin/leads` in future)
    list: (limit: number = 100) => fetchJson<any[]>(`/admin/leads?limit=${limit}`),
  },
  orders: {
    // Submit order endpoint (uses `lead_id` when present)
    submit: (payload: Record<string, any>) => sendJson<any>("/submit_order", "POST", payload),
    // Recent orders list (backend route optional)
    recent: (limit: number = 50) => fetchJson<any[]>(`/orders?limit=${limit}`),
  },
  procurement: {
    shipments: (params?: { status?: string; supplier_name?: string; limit?: number }) => {
      const q = new URLSearchParams();
      if (params?.status) q.set("status", params.status);
      if (params?.supplier_name) q.set("supplier_name", params.supplier_name);
      q.set("limit", String(params?.limit ?? 100));
      return fetchRaw<{ data: ProcurementShipment[]; count: number }>(`/procurement/import-agent/shipments?${q.toString()}`);
    },
    analyze: (payload?: { threshold_days?: number; daily_cost?: number }) =>
      sendJson<{ data: ProcurementAnalysis }>("/procurement/import-agent/analyze", "POST", payload ?? {}),
    scorecard: () =>
      fetchRaw<{ data: SupplierScorecardRow[] }>("/procurement/import-agent/scorecard"),
    transition: (shipmentId: string, payload: { next_status: string; reason?: string }) =>
      sendJson<{ data: ProcurementShipment }>(`/procurement/import-agent/shipments/${shipmentId}/status`, "PATCH", payload),
    escalate: (
      shipmentId: string,
      payload?: { reason?: string; notify_regulatory?: boolean; notify_executive_dashboard?: boolean },
    ) =>
      sendJson<{ status: string; shipment_id: string; reason: string }>(
        `/procurement/import-agent/shipments/${shipmentId}/escalate`,
        "POST",
        payload ?? {},
      ),
  },
    ops: {
      kpis: () => fetchRaw<OpsKpis>("/ops/kpis"),
      forecastStockTurnover: (window: number = 3, horizon: number = 3) =>
        fetchRaw<OpsForecast>(`/ops/forecast/stock_turnover?window=${window}&horizon=${horizon}`),
    },
  inventory: {
    stock: async (skus?: string[]) => {
      // TODO: support skus param via POST body if needed
      const data = await fetchRaw("/stock");
      return data.stock as any[];
    },
    latestSnapshot: () => fetchJson<any[]>("/stock"),
    // simple search endpoint used by staff UI autocomplete
    search: (query: string) => fetchJson<any[]>(`/inventory?query=${encodeURIComponent(query)}`),
    recordMovement: (payload: {
      item_id: string;
      change: number;
      movement_type: string;
      source?: string;
      destination?: string;
      created_by?: string;
      metadata?: Record<string, any>;
    }) => sendJson<{ status: string; movement: any }>("/inventory/movements", "POST", payload),
  },
  projects: {
    readiness: () => fetchRaw<{ ready: boolean; reason?: string; checks?: Record<string, boolean> }>("/controls/readiness"),
    list: (limit: number = 50, status?: string) => {
      const q = new URLSearchParams({ limit: String(limit) });
      if (status) q.set("status", status);
      return fetchRaw<{ data: any[] }>(`/controls/projects?${q.toString()}`).then(r => r.data);
    },
    create: (payload: {
      name: string;
      description?: string;
      status?: string;
      activity_type?: string;
      supplier_name?: string;
      assigned_staff_id?: string;
      workflow_stage?: string;
      po_reference?: string;
      temperature_profile?: string;
      nafdac_sampling_status?: string;
      quality_check_status?: string;
      quality_notes?: string;
    }) =>
      sendJson<any>("/controls/projects", "POST", payload).then((r) => r?.data ?? r),
    transitionStage: (
      projectId: string,
      payload: {
        workflow_stage: string;
        reason_code?: string;
        nafdac_sampling_status?: string;
        quality_check_status?: string;
        quality_notes?: string;
      },
    ) =>
      sendJson<any>(`/controls/projects/${encodeURIComponent(projectId)}/stage`, "POST", payload)
        .then((r) => r?.data ?? r),
  },
  suppliers: {
    list: () => fetchRaw<any[]>("/suppliers"),
    create: (payload: Record<string, any>) => sendJson<any>("/suppliers", "POST", payload),
    metrics: (supplierName: string) =>
      fetchRaw<any>(`/suppliers/${encodeURIComponent(supplierName)}/metrics`),
  },
  calendar: {
    /** mine: only events I attend or created (My Schedule). */
    list: (month?: string, mine = false) => {
      const qs = new URLSearchParams();
      if (month) qs.set("month", month);
      if (mine) qs.set("mine", "true");
      return fetchRaw<{ events: any[] }>(`/calendar/events${qs.toString() ? `?${qs}` : ""}`);
    },
    create: (payload: {
      title: string;
      description?: string;
      event_type?: string;
      start_time: string;
      end_time?: string;
      location?: string;
      all_day?: boolean;
      metadata?: Record<string, any>;
    }) => sendJson<{ data: any }>("/calendar/events", "POST", payload),
    update: (eventId: string, payload: Record<string, any>) =>
      sendJson<{ data: any }>(`/calendar/events/${eventId}`, "PATCH", payload),
    delete: (eventId: string) =>
      sendDelete<{ status: string }>(`/calendar/events/${eventId}`),
    /** Pharma logistics: returns batches expiring within window_days (default 30). */
    logisticsAlerts: (windowDays = 30) =>
      fetchRaw<{
        alerts: Array<{
          event_id: string;
          title: string;
          event_type: string;
          batch_id?: string;
          product_name?: string;
          expiry_date: string;
          days_until_expiry: number;
          is_cold_chain: boolean;
          is_nafdac_regulated: boolean;
        }>;
        total: number;
        window_days: number;
      }>(`/calendar/logistics/alerts?window_days=${windowDays}`),
  },
  tasks: {
    /** mine: only tasks assigned to me or created by me (My Schedule). */
    list: (status?: string, mine = false) => {
      const qs = new URLSearchParams();
      if (status) qs.set("status", status);
      if (mine) qs.set("mine", "true");
      return fetchRaw<{ tasks: any[] }>(`/tasks${qs.toString() ? `?${qs}` : ""}`);
    },
    create: (payload: {
      title: string;
      description?: string;
      priority?: string;
      due_date?: string;
      assigned_to?: string;
    }) => sendJson<{ data: any }>("/tasks", "POST", payload),
    update: (taskId: string, payload: Record<string, any>) =>
      sendJson<{ data: any }>(`/tasks/${taskId}`, "PATCH", payload),
    delete: (taskId: string) =>
      sendDelete<{ status: string }>(`/tasks/${taskId}`),
  },
  agents: {
    list: () => fetchRaw<{ agents: any[]; count: number }>("/agents/list"),
    execute: (question: string, mode?: string) =>
      sendJson<{
        agents_executed: string[];
        merged: any;
        insights: any[];
        errors?: any[];
      }>("/agents/execute", "POST", { question, mode }),
    run: (agentName: string, context?: Record<string, any>) =>
      sendJson<{ agent: string; insight: any; success: boolean }>(
        `/agents/run/${agentName}`,
        "POST",
        context || {},
      ),
    cached: (agentName: string) =>
      fetchRaw<{ key: string; value: any }>(`/cache/get/${agentName}`),
    cacheTtl: (agentName: string) =>
      fetchRaw<{ key: string; ttl_seconds: number | null }>(`/cache/ttl/${agentName}`),
  },
  // ── Phase 12 — Facility Audits & Equipment Maintenance (hospital-native;
  // distinct from the pharma `compliance` namespace above) ─────────────────
  facility: {
    listAudits: (params?: { status?: string; department?: string }) => {
      const qs = new URLSearchParams();
      if (params?.status)     qs.set('status', params.status);
      if (params?.department) qs.set('department', params.department);
      return fetchRaw<any>('/facility/audits?' + qs);
    },
    createAudit: (payload: { audit_title: string; department: string; scheduled_date: string; risk_level?: string }) =>
      sendJson<any>('/facility/audits', 'POST', payload),
    getAudit: (id: string) => fetchRaw<any>('/facility/audits/' + id),
    startAudit: (id: string) => sendJson<any>(`/facility/audits/${id}/start`, 'PATCH', {}),
    completeAudit: (id: string, payload: { findings?: string; recommendations?: string; score?: number }) =>
      sendJson<any>(`/facility/audits/${id}/complete`, 'PATCH', payload),
    listMaintenance: (statusFilter?: 'all' | 'overdue' | 'upcoming') => {
      const qs = statusFilter && statusFilter !== 'all' ? '?status_filter=' + statusFilter : '';
      return fetchRaw<any>('/facility/maintenance' + qs);
    },
    createMaintenance: (payload: {
      equipment_name: string; equipment_type?: string; location?: string;
      maintenance_type?: string; description?: string; due_date: string;
    }) => sendJson<any>('/facility/maintenance', 'POST', payload),
    getMaintenance: (id: string) => fetchRaw<any>('/facility/maintenance/' + id),
    completeMaintenance: (id: string, payload: { completion_notes?: string; next_due_date?: string }) =>
      sendJson<any>(`/facility/maintenance/${id}/complete`, 'PATCH', payload),
    stats: () => fetchRaw<any>('/facility/stats'),
  },
  knowledge: {
    getDocuments: (docType?: string, department?: string, page = 1) => {
      const params = new URLSearchParams();
      if (docType) params.set("doc_type", docType);
      if (department) params.set("department", department);
      params.set("page", String(page));
      return fetchRaw<{ data: any[]; page: number; page_size: number }>(
        `/api/documents?${params.toString()}`
      );
    },
    getDocument: (id: string) => fetchRaw<any>(`/api/documents/${encodeURIComponent(id)}`),
    ingestFile: (formData: FormData) =>
      sendFormData<{ status: string; document_id: string; chunks: number; filename: string; message: string }>(
        "/knowledge/ingest",
        "POST",
        formData
      ),
    search: (q: string, department?: string, docType?: string) => {
      const params = new URLSearchParams({ q });
      if (department) params.set("department", department);
      if (docType) params.set("doc_type", docType);
      return fetchRaw<any>(`/knowledge/search?${params.toString()}`);
    },
    getGaps: (status?: string, page = 1) => {
      const params = new URLSearchParams({ page: String(page) });
      if (status) params.set("status", status);
      return fetchRaw<{ data: any[]; page: number }>(`/knowledge/gaps?${params.toString()}`);
    },
    resolveGap: (gapId: number) =>
      fetchRaw<any>(`/knowledge/gaps/${gapId}/resolve`),
  },
  salesCrm: {
    pipeline: (limit: number = 200) =>
      fetchRaw<any>(`/crm/sales/pipeline?limit=${limit}`),

    moveStage: (leadId: number, stage: string, notes?: string) =>
      sendJson<any>(`/crm/sales/leads/${leadId}/stage`, "PATCH", { stage, notes }),

    createFollowUp: (payload: {
      lead_id?: number;
      customer_id?: number;
      assigned_rep?: string;
      reminder_type?: string;
      due_at: string;
      note?: string;
    }) => sendJson<any>("/crm/sales/followups", "POST", payload),

    dueReminders: (hours: number = 24, repId?: string) => {
      const q = new URLSearchParams({ hours: String(hours) });
      if (repId) q.set("rep_id", repId);
      return fetchRaw<any>(`/crm/sales/followups/due?${q.toString()}`);
    },

    updateReminder: (reminderId: string, status: string, note?: string) =>
      sendJson<any>(`/crm/sales/followups/${encodeURIComponent(reminderId)}`, "PATCH", {
        status,
        note,
      }),

    queueBulkMessage: (payload: {
      channel: string;
      message_text: string;
      subject?: string;
      recipient_filter?: Record<string, any>;
    }) => sendJson<any>("/crm/sales/bulk-message", "POST", payload),

    listBulkMessages: (limit: number = 20) =>
      fetchRaw<any[]>(`/crm/sales/bulk-message?limit=${limit}`),

    weeklyReport: (weekStart?: string) => {
      const q = weekStart ? `?week_start=${weekStart}` : "";
      return fetchRaw<any>(`/crm/sales/weekly-report${q}`);
    },

    query: (query: string) =>
      sendJson<{ query: string; answer: string }>("/crm/sales/query", "POST", { query }),

    leaderboard: (days: number = 30) =>
      fetchRaw<any>(`/crm/sales/leaderboard?days=${days}`),

    dispatchBulkMessage: (jobId: string) =>
      sendJson<any>(`/crm/sales/bulk-message/${encodeURIComponent(jobId)}/dispatch`, "POST", {}),

    getLeadBrief: (leadId: number) =>
      fetchRaw<any>(`/crm/sales/leads/${leadId}/brief`),

    getProductAvailability: (leadId: number) =>
      fetchRaw<any>(`/crm/sales/leads/${leadId}/product-availability`),

    getPurchaseHistory: (leadId: number, limit = 20) =>
      fetchRaw<any>(`/crm/sales/leads/${leadId}/purchase-history?limit=${limit}`),

    weeklyReportPdfUrl: (weekStart?: string) => {
      const q = weekStart ? `?week_start=${weekStart}` : "";
      return apiUrl(`/crm/sales/weekly-report/pdf${q}`);
    },

    // Gap-fill: Lead CRUD
    createLead: (payload: {
      company_name: string;
      contact_person?: string;
      contact_phone?: string;
      product_interest?: string[];
      stage?: string;
      expected_value?: number;
      payment_terms?: string;
      notes?: string;
      next_action?: string;
      assigned_rep?: string;
    }) => sendJson<any>("/crm/sales/leads", "POST", payload),

    updateLead: (leadId: number, payload: Record<string, any>) =>
      sendJson<any>(`/crm/sales/leads/${leadId}`, "PATCH", payload),

    // Gap-fill: Interaction log
    logInteraction: (leadId: number, payload: {
      interaction_type: string;
      summary: string;
      outcome?: string;
      next_step?: string;
      occurred_at?: string;
    }) => sendJson<any>(`/crm/sales/leads/${leadId}/interactions`, "POST", payload),

    listInteractions: (leadId: number, limit = 50) =>
      fetchRaw<any>(`/crm/sales/leads/${leadId}/interactions?limit=${limit}`),

    // Gap-fill: Sales targets
    createTarget: (payload: {
      rep_id?: string;
      period: string;
      period_type: string;
      target_value: number;
      target_deals?: number;
    }) => sendJson<any>("/crm/sales/targets", "POST", payload),

    listTargets: (period?: string, repId?: string) => {
      const q = new URLSearchParams();
      if (period) q.set("period", period);
      if (repId) q.set("rep_id", repId);
      return fetchRaw<any>(`/crm/sales/targets${q.toString() ? `?${q.toString()}` : ""}`);
    },

    targetsVsActuals: (period: string) =>
      fetchRaw<any>(`/crm/sales/targets/vs-actuals?period=${encodeURIComponent(period)}`),
  },


  // -------------------------------------------------------------------------
  // Quality Control
  // -------------------------------------------------------------------------


  // ── Report Intelligence API ────────────────────────────────────────────────
  reports: {
    /** Run the ReportGenerationAgent for any report type. Returns full narrative. */
    generate: (payload: { report_type?: string; intent_text?: string }) =>
      sendJson<{
        report_type: string;
        section_title: string;
        full_report: string;
        findings: string[];
        recommendations: string[];
        quality_score: number;
        rag_hits: number;
        data_rows: number;
        status: string;
      }>("/reports/generate", "POST", payload),

    /** Run the agent and stream the result as a branded .docx, triggering a
     * browser download. `entity_id` scopes the report to one specific record
     * (only honored by report types that define id_column, e.g. facility_audit,
     * equipment_maintenance) instead of the usual aggregate-across-recent-rows
     * narrative. */
    generateDocx: async (payload: { report_type?: string; intent_text?: string; entity_id?: string }) => {
      const { blob, filename } = await sendJsonForDownload("/reports/generate/docx", "POST", payload);
      triggerBlobDownload(blob, filename);
    },

    /** List recently stored reports (optionally filtered by type). */
    history: (report_type?: string, limit = 10) => {
      const p = new URLSearchParams({ limit: String(limit) });
      if (report_type) p.set("report_type", report_type);
      return fetchRaw<{ reports: any[] }>(`/reports/history?${p}`);
    },

    /** Get full narrative of a single stored report by ID. */
    detail: (reportId: string) =>
      fetchRaw<any>(`/reports/history/${encodeURIComponent(reportId)}`),

    /** Download a stored report as .docx by ID — returns the fetch URL (caller adds auth). */
    detailDocxUrl: (reportId: string) =>
      `/reports/history/${encodeURIComponent(reportId)}/docx`,

    // Reports about one record (reportGUide.md s12): type -> record -> review -> report
    catalog: () => fetchRaw<{ types: any[]; kind_labels: Record<string, string> }>("/reports/catalog"),
    subjects: (kind: string, search = "") =>
      fetchRaw<{ items: any[] }>(`/reports/subjects/${encodeURIComponent(kind)}?search=${encodeURIComponent(search)}`),
    dossier: (report_type: string, kind: string, id: string) =>
      fetchRaw<any>(`/reports/dossier?${new URLSearchParams({ report_type, kind, id })}`),
    fromRecord: (payload: { report_type: string; kind: string; id: string; notes?: string }) =>
      sendJson<any>("/reports/from-record", "POST", payload),
    library: (kind?: string, subjectId?: string) => {
      const p = new URLSearchParams();
      if (kind) p.set("kind", kind);
      if (subjectId) p.set("subject_id", subjectId);
      return fetchRaw<{ reports: any[] }>(`/reports/library?${p}`);
    },
    record: (id: string) => fetchRaw<any>(`/reports/record/${encodeURIComponent(id)}`),
    approveRecord: (id: string) => sendJson<any>(`/reports/record/${encodeURIComponent(id)}/approve`, "POST", {}),
    downloadRecord: (id: string) => downloadGet(`/reports/record/${encodeURIComponent(id)}/docx`),
  },

  // Procurement & Stores (reportGUide.md s6)
  stores: {
    overview: () => fetchRaw<any>("/procurement/overview"),
    plan: (refresh = false) => fetchRaw<any>(`/procurement/reorder-plan${refresh ? "?refresh=true" : ""}`),
    orders: (status?: string) => fetchRaw<{ orders: any[] }>(`/procurement/orders${status ? `?status=${status}` : ""}`),
    raise: (p: { formulary_id: number; quantity: number; urgency?: string; notes?: string; supplier_id?: string }) =>
      sendJson<any>("/procurement/orders", "POST", p),
    approve: (id: number) => sendJson<any>(`/procurement/orders/${id}/approve`, "POST", {}),
    place: (id: number, p: { supplier_id: string; expected_date: string; quantity?: number }) =>
      sendJson<any>(`/procurement/orders/${id}/place`, "POST", p),
    cancel: (id: number, reason: string) => sendJson<any>(`/procurement/orders/${id}/cancel`, "POST", { reason }),
    suppliers: () => fetchRaw<any>("/procurement/suppliers"),
  },

  // Patient Relations - HMO & corporate accounts (reportGUide.md s7)
  relations: {
    overview: () => fetchRaw<any>("/relations/overview"),
    payers: () => fetchRaw<any>("/relations/payers"),
    payer: (id: number | string) => fetchRaw<any>(`/relations/payers/${id}`),
    logContact: (id: number | string, p: { kind: string; summary: string; follow_up_on?: string }) =>
      sendJson<any>(`/relations/payers/${id}/contacts`, "POST", p),
    done: (contactId: string) => sendJson<any>(`/relations/contacts/${contactId}/done`, "POST", {}),
  },

  // The calendar over the records (reportGUide.md s10)
  hospitalCalendar: {
    feed: (from: string, to: string, sources?: string[]) =>
      fetchRaw<any>(`/calendar/hospital?${new URLSearchParams({ from, to, ...(sources?.length ? { sources: sources.join(",") } : {}) })}`),
    reschedule: (source: string, id: string, date: string) =>
      sendJson<any>("/calendar/hospital/reschedule", "POST", { source, id, date }),
  },

  // -------------------------------------------------------------------------
  // HOSPITAL DOMAIN  (Phase 4+ routers)
  // -------------------------------------------------------------------------
  hospital: {
    patients: {
      register: (payload: Record<string, any>) =>
        sendJson<any>('/patients/register', 'POST', {
          ...payload,
          blood_group: payload.blood_group ?? payload.blood_type,
        }),
      search: (q: string) =>
        fetchRaw<any>('/patients/search?q=' + encodeURIComponent(q)),
      /** The patient list A-Z (first name, then surname), a page at a time. */
      listAz: (offset = 0, limit = 50) =>
        fetchRaw<any>(`/patients/search?sort=name&limit=${limit}&offset=${offset}`),
      // Billing, encounters and the ledger all hold the numeric id, not the MRN.
      getById: (id: number | string) => fetchRaw<any>('/patients/by-id/' + id),
      get: (mrn: string) =>
        fetchRaw<any>('/patients/' + encodeURIComponent(mrn)),
      profile: (mrn: string) =>
        fetchRaw<any>('/patients/' + encodeURIComponent(mrn) + '/profile'),
      relationshipTree: (mrn: string) =>
        fetchRaw<any>('/patients/' + encodeURIComponent(mrn) + '/relationship-tree'),
      update: (mrn: string, payload: Record<string, any>) => {
        const body = { ...payload };
        // Only fall back to the legacy blood_type name when blood_group is
        // truly absent — `??` alone would also catch an explicit
        // `blood_group: null` (a deliberate "clear this field" signal, see
        // patient_registration.py's exclude_unset handling) and silently
        // turn it into undefined, dropping the key from the request instead
        // of clearing it.
        if (body.blood_group === undefined && body.blood_type !== undefined) {
          body.blood_group = body.blood_type;
        }
        delete body.blood_type;
        return sendJson<any>('/patients/' + encodeURIComponent(mrn), 'PATCH', body);
      },
    },
    queue: {
      open: (payload: Record<string, any>) =>
        sendJson<any>('/queue/encounters', 'POST', payload),
      requestAdmission: (encounterId: number | string, p?: { ward_preference?: string; reason?: string; urgency?: string }) =>
        sendJson<any>('/queue/encounters/' + encounterId + '/request-admission', 'POST', p ?? {}),
      listAdmissionRequests: (status = 'pending') =>
        fetchRaw<any>('/queue/admission-requests?status=' + encodeURIComponent(status)),
      decideAdmission: (requestId: number | string, p: { accept: boolean; bed_id?: number; note?: string }) =>
        sendJson<any>('/queue/admission-requests/' + requestId + '/decision', 'POST', p),
      listInpatients: () => fetchRaw<any>('/queue/inpatients'),
        /** Doctors on seat today (room, clock, roster, leave) for the front desk's check-in picker. */
        doctorsToday: () => fetchRaw<any>('/queue/doctors-today'),
      listRoomAssignments: (day?: string) =>
        fetchRaw<any>('/queue/room-assignments' + (day ? '?assigned_on=' + encodeURIComponent(day) : '')),
      assignRoom: (p: { doctor_id: string; room: string; assigned_on?: string; notes?: string }) =>
        sendJson<any>('/queue/room-assignments', 'POST', p),
      clearRoomAssignment: (id: number | string) =>
        sendJson<any>('/queue/room-assignments/' + id, 'DELETE', {}),
      getActiveEncounter: (patientId: string | number) =>
        fetchRaw<{ active_encounter: any | null }>('/queue/patients/' + patientId + '/active-encounter'),
      list: (params?: { status?: string; department?: string; doctor?: string; patient_id?: number; active_only?: boolean }) => {
        const qs = new URLSearchParams();
        if (params?.status)      qs.set('status', params.status);
        if (params?.department)  qs.set('department', params.department);
        if (params?.doctor)      qs.set('doctor', params.doctor);
        if (params?.patient_id)  qs.set('patient_id', String(params.patient_id));
        if (params?.active_only) qs.set('active_only', 'true');
        return fetchRaw<any>('/queue/encounters' + (qs.toString() ? '?' + qs : ''));
      },
      get:       (id: string) => fetchRaw<any>('/queue/encounters/' + id),
      triage:    (id: string, p: Record<string, any>) => sendJson<any>('/queue/encounters/' + id + '/triage', 'POST', {
        ...p,
        triage_level: p.triage_level ?? p.triage_priority,
      }),
      consult:      (id: string, p: Record<string, any>) => sendJson<any>('/queue/encounters/' + id + '/consult', 'POST', p),
      advance:      (id: string, p: Record<string, any>) => sendJson<any>('/queue/encounters/' + id + '/advance', 'POST', p),
      discharge:    (id: string, p: Record<string, any>) => sendJson<any>('/queue/encounters/' + id + '/discharge', 'POST', p),
      nursingDone:  (id: string | number) => sendJson<any>('/queue/encounters/' + id + '/nurse-done', 'POST', {}),
      callPatient:  (id: string | number, room?: string) => sendJson<any>('/queue/encounters/' + id + '/call', 'POST', { room }),
      assignNurse:  (id: string | number, nurseId: string | null) => sendJson<any>('/queue/encounters/' + id + '/assign-nurse', 'PATCH', { nurse_id: nurseId }),
      listNotes:    (id: string) => fetchRaw<any>('/queue/encounters/' + id + '/notes'),
      addNote:      (id: string, p: Record<string, any>) => sendJson<any>('/queue/encounters/' + id + '/notes', 'POST', p),
      pauseConsultation:  (id: string | number, reason?: string) => sendJson<any>('/queue/encounters/' + id + '/pause', 'POST', { reason }),
      resumeConsultation: (id: string | number) => sendJson<any>('/queue/encounters/' + id + '/resume', 'POST', {}),
      endConsultation:    (id: string | number, p?: Record<string, any>) => sendJson<any>('/queue/encounters/' + id + '/end-consultation', 'POST', p ?? {}),
    },
    display: {
      getQueue: (department?: string) =>
        fetchRaw<any>('/integrations/queue/display' + (department ? '?department=' + encodeURIComponent(department) : '')),
    },
    wards: {
      list: () => fetchRaw<any>('/wards'),
      create: (p: Record<string, any>) => sendJson<any>('/wards', 'POST', p),
      beds: (wardId: string) => fetchRaw<any>('/wards/' + wardId + '/beds'),
      availableBeds: () => fetchRaw<any>('/wards/beds/available'),
      addBed: (wardId: string, p: Record<string, any>) => sendJson<any>('/wards/' + wardId + '/beds', 'POST', p),
      admitBed: (wardId: string, bedId: string, p: Record<string, any>) =>
        sendJson<any>('/wards/' + wardId + '/beds/' + bedId + '/admit', 'POST', p),
      freeBed: (wardId: string, bedId: string) =>
        sendJson<any>('/wards/' + wardId + '/beds/' + bedId + '/discharge', 'POST', {}),
      updateBedStatus: (wardId: string, bedId: string, p: { status: string; notes?: string }) =>
        sendJson<any>('/wards/' + wardId + '/beds/' + bedId + '/status', 'PATCH', p),
    },
    billing: {
      createBill: (p: Record<string, any>) => sendJson<any>('/billing_hospital/bills', 'POST', p),
      revenueSplit: (p?: { date_from?: string; date_to?: string }) => {
        const qs = new URLSearchParams();
        if (p?.date_from) qs.set('date_from', p.date_from);
        if (p?.date_to) qs.set('date_to', p.date_to);
        const s = qs.toString();
        return fetchRaw<any>('/billing_hospital/revenue-split' + (s ? '?' + s : ''));
      },
      encounterCharges: (encounterId: number | string) =>
        fetchRaw<any>('/billing_hospital/encounters/' + encounterId + '/charges'),
      addEncounterCharge: (encounterId: number | string, p: Record<string, any>) =>
        sendJson<any>('/billing_hospital/encounters/' + encounterId + '/charges', 'POST', p),
      removeEncounterCharge: (encounterId: number | string, chargeId: number | string) =>
        sendJson<any>('/billing_hospital/encounters/' + encounterId + '/charges/' + chargeId, 'DELETE', {}),
      listAdjustments: (billId: number | string) =>
        fetchRaw<any>('/billing_hospital/bills/' + billId + '/adjustments'),
      adjustBill: (billId: number | string, p: Record<string, any>) =>
        sendJson<any>('/billing_hospital/bills/' + billId + '/adjust', 'POST', p),
      reverseAdjustment: (billId: number | string, adjustmentId: number | string, reason: string) =>
        sendJson<any>('/billing_hospital/bills/' + billId + '/adjustments/' + adjustmentId + '/reverse',
          'POST', { adjustment_type: 'reversal', amount: 1, reason }),
      wardRates: () => fetchRaw<any>('/billing_hospital/ward-rates'),
      // Room rates, which are what actually bills: the charge resolves
      // bed -> room -> ward, so with 19 of 21 rooms priced, editing a ward rate
      // changes nothing for those beds.
      listRooms: () => fetchRaw<any>('/wards/rooms'),
      setRoomRate: (roomId: number | string, daily_rate: number) =>
        sendJson<any>('/wards/rooms/' + roomId + '/rate', 'PATCH', { daily_rate }),
      setWardRate: (wardId: number | string, daily_rate: number) =>
        sendJson<any>('/billing_hospital/ward-rates/' + wardId, 'PATCH', { daily_rate }),
      requestDiscount: (billId: number | string, amount: number, reason?: string) =>
        sendJson<any>('/billing_hospital/bills/' + billId + '/request-discount', 'POST', { amount, reason }),
      pendingDiscounts: () => fetchRaw<any>('/billing_hospital/bills/pending-discounts'),
      // NOTE the field name: this endpoint takes `approve`, while the pharmacy
      // APPROVAL endpoint takes `approved`. Normalised here so callers pass a
      // plain boolean and cannot get it wrong — sending the other spelling
      // fails validation with a 422 rather than doing nothing visible.
      discountDecision: (billId: number | string, approved: boolean, note?: string) =>
        sendJson<any>('/billing_hospital/bills/' + billId + '/discount-decision', 'POST', { approve: approved, note }),
      decideDiscount: (billId: number | string, approve: boolean, note?: string) =>
        sendJson<any>('/billing_hospital/bills/' + billId + '/discount-decision', 'POST', { approve, note }),
      createBillFromEncounter: (p: Record<string, any>) => sendJson<any>('/billing_hospital/bills/from-encounter', 'POST', p),
      listBills: (params?: { status?: string; patient_id?: number; encounter_id?: number; entity?: string; limit?: number; payer?: string }) => {
        const qs = new URLSearchParams();
        if (params?.payer)       qs.set('payer', params.payer);
        if (params?.entity)      qs.set('entity', params.entity);
        if (params?.limit)       qs.set('limit', String(params.limit));
        if (params?.status)      qs.set('status', params.status);
        if (params?.patient_id)  qs.set('patient_id', String(params.patient_id));
        if (params?.encounter_id) qs.set('encounter_id', String(params.encounter_id));
        return fetchRaw<any>('/billing_hospital/bills' + (qs.toString() ? '?' + qs : ''));
      },
      getBill: (id: string) => fetchRaw<any>('/billing_hospital/bills/' + id),
      getSuggestedItems: (encounterId: string | number) =>
        fetchRaw<any>('/billing_hospital/encounters/' + encounterId + '/suggested-items'),
      getInvoice: (billId: string | number) =>
        fetchRaw<any>('/billing_hospital/bills/' + billId + '/invoice'),
      recordPayment: (id: string, p: Record<string, any>) => sendJson<any>('/billing_hospital/bills/' + id + '/payment', 'POST', {
        ...p,
        reference: p.reference ?? p.reference_number,
      }),
      waiveBill:     (id: string, p: Record<string, any>) => sendJson<any>('/billing_hospital/bills/' + id + '/waive', 'POST', p),
      createClaim:   (p: Record<string, any>) => sendJson<any>('/billing_hospital/claims', 'POST', {
        ...p,
        billing_id: p.billing_id ?? p.bill_id,
        hmo_provider: p.hmo_provider ?? p.insurer_name,
      }),
      listClaims: (params?: { status?: string }) => {
        const qs = new URLSearchParams();
        if (params?.status) qs.set('status', params.status);
        return fetchRaw<any>('/billing_hospital/claims' + (qs.toString() ? '?' + qs : ''));
      },
      updateClaim: (id: string, p: Record<string, any>) => sendJson<any>('/billing_hospital/claims/' + id, 'PATCH', p),
      getStats: () => fetchRaw<any>('/billing_hospital/stats'),
      writeOffBill: (id: string, p: Record<string, any> = {}) =>
        sendJson<any>('/billing_hospital/bills/' + id + '/write-off', 'POST', p),
      listUnbilledEncounters: (limit?: number) =>
        fetchRaw<any>('/billing_hospital/unbilled-encounters' + (limit ? '?limit=' + limit : '')),
      // Stage billing (front desk -> doctor -> cashier -> services), corrections and printed documents.
      voidPayment: (paymentId: number | string, reason: string) =>
        sendJson<any>('/billing_hospital/payments/' + paymentId + '/void', 'POST', { reason }),
      voidBill: (billId: number | string, reason: string) =>
        sendJson<any>('/billing_hospital/bills/' + billId + '/void', 'POST', { reason }),
      releaseBill: (billId: number | string, reason: string) =>
        sendJson<any>('/billing_hospital/bills/' + billId + '/release', 'POST', { reason }),
      releaseOrder: (source: string, source_id: number | string, reason: string) =>
        sendJson<any>('/billing_hospital/releases', 'POST', { source, source_id: String(source_id), reason }),
      clearance: (source: string, source_id: number | string) =>
        fetchRaw<any>('/billing_hospital/clearance?source=' + encodeURIComponent(source) + '&source_id=' + encodeURIComponent(String(source_id))),
      claimsForm: (billId: number | string) => fetchRaw<any>('/billing_hospital/bills/' + billId + '/claims-form'),
      patientAccount: (patientId: number | string) => fetchRaw<any>('/billing_hospital/patients/' + patientId + '/account'),
      sendToCashier: (encounterId: number | string) =>
        sendJson<any>('/queue/encounters/' + encounterId + '/send-to-cashier', 'POST', {}),
      frontDeskQuote: (encounterId: number | string) =>
        fetchRaw<any>('/billing_hospital/encounters/' + encounterId + '/front-desk-quote'),
      consultationQuote: (p: { patient_id: number | string; department?: string; doctor_id?: string; specialty?: string; kind?: string }) => {
        const qs = new URLSearchParams();
        Object.entries(p).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') qs.set(k, String(v)); });
        return fetchRaw<any>('/billing_hospital/consultation-quote?' + qs.toString());
      },
      consultationTariffs: () => fetchRaw<any>('/billing_hospital/consultation-tariffs'),
      saveConsultationTariff: (id: number | string | 'new', p: Record<string, any>) =>
        sendJson<any>('/billing_hospital/consultation-tariffs/' + id, 'PUT', p),
      saveDoctorFee: (doctorId: string, p: Record<string, any>) =>
        sendJson<any>('/billing_hospital/doctor-fees/' + doctorId, 'PUT', p),
      saveBillingSettings: (p: Record<string, any>) => sendJson<any>('/billing_hospital/billing-settings', 'PUT', p),
      importConsultationTariffs: (rows: Record<string, any>[]) =>
        sendJson<any>('/billing_hospital/consultation-tariffs/import', 'POST', { rows }),
    },
    // Department stores (Immunisation, Lab, Urology...) run by the departments themselves.
    stores: {
      get: (path: string, params?: Record<string, any>) => {
        const qs = new URLSearchParams();
        Object.entries(params ?? {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') qs.set(k, String(v)); });
        return fetchRaw<any>('/stock/stores' + path + (qs.toString() ? '?' + qs : ''));
      },
      post: (path: string, body: Record<string, any>) => sendJson<any>('/stock/stores' + path, 'POST', body),
    },
    appointments: {
      createSlot: (p: Record<string, any>) => sendJson<any>('/appointments/slots', 'POST', {
        ...p,
        doctor_id: p.doctor_id || undefined,
        doctor_name: p.doctor_name ?? p.provider_name,
        slot_date: p.slot_date ?? p.date,
        slot_time: p.slot_time ?? p.start_time,
        max_patients: p.max_patients ?? p.capacity,
        department: p.department === 'General OPD' ? 'OPD' : p.department,
      }),
      listSlots: (params?: { date?: string; provider?: string; availableOnly?: boolean; mine?: boolean }) => {
        const qs = new URLSearchParams();
        if (params?.mine)     qs.set('mine', 'true');
        if (params?.date)     qs.set('slot_date', params.date);
        if (params?.provider) qs.set('doctor_name', params.provider);
        if (params?.availableOnly === false) qs.set('available_only', 'false');
        return fetchRaw<any>('/appointments/slots' + (qs.toString() ? '?' + qs : ''));
      },
      deleteSlot: (id: string) => sendDelete<any>('/appointments/slots/' + id),
      book: (p: Record<string, any>) => sendJson<any>('/appointments/book', 'POST', p),
      list: (params?: { date?: string; date_to?: string; status?: string; mine?: boolean }) => {
        const qs = new URLSearchParams();
        if (params?.mine)    qs.set('mine',    'true');
        if (params?.date)    qs.set('date',    params.date);
        if (params?.date_to) qs.set('date_to', params.date_to);
        if (params?.status)  qs.set('status',  params.status === 'scheduled' ? 'booked' : params.status);
        return fetchRaw<any>('/appointments' + (qs.toString() ? '?' + qs : ''));
      },
      arrive:   (id: string) => sendJson<any>('/appointments/' + id + '/arrive',   'PATCH', {}),
      complete: (id: string) => sendJson<any>('/appointments/' + id + '/complete', 'PATCH', {}),
      cancel:   (id: string, p: Record<string, any>) => sendJson<any>('/appointments/' + id + '/cancel', 'PATCH', p),
      noShow:   (id: string) => sendJson<any>('/appointments/' + id + '/no-show', 'PATCH', {}),
      // Scheduling Control Center additions
      calendar: (params?: { date_from?: string; date_to?: string; doctor_name?: string; doctor_id?: string; department?: string; mine?: boolean }) => {
        const qs = new URLSearchParams();
        if (params?.mine)        qs.set('mine',        'true');
        if (params?.date_from)   qs.set('date_from',   params.date_from);
        if (params?.date_to)     qs.set('date_to',     params.date_to);
        if (params?.doctor_id)   qs.set('doctor_id',   params.doctor_id);
        else if (params?.doctor_name) qs.set('doctor_name', params.doctor_name);
        if (params?.department)  qs.set('department',  params.department);
        return fetchRaw<any>('/appointments/calendar' + (qs.toString() ? '?' + qs : ''));
      },
      doctors:  () => fetchRaw<{ doctors: { doctor_name: string; department: string }[] }>('/appointments/doctors'),
      nextSlot: (params?: { doctor_name?: string; department?: string }) => {
        const qs = new URLSearchParams();
        if (params?.doctor_name) qs.set('doctor_name', params.doctor_name);
        if (params?.department)  qs.set('department',  params.department);
        return fetchRaw<any>('/appointments/next-slot' + (qs.toString() ? '?' + qs : ''));
      },
      remind: (id: string) => sendJson<any>('/appointments/' + id + '/remind', 'POST', {}),
    },
    coverage: {
      quote: (p: Record<string, any>) => sendJson<any>('/coverage/quote', 'POST', p),
      estimateBill: (p: Record<string, any>) => sendJson<any>('/coverage/estimate-bill', 'POST', p),
      patients: (params?: { hmo_id?: string | number; search?: string }) => {
        const qs = new URLSearchParams();
        if (params?.hmo_id) qs.set('hmo_id', String(params.hmo_id));
        if (params?.search) qs.set('search', params.search);
        return fetchRaw<any>('/coverage/patients' + (qs.toString() ? '?' + qs : ''));
      },
      hmos: () => fetchRaw<any>('/coverage/hmos'),
      createHmo: (p: Record<string, any>) => sendJson<any>('/coverage/hmos', 'POST', p),
      updateHmo: (id: number | string, p: Record<string, any>) => sendJson<any>('/coverage/hmos/' + id, 'PATCH', p),
      listPlans: (hmo_id: number | string, activeOnly = true) =>
        fetchRaw<any>('/coverage/hmos/' + hmo_id + '/plans' + (activeOnly ? '' : '?active_only=false')),
      createPlan: (hmo_id: number | string, p: Record<string, any>) =>
        sendJson<any>('/coverage/hmos/' + hmo_id + '/plans', 'POST', p),
      services: (params?: { category?: string; q?: string; limit?: number } | string) => {
        // Legacy call sites passed a bare category string.
        const p = typeof params === 'string' ? { category: params } : (params ?? {});
        const qs = new URLSearchParams();
        if (p.category) qs.set('category', p.category);
        if (p.q) qs.set('q', p.q);
        if (p.limit) qs.set('limit', String(p.limit));
        const s = qs.toString();
        return fetchRaw<any>('/coverage/services' + (s ? '?' + s : ''));
      },
      /** Every HMO's negotiated price for one service (migration 198). */
      servicePayerPrices: (serviceId: number | string) =>
        fetchRaw<any>('/coverage/services/' + serviceId + '/payer-prices'),
      createService: (p: Record<string, any>) => sendJson<any>('/coverage/services', 'POST', p),
      updateService: (id: string | number, p: Record<string, any>) => sendJson<any>('/coverage/services/' + id, 'PATCH', p),
      listRules: (hmo_id?: string) => fetchRaw<any>('/coverage/rules' + (hmo_id ? '?hmo_id=' + encodeURIComponent(hmo_id) : '')),
      createRule: (p: Record<string, any>) => sendJson<any>('/coverage/rules', 'POST', p),
      updateRule: (id: number | string, p: Record<string, any>) => sendJson<any>('/coverage/rules/' + id, 'PATCH', p),
      previewTariffImport: (hmoId: number | string, file: File) => {
        const fd = new FormData();
        fd.append('file', file);
        return sendFormData<any>('/coverage/hmos/' + hmoId + '/tariff-import/preview', 'POST', fd);
      },
      commitTariffImport: (hmoId: number | string, rows: any[]) =>
        sendJson<any>('/coverage/hmos/' + hmoId + '/tariff-import/commit', 'POST', { rows }),
      listPatientInsurance: (patientId: number | string) =>
        fetchRaw<any>('/coverage/patient-insurance?patient_id=' + patientId),
      createPatientInsurance: (p: Record<string, any>) => sendJson<any>('/coverage/patient-insurance', 'POST', p),
      updatePatientInsurance: (id: number | string, p: Record<string, any>) =>
        sendJson<any>('/coverage/patient-insurance/' + id, 'PATCH', p),
      listClaims: (params?: { patient_id?: number | string; status?: string; hmo_provider_id?: number | string }) => {
        const qs = new URLSearchParams();
        if (params?.patient_id) qs.set('patient_id', String(params.patient_id));
        if (params?.status) qs.set('status', params.status);
        if (params?.hmo_provider_id) qs.set('hmo_provider_id', String(params.hmo_provider_id));
        const q = qs.toString();
        return fetchRaw<any>('/coverage/claims' + (q ? '?' + q : ''));
      },
      updateClaim: (id: number | string, p: Record<string, any>) => sendJson<any>('/coverage/claims/' + id, 'PATCH', p),
      requestAuthorization: (p: Record<string, any>) => sendJson<any>('/coverage/authorizations', 'POST', p),
      listAuthorizations: (status?: string) => fetchRaw<any>('/coverage/authorizations' + (status ? '?status=' + encodeURIComponent(status) : '')),
      resolveAuthorization: (id: number, p: Record<string, any>) => sendJson<any>('/coverage/authorizations/' + id, 'PATCH', p),
      /** HMO desk: the HMO patients on the queue now (and discharged in the last `days` days). */
      hmoDesk: (days = 0) => fetchRaw<any>('/coverage/hmo-desk?days=' + days),
      hmoDeskPatient: (encounterId: number | string) => fetchRaw<any>('/coverage/hmo-desk/' + encounterId),
      hmoDeskVerify: (encounterId: number | string, verified: boolean, note?: string) =>
        sendJson<any>('/coverage/hmo-desk/' + encounterId + '/verify', 'POST', { verified, note }),
      /** The patient's signature for the visit's claims form, from the signature pad. */
      hmoDeskSignature: async (encounterId: number | string, file: File): Promise<{ signature_url: string }> => {
        const token = await getBearerToken();
        const form = new FormData();
        form.append('file', file);
        const res = await fetch(apiUrl('/coverage/hmo-desk/' + encounterId + '/signature'), {
          method: 'POST', headers: { 'Authorization': `Bearer ${token}` }, body: form,
        });
        if (!res.ok) throw new ApiError('Signature upload failed', res.status, 'server');
        return res.json();
      },
      /** The HMO team's check of a visit's billed services (covered / not covered / HMO approval). */
      visitServices: (encounterId: number | string) => fetchRaw<any>('/coverage/visits/' + encounterId + '/services'),
      decideService: (itemId: number | string, decision: 'covered' | 'not_covered', note?: string) =>
        sendJson<any>('/coverage/bill-items/' + itemId + '/decision', 'POST', { decision, note }),
      requestServiceApproval: (itemId: number | string, reason: string) =>
        sendJson<any>('/coverage/bill-items/' + itemId + '/request-approval', 'POST', { reason }),
      answerServiceApproval: (itemId: number | string, p: { approved: boolean; authorization_code?: string; note?: string }) =>
        sendJson<any>('/coverage/bill-items/' + itemId + '/approval', 'POST', p),
      approvalRequests: () => fetchRaw<any>('/coverage/approval-requests'),
    },
    hope: {
      sync: (entity: 'patients' | 'appointments' | 'admissions' | 'lab' | 'pharmacy' | 'billing', limit = 200) =>
        sendJson<any>('/hope/sync/' + entity + '?limit=' + String(limit), 'POST', {}),
    },
    clinical: {
      searchIcd10: (q: string) => fetchRaw<any>('/clinical/icd10?q=' + encodeURIComponent(q)),
      /** ICD-10 diagnoses suggested from what the doctor has written (complaint, history, examination, assessment). */
      suggestIcd10: (text: string) => fetchRaw<any>('/clinical/icd10/suggest?text=' + encodeURIComponent(text.slice(0, 1500))),
      listNoteTitles: (department?: string) =>
        fetchRaw<any>('/clinical/note-titles' + (department ? '?department=' + encodeURIComponent(department) : '')),
      searchDrugs: (q: string) => fetchRaw<any>('/clinical/drugs?q=' + encodeURIComponent(q)),

      // ── Phase B0: migrated Hope reference data (migrations 179-195) ──────
      // NOTE: listNoteTitles above serves royan_note_titles (5 seed rows, the
      // note-type catalog). listNoteTemplates below serves royan_note_templates
      // (528 migrated phrase bundles). Different tables, different purposes.
      listNoteTemplates: (p?: { context_type?: string; scope?: string; q?: string }) => {
        const qs = new URLSearchParams();
        if (p?.context_type) qs.set('context_type', p.context_type);
        if (p?.scope) qs.set('scope', p.scope);
        if (p?.q) qs.set('q', p.q);
        const s = qs.toString();
        return fetchRaw<any>('/clinical/note-templates' + (s ? '?' + s : ''));
      },
      listNoteTemplateTexts: (templateId: number | string, contextType?: string) =>
        fetchRaw<any>('/clinical/note-templates/' + templateId + '/texts' +
          (contextType ? '?context_type=' + encodeURIComponent(contextType) : '')),
      // A doctor's own templates. Only the owner can update or delete one.
      createNoteTemplate: (body: NoteTemplateWrite) =>
        sendJson<any>('/clinical/note-templates', 'POST', body),
      updateNoteTemplate: (templateId: number | string, body: NoteTemplateWrite) =>
        sendJson<any>('/clinical/note-templates/' + templateId, 'PUT', body),
      deleteNoteTemplate: (templateId: number | string) =>
        sendJson<any>('/clinical/note-templates/' + templateId, 'DELETE', {}),

      listExamTemplates: (p?: { category?: string; patient_sex?: string | null }) => {
        const qs = new URLSearchParams();
        if (p?.category) qs.set('category', p.category);
        if (p?.patient_sex) qs.set('patient_sex', p.patient_sex);
        const s = qs.toString();
        return fetchRaw<any>('/clinical/exam-templates' + (s ? '?' + s : ''));
      },
      // Capped server-side: 44,405 findings exist, ~2,760 per ROS organ system.
      listExamFindings: (templateId: number | string, p?: { q?: string; defaults_only?: boolean; limit?: number }) => {
        const qs = new URLSearchParams();
        if (p?.q) qs.set('q', p.q);
        if (p?.defaults_only) qs.set('defaults_only', 'true');
        if (p?.limit) qs.set('limit', String(p.limit));
        const s = qs.toString();
        return fetchRaw<any>('/clinical/exam-templates/' + templateId + '/findings' + (s ? '?' + s : ''));
      },

      searchSmartPhrases: (q?: string, isNursing?: boolean) => {
        const qs = new URLSearchParams();
        if (q) qs.set('q', q);
        if (isNursing !== undefined) qs.set('is_nursing', String(isNursing));
        const s = qs.toString();
        return fetchRaw<any>('/clinical/smart-phrases' + (s ? '?' + s : ''));
      },
      listSmartPhraseOptions: (tokenId: string) =>
        fetchRaw<any>('/clinical/smart-phrase-options?token_id=' + encodeURIComponent(tokenId)),

      listOrderSets: () => fetchRaw<any>('/clinical/order-sets'),
      listOrderSetItems: (orderSetId: number | string) =>
        fetchRaw<any>('/clinical/order-sets/' + orderSetId + '/items'),

      searchRadiologyCatalog: (q?: string) =>
        fetchRaw<any>('/clinical/radiology-catalog' + (q ? '?q=' + encodeURIComponent(q) : '')),
      searchSurgeryCatalog: (q?: string) =>
        fetchRaw<any>('/clinical/surgery-catalog' + (q ? '?q=' + encodeURIComponent(q) : '')),
      searchAllergens: (q: string) =>
        fetchRaw<any>('/clinical/allergens?q=' + encodeURIComponent(q)),
      searchDiagnosisCatalog: (q?: string) =>
        fetchRaw<any>('/clinical/diagnosis-catalog' + (q ? '?q=' + encodeURIComponent(q) : '')),
      searchTariffCatalog: (q?: string) =>
        fetchRaw<any>('/clinical/tariff-catalog' + (q ? '?q=' + encodeURIComponent(q) : '')),

      // Patient-scoped note listing across ALL encounters. The only other note
      // listing is encounter-scoped (queue.listNotes), which is right for a
      // consultation but wrong for the Nurse Station.
      listPatientNotes: (patientId: number | string, p?: { note_type?: string; limit?: number }) => {
        const qs = new URLSearchParams();
        if (p?.note_type) qs.set('note_type', p.note_type);
        if (p?.limit) qs.set('limit', String(p.limit));
        const s = qs.toString();
        return fetchRaw<any>('/clinical/patients/' + patientId + '/notes' + (s ? '?' + s : ''));
      },

      /**
       * Recent notes across every patient — the ward's activity rather than one
       * chart's. Backs the Nursing Station, where the question is "what has been
       * written since my last shift", not "what is on this patient".
       */
      listRecentNotes: (p?: { note_type?: string; limit?: number }) => {
        const qs = new URLSearchParams();
        if (p?.note_type) qs.set('note_type', p.note_type);
        if (p?.limit) qs.set('limit', String(p.limit));
        const s = qs.toString();
        return fetchRaw<any>('/clinical/notes/recent' + (s ? '?' + s : ''));
      },

      // Patient-scoped migrated history (backs the new chart cards in B2)
      listFlowsheet: (patientId: number | string, limit = 200) =>
        fetchRaw<any>('/clinical/patients/' + patientId + '/flowsheet?limit=' + limit),
      listWardStays: (patientId: number | string) =>
        fetchRaw<any>('/clinical/patients/' + patientId + '/ward-stays'),
      listPatientDocuments: (patientId: number | string) =>
        fetchRaw<any>('/clinical/patients/' + patientId + '/documents'),
      listMedicationAdministration: (patientId: number | string) =>
        fetchRaw<any>('/clinical/patients/' + patientId + '/medication-administration'),
      listPatientEncounters: (patientId: number | string, limit = 100) =>
        fetchRaw<any>('/clinical/patients/' + patientId + '/encounters?limit=' + limit),
      financialLedger: (patientId: number | string, limit = 100) =>
        fetchRaw<any>('/clinical/patients/' + patientId + '/financial-ledger?limit=' + limit),
      doctorSchedule: (doctorRef?: string) =>
        fetchRaw<any>('/clinical/doctor-schedule' + (doctorRef ? '?doctor_ref=' + encodeURIComponent(doctorRef) : '')),
      hopeArchive: (sourceTable?: string, limit = 50) =>
        fetchRaw<any>('/clinical/hope-archive?limit=' + limit + (sourceTable ? '&source_table=' + encodeURIComponent(sourceTable) : '')),
      listBillingHistory: (patientId: number | string, limit = 100) =>
        fetchRaw<any>('/clinical/patients/' + patientId + '/billing-history?limit=' + limit),

      addNoteAddendum: (encounterId: number | string, noteId: number | string, p: { content: string; reason?: string }) =>
        sendJson<any>('/queue/encounters/' + encounterId + '/notes/' + noteId + '/addendum', 'POST', p),
      listProblems: (patientId: number | string, status?: string) =>
        fetchRaw<any>('/clinical/patients/' + patientId + '/problems' + (status ? '?status=' + encodeURIComponent(status) : '')),
      addProblem: (patientId: number | string, p: Record<string, any>) =>
        sendJson<any>('/clinical/patients/' + patientId + '/problems', 'POST', p),
      updateProblem: (problemId: number | string, p: Record<string, any>) =>
        sendJson<any>('/clinical/problems/' + problemId, 'PATCH', p),
      deleteProblem: (problemId: number | string) =>
        sendJson<any>('/clinical/problems/' + problemId, 'DELETE', {}),
      // Postings — CPRS cover-sheet clinical flags/notices
      listPostings: (patientId: number | string, activeOnly = true) =>
        fetchRaw<any>('/clinical/patients/' + patientId + '/postings?active_only=' + activeOnly),
      addPosting: (patientId: number | string, p: Record<string, any>) =>
        sendJson<any>('/clinical/patients/' + patientId + '/postings', 'POST', p),
      resolvePosting: (postingId: number | string) =>
        sendJson<any>('/clinical/postings/' + postingId + '/resolve', 'PATCH', {}),
      // Clinical Reminders — CPRS cover-sheet due/overdue care-gap alerts
      listReminders: (patientId: number | string) =>
        fetchRaw<any>('/clinical/patients/' + patientId + '/reminders'),
      dismissReminder: (reminderId: number | string) =>
        sendJson<any>('/clinical/reminders/' + reminderId + '/dismiss', 'PATCH', {}),
    },
    consent: {
      list: (patientId: number | string) => fetchRaw<any>('/patients/' + patientId + '/consent'),
      add: (patientId: number | string, p: Record<string, any>) =>
        sendJson<any>('/patients/' + patientId + '/consent', 'POST', p),
    },
    inpatientBill: {
      get: (encounterId: number | string) =>
        fetchRaw<any>('/billing_hospital/inpatient-bill/' + encounterId),
      addLine: (encounterId: number | string, p: Record<string, any>) =>
        sendJson<any>('/billing_hospital/inpatient-bill/' + encounterId + '/lines', 'POST', p),
    },
    // ── Phase 2 additions ────────────────────────────────────────────────
    pharmacy: {
      // Prescriptions (consolidated here to avoid duplicate key override —
      // see the `lab` block below for the same pattern)
      stats: () => fetchRaw<any>('/pharmacy/stats'),
      administrationQueue: (params?: { encounter_id?: number | string }) => {
        const qs = params?.encounter_id ? '?encounter_id=' + params.encounter_id : '';
        return fetchRaw<any>('/pharmacy/administration-queue' + qs);
      },
      pendingApprovals: () => fetchRaw<any>('/pharmacy/prescriptions/pending-approval'),
      approvalDecision: (rxId: number | string, approved: boolean, note?: string) =>
        sendJson<any>('/pharmacy/prescriptions/' + rxId + '/approval-decision', 'POST', { approved, note }),
      requestApproval: (rxId: number | string, reason?: string) =>
        sendJson<any>('/pharmacy/prescriptions/' + rxId + '/request-approval', 'POST', { reason }),
      decideApproval: (rxId: number | string, approved: boolean, note?: string) =>
        sendJson<any>('/pharmacy/prescriptions/' + rxId + '/approval-decision', 'POST', { approved, note }),
      createRx: (p: Record<string, any>) => sendJson<any>('/pharmacy/prescriptions', 'POST', p),
      listRx: (params?: { status?: string; encounter_id?: string | number; patient_id?: string | number; view?: "active" | "done" }) => {
        // Real backend status values only (pending|partially_dispensed|
        // dispensed|cancelled|returned) — the old active/partial alias-remap
        // shim is gone now that the panel replaces the pill-filtered page.
        const qs = new URLSearchParams();
        if (params?.status) qs.set('status', params.status);
        if (params?.encounter_id) qs.set('encounter_id', String(params.encounter_id));
        if (params?.patient_id) qs.set('patient_id', String(params.patient_id));
        if (params?.view) qs.set('view', params.view);
        return fetchRaw<any>('/pharmacy/prescriptions' + (qs.toString() ? '?' + qs : ''));
      },
      getRx: (id: string | number) => fetchRaw<any>('/pharmacy/prescriptions/' + id),
      dispense: (id: string | number, p: Record<string, any>) => sendJson<any>('/pharmacy/prescriptions/' + id + '/dispense', 'POST',  p),
      cancel:   (id: string | number, p: Record<string, any> = {}) => sendJson<any>('/pharmacy/prescriptions/' + id + '/cancel',   'POST', p),
      administer: (id: string | number, p: Record<string, any>) => sendJson<any>('/pharmacy/prescriptions/' + id + '/administer', 'POST', p),
      // Allergies
      listAllergies: (patientId: number | string) =>
        fetchRaw<any>('/pharmacy/allergies/' + patientId),
      addAllergy: (patientId: number | string, p: Record<string, any>) =>
        sendJson<any>('/pharmacy/allergies/' + patientId, 'POST', p),
      removeAllergy: (allergyId: number | string) =>
        sendJson<any>('/pharmacy/allergies/record/' + allergyId, 'DELETE', {}),
      // Drug inventory
      listInventory: (params?: { drug_name?: string; low_stock?: boolean }) => {
        const qs = new URLSearchParams();
        if (params?.drug_name) qs.set('drug_name', params.drug_name);
        if (params?.low_stock) qs.set('low_stock', 'true');
        const q = qs.toString();
        return fetchRaw<any>('/pharmacy/inventory' + (q ? '?' + q : ''));
      },
      addInventoryItem: (p: Record<string, any>) =>
        sendJson<any>('/pharmacy/inventory', 'POST', p),
      updateInventoryItem: (id: number | string, p: Record<string, any>) =>
        sendJson<any>('/pharmacy/inventory/' + id, 'PATCH', p),
      adjustStock: (id: number | string, p: Record<string, any>) =>
        sendJson<any>('/pharmacy/inventory/' + id + '/adjust', 'POST', p),
      listExpiring: (withinDays?: number) =>
        fetchRaw<any>('/pharmacy/inventory/expiring' + (withinDays ? '?within_days=' + withinDays : '')),
      listExpired: () => fetchRaw<any>('/pharmacy/inventory/expired'),
      // Pharmacy Inventory workspace — batch/lot-aware stock, risk tiers, trends
      medicationHistory: (patientId: number | string) =>
        fetchRaw<any>('/pharmacy/patients/' + patientId + '/medication-history'),
      requestDispensingDiscount: (dispensingId: number | string, body: Record<string, any>) =>
        sendJson<any>('/pharmacy/dispensing/' + dispensingId + '/request-discount', 'POST', body),
      decideDispensingDiscount: (dispensingId: number | string, approved: boolean, note?: string) =>
        // `approve`, like the billing one — unlike approvalDecision below.
        sendJson<any>('/pharmacy/dispensing/' + dispensingId + '/discount-decision', 'POST',
                      { approve: approved, note }),
      pendingDispensingDiscounts: () =>
        fetchRaw<any>('/pharmacy/dispensing/pending-discounts'),
      inventory: {
        cards: (params?: { category?: string; risk_tier?: string; search?: string }) => {
          const qs = new URLSearchParams();
          if (params?.category) qs.set('category', params.category);
          if (params?.risk_tier) qs.set('risk_tier', params.risk_tier);
          if (params?.search) qs.set('search', params.search);
          const q = qs.toString();
          return fetchRaw<any>('/pharmacy/inventory/cards' + (q ? '?' + q : ''));
        },
        drugs: (params?: { search?: string; category?: string; limit?: number }) => {
          const qs = new URLSearchParams();
          if (params?.search) qs.set('search', params.search);
          if (params?.category) qs.set('category', params.category);
          if (params?.limit) qs.set('limit', String(params.limit));
          const q = qs.toString();
          return fetchRaw<any>('/pharmacy/inventory/drugs' + (q ? '?' + q : ''));
        },
        drug: (formularyId: number | string) => fetchRaw<any>('/pharmacy/inventory/drugs/' + formularyId),
        // Migrated per-batch pricing (mrp / purchase / cost / sale + margin).
        // royan_inventory_batches carries only a single unit_cost, so this is
        // the only view of actual margin per batch.
        drugRates: (formularyId: number | string) =>
          fetchRaw<any>('/pharmacy/inventory/drugs/' + formularyId + '/rates'),
        addDrug: (p: Record<string, any>) => sendJson<any>('/pharmacy/inventory/drugs', 'POST', p),
        receiveBatch: (formularyId: number | string, p: Record<string, any>) =>
          sendJson<any>('/pharmacy/inventory/drugs/' + formularyId + '/receive', 'POST', p),
        adjustBatch: (batchId: number | string, p: { adjustment: number; reason?: string; notes?: string }) =>
          sendJson<any>('/pharmacy/inventory/batches/' + batchId + '/adjust', 'POST', p),
        report: () => fetchRaw<any>('/pharmacy/inventory/report'),
        restockSuggestion: (formularyId: number | string) =>
          fetchRaw<any>('/pharmacy/inventory/restock-suggestion/' + formularyId),
        expired: (p?: { include_empty?: boolean }) =>
          fetchRaw<any>('/pharmacy/inventory/expired' + (p?.include_empty ? '?include_empty=true' : '')),
        disposeBatch: (batchId: number | string, body: Record<string, any>) =>
          sendJson<any>('/pharmacy/inventory/batches/' + batchId + '/dispose', 'POST', body),
        summary: () => fetchRaw<any>('/pharmacy/inventory/summary'),
        trendsMostPrescribed: (params?: { window_days?: number; limit?: number }) => {
          const qs = new URLSearchParams();
          if (params?.window_days) qs.set('window_days', String(params.window_days));
          if (params?.limit) qs.set('limit', String(params.limit));
          const q = qs.toString();
          return fetchRaw<any>('/pharmacy/inventory/trends/most-prescribed' + (q ? '?' + q : ''));
        },
        trendsRecentlyDispensed: (limit?: number) =>
          fetchRaw<any>('/pharmacy/inventory/trends/recently-dispensed' + (limit ? '?limit=' + limit : '')),
      },
      // Sales on Return (SOR)
      createReturn: (p: Record<string, any>) => sendJson<any>('/pharmacy/returns', 'POST', p),
      listReturns: (params?: { patient_id?: number | string; dispensing_id?: number | string }) => {
        const qs = new URLSearchParams();
        if (params?.patient_id) qs.set('patient_id', String(params.patient_id));
        if (params?.dispensing_id) qs.set('dispensing_id', String(params.dispensing_id));
        const q = qs.toString();
        return fetchRaw<any>('/pharmacy/returns' + (q ? '?' + q : ''));
      },
      // Drug-collection signature capture
      uploadSignature: async (dispensingId: string | number, file: File): Promise<{ signature_url: string }> => {
        const token = await getBearerToken();
        const form = new FormData();
        form.append('file', file);
        const res = await fetch(apiUrl('/pharmacy/dispensing/' + dispensingId + '/signature'), {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
          body: form,
        });
        if (!res.ok) throw new ApiError('Upload failed', res.status, 'server');
        return res.json();
      },
      signatureUrl: (filename: string) => apiUrl('/pharmacy/signatures/' + encodeURIComponent(filename)),
      // Replenishment — sku maps from drug_name; status ∈ recommended|approved|ordered|received|cancelled
      listReplenishmentRequests: (params?: { sku?: string; status?: string }) => {
        const qs = new URLSearchParams();
        if (params?.sku) qs.set('sku', params.sku);
        if (params?.status) qs.set('status', params.status);
        const q = qs.toString();
        return fetchRaw<any>('/pharmacy/replenishment-requests' + (q ? '?' + q : ''));
      },
      createReplenishmentRequest: (p: { formulary_id?: number | string; drug_name?: string; requested_qty?: number; ward?: string; urgency?: string; unit?: string; notes?: string }) =>
        sendJson<any>('/pharmacy/replenishment-request', 'POST', p),
      updateReplenishmentStatus: (id: number | string, status: string) =>
        sendJson<any>('/pharmacy/replenishment-requests/' + id + '/status?status=' + encodeURIComponent(status), 'PATCH', {}),
    },
    nursing: {
      recordVitals: (p: Record<string, any>) => sendJson<any>('/nursing/vitals', 'POST', p),
      listVitals: (patientId: number | string, encounterId?: number | string) => {
        const qs = encounterId ? '?encounter_id=' + encounterId : '';
        return fetchRaw<any>('/nursing/vitals/' + patientId + qs);
      },
      createCarePlan: (p: Record<string, any>) => sendJson<any>('/nursing/care-plans', 'POST', p),
      listCarePlans: (patientId: number | string, encounterId?: number | string) => {
        const qs = encounterId ? '?encounter_id=' + encounterId : '';
        return fetchRaw<any>('/nursing/care-plans/' + patientId + qs);
      },
      updateCarePlan: (planId: number | string, p: Record<string, any>) =>
        sendJson<any>('/nursing/care-plans/' + planId, 'PATCH', p),
      logFluid: (p: Record<string, any>) => sendJson<any>('/nursing/fluid-balance', 'POST', p),
      getFluidBalance: (encounterId: number | string) =>
        fetchRaw<any>('/nursing/fluid-balance/' + encounterId),
      recordMAR: (p: Record<string, any>) => sendJson<any>('/nursing/mar', 'POST', p),
      listMAR: (encounterId: number | string, status?: string) => {
        const qs = status ? '?status=' + encodeURIComponent(status) : '';
        return fetchRaw<any>('/nursing/mar/' + encounterId + qs);
      },
      updateMAR: (entryId: number | string, p: Record<string, any>) =>
        sendJson<any>('/nursing/mar/' + entryId, 'PATCH', p),
    },
    lab: {
      // Core lab methods (consolidated here to avoid duplicate key override)
      stats: () => fetchRaw<any>('/lab/stats'),
      placeOrder: (p: Record<string, any>) => sendJson<any>('/lab/orders', 'POST', p),
      listOrders: (params?: { status?: string; urgency?: string; patient_id?: number; ordered_by?: string; encounter_id?: number; view?: "active" | "done" }) => {
        const qs = new URLSearchParams();
        if (params?.view) qs.set('view', params.view);
        if (params?.encounter_id) qs.set('encounter_id', String(params.encounter_id));
        if (params?.status)     qs.set('status',     params.status);
        if (params?.urgency)    qs.set('urgency',    params.urgency);
        if (params?.patient_id) qs.set('patient_id', String(params.patient_id));
        if (params?.ordered_by) qs.set('ordered_by', params.ordered_by);
        return fetchRaw<any>('/lab/orders' + (qs.toString() ? '?' + qs : ''));
      },
      getOrder: (id: string | number) => fetchRaw<any>('/lab/orders/' + id),
      collect: (id: string | number, p: Record<string, any> = {}) => sendJson<any>('/lab/orders/' + id + '/collect', 'POST', p),
      receive: (id: string | number, p: Record<string, any> = {}) => sendJson<any>('/lab/orders/' + id + '/receive', 'POST', p),
      reject: (id: string | number, p: Record<string, any>) => sendJson<any>('/lab/orders/' + id + '/reject', 'POST', p),
      recordResult: (id: string | number, p: Record<string, any>) => sendJson<any>('/lab/orders/' + id + '/result', 'POST', p),
      verify: (id: string | number, p: Record<string, any> = {}) => sendJson<any>('/lab/orders/' + id + '/verify', 'POST', p),
      amendResult: (id: string | number, p: Record<string, any>) => sendJson<any>('/lab/orders/' + id + '/result/amend', 'POST', p),
      getResultVersions: (id: string | number) => fetchRaw<any>('/lab/orders/' + id + '/results'),
      listCatalog: (p?: { q?: string; category?: string; include_inactive?: boolean }) => {
        const qs = new URLSearchParams();
        if (p?.q) qs.set('q', p.q);
        if (p?.category) qs.set('category', p.category);
        if (p?.include_inactive) qs.set('include_inactive', 'true');
        const s = qs.toString();
        return fetchRaw<any>('/lab/catalog' + (s ? '?' + s : ''));
      },
      testDetail: (id: number | string) => fetchRaw<any>('/lab/catalog/' + id + '/detail'),
      createCatalogEntry: (p: Record<string, any>) => sendJson<any>('/lab/catalog', 'POST', p),
      updateCatalogEntry: (id: number | string, p: Record<string, any>) =>
        sendJson<any>('/lab/catalog/' + id, 'PATCH', p),
      searchCatalog: (q: string, limit = 20) =>
        fetchRaw<any>('/lab/catalog/search?q=' + encodeURIComponent(q) + '&limit=' + limit),
      turnaround: () => fetchRaw<any>('/lab/turnaround'),
      critical:   () => fetchRaw<any>('/lab/critical'),
      listReferenceRanges: (testName?: string) => {
        const qs = testName ? '?test_name=' + encodeURIComponent(testName) : '';
        return fetchRaw<any>('/lab/reference-ranges' + qs);
      },
      createReferenceRange: (p: Record<string, any>) =>
        sendJson<any>('/lab/reference-ranges', 'POST', p),
      updateReferenceRange: (id: number | string, p: Record<string, any>) =>
        sendJson<any>('/lab/reference-ranges/' + id, 'PATCH', p),
      deleteReferenceRange: (id: number | string) =>
        sendJson<any>('/lab/reference-ranges/' + id, 'DELETE', {}),
      patientHistory: (patientId: number | string, testName?: string) => {
        const qs = testName ? '?test_name=' + encodeURIComponent(testName) : '';
        return fetchRaw<any>('/lab/patients/' + patientId + '/history' + qs);
      },
      sendOut: (orderId: number | string, p: Record<string, any>) =>
        sendJson<any>('/lab/orders/' + orderId + '/send-out', 'POST', p),
      uploadReport: async (orderId: string | number, file: File): Promise<{ report_file_url: string }> => {
        const token = await getBearerToken();
        const form = new FormData();
        form.append('file', file);
        const res = await fetch(apiUrl('/lab/orders/' + orderId + '/report-upload'), {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
          body: form,
        });
        if (!res.ok) throw new ApiError('Upload failed', res.status, 'server');
        return res.json();
      },
      reportUrl: (filename: string) => apiUrl('/lab/reports/' + encodeURIComponent(filename)),
      /** The printed lab report (Scancare template) for one or more orders of one patient. */
      report: (orderIds: Array<number | string>) => fetchRaw<any>('/lab/report?orders=' + orderIds.join(',')),
      /** Report lines to fill for a test with no template (last used here, else Hope's). */
      parameters: (testName: string, orderId?: number | string) =>
        fetchRaw<any>('/lab/parameters?test_name=' + encodeURIComponent(testName) + (orderId ? '&order_id=' + orderId : '')),
      listTemplates: (params?: { test_name?: string; active_only?: boolean }) => {
        const qs = new URLSearchParams();
        if (params?.test_name) qs.set('test_name', params.test_name);
        if (params?.active_only === false) qs.set('active_only', 'false');
        const q = qs.toString();
        return fetchRaw<any>('/lab/templates' + (q ? '?' + q : ''));
      },
      createTemplate: (p: Record<string, any>) => sendJson<any>('/lab/templates', 'POST', p),
      getTemplateForTest: (testName: string) =>
        fetchRaw<any>('/lab/templates/for-test?test_name=' + encodeURIComponent(testName)),
    },
    // ── Phase 3 — Radiology ───────────────────────────────────────────────
    radiology: {
      createOrder: (p: Record<string, any>) => sendJson<any>('/radiology/orders', 'POST', p),
      /** The printed Scancare report for a scan. */
      report: (orderId: number | string) => fetchRaw<any>('/radiology/report/' + orderId),
      /** What the report form starts with: Scancare's standard wording for this study (measurements blanked). */
      reportTemplate: (orderId: number | string) => fetchRaw<any>('/radiology/orders/' + orderId + '/report-template'),
      scancareOverview: (p: { date_from?: string; date_to?: string; include_history?: boolean } = {}) => {
        const qs = new URLSearchParams();
        if (p.date_from) qs.set('date_from', p.date_from);
        if (p.date_to) qs.set('date_to', p.date_to);
        if (p.include_history) qs.set('include_history', 'true');
        return fetchRaw<any>('/radiology/scancare/overview' + (qs.toString() ? '?' + qs : ''));
      },
      billStudy: (orderId: number | string) => sendJson<any>('/radiology/orders/' + orderId + '/bill', 'POST', {}),
      scancareWalkIn: (p: { patient_id: number; studies: number[]; urgency?: string; clinical_indication?: string; referred_by?: string }) =>
        sendJson<any>('/radiology/scancare/walk-in', 'POST', p),
      chargePreview: (orderId: number | string) =>
        fetchRaw<any>('/radiology/orders/' + orderId + '/charge-preview'),
      listOrders: (params?: { status?: string; modality?: string; patient_id?: number; encounter_id?: number; urgency?: string; date?: string; ordered_by?: string; view?: "active" | "done" }) => {
        const qs = new URLSearchParams();
        if (params?.view) qs.set('view', params.view);
        if (params?.status) qs.set('status', params.status);
        if (params?.modality) qs.set('modality', params.modality);
        if (params?.patient_id) qs.set('patient_id', String(params.patient_id));
        if (params?.encounter_id) qs.set('encounter_id', String(params.encounter_id));
        if (params?.urgency) qs.set('urgency', params.urgency);
        if (params?.date) qs.set('date', params.date);
        if (params?.ordered_by) qs.set('ordered_by', params.ordered_by);
        const q = qs.toString();
        return fetchRaw<any>('/radiology/orders' + (q ? '?' + q : ''));
      },
      getOrder: (id: number | string) => fetchRaw<any>('/radiology/orders/' + id),
      submitReport: (id: number | string, p: Record<string, any>) =>
        sendJson<any>('/radiology/orders/' + id + '/report', 'PATCH', p),
      amendReport: (id: number | string, p: Record<string, any>) =>
        sendJson<any>('/radiology/orders/' + id + '/report/amend', 'PATCH', p),
      verify: (id: number | string, p: Record<string, any> = {}) =>
        sendJson<any>('/radiology/orders/' + id + '/verify', 'POST', p),
      advanceStatus: (id: number | string, p: Record<string, any>) =>
        sendJson<any>('/radiology/orders/' + id + '/status', 'PATCH', p),
      patientHistory: (patientId: number | string, modality?: string) => {
        const qs = modality ? '?modality=' + encodeURIComponent(modality) : '';
        return fetchRaw<any>('/radiology/patients/' + patientId + '/history' + qs);
      },
      stats: () => fetchRaw<any>('/radiology/stats'),
      listTemplates: (params?: { modality?: string; search?: string }) => {
        const qs = new URLSearchParams();
        if (params?.modality) qs.set('modality', params.modality);
        if (params?.search) qs.set('search', params.search);
        const q = qs.toString();
        return fetchRaw<any>('/radiology/templates' + (q ? '?' + q : ''));
      },
      getTemplate: (id: number | string) => fetchRaw<any>('/radiology/templates/' + id),
    },
    // ── Phase 4 — Surgical Theatre ────────────────────────────────────────
    theatre: {
      scheduleCase: (p: Record<string, any>) => sendJson<any>('/theatre/cases', 'POST', p),
      listCases: (params?: { status?: string; urgency?: string; surgeon_id?: string; date?: string; patient_id?: number }) => {
        const qs = new URLSearchParams();
        if (params?.status) qs.set('status', params.status);
        if (params?.urgency) qs.set('urgency', params.urgency);
        if (params?.surgeon_id) qs.set('surgeon_id', params.surgeon_id);
        if (params?.date) qs.set('date', params.date);
        if (params?.patient_id) qs.set('patient_id', String(params.patient_id));
        const q = qs.toString();
        return fetchRaw<any>('/theatre/cases' + (q ? '?' + q : ''));
      },
      getCase: (id: number | string) => fetchRaw<any>('/theatre/cases/' + id),
      advanceStatus: (id: number | string, p: Record<string, any>) =>
        sendJson<any>('/theatre/cases/' + id + '/status', 'PATCH', p),
      submitPreOp: (id: number | string, p: Record<string, any>) =>
        sendJson<any>('/theatre/cases/' + id + '/pre-op', 'PATCH', p),
      submitAnaesthetic: (id: number | string, p: Record<string, any>) =>
        sendJson<any>('/theatre/cases/' + id + '/anaesthetic', 'PATCH', p),
      submitOperativeNotes: (id: number | string, p: Record<string, any>) =>
        sendJson<any>('/theatre/cases/' + id + '/operative-notes', 'PATCH', p),
      submitPostOp: (id: number | string, p: Record<string, any>) =>
        sendJson<any>('/theatre/cases/' + id + '/post-op', 'PATCH', p),
      dailySchedule: (date: string, theatreName?: string) => {
        const qs = '?date=' + encodeURIComponent(date) + (theatreName ? '&theatre_name=' + encodeURIComponent(theatreName) : '');
        return fetchRaw<any>('/theatre/schedule' + qs);
      },
      stats: () => fetchRaw<any>('/theatre/stats'),
      verifyOperativeNotes: (id: number | string, p: Record<string, any> = {}) =>
        sendJson<any>('/theatre/cases/' + id + '/operative-notes/verify', 'POST', p),
      amendOperativeNotes: (id: number | string, p: Record<string, any>) =>
        sendJson<any>('/theatre/cases/' + id + '/operative-notes/amend', 'PATCH', p),
    },
    // ── Phase 5 — MCH / OB-GYN ───────────────────────────────────────────
    mch: {
      // ANC
      registerAnc: (p: Record<string, any>) => sendJson<any>('/mch/anc', 'POST', p),
      listAnc: (params?: { patient_id?: number; status?: string }) => {
        const qs = new URLSearchParams();
        if (params?.patient_id) qs.set('patient_id', String(params.patient_id));
        if (params?.status)     qs.set('status', params.status);
        return fetchRaw<any>('/mch/anc?' + qs);
      },
      getAnc: (id: number | string) => fetchRaw<any>('/mch/anc/' + id),
      updateAnc: (id: number | string, p: Record<string, any>) =>
        sendJson<any>('/mch/anc/' + id, 'PATCH', p),
      // ANC Visits
      logVisit: (ancId: number | string, p: Record<string, any>) =>
        sendJson<any>('/mch/anc/' + ancId + '/visits', 'POST', p),
      listVisits: (ancId: number | string) =>
        fetchRaw<any>('/mch/anc/' + ancId + '/visits'),
      // Partograph
      addPartographEntry: (ancId: number | string, p: Record<string, any>) =>
        sendJson<any>('/mch/anc/' + ancId + '/partograph', 'POST', p),
      getPartograph: (ancId: number | string) =>
        fetchRaw<any>('/mch/anc/' + ancId + '/partograph'),
      // Delivery
      recordDelivery: (ancId: number | string, p: Record<string, any>) =>
        sendJson<any>('/mch/anc/' + ancId + '/delivery', 'POST', p),
      getDelivery: (ancId: number | string) =>
        fetchRaw<any>('/mch/anc/' + ancId + '/delivery'),
      // Newborn
      addNewbornAssessment: (deliveryId: number | string, p: Record<string, any>) =>
        sendJson<any>('/mch/delivery/' + deliveryId + '/newborn', 'POST', p),
      getNewbornAssessments: (deliveryId: number | string) =>
        fetchRaw<any>('/mch/delivery/' + deliveryId + '/newborn'),
      // Immunisation
      logImmunisation: (patientId: number | string, p: Record<string, any>) =>
        sendJson<any>('/mch/patients/' + patientId + '/immunisation', 'POST', p),
      getImmunisationHistory: (patientId: number | string) =>
        fetchRaw<any>('/mch/patients/' + patientId + '/immunisation'),
      // Babies (mother-baby linkage)
      listBabies: (motherPatientId: number | string) =>
        fetchRaw<any>('/mch/patients/' + motherPatientId + '/babies'),
      // Babies roster (hospital-wide, not scoped to one mother) + detail
      listBabiesRoster: (params?: { search?: string; status?: string; limit?: number }) => {
        const qs = new URLSearchParams();
        if (params?.search) qs.set('search', params.search);
        if (params?.status) qs.set('status', params.status);
        if (params?.limit)  qs.set('limit', String(params.limit));
        const s = qs.toString();
        return fetchRaw<any>('/mch/babies' + (s ? '?' + s : ''));
      },
      getBaby: (patientId: number | string) => fetchRaw<any>('/mch/babies/' + patientId),
      registerBaby: (payload: Record<string, any>) => sendJson<any>('/mch/babies/register', 'POST', payload),
      // Vaccine schedule reference data
      listVaccineSchedule: (params?: { patient_id?: number | string }) => {
        const qs = params?.patient_id ? '?patient_id=' + params.patient_id : '';
        return fetchRaw<any>('/mch/vaccine-schedule' + qs);
      },
      // Stats
      stats: () => fetchRaw<any>('/mch/stats'),
    },
  },
  // ── Phase 6 — Notifications / SMS ───────────────────────────────────────
  notifications: {
    send: (p: Record<string, any>) => sendJson<any>('/notifications/send', 'POST', p),
    bulkSend: (p: Record<string, any>) => sendJson<any>('/notifications/bulk', 'POST', p),
    appointmentReminder: (p: { days_ahead?: number; message_template?: string }) =>
      sendJson<any>('/notifications/appointment-reminder', 'POST', p),
    listLogs: (params?: { channel?: string; status?: string; patient_id?: number; campaign_name?: string; date?: string }) => {
      const qs = new URLSearchParams();
      if (params?.channel)       qs.set('channel', params.channel);
      if (params?.status)        qs.set('status', params.status);
      if (params?.patient_id)    qs.set('patient_id', String(params.patient_id));
      if (params?.campaign_name) qs.set('campaign_name', params.campaign_name);
      if (params?.date)          qs.set('date', params.date);
      return fetchRaw<any>('/notifications/logs?' + qs);
    },
    listTemplates: (params?: { channel?: string; category?: string }) => {
      const qs = new URLSearchParams();
      if (params?.channel)   qs.set('channel', params.channel);
      if (params?.category)  qs.set('category', params.category);
      return fetchRaw<any>('/notifications/templates?' + qs);
    },
    createTemplate: (p: Record<string, any>) => sendJson<any>('/notifications/templates', 'POST', p),
    updateTemplate: (id: number | string, p: Record<string, any>) =>
      sendJson<any>('/notifications/templates/' + id, 'PATCH', p),
    deleteTemplate: (id: number | string) =>
      sendJson<any>('/notifications/templates/' + id, 'DELETE', {}),
    stats: () => fetchRaw<any>('/notifications/stats'),
  },
  // ── Phase 6 — Telemedicine ───────────────────────────────────────────────
  telemedicine: {
    createSession: (p: Record<string, any>) => sendJson<any>('/telemedicine/sessions', 'POST', p),
    listSessions: (params?: { status?: string; doctor_id?: string; patient_id?: number; date?: string }) => {
      const qs = new URLSearchParams();
      if (params?.status)     qs.set('status', params.status);
      if (params?.doctor_id)  qs.set('doctor_id', params.doctor_id);
      if (params?.patient_id) qs.set('patient_id', String(params.patient_id));
      if (params?.date)       qs.set('date', params.date);
      return fetchRaw<any>('/telemedicine/sessions?' + qs);
    },
    getSession: (id: number | string) => fetchRaw<any>('/telemedicine/sessions/' + id),
    advanceStatus: (id: number | string, p: Record<string, any>) =>
      sendJson<any>('/telemedicine/sessions/' + id + '/status', 'PATCH', p),
    getJoinLinks: (id: number | string) =>
      fetchRaw<any>('/telemedicine/sessions/' + id + '/join'),
    stats: () => fetchRaw<any>('/telemedicine/stats'),
  },
  // ── Phase 7 — Quality & Safety ────────────────────────────────────────────
  quality: {
    reportIncident: (p: Record<string, any>) => sendJson<any>('/quality/incidents', 'POST', p),
    listIncidents: (params?: { status?: string; severity?: string; category?: string; ward?: string }) => {
      const qs = new URLSearchParams();
      if (params?.status)   qs.set('status', params.status);
      if (params?.severity) qs.set('severity', params.severity);
      if (params?.category) qs.set('category', params.category);
      if (params?.ward)     qs.set('ward', params.ward);
      return fetchRaw<any>('/quality/incidents?' + qs);
    },
    getIncident: (id: number | string) => fetchRaw<any>('/quality/incidents/' + id),
    updateIncidentStatus: (id: number | string, p: Record<string, any>) =>
      sendJson<any>('/quality/incidents/' + id + '/status', 'PATCH', p),
    submitInvestigation: (id: number | string, p: Record<string, any>) =>
      sendJson<any>('/quality/incidents/' + id + '/investigation', 'PATCH', p),
    logInfection: (p: Record<string, any>) => sendJson<any>('/quality/infection-control', 'POST', p),
    listInfections: (params?: { ward?: string; event_type?: string }) => {
      const qs = new URLSearchParams();
      if (params?.ward)       qs.set('ward', params.ward);
      if (params?.event_type) qs.set('event_type', params.event_type);
      return fetchRaw<any>('/quality/infection-control?' + qs);
    },
    infectionStats: () => fetchRaw<any>('/quality/infection-control/stats'),
    submitHefamaa: (p: Record<string, any>) => sendJson<any>('/quality/hefamaa', 'POST', p),
    listHefamaa: (department?: string) => {
      const qs = department ? '?department=' + encodeURIComponent(department) : '';
      return fetchRaw<any>('/quality/hefamaa' + qs);
    },
    getHefamaa: (id: number | string) => fetchRaw<any>('/quality/hefamaa/' + id),
    stats: () => fetchRaw<any>('/quality/stats'),
    /** Compliance page: score and what pulls it down, HEFAMAA, audits (services/quality_hub.compliance). */
    complianceOverview: () => fetchRaw<any>('/quality/compliance-overview'),
    /** Pharmacy QC page: expiry, batches missing facts, medication incidents (quality_hub.pharmacy_qc). */
    pharmacyQc: () => fetchRaw<any>('/quality/pharmacy-qc'),
  },
  // ── Phase 7 — HR Shifts & Leave ───────────────────────────────────────────
  hr: {
    // Consolidated here to avoid duplicate key override — see `pharmacy`/`lab` for the same pattern
    summary: (periods: number = 3) => fetchRaw<HrSummaryResponse>(`/hr/analytics/summary?periods=${periods}`),
    createShift: (p: Record<string, any>) => sendJson<any>('/hr/shifts', 'POST', p),
    listShifts: (params?: { staff_id?: string; department?: string; shift_date?: string; week_start?: string; status?: string }) => {
      const qs = new URLSearchParams();
      if (params?.staff_id)   qs.set('staff_id', params.staff_id);
      if (params?.department) qs.set('department', params.department);
      if (params?.shift_date) qs.set('shift_date', params.shift_date);
      if (params?.week_start) qs.set('week_start', params.week_start);
      if (params?.status)     qs.set('status', params.status);
      return fetchRaw<any>('/hr/shifts?' + qs);
    },
    updateShift: (id: number | string, p: Record<string, any>) =>
      sendJson<any>('/hr/shifts/' + id, 'PATCH', p),
    deleteShift: (id: number | string) =>
      sendJson<any>('/hr/shifts/' + id, 'DELETE', {}),
    submitLeave: (p: Record<string, any>) => sendJson<any>('/hr/leave', 'POST', p),
    listLeave: (params?: { staff_id?: string; status?: string; leave_type?: string }) => {
      const qs = new URLSearchParams();
      if (params?.staff_id)   qs.set('staff_id', params.staff_id);
      if (params?.status)     qs.set('status', params.status);
      if (params?.leave_type) qs.set('leave_type', params.leave_type);
      return fetchRaw<any>('/hr/leave?' + qs);
    },
    getLeave: (id: number | string) => fetchRaw<any>('/hr/leave/' + id),
    updateLeaveStatus: (id: number | string, p: Record<string, any>) =>
      sendJson<any>('/hr/leave/' + id + '/status', 'PATCH', p),
    createPayroll: (p: Record<string, any>) => sendJson<any>('/hr/payroll', 'POST', p),
    listPayroll: (params?: { staff_id?: string; status?: string }) => {
      const qs = new URLSearchParams();
      if (params?.staff_id) qs.set('staff_id', params.staff_id);
      if (params?.status)   qs.set('status', params.status);
      return fetchRaw<any>('/hr/payroll?' + qs);
    },
    payrollSummary: (staffId: string) => fetchRaw<any>('/hr/payroll/' + staffId + '/summary'),
    stats: () => fetchRaw<any>('/hr/stats'),
  },
  admin: {
    feeSchedule: {
      list: (category?: string, activeOnly = true) => {
        const qs = new URLSearchParams();
        if (category) qs.set('category', category);
        qs.set('active_only', String(activeOnly));
        return fetchRaw<any>('/admin/fee-schedule?' + qs);
      },
      create: (p: Record<string, any>) => sendJson<any>('/admin/fee-schedule', 'POST', p),
      update: (id: number | string, p: Record<string, any>) =>
        sendJson<any>('/admin/fee-schedule/' + id, 'PATCH', p),
      delete: (id: number | string) => sendJson<any>('/admin/fee-schedule/' + id, 'DELETE', {}),
    },
  },
  // ── Phase 8 — Hospital Reports ────────────────────────────────────────────
  hospitalReports: {
    diseaseBurden: (params?: { start_date?: string; end_date?: string; limit?: number }) => {
      const qs = new URLSearchParams();
      if (params?.start_date) qs.set('start_date', params.start_date);
      if (params?.end_date)   qs.set('end_date', params.end_date);
      if (params?.limit)      qs.set('limit', String(params.limit));
      return fetchRaw<any>('/hospital-reports/disease-burden?' + qs);
    },
    hmis: (month?: string) => {
      const qs = month ? '?month=' + encodeURIComponent(month) : '';
      return fetchRaw<any>('/hospital-reports/hmis' + qs);
    },
    nhiaExport: (params?: { start_date?: string; end_date?: string; hmo_id?: number; limit?: number }) => {
      const qs = new URLSearchParams();
      if (params?.start_date) qs.set('start_date', params.start_date);
      if (params?.end_date)   qs.set('end_date', params.end_date);
      if (params?.hmo_id)     qs.set('hmo_id', String(params.hmo_id));
      if (params?.limit)      qs.set('limit', String(params.limit));
      return fetchRaw<any>('/hospital-reports/nhia-export?' + qs);
    },
    financialSummary: (params?: { start_date?: string; end_date?: string }) => {
      const qs = new URLSearchParams();
      if (params?.start_date) qs.set('start_date', params.start_date);
      if (params?.end_date)   qs.set('end_date', params.end_date);
      return fetchRaw<any>('/hospital-reports/financial-summary?' + qs);
    },
    patientDemographics: () => fetchRaw<any>('/hospital-reports/patient-demographics'),
    bedOccupancy: () => fetchRaw<any>('/hospital-reports/bed-occupancy'),
  },
  // ── Phase 8 — Payment Gateway ─────────────────────────────────────────────
  payments: {
    initiate: (p: Record<string, any>) => sendJson<any>('/payments/initiate', 'POST', p),
    verify: (reference: string) => fetchRaw<any>('/payments/' + reference),
    list: (params?: { patient_id?: number; encounter_id?: number; status?: string; gateway?: string; limit?: number }) => {
      const qs = new URLSearchParams();
      if (params?.patient_id)   qs.set('patient_id',   String(params.patient_id));
      if (params?.encounter_id) qs.set('encounter_id', String(params.encounter_id));
      if (params?.status)       qs.set('status',       params.status);
      if (params?.gateway)      qs.set('gateway',      params.gateway);
      if (params?.limit)        qs.set('limit',        String(params.limit));
      return fetchRaw<any>('/payments?' + qs);
    },
  },
  // ── Phase 8 — Integrations (PACS + Kiosk) ────────────────────────────────
  integrations: {
    pacs: {
      push: (p: Record<string, any>) => sendJson<any>('/integrations/pacs/study', 'POST', p),
      get: (accession: string) => fetchRaw<any>('/integrations/pacs/study/' + accession),
      list: (params?: { patient_id?: number; status?: string; limit?: number }) => {
        const qs = new URLSearchParams();
        if (params?.patient_id) qs.set('patient_id', String(params.patient_id));
        if (params?.status)     qs.set('status',     params.status);
        if (params?.limit)      qs.set('limit',      String(params.limit));
        return fetchRaw<any>('/integrations/pacs/studies?' + qs);
      },
    },
    kiosk: {
      checkin: (p: Record<string, any>) => sendJson<any>('/integrations/kiosk/checkin', 'POST', p),
      queueStatus: () => fetchRaw<any>('/integrations/kiosk/queue-status'),
      listCheckins: (date?: string) => {
        const qs = date ? '?checkin_date=' + encodeURIComponent(date) : '';
        return fetchRaw<any>('/integrations/kiosk/checkins' + qs);
      },
    },
  },
  // ── Phase 9 — Specialist Clinic Templates ────────────────────────────────
  specialist: {
    listTemplates: (specialty?: string, activeOnly = true) => {
      const qs = new URLSearchParams();
      if (specialty) qs.set('specialty', specialty);
      qs.set('active_only', String(activeOnly));
      return fetchRaw<any>('/specialist/templates?' + qs);
    },
    getTemplate: (id: number | string) => fetchRaw<any>('/specialist/templates/' + id),
    createTemplate: (p: Record<string, any>) => sendJson<any>('/specialist/templates', 'POST', p),
    updateTemplate: (id: number | string, p: Record<string, any>) =>
      sendJson<any>('/specialist/templates/' + id, 'PATCH', p),
    deleteTemplate: (id: number | string) =>
      sendJson<any>('/specialist/templates/' + id, 'DELETE', {}),
    seedTemplates: () => sendJson<any>('/specialist/seed', 'POST', {}),
    submitNote: (p: Record<string, any>) => sendJson<any>('/specialist/notes', 'POST', p),
    listNotes: (params?: { patient_id?: number; encounter_id?: number; specialty?: string; limit?: number }) => {
      const qs = new URLSearchParams();
      if (params?.patient_id)   qs.set('patient_id',   String(params.patient_id));
      if (params?.encounter_id) qs.set('encounter_id', String(params.encounter_id));
      if (params?.specialty)    qs.set('specialty',    params.specialty);
      if (params?.limit)        qs.set('limit',        String(params.limit));
      return fetchRaw<any>('/specialist/notes?' + qs);
    },
    getNote:   (id: number | string) => fetchRaw<any>('/specialist/notes/' + id),
    amendNote: (id: number | string, p: Record<string, any>) =>
      sendJson<any>('/specialist/notes/' + id, 'PATCH', p),
  },
  medicalRecords: {
    listDocuments: (patientId?: number | string) => {
      const qs = patientId ? '?patient_id=' + patientId : '';
      return fetchRaw<any>('/documents' + qs);
    },
    createDocument: (p: Record<string, any>) => sendJson<any>('/documents', 'POST', p),
    uploadFile: async (documentId: string, file: File) => {
      const token = authClient.getAccessToken();
      const form = new FormData();
      form.append('file', file);
      const res = await fetch(apiUrl(`/documents/${documentId}/upload-version`), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      if (!res.ok) throw new Error('Upload failed');
      return res.json();
    },
    generateReferral: (encounterId: number | string, p: Record<string, any>) =>
      sendJson<any>('/documents/referral-letter/' + encounterId, 'POST', p),
  },
  // ── Staff Workspace (backend/src/routers/staff_workspace.py) — every member of staff ──
  workspace: {
    day: () => fetchRaw<any>("/workspace/day"),
    operational: () => fetchRaw<any>("/workspace/operational"),
    take: (rule: string, id: string, assign_to?: string) => sendJson<any>("/workspace/operational/take", "POST", { rule, id, assign_to }),
    time: () => fetchRaw<any>("/workspace/time"),
    clockIn: (payload: Record<string, any> = {}) => sendJson<any>("/workspace/time/start", "POST", payload),
    takeBreak: () => sendJson<any>("/workspace/time/break", "POST", {}),
    resume: () => sendJson<any>("/workspace/time/resume", "POST", {}),
    clockOut: (payload: Record<string, any> = {}) => sendJson<any>("/workspace/time/stop", "POST", payload),
    clockCancel: () => sendJson<any>("/workspace/time/cancel", "POST", {}),
    tasks: () => fetchRaw<any>("/workspace/tasks"),
    createTask: (payload: Record<string, any>) => sendJson<any>("/workspace/tasks", "POST", payload),
    task: (id: string) => fetchRaw<any>(`/workspace/tasks/${id}`),
    updateTask: (id: string, payload: Record<string, any>) => sendJson<any>(`/workspace/tasks/${id}`, "PATCH", payload),
    setStatus: (id: string, status: string, extra: Record<string, any> = {}) =>
      sendJson<any>(`/workspace/tasks/${id}/status`, "POST", { status, ...extra }),
    comment: (id: string, body: string) => sendJson<any>(`/workspace/tasks/${id}/comment`, "POST", { body }),
    requests: () => fetchRaw<any>("/workspace/requests"),
    createRequest: (payload: Record<string, any>) => sendJson<any>("/workspace/requests", "POST", payload),
    request: (id: string) => fetchRaw<any>(`/workspace/requests/${id}`),
    requestAction: (id: string, action: string, payload: Record<string, any> = {}) =>
      sendJson<any>(`/workspace/requests/${id}/${action}`, "POST", payload),
    inbox: (filter = "all") => fetchRaw<any>(`/workspace/inbox?filter=${filter}`),
    markRead: (ids?: number[]) => sendJson<any>("/workspace/inbox/read", "POST", { ids }),
    conversations: () => fetchRaw<any>("/workspace/conversations"),
    messages: (other: string) => fetchRaw<any>(`/workspace/messages/${other}`),
    send: (other: string, body: string) => sendJson<any>(`/workspace/messages/${other}`, "POST", { body }),
    team: () => fetchRaw<any>("/workspace/team"),
    progress: (range = "week") => fetchRaw<any>(`/workspace/progress?range=${range}`),
    journal: (range = "today") => fetchRaw<any[]>(`/workspace/journal?range=${range}`),
    parse: (text: string) => sendJson<any>("/workspace/parse", "POST", { text }),
    quick: (text: string) => sendJson<any>("/workspace/quick", "POST", { text }),
    escalationPolicy: () => fetchRaw<Record<string, { after_hours: number; to: string }[]>>("/workspace/escalation-policy"),
    saveEscalationPolicy: (subject: string, priority: string, steps: { after_hours: number; to: string }[]) =>
      sendJson<any>("/workspace/escalation-policy", "PUT", { subject, priority, steps }),
    runEscalations: () => sendJson<any>("/workspace/escalations/run", "POST", {}),
    prefs: () => fetchRaw<any>("/workspace/prefs"),
    savePrefs: (payload: Record<string, any>) => sendJson<any>("/workspace/prefs", "PUT", payload),
    leave: () => fetchRaw<any>("/workspace/leave"),
    requestLeave: (payload: Record<string, any>) => sendJson<any>("/workspace/leave", "POST", payload),
  },
  // ── HR hub (backend/src/routers/hr_hub.py) — live overview, directory, timesheets, payroll run ──
  hrHub: {
    overview: (week?: string) => fetchRaw<any>(`/hr/overview${week ? `?week=${week}` : ""}`),
    people: () => fetchRaw<any>("/hr/people"),
    person: (key: string) => fetchRaw<any>(`/hr/people/${encodeURIComponent(key)}`),
    addPerson: (payload: Record<string, any>) => sendJson<any>("/hr/people", "POST", payload),
    updatePerson: (key: string, payload: Record<string, any>) => sendJson<any>(`/hr/people/${encodeURIComponent(key)}`, "PATCH", payload),
    timesheets: (week?: string, person?: string) =>
      fetchRaw<any>(`/hr/timesheets?${new URLSearchParams({ ...(week ? { week } : {}), ...(person ? { person } : {}) }).toString()}`),
    timesheetsCsvUrl: (week?: string) => apiUrl(`/hr/timesheets.csv${week ? `?week=${week}` : ""}`),
    addEntry: (payload: Record<string, any>) => sendJson<any>("/hr/timesheets", "POST", payload),
    review: (id: string, action: string, payload: Record<string, any> = {}) => sendJson<any>(`/hr/timesheets/${id}/${action}`, "POST", payload),
    approveWeek: (payload: Record<string, any>) => sendJson<any>("/hr/timesheets/approve-week", "POST", payload),
    payrollRun: (period?: string) => fetchRaw<any>(`/hr/payroll-run${period ? `?period=${period}` : ""}`),
    preparePayroll: (period?: string) => sendJson<any>("/hr/payroll-run/prepare", "POST", { period }),
    payrollBulk: (action: "approve" | "pay", payload: Record<string, any>) => sendJson<any>(`/hr/payroll-run/${action}`, "POST", payload),
    updatePayroll: (id: string, payload: Record<string, any>) => sendJson<any>(`/hr/payroll-records/${id}`, "PATCH", payload),
    payrollAction: (id: string, action: "approve" | "pay" | "delete", payload: Record<string, any> = {}) =>
      sendJson<any>(`/hr/payroll-records/${id}/${action}`, "POST", payload),
    peopleSummary: () => fetchRaw<any>("/hr/people-summary"),
  },
};
