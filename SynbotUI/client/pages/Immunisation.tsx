import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Syringe, RefreshCw, Search, Loader2, ChevronRight, Plus, UserCheck, X } from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { AlertBanner } from "@/components/AlertBanner";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";

const EMPTY_BABY_FORM = {
  first_name: "", last_name: "", date_of_birth: "", gender: "",
  place_of_birth: "", father_name: "",
};

const STATUS_BADGE: Record<string, string> = {
  overdue:     "bg-red-100 text-red-700 border-red-300",
  due_soon:    "bg-orange-100 text-orange-700 border-orange-300",
  // Distinct from up_to_date on purpose: nothing to action today, but doses
  // remain. Green "Up to Date" on a child with doses still ahead reads as
  // "fully vaccinated" and would stop someone looking further.
  on_schedule: "bg-blue-100 text-blue-700 border-blue-300",
  up_to_date:  "bg-green-100 text-green-700 border-green-300",
  // Deliberately NOT red. "No record" means this hospital has never recorded a
  // dose for this child — most were vaccinated elsewhere, which is normal here.
  // Colouring it like a missed dose sends staff chasing families who have done
  // nothing wrong, and buries the children who genuinely are overdue.
  no_record:   "bg-slate-100 text-slate-700 border-slate-300",
};

const STATUS_LABEL: Record<string, string> = {
  overdue: "Overdue",
  due_soon: "Due Soon",
  on_schedule: "On Schedule",
  up_to_date: "Schedule Complete",
  no_record: "No record on file",
};

function ageFromDob(dob?: string): string {
  if (!dob) return "—";
  const d = new Date(dob);
  const days = Math.floor((Date.now() - d.getTime()) / (24 * 3600 * 1000));
  if (isNaN(days)) return "—";
  if (days < 60) return `${days}d`;
  if (days < 730) return `${Math.floor(days / 30)}mo`;
  return `${Math.floor(days / 365.25)}y`;
}

