import type { ReactNode } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Loader2, Printer, ArrowLeft } from "lucide-react";
import { api } from "@/lib/api-client";
import { naira, fmtDate } from "@/components/billing/billing-shared";

/**
 * Royan's printed documents, laid out like the forms the hospital already uses (finance meeting, 10 Oct 2026):
 *   /hospital/billing/:billId/invoice            the invoice (bill)
 *   /hospital/billing/:billId/invoice?receipt=ID the receipt for one payment
 *   /hospital/billing/:billId/invoice?claims=1   the HMO claims form for the visit
 * A Scancare bill prints on Scancare's letterhead - it is Scancare's sale, in Scancare's books.
 */

const COMPANIES: Record<string, { name: string; short: string; logo?: string }> = {
  ROYAN: { name: "ROYAN HOSPITAL", short: "Royan Hospital", logo: "/royan-logo.png" },
  SCANCARE: { name: "SCANCARE", short: "Scancare" },
};
const ADDRESS = "72, Aina Street, Ojodu, Lagos";
const PHONES = ["+234 700 DIAL ROYAN", "+234 700 342 76926", "+234 813 240 49706", "+234 1 342 2834"];

const CATEGORY_LABEL: Record<string, string> = {
  lab: "Laboratory Charges", pharmacy: "Pharmacy Charges", drug: "Pharmacy Charges", radiology: "Radiology Charges",
  imaging: "Radiology Charges", ward: "Ward Charges", nursing: "Nursing Charges", procedure: "Procedure Charges",
  surgery: "Surgery Charges", theatre: "Theatre Charges",
};
const ITEMISED = new Set(["consultation", "registration", "misc", "other"]);

function ageFromDob(dob?: string): string {
  if (!dob) return "—";
  const age = Math.floor((Date.now() - new Date(dob).getTime()) / (365.25 * 24 * 3600 * 1000));
  return isNaN(age) ? "—" : `${age}`;
}
const num = (v: any) => Number(v ?? 0);
const plain = (v: any) => num(v).toLocaleString("en-NG", { maximumFractionDigits: 2 });
const method = (m?: string) => ({ pos: "Debit Card", card: "Debit Card", transfer: "Bank Transfer", cash: "Cash" } as Record<string, string>)[String(m ?? "").toLowerCase()]
  ?? String(m ?? "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

function Letterhead({ company }: { company: string }) {
  const c = COMPANIES[company] ?? COMPANIES.ROYAN;
  return (
    <div className="flex items-start justify-between pb-3 mb-3">
      <div className="flex items-center gap-3">
        {c.logo && <img src={c.logo} alt={c.short} className="h-14 w-14 object-contain" />}
        <div>
          <h1 className="text-xl font-bold tracking-widest">{c.name}</h1>
          <p className="text-xs text-gray-600">{ADDRESS}</p>
        </div>
      </div>
      <div className="text-right text-xs text-gray-700 leading-tight">
        {PHONES.map((p) => <p key={p}>{p}</p>)}
        <p>info@royanhospital.com</p>
        <p>www.royanhospital.com</p>
      </div>
    </div>
  );
}

function Toolbar({ label }: { label: string }) {
  const navigate = useNavigate();
  return (
    <div className="print:hidden sticky top-0 z-10 flex items-center justify-between border-b bg-background px-4 py-2.5">
      <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => navigate(-1)}>
        <ArrowLeft className="h-3.5 w-3.5" /> Back
      </Button>
      <Button size="sm" className="gap-1.5" onClick={() => window.print()}>
        <Printer className="h-3.5 w-3.5" /> {label}
      </Button>
    </div>
  );
}

function Message({ text }: { text: string }) {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-background text-muted-foreground">
      <p>{text}</p>
      <Button variant="outline" onClick={() => navigate(-1)}>Go back</Button>
    </div>
  );
}

