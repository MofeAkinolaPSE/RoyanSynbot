import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
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
  Heart, Loader2, Plus, Baby, ClipboardList, ActivitySquare,
  Syringe, ChevronRight, AlertTriangle, Ban,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { PANEL_WIDTH } from "@/components/shared/panel-shared";
import {
  ANCStatusBadge, BoolCheck, DetailRow, SectionLabel,
  emptyVisit, emptyDelivery, emptyNewborn, stripEmptyStrings,
} from "@/components/mch/mch-shared";

interface ANCWorkspacePanelProps {
  anc: {
    id: number | string;
    patient_id: number;
    patient_name?: string;
    mrn?: string;
    status?: string;
    gravida?: number;
    para?: number;
    edd?: string;
    gestational_age_weeks?: number;
    blood_group?: string;
    rhesus?: string;
    hiv_status?: string;
    hbsag?: string;
    syphilis?: string;
    malaria_prophylaxis?: boolean;
    tetanus_toxoid?: boolean;
    iron_folic_acid?: boolean;
    risk_factors?: string;
    referred_from?: string;
    notes?: string;
  } & Record<string, any>;
  onClose: () => void;
}

export function ANCWorkspacePanel({ anc: initialAnc, onClose }: ANCWorkspacePanelProps) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const qc = useQueryClient();

  const ancId = initialAnc.id;

  const [visitOpen, setVisitOpen] = useState(false);
  const [visitForm, setVisitForm] = useState({ ...emptyVisit });
  const [deliveryOpen, setDeliveryOpen] = useState(false);
  const [deliveryForm, setDeliveryForm] = useState({ ...emptyDelivery });
  const [newbornOpen, setNewbornOpen] = useState(false);
  const [newbornForm, setNewbornForm] = useState({ ...emptyNewborn });

  const { data: ancData } = useQuery({
    queryKey: ["anc-detail", ancId],
    queryFn: () => api.hospital.mch.getAnc(ancId),
  });
  const anc = { ...initialAnc, ...(ancData?.record ?? {}) };

  const { data: visitsData, isLoading: visitsLoading } = useQuery({
    queryKey: ["anc-visits", ancId],
    queryFn: () => api.hospital.mch.listVisits(ancId),
  });
  const visits: any[] = visitsData?.visits ?? [];

  const { data: deliveryData } = useQuery({
    queryKey: ["anc-delivery", ancId],
    queryFn: () => api.hospital.mch.getDelivery(ancId),
    enabled: anc.status === "delivered",
    retry: false,
  });
  const delivery: any | null = deliveryData?.record ?? null;

  const { data: newbornData } = useQuery({
    queryKey: ["anc-newborn", delivery?.id],
    queryFn: () => api.hospital.mch.getNewbornAssessments(delivery!.id),
    enabled: !!delivery?.id,
  });
  const newbornAssessment: any | null = (newbornData?.assessments ?? [])[0] ?? null;

  const { data: babiesData } = useQuery({
    queryKey: ["mch-babies", anc.patient_id],
    queryFn: () => api.hospital.mch.listBabies(anc.patient_id),
  });
  const babies: any[] = babiesData?.babies ?? [];

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ["anc-detail", ancId] });
    void qc.invalidateQueries({ queryKey: ["anc-list"] });
    void qc.invalidateQueries({ queryKey: ["mch-stats"] });
  };

  const statusMut = useMutation({
    mutationFn: (status: string) => api.hospital.mch.updateAnc(ancId, { status }),
    onSuccess: (_res, status) => { toast({ title: `Marked ${status}` }); invalidateAll(); },
    onError: () => toast({ title: "Failed to update status", variant: "destructive" }),
  });

  const visitMut = useMutation({
    mutationFn: (d: typeof visitForm) => api.hospital.mch.logVisit(ancId, {
      ...stripEmptyStrings(d),
      gestational_age_weeks: d.gestational_age_weeks ? Number(d.gestational_age_weeks) : undefined,
      weight_kg: d.weight_kg ? Number(d.weight_kg) : undefined,
      bp_systolic: d.bp_systolic ? Number(d.bp_systolic) : undefined,
      bp_diastolic: d.bp_diastolic ? Number(d.bp_diastolic) : undefined,
      fundal_height_cm: d.fundal_height_cm ? Number(d.fundal_height_cm) : undefined,
      fetal_heart_rate: d.fetal_heart_rate ? Number(d.fetal_heart_rate) : undefined,
      haemoglobin: d.haemoglobin ? Number(d.haemoglobin) : undefined,
    }),
    onSuccess: () => {
      toast({ title: "ANC visit recorded" });
      setVisitOpen(false);
      setVisitForm({ ...emptyVisit });
      void qc.invalidateQueries({ queryKey: ["anc-visits", ancId] });
    },
    onError: () => toast({ title: "Failed to record visit", variant: "destructive" }),
  });

  const deliveryMut = useMutation({
    mutationFn: (d: typeof deliveryForm) => api.hospital.mch.recordDelivery(ancId, {
      ...stripEmptyStrings(d),
      duration_of_labour_hours: d.duration_of_labour_hours ? Number(d.duration_of_labour_hours) : undefined,
      blood_loss_ml: d.blood_loss_ml ? Number(d.blood_loss_ml) : undefined,
    }),
    onSuccess: () => {
      toast({ title: "Delivery recorded" });
      setDeliveryOpen(false);
      setDeliveryForm({ ...emptyDelivery });
      invalidateAll();
      void qc.invalidateQueries({ queryKey: ["anc-delivery", ancId] });
    },
    onError: (e: any) => toast({ title: e?.message || "Failed to record delivery", variant: "destructive" }),
  });

  const newbornMut = useMutation({
    mutationFn: (d: typeof newbornForm) => api.hospital.mch.addNewbornAssessment(delivery!.id, {
      ...stripEmptyStrings(d),
      birth_weight_kg: d.birth_weight_kg ? Number(d.birth_weight_kg) : undefined,
      length_cm: d.length_cm ? Number(d.length_cm) : undefined,
      head_circumference_cm: d.head_circumference_cm ? Number(d.head_circumference_cm) : undefined,
      apgar_1min: d.apgar_1min !== "" ? Number(d.apgar_1min) : undefined,
      apgar_5min: d.apgar_5min !== "" ? Number(d.apgar_5min) : undefined,
      apgar_10min: d.apgar_10min !== "" ? Number(d.apgar_10min) : undefined,
      gestational_age_at_birth: d.gestational_age_at_birth ? Number(d.gestational_age_at_birth) : undefined,
      father_name: d.father_name || undefined,
      place_of_birth: d.place_of_birth || undefined,
    }),
    onSuccess: (res: any) => {
      toast({ title: "Newborn assessment saved", description: res?.baby_patient?.mrn ? `Baby MRN ${res.baby_patient.mrn} created` : undefined });
      setNewbornOpen(false);
      setNewbornForm({ ...emptyNewborn });
      void qc.invalidateQueries({ queryKey: ["anc-newborn", delivery?.id] });
      // The assessment creates the baby's own patient record (mother_patient_id
      // -> anc.patient_id) as a side effect, so every babies-roster view needs
      // invalidating too -- previously only the assessment query itself was
      // invalidated, so a freshly-created baby didn't appear anywhere (this
      // panel's own list, the mother's chart, or the hospital-wide roster)
      // until something unrelated happened to refetch it.
      void qc.invalidateQueries({ queryKey: ["mch-babies", anc.patient_id] });
      void qc.invalidateQueries({ queryKey: ["patient-babies", anc.patient_id] });
      void qc.invalidateQueries({ queryKey: ["immunisation-babies"] });
      void qc.invalidateQueries({ queryKey: ["mch-babies", anc.patient_id] });
      invalidateAll();
    },
    onError: () => toast({ title: "Failed to save newborn assessment", variant: "destructive" }),
  });

  const canTransition = anc.status === "active";

  return (
    <Sheet open onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className={cn(PANEL_WIDTH.default, "overflow-y-auto p-0 flex flex-col")} side="right">
        <SheetHeader className="px-5 pt-5 pb-4 border-b shrink-0">
          <div className="flex items-start gap-3">
            <div className="h-10 w-10 rounded-full bg-blue-500/10 flex items-center justify-center shrink-0">
              <Heart className="h-5 w-5 text-blue-500" />
            </div>
            <div className="flex-1 min-w-0">
              <SheetTitle className="text-base leading-tight">{anc.patient_name ?? `ANC #${ancId}`}</SheetTitle>
              <div className="flex flex-wrap items-center gap-2 mt-1">
                {anc.mrn && <span className="text-xs text-muted-foreground font-mono">{anc.mrn}</span>}
                <ANCStatusBadge status={anc.status} />
                <span className="text-xs text-muted-foreground">G{anc.gravida ?? "?"}/P{anc.para ?? "?"}</span>
              </div>
            </div>
          </div>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          <section>
            <SectionLabel icon={<ClipboardList className="h-3.5 w-3.5" />} label="ANC Info" />
            <DetailRow label="EDD" value={anc.edd} />
            <DetailRow label="GA (weeks)" value={anc.gestational_age_weeks} />
            <DetailRow label="Blood Group" value={anc.blood_group} />
            <DetailRow label="Rhesus" value={anc.rhesus} />
            <DetailRow label="HIV" value={anc.hiv_status} />
            <DetailRow label="HBsAg" value={anc.hbsag} />
            <DetailRow label="Syphilis" value={anc.syphilis} />
            <DetailRow label="Risk Factors" value={anc.risk_factors} />
            <DetailRow label="Referred From" value={anc.referred_from} />
            <DetailRow label="Notes" value={anc.notes} />
            <div className="flex flex-wrap gap-3 mt-2">
              {anc.malaria_prophylaxis && <Badge variant="outline" className="text-xs">Malaria prophylaxis</Badge>}
              {anc.tetanus_toxoid && <Badge variant="outline" className="text-xs">Tetanus toxoid</Badge>}
              {anc.iron_folic_acid && <Badge variant="outline" className="text-xs">Iron/Folic acid</Badge>}
            </div>
            {canTransition && (
              <div className="flex gap-2 mt-3">
                <Button size="sm" variant="outline" className="text-orange-600 border-orange-300 hover:bg-orange-50"
                  disabled={statusMut.isPending} onClick={() => statusMut.mutate("referred")}>
                  <AlertTriangle className="h-3.5 w-3.5 mr-1.5" /> Mark Referred
                </Button>
                <Button size="sm" variant="outline" className="text-red-600 border-red-300 hover:bg-red-50"
                  disabled={statusMut.isPending} onClick={() => statusMut.mutate("miscarriage")}>
                  <Ban className="h-3.5 w-3.5 mr-1.5" /> Mark Miscarriage
                </Button>
              </div>
            )}
          </section>

          <Separator />

          <section>
            <div className="flex items-center justify-between mb-2">
              <SectionLabel icon={<ActivitySquare className="h-3.5 w-3.5" />} label="Visits" />
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setVisitOpen(true)}>
                <Plus className="h-3 w-3 mr-1" /> Log Visit
              </Button>
            </div>
            {visitsLoading ? (
              <div className="flex justify-center py-4"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>
            ) : visits.length === 0 ? (
              <p className="text-xs text-muted-foreground py-2">No visits recorded yet</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    {["Date", "GA", "BP", "FHR", "Weight", "Oedema"].map(h => (
                      <TableHead key={h} className="text-xs">{h}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visits.map((v: any) => (
                    <TableRow key={v.id}>
                      <TableCell className="text-xs">{v.visit_date}</TableCell>
                      <TableCell className="text-xs">{v.gestational_age_weeks ?? "—"}</TableCell>
                      <TableCell className="text-xs">{v.bp_systolic && v.bp_diastolic ? `${v.bp_systolic}/${v.bp_diastolic}` : "—"}</TableCell>
                      <TableCell className="text-xs">{v.fetal_heart_rate ?? "—"}</TableCell>
                      <TableCell className="text-xs">{v.weight_kg ? `${v.weight_kg}kg` : "—"}</TableCell>
                      <TableCell className="text-xs">{v.oedema ? <span className="text-yellow-600">Yes</span> : "No"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </section>

          <Separator />

          <section>
            <SectionLabel icon={<Baby className="h-3.5 w-3.5" />} label="Delivery" />
            {!delivery ? (
              canTransition ? (
                <Button size="sm" className="bg-blue-600 hover:bg-blue-700" onClick={() => setDeliveryOpen(true)}>
                  <Baby className="h-3.5 w-3.5 mr-1.5" /> Record Delivery
                </Button>
              ) : (
                <p className="text-xs text-muted-foreground">No delivery record for this case.</p>
              )
            ) : (
              <>
                <DetailRow label="Date" value={delivery.delivery_date} />
                <DetailRow label="Mode" value={delivery.mode_of_delivery?.toUpperCase()} />
                <DetailRow label="Labour Duration" value={delivery.duration_of_labour_hours ? `${delivery.duration_of_labour_hours}h` : undefined} />
                <DetailRow label="Blood Loss" value={delivery.blood_loss_ml ? `${delivery.blood_loss_ml}mL` : undefined} />
                <DetailRow label="Complications" value={delivery.maternal_complications} />

                <div className="mt-3">
                  <SectionLabel icon={<Baby className="h-3.5 w-3.5" />} label="Newborn Assessment" />
                  {!newbornAssessment ? (
                    <Button size="sm" variant="outline" className="border-sky-400 text-sky-600 hover:bg-sky-50"
                      onClick={() => setNewbornOpen(true)}>
                      <Baby className="h-3.5 w-3.5 mr-1.5" /> + Newborn Assessment
                    </Button>
                  ) : (
                    <>
                      <DetailRow label="Sex" value={newbornAssessment.sex} />
                      <DetailRow label="Birth Weight" value={newbornAssessment.birth_weight_kg ? `${newbornAssessment.birth_weight_kg}kg` : undefined} />
                      <DetailRow label="Apgar 1/5/10" value={`${newbornAssessment.apgar_1min ?? "—"} / ${newbornAssessment.apgar_5min ?? "—"} / ${newbornAssessment.apgar_10min ?? "—"}`} />
                    </>
                  )}
                </div>
              </>
            )}
          </section>

          {babies.length > 0 && (
            <>
              <Separator />
              <section>
                <SectionLabel icon={<Baby className="h-3.5 w-3.5" />} label="Babies" />
                <div className="space-y-2">
                  {babies.map((b: any) => (
                    <div key={b.id} className="flex items-center justify-between text-sm border-b border-border/50 pb-1.5 last:border-0">
                      <span>{b.first_name} {b.last_name} · {b.gender ?? "—"} · MRN {b.mrn}</span>
                      <div className="flex gap-1">
                        <Button size="sm" variant="ghost" className="h-6 text-xs px-2"
                          onClick={() => navigate(`/hospital/immunisation/${b.id}`)}>
                          <Syringe className="h-3 w-3 mr-1" /> Immun.
                        </Button>
                        <Button size="sm" variant="ghost" className="h-6 text-xs px-2"
                          onClick={() => { onClose(); navigate(`/hospital/patients/${b.mrn}`); }}>
                          Chart <ChevronRight className="h-3 w-3 ml-0.5" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </>
          )}
        </div>
      </SheetContent>

      {/* ── Log ANC Visit Dialog ──────────────────────────────────────────── */}
      <Dialog open={visitOpen} onOpenChange={setVisitOpen}>
        <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ActivitySquare className="w-5 h-5 text-blue-500" /> Log ANC Visit
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            {[
              { key: "visit_date", label: "Visit Date", type: "date" },
              { key: "gestational_age_weeks", label: "GA (weeks)", type: "number" },
              { key: "weight_kg", label: "Weight (kg)", type: "number" },
              { key: "bp_systolic", label: "BP Systolic", type: "number" },
              { key: "bp_diastolic", label: "BP Diastolic", type: "number" },
              { key: "fundal_height_cm", label: "Fundal Height (cm)", type: "number" },
              { key: "fetal_heart_rate", label: "FHR (bpm)", type: "number" },
              { key: "haemoglobin", label: "Haemoglobin (g/dL)", type: "number" },
            ].map(f => (
              <div key={f.key} className="space-y-1">
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                <Input type={f.type} value={(visitForm as any)[f.key] || ""}
                  onChange={e => setVisitForm(p => ({ ...p, [f.key]: e.target.value }))} className="h-8 text-sm" />
              </div>
            ))}
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Presentation</Label>
              <Select value={visitForm.presentation || ""} onValueChange={v => setVisitForm(p => ({ ...p, presentation: v }))}>
                <SelectTrigger className="h-8 text-sm"><SelectValue placeholder="Select…" /></SelectTrigger>
                <SelectContent>{["cephalic", "breech", "transverse"].map(o => <SelectItem key={o} value={o} className="capitalize">{o}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Malaria RDT</Label>
              <Select value={visitForm.malaria_rapid_test || ""} onValueChange={v => setVisitForm(p => ({ ...p, malaria_rapid_test: v }))}>
                <SelectTrigger className="h-8 text-sm"><SelectValue placeholder="Select…" /></SelectTrigger>
                <SelectContent>{["negative", "positive"].map(o => <SelectItem key={o} value={o} className="capitalize">{o}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="col-span-2 flex gap-4">
              <BoolCheck label="Oedema" checked={visitForm.oedema} onChange={v => setVisitForm(p => ({ ...p, oedema: v }))} />
              <BoolCheck label="Proteinuria" checked={visitForm.proteinuria} onChange={v => setVisitForm(p => ({ ...p, proteinuria: v }))} />
            </div>
            {[
              { key: "drugs_given", label: "Drugs Given", colSpan: 2 },
              { key: "counselling_given", label: "Counselling Given", colSpan: 2 },
              { key: "next_visit_date", label: "Next Visit Date", type: "date" },
              { key: "clinician_id", label: "Clinician ID" },
              { key: "notes", label: "Notes", colSpan: 2 },
            ].map(f => (
              <div key={f.key} className={cn("space-y-1", (f as any).colSpan === 2 ? "col-span-2" : "")}>
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                {(f as any).colSpan === 2 && !f.type
                  ? <Textarea value={(visitForm as any)[f.key] || ""} onChange={e => setVisitForm(p => ({ ...p, [f.key]: e.target.value }))} className="h-12 text-sm resize-none" />
                  : <Input type={f.type || "text"} value={(visitForm as any)[f.key] || ""} onChange={e => setVisitForm(p => ({ ...p, [f.key]: e.target.value }))} className="h-8 text-sm" />
                }
              </div>
            ))}
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" onClick={() => setVisitOpen(false)}>Cancel</Button>
            <Button className="bg-blue-600 hover:bg-blue-700" disabled={visitMut.isPending} onClick={() => visitMut.mutate(visitForm)}>
              {visitMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null} Save Visit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Record Delivery Dialog ──────────────────────────────────────────── */}
      <Dialog open={deliveryOpen} onOpenChange={setDeliveryOpen}>
        <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Baby className="w-5 h-5 text-blue-500" /> Record Delivery</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Delivery Date</Label>
              <Input type="date" value={deliveryForm.delivery_date} onChange={e => setDeliveryForm(p => ({ ...p, delivery_date: e.target.value }))} className="h-8 text-sm" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Delivery Time</Label>
              <Input type="time" value={deliveryForm.delivery_time} onChange={e => setDeliveryForm(p => ({ ...p, delivery_time: e.target.value }))} className="h-8 text-sm" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Mode of Delivery</Label>
              <Select value={deliveryForm.mode_of_delivery} onValueChange={v => setDeliveryForm(p => ({ ...p, mode_of_delivery: v }))}>
                <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>{["svd", "assisted", "cs", "breech"].map(o => <SelectItem key={o} value={o} className="uppercase">{o.toUpperCase()}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Anaesthesia</Label>
              <Input value={deliveryForm.anaesthesia_type} onChange={e => setDeliveryForm(p => ({ ...p, anaesthesia_type: e.target.value }))} className="h-8 text-sm" />
            </div>
            {[
              { key: "duration_of_labour_hours", label: "Labour Duration (hrs)", type: "number" },
              { key: "blood_loss_ml", label: "Blood Loss (mL)", type: "number" },
              { key: "perineal_tear", label: "Perineal Tear Grade" },
              { key: "attending_clinician", label: "Attending Clinician" },
              { key: "indication", label: "Indication (if CS/assisted)", colSpan: 2 },
              { key: "maternal_complications", label: "Maternal Complications", colSpan: 2 },
              { key: "notes", label: "Notes", colSpan: 2 },
            ].map(f => (
              <div key={f.key} className={cn("space-y-1", (f as any).colSpan === 2 ? "col-span-2" : "")}>
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                {(f as any).colSpan === 2
                  ? <Textarea value={(deliveryForm as any)[f.key] || ""} onChange={e => setDeliveryForm(p => ({ ...p, [f.key]: e.target.value }))} className="h-14 text-sm resize-none" />
                  : <Input type={f.type || "text"} value={(deliveryForm as any)[f.key] || ""} onChange={e => setDeliveryForm(p => ({ ...p, [f.key]: e.target.value }))} className="h-8 text-sm" />
                }
              </div>
            ))}
            <div className="col-span-2 flex gap-4">
              <BoolCheck label="Placenta complete" checked={deliveryForm.placenta_complete} onChange={v => setDeliveryForm(p => ({ ...p, placenta_complete: v }))} />
              <BoolCheck label="Episiotomy performed" checked={deliveryForm.episiotomy} onChange={v => setDeliveryForm(p => ({ ...p, episiotomy: v }))} />
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" onClick={() => setDeliveryOpen(false)}>Cancel</Button>
            <Button className="bg-blue-600 hover:bg-blue-700" disabled={deliveryMut.isPending} onClick={() => deliveryMut.mutate(deliveryForm)}>
              {deliveryMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null} Record Delivery
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Newborn Assessment Dialog ──────────────────────────────────────── */}
      <Dialog open={newbornOpen} onOpenChange={setNewbornOpen}>
        <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Baby className="w-5 h-5 text-sky-500" /> Newborn Assessment</DialogTitle>
            <DialogDescription>Delivery recorded {delivery?.delivery_date}</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 mt-2">
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Sex</Label>
              <Select value={newbornForm.sex} onValueChange={v => setNewbornForm(p => ({ ...p, sex: v }))}>
                <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>{["male", "female", "indeterminate"].map(o => <SelectItem key={o} value={o} className="capitalize">{o}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            {[
              { key: "birth_weight_kg", label: "Birth Weight (kg)", type: "number" },
              { key: "length_cm", label: "Length (cm)", type: "number" },
              { key: "head_circumference_cm", label: "Head Circ. (cm)", type: "number" },
              { key: "apgar_1min", label: "Apgar 1min (0-10)", type: "number" },
              { key: "apgar_5min", label: "Apgar 5min (0-10)", type: "number" },
              { key: "apgar_10min", label: "Apgar 10min (0-10)", type: "number" },
              { key: "gestational_age_at_birth", label: "GA at Birth (wks)", type: "number" },
              { key: "resuscitation_type", label: "Resuscitation Type" },
              { key: "place_of_birth", label: "Place of Birth" },
              { key: "father_name", label: "Father's / Guardian's Name" },
              { key: "congenital_anomalies", label: "Congenital Anomalies", colSpan: 2 },
              { key: "notes", label: "Notes", colSpan: 2 },
            ].map(f => (
              <div key={f.key} className={cn("space-y-1", (f as any).colSpan === 2 ? "col-span-2" : "")}>
                <Label className="text-xs text-muted-foreground">{f.label}</Label>
                {(f as any).colSpan === 2
                  ? <Textarea value={(newbornForm as any)[f.key] || ""} onChange={e => setNewbornForm(p => ({ ...p, [f.key]: e.target.value }))} className="h-14 text-sm resize-none" />
                  : <Input type={f.type || "text"} value={(newbornForm as any)[f.key] || ""} onChange={e => setNewbornForm(p => ({ ...p, [f.key]: e.target.value }))} className="h-8 text-sm" />
                }
              </div>
            ))}
            <div className="col-span-2 grid grid-cols-2 gap-2">
              {[
                ["cry_at_birth", "Cry at birth"],
                ["resuscitation_needed", "Resuscitation needed"],
                ["eye_prophylaxis", "Eye prophylaxis given"],
                ["vitamin_k_given", "Vitamin K given"],
                ["bcg_given", "BCG given"],
                ["opv0_given", "OPV 0 given"],
                ["hbv_given", "HBV birth dose given"],
                ["breast_feeding_initiated", "Breastfeeding initiated"],
              ].map(([k, l]) => (
                <BoolCheck key={k} label={l} checked={!!(newbornForm as any)[k]} onChange={v => setNewbornForm(p => ({ ...p, [k]: v }))} />
              ))}
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" onClick={() => setNewbornOpen(false)}>Cancel</Button>
            <Button className="bg-blue-600 hover:bg-blue-700" disabled={newbornMut.isPending} onClick={() => newbornMut.mutate(newbornForm)}>
              {newbornMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null} Save Assessment
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Sheet>
  );
}
