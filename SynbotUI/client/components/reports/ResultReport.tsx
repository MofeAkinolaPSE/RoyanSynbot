/**
 * Lab and Scancare results as Scancare's printed report (template: backend/docs/scan care template and logo).
 * The lab / Scancare enter their findings; the report is built from them (backend services/result_reports.py) and
 * opens in a pop-up from every "View report" button - the doctor's results review, the lab and Scancare workspaces,
 * the patient's record - with Print.
 *
 *   <ViewReportButton kind="lab" orderIds={[id]} />      one or more lab tests of one patient
 *   <ViewReportButton kind="scan" orderIds={[id]} />     one scan
 */
import { useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileText, Loader2, Printer } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";

type Dict = Record<string, any>;
type Kind = "lab" | "scan";

const NAVY = "#34468c";
const RED = "#e30613";
const BLUE = "#1d1dd6";
const ADDRESS = "74, Aina Street, off Ogunnisi road, Ojodu Berger, Lagos Nigeria.";
const CONTACTS = ["+234 700 722 62273", "+234 700 SCANCARE", "info@scancarenigeria.com", "www.scancarenigeria.com"];

function Letterhead() {
  return (
    <div className="relative h-[104px] overflow-hidden">
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 800 104" preserveAspectRatio="none" aria-hidden>
        <polygon points="0,8 70,8 235,80 800,80 800,104 0,104" fill="#a7a9ac" />
        <polygon points="0,8 70,8 235,80 0,80" fill="#c9cacc" />
        <polygon points="0,58 0,104 82,104" fill={RED} />
        <polygon points="420,0 800,0 800,104 786,104 786,20 742,8 420,8" fill={NAVY} />
        <polygon points="742,8 786,20 786,104 778,104 778,26 736,14" fill="#ffffff" opacity="0.9" />
      </svg>
      <div className="absolute left-[11%] top-[4px] flex flex-col">
        <img src="/scancare-logo.png" alt="Scancare Diagnostic Centre" className="h-[50px] w-auto object-contain mix-blend-multiply" />
        <div className="ml-2 mt-0.5 space-y-[1px] text-[0.773em] font-semibold leading-[10px] text-[#2b2b2b]">
          <p>☎ {CONTACTS[0]} · {CONTACTS[1]}</p>
          <p>✉ {CONTACTS[2]}</p>
          <p>🌐 {CONTACTS[3]}</p>
        </div>
      </div>
    </div>
  );
}

function Footer() {
  return (
    <div className="relative mt-8 h-[34px] overflow-hidden">
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 800 34" preserveAspectRatio="none" aria-hidden>
        <polygon points="0,0 8,34 800,34 800,10 0,10" fill={NAVY} />
      </svg>
      <p className="absolute bottom-[7px] left-[6%] text-[0.909em] font-semibold text-white">{ADDRESS}</p>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="grid grid-cols-[118px_10px_1fr] text-[1em] leading-[17px]">
      <span>{label}</span><span>:</span><span className="font-medium uppercase">{value || ""}</span>
    </div>
  );
}

function PatientBlock({ r }: { r: Dict }) {
  return (
    <div className="mt-2 grid grid-cols-2 gap-x-6 border-y border-black py-1">
      <div>
        <InfoRow label="Patient Name" value={r.patient_name} />
        <InfoRow label="Patient ID" value={r.patient_id} />
        <InfoRow label="Ref By" value={r.ref_by} />
        <InfoRow label={r.kind === "scan" ? "Scan Date" : "Sample Received"} value={r.sample_received} />
        <InfoRow label={r.kind === "scan" ? "Scan Request No." : "Lab Request No."} value={r.request_no} />
      </div>
      <div>
        <InfoRow label="Age/Gender" value={r.age_gender} />
        <InfoRow label="Mobile No." value={r.mobile} />
        <InfoRow label="Consultant Name" value={r.consultant} />
        <InfoRow label="Report Print Date" value={r.printed_at} />
        <InfoRow label="Provisional Diagnosis" value={r.provisional_diagnosis} />
      </div>
    </div>
  );
}

