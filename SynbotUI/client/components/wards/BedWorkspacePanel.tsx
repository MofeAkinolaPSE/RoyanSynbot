import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import {
  BedDouble, User, UserPlus, ExternalLink, Loader2, Wrench, ShieldCheck,
  CheckCircle2, Trash2,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { BedBadge, DetailRow, SectionLabel } from "@/components/wards/wards-shared";
import { PANEL_WIDTH } from "@/components/shared/panel-shared";
import { NursingWorkspacePanel } from "@/components/nursing/NursingWorkspacePanel";
import { HeartPulse, NotebookPen, Activity } from "lucide-react";
import { cn } from "@/lib/utils";
import { InpatientCharges } from "@/components/wards/InpatientCharges";

interface BedWorkspacePanelProps {
  bed: {
    id: string | number;
    ward_id: string | number;
    ward_name?: string;
    bed_number?: string;
    bed_type?: string;
    status?: string;
    current_patient_id?: string | number;
    /** Occupant's active encounter — nursing notes are written against one. */
    current_encounter_id?: number | null;
    patient_name?: string;
    patient_mrn?: string;
    admitted_at?: string;
    notes?: string;
  } & Record<string, any>;
  onClose: () => void;
}

function ageFromDob(dob?: string): string {
  if (!dob) return "—";
  const age = Math.floor((Date.now() - new Date(dob).getTime()) / (365.25 * 24 * 3600 * 1000));
  return isNaN(age) ? "—" : `${age}y`;
}

/**
 * royan_beds records admitted_at and no duration, so length of stay is derived.
 * A current occupant is measured to now, which is the number a ward round
 * actually asks for.
 */
function bedLengthOfStay(admitted?: string | null): string | undefined {
  if (!admitted) return undefined;
  const start = new Date(admitted).getTime();
  if (!Number.isFinite(start)) return undefined;
  const ms = Date.now() - start;
  if (ms < 0) return undefined;
  const days = Math.floor(ms / 86_400_000);
  const hours = Math.floor((ms % 86_400_000) / 3_600_000);
  if (days === 0) return `${hours} hour${hours === 1 ? "" : "s"}`;
  return `${days} day${days === 1 ? "" : "s"}${hours ? `, ${hours}h` : ""}`;
}

export function BedWorkspacePanel({ bed: initialBed, onClose }: BedWorkspacePanelProps) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const qc = useQueryClient();

  // Which nursing tab to open for the bed's occupant, if any.
  const [nursingTab, setNursingTab] = useState<string | null>(null);
  const [patientQuery, setPatientQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const [selectedPatient, setSelectedPatient] = useState<any | null>(null);
  const [selectedEncounterId, setSelectedEncounterId] = useState("none");
  const [admitNotes, setAdmitNotes] = useState("");

  const wardId = String(initialBed.ward_id);
  const bedId = String(initialBed.id);

  const { data: bedsData, isLoading } = useQuery({
    queryKey: ["beds", wardId],
    queryFn: () => api.hospital.wards.beds(wardId),
    refetchInterval: 15_000,
  });
  const beds: any[] = bedsData?.beds ?? [];
  const b: typeof initialBed = beds.find((x: any) => String(x.id) === bedId) ?? initialBed;

  function handleQueryChange(val: string) {
    setPatientQuery(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedQuery(val), 400);
  }

  const { data: searchData, isFetching: searching } = useQuery({
    queryKey: ["bed-panel-patient-search", debouncedQuery],
    queryFn: () => api.hospital.patients.search(debouncedQuery),
    enabled: !selectedPatient && debouncedQuery.length >= 2,
  });
  const searchResults: any[] = Array.isArray(searchData) ? searchData : (searchData?.patients ?? []);

  const { data: encountersData } = useQuery({
    queryKey: ["bed-panel-encounters", selectedPatient?.id],
    queryFn: () => api.hospital.queue.list({ patient_id: Number(selectedPatient.id), active_only: true }),
    enabled: !!selectedPatient,
  });
  const activeEncounters: any[] = encountersData?.encounters ?? [];

  useEffect(() => {
    if (activeEncounters.length === 1) {
      setSelectedEncounterId(String(activeEncounters[0].id));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeEncounters.length]);

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ["beds"] });
    void qc.invalidateQueries({ queryKey: ["wards"] });
  };

  const admitMut = useMutation({
    mutationFn: () => api.hospital.wards.admitBed(wardId, bedId, {
      patient_id: Number(selectedPatient.id),
      encounter_id: selectedEncounterId !== "none" ? Number(selectedEncounterId) : undefined,
      notes: admitNotes || undefined,
    }),
    onSuccess: () => {
      toast({ title: "Patient admitted to bed" });
      setSelectedPatient(null);
      setPatientQuery("");
      setDebouncedQuery("");
      setSelectedEncounterId("none");
      setAdmitNotes("");
      invalidateAll();
    },
    onError: (e: any) => toast({ title: "Admission failed", description: e.message, variant: "destructive" }),
  });

  const freeMut = useMutation({
    mutationFn: () => api.hospital.wards.freeBed(wardId, bedId),
    onSuccess: () => { toast({ title: "Bed freed" }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const statusMut = useMutation({
    mutationFn: (status: string) => api.hospital.wards.updateBedStatus(wardId, bedId, { status }),
    onSuccess: (_res, status) => { toast({ title: `Bed marked ${status}` }); invalidateAll(); },
    onError: (e: any) => toast({ title: "Error", description: e.message, variant: "destructive" }),
  });

  const status = b.status ?? "available";
  const canFree            = status === "occupied";
  const canMarkReserved    = status === "available";
  const canMarkMaintenance = status === "available" || status === "reserved";
  const canMarkAvailable   = status === "reserved" || status === "maintenance";

  return (
    <Sheet open onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className={cn(PANEL_WIDTH.default, "overflow-y-auto p-0 flex flex-col")} side="right">
        <SheetHeader className="px-5 pt-5 pb-4 border-b shrink-0">
          <div className="flex items-start gap-3">
            <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
              <BedDouble className="h-5 w-5 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <SheetTitle className="text-base leading-tight">Bed {b.bed_number ?? bedId}</SheetTitle>
              <div className="flex flex-wrap items-center gap-2 mt-1">
                <span className="text-xs text-muted-foreground">{b.ward_name ?? `Ward ${wardId}`}</span>
                <Badge variant="outline" className="text-xs capitalize">{b.bed_type ?? "standard"}</Badge>
                <BedBadge status={status} />
              </div>
            </div>
          </div>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {isLoading && !bedsData ? (
            <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
          ) : (
            <>
              <section>
                <SectionLabel icon={<BedDouble className="h-3.5 w-3.5" />} label="Bed Detail" />
                <DetailRow label="Type"      value={b.bed_type} />
                <DetailRow label="Status"    value={status} />
                <DetailRow label="Admitted"  value={b.admitted_at ? new Date(b.admitted_at).toLocaleString() : undefined} />
                <DetailRow label="Notes"     value={b.notes} />
              </section>

              {b.current_patient_id && (
                <>
                  <Separator />
                  <section>
                    <SectionLabel icon={<User className="h-3.5 w-3.5" />} label="Occupant" />
                    <DetailRow label="Name" value={b.patient_name} />
                    <DetailRow label="MRN"  value={b.patient_mrn} mono />
                    {/* Derived from admitted_at rather than stored — royan_beds
                        has no duration column, and an open stay measures to now,
                        which is what a ward round wants to know. */}
                    <DetailRow label="Length of stay" value={bedLengthOfStay(b.admitted_at)} />
                    {!b.current_encounter_id && (
                      <p className="mt-2 text-xs italic text-muted-foreground">
                        No open encounter for this patient, so nursing entries cannot be
                        recorded from here. Open the full record to review their history.
                      </p>
                    )}
                    <div className="mt-2 flex flex-wrap gap-2">
                      {/* This panel used to offer bed administration only: no
                          vitals, notes, MAR or care plans. Clicking an occupied
                          bed is usually about the patient in it, not the bed. */}
                      <Button variant="outline" size="sm" className="gap-1.5"
                        disabled={!b.current_encounter_id}
                        onClick={() => setNursingTab("detail")}>
                        <HeartPulse className="h-3.5 w-3.5" /> Nursing record
                      </Button>
                      <Button variant="outline" size="sm" className="gap-1.5"
                        disabled={!b.current_encounter_id}
                        onClick={() => setNursingTab("notes")}>
                        <NotebookPen className="h-3.5 w-3.5" /> Notes
                      </Button>
                      <Button variant="outline" size="sm" className="gap-1.5"
                        disabled={!b.current_encounter_id}
                        onClick={() => setNursingTab("vitals")}>
                        <Activity className="h-3.5 w-3.5" /> Vitals
                      </Button>
                      <Button variant="ghost" size="sm" className="gap-1.5"
                        disabled={!b.patient_mrn}
                        onClick={() => { if (b.patient_mrn) { navigate(`/hospital/patients/${b.patient_mrn}`); onClose(); } }}>
                        <ExternalLink className="h-3.5 w-3.5" /> Full record
                      </Button>
                    </div>
                  </section>

                  {b.current_encounter_id && (
                    <>
                      <Separator />
                      <section>
                        <InpatientCharges
                          encounterId={b.current_encounter_id}
                          onGenerateBill={() => {
                            if (b.patient_mrn) {
                              navigate(`/hospital/billing?patient_mrn=${b.patient_mrn}`);
                              onClose();
                            }
                          }}
                        />
                      </section>
                    </>
                  )}
                </>
              )}

              {status === "available" && (
                <>
                  <Separator />
                  <section className="space-y-2">
                    <SectionLabel icon={<UserPlus className="h-3.5 w-3.5" />} label="Admit Patient" />
                    {!selectedPatient ? (
                      <>
                        <Input placeholder="Search patient by name, phone, or HMO ID…" value={patientQuery}
                          onChange={e => handleQueryChange(e.target.value)} />
                        {searching && <p className="text-xs text-muted-foreground">Searching…</p>}
                        {searchResults.length > 0 && (
                          <div className="space-y-1.5 max-h-56 overflow-y-auto">
                            {searchResults.map((p: any) => (
                              <button key={p.id}
                                className="w-full text-left rounded-md border px-3 py-2 text-xs hover:bg-muted/40 transition-colors"
                                onClick={() => { setSelectedPatient(p); setSelectedEncounterId("none"); }}>
                                <p className="font-medium text-sm">{p.first_name} {p.last_name}</p>
                                <p className="text-muted-foreground">
                                  MRN: {p.mrn} · {ageFromDob(p.date_of_birth)} · {p.gender ?? "—"} · {p.phone ?? "—"}
                                </p>
                              </button>
                            ))}
                          </div>
                        )}
                        {debouncedQuery.length >= 2 && !searching && searchResults.length === 0 && (
                          <p className="text-xs text-muted-foreground">No patients found.</p>
                        )}
                      </>
                    ) : (
                      <div className="space-y-2">
                        <div className="rounded-md border border-primary/40 bg-primary/5 px-3 py-2 flex items-center justify-between">
                          <div>
                            <p className="text-sm font-medium">{selectedPatient.first_name} {selectedPatient.last_name}</p>
                            <p className="text-xs text-muted-foreground font-mono">{selectedPatient.mrn}</p>
                          </div>
                          <Button variant="ghost" size="sm" onClick={() => { setSelectedPatient(null); setSelectedEncounterId("none"); }}>Change</Button>
                        </div>
                        <div className="space-y-1">
                          <Label className="text-xs">Active Encounter (optional)</Label>
                          <Select value={selectedEncounterId} onValueChange={setSelectedEncounterId}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="none">None</SelectItem>
                              {activeEncounters.map((enc: any) => (
                                <SelectItem key={enc.id} value={String(enc.id)}>
                                  {enc.queue_number ?? `Encounter #${enc.id}`} — {enc.department ?? "—"} ({enc.status?.replace(/_/g, " ")})
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="space-y-1">
                          <Label className="text-xs">Notes</Label>
                          <Textarea rows={2} placeholder="Admission notes (optional)" value={admitNotes}
                            onChange={e => setAdmitNotes(e.target.value)} />
                        </div>
                        <Button size="sm" className="w-full gap-1.5" disabled={admitMut.isPending} onClick={() => admitMut.mutate()}>
                          {admitMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <UserPlus className="h-3.5 w-3.5" />}
                          Confirm Admission
                        </Button>
                      </div>
                    )}
                  </section>
                </>
              )}
            </>
          )}
        </div>

        <Separator className="shrink-0" />
        <div className="px-5 py-3 flex flex-wrap gap-2 shrink-0">
          {canFree && (
            <Button size="sm" variant="outline" className="gap-1.5 text-red-500 border-red-500/30 hover:bg-red-500/10"
              disabled={freeMut.isPending}
              onClick={() => { if (window.confirm("Free this bed? This discharges the current occupant.")) freeMut.mutate(); }}>
              <Trash2 className="h-3.5 w-3.5" /> Free Bed
            </Button>
          )}
          {canMarkReserved && (
            <Button size="sm" variant="outline" className="gap-1.5" disabled={statusMut.isPending}
              onClick={() => statusMut.mutate("reserved")}>
              <ShieldCheck className="h-3.5 w-3.5" /> Mark Reserved
            </Button>
          )}
          {canMarkMaintenance && (
            <Button size="sm" variant="outline" className="gap-1.5" disabled={statusMut.isPending}
              onClick={() => statusMut.mutate("maintenance")}>
              <Wrench className="h-3.5 w-3.5" /> Mark Maintenance
            </Button>
          )}
          {canMarkAvailable && (
            <Button size="sm" variant="outline" className="gap-1.5 text-green-500 border-green-500/30 hover:bg-green-500/10" disabled={statusMut.isPending}
              onClick={() => statusMut.mutate("available")}>
              <CheckCircle2 className="h-3.5 w-3.5" /> Mark Available
            </Button>
          )}
        </div>
      </SheetContent>

      {/* The occupant's nursing record. Rendered as a sibling rather than
          nested inside this Sheet's content, so there is one Sheet on screen at
          a time and only one focus trap. Closing it returns here. */}
      {nursingTab && b.current_patient_id && b.current_encounter_id && (
        <NursingWorkspacePanel
          encounter={{
            id: b.current_encounter_id,
            patient_id: Number(b.current_patient_id),
            patient_mrn: b.patient_mrn,
            patient_name: b.patient_name,
            department: b.ward_name,
            created_at: b.admitted_at,
          }}
          initialTab={nursingTab}
          onClose={() => setNursingTab(null)}
        />
      )}
    </Sheet>
  );
}
