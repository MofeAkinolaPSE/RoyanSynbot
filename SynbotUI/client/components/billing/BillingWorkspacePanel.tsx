import { Fragment, useEffect, useState } from "react";
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
  ShieldOff, Ban, Printer, Percent, Undo2, Unlock, FileText, Wallet
} from "lucide-react";
import { api } from "@/lib/api-client";
import { HmoServicesCheck } from "@/components/hmo/HmoServicesCheck";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/components/AuthProvider";
import { SectionLabel, PANEL_WIDTH } from "@/components/shared/panel-shared";
import { cn } from "@/lib/utils";
import { CorrectionPen } from "@/components/billing/CorrectionPen";
import { askConfirm, askText } from "@/lib/ask";
import {
  fmtDate, elapsed, naira, BillBadge, ClaimBadge, DetailRow,
  PAYMENT_METHODS, PAYMENT_METHOD_LABELS, CLAIM_STATUSES, OPEN_BILL_STATUSES,
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
  /** Open straight on "receive payment", the amount pre-filled with what is outstanding. */
  receive?: boolean;
}

const emptyPayment = { amount: "", payment_method: "pos", reference: "" };
const emptyClaim = { insurer_name: "", claim_amount: "", notes: "" };
const emptyClaimUpdate = { status: "approved", authorisation_code: "", approved_amount: "", notes: "" };