const Sheet = ({ children, narrow }: { children: ReactNode; narrow?: boolean }) => (
  <div className={`${narrow ? "max-w-[720px]" : "max-w-[820px]"} mx-auto bg-white text-black my-6 print:my-0 shadow-lg print:shadow-none rounded-md print:rounded-none border print:border-0 p-8 print:p-6`}>
    {children}
  </div>
);

export default function HospitalInvoice() {
  const { billId } = useParams<{ billId: string }>();
  const [searchParams] = useSearchParams();
  const receiptPaymentId = searchParams.get("receipt");
  const claims = searchParams.get("claims") === "1";

  const { data, isLoading, error } = useQuery({
    queryKey: ["hospital-invoice", billId],
    queryFn: () => api.hospital.billing.getInvoice(billId!),
    enabled: !!billId && !claims,
  });
  const claimsQ = useQuery({
    queryKey: ["hospital-claims-form", billId],
    queryFn: () => api.hospital.billing.claimsForm(billId!),
    enabled: !!billId && claims,
  });

  if (claims) {
    if (claimsQ.isLoading) return <Loading />;
    if (claimsQ.error || !claimsQ.data) return <Message text="Couldn't load the claims form." />;
    return <ClaimsForm f={claimsQ.data} />;
  }
  if (isLoading) return <Loading />;
  if (error || !data) return <Message text="Couldn't load this invoice." />;

  const { bill, items, patient, encounter, inpatient_lines: inpatientLines, amount_in_words: amountInWords } = data;
  const company = data.company ?? bill?.entity ?? "ROYAN";
  const patientName = `${patient?.first_name ?? ""} ${patient?.last_name ?? ""}`.trim() || "—";
  const admitted = !!encounter?.admitted;
  const receipts: any[] = data.receipts ?? data.payments ?? [];

  if (receiptPaymentId) {
    const r = receipts.find((p: any) => String(p.id) === String(receiptPaymentId));
    // Asked for a receipt that does not exist on this bill: say so rather than quietly showing the invoice.
    if (!r) return <Message text="No payment on this bill matches that receipt." />;
    return <Receipt bill={bill} items={items ?? []} receipts={receipts} r={r} company={company} patientName={patientName} />;
  }

  // Royan's invoice: registration and consultation line by line, everything else one line per department.
  const grouped: { label: string; code?: string; rate: number | null; qty: number | null; amount: number }[] = [];
  const byCat = new Map<string, number>();
  for (const it of items ?? []) {
    const cat = String(it.category ?? "").toLowerCase();
    const amount = num(it.gross_amount ?? num(it.quantity) * num(it.unit_price));
    if (ITEMISED.has(cat) || !cat || it.source === "registration" || it.source === "consultation") grouped.push({ label: it.description, code: it.service_code, rate: num(it.unit_price), qty: num(it.quantity), amount });
    else byCat.set(CATEGORY_LABEL[cat] ?? `${cat[0].toUpperCase()}${cat.slice(1)} Charges`, (byCat.get(CATEGORY_LABEL[cat] ?? `${cat[0].toUpperCase()}${cat.slice(1)} Charges`) ?? 0) + amount);
  }
  byCat.forEach((amount, label) => grouped.push({ label, rate: amount, qty: null, amount }));
  if (admitted) for (const l of inpatientLines ?? []) grouped.push({ label: `${l.service_name}${l.charged_at ? ` (${fmtDate(l.charged_at)})` : ""}`, rate: num(l.unit_price), qty: num(l.quantity), amount: num(l.total) });
  const regId = `${company === "SCANCARE" ? "SC" : "RO"}/${admitted ? "I" : "O"}-${bill.encounter_id ?? bill.id}`;
  const cell = "border border-gray-500 px-2 py-1";

  return (
    <div className="min-h-screen bg-slate-100 print:bg-white">
      <Toolbar label="Print invoice" />
      <Sheet>
        <Letterhead company={company} />
        <div className="border border-gray-500 mb-3">
          <p className="text-center text-sm font-semibold border-b border-gray-500 py-1">Patient Information</p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 px-3 py-2.5 text-sm">
            <div><span className="text-gray-600">Name :</span> <span className="font-semibold uppercase">{patientName}</span></div>
            <div><span className="text-gray-600">Registration ID :</span> <span className="font-mono">{regId}</span></div>
            <div><span className="text-gray-600">Address :</span> <span className="uppercase">{patient?.address ?? "—"}</span></div>
            <div><span className="text-gray-600">Patient ID :</span> <span className="font-mono">{patient?.mrn ?? "—"}</span></div>
            <div><span className="text-gray-600">Primary Care Provider :</span> <span>{data.doctor ?? encounter?.consulting_doctor ?? "—"}</span></div>
            <div><span className="text-gray-600">Sex / Age :</span> <span className="capitalize">{patient?.gender ?? "—"} / {ageFromDob(patient?.date_of_birth)} Year</span></div>
            <div><span className="text-gray-600">Bill No :</span> <span className="font-mono">{bill.bill_number}</span></div>
            <div><span className="text-gray-600">Date :</span> <span>{fmtDate(bill.billed_at)}</span></div>
          </div>
        </div>

        <table className="w-full border-collapse text-sm mb-3">
          <thead>
            <tr>
              <th className={`${cell} text-left w-12`}>Sr. No.</th>
              <th className={`${cell} text-left`}>Item</th>
              <th className={`${cell} text-left w-24`}>CGHS Code No.</th>
              <th className={`${cell} text-right w-24`}>Rate</th>
              <th className={`${cell} text-right w-12`}>Qty.</th>
              <th className={`${cell} text-right w-28`}>Amount</th>
            </tr>
          </thead>
          <tbody>
            <tr><td className={cell} /><td className={`${cell} font-semibold italic`} colSpan={5}>{admitted ? "Inpatient Charges" : "Conservative Charges"}</td></tr>
            {grouped.length === 0 ? (
              <tr><td colSpan={6} className={`${cell} text-center text-gray-500`}>No charges recorded</td></tr>
            ) : grouped.map((g, i) => (
              <tr key={i}>
                <td className={cell}>{i + 1}</td>
                <td className={`${cell} uppercase`}>{g.label}</td>
                <td className={`${cell} font-mono text-xs`}>{g.code ?? ""}</td>
                <td className={`${cell} text-right`}>{g.rate === null ? "" : plain(g.rate)}</td>
                <td className={`${cell} text-right`}>{g.qty === null ? "-" : g.qty}</td>
                <td className={`${cell} text-right`}>{plain(g.amount)}</td>
              </tr>
            ))}
            <tr className="font-semibold">
              <td className={cell} colSpan={5}><span className="float-right">Total</span></td>
              <td className={`${cell} text-right`}>{naira(bill.total_amount)}</td>
            </tr>
            {num(bill.discount) > 0 && (
              <tr><td className={cell} colSpan={5}><span className="float-right">Discount</span></td><td className={`${cell} text-right`}>-{naira(bill.discount)}</td></tr>
            )}
            {num(bill.hmo_covered) > 0 && (
              <tr><td className={cell} colSpan={5}><span className="float-right">HMO Covered</span></td><td className={`${cell} text-right`}>-{naira(bill.hmo_covered)}</td></tr>
            )}
          </tbody>
        </table>

        <div className="flex items-start justify-between gap-6 text-sm mb-10">
          <div>
            <p className="text-gray-600">Amount Chargeable (in words)</p>
            <p className="font-semibold">{amountInWords}</p>
          </div>
          <table className="border-collapse text-sm min-w-[240px]">
            <tbody>
              <tr><td className={cell}>Amount Chargeable</td><td className={`${cell} text-right font-semibold`}>{naira(bill.patient_due)}</td></tr>
              <tr><td className={cell}>Amount Paid</td><td className={`${cell} text-right`}>{naira(bill.amount_paid)}</td></tr>
              <tr><td className={cell}>Balance</td><td className={`${cell} text-right font-semibold`}>{naira(bill.outstanding)}</td></tr>
            </tbody>
          </table>
        </div>

        <div className="flex items-end justify-between text-sm">
          <p className="font-semibold">Signature of Patient : <span className="inline-block w-48 border-b border-black" /></p>
          <div className="border border-gray-500 px-4 pt-2 pb-1 text-center min-w-[340px]">
            <p className="font-bold">{(COMPANIES[company] ?? COMPANIES.ROYAN).name}</p>
            {/* until staff signatures are on file, each signatory's name and role stand in for the signature */}
            <div className="mt-3 grid grid-cols-4 gap-3 text-xs">
              {([["bill_manager", "Bill Manager"], ["cashier", "Cashier"], ["med_supdt", "Med. Supdt."], ["authorised", "Authorised Signatory"]] as const).map(([k, label]) => (
                <Signatory key={k} label={label} person={data.signatories?.[k]} />
              ))}
            </div>
          </div>
        </div>
        {bill.status === "void" && <p className="mt-6 text-center text-lg font-bold text-red-600">VOID — {bill.void_reason}</p>}
      </Sheet>
    </div>
  );
}

