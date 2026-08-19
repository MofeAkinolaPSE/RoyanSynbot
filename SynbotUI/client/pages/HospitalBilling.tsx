import { useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { BackButton } from "@/components/BackButton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  DollarSign, RefreshCw, Loader2, ReceiptText, Building, AlertCircle,
  User, FilePlus2, AlertTriangle,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { BillingWorkspacePanel } from "@/components/billing/BillingWorkspacePanel";
import { GenerateBillPanel } from "@/components/billing/GenerateBillPanel";
import { BillBadge, ClaimBadge, naira, fmtDate, BILL_STATUSES, CLAIM_STATUSES } from "@/components/billing/billing-shared";

// ─── Types ────────────────────────────────────────────────────────────────────
interface Bill {
  id: number;
  patient_id?: number;
  patient_name?: string;
  patient_mrn?: string;
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
  notes?: string;
}

interface UnbilledEncounter {
  id: number;
  patient_id?: number;
  patient_name?: string;
  patient_mrn?: string;
  queue_number?: string;
  department?: string;
  chief_complaint?: string;
  created_at?: string;
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function HospitalBilling() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const patientIdFilter = Number(searchParams.get("patient_id") ?? 0) || undefined;

  const [tab, setTab] = useState("bills");
  const [billFilter, setBillFilter]     = useState("all");
  const [claimFilter, setClaimFilter]   = useState("all");
  const [panelBill, setPanelBill]       = useState<Bill | null>(null);
  const [generateEncounter, setGenerateEncounter] = useState<UnbilledEncounter | null>(null);

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

  // Deliberately NOT tab-gated — the previous KPI bug (hmoPending reading 0
  // off the Bills tab) came from exactly this kind of gating. The tab
  // trigger's badge count must stay accurate regardless of active tab.
  const { data: unbilledData, refetch: refetchUnbilled } = useQuery({
    queryKey: ["hospital-unbilled-encounters"],
    queryFn: () => api.hospital.billing.listUnbilledEncounters(),
    refetchInterval: 30_000,
  });
  const unbilled: UnbilledEncounter[] = Array.isArray(unbilledData?.encounters) ? unbilledData.encounters : [];

  // KPIs — sourced from /billing_hospital/stats, not client-side aggregation
  // over a possibly filter/tab-scoped worklist (the exact bug this replaces).
  const { data: statsData } = useQuery({
    queryKey: ["hospital-billing-stats"],
    queryFn: () => api.hospital.billing.getStats(),
    refetchInterval: 60_000,
  });
  const stats = statsData ?? {};

  return (
    <motion.div className="space-y-6" {...motionTransitions.fadeInUp}>
      {/* Patient filter banner */}
      {patientIdFilter && (
        <div className="flex items-center gap-3 rounded-lg border border-blue-500/20 bg-blue-500/5 px-4 py-2.5">
          <User className="h-4 w-4 text-blue-400 shrink-0" />
          <span className="text-sm text-blue-700 dark:text-blue-300 flex-1">
            {billsLoading ? (
              "Loading patient billing…"
            ) : bills[0]?.patient_name ? (
              <>
                Showing bills for <span className="font-semibold">{bills[0].patient_name}</span>
                {bills[0].patient_mrn && <span className="font-mono ml-1.5 opacity-80">({bills[0].patient_mrn})</span>}
              </>
            ) : (
              <>Showing bills for Patient ID <span className="font-mono font-semibold">{patientIdFilter}</span> — no bills on file yet</>
            )}
          </span>
          <BackButton fallback="/hospital/billing" className="h-7 text-xs text-muted-foreground hover:text-foreground">All Bills</BackButton>
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
        <Button variant="outline" size="sm" onClick={() => { void refetchBills(); void refetchClaims(); void refetchUnbilled(); }} disabled={billingFetching} className="gap-2">
          <RefreshCw className={cn("h-3.5 w-3.5", billingFetching && "animate-spin")} /> Refresh
        </Button>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {[
          { label: "Total Outstanding", value: naira(stats.total_outstanding), icon: <DollarSign className="h-4 w-4" />,   color: "text-red-400"    },
          { label: "Pending Bills",     value: stats.pending_count ?? 0,       icon: <ReceiptText className="h-4 w-4" />,  color: "text-yellow-400" },
          { label: "Partial Bills",     value: stats.partial_count ?? 0,       icon: <AlertCircle className="h-4 w-4" />,  color: "text-blue-400"   },
          { label: "Disputed Bills",    value: stats.disputed_count ?? 0,      icon: <AlertTriangle className="h-4 w-4" />, color: "text-orange-400" },
          { label: "HMO Pending Claims", value: stats.hmo_pending_count ?? 0,  icon: <Building className="h-4 w-4" />,     color: "text-purple-400" },
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
          <TabsTrigger value="unbilled" className="gap-1.5">
            Awaiting Generation
            {unbilled.length > 0 && (
              <span className="rounded-full bg-red-500/20 text-red-700 dark:text-red-400 text-[12px] font-semibold px-1.5 py-0.5">{unbilled.length}</span>
            )}
          </TabsTrigger>
        </TabsList>

        {/* Bills tab */}
        <TabsContent value="bills" className="space-y-4">
          <div className="mt-4 flex flex-wrap gap-2">
            {["all", ...BILL_STATUSES].map(s => (
              <button key={s} onClick={() => setBillFilter(s)}
                className={cn("rounded-full border px-3 py-1 text-xs capitalize transition-colors",
                  billFilter === s ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-muted")}>
                {s === "all" ? "All" : s.replace(/_/g, " ")}
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
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {bills.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={8} className="py-8 text-center text-muted-foreground">
                          <ReceiptText className="mx-auto mb-2 h-6 w-6 opacity-30" />No bills found
                        </TableCell>
                      </TableRow>
                    ) : bills.map(b => (
                      <TableRow key={b.id} className="cursor-pointer hover:bg-muted" onClick={() => setPanelBill(b)}>
                        <TableCell className="font-mono text-xs">{b.bill_number ?? String(b.id).slice(0, 8)}</TableCell>
                        <TableCell className="text-xs">
                          {b.patient_name ? (
                            <div className="flex flex-col">
                              <span className="font-medium">{b.patient_name}</span>
                              {b.patient_mrn && <span className="font-mono text-[12px] text-muted-foreground">{b.patient_mrn}</span>}
                            </div>
                          ) : (
                            <span className="font-mono">{b.patient_id != null ? String(b.patient_id) : "—"}</span>
                          )}
                        </TableCell>
                        <TableCell className="text-right text-sm">{naira(b.subtotal)}</TableCell>
                        <TableCell className="text-right text-xs">
                          {(b.hmo_covered ?? 0) > 0 ? (
                            <span className="text-green-700 dark:text-green-400 font-medium">{naira(b.hmo_covered)}</span>
                          ) : "—"}
                        </TableCell>
                        <TableCell className="text-right text-xs text-muted-foreground">
                          {b.discount != null && b.discount > 0 ? naira(b.discount) : "—"}
                        </TableCell>
                        <TableCell className={cn("text-right text-sm font-semibold", (b.patient_balance ?? 0) > 0 ? "text-red-700 dark:text-red-400" : "text-green-700 dark:text-green-400")}>
                          {naira(b.patient_balance)}
                        </TableCell>
                        <TableCell><BillBadge status={b.status} /></TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {b.billed_at ? new Date(b.billed_at).toLocaleDateString() : "—"}
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
            {["all", ...CLAIM_STATUSES].map(s => (
              <button key={s} onClick={() => setClaimFilter(s)}
                className={cn("rounded-full border px-3 py-1 text-xs capitalize transition-colors",
                  claimFilter === s ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-muted")}>
                {s === "all" ? "All" : s.replace(/_/g, " ")}
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
                      <TableHead>Notes</TableHead>
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
                        <TableCell className="text-right text-sm text-green-700 dark:text-green-400">{naira(c.approved_amount)}</TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-[120px] truncate">
                          {c.notes ?? "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Awaiting Generation tab */}
        <TabsContent value="unbilled" className="space-y-4">
          <p className="mt-4 text-xs text-muted-foreground">
            Encounters routed to billing with no bill generated yet. Click one to create its bill.
          </p>
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Queue #</TableHead>
                    <TableHead>Patient</TableHead>
                    <TableHead>Department</TableHead>
                    <TableHead>Chief Complaint</TableHead>
                    <TableHead>Ready Since</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {unbilled.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                        <FilePlus2 className="mx-auto mb-2 h-6 w-6 opacity-30" />Nothing awaiting a bill
                      </TableCell>
                    </TableRow>
                  ) : unbilled.map(e => (
                    <TableRow key={e.id} className="cursor-pointer hover:bg-muted" onClick={() => setGenerateEncounter(e)}>
                      <TableCell className="font-mono text-xs text-primary font-semibold">{e.queue_number ?? String(e.id).slice(0, 6)}</TableCell>
                      <TableCell>
                        <div className="text-sm font-medium">{e.patient_name ?? "Unknown"}</div>
                        {e.patient_mrn && <div className="text-[12px] font-mono text-muted-foreground">{e.patient_mrn}</div>}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">{e.department ?? "—"}</TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-[180px] truncate">{e.chief_complaint ?? "—"}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{fmtDate(e.created_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {panelBill && (
        <BillingWorkspacePanel bill={panelBill} onClose={() => setPanelBill(null)} />
      )}
      {generateEncounter && (
        <GenerateBillPanel encounter={generateEncounter} onClose={() => setGenerateEncounter(null)} />
      )}
    </motion.div>
  );
}
