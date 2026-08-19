import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { Video, Copy, Loader2, User, Stethoscope } from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { TELE_STATUS_COLORS, TELE_ACTIONS, DetailRow, SectionLabel } from "@/components/engagement/engagement-shared";

interface TelemedicineSessionPanelProps {
  session: any;
  onClose: () => void;
}

export function TelemedicineSessionPanel({ session: initialSession, onClose }: TelemedicineSessionPanelProps) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const sessionId = initialSession.id;

  const [showEndForm, setShowEndForm] = useState(false);
  const [endForm, setEndForm] = useState({ doctor_notes: "", prescriptions_issued: false });

  const { data: sessionData } = useQuery({
    queryKey: ["tele-session", sessionId],
    queryFn: () => api.telemedicine.getSession(sessionId),
  });
  const session = { ...initialSession, ...(sessionData?.session ?? {}) };

  const { data: joinData, isLoading: joinLoading } = useQuery({
    queryKey: ["tele-join", sessionId],
    queryFn: () => api.telemedicine.getJoinLinks(sessionId),
  });

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ["tele-session", sessionId] });
    void qc.invalidateQueries({ queryKey: ["tele-sessions"] });
    void qc.invalidateQueries({ queryKey: ["tele-stats"] });
  };

  const statusMut = useMutation({
    mutationFn: (payload: { status: string; doctor_notes?: string; prescriptions_issued?: boolean }) =>
      api.telemedicine.advanceStatus(sessionId, payload),
    onSuccess: (_res, payload) => {
      toast({ title: `Session ${payload.status.replace("_", " ")}` });
      setShowEndForm(false);
      setEndForm({ doctor_notes: "", prescriptions_issued: false });
      invalidateAll();
    },
    onError: (e: any) => toast({ title: e?.message || "Status change failed", variant: "destructive" }),
  });

  function copyLink(link: string) {
    navigator.clipboard.writeText(link);
    toast({ title: "Link copied" });
  }

  const actions = TELE_ACTIONS[session.status] ?? [];

  return (
    <Sheet open onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent className="w-[560px] sm:w-[640px] overflow-y-auto p-0 flex flex-col" side="right">
        <SheetHeader className="px-5 pt-5 pb-4 border-b shrink-0">
          <div className="flex items-start gap-3">
            <div className="h-10 w-10 rounded-full bg-blue-500/10 flex items-center justify-center shrink-0">
              <Video className="h-5 w-5 text-blue-500" />
            </div>
            <div className="flex-1 min-w-0">
              <SheetTitle className="text-base leading-tight">Session #{sessionId}</SheetTitle>
              <div className="flex flex-wrap items-center gap-2 mt-1">
                <Badge variant="outline" className={cn("text-xs capitalize", TELE_STATUS_COLORS[session.status] || "")}>
                  {session.status?.replace("_", " ")}
                </Badge>
                <span className="text-xs text-muted-foreground capitalize">{session.visit_type?.replace("_", " ")}</span>
              </div>
            </div>
          </div>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          <section>
            <SectionLabel icon={<User className="h-3.5 w-3.5" />} label="Session Detail" />
            <DetailRow label="Patient ID" value={session.patient_id} mono />
            <DetailRow label="Doctor" value={session.doctor_id} />
            <DetailRow label="Date" value={session.scheduled_date} />
            <DetailRow label="Time" value={session.scheduled_time} mono />
            <DetailRow label="Duration" value={session.duration_minutes ? `${session.duration_minutes} min` : undefined} />
            <DetailRow label="Chief Complaint" value={session.chief_complaint} />
            <DetailRow label="Notes" value={session.notes} />
          </section>

          <Separator />

          <section>
            <SectionLabel icon={<Video className="h-3.5 w-3.5" />} label="Join Links" />
            {joinLoading ? (
              <div className="flex justify-center py-4"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>
            ) : (
              <div className="space-y-3">
                {[
                  { label: "Doctor Link (Host)", key: "doctor_link" },
                  { label: "Patient Link (Guest)", key: "patient_link" },
                ].map(item => (
                  <div key={item.key} className="space-y-1">
                    <Label className="text-xs text-muted-foreground">{item.label}</Label>
                    <div className="flex gap-2">
                      <Input readOnly value={joinData?.[item.key] || ""} className="text-xs font-mono flex-1 h-8" />
                      <Button size="sm" variant="outline" className="h-8 px-2" onClick={() => copyLink(joinData?.[item.key])}>
                        <Copy className="w-3 h-3" />
                      </Button>
                      <Button size="sm" className="h-8 bg-green-700 hover:bg-green-600 px-2"
                        onClick={() => window.open(joinData?.[item.key], "_blank")}>
                        <Video className="w-3 h-3" />
                      </Button>
                    </div>
                  </div>
                ))}
                <p className="text-xs text-muted-foreground">Powered by Jitsi Meet. No download required — opens in browser.</p>
              </div>
            )}
          </section>

          {(actions.length > 0 || showEndForm) && (
            <>
              <Separator />
              <section>
                <SectionLabel icon={<Stethoscope className="h-3.5 w-3.5" />} label="Status" />
                {showEndForm ? (
                  <div className="space-y-3">
                    <div className="space-y-1">
                      <Label className="text-xs text-muted-foreground">Doctor Notes</Label>
                      <Textarea value={endForm.doctor_notes}
                        onChange={e => setEndForm(f => ({ ...f, doctor_notes: e.target.value }))}
                        className="text-sm h-20 resize-none" placeholder="Clinical summary of the visit…" />
                    </div>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input type="checkbox" checked={endForm.prescriptions_issued}
                        onChange={e => setEndForm(f => ({ ...f, prescriptions_issued: e.target.checked }))}
                        className="rounded border-border" />
                      <span className="text-xs text-muted-foreground">Prescriptions issued</span>
                    </label>
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" onClick={() => setShowEndForm(false)}>Cancel</Button>
                      <Button size="sm" className="bg-blue-600 hover:bg-blue-700" disabled={statusMut.isPending}
                        onClick={() => statusMut.mutate({ status: "completed", doctor_notes: endForm.doctor_notes || undefined, prescriptions_issued: endForm.prescriptions_issued })}>
                        {statusMut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : null}
                        Confirm End Session
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {actions.map(a => (
                      <Button key={a.status} size="sm"
                        variant={a.status === "cancelled" || a.status === "no_show" ? "outline" : "default"}
                        className={cn(
                          a.status === "cancelled" && "text-red-500 border-red-500/40 hover:bg-red-500/10",
                          a.status === "no_show" && "text-orange-500 border-orange-500/40 hover:bg-orange-500/10",
                          a.status === "active" && "bg-blue-600 hover:bg-blue-700",
                        )}
                        disabled={statusMut.isPending}
                        onClick={() => {
                          if (a.status === "completed") setShowEndForm(true);
                          else statusMut.mutate({ status: a.status });
                        }}>
                        {a.label}
                      </Button>
                    ))}
                  </div>
                )}
              </section>
            </>
          )}

          {(session.doctor_notes || session.prescriptions_issued) && (
            <>
              <Separator />
              <section>
                <SectionLabel icon={<Stethoscope className="h-3.5 w-3.5" />} label="Visit Summary" />
                <DetailRow label="Doctor Notes" value={session.doctor_notes} />
                {session.prescriptions_issued && <Badge variant="outline" className="text-xs mt-1">Prescriptions issued</Badge>}
              </section>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
