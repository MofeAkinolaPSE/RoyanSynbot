import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  BadgeCheck, CheckCircle2, Clock, FileSignature, FileText, FlaskConical, KeyRound, Loader2, Pill, ReceiptText,
  RefreshCw, ShieldCheck, Users,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SignaturePad } from "@/components/pharmacy/SignaturePad";
import { PANEL_WIDTH, SectionLabel } from "@/components/shared/panel-shared";
import { naira } from "@/components/billing/billing-shared";
import { api } from "@/lib/api-client";
import { encounterStatusLabel } from "@/lib/encounter-status";
import { motionTransitions } from "@/lib/motion";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

/**
 * HMO Desk (finance meeting, Oct 2026): the HMO officer's own queue - only the HMO patients, as they move through
 * the visit. For each: the HMO and card number, where they are, what was ordered, what the pharmacy has dispensed
 * (it shows here as the pharmacist signs it off), the bills and the HMO's share, and the Royan claims form - which
 * the patient signs on the signature pad and the officer checks before it goes to the HMO.
 */

type Drug = { id: number; drug: string; dosage?: string; duration?: string; quantity?: number; dispensed: boolean; dispensed_at?: string; dispensed_by?: string; cost: number; approval_status?: string };
type Row = {
  encounter_id: number; queue_number?: string; status: string; arrived_at?: string; discharged_at?: string; doctor?: string;
  chief_complaint?: string; patient_id: number; mrn: string; patient_name: string; hmo_name?: string; membership_id?: string;
  diagnoses: { code?: string; description?: string }[]; labs: { test: string; status: string }[]; drugs: Drug[];
  drugs_dispensed: number; bills: any[]; billed: number; hmo_share: number; patient_owes: number; claim_bill_id?: number;
  claim_status?: string; approvals_pending: number; signed: boolean; signed_at?: string; signed_by?: string;
  verified_at?: string; verified_by?: string; verify_note?: string;
};

const LAB_DONE = new Set(["resulted", "verified", "completed"]);
const when = (t?: string) => (t ? new Date(t).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "");

