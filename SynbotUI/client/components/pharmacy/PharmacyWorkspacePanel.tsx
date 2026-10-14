import { useState } from "react";
import { handlePayFirst } from "@/lib/pay-first";
import { useAuth } from "@/components/AuthProvider";
import { SignaturePad } from "@/components/pharmacy/SignaturePad";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  User, Pill, ClipboardList, ShieldAlert, Undo2, PenLine, Eye,
  ExternalLink, Loader2, XCircle, Percent
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { SectionLabel, PANEL_WIDTH } from "@/components/shared/panel-shared";
import { MedicationHistoryTab } from "@/components/pharmacy/MedicationHistoryTab";
import {
  StatusBadge, MedAdminStatusBadge, WorkflowProgress, DetailRow, elapsed,
} from "@/components/pharmacy/pharmacy-shared";

interface PharmacyWorkspacePanelProps {
  prescription: {
    id: string | number;
    patient_id?: string | number;
    patient_mrn?: string;
    patient_name?: string;
    patient_gender?: string;
    patient_dob?: string;
    drug_name?: string;
    dosage?: string;
    frequency?: string;
    route?: string;
    quantity?: number;
    unit?: string;
    status?: string;
    prescribed_at?: string;
  };
  onClose: () => void;
  initialTab?: string;
}

const emptyDispenseForm = { quantity_dispensed: "", batch_id: "", batch_number: "", expiry_date: "", unit_cost: "", counselling_given: false, counselling_notes: "" };
const emptyAdministerForm = { dose_given: "", route: "", site: "", status: "given", omission_reason: "", witnessed_by: "", notes: "" };
const emptyReturnForm = { quantity_returned: "", reason: "", restock: false };