/** A signatory's credentials (name, role, staff number) above the line where the signature will go. */
function Signatory({ label, person }: { label: string; person?: { name?: string; title?: string; staff_number?: string } | null }) {
  return (
    <div className="flex min-w-0 flex-col items-center text-center">
      <div className="flex min-h-[34px] w-full flex-col justify-end border-b border-gray-600 pb-0.5">
        {person?.name && <span className="truncate font-semibold normal-case" title={person.name}>{person.name}</span>}
        {(person?.title || person?.staff_number) && (
          <span className="truncate text-xs font-normal text-gray-700">{[person.title, person.staff_number].filter(Boolean).join(" · ")}</span>
        )}
      </div>
      <span className="mt-0.5 font-normal">{label}</span>
    </div>
  );
}

function Loading() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  );
}

/** Royan's receipt: what was billed, this payment, what was paid before it, and what is left. */
function Receipt({ bill, items, receipts, r, company, patientName }: {
  bill: any; items: any[]; receipts: any[]; r: any; company: string; patientName: string;
}) {
  const standing = receipts.filter((p: any) => (p.status ?? "posted") !== "void");
  const at = new Date(r.received_at).getTime();
  const previous = standing.filter((p: any) => p.id !== r.id && (new Date(p.received_at).getTime() < at || (new Date(p.received_at).getTime() === at && p.id < r.id)))
    .reduce((n: number, p: any) => n + num(p.amount), 0);
  const totalBill = num(bill.patient_due ?? bill.patient_balance);
  const totalPaid = previous + num(r.amount);
  const balance = Math.max(totalBill - totalPaid, 0);
  const voided = (r.status ?? "posted") === "void";
  const cell = "border border-gray-600 px-2 py-0.5";
  return (
    <div className="min-h-screen bg-slate-100 print:bg-white">
      <Toolbar label="Print receipt" />
      <Sheet narrow>
        <Letterhead company={company} />
        <table className="w-full border-collapse text-sm">
          <tbody>
            <tr>
              <td className={`${cell} font-semibold`} colSpan={2}>Date : {new Date(r.received_at).toLocaleString("en-GB")}</td>
              <td className={`${cell} text-center font-bold tracking-[0.3em]`} colSpan={2}>RECEIPT</td>
              <td className={`${cell} text-right font-semibold`}>Bill No - {bill.bill_number}</td>
            </tr>
            <tr className="font-semibold">
              <td className={cell}>PARTICULARS</td><td className={cell}>UNIT PRICE</td><td className={cell}>UNIT/S</td>
              <td className={cell}>Discount</td><td className={`${cell} text-right`}>AMOUNT</td>
            </tr>
            {items.map((it: any) => (
              <tr key={it.id}>
                <td className={`${cell} uppercase`}>{it.description}</td>
                <td className={cell}>{plain(it.unit_price)}</td>
                <td className={cell}>{plain(it.quantity)}</td>
                <td className={cell}>0</td>
                <td className={`${cell} text-right`}>{naira(it.gross_amount ?? num(it.quantity) * num(it.unit_price))}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-1 text-right text-sm font-semibold leading-snug">
          {num(bill.discount) > 0 && <p>Discount : {plain(bill.discount)}</p>}
          {num(bill.hmo_covered) > 0 && <p>HMO Covered : {plain(bill.hmo_covered)}</p>}
          <p>Total Bill Amount : {plain(totalBill)}</p>
          <p>Total Paid Amount : {plain(totalPaid)}</p>
          <p>Previous Amount : {plain(previous)}</p>
          <p>Balance : {plain(balance)}</p>
        </div>
        <p className="mt-1 text-center text-sm font-semibold">
          By {method(r.payment_method)} : {plain(r.amount)}{r.reference ? ` (ref ${r.reference})` : ""} · Receipt {r.receipt_number ?? `#${r.id}`}
        </p>
        <p className="border border-gray-600 px-2 py-1 text-center text-sm font-semibold">
          Received with thanks from <span className="uppercase">{patientName}</span> sum of {r.amount_in_words ?? ""}.
        </p>
        <div className="mt-8 flex items-end justify-between text-sm font-semibold">
          <span>Name &amp; Sign. Of Patient</span>
          <div className="min-w-[200px] text-xs"><Signatory label="Auth. Sign. (Cashier)" person={r.received_by_person} /></div>
        </div>
        {voided && <p className="mt-6 text-center text-lg font-bold text-red-600">VOID — {r.void_reason}</p>}
      </Sheet>
    </div>
  );
}

/** Royan's HMO claims form, filled from the visit; the patient's signature is the one taken on the pharmacy tablet. */
function ClaimsForm({ f }: { f: any }) {
  const company = (COMPANIES[f.company] ?? COMPANIES.ROYAN).name;
  const sum = (rows: any[]) => rows.reduce((n, r) => n + num(r.cost), 0);
  const names = (rows: any[]) => rows.map((r) => r.description).join(", ");
  const medications: any[] = f.medications ?? [];
  const blanks = Math.max(0, 12 - medications.length);
  const line = "border-b border-dotted border-gray-500 flex-1 px-1";
  const field = (label: string, value: any) => (
    <div className="flex items-end gap-1"><span className="whitespace-nowrap">{label}:</span><span className={line}>{value ?? ""}</span></div>
  );
  const costed = (label: string, rows: any[], extra?: string) => (
    <div className="flex items-end gap-2">
      <div className="flex flex-1 items-end gap-1"><span className="whitespace-nowrap">{label}:</span><span className={line}>{[names(rows), extra].filter(Boolean).join(" · ")}</span></div>
      <span className="w-24 border border-gray-600 px-1 text-right">{rows.length ? plain(sum(rows)) : ""}</span>
    </div>
  );
  const cell = "border border-gray-600 px-2 py-1";
  return (
    <div className="min-h-screen bg-slate-100 print:bg-white">
      <Toolbar label="Print claims form" />
      <Sheet narrow>
        <h1 className="text-center text-xl font-semibold tracking-wide">{company} CLAIMS FORM</h1>
        <p className="mb-4 text-center text-xs uppercase text-gray-600">{ADDRESS}</p>
        <div className="space-y-1.5 text-sm">
          {field("Name of HMO", f.hmo_name)}
          {field("Patient's Name", f.patient_name)}
          {field("Health Card No.", [f.health_card_no, f.authorisation_code ? `Auth: ${f.authorisation_code}` : null].filter(Boolean).join(" · "))}
          <div className="flex gap-3">{field("Primary Diagnosis", f.primary_diagnosis)}<div className="w-24">{field("Age", f.age)}</div><div className="w-24">{field("Sex", f.sex)}</div></div>
          <div className="flex gap-3">{field("Differential Diagnosis", f.differential_diagnosis)}<div className="w-56">{field("Date of Attendance", f.date_of_attendance ? fmtDate(f.date_of_attendance) : "")}</div></div>
          <div className="flex justify-end"><span className="w-24 border border-gray-600 px-1 text-center text-xs font-semibold">COSTS</span></div>
          {costed("Surgical Procedure", f.procedures ?? [])}
          {costed("Investigations", f.investigations ?? [])}
          {costed("Admission", f.admission ?? [])}
          {costed("Consultation", f.consultation ?? [])}
          {(f.other ?? []).length > 0 && costed("Other", f.other)}
        </div>
        <table className="mt-2 w-full border-collapse text-sm">
          <thead>
            <tr><th className={`${cell} w-12 text-left`}>S/N</th><th className={`${cell} text-left`}>Medication</th><th className={`${cell} text-left w-32`}>Dosage</th><th className={`${cell} text-left w-28`}>Duration</th><th className={`${cell} text-right w-24`}>Costs</th></tr>
          </thead>
          <tbody>
            {medications.map((m, i) => (
              <tr key={i}><td className={cell}>{i + 1}</td><td className={cell}>{m.name}{m.quantity ? ` × ${m.quantity}` : ""}</td><td className={cell}>{m.dosage}</td><td className={cell}>{m.duration}</td><td className={`${cell} text-right`}>{m.cost ? plain(m.cost) : ""}</td></tr>
            ))}
            {Array.from({ length: blanks }).map((_, i) => (
              <tr key={`b${i}`}><td className={`${cell} h-6`} /><td className={cell} /><td className={cell} /><td className={cell} /><td className={cell} /></tr>
            ))}
            <tr><td colSpan={3} /><td className="px-2 py-1 text-right font-semibold">Total</td><td className={`${cell} text-right font-semibold`}>{plain(f.total)}</td></tr>
          </tbody>
        </table>
        {(f.approval_codes ?? []).length > 0 && (
          <p className="mt-2 text-xs">HMO approval code(s) for services added after review: <span className="font-semibold">{f.approval_codes.join(", ")}</span></p>
        )}
        {(f.not_covered ?? []).length > 0 && (
          <p className="mt-2 text-xs text-gray-600">
            Not covered by the HMO (paid by the patient, not claimed): {f.not_covered.map((n: any) => `${n.description} (${plain(n.cost)})`).join("; ")}
          </p>
        )}
        <div className="mt-4 text-sm">{field("Clinical Summary", f.clinical_summary)}</div>
        <div className="mt-12 flex items-end justify-between text-sm">
          <div className="text-center">
            <div className="flex h-12 w-56 flex-col justify-end border-b border-dotted border-gray-600 text-xs">
              {f.verified_by && <><span className="font-semibold">{f.verified_by}</span><span>checked {fmtDate(f.verified_at)}</span></>}
            </div>
            <p className="italic">Authorized HMO Officer's Signature</p>
          </div>
          <div className="text-center">
            <div className="w-56 border-b border-dotted border-gray-600 h-12 flex items-end justify-center">
              {f.patient_signature_url && <img src={f.patient_signature_url} alt="Patient's signature" className="max-h-12 object-contain" />}
            </div>
            <p className="italic">Patient's Signature</p>
          </div>
        </div>
        <p className="mt-6 text-xs text-gray-500">Bill {f.bill_number} · Hospital No. {f.mrn ?? "—"}</p>
      </Sheet>
    </div>
  );
}
