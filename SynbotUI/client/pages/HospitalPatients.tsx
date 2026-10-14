import { useState, useCallback, useRef, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  UserPlus, Search, Loader2, Users,
  Droplets, User, ChevronRight, Activity, Clock,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { PatientCprsPanel } from "@/components/PatientCprsPanel";

// ─── Types ────────────────────────────────────────────────────────────────────
interface Patient {
  id: string;
  mrn: string;
  first_name: string;
  last_name: string;
  date_of_birth?: string;
  gender?: string;
  phone?: string;
  blood_group?: string;
  hmo_provider?: string;
  hmo_id?: string;
  current_status?: string;
  insurance?: { active?: boolean; hmo_name?: string; plan_name?: string; membership_id?: string };
  address?: string;
  next_of_kin_name?: string;
  next_of_kin_phone?: string;
  registration_date?: string;
}

const BLOOD_TYPES = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "unknown"];

function genderBadge(g?: string) {
  if (!g) return null;
  const map: Record<string, string> = {
    male:   "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
    female: "bg-pink-500/20 text-pink-700 dark:text-pink-400 border-pink-500/30",
    other:  "bg-slate-500/20 text-slate-700 dark:text-slate-300 border-slate-500/30",
  };
  return (
    <Badge variant="outline" className={cn("text-xs capitalize", map[g.toLowerCase()] ?? map.other)}>
      {g}
    </Badge>
  );
}

function calcAge(dob?: string) {
  if (!dob) return "—";
  const d = new Date(dob);
  const age = new Date().getFullYear() - d.getFullYear();
  return `${age} yrs`;
}

function displayName(p: { first_name: string; last_name: string; mrn: string }): string {
  if (p.first_name === "Unknown" || !p.first_name) return p.mrn;
  return `${p.first_name} ${p.last_name}`.trim();
}

// ─── Empty form ────────────────────────────────────────────────────────────────
const emptyForm = {
  first_name: "", last_name: "", date_of_birth: "", gender: "",
  phone: "", blood_group: "", address: "", next_of_kin_name: "", next_of_kin_phone: "",
  hmo_provider: "", hmo_id: "",
};