function Heading({ text }: { text: string }) {
  return (
    <div className="my-3 border-2 border-black py-1 text-center text-[1.18em] font-bold tracking-wide" style={{ color: BLUE }}>
      {text}
    </div>
  );
}

function Signatories({ people }: { people: Dict[] }) {
  if (!people?.length) return <div className="h-10" />;
  return (
    <div className="mt-8 grid grid-cols-2 gap-6 text-[0.909em] font-bold">
      {people.map((p) => (
        <div key={p.name} className="flex flex-col">
          <span className="mb-1 h-6 w-40 border-b border-gray-400" />
          <span>{p.name}{p.title ? ` - ${p.title}` : ""}</span>
        </div>
      ))}
    </div>
  );
}

function LabBody({ r }: { r: Dict }) {
  return (
    <>
      <div className="mt-2 grid grid-cols-[2fr_1fr_1fr_1.3fr] text-[0.955em] font-bold underline">
        <span>INVESTIGATION</span><span>OBSERVED VALUE</span><span>UNITS</span><span>NORMAL RANGE</span>
      </div>
      {(r.sections ?? []).map((s: Dict) => (
        <section key={s.heading}>
          <Heading text={s.heading} />
          {s.tests.map((t: Dict) => (
            <div key={t.order_id} className="mb-3">
              <p className="mb-1 text-[1.09em] font-bold underline">{t.test_name}</p>
              {!t.resulted && <p className="text-[1em] italic text-gray-600">Result not ready yet.</p>}
              {t.rows.map((row: Dict, i: number) => {
                const flagged = !!row.flag;
                return (
                  <div key={i} className="grid grid-cols-[2fr_1fr_1fr_1.3fr] text-[1em] leading-[22px]">
                    <span className="flex justify-between pr-6"><span>{row.name}</span><span>:</span></span>
                    <span className={cn(flagged ? "font-bold text-red-600" : "text-green-700")}>
                      {row.value ?? "—"}{flagged && row.flag !== "*" ? ` ${row.flag}` : ""}
                    </span>
                    <span>{row.unit ?? ""}</span>
                    <span>{row.range ?? ""}</span>
                  </div>
                );
              })}
              {t.notes?.map((n: string, i: number) => (
                <p key={i} className="mt-1 whitespace-pre-wrap text-[0.955em]">{n}</p>
              ))}
              {t.amended && <p className="mt-1 text-[0.909em] italic">This result was amended after verification.</p>}
            </div>
          ))}
        </section>
      ))}
      <p className="mt-2 border-t border-black pt-1 text-[0.773em]">NOTE:- {r.note}</p>
    </>
  );
}

function ScanBody({ r }: { r: Dict }) {
  return (
    <>
      <Heading text={r.heading} />
      <p className="mb-2 text-[1.09em] font-bold underline">{r.test_name}</p>
      {r.clinical_indication && !String(r.report ?? "").toUpperCase().includes("INDICATION") && (
        <p className="mb-2 text-[1em]"><span className="font-bold">INDICATION: </span>{r.clinical_indication}</p>
      )}
      {r.report && <p className="whitespace-pre-wrap text-[1em] leading-[18px]">{r.report}</p>}
      {r.findings && r.findings !== r.report && (
        <div className="mt-2 text-[1em]"><p className="font-bold">FINDINGS:</p><p className="whitespace-pre-wrap leading-[18px]">{r.findings}</p></div>
      )}
      {r.impression && (
        <div className="mt-3 text-[1em]"><p className="font-bold">IMPRESSION:</p><p className="whitespace-pre-wrap font-semibold leading-[18px]">{r.impression}</p></div>
      )}
      {!r.complete && <p className="text-[1em] italic text-gray-600">The report has not been written yet.</p>}
    </>
  );
}

