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
import { ShowMeHow } from "@/components/tour/ShowMeHow";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { BillingWorkspacePanel } from "@/components/billing/BillingWorkspacePanel";
import { GenerateBillPanel } from "@/components/billing/GenerateBillPanel";
import { BillBadge, ClaimBadge, naira, fmtDate, BILL_STATUSES, CLAIM_STATUSES } from "@/components/billing/billing-shared";
import { PatientBillingHistory } from "@/components/billing/PatientBillingHistory";
import { WardRatesCard } from "@/components/billing/WardRatesCard";
import { RoomRatesCard } from "@/components/billing/RoomRatesCard";
import { DiscountApprovalsCard } from "@/components/billing/DiscountApprovalsCard";

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

  // Identity comes from the patient record, not from the first bill. A patient
  // with no bills yet still has a name, and a cashier reading
  // "Patient ID 94398" cannot confirm they have the right person.
  const { data: patientData } = useQuery({
    queryKey: ["billing-patient", patientIdFilter],
    queryFn: () => api.hospital.patients.getById(patientIdFilter!),
    enabled: !!patientIdFilter,
  });
  const billingPatient = patientData?.patient;

  const [tab, setTab] = useState("bills");
  const [billFilter, setBillFilter]     = useState("all");
  // Royan and Scancare are separate companies: the hospital's bills by default, Scancare's on request
  const [company, setCompany]           = useState("ROYAN");
  // HMO patients' bills apart from private ones (the HMO desk opens this page on ?payer=hmo)
  const [payer, setPayer]               = useState<string>(() => (["hmo", "private"].includes(searchParams.get("payer") ?? "") ? searchParams.get("payer")! : "all"));
  const [claimFilter, setClaimFilter]   = useState("all");
  const [panelBill, setPanelBill]       = useState<Bill | null>(null);
  const [panelReceive, setPanelReceive] = useState(false);
  const [panelTab, setPanelTab]         = useState<string | undefined>(undefined);
  const [generateEncounter, setGenerateEncounter] = useState<UnbilledEncounter | null>(null);

  // Queries
  const { data: billsData, isLoading: billsLoading, refetch: refetchBills, isFetching: billingFetching } = useQuery({
    queryKey: ["hospital-bills", billFilter, patientIdFilter, company, payer],
    queryFn: () => api.hospital.billing.listBills({
      ...(company !== "ALL" && { entity: company }),
      ...(payer !== "all" && { payer }),
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
            {(() => {
              const name = billingPatient?.full_name ?? bills[0]?.patient_name;
              const mrn  = billingPatient?.mrn ?? bills[0]?.patient_mrn;
              if (billsLoading && !name) return "Loading patient billing…";
              if (!name) {
                return (
                  <>Showing bills for Patient ID <span className="font-mono font-semibold">{patientIdFilter}</span></>
                );
              }
              return (
                <>
                  Showing bills for <span className="font-semibold">{name}</span>
                  {mrn && <span className="ml-1.5 font-mono opacity-80">({mrn})</span>}
                  {billingPatient?.patient_type && (
                    <span className="ml-1.5 capitalize opacity-80">· {billingPatient.patient_type}</span>
                  )}
                  {bills.length === 0 && !billsLoading && (
                    <span className="ml-1.5 opacity-80">— no bills on file yet</span>
                  )}
                </>
              );
            })()}
          </span>
          <BackButton fallback="/hospital/billing" className="h-7 text-xs text-muted-foreground hover:text-foreground">All Bills</BackButton>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight">
              {patientIdFilter ? "Patient Billing" : "Hospital Billing"}
            </h1>
            <ShowMeHow only={["cashier-payment"]} />
          </div>
          <p className="text-sm text-muted-foreground">
            {patientIdFilter ? "Bills, payments and claims for this patient" : "Bills, payments, and HMO claims management"}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => { void refetchBills(); void refetchClaims(); void refetchUnbilled(); }} disabled={billingFetching} className="gap-2">
          <RefreshCw className={cn("h-3.5 w-3.5", billingFetching && "animate-spin")} /> Refresh
        </Button>
      </div>

      {/* Discounts a cashier applied, waiting for finance / an admin (the workspace links here) */}
      {!patientIdFilter && <DiscountApprovalsCard />}

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
          <TabsTrigger value="bills" data-tour-id="billing-bills-tab">Bills</TabsTrigger>
          <TabsTrigger value="claims">HMO Claims</TabsTrigger>
          <TabsTrigger value="history" className="gap-1.5">
            Patient Account
          </TabsTrigger>
          <TabsTrigger value="unbilled" className="gap-1.5">
            Awaiting Generation
            {unbilled.length > 0 && (
              <span className="rounded-full bg-red-500/20 text-red-700 dark:text-red-400 text-xs font-semibold px-1.5 py-0.5">{unbilled.length}</span>
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
            <select className="ml-auto h-8 rounded-md border bg-background px-2 text-xs" value={payer} onChange={(e) => setPayer(e.target.value)}>
              <option value="all">All patients</option><option value="hmo">HMO patients</option><option value="private">Private patients</option>
            </select>
            <select className="h-8 rounded-md border bg-background px-2 text-xs" value={company} onChange={(e) => setCompany(e.target.value)}>
              <option value="ROYAN">Royan Hospital bills</option><option value="SCANCARE">Scancare bills</option><option value="ALL">Both companies</option>
            </select>
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
                      <TableHead />
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
                      <TableRow key={b.id} className="cursor-pointer hover:bg-muted" onClick={() => { setPanelReceive(false); setPanelTab(undefined); setPanelBill(b); }}>
                        <TableCell className="font-mono text-xs">{b.bill_number ?? String(b.id).slice(0, 8)}</TableCell>
                        <TableCell className="text-xs">
                          {b.patient_name ? (
                            <div className="flex flex-col">
                              <span className="font-medium">{b.patient_name}</span>
                              {b.patient_mrn && <span className="font-mono text-xs text-muted-foreground">{b.patient_mrn}</span>}
                              {(b as any).payer_type === "hmo" ? (
                                <span className="mt-0.5 inline-flex w-fit items-center rounded border border-violet-400 bg-violet-50 px-1.5 py-0.5 text-xs font-semibold text-violet-800 dark:bg-violet-500/15 dark:text-violet-300">
                                  HMO · {(b as any).hmo_name ?? "insured"}{(b as any).membership_id ? ` · ${(b as any).membership_id}` : ""}
                                </span>
                              ) : (b as any).payer_type === "private" ? (
                                <span className="mt-0.5 w-fit text-xs font-medium text-foreground/70">Private</span>
                              ) : null}
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
                        <TableCell className={cn("text-right text-sm font-semibold", ((b as any).outstanding ?? b.patient_balance ?? 0) > 0 ? "text-red-700 dark:text-red-400" : "text-green-700 dark:text-green-400")}>
                          {naira(b.patient_balance)}
                          {(b as any).amount_paid > 0 && ((b as any).outstanding ?? 0) > 0 && (
                            <span className="block text-xs font-normal text-muted-foreground">{naira((b as any).outstanding)} owing</span>
                          )}
                        </TableCell>
                        <TableCell><BillBadge status={b.status} /></TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {b.billed_at ? new Date(b.billed_at).toLocaleDateString() : "—"}
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-right" onClick={(e) => e.stopPropagation()}>
                          {["pending", "partial"].includes(String(b.status)) && ((b as any).outstanding ?? 0) > 0 && (
                            <Button size="sm" className="h-7 px-2 text-xs" onClick={() => { setPanelTab(undefined); setPanelReceive(true); setPanelBill(b); }}>
                              Receive
                            </Button>
                          )}
                          {(b as any).payer_type === "hmo" && (
                            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => window.open(`#/hospital/billing/${b.id}/invoice?claims=1`, "_blank")}>
                              Claims form
                            </Button>
                          )}
                          <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => window.open(`#/hospital/billing/${b.id}/invoice`, "_blank")}>
                            Invoice
                          </Button>
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
                      <TableRow key={c.id} className={c.billing_id ? "cursor-pointer hover:bg-muted" : ""}
                        onClick={() => { if (c.billing_id) { setPanelReceive(false); setPanelTab("claims"); setPanelBill({ id: c.billing_id } as any); } }}>
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
                        {e.patient_mrn && <div className="text-xs font-mono text-muted-foreground">{e.patient_mrn}</div>}
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
        {/* Search any patient and read their whole account, including bills
            from before go-live. The Bills worklist deliberately hides those. */}
        <TabsContent value="history" className="space-y-4">
          <PatientBillingHistory initialPatientId={patientIdFilter} />
        </TabsContent>
      </Tabs>

      {panelBill && (
        <BillingWorkspacePanel key={`${panelBill.id}:${panelReceive}:${panelTab}`} bill={panelBill} receive={panelReceive} initialTab={panelTab}
          onClose={() => setPanelBill(null)} />
      )}
      {generateEncounter && (
        <GenerateBillPanel encounter={{ ...generateEncounter, patient_id: generateEncounter.patient_id ?? "" }} onClose={() => setGenerateEncounter(null)} />
      )}

      {/* Rate configuration, at the bottom and folded away.
          These are two long lists of rooms and wards that get set once and
          rarely revisited, and sitting above the bills they pushed the actual
          billing work off the screen. Rooms first: the charge resolves
          bed -> room -> ward, so the room rate is what almost every bed bills
          at, and the ward card sets the fallback for rooms with none. */}
      <div className="space-y-3 pt-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Rate configuration
        </p>
        <RoomRatesCard />
        <WardRatesCard />
      </div>

    </motion.div>
  );
}
