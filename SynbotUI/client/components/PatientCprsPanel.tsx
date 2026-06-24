import { useQuery } from "@tanstack/react-query";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  User, Shield, Activity, FlaskConical, Pill, ExternalLink, Plus,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";

interface PatientCprsPanelProps {
  patientMrn: string;
  encounterId?: number;
  onClose: () => void;
}

const STATUS_COLORS: Record<string, string> = {
  patient_registered: "bg-slate-100 text-slate-700",
  triaged:            "bg-yellow-100 text-yellow-700",
  nurse_assessment:   "bg-teal-100 text-teal-700",
  called:             "bg-blue-100 text-blue-700",
  consulting:         "bg-indigo-100 text-indigo-700",
  lab_ordered:        "bg-purple-100 text-purple-700",
  pharmacy_dispensing:"bg-orange-100 text-orange-700",
  billing_pending:    "bg-pink-100 text-pink-700",
  discharged:         "bg-green-100 text-green-700",
};

function ageFromDob(dob?: string): string {
  if (!dob) return "—";
  const d = new Date(dob);
  const age = Math.floor((Date.now() - d.getTime()) / (365.25 * 24 * 3600 * 1000));
  return isNaN(age) ? "—" : `${age}y`;
}

function formatDate(iso?: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-NG", { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

export function PatientCprsPanel({ patientMrn, encounterId, onClose }: PatientCprsPanelProps) {
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["cprs-panel", patientMrn],
    queryFn: () => api.hospital.patients.profile(patientMrn),
    enabled: !!patientMrn,
    staleTime: 60_000,
  });

  const patient       = data?.patient ?? data;
  const insurance     = data?.insurance ?? data?.hmo;
  const activeEncounter = data?.active_encounter;
  const labOrders     = (data?.lab_orders ?? []).slice(0, 3);
  const prescriptions = (data?.prescriptions ?? data?.medications ?? []).slice(0, 3);

  return (
    <Sheet open onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className="w-[420px] sm:w-[460px] overflow-y-auto p-0" side="right">
        {isLoading ? (
          <LoadingSkeleton />
        ) : !patient ? (
          <div className="flex items-center justify-center h-40 text-sm text-muted-foreground">
            Patient not found.
          </div>
        ) : (
          <>
            {/* Header */}
            <SheetHeader className="px-5 pt-5 pb-4 border-b">
              <div className="flex items-start gap-3">
                <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                  <User className="h-5 w-5 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <SheetTitle className="text-base leading-tight">
                    {patient.first_name} {patient.last_name}
                  </SheetTitle>
                  <div className="flex flex-wrap items-center gap-2 mt-1">
                    <Badge variant="outline" className="text-xs font-mono">{patient.mrn}</Badge>
                    <span className="text-xs text-muted-foreground">
                      {ageFromDob(patient.date_of_birth)} · {patient.gender ?? "—"}
                    </span>
                    {patient.blood_group && (
                      <Badge className="text-xs bg-red-100 text-red-700 hover:bg-red-100">
                        {patient.blood_group}
                      </Badge>
                    )}
                  </div>
                  {patient.phone && (
                    <p className="text-xs text-muted-foreground mt-1">{patient.phone}</p>
                  )}
                  {patient.allergies && (
                    <p className="text-xs text-destructive mt-1">
                      ⚠ Allergies: {patient.allergies}
                    </p>
                  )}
                </div>
              </div>
            </SheetHeader>

            <div className="divide-y divide-border">
              {/* Insurance / HMO */}
              {insurance && (
                <section className="px-5 py-3">
                  <div className="flex items-center gap-2 mb-2">
                    <Shield className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      Insurance
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium">
                      {insurance.hmo_provider ?? insurance.provider ?? insurance.insurer_name ?? "—"}
                    </span>
                    <Badge
                      className={cn(
                        "text-xs",
                        insurance.status === "active"
                          ? "bg-green-100 text-green-700 hover:bg-green-100"
                          : "bg-slate-100 text-slate-600 hover:bg-slate-100"
                      )}
                    >
                      {insurance.status ?? "—"}
                    </Badge>
                  </div>
                  {insurance.policy_number && (
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Policy: {insurance.policy_number}
                    </p>
                  )}
                </section>
              )}

              {/* Active Encounter */}
              {activeEncounter && (
                <section className="px-5 py-3">
                  <div className="flex items-center gap-2 mb-2">
                    <Activity className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      Active Encounter
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-lg font-bold font-mono text-primary">
                      {activeEncounter.queue_number ?? String(activeEncounter.id).slice(0, 8)}
                    </span>
                    <Badge
                      className={cn(
                        "text-xs capitalize",
                        STATUS_COLORS[activeEncounter.status ?? ""] ?? "bg-slate-100 text-slate-700"
                      )}
                    >
                      {(activeEncounter.status ?? "—").replace(/_/g, " ")}
                    </Badge>
                  </div>
                  {activeEncounter.department && (
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {activeEncounter.department}
                      {activeEncounter.consulting_room ? ` · ${activeEncounter.consulting_room}` : ""}
                    </p>
                  )}
                  {activeEncounter.chief_complaint && (
                    <p className="text-sm text-foreground mt-1 line-clamp-2">
                      {activeEncounter.chief_complaint}
                    </p>
                  )}
                </section>
              )}

              {/* Recent Labs */}
              <section className="px-5 py-3">
                <div className="flex items-center gap-2 mb-2">
                  <FlaskConical className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                    Recent Labs
                  </span>
                </div>
                {labOrders.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No recent lab orders.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {labOrders.map((lab: any, i: number) => (
                      <li key={lab.id ?? i} className="flex items-center justify-between text-sm">
                        <span className="text-foreground truncate">
                          {lab.test_name ?? lab.panel_name ?? lab.test_type ?? "Lab Order"}
                        </span>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-xs text-muted-foreground">
                            {formatDate(lab.ordered_at ?? lab.created_at)}
                          </span>
                          <Badge
                            className={cn(
                              "text-xs",
                              lab.status === "resulted"
                                ? "bg-green-100 text-green-700 hover:bg-green-100"
                                : "bg-slate-100 text-slate-600 hover:bg-slate-100"
                            )}
                          >
                            {lab.status ?? "—"}
                          </Badge>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              {/* Active Medications */}
              <section className="px-5 py-3">
                <div className="flex items-center gap-2 mb-2">
                  <Pill className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                    Active Medications
                  </span>
                </div>
                {prescriptions.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No active prescriptions.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {prescriptions.map((rx: any, i: number) => (
                      <li key={rx.id ?? i} className="flex items-center justify-between text-sm">
                        <span className="text-foreground truncate">
                          {rx.drug_name ?? rx.medication_name ?? rx.name ?? "Medication"}
                          {rx.dosage ? ` ${rx.dosage}` : ""}
                        </span>
                        <Badge
                          className={cn(
                            "text-xs shrink-0",
                            rx.status === "active" || rx.status === "pending"
                              ? "bg-blue-100 text-blue-700 hover:bg-blue-100"
                              : "bg-slate-100 text-slate-600 hover:bg-slate-100"
                          )}
                        >
                          {rx.status ?? "—"}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>

            {/* Action buttons */}
            <Separator />
            <div className="px-5 py-4 flex flex-col gap-2">
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="flex-1 gap-1.5"
                  onClick={() => navigate("/hospital/front-desk", {
                    state: {
                      prefillPatient: {
                        id:            patient.id,
                        mrn:           patient.mrn,
                        first_name:    patient.first_name,
                        last_name:     patient.last_name,
                        gender:        patient.gender,
                        date_of_birth: patient.date_of_birth,
                        phone:         patient.phone,
                        hmo_provider:  patient.hmo_provider,
                      },
                    },
                  })}
                >
                  <Plus className="h-3.5 w-3.5" /> New Encounter
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="flex-1 gap-1.5"
                  onClick={() => navigate("/hospital/lab")}
                >
                  <FlaskConical className="h-3.5 w-3.5" /> Order Lab
                </Button>
              </div>
              <Button
                size="sm"
                className="w-full gap-1.5"
                onClick={() => {
                  navigate(`/hospital/patients/${patientMrn}`);
                  onClose();
                }}
              >
                <ExternalLink className="h-3.5 w-3.5" /> View Full CPRS
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
        <div className="space-y-2 flex-1">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-3 w-28" />
        </div>
      </div>
      <Skeleton className="h-16 w-full" />
      <Skeleton className="h-20 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}