// ─── Component ────────────────────────────────────────────────────────────────
export default function HospitalPatients() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const navigate = useNavigate();

  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState({ ...emptyForm });
  const [cprsMrn, setCprsMrn] = useState<string | null>(null);

  // Hospital KPIs
  const { data: statusData } = useQuery({
    queryKey: ["hp-hospital-status"],
    queryFn: () => api.dashboard.hospitalStatus(),
    staleTime: 60_000,
    refetchInterval: 60_000,
  });
  const kpis = statusData?.kpis ?? statusData ?? {};

  // Every patient A-Z (first name, then surname, as the names show), 50 a page, when no search is active
  const PAGE = 50;
  const [page, setPage] = useState(0);
  const { data: recentData, isFetching: loadingRecent } = useQuery({
    queryKey: ["patients-az", page],
    queryFn: () => api.hospital.patients.listAz(page * PAGE, PAGE),
    enabled: search.trim().length === 0,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });
  const recentPatients: Patient[] = (() => {
    const d = recentData;
    return Array.isArray(d?.patients) ? d.patients : Array.isArray(d) ? d : [];
  })();

  // Search results — keyed on debouncedSearch so only fires after 350ms pause
  const { data: searchData, isFetching: searching } = useQuery({
    queryKey: ["patients-search", debouncedSearch],
    queryFn: () => api.hospital.patients.search(debouncedSearch),
    enabled: debouncedSearch.trim().length >= 2,
    staleTime: 30_000,
  });

  const handleSearchChange = useCallback((val: string) => {
    setSearch(val);
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    searchDebounceRef.current = setTimeout(() => setDebouncedSearch(val), 350);
  }, []);

  const patients: Patient[] = Array.isArray(searchData?.patients)
    ? searchData.patients
    : Array.isArray(searchData)
    ? searchData
    : [];

  // Register mutation
  const location = useLocation();
  const fromFrontDesk = !!(location.state as any)?.fromFrontDesk;
  useEffect(() => { if (fromFrontDesk) setDialogOpen(true); }, [fromFrontDesk]);
  const registerMut = useMutation({
    mutationFn: () => api.hospital.patients.register(form),
    onSuccess: (res: any) => {
      toast({ title: "Patient registered", description: `${form.first_name} ${form.last_name} added to registry${res?.mrn ? ` (${res.mrn})` : ""}.` });
      setDialogOpen(false);
      setForm({ ...emptyForm });
      void qc.invalidateQueries({ queryKey: ["patients-search"] });
      if (fromFrontDesk && res?.patient?.id) navigate("/hospital/front-desk", { state: { prefillPatient: res.patient } });
    },
    onError: (err: any) => toast({ title: "Registration failed", description: err.message, variant: "destructive" }),
  });

  const field = useCallback(
    (key: keyof typeof emptyForm, val: string) => setForm(f => ({ ...f, [key]: val })),
    [],
  );

  const canSubmit = form.first_name.trim() && form.last_name.trim();

  return (
    <motion.div className="space-y-6" {...motionTransitions.fadeInUp}>
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Patient Registry</h1>
          <p className="text-sm text-muted-foreground">Search, register, and manage patient records</p>
        </div>
        <Button onClick={() => setDialogOpen(true)} className="gap-2">
          <UserPlus className="h-4 w-4" /> Register Patient
        </Button>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "Waiting Now",      value: kpis.patients_waiting ?? "—",     icon: <Users className="h-4 w-4" />,    color: "text-yellow-400" },
          { label: "In Consultation",  value: kpis.active_consultations ?? "—", icon: <Activity className="h-4 w-4" />, color: "text-blue-400"   },
          { label: "Avg Wait (min)",   value: kpis.avg_wait_minutes ?? "—",     icon: <Clock className="h-4 w-4" />,    color: "text-slate-400"  },
        ].map(k => (
          <Card key={k.label}>
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">{k.label}</p>
                  <p className="text-2xl font-bold">{k.value}</p>
                </div>
                <span className={k.color}>{k.icon}</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Search bar */}
      <Card>
        <CardContent className="pt-5">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder="Search by name, MRN, phone, or HMO ID..."
              value={search}
              onChange={e => handleSearchChange(e.target.value)}
            />
            {(searching || loadingRecent) && (
              <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" />
            )}
          </div>
          {search.trim().length > 0 && search.trim().length < 2 && (
            <p className="mt-2 text-xs text-muted-foreground">Enter at least 2 characters to search</p>
          )}
        </CardContent>
      </Card>

      {/* Default list — recent patients when no search active */}
      {search.trim().length === 0 && recentPatients.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Users className="h-4 w-4" />
              Patients A–Z
              <span className="text-xs font-normal text-muted-foreground">
                ({page * PAGE + 1}–{page * PAGE + recentPatients.length})
              </span>
              <span className="ml-auto flex gap-1.5">
                <Button size="sm" variant="outline" className="h-7 px-2 text-xs" disabled={page === 0 || loadingRecent} onClick={() => setPage((p) => p - 1)}>Previous</Button>
                <Button size="sm" variant="outline" className="h-7 px-2 text-xs" disabled={recentPatients.length < PAGE || loadingRecent} onClick={() => setPage((p) => p + 1)}>Next</Button>
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>MRN</TableHead>
                  <TableHead>Full Name</TableHead>
                  <TableHead>Age</TableHead>
                  <TableHead>Gender</TableHead>
                  <TableHead>Blood Group</TableHead>
                  <TableHead>HMO</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentPatients.map(p => (
                  <TableRow
                    key={p.id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => setCprsMrn(p.mrn)}
                  >
                    <TableCell className="font-mono text-xs font-semibold text-primary">{p.mrn}</TableCell>
                    <TableCell className="font-medium">{displayName(p)}</TableCell>
                    <TableCell>{calcAge(p.date_of_birth)}</TableCell>
                    <TableCell>{genderBadge(p.gender)}</TableCell>
                    <TableCell className="text-sm">
                      {p.blood_group ? (
                        <span className="flex items-center gap-1">
                          <Droplets className="h-3 w-3 text-red-700 dark:text-red-400" />{p.blood_group}
                        </span>
                      ) : "—"}
                    </TableCell>
                    <TableCell className="text-sm">
                      {(p.hmo_provider || p.insurance?.hmo_name) ? (
                        <Badge variant="outline" className="text-xs">{p.hmo_provider ?? p.insurance?.hmo_name}</Badge>
                      ) : "—"}
                    </TableCell>
                    <TableCell>
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {search.trim().length === 0 && recentPatients.length === 0 && !loadingRecent && (
        <div className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
          <User className="mx-auto mb-3 h-8 w-8 opacity-30" />
          Search by patient name, MRN, phone, or HMO ID to view records
        </div>
      )}

      {/* Search results table */}
      {patients.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Users className="h-4 w-4" />
              {patients.length} Result{patients.length !== 1 ? "s" : ""}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>MRN</TableHead>
                  <TableHead>Full Name</TableHead>
                  <TableHead>Age</TableHead>
                  <TableHead>Gender</TableHead>
                  <TableHead>Phone</TableHead>
                  <TableHead>HMO</TableHead>
                  <TableHead>Blood Group</TableHead>
                  <TableHead>Registered</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {patients.map(p => (
                  <TableRow
                    key={p.id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => setCprsMrn(p.mrn)}
                  >
                    <TableCell className="font-mono text-xs font-semibold text-primary">{p.mrn}</TableCell>
                    <TableCell className="font-medium">{displayName(p)}</TableCell>
                    <TableCell>{calcAge(p.date_of_birth)}</TableCell>
                    <TableCell>{genderBadge(p.gender)}</TableCell>
                    <TableCell className="text-sm">{p.phone || "—"}</TableCell>
                    <TableCell className="text-sm">{p.hmo_provider || p.insurance?.hmo_name || "—"}</TableCell>
                    <TableCell className="text-sm">
                      {p.blood_group ? (
                        <span className="flex items-center gap-1">
                          <Droplets className="h-3 w-3 text-red-400" />{p.blood_group}
                        </span>
                      ) : "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {p.registration_date ? new Date(p.registration_date).toLocaleDateString() : "—"}
                    </TableCell>
                    <TableCell>
                      <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {search.trim().length >= 2 && !searching && patients.length === 0 && (
        <div className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
          No patients found for "<strong>{search}</strong>"
        </div>
      )}

      {/* ── Patient CPRS slide panel ──────────────────────────────────── */}
      {cprsMrn && (
        <PatientCprsPanel patientMrn={cprsMrn} onClose={() => setCprsMrn(null)} />
      )}

      {/* ── Register Patient Dialog ────────────────────────────────────── */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Register New Patient</DialogTitle>
            <DialogDescription>
              Fill in the patient's details. An MRN will be auto-generated.
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4 py-2">
            <div className="space-y-1">
              <Label>First Name *</Label>
              <Input value={form.first_name} onChange={e => field("first_name", e.target.value)} placeholder="e.g. Emeka" />
            </div>
            <div className="space-y-1">
              <Label>Last Name *</Label>
              <Input value={form.last_name} onChange={e => field("last_name", e.target.value)} placeholder="e.g. Okafor" />
            </div>
            <div className="space-y-1">
              <Label>Date of Birth</Label>
              <Input type="date" value={form.date_of_birth} onChange={e => field("date_of_birth", e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Gender</Label>
              <Select value={form.gender} onValueChange={v => field("gender", v)}>
                <SelectTrigger><SelectValue placeholder="Select gender" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="male">Male</SelectItem>
                  <SelectItem value="female">Female</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Phone</Label>
              <Input value={form.phone} onChange={e => field("phone", e.target.value)} placeholder="+234 801 234 5678" />
            </div>
            <div className="space-y-1">
              <Label>Blood Group</Label>
              <Select value={form.blood_group} onValueChange={v => field("blood_group", v)}>
                <SelectTrigger><SelectValue placeholder="Select blood group" /></SelectTrigger>
                <SelectContent>
                  {BLOOD_TYPES.map(bt => <SelectItem key={bt} value={bt}>{bt}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2 space-y-1">
              <Label>Address</Label>
              <Input value={form.address} onChange={e => field("address", e.target.value)} placeholder="Street, City, State" />
            </div>
            <div className="space-y-1">
              <Label>HMO Provider</Label>
              <Input value={form.hmo_provider} onChange={e => field("hmo_provider", e.target.value)} placeholder="e.g. AXA Mansard" />
            </div>
            <div className="space-y-1">
              <Label>HMO ID</Label>
              <Input value={form.hmo_id} onChange={e => field("hmo_id", e.target.value)} placeholder="Membership number" />
            </div>
            <div className="space-y-1">
              <Label>Next of Kin Name</Label>
              <Input value={form.next_of_kin_name} onChange={e => field("next_of_kin_name", e.target.value)} placeholder="Full name" />
            </div>
            <div className="space-y-1">
              <Label>Next of Kin Phone</Label>
              <Input value={form.next_of_kin_phone} onChange={e => field("next_of_kin_phone", e.target.value)} placeholder="+234 ..." />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button disabled={!canSubmit || registerMut.isPending} onClick={() => registerMut.mutate()}>
              {registerMut.isPending ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Registering…</> : "Register Patient"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </motion.div>
  );
}