/** `embedded`: shown as the first tab of HMO Desk & Coverage (/hospital/hmo), without its own page title. */
export default function HMODesk({ embedded = false }: { embedded?: boolean }) {
  const navigate = useNavigate();
  const [days, setDays] = useState(0);   // discharged today; the list starts clean each morning
  const [openId, setOpenId] = useState<number | null>(null);
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["hmo-desk", days],
    queryFn: () => api.hospital.coverage.hmoDesk(days),
    refetchInterval: 20_000,
  });
  const rows: Row[] = data?.patients ?? [];
  const s = data?.summary ?? {};
  const active = rows.filter((r) => r.status !== "discharged");
  const done = rows.filter((r) => r.status === "discharged");
  const open = rows.find((r) => r.encounter_id === openId) ?? null;

  const kpis = [
    { label: "HMO patients on the queue", value: s.on_queue ?? 0, icon: <Users className="h-4 w-4" /> },
    { label: "Waiting on pharmacy", value: s.awaiting_pharmacy ?? 0, icon: <Pill className="h-4 w-4" /> },
    { label: "Claims form to sign", value: s.to_sign ?? 0, icon: <FileSignature className="h-4 w-4" /> },
    { label: "Claims to verify", value: s.to_verify ?? 0, icon: <BadgeCheck className="h-4 w-4" /> },
    { label: "Approvals pending", value: s.approvals_pending ?? 0, icon: <KeyRound className="h-4 w-4" /> },
    { label: "HMO share (on this list)", value: naira(s.hmo_share ?? 0), icon: <ShieldCheck className="h-4 w-4" /> },
  ];

  const table = (list: Row[], empty: string) => (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Queue</TableHead><TableHead>Patient</TableHead><TableHead>HMO · card</TableHead><TableHead>Where</TableHead>
          <TableHead>Services</TableHead><TableHead className="text-right">HMO share</TableHead><TableHead className="text-right">Patient owes</TableHead>
          <TableHead>Claims form</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {list.length === 0 ? (
          <TableRow><TableCell colSpan={8} className="py-8 text-center text-foreground/70">{empty}</TableCell></TableRow>
        ) : list.map((r) => {
          const labsDone = r.labs.filter((l) => LAB_DONE.has(l.status)).length;
          return (
            <TableRow key={r.encounter_id} className="cursor-pointer hover:bg-muted/60" onClick={() => setOpenId(r.encounter_id)}>
              <TableCell className="font-mono text-sm font-semibold">{r.queue_number ?? "—"}</TableCell>
              <TableCell><div className="font-semibold">{r.patient_name}</div><div className="font-mono text-xs text-foreground/70">{r.mrn}</div></TableCell>
              <TableCell><div className="font-medium">{r.hmo_name ?? "—"}</div><div className="font-mono text-xs text-foreground/70">{r.membership_id ?? "no card no."}</div></TableCell>
              <TableCell><Badge variant="outline" className="whitespace-nowrap text-xs">{encounterStatusLabel(r.status)}</Badge>
                {r.approvals_pending > 0 && <div className="mt-1 text-xs font-semibold text-orange-700">{r.approvals_pending} approval{r.approvals_pending > 1 ? "s" : ""} pending</div>}</TableCell>
              <TableCell className="text-xs">
                {r.labs.length > 0 && <div>Lab {labsDone}/{r.labs.length} back</div>}
                {r.drugs.length > 0 && <div className={r.drugs_dispensed < r.drugs.length ? "font-semibold text-amber-700" : "text-green-700"}>Drugs {r.drugs_dispensed}/{r.drugs.length} dispensed</div>}
                {!r.labs.length && !r.drugs.length && <span className="text-foreground/70">Consultation</span>}
              </TableCell>
              <TableCell className="text-right font-semibold">{naira(r.hmo_share)}</TableCell>
              <TableCell className={cn("text-right", r.patient_owes > 0 ? "font-semibold text-red-700" : "text-foreground/70")}>{naira(r.patient_owes)}</TableCell>
              <TableCell className="text-xs">
                {!r.bills.length ? <span className="text-foreground/70">No bill yet</span> : (
                  <div className="space-y-0.5">
                    <div className={r.signed ? "text-green-700" : "text-amber-700"}>{r.signed ? "✓ Signed" : "Not signed"}</div>
                    <div className={r.verified_at ? "text-green-700" : "text-foreground/70"}>{r.verified_at ? "✓ Verified" : "Not verified"}</div>
                  </div>
                )}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );

  return (
    <motion.div className="space-y-5" {...motionTransitions.fadeInUp}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        {embedded ? (
          <p className="text-sm text-foreground/75">The HMO patients on today's queue: services, drugs dispensed, bills and the Royan claims form. Eligibility and the patient's package are confirmed on the HMO's own platform.</p>
        ) : (
          <div>
            <h1 className="text-2xl font-bold tracking-tight">HMO Desk</h1>
            <p className="text-sm text-foreground/75">The HMO patients on today's queue: services, drugs dispensed, bills and the Royan claims form.</p>
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => navigate("/hospital/billing?payer=hmo")}><ReceiptText className="h-4 w-4" /> HMO bills</Button>
          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => void refetch()}>
            <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} /> Refresh
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {kpis.map((k) => (
          <Card key={k.label}><CardContent className="p-3">
            <div className="flex items-center justify-between text-xs font-medium text-foreground/75">{k.label}<span className="text-primary">{k.icon}</span></div>
            <div className="mt-1 text-xl font-bold">{k.value}</div>
          </CardContent></Card>
        ))}
      </div>

      <Card><CardContent className="p-0">
        <div className="border-b px-4 py-2.5 text-sm font-semibold">On the queue now ({active.length})</div>
        {isLoading ? <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          : table(active, "No HMO patients on the queue right now.")}
      </CardContent></Card>

      <Card><CardContent className="p-0">
        <div className="flex items-center justify-between border-b px-4 py-2.5">
          <span className="text-sm font-semibold">Discharged {days === 0 ? "today" : `- last ${days} days`} ({done.length})</span>
          <select className="h-8 rounded-md border bg-background px-2 text-xs" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={0}>Today</option><option value={3}>Last 3 days</option><option value={7}>Last 7 days</option><option value={14}>Last 14 days</option>
          </select>
        </div>
        {!isLoading && table(done, "No HMO patients discharged in this period.")}
      </CardContent></Card>

      <Sheet open={!!open} onOpenChange={(o) => !o && setOpenId(null)}>
        <SheetContent className={cn(PANEL_WIDTH.wide, "overflow-y-auto")}>
          {open && <HmoVisitPanel row={open} />}
        </SheetContent>
      </Sheet>
    </motion.div>
  );
}

function HmoVisitPanel({ row: r }: { row: Row }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [sig, setSig] = useState<File | null>(null);
  const [signing, setSigning] = useState(!r.signed);
  const refresh = () => void qc.invalidateQueries({ queryKey: ["hmo-desk"] });
  const fail = (e: any) => toast({ title: "Could not save", description: e?.message, variant: "destructive" });
  const signMut = useMutation({
    mutationFn: () => api.hospital.coverage.hmoDeskSignature(r.encounter_id, sig!),
    onSuccess: () => { toast({ title: "Signature saved on the claims form" }); setSig(null); setSigning(false); refresh(); },
    onError: fail,
  });
  const verifyMut = useMutation({
    mutationFn: (v: boolean) => api.hospital.coverage.hmoDeskVerify(r.encounter_id, v),
    onSuccess: (_d, v) => { toast({ title: v ? "Claim verified" : "Verification withdrawn" }); refresh(); },
    onError: fail,
  });
  const claimsForm = () => r.claim_bill_id && window.open(`#/hospital/billing/${r.claim_bill_id}/invoice?claims=1`, "_blank");

  return (
    <div className="space-y-5 text-sm">
      <SheetHeader>
        <SheetTitle className="text-lg">{r.patient_name} <span className="font-mono text-sm font-normal text-foreground/70">{r.mrn}</span></SheetTitle>
        <p className="text-sm">
          <span className="font-semibold">{r.hmo_name ?? "HMO"}</span> · card <span className="font-mono">{r.membership_id ?? "—"}</span> · {r.queue_number ?? ""} · {encounterStatusLabel(r.status)}
          {r.doctor ? ` · Dr ${r.doctor.replace(/^Dr\.?\s*/i, "")}` : ""}
        </p>
      </SheetHeader>

      <div className="flex flex-wrap gap-2">
        <Button className="gap-1.5" disabled={!r.claim_bill_id} onClick={claimsForm}><FileText className="h-4 w-4" /> Open Royan claims form</Button>
        <Button variant="outline" className="gap-1.5" onClick={() => navigate(`/hospital/patients/${r.mrn}`)}>Patient record</Button>
        {r.approvals_pending > 0 && <Button variant="outline" className="gap-1.5 border-orange-400 text-orange-800" onClick={() => navigate("/hospital/hmo")}><KeyRound className="h-4 w-4" /> {r.approvals_pending} approval(s) to decide</Button>}
      </div>
      {!r.claim_bill_id && <p className="text-xs text-foreground/75">The claims form opens once the visit has a bill.</p>}

      <section>
        <SectionLabel icon={<FlaskConical className="h-3.5 w-3.5" />} label="Diagnosis and investigations" />
        <p><span className="font-medium">Complaint:</span> {r.chief_complaint || "—"}</p>
        <p><span className="font-medium">Diagnosis:</span> {r.diagnoses.length ? r.diagnoses.map((d) => `${d.description ?? ""}${d.code ? ` (${d.code})` : ""}`).join("; ") : "not yet entered by the doctor"}</p>
        {r.labs.length > 0 && <p><span className="font-medium">Lab:</span> {r.labs.map((l) => `${l.test} - ${LAB_DONE.has(l.status) ? "result out" : l.status.replace(/_/g, " ")}`).join("; ")}</p>}
      </section>

      <section>
        <SectionLabel icon={<Pill className="h-3.5 w-3.5" />} label="Drugs (pharmacy sign-off)" />
        {r.drugs.length === 0 ? <p className="text-foreground/70">No drugs prescribed.</p> : (
          <table className="w-full">
            <thead><tr className="text-left text-xs text-foreground/70"><th className="py-1">Drug</th><th>Dosage</th><th>Qty</th><th>Pharmacy</th><th className="text-right">Cost</th></tr></thead>
            <tbody>
              {r.drugs.map((d) => (
                <tr key={d.id} className="border-t">
                  <td className="py-1.5 font-medium">{d.drug}</td><td>{[d.dosage, d.duration].filter(Boolean).join(" · ")}</td><td>{d.quantity ?? ""}</td>
                  <td>{d.dispensed
                    ? <span className="inline-flex items-center gap-1 text-green-700"><CheckCircle2 className="h-3.5 w-3.5" /> Dispensed {when(d.dispensed_at)}</span>
                    : <span className="inline-flex items-center gap-1 text-amber-700"><Clock className="h-3.5 w-3.5" /> {d.approval_status === "pending" ? "Awaiting approval" : "Waiting at pharmacy"}</span>}</td>
                  <td className="text-right">{d.cost ? naira(d.cost) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section>
        <SectionLabel icon={<ReceiptText className="h-3.5 w-3.5" />} label="Bills" />
        {r.bills.length === 0 ? <p className="text-foreground/70">No bill yet.</p> : (
          <table className="w-full">
            <thead><tr className="text-left text-xs text-foreground/70"><th className="py-1">Bill</th><th className="text-right">Billed</th><th className="text-right">HMO share</th><th className="text-right">Patient owes</th><th>Claim</th><th /></tr></thead>
            <tbody>
              {r.bills.map((b) => (
                <tr key={b.id} className="border-t">
                  <td className="py-1.5 font-mono text-xs">{b.bill_number}</td>
                  <td className="text-right">{naira(b.subtotal - b.discount)}</td>
                  <td className="text-right font-semibold">{naira(b.hmo_covered)}</td>
                  <td className="text-right">{naira(Math.max(b.patient_balance - b.paid, 0))}</td>
                  <td className="text-xs capitalize">{b.claim_status ?? "—"}</td>
                  <td className="text-right"><Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => window.open(`#/hospital/billing/${b.id}/invoice`, "_blank")}>Invoice</Button></td>
                </tr>
              ))}
              <tr className="border-t font-semibold"><td className="py-1.5">Total</td><td className="text-right">{naira(r.billed)}</td><td className="text-right">{naira(r.hmo_share)}</td><td className="text-right">{naira(r.patient_owes)}</td><td /><td /></tr>
            </tbody>
          </table>
        )}
      </section>

      <section className="space-y-2">
        <SectionLabel icon={<FileSignature className="h-3.5 w-3.5" />} label="Patient's signature on the claims form" />
        {r.signed && !signing ? (
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-green-700"><CheckCircle2 className="mr-1 inline h-4 w-4" />Signed{r.signed_at ? ` ${when(r.signed_at)}` : " at the pharmacy"}</span>
            <Button size="sm" variant="outline" onClick={() => setSigning(true)}>Sign again</Button>
          </div>
        ) : (
          <>
            <p className="text-xs text-foreground/75">The patient signs on the signature pad (or this screen with a finger or stylus); it goes straight onto the claims form.</p>
            <SignaturePad onChange={setSig} />
            <div className="flex gap-2">
              <Button size="sm" disabled={!sig || signMut.isPending} onClick={() => signMut.mutate()}>
                {signMut.isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}Save signature
              </Button>
              {r.signed && <Button size="sm" variant="ghost" onClick={() => setSigning(false)}>Cancel</Button>}
            </div>
          </>
        )}
      </section>

      <section className="space-y-2">
        <SectionLabel icon={<BadgeCheck className="h-3.5 w-3.5" />} label="HMO officer's check" />
        {r.verified_at ? (
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-green-700"><CheckCircle2 className="mr-1 inline h-4 w-4" />Verified {when(r.verified_at)}{r.verified_by ? ` by ${r.verified_by}` : ""}</span>
            <Button size="sm" variant="ghost" onClick={() => verifyMut.mutate(false)}>Undo</Button>
          </div>
        ) : (
          <Button size="sm" variant="outline" className="gap-1.5" disabled={!r.claim_bill_id || verifyMut.isPending} onClick={() => verifyMut.mutate(true)}>
            <BadgeCheck className="h-4 w-4" /> I have checked the claims form
          </Button>
        )}
      </section>
    </div>
  );
}
