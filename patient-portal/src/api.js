// Lightweight API client for the patient portal.
// Proxied through /api → backend in dev; in prod served via same Nginx.
const BASE = import.meta.env.VITE_API_URL ?? "/api";
function token() {
    return sessionStorage.getItem("portal_token") ?? "";
}
async function req(method, path, body) {
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
    return res.json();
}
export const portalApi = {
    // Auth: lookup patient by MRN + phone, return a portal JWT
    login: (mrn, phone) => req("POST", "/portal/auth", { mrn, phone }),
    // Patient own data
    profile: () => req("GET", "/portal/me"),
    appointments: () => req("GET", "/portal/appointments"),
    labResults: () => req("GET", "/portal/lab-results"),
    bills: () => req("GET", "/portal/bills"),
    // Initiate payment via Paystack / Flutterwave
    payBill: (billId, gateway = "paystack") => req("POST", "/payments/initiate", {
        bill_id: billId,
        gateway,
        source: "patient_portal",
    }),
    // Verify payment after redirect
    verifyPayment: (reference) => req("GET", `/payments/verify/${reference}`),
};