export function BillingWorkspacePanel({ bill: initialBill, onClose, initialTab, receive }: BillingWorkspacePanelProps) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { roles } = useAuth();
  const isAdmin = roles.includes("admin");
  const qc = useQueryClient();
  const [tab, setTab] = useState(initialTab ?? (receive ? "payments" : "detail"));

  const [paymentFormOpen, setPaymentFormOpen] = useState(!!receive);
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

  const [discountAmount, setDiscountAmount] = useState("");
  const [discountReason, setDiscountReason] = useState("");

  const discountMut = useMutation({
    mutationFn: () =>
      api.hospital.billing.requestDiscount(
        bill.id, Number(discountAmount), discountReason.trim() || undefined,
      ),
    onSuccess: () => {
      setDiscountAmount("");
      setDiscountReason("");
      void qc.invalidateQueries({ queryKey: ["bill", bill.id] });
      void qc.invalidateQueries({ queryKey: ["hospital-bills"] });
      toast({
        title: "Discount sent for approval",
        description: "The bill cannot be settled until an admin decides.",
      });
    },
    onError: (e: any) =>
      toast({ title: "Could not apply discount", description: e?.message, variant: "destructive" }),
  });

  const paymentMut = useMutation({
    mutationFn: () => api.hospital.billing.recordPayment(billId, {
      amount: Number(paymentForm.amount),
      payment_method: paymentForm.payment_method,
      reference: paymentForm.reference || undefined,
    }),
    onSuccess: (res: any) => {
      toast({ title: `Receipt ${res.payment?.receipt_number ?? ""} issued`, description: `Bill is now ${res.bill_status}. Posted to the books.` });
      if (res.payment_id ?? res.payment?.id) window.open(`#/hospital/billing/${billId}/invoice?receipt=${res.payment_id ?? res.payment?.id}`, "_blank");
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

  // Corrections at the cashier: a receipt keyed wrongly is voided (with a reason) and the right one recorded; a bill
  // raised wrongly is voided once its receipts are voided, and the orders can then be billed again. Roy Books follows.
  const booksNote = (res: any) => res?.books?.message ? ` Roy Books: ${res.books.message}` : "";
  const voidPaymentMut = useMutation({
    mutationFn: (v: { id: number; reason: string }) => api.hospital.billing.voidPayment(v.id, v.reason),
    onSuccess: (res: any) => {
      toast({ title: "Receipt voided", description: `Bill is now ${res.bill_status}. Record the correct receipt below.${booksNote(res)}` });
      setPaymentFormOpen(true);
      invalidateAll();
    },
    onError: (e: any) => toast({ title: "Could not void the receipt", description: e.message, variant: "destructive" }),
  });
  const voidBillMut = useMutation({
    mutationFn: (reason: string) => api.hospital.billing.voidBill(billId, reason),
    onSuccess: (res: any) => {
      toast({ title: "Bill voided", description: `Its orders can be billed again (Send to cashier).${booksNote(res)}` });
      invalidateAll();
    },
    onError: (e: any) => toast({ title: "Could not void the bill", description: e.message, variant: "destructive" }),
  });
  const releaseMut = useMutation({
    mutationFn: (reason: string) => api.hospital.billing.releaseBill(billId, reason),
    onSuccess: () => { toast({ title: "Services released", description: "Lab, scan and pharmacy can now serve this bill; the balance stays on the patient's account." }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Could not release", description: e.message, variant: "destructive" }),
  });
  const askVoidPayment = async (p: any) => {
    const reason = await askText(`Void receipt ${p.receipt_number ?? "#" + p.id} for ${naira(p.amount)}?\nGive the reason (wrong amount, wrong method, wrong patient...). You can record the correct receipt straight after.`);
    if (reason && reason.trim().length >= 3) voidPaymentMut.mutate({ id: p.id, reason: reason.trim() });
  };
  const askVoidBill = async () => {
    const reason = await askText(`Void bill ${bill.bill_number ?? "#" + bill.id}?\nThe invoice is reversed in Roy Books and its orders can be billed again. Give the reason.`);
    if (reason && reason.trim().length >= 3) voidBillMut.mutate(reason.trim());
  };
  const askRelease = async () => {
    const reason = await askText("Release services on a part-paid bill?\nThe patient may go to lab / scan / pharmacy now; the balance stays on their account. Give the reason.", "Part payment accepted");
    if (reason && reason.trim().length >= 3) releaseMut.mutate(reason.trim());
  };
  const standingPayments = payments.filter((p: any) => (p.status ?? "posted") !== "void");
  const isHmo = Number(bill.hmo_covered ?? 0) > 0 || !!bill.hmo_id;

  const status = bill.status;
  const isOpen = OPEN_BILL_STATUSES.includes(status as any);
  const outstanding = Number(bill.outstanding ?? 0);
  // The cashier confirms rather than types: the amount is filled with what is outstanding (change it for a part payment).
  const openReceive = () => { setPaymentForm({ ...emptyPayment, amount: outstanding > 0 ? String(outstanding) : "" }); setPaymentFormOpen(true); setTab("payments"); };
  useEffect(() => {
    if (paymentFormOpen && !paymentForm.amount && data?.bill && outstanding > 0) setPaymentForm((f) => ({ ...f, amount: String(outstanding) }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paymentFormOpen, data?.bill?.id, outstanding]);
  const entered = Number(paymentForm.amount || 0);

  return (
    <Sheet open onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className={cn(PANEL_WIDTH.default, "overflow-y-auto p-0 flex flex-col")} side="right">
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
                    {bill.entity === "SCANCARE" && <Badge variant="outline" className="text-xs">Scancare</Badge>}
                    {bill.stage && <Badge variant="outline" className="text-xs capitalize">{bill.stage}</Badge>}
                    {bill.released_at && <Badge variant="outline" className="text-xs text-blue-600">Released</Badge>}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">Billed {elapsed(bill.billed_at)} ago</p>
                  {status === "void" && bill.void_reason && <p className="text-xs text-muted-foreground mt-1">Voided: {bill.void_reason}</p>}
                </div>
              </div>
              <div className="flex flex-wrap gap-2 pt-3">
                <Button size="sm" variant="outline" className="h-7 gap-1 text-xs"
                  onClick={() => window.open(`#/hospital/billing/${bill.id}/invoice`, "_blank")}>
                  <Printer className="h-3 w-3" /> Invoice
                </Button>
                {isHmo && (
                  <Button size="sm" variant="outline" className="h-7 gap-1 text-xs"
                    onClick={() => window.open(`#/hospital/billing/${bill.id}/invoice?claims=1`, "_blank")}>
                    <FileText className="h-3 w-3" /> Claims form
                  </Button>
                )}
                {status === "partial" && !bill.released_at && (
                  <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" disabled={releaseMut.isPending} onClick={askRelease}>
                    <Unlock className="h-3 w-3" /> Release services
                  </Button>
                )}
                {status !== "void" && standingPayments.length === 0 && (
                  <Button size="sm" variant="outline" className="h-7 gap-1 text-xs text-red-600" disabled={voidBillMut.isPending} onClick={askVoidBill}>
                    <Ban className="h-3 w-3" /> Void bill
                  </Button>
                )}
              </div>
            </SheetHeader>

            <Tabs value={tab} onValueChange={setTab} className="flex-1 flex flex-col min-h-0">
              <TabsList className="mx-5 mt-3 bg-muted border border-border shrink-0 flex-wrap h-auto">
                <TabsTrigger value="detail">Detail</TabsTrigger>
                <TabsTrigger value="payments">Payments</TabsTrigger>
                <TabsTrigger value="claims">Claims</TabsTrigger>
                <TabsTrigger value="account">Patient account</TabsTrigger>
                <TabsTrigger value="corrections">Corrections</TabsTrigger>
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
                    <DetailRow
                      label="Discount"
                      value={bill.discount ? naira(bill.discount) : undefined}
                      accent={
                        bill.discount_status === "pending" ? "text-amber-600"
                        : bill.discount_status === "approved" ? "text-green-600"
                        : undefined
                      }
                    />
                    {bill.discount_status === "pending" && (
                      <p className="py-1 text-xs text-amber-600">
                        Waiting for admin approval. Payment is blocked until this is decided.
                      </p>
                    )}
                    {bill.discount_status === "rejected" && (
                      <p className="py-1 text-xs text-muted-foreground">
                        A discount was rejected and cleared from this bill.
                      </p>
                    )}
                    <DetailRow label="HMO Covered"  value={bill.hmo_covered ? naira(bill.hmo_covered) : undefined} accent="text-green-500" />
                    <DetailRow label="Patient Balance" value={naira(bill.patient_balance ?? bill.patient_due)} accent="font-semibold" />
                    <DetailRow label="Amount Paid"  value={naira(bill.amount_paid)} accent="text-green-500" />
                    <DetailRow label="Outstanding"  value={naira(bill.outstanding)} accent={(bill.outstanding ?? 0) > 0 ? "text-red-500 font-semibold" : "text-green-500"} />
                  </section>
                  {isHmo && bill.encounter_id && (
                    <>
                      <Separator />
                      <HmoServicesCheck encounterId={bill.encounter_id} />
                    </>
                  )}

                  {/* Cashier applies a discount; an admin decides. The amount is
                      not deducted until approved, so what the patient owes never
                      silently changes on one person's say-so. */}
                  {bill.status !== "paid" && bill.discount_status !== "pending" && (
                    <>
                      <Separator />
                      <section>
                        <SectionLabel icon={<Percent className="h-3.5 w-3.5" />} label="Apply discount" />
                        <div className="space-y-2">
                          <div className="space-y-1">
                            <Label className="text-xs">Discount</Label>
                            <div className="flex flex-wrap gap-1">
                              {[5, 10, 15, 20, 25, 50].map((pct) => (
                                <Button key={pct} type="button" size="sm" variant="outline" className="h-7 px-2 text-xs"
                                  onClick={() => setDiscountAmount((Math.round(Number(bill.subtotal ?? 0) * pct) / 100).toFixed(2))}>
                                  {pct}%
                                </Button>
                              ))}
                            </div>
                            <Input
                              type="number" min="0" step="100"
                              placeholder="or type an amount (₦)"
                              value={discountAmount}
                              onChange={(e) => setDiscountAmount(e.target.value)}
                              className="h-8 text-xs"
                            />
                            {Number(discountAmount) > 0 && Number(discountAmount) <= Number(bill.subtotal ?? 0) && (
                              <p className="text-xs text-muted-foreground">
                                {Math.round((Number(discountAmount) / Number(bill.subtotal || 1)) * 1000) / 10}% off ·
                                patient will owe {naira(Math.max(Number(bill.subtotal ?? 0) - Number(bill.hmo_covered ?? 0) - Number(discountAmount) - Number(bill.amount_paid ?? 0), 0))}
                              </p>
                            )}
                          </div>
                          <div className="space-y-1">
                            <Label className="text-xs">Reason</Label>
                            <Input
                              placeholder="Why is this being discounted?"
                              value={discountReason}
                              onChange={(e) => setDiscountReason(e.target.value)}
                              className="h-8 text-xs"
                            />
                          </div>
                          <Button
                            size="sm" className="w-full gap-1.5"
                            disabled={
                              discountMut.isPending ||
                              !(Number(discountAmount) > 0) ||
                              Number(discountAmount) > Number(bill.subtotal ?? 0)
                            }
                            onClick={() => discountMut.mutate()}
                          >
                            {discountMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                            Send for approval
                          </Button>
                          {Number(discountAmount) > Number(bill.subtotal ?? 0) && (
                            <p className="text-xs text-red-600">
                              A discount cannot exceed the subtotal.
                            </p>
                          )}
                        </div>
                      </section>
                    </>
                  )}

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
                            <TableHead className="text-xs">Receipt No.</TableHead>
                            <TableHead className="text-xs">Reference</TableHead>
                            <TableHead className="text-xs">By</TableHead>
                            <TableHead className="w-[140px]" />
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {payments.map((p: any) => {
                            const voided = (p.status ?? "posted") === "void";
                            return (
                            <TableRow key={p.id} className={voided ? "opacity-60" : undefined}>
                              <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{fmtDate(p.received_at)}</TableCell>
                              <TableCell className={cn("text-xs font-semibold", voided ? "line-through text-muted-foreground" : "text-green-500")}>
                                {naira(p.amount)}
                                {voided && <span className="block font-normal no-underline">Void: {p.void_reason}</span>}
                              </TableCell>
                              <TableCell className="text-xs">{PAYMENT_METHOD_LABELS[p.payment_method] ?? p.payment_method}</TableCell>
                              {/* The hospital's number, not the payer's — see
                                  the receipt_number column comment. */}
                              <TableCell className="font-mono text-xs">{p.receipt_number ?? "—"}</TableCell>
                              <TableCell className="text-xs text-muted-foreground">{p.reference ?? "—"}</TableCell>
                              <TableCell className="text-xs text-muted-foreground">{p.received_by ?? "—"}</TableCell>
                              <TableCell className="w-[140px] whitespace-nowrap">
                                {!voided && (
                                  <Button
                                    size="sm" variant="ghost" className="h-7 gap-1 px-2 text-xs"
                                    onClick={() => window.open(`#/hospital/billing/${bill.id}/invoice?receipt=${p.id}`, "_blank")}
                                  >
                                    <Printer className="h-3 w-3" /> Receipt
                                  </Button>
                                )}
                                {!voided && !p.external_source && !["waiver", "hmo"].includes(p.payment_method) && (
                                  <Button size="sm" variant="ghost" className="h-7 gap-1 px-2 text-xs text-red-600"
                                    disabled={voidPaymentMut.isPending} onClick={() => askVoidPayment(p)}>
                                    <Undo2 className="h-3 w-3" /> Void
                                  </Button>
                                )}
                              </TableCell>
                            </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </div>
                  )}

                  <div className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
                    <span>Paid <span className="font-semibold text-green-600">{naira(bill.amount_paid)}</span> of {naira(bill.patient_due ?? bill.patient_balance)}</span>
                    <span className={outstanding > 0 ? "font-semibold text-red-600" : "font-semibold text-green-600"}>
                      {outstanding > 0 ? `${naira(outstanding)} owing` : "Paid in full"}
                    </span>
                  </div>
                  {isOpen && (!paymentFormOpen ? (
                    <Button size="sm" className="w-full gap-1.5" onClick={openReceive}>
                      <Plus className="h-3.5 w-3.5" /> Receive payment
                    </Button>
                  ) : (
                    <section className="space-y-2 border-t pt-3">
                      <div className="space-y-1">
                        <Label>Amount received (₦)</Label>
                        <Input type="number" min="0" value={paymentForm.amount}
                          onChange={e => setPaymentForm(f => ({ ...f, amount: e.target.value }))} placeholder="e.g. 5000" />
                        <p className={cn("text-xs", entered > outstanding ? "text-red-600" : "text-muted-foreground")}>
                          {entered <= 0 ? `Outstanding ${naira(outstanding)}`
                            : entered > outstanding ? `More than the ${naira(outstanding)} outstanding`
                            : entered < outstanding ? `Part payment: ${naira(outstanding - entered)} will remain on the patient's account`
                            : "Pays the bill in full"}
                        </p>
                      </div>
                      <div className="space-y-1">
                        <Label>Payment Method</Label>
                        <Select value={paymentForm.payment_method} onValueChange={v => setPaymentForm(f => ({ ...f, payment_method: v }))}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {PAYMENT_METHODS.map(m => <SelectItem key={m} value={m}>{PAYMENT_METHOD_LABELS[m] ?? m}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1">
                        <Label>{paymentForm.payment_method === "pos" ? "POS slip / terminal reference" : "Reference"}</Label>
                        <Input value={paymentForm.reference} onChange={e => setPaymentForm(f => ({ ...f, reference: e.target.value }))}
                          placeholder="Optional - the receipt number is issued automatically" />
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" className="flex-1" onClick={() => { setPaymentFormOpen(false); setPaymentForm({ ...emptyPayment }); }}>Cancel</Button>
                        <Button size="sm" className="flex-1 gap-1.5" disabled={!(entered > 0) || entered > outstanding + 0.001 || paymentMut.isPending} onClick={() => paymentMut.mutate()}>
                          {paymentMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Confirm {entered > 0 ? naira(entered) : ""} received
                        </Button>
                      </div>
                    </section>
                  ))}
                </TabsContent>

                <TabsContent value="account" className="mt-0">
                  {tab === "account" && bill.patient_id && <PatientAccount patientId={bill.patient_id} currentBillId={bill.id} />}
                </TabsContent>

                <TabsContent value="corrections" className="mt-0">
                  <CorrectionPen billId={bill.id} isAdmin={isAdmin} />
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
                                <p className="text-xs text-muted-foreground">{fmtDate(c.submitted_at)}</p>
                                {!terminal && (
                                  <Button size="sm" variant="ghost" className="h-6 px-2 text-xs"
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
                <Button size="sm" variant="outline" className="gap-1.5" data-tour-id="billing-record-payment" onClick={() => { setTab("payments"); setPaymentFormOpen(true); }}>
                  <CreditCard className="h-3.5 w-3.5" /> Record Payment
                </Button>
              )}
              {isOpen && isAdmin && (
                <Button size="sm" variant="outline" className="gap-1.5 text-purple-500 border-purple-500/30 hover:bg-purple-500/10"
                  disabled={waiveMut.isPending}
                  onClick={async () => { if (await askConfirm("Waive the remaining outstanding balance on this bill? This is logged and cannot be undone.")) waiveMut.mutate(); }}>
                  <ShieldOff className="h-3.5 w-3.5" /> Waive
                </Button>
              )}
              {isOpen && isAdmin && (
                <Button size="sm" variant="outline" className="gap-1.5 text-red-500 border-red-500/30 hover:bg-red-500/10"
                  disabled={writeOffMut.isPending}
                  onClick={async () => { if (await askConfirm("Write off this bill as uncollectable? This is logged and cannot be undone.")) writeOffMut.mutate(); }}>
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


/** The patient's account across visits: bills (debit) and receipts (credit) with a running balance, per company. */
export function PatientAccount({ patientId, currentBillId }: { patientId: number; currentBillId?: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ["patient-account", patientId],
    queryFn: () => api.hospital.billing.patientAccount(patientId),
  });
  if (isLoading) return <Skeleton className="h-24 w-full" />;
  const lines: any[] = data?.lines ?? [];
  const balances: Record<string, number> = data?.balances ?? {};
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3">
        {Object.entries(balances).map(([co, bal]) => (
          <div key={co} className="rounded-md border px-3 py-2">
            <p className="text-xs text-muted-foreground flex items-center gap-1"><Wallet className="h-3 w-3" />{co === "SCANCARE" ? "Scancare" : "Royan"} balance</p>
            <p className={cn("text-sm font-semibold", bal > 0 ? "text-red-600" : "text-green-600")}>{naira(bal)}</p>
          </div>
        ))}
      </div>
      {lines.length === 0 ? <p className="text-xs text-muted-foreground">Nothing on this patient's account yet.</p> : (
        <div className="rounded-md border overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">Date</TableHead>
                <TableHead className="text-xs">Ref</TableHead>
                <TableHead className="text-xs">Company</TableHead>
                <TableHead className="text-xs text-right">Debit</TableHead>
                <TableHead className="text-xs text-right">Credit</TableHead>
                <TableHead className="text-xs text-right">Balance</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((l: any) => (
                <TableRow key={l.kind + l.id} className={cn(l.void && "opacity-50 line-through", l.bill_id === currentBillId && "bg-primary/5")}>
                  <TableCell className="text-xs whitespace-nowrap">{fmtDate(l.at)}</TableCell>
                  <TableCell className="text-xs font-mono">{l.ref}{l.kind === "receipt" && l.method ? ` · ${String(l.method).toUpperCase()}` : ""}</TableCell>
                  <TableCell className="text-xs">{l.company === "SCANCARE" ? "Scancare" : "Royan"}</TableCell>
                  <TableCell className="text-xs text-right">{l.debit ? naira(l.debit) : ""}</TableCell>
                  <TableCell className="text-xs text-right">{l.credit ? naira(l.credit) : ""}</TableCell>
                  <TableCell className="text-xs text-right font-medium">{naira(l.balance)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