/** The report sheet itself (white, A4-width), shared by the pop-up and its print window. */
export function ResultReportSheet({ report }: { report: Dict }) {
  return (
    // A replica of the paper form: one fixed base size (11px, as Scancare prints it) and everything inside sized
    // relative to it, so the sheet prints the same on every screen and printer.
    <div className="mx-auto w-full max-w-[800px] bg-white px-1 text-black" style={{ fontFamily: "Arial, Helvetica, sans-serif", fontSize: "11px" }}>
      <Letterhead />
      <PatientBlock r={report} />
      {report.kind === "scan" ? <ScanBody r={report} /> : <LabBody r={report} />}
      <Signatories people={report.signatories} />
      <Footer />
    </div>
  );
}

/** Print just the report: copy it, with the app's styles, into a window of its own. */
function printReport(node: HTMLElement | null, title: string) {
  if (!node) return;
  const w = window.open("", "_blank", "width=900,height=1000");
  if (!w) return window.print();
  const styles = Array.from(document.querySelectorAll('link[rel="stylesheet"], style')).map((n) => n.outerHTML).join("\n");
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${title}</title>
    <base href="${window.location.origin}/">${styles}
    <style>@page{size:A4;margin:10mm}html,body{background:#fff!important}*{-webkit-print-color-adjust:exact;print-color-adjust:exact}</style>
    </head><body>${node.outerHTML}</body></html>`);
  w.document.close();
  const go = () => { w.focus(); w.print(); };
  // wait for the logo and stylesheets before printing
  const imgs = Array.from(w.document.images);
  Promise.all(imgs.map((i) => (i.complete ? Promise.resolve() : new Promise((res) => { i.onload = i.onerror = res; }))))
    .then(() => setTimeout(go, 300));
}

export function ResultReportDialog({ kind, orderIds, open, onOpenChange }: {
  kind: Kind; orderIds: Array<number | string>; open: boolean; onOpenChange: (v: boolean) => void;
}) {
  const sheet = useRef<HTMLDivElement>(null);
  const q = useQuery({
    queryKey: ["result-report", kind, orderIds.join(",")],
    queryFn: () => (kind === "scan" ? api.hospital.radiology.report(orderIds[0]) : api.hospital.lab.report(orderIds)),
    enabled: open && orderIds.length > 0,
  });
  const r: Dict | undefined = q.data;
  const unverified = r && (kind === "scan" ? !r.verified : (r.sections ?? []).some((s: Dict) => s.tests.some((t: Dict) => t.resulted && !t.verified)));
  const title = r ? `${r.patient_name} - ${kind === "scan" ? r.test_name : "Lab report"}` : "Report";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[94vh] max-w-[880px] overflow-y-auto bg-slate-100 p-4 dark:bg-slate-900">
        <DialogHeader className="flex-row items-center justify-between gap-2 space-y-0 pr-8">
          <DialogTitle className="flex items-center gap-2 text-base">
            <FileText className="h-4 w-4" /> {kind === "scan" ? "Scancare report" : "Lab report"}
            {unverified && <Badge variant="outline" className="border-amber-500/40 text-amber-700 dark:text-amber-400">Not yet verified</Badge>}
          </DialogTitle>
          <Button size="sm" className="gap-1.5" disabled={!r} onClick={() => printReport(sheet.current, title)}>
            <Printer className="h-3.5 w-3.5" /> Print
          </Button>
        </DialogHeader>
        {q.isLoading && <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>}
        {q.error && <p className="py-10 text-center text-sm text-muted-foreground">Couldn't load the report.</p>}
        {r && (
          <div className="rounded-md bg-white p-4 shadow" ref={sheet}>
            <ResultReportSheet report={r} />
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** "View report" - opens the result as Scancare's printed report. */
export function ViewReportButton({ kind, orderIds, label = "View report", size = "sm", variant = "outline", className }: {
  kind: Kind; orderIds: Array<number | string>; label?: string; size?: "sm" | "default"; variant?: "outline" | "default" | "ghost" | "link";
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size={size} variant={variant} className={cn("gap-1.5", className)} onClick={(e) => { e.stopPropagation(); setOpen(true); }}>
        <FileText className="h-3.5 w-3.5" /> {label}
      </Button>
      {open && <ResultReportDialog kind={kind} orderIds={orderIds} open={open} onOpenChange={setOpen} />}
    </>
  );
}
