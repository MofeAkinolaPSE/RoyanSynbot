import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { BedDouble, Loader2, Check, X, AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

/**
 * Patients a doctor has asked to admit, waiting on a nurse.
 *
 * "when a doctor requests admission for a particular patient, the nurse
 * dashboard needs to have a card that pops up that says one patient waiting
 * admission... the nurse then clicks on that admission ticket and it moves them
 * to the wards."
 *
 * Accepting assigns the bed in the same action rather than sending the nurse to
 * another screen to do it — the bed is the decision, so splitting it in two just
 * creates a window where the patient is "admitted" to nowhere.
 */

const URGENCY_STYLE: Record<string, string> = {
  immediate: "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-400",
  urgent: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  routine: "border-border text-muted-foreground",
};

export function AdmissionRequestsCard({
  onOpenPatient,
}: {
  onOpenPatient?: (request: any) => void;
}) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [choosingBedFor, setChoosingBedFor] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["admission-requests"],
    queryFn: () => api.hospital.queue.listAdmissionRequests("pending"),
    refetchInterval: 30_000,
  });
  const requests: any[] = data?.requests ?? [];

  // Only fetched once a nurse is actually placing someone.
  const { data: bedsData } = useQuery({
    queryKey: ["available-beds"],
    queryFn: () => api.hospital.wards.availableBeds(),
    enabled: choosingBedFor !== null,
  });
  const beds: any[] = (bedsData?.beds ?? []).filter(
    (b: any) => !b.current_patient_id && b.status !== "maintenance",
  );

  const decide = useMutation({
    mutationFn: (p: { id: number; accept: boolean; bed_id?: number }) =>
      api.hospital.queue.decideAdmission(p.id, { accept: p.accept, bed_id: p.bed_id }),
    onSuccess: (_r, v) => {
      setChoosingBedFor(null);
      void qc.invalidateQueries({ queryKey: ["admission-requests"] });
      void qc.invalidateQueries({ queryKey: ["nurse-wards"] });
      toast({ title: v.accept ? "Patient admitted" : "Admission declined" });
    },
    onError: (e: any) =>
      toast({ title: "Could not save", description: e?.message, variant: "destructive" }),
  });

  const empty = !isLoading && requests.length === 0;

  return (
    <Card className={cn(empty ? "border-border" : "border-teal-500/40")}>
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-2">
        <BedDouble className={cn("h-4 w-4", empty ? "text-muted-foreground" : "text-teal-600 dark:text-teal-400")} />
        {/* Kept visible when empty, unlike the approvals queues. This is a
            workflow entry point: a nurse who has never seen a request arrive
            needs to know where they land, and an always-present slot teaches
            that. A hidden card teaches nothing. */}
        <CardTitle className="text-sm">
          {empty
            ? "Admission requests"
            : requests.length === 1
              ? "1 patient waiting admission"
              : `${requests.length} patients waiting admission`}
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-2 pt-0">
        {isLoading ? (
          <div className="flex justify-center py-6">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : empty ? (
          <p className="py-4 text-center text-xs text-muted-foreground">
            No patients waiting for a bed. When a doctor requests admission, the
            patient appears here for you to place.
          </p>
        ) : (
          requests.map((r) => (
            <div key={r.id} className="rounded-md border bg-muted/30 p-3">
              <div className="flex items-start justify-between gap-2">
                <button
                  className="min-w-0 flex-1 text-left"
                  onClick={() => onOpenPatient?.(r)}
                  disabled={!onOpenPatient}
                >
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-sm font-medium">{r.patient_name ?? "Patient"}</span>
                    {r.patient_mrn && (
                      <span className="font-mono text-xs text-muted-foreground">{r.patient_mrn}</span>
                    )}
                    <Badge variant="outline" className={cn("text-xs capitalize", URGENCY_STYLE[r.urgency] ?? "")}>
                      {r.urgency === "immediate" && <AlertTriangle className="mr-1 h-3 w-3" />}
                      {r.urgency}
                    </Badge>
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {[r.age_display, r.gender, r.department].filter(Boolean).join(" · ")}
                  </p>
                  {r.reason && <p className="mt-1 text-xs">{r.reason}</p>}
                  {r.ward_preference && (
                    <p className="text-xs text-muted-foreground">Preferred ward: {r.ward_preference}</p>
                  )}
                </button>

                <div className="flex shrink-0 gap-1">
                  <Button
                    size="sm" variant="outline"
                    className="h-7 gap-1 border-green-500/40 px-2 text-xs text-green-700 hover:bg-green-500/10 dark:text-green-400"
                    onClick={() => setChoosingBedFor(choosingBedFor === r.id ? null : r.id)}
                    disabled={decide.isPending}
                  >
                    <Check className="h-3.5 w-3.5" /> Admit
                  </Button>
                  <Button
                    size="icon" variant="outline"
                    className="h-7 w-7 border-red-500/40 text-red-700 hover:bg-red-500/10 dark:text-red-400"
                    aria-label="Decline"
                    onClick={() => decide.mutate({ id: r.id, accept: false })}
                    disabled={decide.isPending}
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>

              {choosingBedFor === r.id && (
                <div className="mt-2 border-t pt-2">
                  <Select
                    onValueChange={(v) =>
                      decide.mutate({ id: r.id, accept: true, bed_id: Number(v) })
                    }
                    disabled={decide.isPending}
                  >
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue placeholder="Choose a free bed…" />
                    </SelectTrigger>
                    <SelectContent>
                      {beds.length === 0 ? (
                        <div className="px-2 py-3 text-center text-xs text-muted-foreground">
                          No free beds available
                        </div>
                      ) : (
                        beds.map((b: any) => (
                          <SelectItem key={b.id} value={String(b.id)}>
                            {[b.ward_name, b.bed_number].filter(Boolean).join(" · ")}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                  <button
                    className="mt-1.5 text-xs text-muted-foreground hover:underline"
                    onClick={() => decide.mutate({ id: r.id, accept: true })}
                  >
                    Admit without assigning a bed yet
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}
