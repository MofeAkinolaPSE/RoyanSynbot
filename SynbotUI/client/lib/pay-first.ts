/**
 * Pay first: lab, radiology and pharmacy refuse to serve a private outpatient whose bill is unpaid (HTTP 402).
 * Show the reason; a supervisor (admin / finance / management) may release the order with a reason instead.
 */
import { api, ApiError } from "@/lib/api-client";
import { askConfirm, askText } from "@/lib/ask";

const SUPERVISORS = ["admin", "finance", "management"];

/** Returns true when the error was a pay-first block (handled here), false for any other error. */
export async function handlePayFirst(
  e: unknown, source: "lab_order" | "radiology_order" | "prescription", sourceId: number | string,
  roles: string[], toast: (t: { title: string; description?: string; variant?: "destructive" }) => void,
  retry?: () => void,
): Promise<boolean> {
  if (!(e instanceof ApiError) || e.status !== 402) return false;
  const why = e.message || "The patient pays at the cashier first.";
  if (!roles.some((r) => SUPERVISORS.includes(r))) {
    toast({ title: "Payment needed first", description: `${why} A supervisor can release it if needed.`, variant: "destructive" });
    return true;
  }
  if (!(await askConfirm(`Payment needed first\n${why}\nRelease this order without payment? It is recorded with your name and reason.`))) return true;
  const reason = await askText("Why is this order being served before payment? (emergency, credit agreed...)");
  if (!reason || reason.trim().length < 3) return true;
  try {
    await api.hospital.billing.releaseOrder(source, sourceId, reason.trim());
    toast({ title: "Released", description: "The order may be served now." });
    retry?.();
  } catch (err: any) {
    toast({ title: "Could not release", description: err?.message, variant: "destructive" });
  }
  return true;
}
