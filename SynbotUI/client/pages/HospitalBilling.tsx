import { useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  DollarSign, RefreshCw, Loader2, ReceiptText, Building, AlertCircle,
  CheckCircle2, ArrowLeft, User,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────
interface Bill {
  id: number;
  patient_id?: number;
  encounter_id?: number;
  bill_number?: string;
  subtotal?: number;
  discount?: number;
  hmo_covered?: number;
  patient_balance?: number;
  status?: string;
  billed_at?: string;
}

interface HmoClaim {
  id: number;
  bill_id?: number;
  billing_id?: number;
  hmo_provider?: string;
  insurer_name?: string;
  claim_amount?: number;
  status?: string;
  submitted_at?: string;
  approved_amount?: number;
  dispute_reason?: string;
}

const BILL_STATUS_COLORS: Record<string, string> = {
  pending:   "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  partial:   "bg-blue-500/20 text-blue-400 border-blue-500/30",
  paid:      "bg-green-500/20 text-green-400 border-green-500/30",
  waived:    "bg-purple-500/20 text-purple-400 border-purple-500/30",
  cancelled: "bg-slate-500/20 text-slate-300 border-slate-500/30",
};

const CLAIM_STATUS_COLORS: Record<string, string> = {
  submitted: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  approved:  "bg-green-500/20 text-green-400 border-green-500/30",
  rejected:  "bg-red-500/20 text-red-400 border-red-500/30",
  disputed:  "bg-orange-500/20 text-orange-400 border-orange-500/30",
  pending:   "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
};

function BillBadge({ status }: { status?: string }) {
  const s = status ?? "pending";
  const cls = BILL_STATUS_COLORS[s] ?? BILL_STATUS_COLORS.pending;
  return <Badge variant="outline" className={cn("text-xs capitalize", cls)}>{s}</Badge>;
}

function ClaimBadge({ status }: { status?: string }) {
  const s = status ?? "pending";
  const cls = CLAIM_STATUS_COLORS[s] ?? CLAIM_STATUS_COLORS.pending;
  return <Badge variant="outline" className={cn("text-xs capitalize", cls)}>{s}</Badge>;
}

function naira(n?: number) {
  if (n === undefined || n === null) return "—";
  return `₦${n.toLocaleString("en-NG", { minimumFractionDigits: 2 })}`;
}

const PAYMENT_METHODS = ["cash", "card", "transfer", "hmo", "waiver"];
const EMPTY_PAYMENT = { amount: "", payment_method: "cash", reference_number: "" };
const EMPTY_CLAIM   = { insurer_name: "", claim_amount: "", notes: "" };

// ─── Component ────────────────────────────────────────────────────────────────
export default function HospitalBilling() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const patientIdFilter = Number(searchParams.get("patient_id") ?? 0) || undefined;

  const [tab, setTab] = useState("bills");
  const [billFilter, setBillFilter]       = useState("all");
  const [claimFilter, setClaimFilter]     = useState("all");
  const [paymentOpen, setPaymentOpen]     = useState(false);
  const [waiveOpen, setWaiveOpen]         = useState(false);
  const [newClaimOpen, setNewClaimOpen]   = useState(false);
  const [activeBill, setActiveBill]       = useState<Bill | null>(null);
  const [activeClaim, setActiveClaim]     = useState<HmoClaim | null>(null);
  const [paymentForm, setPaymentForm]     = useState({ ...EMPTY_PAYMENT });
  const [claimForm, setClaimForm]         = useState({ ...EMPTY_CLAIM });

  // Queries
  const { data: billsData, isLoading: billsLoading, refetch: refetchBills, isFetching: billingFetching } = useQuery({
    queryKey: ["hospital-bills", billFilter, patientIdFilter],
    queryFn: () => api.hospital.billing.listBills({
      ...(billFilter !== "all" && { status: billFilter }),
      ...(patientIdFilter && { patient_id: patientIdFilter }),
    }),
    refetchInterval: 60_000,
  });
  const bills: Bill[] = Array.isArray(billsData?.bills) ? billsData.bills : Array.isArray(billsData) ? billsData : [];

  const { data: claimsData, isLoading: claimsLoading, refetch: refetchClaims } = useQuery({
    queryKey: ["hospital-hmo-claims", claimFilter],
    queryFn: () => api.hospital.billing.listClaims(claimFilter !== "all" ? { status: claimFilter } : undefined),
    enabled: tab === "claims",
    refetchInterval: 120_000,
  });
  const claims: HmoClaim[] = Array.isArray(claimsData?.claims) ? claimsData.claims : Array.isArray(claimsData) ? claimsData : [];

  // KPI
  const outstanding    = bills.filter(b => ["pending", "partial"].includes(b.status ?? "")).reduce((s, b) => s + (b.patient_balance ?? 0), 0);
  const pendingCount   = bills.filter(b => b.status === "pending").length;
  const partialCount   = bills.filter(b => b.status === "partial").length;
  const hmoPending     = claims.filter(c => c.status === "submitted" || c.status === "pending").length;

  // Mutations
  const paymentMut = useMutation({
    mutationFn: () => activeBill ? api.hospital.billing.recordPayment(activeBill.id, paymentForm) : Promise.reject(),
    onSuccess: () => {
      toast({ title: "Payment recorded" });
      setPaymentOpen(false);
      setPaymentForm({ ...EMPTY_PAYMENT });
      void qc.invalidateQueries({ queryKey: ["hospital-bills"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const waiveMut = useMutation({
    mutationFn: (bill: Bill) => api.hospital.billing.waiveBill(bill.id, { reason: "Admin waiver" }),
    onSuccess: () => {
      toast({ title: "Bill waived" });
      setWaiveOpen(false);
      void qc.invalidateQueries({ queryKey: ["hospital-bills"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const claimMut = useMutation({
    mutationFn: () => activeBill ? api.hospital.billing.createClaim({ ...claimForm, bill_id: activeBill.id }) : Promise.reject(),
    onSuccess: () => {
      toast({ title: "HMO claim submitted" });
      setNewClaimOpen(false);
      setClaimForm({ ...EMPTY_CLAIM });
      void qc.invalidateQueries({ queryKey: ["hospital-hmo-claims"] });
    },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  return (
    <motion.div className="space-y-6" {...motionTransitions.fadeInUp}>
      {/* Patient filter banner */}
      {patientIdFilter && (
        <div className="flex items-center gap-3 rounded-lg border border-blue-500/20 bg-blue-500/5 px-4 py-2.5">
          <User className="h-4 w-4 text-blue-400 shrink-0" />
          <span className="text-sm text-blue-300 flex-1">
            Showing bills for Patient ID <span className="font-mono font-semibold">{patientIdFilter}</span>
          </span>
          <Button variant="ghost" size="sm" className="h-7 gap-1.5 text-xs text-muted-foreground hover:text-foreground"
            onClick={() => navigate("/hospital/billing")}>
            <ArrowLeft className="h-3.5 w-3.5" /> All Bills
          </Button>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {patientIdFilter ? "Patient Billing" : "Hospital Billing"}
          </h1>
          <p className="text-sm text-muted-foreground">
            {patientIdFilter ? "Bills, payments and claims for this patient" : "Bills, payments, and HMO claims management"}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => { void refetchBills(); void refetchClaims(); }} disabled={billingFetching} className="gap-2">
          <RefreshCw className={cn("h-3.5 w-3.5", billingFetching && "animate-spin")} /> Refresh
        </Button>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "Total Outstanding",    value: naira(outstanding), icon: <DollarSign className="h-4 w-4" />,   color: "text-red-400"    },
          { label: "Pending Bills",         value: pendingCount,       icon: <ReceiptText className="h-4 w-4" />,  color: "text-yellow-400" },
          { label: "Partial Bills",         value: partialCount,       icon: <AlertCircle className="h-4 w-4" />,  color: "text-blue-400"   },
          { label: "HMO Pending Claims",    value: hmoPending,         icon: <Building className="h-4 w-4" />,     color: "text-purple-400" },
        ].map(k => (
          <Card key={k.label}>
            <CardContent className="pt-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">{k.label}</p>
                  <p className={cn("text-xl font-bold", typeof k.value === "string" ? "text-lg" : "")}>{k.value}</p>
                </div>
                <span className={k.color}>{k.icon}</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="bills">Bills</TabsTrigger>
          <TabsTrigger value="claims">HMO Claims</TabsTrigger>
        </TabsList>

        {/* Bills tab */}
        <TabsContent value="bills" className="space-y-4">
          <div className="mt-4 flex flex-wrap gap-2">
            {["all", "pending", "partial", "paid", "waived"].map(s => (
              <button key={s} onClick={() => setBillFilter(s)}
                className={cn("rounded-full border px-3 py-1 text-xs capitalize transition-colors",
                  billFilter === s ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-muted")}>
                {s === "all" ? "All" : s}
              </button>
            ))}
          </div>
          <Card>
            <CardContent className="p-0">
              {billsLoading ? (
                <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Bill #</TableHead>
                      <TableHead>Patient</TableHead>
                      <TableHead className="text-right">Total</TableHead>
                      <TableHead className="text-right">HMO</TableHead>
                      <TableHead className="text-right">Discount</TableHead>
                      <TableHead className="text-right">Patient Due</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Date</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {bills.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={9} className="py-8 text-center text-muted-foreground">
                          <ReceiptText className="mx-auto mb-2 h-6 w-6 opacity-30" />No bills found
                        </TableCell>
                      </TableRow>
                    ) : bills.map(b => (
                      <TableRow key={b.id}>
                        <TableCell className="font-mono text-xs">{b.bill_number ?? String(b.id).slice(0, 8)}</TableCell>
                        <TableCell className="font-mono text-xs">{b.patient_id != null ? String(b.patient_id).slice(0, 8) : "—"}</TableCell>
                        <TableCell className="text-right text-sm">{naira(b.subtotal)}</TableCell>
                        <TableCell className="text-right text-xs">
                          {(b.hmo_covered ?? 0) > 0 ? (
                            <span className="text-green-400 font-medium">{naira(b.hmo_covered)}</span>
                          ) : "—"}
                        </TableCell>
                        <TableCell className="text-right text-xs text-muted-foreground">
                          {b.discount != null && b.discount > 0 ? naira(b.discount) : "—"}
                        </TableCell>
                        <TableCell className={cn("text-right text-sm font-semibold", (b.patient_balance ?? 0) > 0 ? "text-red-400" : "text-green-400")}>
                          {naira(b.patient_balance)}
                        </TableCell>
                        <TableCell><BillBadge status={b.status} /></TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {b.billed_at ? new Date(b.billed_at).toLocaleDateString() : "—"}
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            {["pending", "partial"].includes(b.status ?? "") && (
                              <>
                                <Button size="sm" variant="outline" className="h-7 px-2 text-xs"
                                  onClick={() => { setActiveBill(b); setPaymentOpen(true); }}>
                                  Pay
                                </Button>
                                <Button size="sm" variant="outline" className="h-7 px-2 text-xs border-purple-500/30 text-purple-400 hover:bg-purple-500/10"
                                  onClick={() => { setActiveBill(b); setWaiveOpen(true); }}>
                                  Waive
                                </Button>
                                <Button size="sm" variant="outline" className="h-7 px-2 text-xs border-blue-500/30 text-blue-400 hover:bg-blue-500/10"
                                  onClick={() => { setActiveBill(b); setNewClaimOpen(true); }}>
                                  HMO
                                </Button>
                              </>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* HMO Claims tab */}
        <TabsContent value="claims" className="space-y-4">
          <div className="mt-4 flex flex-wrap gap-2">
            {["all", "pending", "submitted", "approved", "rejected", "disputed"].map(s => (
              <button key={s} onClick={() => setClaimFilter(s)}
                className={cn("rounded-full border px-3 py-1 text-xs capitalize transition-colors",
                  claimFilter === s ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-muted")}>
                {s === "all" ? "All" : s}
              </button>
            ))}
          </div>
          <Card>
            <CardContent className="p-0">
              {claimsLoading ? (
                <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Claim #</TableHead>
                      <TableHead>Insurer</TableHead>
                      <TableHead className="text-right">Claim Amt</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Submitted</TableHead>
                      <TableHead className="text-right">Approved</TableHead>
                      <TableHead>Dispute</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {claims.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                          <Building className="mx-auto mb-2 h-6 w-6 opacity-30" />No HMO claims found
                        </TableCell>
                      </TableRow>
                    ) : claims.map(c => (
                      <TableRow key={c.id}>
                        <TableCell className="font-mono text-xs">{String(c.id).slice(0, 8)}</TableCell>
                        <TableCell className="text-sm">{c.insurer_name ?? c.hmo_provider ?? "—"}</TableCell>
                        <TableCell className="text-right text-sm">{naira(c.claim_amount)}</TableCell>
                        <TableCell><ClaimBadge status={c.status} /></TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {c.submitted_at ? new Date(c.submitted_at).toLocaleDateString() : "—"}
                        </TableCell>
                        <TableCell className="text-right text-sm text-green-400">{naira(c.approved_amount)}</TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-[120px] truncate">
                          {c.dispute_reason ?? "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── Record Payment Dialog ──────────────────────────────────────── */}
      <Dialog open={paymentOpen} onOpenChange={setPaymentOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Record Payment</DialogTitle>
            <DialogDescription>
              {activeBill?.bill_number ?? String(activeBill?.id ?? "").slice(0, 8)} — Patient Due: {naira(activeBill?.patient_balance)}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Amount (₦) *</Label>
              <Input type="number" min="0" value={paymentForm.amount}
                onChange={e => setPaymentForm(f => ({ ...f, amount: e.target.value }))}
                placeholder="e.g. 5000" />
            </div>
            <div className="space-y-1">
              <Label>Payment Method</Label>
              <Select value={paymentForm.payment_method} onValueChange={v => setPaymentForm(f => ({ ...f, payment_method: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {PAYMENT_METHODS.map(m => <SelectItem key={m} value={m} className="capitalize">{m.toUpperCase()}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Reference / Receipt #</Label>
              <Input value={paymentForm.reference_number}
                onChange={e => setPaymentForm(f => ({ ...f, reference_number: e.target.value }))}
                placeholder="Transaction reference (optional)" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPaymentOpen(false)}>Cancel</Button>
            <Button
              disabled={!paymentForm.amount || paymentMut.isPending}
              onClick={() => paymentMut.mutate()}
            >
              {paymentMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}Record Payment
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Waive Confirm Dialog ────────────────────────────────────────── */}
      <Dialog open={waiveOpen} onOpenChange={setWaiveOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Waive Bill</DialogTitle>
            <DialogDescription>
              {activeBill?.bill_number ?? String(activeBill?.id ?? "").slice(0, 8)} — Patient Due: {naira(activeBill?.patient_balance)}
            </DialogDescription>
          </DialogHeader>
          <p className="text-sm text-muted-foreground py-2">
            This will waive the remaining outstanding balance. This action is logged and cannot be undone.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setWaiveOpen(false)}>Cancel</Button>
            <Button variant="destructive"
              disabled={waiveMut.isPending}
              onClick={() => activeBill && waiveMut.mutate(activeBill)}
            >
              {waiveMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}Confirm Waiver
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── New HMO Claim Dialog ────────────────────────────────────────── */}
      <Dialog open={newClaimOpen} onOpenChange={setNewClaimOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Submit HMO Claim</DialogTitle>
            <DialogDescription>{activeBill?.bill_number ?? String(activeBill?.id ?? "").slice(0, 8)}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Insurer Name *</Label>
              <Input value={claimForm.insurer_name}
                onChange={e => setClaimForm(f => ({ ...f, insurer_name: e.target.value }))}
                placeholder="e.g. NHIS, Hygeia, Reliance HMO" />
            </div>
            <div className="space-y-1">
              <Label>Claim Amount (₦) *</Label>
              <Input type="number" min="0" value={claimForm.claim_amount}
                onChange={e => setClaimForm(f => ({ ...f, claim_amount: e.target.value }))}
                placeholder="Amount to claim" />
            </div>
            <div className="space-y-1">
              <Label>Notes</Label>
              <Input value={claimForm.notes}
                onChange={e => setClaimForm(f => ({ ...f, notes: e.target.value }))}
                placeholder="Any additional notes" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setNewClaimOpen(false)}>Cancel</Button>
            <Button
              disabled={!claimForm.insurer_name.trim() || !claimForm.claim_amount || claimMut.isPending}
              onClick={() => claimMut.mutate()}
            >
              {claimMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}Submit Claim
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
