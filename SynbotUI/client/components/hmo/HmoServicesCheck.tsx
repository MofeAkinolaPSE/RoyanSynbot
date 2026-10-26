/**
 * What the HMO covers on this visit (migration 244, backend services/hmo_review.py).
 *
 * The HMO team goes through an HMO patient's billed services before the claims form: covered, or not covered - then
 * the patient pays for it at the cashier before it is given, and it stays off the claim. A service the patient needs
 * that is not covered can be put to the HMO provider: the doctor, the cashier or the HMO team requests approval (the
 * service is held meanwhile) and the HMO team records the answer - approved with the HMO's authorisation code (back
 * on the claim), or declined (the patient pays).
 *
 * Shown on the HMO Desk, the cashier's bill and the doctor's visit. Renders nothing for a private visit.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock, Loader2, ShieldAlert, ShieldCheck, ShieldQuestion, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SectionLabel } from "@/components/shared/panel-shared";
import { naira } from "@/components/billing/billing-shared";
import { useAuth } from "@/components/AuthProvider";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";

type Svc = Record<string, any>;
type Ask = { id: number; kind: "not_covered" | "request" | "approve" | "decline" } | null;
const DECIDERS = ["hmo", "admin", "finance"];

function StateBadge({ s }: { s: Svc }) {
  if (s.state === "approval_requested")
    return <Badge variant="outline" className="gap-1 border-amber-500/50 text-amber-700 dark:text-amber-400"><Clock className="h-3 w-3" /> Awaiting HMO approval</Badge>;
  if (s.hmo_decision === "not_covered")
    return <Badge variant="outline" className="gap-1 border-red-500/50 text-red-700 dark:text-red-400"><XCircle className="h-3 w-3" />
      Not covered{s.hmo_approval_status === "declined" ? " (HMO declined)" : ""} - patient pays{s.bill_paid ? " · paid" : ""}</Badge>;
  if (s.hmo_decision === "covered")
    return <Badge variant="outline" className="gap-1 border-green-500/50 text-green-700 dark:text-green-400"><CheckCircle2 className="h-3 w-3" />
      Covered{s.hmo_approval_code ? ` · code ${s.hmo_approval_code}` : ""}</Badge>;
  return <Badge variant="outline" className="gap-1 text-foreground/70"><ShieldQuestion className="h-3 w-3" /> Not checked yet</Badge>;
}

export function HmoServicesCheck({ encounterId, title = "What the HMO covers", className }: {
  encounterId: number | string; title?: string; className?: string;
}) {
  const { roles } = useAuth();
  const canDecide = (roles ?? []).some((r) => DECIDERS.includes(String(r).toLowerCase()));
  const qc = useQueryClient();
  const { toast } = useToast();
  const [ask, setAsk] = useState<Ask>(null);
  const [text, setText] = useState("");

  const key = ["hmo-visit-services", String(encounterId)];
  const { data, isLoading } = useQuery({
    queryKey: key,
    queryFn: () => api.hospital.coverage.visitServices(encounterId),
    refetchInterval: 20_000,
    enabled: !!encounterId,
  });
  const services: Svc[] = data?.services ?? [];

  const done = (msg: string) => {
    toast({ title: msg });
    setAsk(null);
    setText("");
    void qc.invalidateQueries({ queryKey: key });
    void qc.invalidateQueries({ queryKey: ["hmo-desk"] });
    void qc.invalidateQueries({ queryKey: ["hospital-bills"] });
    void qc.invalidateQueries({ queryKey: ["hospital-bill"] });
  };
  const fail = (e: any) => toast({ title: "Could not save", description: e?.message, variant: "destructive" });
  const decide = useMutation({
    mutationFn: (p: { id: number; decision: "covered" | "not_covered"; note?: string }) => api.hospital.coverage.decideService(p.id, p.decision, p.note),
    onSuccess: (_d, p) => done(p.decision === "covered" ? "Marked covered by the HMO" : "Not covered - moved to the patient to pay"),
    onError: fail,
  });
  const request = useMutation({
    mutationFn: (p: { id: number; reason: string }) => api.hospital.coverage.requestServiceApproval(p.id, p.reason),
    onSuccess: () => done("Approval requested - the HMO team will ask the HMO"),
    onError: fail,
  });
  const answer = useMutation({
    mutationFn: (p: { id: number; approved: boolean; code?: string; note?: string }) =>
      api.hospital.coverage.answerServiceApproval(p.id, { approved: p.approved, authorization_code: p.code, note: p.note }),
    onSuccess: (_d, p) => done(p.approved ? "Approved by the HMO - back on the claim" : "Declined by the HMO - the patient pays"),
    onError: fail,
  });
  const busy = decide.isPending || request.isPending || answer.isPending;

  if (isLoading) return null;
  if (!data?.is_hmo || services.length === 0) return null;
  const sm = data.summary ?? {};

  const submit = () => {
    if (!ask) return;
    const t = text.trim();
    if (ask.kind === "not_covered") decide.mutate({ id: ask.id, decision: "not_covered", note: t || undefined });
    if (ask.kind === "request") t && request.mutate({ id: ask.id, reason: t });
    if (ask.kind === "approve") t && answer.mutate({ id: ask.id, approved: true, code: t });
    if (ask.kind === "decline") answer.mutate({ id: ask.id, approved: false, note: t || undefined });
  };
  const prompt: Record<string, { label: string; placeholder: string; required: boolean; cta: string }> = {
    not_covered: { label: "Why is it not covered? (optional)", placeholder: "e.g. not on the patient's plan", required: false, cta: "Mark not covered" },
    request: { label: "Why does the patient need it? The HMO team sends this to the HMO.", placeholder: "e.g. clinically indicated - suspected typhoid", required: true, cta: "Request HMO approval" },
    approve: { label: "The HMO's authorisation code", placeholder: "e.g. AUTH-123456", required: true, cta: "Record approval" },
    decline: { label: "The HMO's reason (optional)", placeholder: "e.g. excluded on the plan", required: false, cta: "Record decline" },
  };

  return (
    <section className={cn("space-y-2", className)} data-tour-id="hmo-services-check">
      <SectionLabel icon={<ShieldCheck className="h-3.5 w-3.5" />} label={title} />
      <p className="text-xs text-foreground/75">
        {data.hmo_name ?? "HMO"}{data.membership_id ? ` · card ${data.membership_id}` : ""}. HMO pays {naira(sm.hmo_total ?? 0)} · patient pays {naira(sm.patient_total ?? 0)}
        {sm.unchecked ? ` · ${sm.unchecked} not checked yet` : ""}{sm.approval_requested ? ` · ${sm.approval_requested} awaiting the HMO` : ""}.
        {canDecide ? " Mark anything the plan does not cover before the claims form goes out." : " The HMO team marks what the plan covers; you can ask for approval of a needed service it does not."}
      </p>
      <div className="divide-y rounded-md border">
        {services.map((s) => (
          <div key={s.id} className={cn("space-y-2 p-2.5", s.hmo_decision === "not_covered" && "bg-red-50/60 dark:bg-red-500/5")}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm font-medium">{s.description}</p>
                <p className="text-xs capitalize text-foreground/70">{String(s.category ?? "").replace(/_/g, " ")} · {naira(s.gross_amount)} · {s.bill_number}</p>
              </div>
              <StateBadge s={s} />
            </div>
            {(s.hmo_decision_note || s.hmo_approval_reason) && (
              <p className="text-xs text-foreground/75">
                {s.hmo_decision_note && <>Note: {s.hmo_decision_note}. </>}
                {s.hmo_approval_reason && <>Requested by {s.hmo_approval_requested_by}: "{s.hmo_approval_reason}"</>}
              </p>
            )}
            <div className="flex flex-wrap gap-1.5">
              {canDecide && s.state !== "approval_requested" && s.hmo_decision !== "covered" && (
                <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" disabled={busy || s.bill_paid && s.hmo_decision === "not_covered"}
                  onClick={() => decide.mutate({ id: s.id, decision: "covered" })}>
                  <CheckCircle2 className="h-3.5 w-3.5" /> Covered
                </Button>
              )}
              {canDecide && s.hmo_decision !== "not_covered" && (
                <Button size="sm" variant="outline" className="h-7 gap-1 border-red-300 text-xs text-red-700" disabled={busy}
                  onClick={() => { setAsk({ id: s.id, kind: "not_covered" }); setText(""); }}>
                  <XCircle className="h-3.5 w-3.5" /> Not covered
                </Button>
              )}
              {s.hmo_decision === "not_covered" && s.state !== "approval_requested" && !s.bill_paid && (
                <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" disabled={busy}
                  onClick={() => { setAsk({ id: s.id, kind: "request" }); setText(""); }}>
                  <ShieldAlert className="h-3.5 w-3.5" /> Request HMO approval
                </Button>
              )}
              {canDecide && s.state === "approval_requested" && (
                <>
                  <Button size="sm" className="h-7 gap-1 text-xs" disabled={busy} onClick={() => { setAsk({ id: s.id, kind: "approve" }); setText(""); }}>
                    <CheckCircle2 className="h-3.5 w-3.5" /> HMO approved
                  </Button>
                  <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" disabled={busy} onClick={() => { setAsk({ id: s.id, kind: "decline" }); setText(""); }}>
                    <XCircle className="h-3.5 w-3.5" /> HMO declined
                  </Button>
                </>
              )}
              {!canDecide && s.state === "approval_requested" && (
                <span className="text-xs text-amber-700 dark:text-amber-400">Held until the HMO team records the HMO's answer (or the patient pays).</span>
              )}
            </div>
            {ask?.id === s.id && (
              <div className="space-y-1.5 rounded-md bg-muted/50 p-2">
                <p className="text-xs font-medium">{prompt[ask.kind].label}</p>
                <div className="flex gap-1.5">
                  <Input className="h-8 text-sm" autoFocus value={text} placeholder={prompt[ask.kind].placeholder}
                    onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} />
                  <Button size="sm" className="h-8" disabled={busy || (prompt[ask.kind].required && !text.trim())} onClick={submit}>
                    {busy && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}{prompt[ask.kind].cta}
                  </Button>
                  <Button size="sm" variant="ghost" className="h-8" onClick={() => setAsk(null)}>Cancel</Button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
