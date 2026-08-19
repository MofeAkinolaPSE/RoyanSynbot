import { useState } from "react";
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
  };

  async function submitDecision() {
    if (!reviewing || !decision) return;
    setSaving(true);
    try {
      if (decision === "approve") {
        await api.registrations.approve(reviewing.id, { approval_reason: reason, attestation_text: attestation });
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
                  <TableCell><Badge variant="outline" className="text-[12px] capitalize">{r.role}</Badge></TableCell>
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
              disabled={saving || !reason.trim() || (decision === "approve" && !attestation.trim())}
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

// ── Role Assignment tab (moved from AdminDashboard) ───────────────────────────
function UserRoleRow({ user, onSaved }: { user: any; onSaved: () => void }) {
  const { toast } = useToast();
  const [selectedRole, setSelectedRole] = useState<string>((user.roles ?? [])[0] ?? "");
  const [saving, setSaving] = useState(false);

  async function save() {
    if (!selectedRole) return;
    setSaving(true);
    try {
      await api.users.setRoles(user.id, [selectedRole]);
      toast({ title: "Role updated", description: `${user.email} → ${selectedRole}` });
      onSaved();
    } catch (e: any) {
      toast({ title: "Failed", description: e.message, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  }

  const currentRoles: string[] = user.roles ?? [];

  return (
    <TableRow>
      <TableCell className="text-sm font-medium">{user.email}</TableCell>
      <TableCell>
        <div className="flex flex-wrap gap-1">
          {currentRoles.map((r: string) => (
            <Badge key={r} variant="outline" className="text-[12px] capitalize">{r}</Badge>
          ))}
          {currentRoles.length === 0 && <span className="text-xs text-muted-foreground">—</span>}
        </div>
      </TableCell>
      <TableCell>
        <Badge variant="outline" className={cn("text-[12px]", user.is_active ? "text-green-700 bg-green-50 border-green-300" : "text-slate-500")}>
          {user.is_active ? "Active" : "Inactive"}
        </Badge>
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <Select value={selectedRole} onValueChange={setSelectedRole}>
            <SelectTrigger className="h-7 w-36 text-xs"><SelectValue placeholder="Assign role…" /></SelectTrigger>
            <SelectContent>
              {CANONICAL_ROLES.map((r) => <SelectItem key={r} value={r} className="capitalize text-xs">{r}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1" disabled={!selectedRole || saving} onClick={save}>
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />} Save
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}

function RoleAssignmentsTab() {
  const qc = useQueryClient();
  const { data: usersData, refetch } = useQuery({
    queryKey: ["admin-users-roles"],
    queryFn: () => api.users.list(200),
    staleTime: 120_000,
  });
  const users: any[] = Array.isArray(usersData) ? usersData : [];

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          Role Assignments
          <span className="ml-auto text-xs text-muted-foreground font-normal">{users.length} users</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                {["Email", "Current Roles", "Status", "Assign Role"].map((h) => (
                  <TableHead key={h} className="text-xs">{h}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.length === 0 ? (
                <TableRow><TableCell colSpan={4} className="text-center py-8 text-muted-foreground text-sm">No users found</TableCell></TableRow>
              ) : users.map((u: any) => (
                <UserRoleRow key={u.id} user={u} onSaved={() => { void refetch(); void qc.invalidateQueries({ queryKey: ["admin-users-roles"] }); }} />
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
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
      <Tabs defaultValue="pending">
        <TabsList>
          <TabsTrigger value="pending">Pending Registrations</TabsTrigger>
          <TabsTrigger value="roles">Role Assignments</TabsTrigger>
        </TabsList>
        <TabsContent value="pending" className="mt-4">
          <PendingRegistrationsTab />
        </TabsContent>
        <TabsContent value="roles" className="mt-4">
          <RoleAssignmentsTab />
        </TabsContent>
      </Tabs>
    </motion.div>
  );
}
