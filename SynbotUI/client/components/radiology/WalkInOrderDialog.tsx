import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ScanLine, Loader2, Search, UserCheck, AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

/**
 * Book a study for someone who walked in, with no doctor's request behind it.
 *
 * Radiology is both a hospital department and ScanCare, a standalone company.
 * Until now an order could only be created from a consultation — the department
 * could receive work but never originate it, so a client arriving and asking for
 * a scan could not be booked at all.
 *
 * The patient must already exist. Radiology does not register patients: a
 * duplicate record created at a scanner splits that person's history, and the
 * front desk owns registration precisely so that does not happen.
 */
const naira = (v: any) => `₦${Number(v ?? 0).toLocaleString()}`;

const URGENCIES = ["routine", "urgent", "stat"];

export function WalkInOrderDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [patientQuery, setPatientQuery] = useState("");
  const [patient, setPatient] = useState<any | null>(null);
  const [studyQuery, setStudyQuery] = useState("");
  const [study, setStudy] = useState<any | null>(null);
  const [urgency, setUrgency] = useState("routine");
  const [indication, setIndication] = useState("");

  const patients = useQuery({
    queryKey: ["radiology-walkin-patients", patientQuery],
    queryFn: () => api.hospital.patients.search(patientQuery),
    enabled: patientQuery.trim().length >= 2 && !patient,
  });

  const studies = useQuery({
    queryKey: ["radiology-catalog-search", studyQuery],
    queryFn: () => api.hospital.clinical.searchRadiologyCatalog(studyQuery || undefined),
    enabled: open,
  });

  const reset = () => {
    setPatientQuery(""); setPatient(null);
    setStudyQuery(""); setStudy(null);
    setUrgency("routine"); setIndication("");
  };

  const create = useMutation({
    mutationFn: () =>
      api.hospital.radiology.createOrder({
        patient_id: patient.id,
        // No encounter: this is the walk-in path. The backend records
        // "Walk-in (no referral)" rather than leaving the referrer blank.
        modality: study?.modality || "other",
        radiology_catalog_id: study?.id,
        test_name: study?.name,
        urgency,
        clinical_indication: indication.trim() || undefined,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["radiology-orders"] });
      toast({
        title: "Study booked",
        description: `${study?.name} for ${patient?.first_name ?? ""} ${patient?.last_name ?? ""}`.trim(),
      });
      reset();
      onOpenChange(false);
    },
    onError: (e: any) =>
      toast({ title: "Could not book it", description: e?.message, variant: "destructive" }),
  });

  const rows: any[] = patients.data?.patients ?? (Array.isArray(patients.data) ? patients.data : []);
  // The endpoint returns "tests". Reading studies/catalog meant the picker was
  // always empty, so no suggestions ever appeared.
  const catalogue: any[] = studies.data?.tests ?? [];

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) reset(); onOpenChange(o); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ScanLine className="h-4 w-4 text-primary" />
            Book a walk-in study
          </DialogTitle>
          <DialogDescription>
            For a client who came straight to radiology. No doctor's request is
            needed — the order is recorded as a walk-in.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {/* Patient */}
          <div className="space-y-1">
            <Label className="text-xs">Patient</Label>
            {patient ? (
              <div className="flex items-center gap-2 rounded-md border bg-muted/40 px-2.5 py-2">
                <UserCheck className="h-4 w-4 shrink-0 text-primary" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    {patient.first_name} {patient.last_name}
                  </p>
                  <p className="font-mono text-xs text-muted-foreground">{patient.mrn}</p>
                </div>
                <Button size="sm" variant="ghost" className="h-7 text-xs"
                  onClick={() => { setPatient(null); setPatientQuery(""); }}>
                  Change
                </Button>
              </div>
            ) : (
              <>
                <div className="relative">
                  <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={patientQuery}
                    onChange={(e) => setPatientQuery(e.target.value)}
                    placeholder="Search name, phone or MRN…"
                    className="h-8 pl-8 text-sm"
                  />
                </div>
                {patients.isFetching && (
                  <p className="text-xs text-muted-foreground">Searching…</p>
                )}
                {rows.length > 0 && (
                  <div className="max-h-32 overflow-y-auto rounded-md border">
                    {rows.slice(0, 8).map((p: any) => (
                      <button
                        key={p.id}
                        onClick={() => setPatient(p)}
                        className="flex w-full items-center justify-between gap-2 px-2 py-1.5 text-left text-xs hover:bg-muted/60"
                      >
                        <span className="min-w-0 truncate">{p.first_name} {p.last_name}</span>
                        <span className="shrink-0 font-mono text-muted-foreground">{p.mrn}</span>
                      </button>
                    ))}
                  </div>
                )}
                {patientQuery.trim().length >= 2 && !patients.isFetching && rows.length === 0 && (
                  <p className="text-xs text-amber-600">
                    No match. Radiology cannot register patients — send them to the
                    front desk first, so their history stays in one record.
                  </p>
                )}
              </>
            )}
          </div>

          {/* Study */}
          <div className="space-y-1">
            <Label className="text-xs">Study</Label>
            <div className="relative">
              <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={study ? study.name : studyQuery}
                onChange={(e) => { setStudy(null); setStudyQuery(e.target.value); }}
                placeholder="Search the catalogue…"
                className="h-8 pl-8 text-sm"
              />
            </div>
            {!study && catalogue.length > 0 && (
              <div className="max-h-36 overflow-y-auto rounded-md border">
                {catalogue.slice(0, 10).map((c: any) => (
                  <button
                    key={c.id}
                    onClick={() => { setStudy(c); setStudyQuery(""); }}
                    className="flex w-full items-center justify-between gap-2 px-2 py-1.5 text-left text-xs hover:bg-muted/60"
                  >
                    <span className="min-w-0 truncate">{c.name}</span>
                    <span className={cn("shrink-0 tabular-nums",
                      Number(c.base_price) ? "text-muted-foreground" : "text-amber-600")}>
                      {Number(c.base_price) ? naira(c.base_price) : "not priced"}
                    </span>
                  </button>
                ))}
              </div>
            )}
            {study && (
              <div className="flex items-center gap-2 pt-0.5">
                {study.modality && (
                  <Badge variant="outline" className="text-xs capitalize">{study.modality}</Badge>
                )}
                {Number(study.base_price) ? (
                  <span className="text-xs tabular-nums text-muted-foreground">
                    List price {naira(study.base_price)}
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-xs text-amber-600">
                    <AlertTriangle className="h-3 w-3" />
                    No price set — this would bill at ₦0
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Urgency</Label>
              <Select value={urgency} onValueChange={setUrgency}>
                <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {URGENCIES.map((u) => (
                    <SelectItem key={u} value={u} className="capitalize">{u}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Reason for the scan</Label>
            <Textarea
              rows={2} value={indication}
              onChange={(e) => setIndication(e.target.value)}
              placeholder="What the client is presenting with…"
              className="text-sm"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => { reset(); onOpenChange(false); }}>Cancel</Button>
          <Button
            disabled={create.isPending || !patient || !study}
            onClick={() => create.mutate()}
          >
            {create.isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
            Book study
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
