import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Users, ShieldCheck, FileText, Loader2, Plus, Pencil, Check, X, ExternalLink,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { SectionLabel, HMO } from "@/components/hmo/hmo-shared";

interface PatientRow {
  patient_id: number;
  patient_name?: string | null;
  mrn?: string | null;
  hmo_name?: string | null;
}

const POLICY_STATUS_OPTIONS = ["active", "expired", "suspended", "inactive"] as const;

const CLAIM_STATUS_COLORS: Record<string, string> = {
  submitted:       "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/30",
  pre_authorised:  "bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/30",
  approved:        "bg-green-500/10 text-green-700 dark:text-green-400 border-green-500/30",
  rejected:        "bg-red-500/10 text-red-700 dark:text-red-400 border-red-500/30",
  paid:            "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/30",
  disputed:        "bg-orange-500/10 text-orange-700 dark:text-orange-400 border-orange-500/30",
};

export function PatientHMOWorkspacePanel({ patient, hmos, onClose, onViewProvider }: {
  patient: PatientRow;
  hmos: HMO[];
  onClose: () => void;
  onViewProvider: (hmoId: number) => void;
}) {
  const qc = useQueryClient();
  const { toast } = useToast();

  const [editingPolicyId, setEditingPolicyId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState({ hmo_id: "", membership_id: "", status: "active" });
  const [addOpen, setAddOpen] = useState(false);
  const [addForm, setAddForm] = useState({ hmo_id: "", membership_id: "", status: "active" });

  const { data: policiesData, isLoading: policiesLoading } = useQuery({
    queryKey: ["patient-insurance", patient.patient_id],
    queryFn: () => api.hospital.coverage.listPatientInsurance(patient.patient_id),
  });
  const policies: any[] = policiesData?.policies ?? [];

  const { data: claimsData, isLoading: claimsLoading } = useQuery({
    queryKey: ["patient-claims", patient.patient_id],
    queryFn: () => api.hospital.coverage.listClaims({ patient_id: patient.patient_id }),
  });
  const claims: any[] = claimsData?.claims ?? [];

  const invalidatePolicies = () => {
    void qc.invalidateQueries({ queryKey: ["patient-insurance", patient.patient_id] });
    void qc.invalidateQueries({ queryKey: ["hmo-patients"] });
  };

  const updatePolicyMut = useMutation({
    mutationFn: (id: number) => api.hospital.coverage.updatePatientInsurance(id, {
      hmo_id: editForm.hmo_id ? Number(editForm.hmo_id) : undefined,
      membership_id: editForm.membership_id || undefined,
      status: editForm.status || undefined,
    }),
    onSuccess: () => { toast({ title: "Coverage updated" }); setEditingPolicyId(null); invalidatePolicies(); },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  const addPolicyMut = useMutation({
    mutationFn: () => api.hospital.coverage.createPatientInsurance({
      patient_id: patient.patient_id,
      hmo_id: Number(addForm.hmo_id),
      membership_id: addForm.membership_id,
      status: addForm.status,
      is_primary: true,
    }),
    onSuccess: () => {
      toast({ title: "Coverage added" });
      setAddOpen(false);
      setAddForm({ hmo_id: "", membership_id: "", status: "active" });
      invalidatePolicies();
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  const claimMut = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) => api.hospital.coverage.updateClaim(id, { status }),
    onSuccess: () => {
      toast({ title: "Claim updated" });
      void qc.invalidateQueries({ queryKey: ["patient-claims", patient.patient_id] });
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  function startEdit(p: any) {
    setEditingPolicyId(p.id);
    setEditForm({ hmo_id: String(p.hmo_id ?? ""), membership_id: p.membership_id ?? "", status: p.status ?? "active" });
  }

  return (
    <Sheet open onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className="w-[560px] sm:w-[640px] overflow-y-auto p-0 flex flex-col" side="right">
        <SheetHeader className="px-5 pt-5 pb-4 border-b shrink-0">
          <div className="flex items-start gap-3">
            <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
              <Users className="h-5 w-5 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <SheetTitle className="text-base leading-tight">{patient.patient_name ?? `Patient #${patient.patient_id}`}</SheetTitle>
              {patient.mrn && <span className="text-xs text-muted-foreground font-mono">{patient.mrn}</span>}
            </div>
          </div>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {/* ── Coverage / Policies ─────────────────────────────────────────── */}
          <section>
            <div className="flex items-center justify-between mb-2">
              <SectionLabel icon={<ShieldCheck className="h-3.5 w-3.5" />} label="HMO Coverage" />
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setAddOpen(true)}>
                <Plus className="h-3 w-3 mr-1" /> Add Coverage
              </Button>
            </div>
            {policiesLoading ? (
              <div className="flex justify-center py-4"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>
            ) : policies.length === 0 ? (
              <p className="text-xs text-muted-foreground py-2">
                {patient.hmo_name
                  ? `Legacy record only: ${patient.hmo_name} (no structured policy on file yet — add one above to make it fully manageable)`
                  : "No HMO coverage on file"}
              </p>
            ) : (
              <div className="space-y-2">
                {policies.map((p: any) => (
                  <div key={p.id} className="rounded-lg border border-border/50 p-2.5">
                    {editingPolicyId === p.id ? (
                      <div className="space-y-2">
                        <Select value={editForm.hmo_id} onValueChange={v => setEditForm(f => ({ ...f, hmo_id: v }))}>
                          <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="HMO…" /></SelectTrigger>
                          <SelectContent>{hmos.map(h => <SelectItem key={h.id} value={String(h.id)}>{h.name}</SelectItem>)}</SelectContent>
                        </Select>
                        <Input
                          className="h-8 text-xs"
                          placeholder="Membership ID"
                          value={editForm.membership_id}
                          onChange={e => setEditForm(f => ({ ...f, membership_id: e.target.value }))}
                        />
                        <Select value={editForm.status} onValueChange={v => setEditForm(f => ({ ...f, status: v }))}>
                          <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {POLICY_STATUS_OPTIONS.map(s => <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>)}
                          </SelectContent>
                        </Select>
                        <div className="flex gap-2 justify-end">
                          <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setEditingPolicyId(null)}>
                            <X className="h-3 w-3" />
                          </Button>
                          <Button size="sm" className="h-7 text-xs" disabled={updatePolicyMut.isPending} onClick={() => updatePolicyMut.mutate(p.id)}>
                            {updatePolicyMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between text-xs">
                        <div>
                          <p className="font-medium">{p.hmo_name ?? `HMO #${p.hmo_id}`}</p>
                          <p className="text-muted-foreground">{p.membership_id || "—"}{p.is_primary ? " · Primary" : ""}</p>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Badge variant="outline" className={cn("text-xs capitalize",
                            p.status === "active" ? "border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-400" : "border-slate-500/30 bg-slate-500/10 text-slate-700 dark:text-slate-400")}>
                            {p.status}
                          </Badge>
                          <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => startEdit(p)}>
                            <Pencil className="h-3 w-3" />
                          </Button>
                          {p.hmo_id && (
                            <Button size="sm" variant="ghost" className="h-6 w-6 p-0" title="View insurance provider" onClick={() => onViewProvider(p.hmo_id)}>
                              <ExternalLink className="h-3 w-3" />
                            </Button>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          <Separator />

          {/* ── Claims ──────────────────────────────────────────────────────── */}
          <section>
            <SectionLabel icon={<FileText className="h-3.5 w-3.5" />} label="Claims" />
            {claimsLoading ? (
              <div className="flex justify-center py-4"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>
            ) : claims.length === 0 ? (
              <p className="text-xs text-muted-foreground py-2">No claims on file for this patient</p>
            ) : (
              <div className="space-y-2">
                {claims.map((c: any) => (
                  <div key={c.id} className="rounded-lg border border-border/50 p-2.5 text-xs">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium">₦{Number(c.claim_amount ?? 0).toLocaleString()}</span>
                      <Badge variant="outline" className={cn("text-xs capitalize", CLAIM_STATUS_COLORS[c.status] ?? "")}>
                        {String(c.status ?? "").replace("_", " ")}
                      </Badge>
                    </div>
                    <p className="text-muted-foreground">
                      {c.hmo_provider ?? "—"} · Submitted {c.submitted_at ? new Date(c.submitted_at).toLocaleDateString() : "—"}
                    </p>
                    {c.status === "submitted" && (
                      <div className="flex gap-2 mt-2">
                        <Button size="sm" variant="outline" className="h-6 text-xs flex-1" disabled={claimMut.isPending}
                          onClick={() => claimMut.mutate({ id: c.id, status: "approved" })}>
                          Approve
                        </Button>
                        <Button size="sm" variant="outline" className="h-6 text-xs flex-1 text-red-600 dark:text-red-400" disabled={claimMut.isPending}
                          onClick={() => claimMut.mutate({ id: c.id, status: "rejected" })}>
                          Reject
                        </Button>
                      </div>
                    )}
                    {c.status === "approved" && (
                      <Button size="sm" variant="outline" className="h-6 text-xs w-full mt-2" disabled={claimMut.isPending}
                        onClick={() => claimMut.mutate({ id: c.id, status: "paid" })}>
                        Mark Paid
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </SheetContent>

      {/* ── Add Coverage Dialog ───────────────────────────────────────────── */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Add HMO Coverage</DialogTitle>
            <DialogDescription>New coverage record for {patient.patient_name ?? `patient #${patient.patient_id}`}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>HMO *</Label>
              <Select value={addForm.hmo_id} onValueChange={v => setAddForm(f => ({ ...f, hmo_id: v }))}>
                <SelectTrigger><SelectValue placeholder="Select HMO…" /></SelectTrigger>
                <SelectContent>{hmos.map(h => <SelectItem key={h.id} value={String(h.id)}>{h.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Membership ID *</Label>
              <Input value={addForm.membership_id} onChange={e => setAddForm(f => ({ ...f, membership_id: e.target.value }))} placeholder="e.g. MH/CONOIL/086/G-C" />
            </div>
            <div className="space-y-1">
              <Label>Status</Label>
              <Select value={addForm.status} onValueChange={v => setAddForm(f => ({ ...f, status: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {POLICY_STATUS_OPTIONS.map(s => <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>Cancel</Button>
            <Button disabled={!addForm.hmo_id || !addForm.membership_id.trim() || addPolicyMut.isPending} onClick={() => addPolicyMut.mutate()}>
              {addPolicyMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Add
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Sheet>
  );
}
