import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Building2, CheckCircle2, XCircle, ListChecks, FileText, Loader2, Plus, Pencil, Check, X,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { DetailRow, SectionLabel, HMO, Service } from "@/components/hmo/hmo-shared";
import { AddCoverageRuleDialog } from "@/components/hmo/AddCoverageRuleDialog";

interface HMOWorkspacePanelProps {
  hmo: HMO;
  hmos: HMO[];
  services: Service[];
  onClose: () => void;
}

export function HMOWorkspacePanel({ hmo, hmos, services, onClose }: HMOWorkspacePanelProps) {
  const qc = useQueryClient();
  const { toast } = useToast();

  const [ruleDialogOpen, setRuleDialogOpen] = useState(false);
  const [planDialogOpen, setPlanDialogOpen] = useState(false);
  const [planForm, setPlanForm] = useState({ name: "", plan_code: "", notes: "" });

  const [editingInfo, setEditingInfo] = useState(false);
  const [infoForm, setInfoForm] = useState({
    contact_phone: hmo.contact_phone ?? "", contact_email: hmo.contact_email ?? "", notes: hmo.notes ?? "",
  });

  const invalidateHmos = () => void qc.invalidateQueries({ queryKey: ["hmos"] });

  const updateInfoMut = useMutation({
    mutationFn: () => api.hospital.coverage.updateHmo(hmo.id, infoForm),
    onSuccess: () => { toast({ title: "Provider info updated" }); setEditingInfo(false); invalidateHmos(); },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  const toggleActiveMut = useMutation({
    mutationFn: () => api.hospital.coverage.updateHmo(hmo.id, { is_active: hmo.is_active === false }),
    onSuccess: () => { toast({ title: hmo.is_active === false ? "Provider reactivated" : "Provider deactivated" }); invalidateHmos(); },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  const toggleRuleMut = useMutation({
    mutationFn: (rule: any) => api.hospital.coverage.updateRule(rule.id, { is_active: rule.is_active === false }),
    onSuccess: () => { toast({ title: "Rule updated" }); void qc.invalidateQueries({ queryKey: ["coverage-rules", String(hmo.id)] }); },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  const { data: rulesData, isLoading: rulesLoading } = useQuery({
    queryKey: ["coverage-rules", String(hmo.id)],
    queryFn: () => api.hospital.coverage.listRules(String(hmo.id)),
  });
  const rules: any[] = rulesData?.rules ?? [];

  const { data: plansData, isLoading: plansLoading } = useQuery({
    queryKey: ["hmo-plans", hmo.id],
    queryFn: () => api.hospital.coverage.listPlans(hmo.id, false),
  });
  const plans: any[] = plansData?.plans ?? [];

  const planMut = useMutation({
    mutationFn: () => api.hospital.coverage.createPlan(hmo.id, planForm),
    onSuccess: () => {
      toast({ title: "Plan created" });
      setPlanDialogOpen(false);
      setPlanForm({ name: "", plan_code: "", notes: "" });
      void qc.invalidateQueries({ queryKey: ["hmo-plans", hmo.id] });
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  return (
    <Sheet open onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className="w-[560px] sm:w-[640px] overflow-y-auto p-0 flex flex-col" side="right">
        <SheetHeader className="px-5 pt-5 pb-4 border-b shrink-0">
          <div className="flex items-start gap-3">
            <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
              <Building2 className="h-5 w-5 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <SheetTitle className="text-base leading-tight">{hmo.name}</SheetTitle>
              <div className="flex flex-wrap items-center gap-2 mt-1">
                {hmo.code && <span className="text-xs text-muted-foreground font-mono">{hmo.code}</span>}
                <button type="button" disabled={toggleActiveMut.isPending} onClick={() => toggleActiveMut.mutate()}>
                  {hmo.is_active !== false ? (
                    <Badge variant="outline" className="bg-green-500/10 text-green-700 dark:text-green-400 border-green-500/30 text-xs cursor-pointer">
                      <CheckCircle2 className="mr-1 h-3 w-3" /> Active
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="bg-slate-500/10 text-slate-700 dark:text-slate-400 border-slate-500/30 text-xs cursor-pointer">
                      <XCircle className="mr-1 h-3 w-3" /> Inactive
                    </Badge>
                  )}
                </button>
              </div>
            </div>
          </div>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          <section>
            <div className="flex items-center justify-between mb-2">
              <SectionLabel icon={<Building2 className="h-3.5 w-3.5" />} label="HMO Detail" />
              {!editingInfo && (
                <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => {
                  setInfoForm({ contact_phone: hmo.contact_phone ?? "", contact_email: hmo.contact_email ?? "", notes: hmo.notes ?? "" });
                  setEditingInfo(true);
                }}>
                  <Pencil className="h-3 w-3" />
                </Button>
              )}
            </div>
            {editingInfo ? (
              <div className="space-y-2">
                <Input className="h-8 text-xs" placeholder="Phone" value={infoForm.contact_phone} onChange={e => setInfoForm(f => ({ ...f, contact_phone: e.target.value }))} />
                <Input className="h-8 text-xs" placeholder="Email" value={infoForm.contact_email} onChange={e => setInfoForm(f => ({ ...f, contact_email: e.target.value }))} />
                <Input className="h-8 text-xs" placeholder="Notes" value={infoForm.notes} onChange={e => setInfoForm(f => ({ ...f, notes: e.target.value }))} />
                <div className="flex gap-2 justify-end">
                  <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setEditingInfo(false)}><X className="h-3 w-3" /></Button>
                  <Button size="sm" className="h-7 text-xs" disabled={updateInfoMut.isPending} onClick={() => updateInfoMut.mutate()}>
                    {updateInfoMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <DetailRow label="Phone" value={hmo.contact_phone} />
                <DetailRow label="Email" value={hmo.contact_email} />
                <DetailRow label="Notes" value={hmo.notes} />
              </>
            )}
          </section>

          <Separator />

          <section>
            <div className="flex items-center justify-between mb-2">
              <SectionLabel icon={<ListChecks className="h-3.5 w-3.5" />} label="Coverage Rules" />
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setRuleDialogOpen(true)}>
                <Plus className="h-3 w-3 mr-1" /> Add Rule
              </Button>
            </div>
            {rulesLoading ? (
              <div className="flex justify-center py-4"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>
            ) : rules.length === 0 ? (
              <p className="text-xs text-muted-foreground py-2">No coverage rules for this HMO yet</p>
            ) : (
              <div className="space-y-1.5">
                {rules.map((r: any) => {
                  const service = services.find(s => s.id === r.service_id);
                  return (
                    <div key={r.id} className={cn("flex items-center justify-between text-xs border-b border-border/30 pb-1.5 last:border-0", r.is_active === false && "opacity-50")}>
                      <span className="font-medium">{service?.name ?? `Service ${r.service_id}`}</span>
                      <span className="flex items-center gap-1.5 text-muted-foreground capitalize">
                        {r.coverage_type === "percent" ? `${r.coverage_value}%`
                          : r.coverage_type === "fixed" ? `₦${Number(r.coverage_value).toLocaleString()}`
                          : r.coverage_type}
                        {r.requires_approval && <span className="text-orange-500">· Pre-auth</span>}
                        <button
                          type="button"
                          className="underline decoration-dotted ml-1"
                          disabled={toggleRuleMut.isPending}
                          onClick={() => toggleRuleMut.mutate(r)}
                        >
                          {r.is_active === false ? "Enable" : "Disable"}
                        </button>
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          <Separator />

          <section>
            <div className="flex items-center justify-between mb-2">
              <SectionLabel icon={<FileText className="h-3.5 w-3.5" />} label="Plans" />
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setPlanDialogOpen(true)}>
                <Plus className="h-3 w-3 mr-1" /> Add Plan
              </Button>
            </div>
            {plansLoading ? (
              <div className="flex justify-center py-4"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>
            ) : plans.length === 0 ? (
              <p className="text-xs text-muted-foreground py-2">No plans configured for this HMO yet</p>
            ) : (
              <div className="space-y-1.5">
                {plans.map((p: any) => (
                  <div key={p.id} className="flex items-center justify-between text-xs border-b border-border/30 pb-1.5 last:border-0">
                    <span className="font-medium">{p.name}</span>
                    <span className="flex items-center gap-2">
                      {p.plan_code && <span className="text-muted-foreground font-mono">{p.plan_code}</span>}
                      {p.is_active === false && <Badge variant="outline" className="text-[12px] bg-slate-500/10 text-slate-700 dark:text-slate-400 border-slate-500/30">Inactive</Badge>}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </SheetContent>

      <AddCoverageRuleDialog
        open={ruleDialogOpen}
        onOpenChange={setRuleDialogOpen}
        defaultHmoId={hmo.id}
        hmos={hmos}
        services={services}
      />

      {/* ── Add Plan Dialog ──────────────────────────────────────────────── */}
      <Dialog open={planDialogOpen} onOpenChange={setPlanDialogOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Add Plan</DialogTitle>
            <DialogDescription>New plan tier for {hmo.name}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Plan Name *</Label>
              <Input value={planForm.name} onChange={e => setPlanForm(f => ({ ...f, name: e.target.value }))} placeholder="e.g. Gold" />
            </div>
            <div className="space-y-1">
              <Label>Plan Code</Label>
              <Input value={planForm.plan_code} onChange={e => setPlanForm(f => ({ ...f, plan_code: e.target.value }))} placeholder="e.g. GOLD-01" />
            </div>
            <div className="space-y-1">
              <Label>Notes</Label>
              <Input value={planForm.notes} onChange={e => setPlanForm(f => ({ ...f, notes: e.target.value }))} placeholder="Optional notes…" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPlanDialogOpen(false)}>Cancel</Button>
            <Button disabled={!planForm.name.trim() || planMut.isPending} onClick={() => planMut.mutate()}>
              {planMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create Plan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Sheet>
  );
}
