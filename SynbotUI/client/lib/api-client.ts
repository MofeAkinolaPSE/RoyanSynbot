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

export type ApiErrorKind = "session" | "permission" | "validation" | "not_found" | "transport" | "server" | "unknown";

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
  const message =
    (typeof detailPayload === "string" ? detailPayload : detailPayload?.message) ||
    res.statusText ||
    fallbackMessage;
  const code = typeof detailPayload === "object" ? detailPayload?.code : undefined;

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
  method: "POST" | "PUT" | "PATCH",
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
    approve: (id: string, payload: { department_id_override?: number; approval_reason: string; attestation_text: string }) =>
      sendJson<{ status: string; staff_id: string; user_id: string }>(`/staff/registrations/${encodeURIComponent(id)}/approve`, "POST", payload),
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
    create: (payload: {
      email: string;
      password: string;
      roles: string[];
      approval_reason: string;
      attestation_text: string;
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
    setRoles: (userId: string, roles: string[]) =>
      sendJson<any>(`/users/${userId}/roles`, "PATCH", { roles }),
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
    list: (month?: string) => {
      const q = month ? `?month=${month}` : "";
      return fetchRaw<{ events: any[] }>(`/calendar/events${q}`);
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
    list: (status?: string) => {
      const q = status ? `?status=${status}` : "";
      return fetchRaw<{ tasks: any[] }>(`/tasks${q}`);
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
  compliance: {
    status: () => fetchRaw<any>("/compliance/status"),
    audits: (status?: string) => {
      const q = status ? `?status=${status}` : "";
      return fetchRaw<{ data: any[] }>(`/compliance/audits${q}`);
    },
    startAudit: (auditId: string) =>
      sendJson<any>(`/compliance/audits/${auditId}/start`, "POST", {}),
    completeAudit: (auditId: string, payload: { findings?: string; recommendations?: string; score?: number }) =>
      sendJson<any>(`/compliance/audits/${auditId}/complete`, "POST", payload),
    generateAuditReport: (auditId: string, payload: {
      auditor_name?: string;
      summary?: string;
      findings?: string[];
      observations?: string[];
      recommendations?: string[];
      score?: number;
    }) => sendJson<any>(`/compliance/audits/${auditId}/generate-report`, "POST", payload),
    deviations: (status?: string) => {
      const q = status ? `?status=${status}` : "";
      return fetchRaw<{ data: any[] }>(`/compliance/deviations${q}`);
    },
    createDeviation: (payload: {
      title: string;
      severity: string;
      category: string;
      description: string;
      detected_by: string;
      product_batch?: string;
      sop_reference?: string;
    }) => sendJson<any>("/compliance/deviations", "POST", payload),
    updateDeviation: (devId: string, payload: Record<string, any>) =>
      sendJson<any>(`/compliance/deviations/${devId}`, "PUT", payload),
    generateDeviationReport: (devId: string) =>
      sendJson<any>(`/compliance/deviations/${devId}/generate-report`, "POST", {}),
    equipment: () => fetchRaw<{ data: any[] }>("/compliance/equipment"),
    maintenance: (filter?: "overdue" | "upcoming" | "all") => {
      const q = filter && filter !== "all" ? `?filter=${filter}` : "";
      return fetchRaw<{ data: any[] }>(`/compliance/maintenance${q}`);
    },
    completeMaintenance: (maintenanceId: string, payload: {
      completed_by: string;
      notes?: string;
      next_due_date?: string;
    }) => sendJson<any>(`/compliance/maintenance/${maintenanceId}/complete`, "POST", payload),
    generateMaintenanceCertificate: (maintenanceId: string, payload: {
      performed_by: string;
      maintenance_type?: string;
      completion_notes?: string;
      next_maintenance_date?: string;
    }) => sendJson<any>(`/compliance/maintenance/${maintenanceId}/generate-certificate`, "POST", payload),
    recalls: (status?: string) => {
      const q = status ? `?status=${status}` : "";
      return fetchRaw<{ data: any[] }>(`/compliance/recalls${q}`);
    },
    initiateRecall: (payload: {
      product_name: string;
      batch_number: string;
      recall_reason: string;
      severity: string;
      nafdac_notified?: boolean;
    }) => sendJson<any>("/compliance/recalls", "POST", payload),
    updateRecall: (recallId: string, payload: Record<string, any>) =>
      sendJson<any>(`/compliance/recalls/${recallId}`, "PUT", payload),
    generateRecallDocuments: (recallId: string) =>
      sendJson<any>(`/compliance/recalls/${recallId}/generate-documents`, "POST", {}),
    sopList: (category?: string) => {
      const q = category ? `?category=${category}` : "";
      return fetchRaw<{ data: any[] }>(`/compliance/sop${q}`);
    },
    ingestSopDocx: (formData: FormData) =>
      sendFormData<any>("/compliance/sop/ingest-docx", "POST", formData),
    documentArchive: (docType?: string) => {
      const q = docType ? `?doc_type=${docType}` : "";
      return fetchRaw<{ data: any[] }>(`/documents/archive${q}`);
    },
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

  frontdesk: {
    registerWalkIn: (payload: {
      customer_name: string;
      company_name?: string;
      contact_phone?: string;
      email?: string;
      has_appointment?: boolean;
      purpose: string;
      products_requested?: string[];
      notes?: string;
    }) => sendJson<any>("/frontdesk/walk-ins", "POST", payload),

    listWalkIns: (date?: string, status?: string) => {
      const q = new URLSearchParams();
      if (date) q.set("date", date);
      if (status) q.set("status", status);
      return fetchRaw<any>(`/frontdesk/walk-ins${q.toString() ? `?${q.toString()}` : ""}`);
    },

    getWalkIn: (id: string) => fetchRaw<any>(`/frontdesk/walk-ins/${id}`),

    createInvoice: (walkInId: string, payload: {
      items: { product: string; quantity: number; unit_price: number }[];
      payment_method?: string;
      notes?: string;
    }) => sendJson<any>(`/frontdesk/walk-ins/${walkInId}/invoice`, "POST", payload),

    submitQc: (invoiceId: string, payload: {
      passed: boolean;
      inspector_name: string;
      notes?: string;
      batch_numbers?: string[];
    }) => sendJson<any>(`/frontdesk/invoices/${invoiceId}/qc`, "POST", payload),

    financeApproval: (invoiceId: string, payload: {
      approved: boolean;
      approver_name: string;
      reason?: string;
    }) => sendJson<any>(`/frontdesk/invoices/${invoiceId}/finance`, "POST", payload),

    notifyExecutive: (invoiceId: string, message?: string) =>
      sendJson<any>(`/frontdesk/invoices/${invoiceId}/notify`, "POST", { message }),

    // --- New endpoints ---

    searchClients: (q: string, limit?: number) => {
      const params = new URLSearchParams({ q });
      if (limit) params.set("limit", String(limit));
      return fetchRaw<any>(`/frontdesk/clients/search?${params.toString()}`);
    },

    clientHistory: (walkInId: string) =>
      fetchRaw<any>(`/frontdesk/clients/${walkInId}/history`),

    listInvoices: (params?: {
      status?: string;
      date_from?: string;
      date_to?: string;
      q?: string;
      limit?: number;
    }) => {
      const qs = new URLSearchParams();
      if (params?.status)    qs.set("status", params.status);
      if (params?.date_from) qs.set("date_from", params.date_from);
      if (params?.date_to)   qs.set("date_to", params.date_to);
      if (params?.q)         qs.set("q", params.q);
      if (params?.limit)     qs.set("limit", String(params.limit));
      return fetchRaw<any>(`/frontdesk/invoices${qs.toString() ? `?${qs.toString()}` : ""}`);
    },

    getInvoice: (invoiceId: string) =>
      fetchRaw<any>(`/frontdesk/invoices/${invoiceId}`),

    stockCheck: (products: string[]) => {
      const qs = new URLSearchParams({ products: products.join(",") });
      return fetchRaw<any>(`/frontdesk/stock-check?${qs.toString()}`);
    },

    dailyReport: (date?: string) => {
      const qs = new URLSearchParams();
      if (date) qs.set("date", date);
      return fetchRaw<any>(`/frontdesk/reports/daily${qs.toString() ? `?${qs.toString()}` : ""}`);
    },

    cancelWalkIn: (id: string, reason?: string) =>
      sendJson<any>(`/frontdesk/walk-ins/${id}/cancel`, "POST", reason ? { reason } : {}),
  },

  // -------------------------------------------------------------------------
  // Quality Control
  // -------------------------------------------------------------------------
  qc: {
    /** Unified KPI dashboard: expiring count, open deviations, temp alerts, NAFDAC pending, recalls */
    dashboard: () =>
      fetchRaw<any>("/qc/dashboard"),

    /** Expiring stock grouped into expired/critical(≤30d)/high(≤60d)/medium(≤90d) buckets */
    expiryAlerts: (days?: number) => {
      const qs = new URLSearchParams();
      if (days) qs.set("days", String(days));
      return fetchRaw<any>(`/qc/expiry-alerts${qs.toString() ? `?${qs}` : ""}`);
    },

    // --- Temperature logs ---
    logTemperature: (payload: {
      location: string;
      reading_celsius: number;
      min_threshold?: number;
      max_threshold?: number;
      log_session?: "morning" | "midday" | "evening" | "ad_hoc";
      logged_by: string;
      logged_at?: string;
      equipment_id?: string;
      notes?: string;
    }) => sendJson<any>("/qc/temperature-logs", "POST", payload),

    listTemperatureLogs: (params?: {
      location?: string;
      date_from?: string;
      date_to?: string;
      deviations_only?: boolean;
      limit?: number;
    }) => {
      const qs = new URLSearchParams();
      if (params?.location)        qs.set("location", params.location);
      if (params?.date_from)       qs.set("date_from", params.date_from);
      if (params?.date_to)         qs.set("date_to", params.date_to);
      if (params?.deviations_only) qs.set("deviations_only", "true");
      if (params?.limit)           qs.set("limit", String(params.limit));
      return fetchRaw<any>(`/qc/temperature-logs${qs.toString() ? `?${qs}` : ""}`);
    },

    activeDeviations: () =>
      fetchRaw<any>("/qc/temperature-logs/deviations"),

    escalateDeviation: (logId: string, payload: { escalated_to: string; escalation_notes?: string }) =>
      sendJson<any>(`/qc/temperature-logs/${logId}/escalate`, "POST", payload),

    // --- CAPA Deviation reports ---
    createDeviation: (payload: {
      classification?: "minor" | "major" | "critical";
      trigger_type: string;
      trigger_ref?: string;
      observation: string;
      impact_assessment?: string;
      recommendations?: string;
      responsible_department: string;
      responsible_person?: string;
      capa_actions?: object[];
    }) => sendJson<any>("/qc/deviations", "POST", payload),

    listDeviations: (params?: {
      status?: string;
      classification?: string;
      department?: string;
      limit?: number;
    }) => {
      const qs = new URLSearchParams();
      if (params?.status)         qs.set("status", params.status);
      if (params?.classification) qs.set("classification", params.classification);
      if (params?.department)     qs.set("department", params.department);
      if (params?.limit)          qs.set("limit", String(params.limit));
      return fetchRaw<any>(`/qc/deviations${qs.toString() ? `?${qs}` : ""}`);
    },

    updateDeviation: (id: string, payload: {
      status?: string;
      impact_assessment?: string;
      recommendations?: string;
      responsible_person?: string;
      capa_actions?: object[];
    }) => sendJson<any>(`/qc/deviations/${id}`, "PATCH", payload),

    closeDeviation: (id: string, payload: { resolution: string; capa_actions?: object[] }) =>
      sendJson<any>(`/qc/deviations/${id}/close`, "POST", payload),

    // --- NAFDAC batch registry ---
    registerBatch: (payload: {
      batch_number: string;
      product_name: string;
      nafdac_reg_number?: string;
      supplier?: string;
      valid_from?: string;
      valid_to?: string;
      certificate_ref?: string;
      notes?: string;
    }) => sendJson<any>("/qc/nafdac/batches", "POST", payload),

    listBatches: (params?: {
      status?: string;
      product?: string;
      blocked?: boolean;
      limit?: number;
    }) => {
      const qs = new URLSearchParams();
      if (params?.status)            qs.set("status", params.status);
      if (params?.product)           qs.set("product", params.product);
      if (params?.blocked !== undefined) qs.set("blocked", String(params.blocked));
      if (params?.limit)             qs.set("limit", String(params.limit));
      return fetchRaw<any>(`/qc/nafdac/batches${qs.toString() ? `?${qs}` : ""}`);
    },

    approveBatch: (id: string, payload?: {
      valid_from?: string;
      valid_to?: string;
      certificate_ref?: string;
      nafdac_reg_number?: string;
      notes?: string;
    }) => sendJson<any>(`/qc/nafdac/batches/${id}/approve`, "PATCH", payload ?? {}),

    rejectBatch: (id: string, payload: { rejection_reason: string; notes?: string }) =>
      sendJson<any>(`/qc/nafdac/batches/${id}/reject`, "PATCH", payload),

    // --- Product recalls ---
    initiateRecall: (payload: {
      batch_number: string;
      product_name: string;
      recall_reason: string;
      scope?: "voluntary" | "mandatory";
      regulatory_authority?: string;
      distribution_data?: object[];
    }) => sendJson<any>("/qc/recalls", "POST", payload),

    listRecalls: (params?: { status?: string; product?: string; limit?: number }) => {
      const qs = new URLSearchParams();
      if (params?.status)  qs.set("status", params.status);
      if (params?.product) qs.set("product", params.product);
      if (params?.limit)   qs.set("limit", String(params.limit));
      return fetchRaw<any>(`/qc/recalls${qs.toString() ? `?${qs}` : ""}`);
    },

    updateRecallStatus: (id: string, payload: {
      status: "initiated" | "in_progress" | "completed" | "closed";
      distribution_data?: object[];
      notes?: string;
    }) => sendJson<any>(`/qc/recalls/${id}/status`, "PATCH", payload),
  },

  logistics: {
    createRider: (payload: { name: string; phone?: string; vehicle?: string }) =>
      sendJson<any>("/logistics/riders", "POST", payload),

    createDelivery: (payload: {
      destination: string;
      recipient_name?: string;
      recipient_phone?: string;
      dest_lat?: number;
      dest_lng?: number;
    }) => sendJson<any>("/logistics/deliveries", "POST", payload),

    assignRoutes: () => sendJson<any>("/logistics/assign", "POST", {}),

    getRiderRoute: (riderId: string) =>
      fetchRaw<any>(`/logistics/riders/${encodeURIComponent(riderId)}/route`),

    updateDeliveryStatus: (deliveryId: string, status: string) =>
      sendJson<any>(`/logistics/deliveries/${encodeURIComponent(deliveryId)}/status`, "POST", { status }),

    computeRoute: (payload: { origin: string; destinations: string[]; optimize?: boolean }) =>
      sendJson<any>("/logistics/compute-route", "POST", payload),

    // ---- Live tracking (Migration 084) ----

    /** Start a delivery → mints tracking_token, returns PWA URL */
    startDelivery: (deliveryId: string) =>
      sendJson<any>(`/logistics/deliveries/${encodeURIComponent(deliveryId)}/start`, "POST", {}),

    /** Rider PWA: resolve delivery info by token (no JWT) */
    getDeliveryByToken: (token: string) =>
      fetchRaw<any>(`/logistics/track/${encodeURIComponent(token)}`),

    /** Latest rider positions snapshot (dashboard poll fallback) */
    livePositions: () =>
      fetchRaw<any>("/logistics/live-positions"),

    /** All in-transit/assigned deliveries with rider location */
    activeDeliveries: () =>
      fetchRaw<any>("/logistics/active-deliveries"),

    /** GPS ping history / route replay for a delivery */
    deliveryPings: (deliveryId: string) =>
      fetchRaw<any>(`/logistics/deliveries/${encodeURIComponent(deliveryId)}/pings`),
  },

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

    /** URL for downloading a report as a Word document (.docx). Requires auth header. */
    generateDocxUrl: () => "/reports/generate/docx",

    /** Run the agent and download the result as a .docx — returns URL for fetch-with-auth. */
    generateDocx: (payload: { report_type?: string; intent_text?: string }) =>
      sendJson<Blob>("/reports/generate/docx", "POST", payload),

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
      list: (params?: { status?: string; department?: string; doctor?: string }) => {
        const qs = new URLSearchParams();
        if (params?.status)     qs.set('status', params.status);
        if (params?.department) qs.set('department', params.department);
        if (params?.doctor)     qs.set('doctor', params.doctor);
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
      listNotes:    (id: string) => fetchRaw<any>('/queue/encounters/' + id + '/notes'),
      addNote:      (id: string, p: Record<string, any>) => sendJson<any>('/queue/encounters/' + id + '/notes', 'POST', p),
    },
    display: {
      getQueue: (department?: string) =>
        fetchRaw<any>('/integrations/queue/display' + (department ? '?department=' + encodeURIComponent(department) : '')),
    },
    wards: {
      list: () => fetchRaw<any>('/wards'),
      create: (p: Record<string, any>) => sendJson<any>('/wards', 'POST', p),
      beds: (wardId: string) => fetchRaw<any>('/wards/' + wardId + '/beds'),
      addBed: (wardId: string, p: Record<string, any>) => sendJson<any>('/wards/' + wardId + '/beds', 'POST', p),
      admitBed: (wardId: string, bedId: string, p: Record<string, any>) =>
        sendJson<any>('/wards/' + wardId + '/beds/' + bedId + '/admit', 'POST', p),
      freeBed: (wardId: string, bedId: string) =>
        sendJson<any>('/wards/' + wardId + '/beds/' + bedId + '/discharge', 'POST', {}),
    },
    billing: {
      createBill: (p: Record<string, any>) => sendJson<any>('/billing_hospital/bills', 'POST', p),
      createBillFromEncounter: (p: Record<string, any>) => sendJson<any>('/billing_hospital/bills/from-encounter', 'POST', p),
      listBills: (params?: { status?: string; patient_id?: number }) => {
        const qs = new URLSearchParams();
        if (params?.status)     qs.set('status', params.status);
        if (params?.patient_id) qs.set('patient_id', String(params.patient_id));
        return fetchRaw<any>('/billing_hospital/bills' + (qs.toString() ? '?' + qs : ''));
      },
      getBill: (id: string) => fetchRaw<any>('/billing_hospital/bills/' + id),
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
    },
    appointments: {
      createSlot: (p: Record<string, any>) => sendJson<any>('/appointments/slots', 'POST', {
        ...p,
        doctor_name: p.doctor_name ?? p.provider_name,
        slot_date: p.slot_date ?? p.date,
        slot_time: p.slot_time ?? p.start_time,
        max_patients: p.max_patients ?? p.capacity,
        department: p.department === 'General OPD' ? 'OPD' : p.department,
      }),
      listSlots: (params?: { date?: string; provider?: string }) => {
        const qs = new URLSearchParams();
        if (params?.date)     qs.set('slot_date', params.date);
        if (params?.provider) qs.set('doctor_name', params.provider);
        return fetchRaw<any>('/appointments/slots' + (qs.toString() ? '?' + qs : ''));
      },
      deleteSlot: (id: string) => sendDelete<any>('/appointments/slots/' + id),
      book: (p: Record<string, any>) => sendJson<any>('/appointments/book', 'POST', p),
      list: (params?: { date?: string; status?: string }) => {
        const qs = new URLSearchParams();
        if (params?.date)   qs.set('date',   params.date);
        if (params?.status) qs.set('status', params.status === 'scheduled' ? 'booked' : params.status);
        return fetchRaw<any>('/appointments' + (qs.toString() ? '?' + qs : ''));
      },
      arrive:   (id: string) => sendJson<any>('/appointments/' + id + '/arrive',   'PATCH', {}),
      complete: (id: string) => sendJson<any>('/appointments/' + id + '/complete', 'PATCH', {}),
      cancel:   (id: string, p: Record<string, any>) => sendJson<any>('/appointments/' + id + '/cancel', 'PATCH', p),
      // Scheduling Control Center additions
      calendar: (params?: { date_from?: string; date_to?: string; doctor_name?: string; department?: string }) => {
        const qs = new URLSearchParams();
        if (params?.date_from)   qs.set('date_from',   params.date_from);
        if (params?.date_to)     qs.set('date_to',     params.date_to);
        if (params?.doctor_name) qs.set('doctor_name', params.doctor_name);
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
      hmos: () => fetchRaw<any>('/coverage/hmos'),
      createHmo: (p: Record<string, any>) => sendJson<any>('/coverage/hmos', 'POST', p),
      services: (category?: string) => fetchRaw<any>('/coverage/services' + (category ? '?category=' + encodeURIComponent(category) : '')),
      createService: (p: Record<string, any>) => sendJson<any>('/coverage/services', 'POST', p),
      listRules: (hmo_id?: string) => fetchRaw<any>('/coverage/rules' + (hmo_id ? '?hmo_id=' + encodeURIComponent(hmo_id) : '')),
      createRule: (p: Record<string, any>) => sendJson<any>('/coverage/rules', 'POST', p),
      createPatientInsurance: (p: Record<string, any>) => sendJson<any>('/coverage/patient-insurance', 'POST', p),
      requestAuthorization: (p: Record<string, any>) => sendJson<any>('/coverage/authorizations', 'POST', p),
      listAuthorizations: (status?: string) => fetchRaw<any>('/coverage/authorizations' + (status ? '?status=' + encodeURIComponent(status) : '')),
      resolveAuthorization: (id: number, p: Record<string, any>) => sendJson<any>('/coverage/authorizations/' + id, 'PATCH', p),
    },
    hope: {
      sync: (entity: 'patients' | 'appointments' | 'admissions' | 'lab' | 'pharmacy' | 'billing', limit = 200) =>
        sendJson<any>('/hope/sync/' + entity + '?limit=' + String(limit), 'POST', {}),
    },
    clinical: {
      searchIcd10: (q: string) => fetchRaw<any>('/clinical/icd10?q=' + encodeURIComponent(q)),
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
      createRx: (p: Record<string, any>) => sendJson<any>('/pharmacy/prescriptions', 'POST', p),
      listRx: (params?: { status?: string; encounter_id?: string }) => {
        const qs = new URLSearchParams();
        if (params?.status)       qs.set('status',       params.status === 'active' ? 'pending' : params.status === 'partial' ? 'partially_dispensed' : params.status);
        if (params?.encounter_id) qs.set('encounter_id', params.encounter_id);
        return fetchRaw<any>('/pharmacy/prescriptions' + (qs.toString() ? '?' + qs : ''));
      },
      getRx: (id: string | number) => fetchRaw<any>('/pharmacy/prescriptions/' + id),
      dispense: (id: string, p: Record<string, any>) => sendJson<any>('/pharmacy/prescriptions/' + id + '/dispense', 'POST',  p),
      cancel:   (id: string, p: Record<string, any>) => sendJson<any>('/pharmacy/prescriptions/' + id + '/cancel',   'POST', p),
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
      // Replenishment
      listReplenishmentRequests: (params?: { ward?: string; status?: string }) => {
        const qs = new URLSearchParams();
        if (params?.ward) qs.set('ward', params.ward);
        if (params?.status) qs.set('status', params.status);
        const q = qs.toString();
        return fetchRaw<any>('/pharmacy/replenishment-requests' + (q ? '?' + q : ''));
      },
      createReplenishmentRequest: (p: Record<string, any>) =>
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
      listOrders: (params?: { status?: string; urgency?: string; patient_id?: number }) => {
        const qs = new URLSearchParams();
        if (params?.status)     qs.set('status',     params.status);
        if (params?.urgency)    qs.set('urgency',    params.urgency);
        if (params?.patient_id) qs.set('patient_id', String(params.patient_id));
        return fetchRaw<any>('/lab/orders' + (qs.toString() ? '?' + qs : ''));
      },
      collect: (id: string | number) => sendJson<any>('/lab/orders/' + id + '/collect', 'POST', {}),
      recordResult: (id: string | number, p: Record<string, any>) => sendJson<any>('/lab/orders/' + id + '/result', 'POST', p),
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
      listOrders: (params?: { status?: string; modality?: string; patient_id?: number; encounter_id?: number; urgency?: string; date?: string }) => {
        const qs = new URLSearchParams();
        if (params?.status) qs.set('status', params.status);
        if (params?.modality) qs.set('modality', params.modality);
        if (params?.patient_id) qs.set('patient_id', String(params.patient_id));
        if (params?.encounter_id) qs.set('encounter_id', String(params.encounter_id));
        if (params?.urgency) qs.set('urgency', params.urgency);
        if (params?.date) qs.set('date', params.date);
        const q = qs.toString();
        return fetchRaw<any>('/radiology/orders' + (q ? '?' + q : ''));
      },
      getOrder: (id: number | string) => fetchRaw<any>('/radiology/orders/' + id),
      submitReport: (id: number | string, p: Record<string, any>) =>
        sendJson<any>('/radiology/orders/' + id + '/report', 'PATCH', p),
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
    listInfections: (params?: { ward?: string; infection_type?: string }) => {
      const qs = new URLSearchParams();
      if (params?.ward)           qs.set('ward', params.ward);
      if (params?.infection_type) qs.set('infection_type', params.infection_type);
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
    listPayroll: (params?: { staff_id?: string; department?: string; payment_status?: string }) => {
      const qs = new URLSearchParams();
      if (params?.staff_id)       qs.set('staff_id', params.staff_id);
      if (params?.department)     qs.set('department', params.department);
      if (params?.payment_status) qs.set('payment_status', params.payment_status);
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
};
