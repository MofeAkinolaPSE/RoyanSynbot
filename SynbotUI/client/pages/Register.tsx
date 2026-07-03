import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RoleDetailsForm } from "@/components/RoleDetailsForm";
import { api } from "@/lib/api-client";
import { motion } from "framer-motion";
import { CheckCircle2, Loader2 } from "lucide-react";

const ROLE_LABELS: Record<string, string> = {
  admin: "Administrator",
  management: "Management",
  doctor: "Doctor",
  nurse: "Nurse",
  pharmacist: "Pharmacist",
  lab: "Lab Scientist",
  radiology: "Radiographer",
  receptionist: "Receptionist",
  physiotherapist: "Physiotherapist",
  finance: "Finance",
  hr: "HR",
  ops: "Operations",
  quality_assurance: "Quality Assurance",
};

const Register = () => {
  const navigate = useNavigate();
  const [submitted, setSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const { data: rolesData } = useQuery({ queryKey: ["public-roles"], queryFn: () => api.roles.list() });
  const { data: departmentsData } = useQuery({ queryKey: ["public-departments"], queryFn: () => api.publicDepartments.list() });
  const roles = rolesData?.roles ?? [];
  const departments = departmentsData?.records ?? [];

  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    phone: "",
    role: "",
    department: "",
    designation: "",
  });
  const [roleDetails, setRoleDetails] = useState<Record<string, string>>({});

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setSaving(true);
    try {
      await api.registrations.submit({
        full_name: form.full_name,
        email: form.email,
        password: form.password,
        phone: form.phone || undefined,
        role: form.role,
        department: form.department,
        designation: form.designation || undefined,
        kyc_details: roleDetails,
      });
      setSubmitted(true);
    } catch (e: any) {
      setError(e?.message || "Could not submit registration. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  if (submitted) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#06101e] p-6">
        <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/5 p-8 text-center backdrop-blur-2xl">
          <CheckCircle2 className="mx-auto mb-4 h-12 w-12 text-cyan-400" />
          <h2 className="text-xl font-bold text-white">Registration submitted</h2>
          <p className="mt-2 text-sm text-white/50">
            Your details have been sent to an administrator for review. You'll be able to sign in
            once your account is approved.
          </p>
          <Button className="mt-6 w-full" onClick={() => navigate("/login")}>
            Back to Sign In
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#06101e] p-6">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-lg rounded-2xl border border-white/10 bg-white/5 p-8 shadow-2xl backdrop-blur-2xl"
      >
        <div className="mb-6 space-y-1">
          <h2 className="text-xl font-bold text-white">Staff Registration</h2>
          <p className="text-xs text-white/40">
            Submit your details for admin review. Fields differ based on your role.
          </p>
        </div>

        <form className="space-y-4" onSubmit={onSubmit}>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2 space-y-1.5">
              <Label className="text-white/60">Full Name</Label>
              <Input required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} placeholder="e.g. Sarah Ahmed" />
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label className="text-white/60">Email</Label>
              <Input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="you@royanhospital.com" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-white/60">Password</Label>
              <Input type="password" required minLength={10} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-white/60">Phone (optional)</Label>
              <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-white/60">Role</Label>
              <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                <SelectTrigger><SelectValue placeholder="Select role" /></SelectTrigger>
                <SelectContent>
                  {roles.map((r) => <SelectItem key={r} value={r}>{ROLE_LABELS[r] ?? r}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-white/60">Department</Label>
              <Select value={form.department} onValueChange={(v) => setForm({ ...form, department: v })}>
                <SelectTrigger><SelectValue placeholder="Select department" /></SelectTrigger>
                <SelectContent>
                  {departments.map((d) => <SelectItem key={d.id} value={d.name}>{d.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2 space-y-1.5">
              <Label className="text-white/60">Designation / Job Title (optional)</Label>
              <Input value={form.designation} onChange={(e) => setForm({ ...form, designation: e.target.value })} placeholder="e.g. Consultant Physician" />
            </div>
          </div>

          {form.role && (
            <div className="border-t border-white/10 pt-4">
              <RoleDetailsForm role={form.role} value={roleDetails} onChange={setRoleDetails} />
            </div>
          )}

          {error && <p className="text-xs text-red-400">{error}</p>}

          <Button type="submit" disabled={saving || !form.role || !form.department} className="w-full">
            {saving ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Submitting…</> : "Submit for Review"}
          </Button>
        </form>

        <p className="mt-6 text-center text-xs text-white/40">
          Already have an account? <Link to="/login" className="text-cyan-400 hover:underline">Sign in</Link>
        </p>
      </motion.div>
    </div>
  );
};

export default Register;
