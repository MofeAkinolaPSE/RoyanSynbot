// Lightweight API client for the patient portal.
// Proxied through /api → backend in dev; in prod served via same Nginx.

const BASE = import.meta.env.VITE_API_URL ?? "/api";

function token(): string {
  return sessionStorage.getItem("portal_token") ?? "";
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token() ? { Authorization: `Bearer ${token()}` } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json() as Promise<T>;
}

export const portalApi = {
  // Auth: lookup patient by MRN + phone, return a portal JWT
  login: (mrn: string, phone: string) =>
    req<{ token: string; patient: Record<string, unknown> }>("POST", "/portal/auth", { mrn, phone }),

  // Patient own data
  profile: () => req<Record<string, unknown>>("GET", "/portal/me"),

  appointments: () =>
    req<{ appointments: unknown[] }>("GET", "/portal/appointments"),

  labResults: () =>
    req<{ results: unknown[] }>("GET", "/portal/lab-results"),

  bills: () =>
    req<{ bills: unknown[] }>("GET", "/portal/bills"),

  // New portal features
  prescriptions: () =>
    req<{ prescriptions: unknown[] }>("GET", "/portal/prescriptions"),

  vitals: () =>
    req<{ vitals: unknown[] }>("GET", "/portal/vitals"),

  notifications: () =>
    req<{ notifications: unknown[] }>("GET", "/portal/notifications"),

  telemedicine: () =>
    req<{ sessions: unknown[] }>("GET", "/portal/telemedicine"),

  encounters: () =>
    req<{ encounters: unknown[] }>("GET", "/portal/encounters"),

  // Initiate payment via Paystack / Flutterwave
  payBill: (billId: string | number, gateway: "paystack" | "flutterwave" = "paystack") =>
    req<{ checkout_url: string; reference: string }>("POST", "/payments/initiate", {
      bill_id: billId,
      gateway,
      source: "patient_portal",
    }),

  // Verify payment after redirect
  verifyPayment: (reference: string) =>
    req<{ status: string; message: string }>("GET", `/payments/verify/${reference}`),
};
