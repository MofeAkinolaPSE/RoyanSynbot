import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Loader2, Printer, ArrowLeft } from "lucide-react";
import { api } from "@/lib/api-client";
import { naira, fmtDate } from "@/components/billing/billing-shared";

function ageFromDob(dob?: string): string {
  if (!dob) return "—";
  const age = Math.floor((Date.now() - new Date(dob).getTime()) / (365.25 * 24 * 3600 * 1000));
  return isNaN(age) ? "—" : `${age}`;
}

export default function HospitalInvoice() {
  const { billId } = useParams<{ billId: string }>();
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery({
    queryKey: ["hospital-invoice", billId],
    queryFn: () => api.hospital.billing.getInvoice(billId!),
    enabled: !!billId,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-background text-muted-foreground">
        <p>Couldn't load this invoice.</p>
        <Button variant="outline" onClick={() => navigate(-1)}>Go back</Button>
      </div>
    );
  }

  const { bill, items, patient, encounter, inpatient_lines: inpatientLines, amount_in_words: amountInWords } = data;
  const patientName = `${patient?.first_name ?? ""} ${patient?.last_name ?? ""}`.trim() || "—";
  const admitted = !!encounter?.admitted;

  return (
    <div className="min-h-screen bg-slate-100 print:bg-white">
      {/* Screen-only toolbar */}
      <div className="print:hidden sticky top-0 z-10 bg-background border-b px-4 py-2.5 flex items-center justify-between">
        <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => navigate(-1)}>
          <ArrowLeft className="h-3.5 w-3.5" /> Back
        </Button>
        <Button size="sm" className="gap-1.5" onClick={() => window.print()}>
          <Printer className="h-3.5 w-3.5" /> Print
        </Button>
      </div>

      {/* Printable sheet */}
      <div className="max-w-[820px] mx-auto bg-white text-black my-6 print:my-0 shadow-lg print:shadow-none rounded-md print:rounded-none border print:border-0 p-8 print:p-6">
        {/* Header */}
        <div className="flex items-start justify-between border-b-2 border-black pb-4 mb-4">
          <div className="flex items-center gap-3">
            <img src="/royan-logo.png" alt="Royan Hospital" className="h-14 w-14" />
            <div>
              <h1 className="text-xl font-bold tracking-tight">ROYAN HOSPITAL</h1>
              <p className="text-sm text-gray-600">Quality healthcare, close to home</p>
            </div>
          </div>
          <div className="text-right text-sm text-gray-600 space-y-0.5">
            <p>info@royanhospital.com</p>
            <p>www.royanhospital.com</p>
          </div>
        </div>

        {/* Patient Information */}
        <div className="border border-gray-400 mb-4">
          <div className="bg-gray-100 border-b border-gray-400 px-3 py-1.5">
            <h2 className="text-sm font-semibold uppercase tracking-wide">Patient Information</h2>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 px-3 py-2.5 text-sm">
            <div><span className="text-gray-500">Name:</span> <span className="font-medium">{patientName}</span></div>
            <div><span className="text-gray-500">Patient ID:</span> <span className="font-mono font-medium">{patient?.mrn ?? "—"}</span></div>
            <div><span className="text-gray-500">Address:</span> <span>{patient?.address ?? "—"}</span></div>
            <div><span className="text-gray-500">Sex / Age:</span> <span className="capitalize">{patient?.gender ?? "—"} / {ageFromDob(patient?.date_of_birth)} Year</span></div>
            <div><span className="text-gray-500">Payer:</span> <span className="capitalize">{patient?.patient_type === "hmo" ? (patient?.hmo_provider || "HMO") : (patient?.patient_type || "Cash")}</span></div>
            <div><span className="text-gray-500">Primary Care Provider:</span> <span>{encounter?.consulting_doctor ?? "—"}</span></div>
            <div className="col-span-2">
              <span className="text-gray-500">Encounter:</span>{" "}
              <span>{admitted ? "In-house / Admitted" : "Outpatient"} · {encounter?.department ?? "—"} · Bill {bill.bill_number}</span>
            </div>
          </div>
        </div>

        {/* Ward / Nursing charges (admitted only) */}
        {admitted && inpatientLines?.length > 0 && (
          <div className="mb-3">
            <p className="text-sm font-semibold uppercase tracking-wide mb-1">Ward &amp; Nursing Charges</p>
            <table className="w-full border-collapse border border-gray-400 text-sm">
              <thead>
                <tr className="bg-gray-100">
                  <th className="border border-gray-400 px-2 py-1 text-left">Item</th>
                  <th className="border border-gray-400 px-2 py-1 text-right">Rate</th>
                  <th className="border border-gray-400 px-2 py-1 text-right">Qty</th>
                  <th className="border border-gray-400 px-2 py-1 text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {inpatientLines.map((l: any) => (
                  <tr key={l.id}>
                    <td className="border border-gray-400 px-2 py-1">{l.service_name}{l.charged_at ? ` (${fmtDate(l.charged_at)})` : ""}</td>
                    <td className="border border-gray-400 px-2 py-1 text-right">{naira(l.unit_price)}</td>
                    <td className="border border-gray-400 px-2 py-1 text-right">{l.quantity}</td>
                    <td className="border border-gray-400 px-2 py-1 text-right">{naira(l.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Itemized charges */}
        <table className="w-full border-collapse border border-gray-400 text-sm mb-4">
          <thead>
            <tr className="bg-gray-100">
              <th className="border border-gray-400 px-2 py-1 text-left w-10">#</th>
              <th className="border border-gray-400 px-2 py-1 text-left">Item</th>
              <th className="border border-gray-400 px-2 py-1 text-left">Category</th>
              <th className="border border-gray-400 px-2 py-1 text-right">Rate</th>
              <th className="border border-gray-400 px-2 py-1 text-right">Qty</th>
              <th className="border border-gray-400 px-2 py-1 text-right">Amount</th>
            </tr>
          </thead>
          <tbody>
            {(items ?? []).length === 0 ? (
              <tr><td colSpan={6} className="border border-gray-400 px-2 py-3 text-center text-gray-500">No itemized charges recorded</td></tr>
            ) : (items ?? []).map((it: any, i: number) => (
              <tr key={it.id}>
                <td className="border border-gray-400 px-2 py-1">{i + 1}</td>
                <td className="border border-gray-400 px-2 py-1">{it.description}</td>
                <td className="border border-gray-400 px-2 py-1 capitalize">{it.category}</td>
                <td className="border border-gray-400 px-2 py-1 text-right">{naira(it.unit_price)}</td>
                <td className="border border-gray-400 px-2 py-1 text-right">{it.quantity}</td>
                <td className="border border-gray-400 px-2 py-1 text-right">{naira(it.quantity * it.unit_price)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="font-semibold bg-gray-50">
              <td colSpan={5} className="border border-gray-400 px-2 py-1.5 text-right">Total</td>
              <td className="border border-gray-400 px-2 py-1.5 text-right">{naira(bill.total_amount)}</td>
            </tr>
            {bill.discount > 0 && (
              <tr>
                <td colSpan={5} className="border border-gray-400 px-2 py-1 text-right text-gray-600">Discount</td>
                <td className="border border-gray-400 px-2 py-1 text-right text-gray-600">-{naira(bill.discount)}</td>
              </tr>
            )}
            {bill.hmo_covered > 0 && (
              <tr>
                <td colSpan={5} className="border border-gray-400 px-2 py-1 text-right text-gray-600">HMO Covered</td>
                <td className="border border-gray-400 px-2 py-1 text-right text-gray-600">-{naira(bill.hmo_covered)}</td>
              </tr>
            )}
            <tr className="font-semibold">
              <td colSpan={5} className="border border-gray-400 px-2 py-1.5 text-right">Patient Amount Chargeable</td>
              <td className="border border-gray-400 px-2 py-1.5 text-right">{naira(bill.patient_due)}</td>
            </tr>
          </tfoot>
        </table>

        <div className="flex items-start justify-between text-sm mb-8">
          <p className="max-w-[420px]"><span className="text-gray-500">Amount Chargeable (in words):</span> {amountInWords}</p>
          <div className="text-right space-y-0.5">
            <p><span className="text-gray-500">Amount Paid:</span> {naira(bill.amount_paid)}</p>
            <p className="font-semibold"><span className="text-gray-500 font-normal">Balance:</span> {naira(bill.outstanding)}</p>
          </div>
        </div>

        <div className="flex items-end justify-between text-sm">
          <div>
            <div className="w-48 border-b border-black h-8" />
            <p className="text-gray-500 mt-1">Signature of Patient</p>
          </div>
          <div className="text-center">
            <p className="font-bold text-base">ROYAN HOSPITAL</p>
            <p className="text-gray-500 text-[13px]">{fmtDate(bill.billed_at)}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
