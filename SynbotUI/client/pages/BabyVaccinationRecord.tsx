import { useState, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BackButton } from "@/components/BackButton";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Syringe, Loader2, Plus, Trash2, ExternalLink, Baby as BabyIcon,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";

const SCHEDULE_STATUS_BADGE: Record<string, string> = {
  given:    "bg-green-100 text-green-700 border-green-300",
  overdue:  "bg-red-100 text-red-700 border-red-300",
  upcoming: "bg-orange-100 text-orange-700 border-orange-300",
};

const SCHEDULE_STATUS_LABEL: Record<string, string> = {
  given: "Given",
  overdue: "Overdue",
  upcoming: "Upcoming",
};

type DoseRow = {
  checked: boolean;
  vaccine_name: string;
  dose_number: string;
  date_given: string;
  batch_number: string;
  site: string;
  next_due_date: string;
  reaction: string;
  isOther?: boolean;
};

const emptyOtherRow: DoseRow = {
  checked: true, vaccine_name: "", dose_number: "", date_given: "",
  batch_number: "", site: "", next_due_date: "", reaction: "", isOther: true,
};

function ageFromDob(dob?: string): string {
  if (!dob) return "—";
  const d = new Date(dob);
  const days = Math.floor((Date.now() - d.getTime()) / (24 * 3600 * 1000));
  if (isNaN(days)) return "—";
  if (days < 60) return `${days} days`;
  if (days < 730) return `${Math.floor(days / 30)} months`;
  return `${Math.floor(days / 365.25)} years`;
}

const todayIso = () => new Date().toISOString().slice(0, 10);

