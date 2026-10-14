/**
 * User Access - logins, their roles, and what each role opens (reportGUide.md s4).
 *
 * A person can hold several roles; access is the union. Roles come from one server catalogue
 * (backend/src/roles.py) and the "they will be able to open" preview uses the sidebar's own rule,
 * so neither can drift. Every login gets its HR profile on creation, so the person is in HR and on
 * the Team tab at once. Every change records a reason in the audit log.
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { KeyRound, Shield, ShieldCheck, UserPlus, Users, UserX } from "lucide-react";
import { api } from "@/lib/api-client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/workspace/PageHeader";
import { KpiStrip } from "@/components/workspace/KpiStrip";
import { FilterBar } from "@/components/workspace/FilterBar";
import { DetailSheet } from "@/components/workspace/DetailSheet";
import { AccessPreview, RolePicker, type RoleDef } from "@/components/admin/RolePicker";
import { TourPreview } from "@/components/tour/TourPreview";

type UserRecord = {
  id: string; email: string; roles: string[]; is_active: boolean; created_at?: string;
  full_name?: string | null; unit?: string | null; job_title?: string | null; team?: string; has_profile?: boolean;
};

const ATTESTATION = "I attest this access management action is authorized and policy-compliant.";
const SPECIAL_CHARS = "!@#$%^&*()-_=+[]{};:,.?/";
const CLINICAL = new Set(["doctor", "nurse", "pharmacist", "lab", "radiology", "physiotherapist"]);

function passwordProblem(pwd: string): string | null {
  if (pwd.length < 10) return "At least 10 characters";
  if (!/[a-z]/.test(pwd)) return "At least one lowercase letter";
  if (!/[A-Z]/.test(pwd)) return "At least one uppercase letter";
  if (!/[0-9]/.test(pwd)) return "At least one number";
  if (![...SPECIAL_CHARS].some((c) => pwd.includes(c))) return `At least one special character (${SPECIAL_CHARS})`;
  return null;
}

const errText = (e: any, fallback: string) => e?.message || fallback;

export default function AdminUsers() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<UserRecord | null>(null);
  const [statusTarget, setStatusTarget] = useState<UserRecord | null>(null);
  const [passwordTarget, setPasswordTarget] = useState<UserRecord | null>(null);

  const usersQ = useQuery({ queryKey: ["admin-users"], queryFn: () => api.users.list(500) });
  const catalogQ = useQuery({ queryKey: ["user-role-catalog"], queryFn: () => api.users.roles(), staleTime: 300_000 });
  const catalog: RoleDef[] = catalogQ.data?.roles ?? [];
  const labelOf = (k: string) => catalog.find((r) => r.key === k)?.label ?? k;

  const users = useMemo<UserRecord[]>(
    () => (Array.isArray(usersQ.data) ? usersQ.data : []).filter((u: any) => typeof u?.id === "string" && Array.isArray(u?.roles)),
    [usersQ.data],
  );
  const rows = useMemo(() => users.filter((u) =>
    (!search || `${u.full_name ?? ""} ${u.email} ${u.unit ?? ""} ${u.job_title ?? ""}`.toLowerCase().includes(search.toLowerCase())) &&
    (!roleFilter || u.roles.includes(roleFilter)) &&
    (!statusFilter || (statusFilter === "active" ? u.is_active : !u.is_active))), [users, search, roleFilter, statusFilter]);

  const active = users.filter((u) => u.is_active);
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["admin-users"] }); };

  return (
    <div className="flex flex-col gap-5">
      <PageHeader icon={Shield} title="User Access"
                  subtitle="Logins and what each person can open · every login has an HR profile · every change is audited"
                  actions={<Button size="sm" onClick={() => setCreating(true)}><UserPlus className="mr-1.5 h-4 w-4" />New user</Button>} />

      <KpiStrip items={[
        { label: "Active logins", value: active.length, icon: Users, sub: `${users.length - active.length} deactivated`,
          onClick: () => setStatusFilter("active") },
        { label: "Clinical staff logins", value: active.filter((u) => u.roles.some((r) => CLINICAL.has(r))).length, icon: ShieldCheck,
          sub: "doctors, nurses, pharmacy, lab, radiology, physio" },
        { label: "Admins", value: active.filter((u) => u.roles.includes("admin")).length, icon: Shield,
          sub: "can change anyone's access", onClick: () => setRoleFilter("admin") },
        { label: "Logins without an HR profile", value: users.filter((u) => !u.has_profile).length, icon: UserX,
          tone: users.some((u) => !u.has_profile) ? "warning" : "default", sub: "created when their access is next changed" },
      ]} />

      <FilterBar
        search={{ value: search, onChange: setSearch, placeholder: "Search name, email, unit or job title" }}
        selects={[
          { label: "Role", value: roleFilter, onChange: setRoleFilter, placeholder: "All roles",
            options: catalog.map((r) => ({ value: r.key, label: r.label })) },
          { label: "Status", value: statusFilter, onChange: setStatusFilter, placeholder: "Active and deactivated",
            options: [{ value: "active", label: "Active" }, { value: "inactive", label: "Deactivated" }] },
        ]} />

      <div className="rounded-xl border bg-card">
        {usersQ.isLoading ? <p className="p-6 text-sm text-muted-foreground">Loading users...</p>
          : usersQ.isError ? <p className="p-6 text-sm text-destructive">Users could not be loaded: {errText(usersQ.error, "error")}</p>
          : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow>
                <TableHead>Person</TableHead><TableHead>Team · unit</TableHead><TableHead>Roles</TableHead>
                <TableHead>Status</TableHead><TableHead className="text-right">Actions</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {rows.length === 0 && <TableRow><TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">No users match.</TableCell></TableRow>}
                {rows.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell>
                      <div className="font-medium">{u.full_name || <span className="text-muted-foreground">no name recorded</span>}</div>
                      <div className="text-xs text-muted-foreground">{u.email}{u.job_title ? ` · ${u.job_title}` : ""}</div>
                    </TableCell>
                    <TableCell className="text-sm">
                      {u.team || "-"}{u.unit && u.unit !== u.team ? <span className="text-muted-foreground"> · {u.unit}</span> : null}
                      {!u.has_profile && <div className="text-xs text-amber-600">no HR profile yet</div>}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">{u.roles.map((r) => <Badge key={r} variant={r === "admin" ? "default" : "secondary"} className="text-xs">{labelOf(r)}</Badge>)}</div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={u.is_active ? "border-emerald-500/40 text-emerald-600" : "text-muted-foreground"}>
                        {u.is_active ? "Active" : "Deactivated"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex flex-wrap justify-end gap-1.5">
                        <Button size="sm" variant="outline" onClick={() => setEditing(u)}>Edit access</Button>
                        <Button size="sm" variant="ghost" onClick={() => setPasswordTarget(u)}><KeyRound className="mr-1 h-3.5 w-3.5" />Password</Button>
                        <Button size="sm" variant="ghost" onClick={() => setStatusTarget(u)}>{u.is_active ? "Deactivate" : "Activate"}</Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <TourPreview />

      <CreateUserSheet open={creating} onClose={() => setCreating(false)} catalog={catalog} units={catalogQ.data?.units ?? []} onDone={refresh} />
      <EditAccessSheet user={editing} onClose={() => setEditing(null)} catalog={catalog} onDone={refresh} />
      <StatusDialog user={statusTarget} onClose={() => setStatusTarget(null)} onDone={refresh} />
      <PasswordDialog user={passwordTarget} onClose={() => setPasswordTarget(null)} />
    </div>
  );
}

function ReasonField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="space-y-1.5">
      <Label>Reason <span className="text-destructive">*</span></Label>
      <Textarea rows={2} value={value} onChange={(e) => onChange(e.target.value)} placeholder="Why this change - kept in the audit log" />
    </div>
  );
}

function CreateUserSheet({ open, onClose, catalog, units, onDone }: {
  open: boolean; onClose: () => void; catalog: RoleDef[]; units: string[]; onDone: () => void;
}) {
  const blank = { email: "", password: "", full_name: "", unit: "", job_title: "", reason: "" };
  const [f, setF] = useState(blank);
  const [roles, setRoles] = useState<string[]>([]);
  const set = (k: keyof typeof blank) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  const pwd = f.password ? passwordProblem(f.password) : null;
  const ready = /.+@.+\..+/.test(f.email.trim()) && f.password && !pwd && roles.length > 0 && f.reason.trim().length > 0;
  const m = useMutation({
    mutationFn: () => api.users.create({
      email: f.email.trim().toLowerCase(), password: f.password, roles, approval_reason: f.reason.trim(), attestation_text: ATTESTATION,
      full_name: f.full_name.trim() || undefined, unit: f.unit.trim() || undefined, job_title: f.job_title.trim() || undefined,
    }),
    onSuccess: () => { toast.success("User created - their HR profile is ready"); setF(blank); setRoles([]); onDone(); onClose(); },
    onError: (e: any) => toast.error(errText(e, "Could not create the user")),
  });
  return (
    <DetailSheet open={open} onOpenChange={(o) => !o && onClose()} title="New user" icon={UserPlus}
                 description="Creates the login and the person's HR profile together."
                 footer={<Button disabled={!ready || m.isPending} onClick={() => m.mutate()}>{m.isPending ? "Creating..." : "Create user"}</Button>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5 sm:col-span-2"><Label>Full name</Label><Input value={f.full_name} onChange={set("full_name")} placeholder="As it should appear to colleagues" /></div>
        <div className="space-y-1.5"><Label>Email <span className="text-destructive">*</span></Label><Input type="email" value={f.email} onChange={set("email")} /></div>
        <div className="space-y-1.5">
          <Label>Temporary password <span className="text-destructive">*</span></Label>
          <Input type="password" value={f.password} onChange={set("password")} />
          {pwd && <p className="text-xs text-destructive">{pwd}</p>}
        </div>
        <div className="space-y-1.5">
          <Label>Unit</Label>
          <Input list="hr-units" value={f.unit} onChange={set("unit")} placeholder="e.g. Gynaecology, OPD" />
          <datalist id="hr-units">{units.map((u) => <option key={u} value={u} />)}</datalist>
        </div>
        <div className="space-y-1.5"><Label>Job title</Label><Input value={f.job_title} onChange={set("job_title")} /></div>
      </div>
      <div className="space-y-2">
        <Label>Roles <span className="text-destructive">*</span> <span className="font-normal text-muted-foreground">- tick every role they need; access is the union</span></Label>
        <RolePicker catalog={catalog} value={roles} onChange={setRoles} />
      </div>
      <AccessPreview roles={roles} />
      <ReasonField value={f.reason} onChange={(v) => setF({ ...f, reason: v })} />
    </DetailSheet>
  );
}

function EditAccessSheet({ user, onClose, catalog, onDone }: { user: UserRecord | null; onClose: () => void; catalog: RoleDef[]; onDone: () => void }) {
  const [roles, setRoles] = useState<string[]>([]);
  const [reason, setReason] = useState("");
  const [forId, setForId] = useState<string | null>(null);
  if (user && forId !== user.id) { setForId(user.id); setRoles(user.roles); setReason(""); }
  const before = new Set(user?.roles ?? []);
  const added = roles.filter((r) => !before.has(r));
  const removed = (user?.roles ?? []).filter((r) => !roles.includes(r));
  const changed = added.length + removed.length > 0;
  const label = (k: string) => catalog.find((r) => r.key === k)?.label ?? k;
  const m = useMutation({
    mutationFn: () => api.users.setRoles(user!.id, roles, reason.trim()),
    onSuccess: () => { toast.success("Access updated - it applies when their session next refreshes"); onDone(); onClose(); },
    onError: (e: any) => toast.error(errText(e, "Could not change access")),
  });
  return (
    <DetailSheet open={!!user} onOpenChange={(o) => !o && onClose()} title="Edit access" icon={Shield}
                 description={user ? `${user.full_name || user.email} · ${user.email}` : undefined}
                 footer={<Button disabled={!changed || !roles.length || !reason.trim() || m.isPending} onClick={() => m.mutate()}>{m.isPending ? "Saving..." : "Save access"}</Button>}>
      <RolePicker catalog={catalog} value={roles} onChange={setRoles} />
      {changed && (
        <div className="rounded-lg border p-3 text-xs">
          {added.length > 0 && <div><span className="font-medium text-emerald-600">Adds:</span> {added.map(label).join(", ")}</div>}
          {removed.length > 0 && <div><span className="font-medium text-red-600">Removes:</span> {removed.map(label).join(", ")}</div>}
        </div>
      )}
      <AccessPreview roles={roles} />
      <ReasonField value={reason} onChange={setReason} />
    </DetailSheet>
  );
}

function StatusDialog({ user, onClose, onDone }: { user: UserRecord | null; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const next = user ? !user.is_active : true;
  const m = useMutation({
    mutationFn: () => api.users.setStatus(user!.id, { is_active: next, approval_reason: reason.trim(), attestation_text: ATTESTATION }),
    onSuccess: () => { toast.success(next ? "User activated" : "User deactivated"); setReason(""); onDone(); onClose(); },
    onError: (e: any) => toast.error(errText(e, "Could not change status")),
  });
  return (
    <Dialog open={!!user} onOpenChange={(o) => { if (!o) { setReason(""); onClose(); } }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{next ? "Activate" : "Deactivate"} {user?.full_name || user?.email}</DialogTitle>
          <DialogDescription>{next ? "They will be able to sign in again." : "They will not be able to sign in. Their records and history are kept."}</DialogDescription>
        </DialogHeader>
        <ReasonField value={reason} onChange={setReason} />
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant={next ? "default" : "destructive"} disabled={!reason.trim() || m.isPending} onClick={() => m.mutate()}>{next ? "Activate" : "Deactivate"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PasswordDialog({ user, onClose }: { user: UserRecord | null; onClose: () => void }) {
  const [pwd, setPwd] = useState("");
  const [reason, setReason] = useState("");
  const problem = pwd ? passwordProblem(pwd) : null;
  const close = () => { setPwd(""); setReason(""); onClose(); };
  const m = useMutation({
    mutationFn: () => api.users.resetPassword(user!.id, { password: pwd, approval_reason: reason.trim(), attestation_text: ATTESTATION }),
    onSuccess: () => { toast.success("Password reset"); close(); },
    onError: (e: any) => toast.error(errText(e, "Could not reset the password")),
  });
  return (
    <Dialog open={!!user} onOpenChange={(o) => !o && close()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reset password</DialogTitle>
          <DialogDescription>{user?.full_name || user?.email} · give them the new password in person.</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label>New password</Label>
          <Input type="password" value={pwd} onChange={(e) => setPwd(e.target.value)} />
          {problem && <p className="text-xs text-destructive">{problem}</p>}
        </div>
        <ReasonField value={reason} onChange={setReason} />
        <DialogFooter>
          <Button variant="ghost" onClick={close}>Cancel</Button>
          <Button disabled={!pwd || !!problem || !reason.trim() || m.isPending} onClick={() => m.mutate()}>Reset password</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
