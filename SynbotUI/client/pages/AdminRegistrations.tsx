import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Tabs, TabsContent, TabsList, TabsTrigger,
} from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { UserCheck, UserX, Loader2, Save, ShieldCheck } from "lucide-react";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

const CANONICAL_ROLES = [
  "admin", "management", "doctor", "nurse", "pharmacist", "lab", "radiology",
  "receptionist", "physiotherapist", "finance", "hr", "ops", "quality_assurance",
  "hmo", "cashier", "store", "auditor",
];

// ── Pending Registrations tab ──────────────────────────────────────────────────
function PendingRegistrationsTab() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [reviewing, setReviewing] = useState<any | null>(null);
  const [decision, setDecision] = useState<"approve" | "reject" | null>(null);
  const [reason, setReason] = useState("");
  const [attestation, setAttestation] = useState("");
  const [saving, setSaving] = useState(false);
  // Which HR record this person is: an existing one (link the login to it) or "new".
  const [hrChoice, setHrChoice] = useState<string>("");
  const matchesQ = useQuery({
    queryKey: ["staff-registrations", "hr-matches", reviewing?.id],
    queryFn: () => api.registrations.hrMatches(reviewing!.id),
    enabled: !!reviewing && decision === "approve",
  });
  const matches: any[] = matchesQ.data?.data ?? [];
  const emailMatch = matches.find((m) => m.why === "same email");
  const chosen = emailMatch ? emailMatch.id : hrChoice;

  const { data, refetch } = useQuery({
    queryKey: ["staff-registrations", "pending"],
    queryFn: () => api.registrations.list("pending"),
  });
  const rows: any[] = data?.data ?? [];

  const closeDialog = () => {
    setReviewing(null);
    setDecision(null);
    setReason("");
    setAttestation("");
    setHrChoice("");
  };

  async function submitDecision() {
    if (!reviewing || !decision) return;
    setSaving(true);
    try {
      if (decision === "approve") {
        const out = await api.registrations.approve(reviewing.id, {
          approval_reason: reason, attestation_text: attestation,
          link_staff_id: chosen && chosen !== "new" ? chosen : undefined, create_new: chosen === "new",
        });
        if (out.mode === "linked") {
          toast({ title: "Linked to their HR record", description: out.filled?.length ? `Filled from the registration: ${out.filled.join(", ")}` : "HR already held their details" });
        }
      } else {
        await api.registrations.reject(reviewing.id, { reason });
      }
      toast({ title: decision === "approve" ? "Registration approved" : "Registration rejected", description: reviewing.email });
      closeDialog();
      void refetch();
      void qc.invalidateQueries({ queryKey: ["staff-registrations"] });
    } catch (e: any) {
      toast({ title: "Failed", description: e.message, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          Pending Registrations
          <span className="ml-auto text-xs text-muted-foreground font-normal">{rows.length} pending</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                {["Name", "Email", "Role", "Department", "Submitted", "Actions"].map((h) => (
                  <TableHead key={h} className="text-xs">{h}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 ? (
                <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground text-sm">No pending registrations</TableCell></TableRow>
              ) : rows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="text-sm font-medium">{r.full_name}</TableCell>
                  <TableCell className="text-sm">{r.email}</TableCell>
                  <TableCell><Badge variant="outline" className="text-xs capitalize">{r.role}</Badge></TableCell>
                  <TableCell className="text-sm">{r.department ?? "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{new Date(r.created_at).toLocaleDateString()}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1" onClick={() => { setReviewing(r); setDecision("approve"); }}>
                        <UserCheck className="h-3 w-3" /> Approve
                      </Button>
                      <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1 text-destructive" onClick={() => { setReviewing(r); setDecision("reject"); }}>
                        <UserX className="h-3 w-3" /> Reject
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>

      <Dialog open={!!reviewing} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {decision === "approve" ? "Approve" : "Reject"} registration — {reviewing?.full_name}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            {reviewing?.kyc_details && Object.keys(reviewing.kyc_details).length > 0 && (
              <div className="rounded-md border bg-muted/30 p-3 text-xs space-y-1">
                {Object.entries(reviewing.kyc_details).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-4">
                    <span className="text-muted-foreground capitalize">{k.replace(/_/g, " ")}</span>
                    <span className="font-medium">{String(v)}</span>
                  </div>
                ))}
              </div>
            )}
            {decision === "approve" ? (
              <>
                <div className="space-y-1.5 rounded-md border p-3">
                  <div className="text-xs font-medium">Their HR record</div>
                  {matchesQ.isLoading ? <p className="text-xs text-muted-foreground">Looking for them in HR...</p>
                    : emailMatch ? (
                      <p className="text-xs">Already in HR with this email: <b>{emailMatch.full_name}</b> ({emailMatch.department || "no unit"}{emailMatch.designation ? `, ${emailMatch.designation}` : ""}).
                        The login will be attached to that record - no new record is created.</p>
                    ) : (
                      <div className="space-y-1">
                        {matches.map((m) => (
                          <label key={m.id} className="flex cursor-pointer items-start gap-2 text-xs">
                            <input type="radio" name="hr" className="mt-0.5" checked={hrChoice === m.id} disabled={m.has_login} onChange={() => setHrChoice(m.id)} />
                            <span><b>{m.full_name}</b> · {m.department || "no unit"}{m.designation ? `, ${m.designation}` : ""} · {m.staff_number}
                              <span className="text-muted-foreground"> ({m.why}{m.has_login ? ", already has a login" : ""})</span></span>
                          </label>
                        ))}
                        <label className="flex cursor-pointer items-center gap-2 text-xs">
                          <input type="radio" name="hr" checked={hrChoice === "new"} onChange={() => setHrChoice("new")} />
                          <span>{matches.length ? "None of these - they are new to HR" : "Not in HR yet - create their HR record from this registration"}</span>
                        </label>
                      </div>
                    )}
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium">Approval reason</label>
                  <Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why is this registration being approved?" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium">Attestation</label>
                  <Textarea value={attestation} onChange={(e) => setAttestation(e.target.value)} placeholder="I confirm this staff member's identity and role have been verified." />
                </div>
              </>
            ) : (
              <div className="space-y-1">
                <label className="text-xs font-medium">Rejection reason</label>
                <Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why is this registration being rejected?" />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={closeDialog}>Cancel</Button>
            <Button
              onClick={submitDecision}
              disabled={saving || !reason.trim() || (decision === "approve" && (!attestation.trim() || !chosen || matchesQ.isLoading))}
              variant={decision === "reject" ? "destructive" : "default"}
            >
              {saving ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
              Confirm {decision === "approve" ? "Approval" : "Rejection"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

export default function AdminRegistrations() {
  return (
    <motion.div className="p-6 space-y-6" {...motionTransitions.fadeInUp}>
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-5 w-5 text-blue-500" />
        <h1 className="text-lg font-semibold">Staff Registrations</h1>
      </div>
      <PendingRegistrationsTab />
      {/* Roles are changed in one place - User Access - where every role can be combined and a reason is recorded. */}
      <p className="text-xs text-muted-foreground">
        To change what an existing person can open, use <Link to="/admin/users" className="text-primary hover:underline">User Access</Link>.
      </p>
    </motion.div>
  );
}