export default function BabyVaccinationRecord() {
  const { patientId } = useParams<{ patientId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const qc = useQueryClient();

  const [doseOpen, setDoseOpen] = useState(false);
  const [doseRows, setDoseRows] = useState<DoseRow[]>([]);

  const { data: babyData, isLoading: babyLoading } = useQuery({
    queryKey: ["baby-detail", patientId],
    queryFn: () => api.hospital.mch.getBaby(patientId!),
    enabled: !!patientId,
  });
  const baby = babyData?.baby;

  const { data: scheduleData, isLoading: scheduleLoading } = useQuery({
    queryKey: ["baby-schedule", patientId],
    queryFn: () => api.hospital.mch.listVaccineSchedule({ patient_id: patientId! }),
    enabled: !!patientId,
  });
  const schedule: any[] = scheduleData?.schedule ?? [];

  const { data: historyData } = useQuery({
    queryKey: ["baby-immunisation-history", patientId],
    queryFn: () => api.hospital.mch.getImmunisationHistory(patientId!),
    enabled: !!patientId,
  });
  const history: any[] = historyData?.immunisations ?? [];
  const scheduleVaccineNames = useMemo(
    () => new Set(schedule.map(s => (s.vaccine_name || "").trim().toLowerCase())),
    [schedule],
  );

  const doseMut = useMutation({
    mutationFn: (rows: DoseRow[]) => api.hospital.mch.logImmunisation(
      patientId!,
      rows
        .filter(r => r.checked && r.vaccine_name.trim())
        .map(({ checked, isOther, ...rest }) => ({
          vaccine_name: rest.vaccine_name,
          date_given: rest.date_given || todayIso(),
          dose_number: rest.dose_number ? Number(rest.dose_number) : undefined,
          batch_number: rest.batch_number || undefined,
          site: rest.site || undefined,
          next_due_date: rest.next_due_date || undefined,
          reaction: rest.reaction || undefined,
        })),
    ),
    onSuccess: (res: any) => {
      toast({ title: `${res?.count ?? "Immunisation"} dose(s) recorded` });
      setDoseOpen(false);
      qc.invalidateQueries({ queryKey: ["baby-schedule", patientId] });
      qc.invalidateQueries({ queryKey: ["baby-immunisation-history", patientId] });
      qc.invalidateQueries({ queryKey: ["immunisation-babies"] });
    },
    onError: () => toast({ title: "Failed to log immunisation", variant: "destructive" }),
  });

  const openDoseDialog = () => {
    const due = schedule.filter(s => s.status === "overdue" || s.status === "upcoming");
    setDoseRows(due.map(s => ({
      checked: true,
      vaccine_name: s.vaccine_name,
      dose_number: "",
      date_given: todayIso(),
      batch_number: "",
      site: "",
      next_due_date: "",
      reaction: "",
    })));
    setDoseOpen(true);
  };

  if (babyLoading) {
    return (
      <div className="p-6 flex items-center justify-center text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading vaccination record…
      </div>
    );
  }

  if (!baby) {
    return (
      <div className="p-6 text-center text-muted-foreground">
        Patient not found.
        <div className="mt-3">
          <BackButton fallback="/hospital/immunisation" variant="outline">Back to Immunisation</BackButton>
        </div>
      </div>
    );
  }

  const na = baby.newborn_assessment;

  return (
    <motion.div className="p-6 space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BackButton fallback="/hospital/immunisation" iconOnly />
          <div className="p-2 bg-sky-500/20 rounded-lg">
            <Syringe className="w-6 h-6 text-sky-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Vaccination Record</h1>
            <p className="text-sm text-muted-foreground">{baby.first_name} {baby.last_name} · MRN {baby.mrn}</p>
          </div>
        </div>
        <Button size="sm" className="bg-blue-700 hover:bg-blue-800" onClick={openDoseDialog} disabled={scheduleLoading}>
          <Syringe className="w-4 h-4 mr-1" /> Record Dose(s)
        </Button>
      </div>

      {/* Bio header */}
      <Card className="border-border">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <BabyIcon className="w-4 h-4 text-sky-400" /> Child Information
            <Button variant="link" size="sm" className="h-auto p-0 ml-auto text-xs"
              onClick={() => navigate(`/hospital/patients/${baby.mrn}`)}>
              Edit demographic info <ExternalLink className="w-3 h-3 ml-1" />
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            {[
              { label: "Date of Birth", value: baby.date_of_birth },
              { label: "Age", value: ageFromDob(baby.date_of_birth) },
              { label: "Gender", value: baby.gender },
              { label: "Place of Birth", value: baby.place_of_birth },
              { label: "Birth Weight", value: na?.birth_weight_kg ? `${na.birth_weight_kg} kg` : null },
              { label: "Birth Length", value: na?.length_cm ? `${na.length_cm} cm` : null },
              { label: "Head Circumference", value: na?.head_circumference_cm ? `${na.head_circumference_cm} cm` : null },
              { label: "Father's Name", value: baby.father_name },
              { label: "Address", value: baby.address },
              { label: "Phone", value: baby.phone },
            ].map(f => (
              <div key={f.label}>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">{f.label}</p>
                <p className="text-foreground">{f.value || "—"}</p>
              </div>
            ))}
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide">Mother</p>
              {baby.mother ? (
                <button className="text-blue-600 hover:underline"
                  onClick={() => navigate(`/hospital/patients/${baby.mother.mrn}`)}>
                  {baby.mother.first_name} {baby.mother.last_name}
                </button>
              ) : <p className="text-foreground">—</p>}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Vaccination Schedule */}
      <Card className="border-border">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Vaccination Schedule</CardTitle>
        </CardHeader>
        <CardContent>
          {scheduleLoading ? (
            <div className="flex items-center justify-center py-6 text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading schedule…
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Age</TableHead>
                  <TableHead>Vaccine</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {schedule.map((s, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-sm">{s.age_milestone}</TableCell>
                    <TableCell className="text-sm">{s.vaccine_name}{s.notes ? <span className="text-xs text-muted-foreground"> — {s.notes}</span> : null}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className={SCHEDULE_STATUS_BADGE[s.status] || ""}>
                        {SCHEDULE_STATUS_LABEL[s.status] || s.status}
                        {s.status === "given" && s.date_given ? ` (${s.date_given})` : ""}
                        {s.status !== "given" && s.due_date ? ` (${s.due_date})` : ""}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Dose Log */}
      <Card className="border-border">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Dose Log</CardTitle>
        </CardHeader>
        <CardContent>
          {history.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">No doses recorded yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date Given</TableHead>
                  <TableHead>Vaccine</TableHead>
                  <TableHead>Dose</TableHead>
                  <TableHead>Batch No.</TableHead>
                  <TableHead>Administered By</TableHead>
                  <TableHead>Next Visit</TableHead>
                  <TableHead>Notes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.map((h: any) => {
                  const isOther = !scheduleVaccineNames.has((h.vaccine_name || "").trim().toLowerCase());
                  return (
                    <TableRow key={h.id}>
                      <TableCell className="text-sm">{h.date_given || "—"}</TableCell>
                      <TableCell className="text-sm">
                        {h.vaccine_name}
                        {isOther && <Badge variant="outline" className="ml-2 text-[12px]">Other</Badge>}
                      </TableCell>
                      <TableCell className="text-sm">{h.dose_number || "—"}</TableCell>
                      <TableCell className="text-sm">{h.batch_number || "—"}</TableCell>
                      <TableCell className="text-sm">{h.administered_by || "—"}</TableCell>
                      <TableCell className="text-sm">{h.next_due_date || "—"}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{h.reaction || h.notes || "—"}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Record Dose(s) Dialog */}
      <Dialog open={doseOpen} onOpenChange={setDoseOpen}>
        <DialogContent className="bg-card border-border text-foreground max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Syringe className="w-5 h-5 text-blue-400" />
              Record Dose(s) — {baby.first_name} {baby.last_name}
            </DialogTitle>
            <DialogDescription className="text-muted-foreground text-xs">
              Vaccines currently due or overdue are pre-checked — uncheck anything not actually given today, or add another vaccine below.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-2">
            {doseRows.length === 0 && (
              <p className="text-sm text-muted-foreground">Nothing currently due — use "Add Other Vaccine" for a booster, travel, or catch-up dose.</p>
            )}
            {doseRows.map((row, i) => (
              <div key={i} className={cn("rounded border p-3 space-y-2 relative", row.checked ? "border-border" : "border-border/50 opacity-60")}>
                <Button size="icon" variant="ghost" className="absolute top-1 right-1 h-6 w-6"
                  onClick={() => setDoseRows(rows => rows.filter((_, j) => j !== i))}>
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
                <div className="flex items-start gap-3">
                  <Checkbox checked={row.checked} className="mt-2"
                    onCheckedChange={v => setDoseRows(rows => rows.map((r, j) => j === i ? { ...r, checked: Boolean(v) } : r))} />
                  <div className="grid grid-cols-2 gap-3 flex-1">
                    <div className="col-span-2 space-y-1">
                      <Label className="text-xs text-muted-foreground">Vaccine Name *</Label>
                      <Input value={row.vaccine_name} disabled={!row.isOther}
                        onChange={e => setDoseRows(rows => rows.map((r, j) => j === i ? { ...r, vaccine_name: e.target.value } : r))}
                        className="bg-background border-border text-foreground text-sm h-8" />
                    </div>
                    {[
                      { key: "dose_number",   label: "Dose No.",     type: "number" },
                      { key: "date_given",    label: "Date Given",   type: "date" },
                      { key: "batch_number",  label: "Batch No." },
                      { key: "site",          label: "Site (LTA/RTA/oral)" },
                      { key: "next_due_date", label: "Next Visit",   type: "date" },
                      { key: "reaction",      label: "Reaction" },
                    ].map(f => (
                      <div key={f.key} className="space-y-1">
                        <Label className="text-xs text-muted-foreground">{f.label}</Label>
                        <Input type={f.type || "text"} value={(row as any)[f.key] || ""}
                          onChange={e => setDoseRows(rows => rows.map((r, j) => j === i ? { ...r, [f.key]: e.target.value } : r))}
                          className="bg-background border-border text-foreground text-sm h-8" />
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))}
            <Button size="sm" variant="outline" className="border-border gap-1"
              onClick={() => setDoseRows(rows => [...rows, { ...emptyOtherRow, date_given: todayIso() }])}>
              <Plus className="w-3.5 h-3.5" /> Add Other Vaccine
            </Button>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" className="border-border" onClick={() => setDoseOpen(false)}>Cancel</Button>
            <Button className="bg-blue-700 hover:bg-blue-800"
              disabled={doseMut.isPending || !doseRows.some(r => r.checked && r.vaccine_name.trim())}
              onClick={() => doseMut.mutate(doseRows)}>
              {doseMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Save {doseRows.filter(r => r.checked && r.vaccine_name.trim()).length || ""} Dose(s)
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
