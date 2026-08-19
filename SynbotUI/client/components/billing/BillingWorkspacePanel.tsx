import { Fragment, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  User, ReceiptText, CreditCard, Building, Plus, ExternalLink, Loader2,
  ShieldOff, Ban, Printer,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/components/AuthProvider";
import {
  fmtDate, elapsed, naira, BillBadge, ClaimBadge, DetailRow,
  PAYMENT_METHODS, CLAIM_STATUSES, OPEN_BILL_STATUSES,
} from "@/components/billing/billing-shared";

interface BillingWorkspacePanelProps {
  bill: {
    id: number;
    patient_id?: number;
    patient_name?: string;
    patient_mrn?: string;
    encounter_id?: number;
    bill_number?: string;
    status?: string;
    billed_at?: string;
  } & Record<string, any>;
  onClose: () => void;
  initialTab?: string;
}

const emptyPayment = { amount: "", payment_method: "cash", reference: "" };
const emptyClaim = { insurer_name: "", claim_amount: "", notes: "" };
const emptyClaimUpdate = { status: "approved", authorisation_code: "", approved_amount: "", notes: "" };

export function BillingWorkspacePanel({ bill: initialBill, onClose, initialTab }: BillingWorkspacePanelProps) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { roles } = useAuth();
  const isAdmin = roles.includes("admin");
  const qc = useQueryClient();
  const [tab, setTab] = useState(initialTab ?? "detail");

  const [paymentFormOpen, setPaymentFormOpen] = useState(false);
  const [paymentForm, setPaymentForm] = useState({ ...emptyPayment });
  const [claimFormOpen, setClaimFormOpen] = useState(false);
  const [claimForm, setClaimForm] = useState({ ...emptyClaim });
  const [editingClaimId, setEditingClaimId] = useState<number | null>(null);
  const [claimUpdateForm, setClaimUpdateForm] = useState({ ...emptyClaimUpdate });

  const billId = String(initialBill.id);

  const { data, isLoading } = useQuery({
    queryKey: ["billing-panel-detail", billId],
    queryFn: () => api.hospital.billing.getBill(billId),
    refetchInterval: 15_000,
  });
  const bill: typeof initialBill = { ...initialBill, ...(data?.bill ?? {}) };
  const items: any[] = data?.items ?? [];
  const payments: any[] = data?.payments ?? [];
  const claims: any[] = data?.claims ?? [];

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ["billing-panel-detail", billId] });
    void qc.invalidateQueries({ queryKey: ["hospital-bills"] });
    void qc.invalidateQueries({ queryKey: ["hospital-billing-stats"] });
  };

  const paymentMut = useMutation({
    mutationFn: () => api.hospital.billing.recordPayment(billId, {
      amount: Number(paymentForm.amount),
      payment_method: paymentForm.payment_method,
      reference: paymentForm.reference || undefined,
    }),
    onSuccess: (res: any) => {
      toast({ title: "Payment recorded", description: `Bill status: ${res.bill_status}` });
      setPaymentForm({ ...emptyPayment });
      setPaymentFormOpen(false);
      invalidateAll();
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const waiveMut = useMutation({
    mutationFn: () => api.hospital.billing.waiveBill(billId, {}),
    onSuccess: () => { toast({ title: "Bill waived" }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const writeOffMut = useMutation({
    mutationFn: () => api.hospital.billing.writeOffBill(billId, {}),
    onSuccess: () => { toast({ title: "Bill written off" }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const claimMut = useMutation({
    mutationFn: () => api.hospital.billing.createClaim({
      ...claimForm,
      claim_amount: Number(claimForm.claim_amount),
      bill_id: initialBill.id,
    }),
    onSuccess: () => {
      toast({ title: "HMO claim submitted" });
      setClaimForm({ ...emptyClaim });
      setClaimFormOpen(false);
      invalidateAll();
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const claimUpdateMut = useMutation({
    mutationFn: (vars: { claimId: number; status: string; authorisation_code?: string; approved_amount?: string; notes?: string }) =>
      api.hospital.billing.updateClaim(String(vars.claimId), {
        status: vars.status,
        authorisation_code: vars.authorisation_code || undefined,
        approved_amount: vars.approved_amount ? Number(vars.approved_amount) : undefined,
        notes: vars.notes || undefined,
      }),
    onSuccess: () => {
      toast({ title: "Claim updated" });
      setEditingClaimId(null);
      invalidateAll();
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const status = bill.status;
  const isOpen = OPEN_BILL_STATUSES.includes(status as any);

  return (
    <Sheet open onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className="w-[560px] sm:w-[640px] overflow-y-auto p-0 flex flex-col" side="right">
        {isLoading && !data ? (
          <LoadingSkeleton />
        ) : (
          <>
            <SheetHeader className="px-5 pt-5 pb-4 border-b shrink-0">
              <div className="flex items-start gap-3">
                <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                  <ReceiptText className="h-5 w-5 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <SheetTitle className="text-base leading-tight">{bill.bill_number ?? `Bill #${bill.id}`}</SheetTitle>
                  <div className="flex flex-wrap items-center gap-2 mt-1">
                    <span className="text-xs text-muted-foreground">{bill.patient_name ?? `Patient ID ${bill.patient_id}`}</span>
                    {bill.patient_mrn && <Badge variant="outline" className="text-xs font-mono">{bill.patient_mrn}</Badge>}
                    <BillBadge status={status} />
                  </div>
                  <p className="text-[13px] text-muted-foreground mt-1">Billed {elapsed(bill.billed_at)} ago</p>
                </div>
              </div>
            </SheetHeader>

            <Tabs value={tab} onValueChange={setTab} className="flex-1 flex flex-col min-h-0">
              <TabsList className="mx-5 mt-3 bg-muted border border-border shrink-0 flex-wrap h-auto">
                <TabsTrigger value="detail">Detail</TabsTrigger>
                <TabsTrigger value="payments">Payments</TabsTrigger>
                <TabsTrigger value="claims">Claims</TabsTrigger>
              </TabsList>

              <div className="flex-1 overflow-y-auto px-5 py-4">
                {/* ── Detail ── */}
                <TabsContent value="detail" className="mt-0 space-y-4">
                  <section>
                    <SectionLabel icon={<User className="h-3.5 w-3.5" />} label="Patient" />
                    <DetailRow label="Name" value={bill.patient_name} />
                    <DetailRow label="MRN"  value={bill.patient_mrn} mono />
                  </section>
                  <Separator />
                  <section>
                    <SectionLabel icon={<ReceiptText className="h-3.5 w-3.5" />} label="Charges" />
                    <DetailRow label="Consultation" value={bill.consultation_fee ? naira(bill.consultation_fee) : undefined} />
                    <DetailRow label="Lab"          value={bill.lab_charges ? naira(bill.lab_charges) : undefined} />
                    <DetailRow label="Pharmacy"     value={bill.pharmacy_charges ? naira(bill.pharmacy_charges) : undefined} />
                    <DetailRow label="Ward"         value={bill.ward_charges ? naira(bill.ward_charges) : undefined} />
                    <DetailRow label="Procedure"    value={bill.procedure_charges ? naira(bill.procedure_charges) : undefined} />
                    <DetailRow label="Miscellaneous" value={bill.miscellaneous ? naira(bill.miscellaneous) : undefined} />
                    <DetailRow label="Subtotal"     value={naira(bill.subtotal ?? bill.total_amount)} accent="font-semibold" />
                    <DetailRow label="Discount"     value={bill.discount ? naira(bill.discount) : undefined} />
                    <DetailRow label="HMO Covered"  value={bill.hmo_covered ? naira(bill.hmo_covered) : undefined} accent="text-green-500" />
                    <DetailRow label="Patient Balance" value={naira(bill.patient_balance ?? bill.patient_due)} accent="font-semibold" />
                    <DetailRow label="Amount Paid"  value={naira(bill.amount_paid)} accent="text-green-500" />
                    <DetailRow label="Outstanding"  value={naira(bill.outstanding)} accent={(bill.outstanding ?? 0) > 0 ? "text-red-500 font-semibold" : "text-green-500"} />
                  </section>
                  {items.length > 0 && (
                    <>
                      <Separator />
                      <section>
                        <SectionLabel icon={<ReceiptText className="h-3.5 w-3.5" />} label="Line Items" />
                        <ul className="text-xs text-muted-foreground space-y-1">
                          {items.map((it: any) => (
                            <li key={it.id} className="flex justify-between">
                              <span>{it.description} × {it.quantity}</span>
                              <span>{naira(it.quantity * it.unit_price)}</span>
                            </li>
                          ))}
                        </ul>
                      </section>
                    </>
                  )}
                  <Separator />
                  <section>
                    <SectionLabel icon={<User className="h-3.5 w-3.5" />} label="Billing Info" />
                    <DetailRow label="Billed by" value={bill.billed_by} mono />
                    <DetailRow label="Billed at" value={bill.billed_at ? fmtDate(bill.billed_at) : undefined} />
                    <DetailRow label="Notes"     value={bill.notes} />
                  </section>
                </TabsContent>

                {/* ── Payments ── */}
                <TabsContent value="payments" className="mt-0 space-y-3">
                  {payments.length === 0 ? (
                    <p className="text-xs text-muted-foreground">No payments recorded yet.</p>
                  ) : (
                    <div className="rounded-md border overflow-x-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="text-xs">Date</TableHead>
                            <TableHead className="text-xs">Amount</TableHead>
                            <TableHead className="text-xs">Method</TableHead>
                            <TableHead className="text-xs">Reference</TableHead>
                            <TableHead className="text-xs">By</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {payments.map((p: any) => (
                            <TableRow key={p.id}>
                              <TableCell className="text-[13px] text-muted-foreground whitespace-nowrap">{fmtDate(p.received_at)}</TableCell>
                              <TableCell className="text-xs font-semibold text-green-500">{naira(p.amount)}</TableCell>
                              <TableCell className="text-xs uppercase">{p.payment_method}</TableCell>
                              <TableCell className="text-xs text-muted-foreground">{p.reference ?? "—"}</TableCell>
                              <TableCell className="text-[13px] text-muted-foreground">{p.received_by ?? "—"}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}

                  {isOpen && (!paymentFormOpen ? (
                    <Button size="sm" variant="outline" className="w-full gap-1.5" onClick={() => setPaymentFormOpen(true)}>
                      <Plus className="h-3.5 w-3.5" /> Record Payment
                    </Button>
                  ) : (
                    <section className="space-y-2 border-t pt-3">
                      <div className="space-y-1">
                        <Label>Amount (₦) *</Label>
                        <Input type="number" min="0" value={paymentForm.amount}
                          onChange={e => setPaymentForm(f => ({ ...f, amount: e.target.value }))} placeholder="e.g. 5000" />
                      </div>
                      <div className="space-y-1">
                        <Label>Payment Method</Label>
                        <Select value={paymentForm.payment_method} onValueChange={v => setPaymentForm(f => ({ ...f, payment_method: v }))}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {PAYMENT_METHODS.map(m => <SelectItem key={m} value={m} className="uppercase">{m}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1">
                        <Label>Reference / Receipt #</Label>
                        <Input value={paymentForm.reference} onChange={e => setPaymentForm(f => ({ ...f, reference: e.target.value }))}
                          placeholder="Transaction reference (optional)" />
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" className="flex-1" onClick={() => { setPaymentFormOpen(false); setPaymentForm({ ...emptyPayment }); }}>Cancel</Button>
                        <Button size="sm" className="flex-1 gap-1.5" disabled={!paymentForm.amount || paymentMut.isPending} onClick={() => paymentMut.mutate()}>
                          {paymentMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Record Payment
                        </Button>
                      </div>
                    </section>
                  ))}
                </TabsContent>

                {/* ── Claims ── */}
                <TabsContent value="claims" className="mt-0 space-y-3">
                  {claims.length === 0 ? (
                    <p className="text-xs text-muted-foreground">No HMO claims submitted yet.</p>
                  ) : (
                    <div className="space-y-2">
                      {claims.map((c: any) => {
                        const terminal = ["paid", "rejected"].includes(c.status);
                        return (
                          <Fragment key={c.id}>
                            <div className="rounded-md border p-2.5 space-y-1.5">
                              <div className="flex items-start justify-between gap-2">
                                <p className="text-sm font-medium">{c.insurer_name ?? c.hmo_provider}</p>
                                <ClaimBadge status={c.status} />
                              </div>
                              <p className="text-xs text-muted-foreground">Claim: {naira(c.claim_amount)}{c.approved_amount != null && <> · Approved: {naira(c.approved_amount)}</>}</p>
                              {c.notes && <p className="text-xs text-muted-foreground">{c.notes}</p>}
                              <div className="flex items-center justify-between">
                                <p className="text-[13px] text-muted-foreground">{fmtDate(c.submitted_at)}</p>
                                {!terminal && (
                                  <Button size="sm" variant="ghost" className="h-6 px-2 text-[13px]"
                                    onClick={() => { setEditingClaimId(c.id); setClaimUpdateForm({ ...emptyClaimUpdate }); }}>
                                    Update Status
                                  </Button>
                                )}
                              </div>
                            </div>
                            {editingClaimId === c.id && (
                              <div className="rounded-md border border-primary/30 bg-muted/30 p-2 space-y-2">
                                <Select value={claimUpdateForm.status} onValueChange={v => setClaimUpdateForm(f => ({ ...f, status: v }))}>
                                  <SelectTrigger><SelectValue /></SelectTrigger>
                                  <SelectContent>
                                    {CLAIM_STATUSES.map(s => (
                                      <SelectItem key={s} value={s} className="capitalize">{s.replace(/_/g, " ")}</SelectItem>
                                    ))}
                                  </SelectContent>
                                </Select>
                                <div className="grid grid-cols-2 gap-2">
                                  <Input placeholder="Authorisation code" value={claimUpdateForm.authorisation_code}
                                    onChange={e => setClaimUpdateForm(f => ({ ...f, authorisation_code: e.target.value }))} />
                                  <Input type="number" placeholder="Approved amount" value={claimUpdateForm.approved_amount}
                                    onChange={e => setClaimUpdateForm(f => ({ ...f, approved_amount: e.target.value }))} />
                                </div>
                                <Textarea rows={2} placeholder="Notes (optional)" value={claimUpdateForm.notes}
                                  onChange={e => setClaimUpdateForm(f => ({ ...f, notes: e.target.value }))} />
                                <div className="flex gap-2">
                                  <Button size="sm" variant="outline" className="flex-1" onClick={() => setEditingClaimId(null)}>Cancel</Button>
                                  <Button size="sm" className="flex-1" disabled={claimUpdateMut.isPending}
                                    onClick={() => claimUpdateMut.mutate({ claimId: c.id, ...claimUpdateForm })}>
                                    {claimUpdateMut.isPending && <Loader2 className="h-3 w-3 animate-spin mr-1" />}Save
                                  </Button>
                                </div>
                              </div>
                            )}
                          </Fragment>
                        );
                      })}
                    </div>
                  )}

                  {isOpen && (!claimFormOpen ? (
                    <Button size="sm" variant="outline" className="w-full gap-1.5" onClick={() => setClaimFormOpen(true)}>
                      <Plus className="h-3.5 w-3.5" /> Submit HMO Claim
                    </Button>
                  ) : (
                    <section className="space-y-2 border-t pt-3">
                      <div className="space-y-1">
                        <Label>Insurer Name *</Label>
                        <Input value={claimForm.insurer_name} onChange={e => setClaimForm(f => ({ ...f, insurer_name: e.target.value }))}
                          placeholder="e.g. NHIS, Hygeia, Reliance HMO" />
                      </div>
                      <div className="space-y-1">
                        <Label>Claim Amount (₦) *</Label>
                        <Input type="number" min="0" value={claimForm.claim_amount} onChange={e => setClaimForm(f => ({ ...f, claim_amount: e.target.value }))}
                          placeholder="Amount to claim" />
                      </div>
                      <div className="space-y-1">
                        <Label>Notes</Label>
                        <Input value={claimForm.notes} onChange={e => setClaimForm(f => ({ ...f, notes: e.target.value }))}
                          placeholder="Any additional notes" />
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" className="flex-1" onClick={() => { setClaimFormOpen(false); setClaimForm({ ...emptyClaim }); }}>Cancel</Button>
                        <Button size="sm" className="flex-1 gap-1.5"
                          disabled={!claimForm.insurer_name.trim() || !claimForm.claim_amount || claimMut.isPending}
                          onClick={() => claimMut.mutate()}>
                          {claimMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Submit Claim
                        </Button>
                      </div>
                    </section>
                  ))}
                </TabsContent>
              </div>
            </Tabs>

            <Separator className="shrink-0" />
            <div className="px-5 py-3 flex flex-wrap gap-2 shrink-0">
              {isOpen && (
                <Button size="sm" variant="outline" className="gap-1.5" onClick={() => { setTab("payments"); setPaymentFormOpen(true); }}>
                  <CreditCard className="h-3.5 w-3.5" /> Record Payment
                </Button>
              )}
              {isOpen && isAdmin && (
                <Button size="sm" variant="outline" className="gap-1.5 text-purple-500 border-purple-500/30 hover:bg-purple-500/10"
                  disabled={waiveMut.isPending}
                  onClick={() => { if (window.confirm("Waive the remaining outstanding balance on this bill? This is logged and cannot be undone.")) waiveMut.mutate(); }}>
                  <ShieldOff className="h-3.5 w-3.5" /> Waive
                </Button>
              )}
              {isOpen && isAdmin && (
                <Button size="sm" variant="outline" className="gap-1.5 text-red-500 border-red-500/30 hover:bg-red-500/10"
                  disabled={writeOffMut.isPending}
                  onClick={() => { if (window.confirm("Write off this bill as uncollectable? This is logged and cannot be undone.")) writeOffMut.mutate(); }}>
                  <Ban className="h-3.5 w-3.5" /> Write Off
                </Button>
              )}
              {isOpen && (
                <Button size="sm" variant="outline" className="gap-1.5" onClick={() => { setTab("claims"); setClaimFormOpen(true); }}>
                  <Building className="h-3.5 w-3.5" /> Submit HMO Claim
                </Button>
              )}
              <Button size="sm" variant="outline" className="gap-1.5"
                onClick={() => window.open(`${window.location.origin}${window.location.pathname}#/hospital/billing/${bill.id}/invoice`, "_blank")}>
                <Printer className="h-3.5 w-3.5" /> Print Invoice
              </Button>
              <Button size="sm" variant="ghost" className="gap-1.5 ml-auto"
                disabled={!bill.patient_mrn}
                onClick={() => { if (bill.patient_mrn) { navigate(`/hospital/patients/${bill.patient_mrn}`); onClose(); } }}>
                <ExternalLink className="h-3.5 w-3.5" /> Open Patient Record
              </Button>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function SectionLabel({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <span className="text-muted-foreground">{icon}</span>
      <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{label}</span>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="p-5 space-y-4">
      <div className="flex items-center gap-3">
        <Skeleton className="h-10 w-10 rounded-full" />
        <div className="space-y-2 flex-1"><Skeleton className="h-4 w-40" /><Skeleton className="h-3 w-28" /></div>
      </div>
      <Skeleton className="h-16 w-full" />
      <Skeleton className="h-20 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}