export default function Immunisation() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { toast } = useToast();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const motherDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  // New Baby dialog state
  const [newBabyOpen, setNewBabyOpen] = useState(false);
  const [motherQuery, setMotherQuery] = useState("");
  const [motherResults, setMotherResults] = useState<any[]>([]);
  const [motherSearching, setMotherSearching] = useState(false);
  const [selectedMother, setSelectedMother] = useState<any | null>(null);
  const [babyForm, setBabyForm] = useState({ ...EMPTY_BABY_FORM });

  const handleSearchChange = (val: string) => {
    setSearchQuery(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedQ(val), 400);
  };

  const handleMotherSearchChange = (val: string) => {
    setMotherQuery(val);
    if (motherDebounceRef.current) clearTimeout(motherDebounceRef.current);
    if (val.trim().length < 2) {
      setMotherResults([]);
      return;
    }
    motherDebounceRef.current = setTimeout(async () => {
      setMotherSearching(true);
      try {
        const res: any = await api.hospital.patients.search(val.trim());
        const rows = Array.isArray(res?.patients) ? res.patients : Array.isArray(res) ? res : [];
        setMotherResults(rows);
      } catch {
        setMotherResults([]);
      } finally {
        setMotherSearching(false);
      }
    }, 400);
  };

  function closeNewBabyDialog() {
    setNewBabyOpen(false);
    setMotherQuery("");
    setMotherResults([]);
    setSelectedMother(null);
    setBabyForm({ ...EMPTY_BABY_FORM });
  }

  const registerBabyMut = useMutation({
    mutationFn: () => api.hospital.mch.registerBaby({
      mother_patient_id: selectedMother?.id,
      first_name: babyForm.first_name.trim(),
      last_name: babyForm.last_name.trim() || undefined,
      date_of_birth: babyForm.date_of_birth,
      gender: babyForm.gender || undefined,
      place_of_birth: babyForm.place_of_birth.trim() || undefined,
      father_name: babyForm.father_name.trim() || undefined,
    }),
    onSuccess: (res: any) => {
      toast({ title: "Baby registered", description: `MRN ${res?.baby?.mrn ?? ""} — linked to ${selectedMother?.first_name} ${selectedMother?.last_name}` });
      closeNewBabyDialog();
      void qc.invalidateQueries({ queryKey: ["immunisation-babies"] });
    },
    onError: (e: any) => toast({ title: "Failed to register baby", description: e.message, variant: "destructive" }),
  });

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["immunisation-babies", debouncedQ, statusFilter],
    queryFn: () => api.hospital.mch.listBabiesRoster({
      search: debouncedQ || undefined,
      status: statusFilter === "all" ? undefined : statusFilter,
    }),
  });
  const babies: any[] = data?.babies ?? [];

  return (
    <motion.div className="p-6 space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-sky-500/20 rounded-lg">
            <Syringe className="w-6 h-6 text-sky-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Immunisation</h1>
            <p className="text-sm text-muted-foreground">Babies currently in the immunisation program — due, overdue, and completed doses</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="border-border" onClick={() => { window.location.hash = "#/hospital/stores?dept=IMMUNISATION"; }}>
            <Syringe className="w-4 h-4 mr-1" /> Vaccine stock
          </Button>
          <Button variant="outline" size="sm" className="border-border" onClick={() => refetch()}>
            <RefreshCw className={cn("w-4 h-4 mr-1", isFetching && "animate-spin")} /> Refresh
          </Button>
          <Button size="sm" className="gap-1.5" onClick={() => setNewBabyOpen(true)}>
            <Plus className="w-4 h-4" /> New Baby
          </Button>
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="relative max-w-sm flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search by baby name or MRN"
            value={searchQuery}
            onChange={e => handleSearchChange(e.target.value)}
            className="pl-9 bg-background border-border text-foreground text-sm"
          />
        </div>
        <Tabs value={statusFilter} onValueChange={setStatusFilter}>
          <TabsList className="bg-muted border border-border">
            <TabsTrigger value="all">All</TabsTrigger>
            <TabsTrigger value="overdue">Overdue</TabsTrigger>
            <TabsTrigger value="no_record">No record</TabsTrigger>
            <TabsTrigger value="due_soon">Due Soon</TabsTrigger>
            <TabsTrigger value="on_schedule">On Schedule</TabsTrigger>
            <TabsTrigger value="up_to_date">Complete</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      <Card className="border-border">
        <CardContent className="pt-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-10 text-muted-foreground">
              <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading babies…
            </div>
          ) : babies.length === 0 ? (
            <div className="text-center py-10 text-sm text-muted-foreground">
              No babies found{debouncedQ ? ` matching "${debouncedQ}"` : ""}.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Baby</TableHead>
                  <TableHead>DOB / Age</TableHead>
                  <TableHead>Mother</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Next Due</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {babies.map(b => (
                  <TableRow
                    key={b.id}
                    className="cursor-pointer hover:bg-muted/40"
                    onClick={() => navigate(`/hospital/immunisation/${b.id}`)}
                  >
                    <TableCell>
                      <div className="font-medium text-foreground">{b.first_name} {b.last_name}</div>
                      <div className="text-xs text-muted-foreground">MRN {b.mrn}</div>
                    </TableCell>
                    <TableCell className="text-sm">
                      <div>{b.date_of_birth || "—"}</div>
                      <div className="text-xs text-muted-foreground">{ageFromDob(b.date_of_birth)}</div>
                    </TableCell>
                    <TableCell className="text-sm">
                      {b.mother_name ? (
                        <button
                          className="text-blue-600 hover:underline"
                          onClick={e => { e.stopPropagation(); navigate(`/hospital/patients/${b.mother_mrn}`); }}
                        >
                          {b.mother_name}
                        </button>
                      ) : "—"}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={STATUS_BADGE[b.overall_status] || ""}>
                        {STATUS_LABEL[b.overall_status] || b.overall_status}
                        {b.overall_status !== "no_record" && b.overdue_count > 0 ? ` (${b.overdue_count})` : ""}
                      </Badge>
                    </TableCell>
                    {/* Missed doses and the next appointment are different facts
                        and now render as different lines. They previously shared
                        one slot, so a missed dose displaced the next due date and
                        the column showed a date in the past under "Next Due". */}
                    <TableCell className="text-sm">
                      {b.oldest_overdue && (
                        <div className="text-red-600 dark:text-red-400">
                          Missed {b.oldest_overdue.vaccine_name}
                          <span className="ml-1 text-xs">
                            ({b.oldest_overdue.days_overdue}d overdue)
                          </span>
                        </div>
                      )}
                      {b.next_due ? (
                        <div className={b.oldest_overdue ? "text-xs text-muted-foreground" : ""}>
                          {b.oldest_overdue && "Next: "}
                          {b.next_due.vaccine_name}
                          <span className="ml-1 text-xs text-muted-foreground">({b.next_due.due_date})</span>
                        </div>
                      ) : !b.oldest_overdue ? "—" : (
                        <div className="text-xs text-muted-foreground">Schedule complete</div>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" onClick={e => { e.stopPropagation(); navigate(`/hospital/immunisation/${b.id}`); }}>
                        View Record <ChevronRight className="w-3.5 h-3.5 ml-1" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* ── New Baby Dialog ─────────────────────────────────────────────── */}
      <Dialog open={newBabyOpen} onOpenChange={o => { if (!o) closeNewBabyDialog(); }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Register New Baby</DialogTitle>
            <DialogDescription>Starts the baby on the immunisation program, always linked to a mother's patient record.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Mother *</Label>
              {selectedMother ? (
                <div className="flex items-center justify-between rounded-md border border-green-500/30 bg-green-500/5 px-3 py-2">
                  <div className="flex items-center gap-2 text-sm">
                    <UserCheck className="h-4 w-4 text-green-500" />
                    <span className="font-medium">{selectedMother.first_name} {selectedMother.last_name}</span>
                    <span className="text-xs text-muted-foreground font-mono">{selectedMother.mrn}</span>
                  </div>
                  <Button size="sm" variant="ghost" className="h-6 px-2" onClick={() => setSelectedMother(null)}>
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ) : (
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    placeholder="Search mother by name or MRN…"
                    value={motherQuery}
                    onChange={e => handleMotherSearchChange(e.target.value)}
                    className="pl-9"
                  />
                  {motherSearching && (
                    <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 animate-spin text-muted-foreground" />
                  )}
                  {motherResults.length > 0 && (
                    <div className="absolute z-10 mt-1 w-full rounded-md border bg-popover shadow-md max-h-48 overflow-y-auto">
                      {motherResults.map((m: any) => (
                        <button
                          key={m.id}
                          className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-muted"
                          onClick={() => { setSelectedMother(m); setMotherResults([]); setMotherQuery(""); }}
                        >
                          <span>{m.first_name} {m.last_name}</span>
                          <span className="text-xs text-muted-foreground font-mono">{m.mrn}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Baby's First Name *</Label>
                <Input value={babyForm.first_name} onChange={e => setBabyForm(f => ({ ...f, first_name: e.target.value }))} placeholder="e.g. Baby" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Last Name</Label>
                <Input value={babyForm.last_name} onChange={e => setBabyForm(f => ({ ...f, last_name: e.target.value }))} placeholder="Defaults to mother's" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Date of Birth *</Label>
                <Input type="date" value={babyForm.date_of_birth} onChange={e => setBabyForm(f => ({ ...f, date_of_birth: e.target.value }))} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Gender</Label>
                <Select value={babyForm.gender} onValueChange={v => setBabyForm(f => ({ ...f, gender: v }))}>
                  <SelectTrigger><SelectValue placeholder="Select…" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="male">Male</SelectItem>
                    <SelectItem value="female">Female</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Place of Birth</Label>
                <Input value={babyForm.place_of_birth} onChange={e => setBabyForm(f => ({ ...f, place_of_birth: e.target.value }))} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Father's Name</Label>
                <Input value={babyForm.father_name} onChange={e => setBabyForm(f => ({ ...f, father_name: e.target.value }))} />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeNewBabyDialog}>Cancel</Button>
            <Button
              disabled={!selectedMother || !babyForm.first_name.trim() || !babyForm.date_of_birth || registerBabyMut.isPending}
              onClick={() => registerBabyMut.mutate()}
            >
              {registerBabyMut.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Register Baby
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
