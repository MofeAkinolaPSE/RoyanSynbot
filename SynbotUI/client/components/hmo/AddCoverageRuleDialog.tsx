import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { COVERAGE_TYPES, LIMIT_TYPES, HMO, Service } from "@/components/hmo/hmo-shared";

const emptyRuleForm = {
  hmo_id: "",
  service_id: "",
  coverage_type: "percent" as typeof COVERAGE_TYPES[number],
  coverage_value: "",
  requires_approval: false,
  limit_type: "none" as typeof LIMIT_TYPES[number],
  limit_value: "",
  notes: "",
};

interface AddCoverageRuleDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultHmoId?: number | string;
  hmos: HMO[];
  services: Service[];
}

export function AddCoverageRuleDialog({ open, onOpenChange, defaultHmoId, hmos, services }: AddCoverageRuleDialogProps) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [ruleForm, setRuleForm] = useState({ ...emptyRuleForm });

  useEffect(() => {
    if (open) {
      setRuleForm({ ...emptyRuleForm, hmo_id: defaultHmoId ? String(defaultHmoId) : "" });
    }
  }, [open, defaultHmoId]);

  const ruleMut = useMutation({
    mutationFn: () => api.hospital.coverage.createRule({
      ...ruleForm,
      hmo_id: parseInt(ruleForm.hmo_id),
      service_id: parseInt(ruleForm.service_id),
      coverage_value: parseFloat(ruleForm.coverage_value) || 0,
      limit_value: ruleForm.limit_value ? parseFloat(ruleForm.limit_value) : undefined,
    }),
    onSuccess: () => {
      toast({ title: "Coverage rule created" });
      onOpenChange(false);
      void qc.invalidateQueries({ queryKey: ["coverage-rules"] });
    },
    onError: (e: any) => toast({ title: "Failed", description: e.message, variant: "destructive" }),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Coverage Rule</DialogTitle>
          <DialogDescription>Define what an HMO covers for a given service</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1">
            <Label>HMO *</Label>
            <Select value={ruleForm.hmo_id} onValueChange={v => setRuleForm(f => ({ ...f, hmo_id: v }))}>
              <SelectTrigger><SelectValue placeholder="Select HMO" /></SelectTrigger>
              <SelectContent>
                {hmos.map(h => <SelectItem key={h.id} value={String(h.id)}>{h.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Service *</Label>
            <Select value={ruleForm.service_id} onValueChange={v => setRuleForm(f => ({ ...f, service_id: v }))}>
              <SelectTrigger><SelectValue placeholder="Select service" /></SelectTrigger>
              <SelectContent>
                {services.map(s => <SelectItem key={s.id} value={String(s.id)}>{s.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Coverage Type</Label>
              <Select value={ruleForm.coverage_type} onValueChange={v => setRuleForm(f => ({ ...f, coverage_type: v as any }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {COVERAGE_TYPES.map(t => <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>
                {ruleForm.coverage_type === "percent" ? "Coverage %" : ruleForm.coverage_type === "fixed" ? "Fixed Amount (₦)" : "Value"}
              </Label>
              <Input
                type="number"
                min={0}
                max={ruleForm.coverage_type === "percent" ? 100 : undefined}
                value={ruleForm.coverage_value}
                onChange={e => setRuleForm(f => ({ ...f, coverage_value: e.target.value }))}
                placeholder={ruleForm.coverage_type === "percent" ? "e.g. 80" : "e.g. 5000"}
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <input
              id="requires-approval"
              type="checkbox"
              checked={ruleForm.requires_approval}
              onChange={e => setRuleForm(f => ({ ...f, requires_approval: e.target.checked }))}
              className="rounded border-border"
            />
            <Label htmlFor="requires-approval">Requires pre-authorization</Label>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Limit Type</Label>
              <Select value={ruleForm.limit_type} onValueChange={v => setRuleForm(f => ({ ...f, limit_type: v as any }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {LIMIT_TYPES.map(t => <SelectItem key={t} value={t} className="capitalize">{t.replace(/_/g, " ")}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {ruleForm.limit_type !== "none" && (
              <div className="space-y-1">
                <Label>Limit (₦)</Label>
                <Input
                  type="number"
                  min={0}
                  value={ruleForm.limit_value}
                  onChange={e => setRuleForm(f => ({ ...f, limit_value: e.target.value }))}
                  placeholder="e.g. 50000"
                />
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={!ruleForm.hmo_id || !ruleForm.service_id || ruleMut.isPending} onClick={() => ruleMut.mutate()}>
            {ruleMut.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Create Rule
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