export function PharmacyWorkspacePanel({ prescription: initialRx, onClose, initialTab }: PharmacyWorkspacePanelProps) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState(initialTab ?? "detail");

  const [dispenseForm, setDispenseForm] = useState({ ...emptyDispenseForm });
  const [safetyAlert, setSafetyAlert] = useState<{ kind: "allergy" | "ddi"; items: any[]; message: string } | null>(null);
  const [administerForm, setAdministerForm] = useState({ ...emptyAdministerForm });

  // A staff discount is requested here and approved by an admin elsewhere; the
  // pharmacist never applies one on their own authority.
  const [discountRowId, setDiscountRowId] = useState<number | null>(null);
  const [discountForm, setDiscountForm] = useState({ amount: "", discount_type: "staff", reason: "" });
  const [returnRowId, setReturnRowId] = useState<string | number | null>(null);
  const [returnForm, setReturnForm] = useState({ ...emptyReturnForm });
  const [signatureRowId, setSignatureRowId] = useState<string | number | null>(null);
  const [signatureFile, setSignatureFile] = useState<File | null>(null);

  const rxId = String(initialRx.id);
  const { roles: payFirstRoles } = useAuth();

  const { data, isLoading } = useQuery({
    queryKey: ["pharmacy-panel-rx", rxId],
    queryFn: () => api.hospital.pharmacy.getRx(rxId),
    refetchInterval: 15_000,
  });
  const rx: typeof initialRx & Record<string, any> = { ...initialRx, ...(data?.prescription ?? {}) };
  // An HMO patient's visit: the pharmacist can open the visit's Royan claims form (the patient signs it here)
  const { data: visitBills } = useQuery({
    queryKey: ["rx-visit-bills", rx.encounter_id],
    queryFn: () => api.hospital.billing.listBills({ encounter_id: Number(rx.encounter_id) }),
    enabled: !!rx.encounter_id,
    staleTime: 60_000,
  });
  const hmoBill = (visitBills?.bills ?? []).find((b: any) => b.payer_type === "hmo" && b.status !== "void");
  const dispensingRecords: any[] = data?.dispensing_records ?? [];
  const marEntries: any[] = data?.mar_entries ?? [];
  const returns: any[] = data?.returns ?? [];
  const totalDispensed: number = data?.total_dispensed ?? 0;
  const remainingQuantity: number = data?.remaining_quantity ?? (Number(rx.quantity ?? 0) - totalDispensed);
  const availableBatches: any[] = data?.available_batches ?? [];

  const returnsByDispensing = new Map<string, number>();
  for (const r of returns) {
    const key = String(r.dispensing_id);
    returnsByDispensing.set(key, (returnsByDispensing.get(key) ?? 0) + Number(r.quantity_returned ?? 0));
  }

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ["pharmacy-panel-rx", rxId] });
    void qc.invalidateQueries({ queryKey: ["pharmacy-rx"] });
    void qc.invalidateQueries({ queryKey: ["pharmacy-stats"] });
    void qc.invalidateQueries({ queryKey: ["pharmacy-inventory"] });
    void qc.invalidateQueries({ queryKey: ["pharmacy-returns"] });
  };

  const dispenseMut = useMutation({
    mutationFn: (overrideFlags: Record<string, boolean> = {}) => api.hospital.pharmacy.dispense(rxId, {
      quantity_dispensed: Number(dispenseForm.quantity_dispensed),
      batch_id: dispenseForm.batch_id ? Number(dispenseForm.batch_id) : undefined,
      batch_number: dispenseForm.batch_id ? undefined : (dispenseForm.batch_number || undefined),
      expiry_date: dispenseForm.batch_id ? undefined : (dispenseForm.expiry_date || undefined),
      unit_cost: dispenseForm.unit_cost ? Number(dispenseForm.unit_cost) : undefined,
      counselling_given: dispenseForm.counselling_given,
      counselling_notes: dispenseForm.counselling_notes || undefined,
      ...overrideFlags,
    }),
    onSuccess: (res: any) => {
      if (res?.ok === false) {
        if (res.allergy_alert) setSafetyAlert({ kind: "allergy", items: res.allergies ?? [], message: res.message });
        else if (res.ddi_alert) setSafetyAlert({ kind: "ddi", items: res.interactions ?? [], message: res.message });
        return;
      }
      toast({ title: "Dispensed", description: `${dispenseForm.quantity_dispensed} ${rx.unit ?? ""} — status: ${res.prescription_status}` });
      setDispenseForm({ ...emptyDispenseForm });
      setSafetyAlert(null);
      invalidateAll();
    },
    onError: async (e: any) => {
      if (await handlePayFirst(e, "prescription", rxId, payFirstRoles, toast)) return;
      toast({ title: "Failed to dispense", description: e.message, variant: "destructive" });
    },
  });

  const administerMut = useMutation({
    mutationFn: () => api.hospital.pharmacy.administer(rxId, {
      dose_given: administerForm.dose_given || undefined,
      route: administerForm.route || undefined,
      site: administerForm.site || undefined,
      status: administerForm.status,
      omission_reason: administerForm.omission_reason || undefined,
      witnessed_by: administerForm.witnessed_by || undefined,
      notes: administerForm.notes || undefined,
    }),
    onSuccess: () => {
      toast({ title: "Administration recorded" });
      setAdministerForm({ ...emptyAdministerForm });
      invalidateAll();
    },
    onError: (e: any) => toast({ title: "Failed to record administration", description: e.message, variant: "destructive" }),
  });

  const cancelMut = useMutation({
    mutationFn: () => api.hospital.pharmacy.cancel(rxId, {}),
    onSuccess: () => { toast({ title: "Prescription cancelled" }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Failed to cancel", description: e.message, variant: "destructive" }),
  });

  const discountMut = useMutation({
    mutationFn: () =>
      api.hospital.pharmacy.requestDispensingDiscount(discountRowId!, {
        amount: Number(discountForm.amount),
        discount_type: discountForm.discount_type,
        reason: discountForm.reason.trim() || undefined,
      }),
    onSuccess: () => {
      setDiscountRowId(null);
      setDiscountForm({ amount: "", discount_type: "staff", reason: "" });
      void qc.invalidateQueries({ queryKey: ["pharmacy-prescription", rx.id] });
      toast({
        title: "Discount sent for approval",
        description: "Nothing is deducted until an administrator approves it.",
      });
    },
    onError: (e: any) =>
      toast({ title: "Could not request it", description: e?.message, variant: "destructive" }),
  });

  const returnMut = useMutation({
    mutationFn: () => api.hospital.pharmacy.createReturn({
      dispensing_id: returnRowId,
      quantity_returned: Number(returnForm.quantity_returned),
      reason: returnForm.reason || undefined,
      restock: returnForm.restock,
    }),
    onSuccess: () => {
      toast({ title: "Return recorded" });
      setReturnRowId(null);
      setReturnForm({ ...emptyReturnForm });
      invalidateAll();
    },
    onError: (e: any) => toast({ title: "Failed to record return", description: e.message, variant: "destructive" }),
  });

  const signatureMut = useMutation({
    mutationFn: () => {
      if (!signatureRowId || !signatureFile) return Promise.reject();
      return api.hospital.pharmacy.uploadSignature(signatureRowId, signatureFile);
    },
    onSuccess: () => {
      toast({ title: "Signature captured" });
      setSignatureRowId(null);
      setSignatureFile(null);
      invalidateAll();
    },
    onError: (e: any) => toast({ title: "Upload failed", description: e.message, variant: "destructive" }),
  });

  const status = rx.status;
  const canDispense  = remainingQuantity > 0 && !["cancelled", "returned"].includes(status ?? "");
  const canAdminister = ["dispensed", "partially_dispensed"].includes(status ?? "");
  const canCancel    = !["dispensed", "cancelled"].includes(status ?? "");

  return (
    <Sheet open onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className={cn(PANEL_WIDTH.default, "overflow-y-auto p-0 flex flex-col")} side="right">
        {isLoading && !data ? (
          <LoadingSkeleton />
        ) : (
          <>
            {/* Header */}
            <SheetHeader className="px-5 pt-5 pb-4 border-b shrink-0">
              <div className="flex items-start gap-3">
                <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                  <Pill className="h-5 w-5 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <SheetTitle className="text-base leading-tight">{rx.drug_name ?? "Prescription"}</SheetTitle>
                  <div className="flex flex-wrap items-center gap-2 mt-1">
                    <span className="text-xs text-muted-foreground">{rx.patient_name ?? `Patient ID ${rx.patient_id}`}</span>
                    {rx.patient_mrn && <Badge variant="outline" className="text-xs font-mono">{rx.patient_mrn}</Badge>}
                    <StatusBadge status={status} />
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">Rx #{rx.id} · Prescribed {elapsed(rx.prescribed_at)} ago</p>
                  {hmoBill && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className="border-violet-400 text-xs font-semibold text-violet-800 dark:text-violet-300">
                        HMO · {hmoBill.hmo_name ?? "insured"}{hmoBill.membership_id ? ` · ${hmoBill.membership_id}` : ""}
                      </Badge>
                      <Button size="sm" variant="outline" className="h-6 px-2 text-xs"
                        onClick={() => window.open(`#/hospital/billing/${hmoBill.id}/invoice?claims=1`, "_blank")}>
                        Claims form
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            </SheetHeader>

            {/* Tabs */}
            <Tabs value={tab} onValueChange={setTab} className="flex-1 flex flex-col min-h-0">
              <TabsList className="mx-5 mt-3 bg-muted border border-border shrink-0 flex-wrap h-auto">
                <TabsTrigger value="detail">Detail</TabsTrigger>
                <TabsTrigger value="dispense">Dispense</TabsTrigger>
                <TabsTrigger value="administer">Administer</TabsTrigger>
                <TabsTrigger value="history">History</TabsTrigger>
              </TabsList>

              <div className="flex-1 overflow-y-auto px-5 py-4">
                {/* ── Detail ── */}
                <TabsContent value="detail" className="mt-0 space-y-4">
                  <section>
                    <SectionLabel icon={<User className="h-3.5 w-3.5" />} label="Patient" />
                    <DetailRow label="Name"   value={rx.patient_name} />
                    <DetailRow label="MRN"    value={rx.patient_mrn} mono />
                    <DetailRow label="Gender" value={rx.patient_gender} />
                    <DetailRow label="DOB"    value={rx.patient_dob} />
                  </section>
                  <Separator />
                  <section>
                    <SectionLabel icon={<Pill className="h-3.5 w-3.5" />} label="Prescription Details" />
                    <DetailRow label="Drug"        value={rx.drug_name} />
                    <DetailRow label="Dosage"      value={rx.dosage} />
                    <DetailRow label="Frequency"   value={rx.frequency} />
                    <DetailRow label="Duration"    value={rx.duration} />
                    <DetailRow label="Route"       value={rx.route} />
                    <DetailRow label="Quantity"    value={rx.quantity != null ? `${rx.quantity} ${rx.unit ?? ""}` : undefined} />
                    <DetailRow label="Special Instructions" value={rx.special_instructions} />
                    <DetailRow label="Prescribed by" value={rx.prescribed_by} mono />
                    <DetailRow label="Prescribed at" value={rx.prescribed_at
                      ? new Date(rx.prescribed_at).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
                      : undefined}
                    />
                  </section>
                  <Separator />
                  <section>
                    <SectionLabel icon={<ClipboardList className="h-3.5 w-3.5" />} label="Workflow" />
                    <WorkflowProgress status={status} />
                    <p className="text-xs text-muted-foreground mt-2">
                      {marEntries.length > 0
                        ? `${marEntries.length} dose(s) administered, last ${elapsed(marEntries[0]?.admin_time)} ago`
                        : "No doses administered yet"}
                    </p>
                  </section>
                </TabsContent>

                {/* ── Dispense ── */}
                <TabsContent value="dispense" className="mt-0 space-y-4">
                  <section className="rounded-md border p-3 text-sm flex items-center justify-between">
                    <div>
                      <p className="text-xs text-muted-foreground">Total Dispensed</p>
                      <p className="font-semibold">{totalDispensed} / {rx.quantity} {rx.unit}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-muted-foreground">Remaining</p>
                      <p className={cn("font-semibold", remainingQuantity > 0 ? "text-yellow-500" : "text-green-500")}>{remainingQuantity} {rx.unit}</p>
                    </div>
                  </section>

                  {dispensingRecords.length === 0 ? (
                    <p className="text-xs text-muted-foreground">No dispensing events recorded yet.</p>
                  ) : (
                    <div className="space-y-2">
                      {dispensingRecords.map((d: any) => {
                        const returned = returnsByDispensing.get(String(d.id)) ?? 0;
                        const returnable = Number(d.quantity_dispensed ?? 0) - returned;
                        return (
                          <div key={d.id} className="rounded-md border p-2 text-xs space-y-1">
                            <div className="flex items-center justify-between">
                              <span className="font-medium">{d.quantity_dispensed} {d.unit} dispensed</span>
                              <span className="text-muted-foreground">{elapsed(d.dispensed_at)} ago</span>
                            </div>
                            <div className="text-muted-foreground">
                              {[d.batch_number && `Batch ${d.batch_number}`, d.expiry_date && `Exp ${d.expiry_date}`, `by ${d.dispensed_by}`].filter(Boolean).join(" · ")}
                            </div>
                            {d.counselling_given && <p className="text-green-500">Counselling given</p>}
                            {returned > 0 && <p className="text-orange-500">{returned} {d.unit} returned</p>}
                            {d.discount_status && d.discount_status !== "none" && (
                              <p className={cn(
                                "text-xs",
                                d.discount_status === "approved" ? "text-green-600"
                                  : d.discount_status === "rejected" ? "text-muted-foreground"
                                  : "text-amber-600",
                              )}>
                                {d.discount_status === "pending"
                                  ? `Discount of ₦${Number(d.discount).toLocaleString()} awaiting approval`
                                  : d.discount_status === "approved"
                                  ? `₦${Number(d.discount).toLocaleString()} discount approved`
                                  : "Discount rejected"}
                              </p>
                            )}
                            <div className="flex gap-2 pt-1">
                              {Number(d.total_cost) > 0 &&
                               (!d.discount_status || d.discount_status === "none" || d.discount_status === "rejected") && (
                                <Button size="sm" variant="ghost" className="h-6 px-2 text-xs gap-1"
                                  onClick={() => { setDiscountRowId(d.id); setDiscountForm({ amount: "", discount_type: "staff", reason: "" }); }}>
                                  <Percent className="h-3 w-3" /> Request Discount
                                </Button>
                              )}
                              {returnable > 0 && (
                                <Button size="sm" variant="ghost" className="h-6 px-2 text-xs gap-1"
                                  onClick={() => { setReturnRowId(d.id); setReturnForm({ ...emptyReturnForm }); }}>
                                  <Undo2 className="h-3 w-3" /> Record Return
                                </Button>
                              )}
                              {d.signature_url ? (
                                <Button size="sm" variant="ghost" className="h-6 px-2 text-xs gap-1"
                                  onClick={() => window.open(api.hospital.pharmacy.signatureUrl(String(d.signature_url).split("/").pop()!), "_blank")}>
                                  <Eye className="h-3 w-3" /> View Signature
                                </Button>
                              ) : (
                                <Button size="sm" variant="ghost" className="h-6 px-2 text-xs gap-1"
                                  onClick={() => { setSignatureRowId(d.id); setSignatureFile(null); }}>
                                  <PenLine className="h-3 w-3" /> Capture Signature
                                </Button>
                              )}
                            </div>

                            {discountRowId === d.id && (
                              <div className="mt-2 space-y-2 rounded border border-amber-500/30 bg-amber-500/5 p-2">
                                <div className="grid grid-cols-2 gap-2">
                                  <Input
                                    type="number" min="0" step="10"
                                    placeholder={`Amount (max ₦${Number(d.total_cost ?? 0).toLocaleString()})`}
                                    value={discountForm.amount}
                                    onChange={e => setDiscountForm(f => ({ ...f, amount: e.target.value }))}
                                  />
                                  <select
                                    className="h-9 rounded-md border bg-background px-2 text-xs"
                                    value={discountForm.discount_type}
                                    onChange={e => setDiscountForm(f => ({ ...f, discount_type: e.target.value }))}
                                  >
                                    <option value="staff">Staff</option>
                                    <option value="staff_dependant">Staff dependant</option>
                                    <option value="goodwill">Goodwill</option>
                                    <option value="hardship">Hardship</option>
                                    <option value="other">Other</option>
                                  </select>
                                </div>
                                <Input
                                  placeholder="Reason (optional)"
                                  value={discountForm.reason}
                                  onChange={e => setDiscountForm(f => ({ ...f, reason: e.target.value }))}
                                />
                                <p className="text-xs text-muted-foreground">
                                  An administrator approves this before anything is deducted.
                                </p>
                                <div className="flex justify-end gap-2">
                                  <Button size="sm" variant="ghost" className="h-7 text-xs"
                                    onClick={() => setDiscountRowId(null)}>Cancel</Button>
                                  <Button size="sm" className="h-7 text-xs"
                                    disabled={discountMut.isPending || !(Number(discountForm.amount) > 0)}
                                    onClick={() => discountMut.mutate()}>
                                    {discountMut.isPending && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
                                    Send for approval
                                  </Button>
                                </div>
                              </div>
                            )}

                            {returnRowId === d.id && (
                              <div className="mt-2 rounded border border-orange-500/30 bg-orange-500/5 p-2 space-y-2">
                                <div className="grid grid-cols-2 gap-2">
                                  <Input placeholder={`Qty (max ${returnable})`} type="number" value={returnForm.quantity_returned}
                                    onChange={e => setReturnForm(f => ({ ...f, quantity_returned: e.target.value }))} />
                                  <div className="flex items-center gap-1.5">
                                    <Checkbox id={`restock-${d.id}`} checked={returnForm.restock}
                                      onCheckedChange={v => setReturnForm(f => ({ ...f, restock: !!v }))} />
                                    <Label htmlFor={`restock-${d.id}`} className="text-xs cursor-pointer">Restock</Label>
                                  </div>
                                </div>
                                <Input placeholder="Reason (optional)" value={returnForm.reason}
                                  onChange={e => setReturnForm(f => ({ ...f, reason: e.target.value }))} />
                                <div className="flex gap-2">
                                  <Button size="sm" variant="outline" className="h-6 text-xs flex-1" onClick={() => setReturnRowId(null)}>Cancel</Button>
                                  <Button size="sm" className="h-6 text-xs flex-1"
                                    disabled={!returnForm.quantity_returned || Number(returnForm.quantity_returned) > returnable || returnMut.isPending}
                                    onClick={() => returnMut.mutate()}>
                                    {returnMut.isPending && <Loader2 className="h-3 w-3 animate-spin mr-1" />}Submit
                                  </Button>
                                </div>
                              </div>
                            )}

                            {signatureRowId === d.id && (
                              <div className="mt-2 rounded border border-border bg-muted/30 p-2 space-y-2">
                                <SignaturePad onChange={setSignatureFile} />
                                <Input type="file" accept="image/png,image/jpeg,image/webp" className="text-xs"
                                  title="Or upload a signature image from the signature tablet"
                                  onChange={e => setSignatureFile(e.target.files?.[0] ?? null)} />
                                <div className="flex gap-2">
                                  <Button size="sm" variant="outline" className="h-6 text-xs flex-1" onClick={() => setSignatureRowId(null)}>Cancel</Button>
                                  <Button size="sm" className="h-6 text-xs flex-1" disabled={!signatureFile || signatureMut.isPending}
                                    onClick={() => signatureMut.mutate()}>
                                    {signatureMut.isPending && <Loader2 className="h-3 w-3 animate-spin mr-1" />}Save signature
                                  </Button>
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {safetyAlert && (
                    <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 space-y-2">
                      <div className="flex items-center gap-1.5 text-red-500 text-sm font-medium">
                        <ShieldAlert className="h-4 w-4" /> {safetyAlert.kind === "allergy" ? "Allergy Alert" : "Drug Interaction Alert"}
                      </div>
                      <p className="text-xs text-muted-foreground">{safetyAlert.message}</p>
                      <ul className="text-xs space-y-1">
                        {safetyAlert.items.map((it: any, i: number) => (
                          <li key={i} className="text-red-700 dark:text-red-400">
                            {safetyAlert.kind === "allergy"
                              ? `${it.allergen} — ${it.severity}${it.reaction ? ` (${it.reaction})` : ""}`
                              : `${it.drug} — ${it.severity}${it.description ? `: ${it.description}` : ""}`}
                          </li>
                        ))}
                      </ul>
                      <Button size="sm" variant="destructive" className="w-full" disabled={dispenseMut.isPending}
                        onClick={() => dispenseMut.mutate(safetyAlert.kind === "allergy" ? { override_allergy: true } : { acknowledge_ddi: true })}>
                        {dispenseMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
                        Override & Dispense
                      </Button>
                    </div>
                  )}

                  {canDispense && !safetyAlert && (
                    <section className="space-y-2 border-t pt-3">
                      <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Dispense</Label>
                      <div className="grid grid-cols-2 gap-2">
                        <Input placeholder={`Quantity (max ${remainingQuantity})`} type="number" value={dispenseForm.quantity_dispensed}
                          onChange={e => setDispenseForm(f => ({ ...f, quantity_dispensed: e.target.value }))} />
                        <Input placeholder="Unit cost" type="number" value={dispenseForm.unit_cost}
                          onChange={e => setDispenseForm(f => ({ ...f, unit_cost: e.target.value }))} />
                        {availableBatches.length > 0 ? (
                          <div className="col-span-2">
                            <Select value={dispenseForm.batch_id || "auto"} onValueChange={v => setDispenseForm(f => ({ ...f, batch_id: v === "auto" ? "" : v }))}>
                              <SelectTrigger><SelectValue /></SelectTrigger>
                              <SelectContent>
                                <SelectItem value="auto">Auto (FEFO — recommended)</SelectItem>
                                {availableBatches.map((b: any) => (
                                  <SelectItem key={b.id} value={String(b.id)}>
                                    {b.batch_number} — exp {b.expiry_date ?? "n/a"} — {b.quantity_on_hand} left
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        ) : (
                          <>
                            <Input placeholder="Batch number" value={dispenseForm.batch_number}
                              onChange={e => setDispenseForm(f => ({ ...f, batch_number: e.target.value }))} />
                            <Input placeholder="Expiry date" type="date" value={dispenseForm.expiry_date}
                              onChange={e => setDispenseForm(f => ({ ...f, expiry_date: e.target.value }))} />
                          </>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Checkbox id="counselling" checked={dispenseForm.counselling_given}
                          onCheckedChange={v => setDispenseForm(f => ({ ...f, counselling_given: !!v }))} />
                        <Label htmlFor="counselling" className="text-xs cursor-pointer">Counselling given</Label>
                      </div>
                      {dispenseForm.counselling_given && (
                        <Textarea rows={2} placeholder="Counselling notes" value={dispenseForm.counselling_notes}
                          onChange={e => setDispenseForm(f => ({ ...f, counselling_notes: e.target.value }))} />
                      )}
                      <Button size="sm" className="w-full gap-1.5"
                        disabled={!dispenseForm.quantity_dispensed.trim() || Number(dispenseForm.quantity_dispensed) > remainingQuantity || dispenseMut.isPending}
                        onClick={() => dispenseMut.mutate({})}>
                        {dispenseMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Pill className="h-3.5 w-3.5" />}
                        Dispense
                      </Button>
                    </section>
                  )}
                </TabsContent>

                {/* ── Administer ── */}
                <TabsContent value="administer" className="mt-0 space-y-4">
                  {marEntries.length === 0 ? (
                    <p className="text-xs text-muted-foreground">No administration events recorded yet.</p>
                  ) : (
                    <div className="space-y-2">
                      {marEntries.map((m: any) => (
                        <div key={m.id} className="rounded-md border p-2 text-xs space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="font-medium">{m.dose_given} {m.route ? `· ${m.route}` : ""}{m.site ? ` · ${m.site}` : ""}</span>
                            <MedAdminStatusBadge status={m.status} />
                          </div>
                          <p className="text-muted-foreground">By {m.administered_by} · {elapsed(m.admin_time)} ago{m.witnessed_by ? ` · Witnessed by ${m.witnessed_by}` : ""}</p>
                          {m.omission_reason && <p className="text-orange-500">Reason: {m.omission_reason}</p>}
                          {m.notes && <p className="text-muted-foreground">{m.notes}</p>}
                        </div>
                      ))}
                    </div>
                  )}

                  {canAdminister && (
                    <section className="space-y-2 border-t pt-3">
                      <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Record Administration</Label>
                      <div className="grid grid-cols-2 gap-2">
                        <Input placeholder="Dose given" value={administerForm.dose_given || rx.dosage || ""}
                          onChange={e => setAdministerForm(f => ({ ...f, dose_given: e.target.value }))} />
                        <Input placeholder="Route" value={administerForm.route || rx.route || ""}
                          onChange={e => setAdministerForm(f => ({ ...f, route: e.target.value }))} />
                        <Input placeholder="Site (optional)" value={administerForm.site}
                          onChange={e => setAdministerForm(f => ({ ...f, site: e.target.value }))} />
                        <Select value={administerForm.status} onValueChange={v => setAdministerForm(f => ({ ...f, status: v }))}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {["given", "refused", "held", "not_available", "omitted"].map(s => (
                              <SelectItem key={s} value={s} className="capitalize">{s.replace(/_/g, " ")}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      {administerForm.status !== "given" && (
                        <Input placeholder="Reason" value={administerForm.omission_reason}
                          onChange={e => setAdministerForm(f => ({ ...f, omission_reason: e.target.value }))} />
                      )}
                      <Input placeholder="Witnessed by (optional)" value={administerForm.witnessed_by}
                        onChange={e => setAdministerForm(f => ({ ...f, witnessed_by: e.target.value }))} />
                      <Textarea rows={2} placeholder="Notes (optional)" value={administerForm.notes}
                        onChange={e => setAdministerForm(f => ({ ...f, notes: e.target.value }))} />
                      <Button size="sm" className="w-full gap-1.5" disabled={administerMut.isPending} onClick={() => administerMut.mutate()}>
                        {administerMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ClipboardList className="h-3.5 w-3.5" />}
                        Record Administration
                      </Button>
                    </section>
                  )}
                </TabsContent>

              <TabsContent value="history" className="mt-0">
                {/* The complete regimen, built from what was dispensed. */}
                <MedicationHistoryTab patientId={rx.patient_id} />
              </TabsContent>
              </div>
            </Tabs>

            {/* Footer action bar */}
            <Separator className="shrink-0" />
            <div className="px-5 py-3 flex flex-wrap gap-2 shrink-0">
              {canDispense && (
                <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setTab("dispense")}>
                  <Pill className="h-3.5 w-3.5" /> Dispense
                </Button>
              )}
              {canAdminister && (
                <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setTab("administer")}>
                  <ClipboardList className="h-3.5 w-3.5" /> Administer
                </Button>
              )}
              {canCancel && (
                <Button size="sm" variant="outline" className="gap-1.5 text-red-500 border-red-500/30 hover:bg-red-500/10"
                  disabled={cancelMut.isPending}
                  onClick={() => { if (window.confirm("Cancel this prescription?")) cancelMut.mutate(); }}>
                  <XCircle className="h-3.5 w-3.5" /> Cancel
                </Button>
              )}
              <Button size="sm" variant="ghost" className="gap-1.5 ml-auto"
                disabled={!rx.patient_mrn}
                onClick={() => { if (rx.patient_mrn) { navigate(`/hospital/patients/${rx.patient_mrn}`); onClose(); } }}>
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
