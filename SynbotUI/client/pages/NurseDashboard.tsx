import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  HeartPulse, BedDouble, AlertTriangle, Activity, Droplets,
  ChevronDown, Loader2, RefreshCw, ArrowRight,
} from "lucide-react";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { api } from "@/lib/api-client";
import { AlertBanner } from "@/components/AlertBanner";
import { cn } from "@/lib/utils";

function fmtDate(ts?: string) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("en-NG", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

// ── Ward Row (lazy-loads beds on expand) ──────────────────────────────────────
function WardRow({ ward }: { ward: any }) {
  const [expanded, setExpanded] = useState(false);

  const { data: bedsData, isLoading: bedsLoading } = useQuery({
    queryKey: ["ward-beds-nurse", ward.id],
    queryFn: () => api.hospital.wards.beds(String(ward.id)),
    enabled: expanded,
    staleTime: 60_000,
  });

  const beds: any[] = Array.isArray(bedsData?.beds) ? bedsData.beds : [];
  const total    = ward.total_beds ?? ward.bed_count ?? 0;
  const occupied = ward.occupied_beds ?? beds.filter((b: any) => b.status === "occupied" || b.patient_id).length ?? 0;
  const pct = total > 0 ? Math.round((occupied / total) * 100) : 0;

  return (
    <div className="border-b border-border/50 last:border-0">
      <button
        className="flex w-full items-center justify-between px-4 py-3 hover:bg-muted/40 transition-colors text-left"
        onClick={() => setExpanded(e => !e)}
      >
        <span className="font-medium text-sm">{ward.name ?? ward.ward_name}</span>
        <div className="flex items-center gap-4">
          <div className="w-28 hidden sm:block">
            <Progress value={pct} className="h-1.5" />
          </div>
          <span className="text-xs text-muted-foreground w-24 text-right">
            {occupied}/{total} beds ({pct}%)
          </span>
          <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", expanded && "rotate-180")} />
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-3">
          {bedsLoading ? (
            <div className="flex items-center gap-2 py-2 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" /> Loading beds…
            </div>
          ) : beds.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">No beds configured</p>
          ) : (
            <div className="space-y-1">
              {beds.map((bed: any) => (
                <div key={bed.id} className="flex items-center gap-3 text-xs py-1">
                  <span className="font-mono text-muted-foreground w-10 shrink-0">{bed.bed_number}</span>
                  <span className="flex-1 min-w-0 truncate">
                    {bed.patient_name ?? <span className="text-muted-foreground/50 italic">Empty</span>}
                  </span>
                  <Badge
                    variant="outline"
                    className={cn("text-[10px] shrink-0",
                      bed.status === "occupied" ? "bg-blue-50 text-blue-700 border-blue-300" : "bg-green-50 text-green-700 border-green-300"
                    )}
                  >
                    {bed.status ?? "available"}
                  </Badge>
                  {bed.patient_mrn && (
                    <Button variant="ghost" size="sm" asChild className="h-5 px-1.5 text-[10px] text-primary shrink-0">
                      <Link to={`/hospital/patients/${bed.patient_mrn}`}>CPRS</Link>
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function NurseDashboard() {
  const today = new Date().toLocaleDateString("en-NG", { weekday: "long", year: "numeric", month: "long", day: "numeric" });

  const { data: wardsData, isLoading: wardsLoading, refetch: refetchWards } = useQuery({
    queryKey: ["nurse-wards"],
    queryFn: () => api.hospital.wards.list(),
    refetchInterval: 120_000,
    staleTime: 60_000,
  });
  const wards: any[] = Array.isArray(wardsData?.wards) ? wardsData.wards : Array.isArray(wardsData) ? wardsData : [];

  const { data: inpatientsData, refetch: refetchInpatients } = useQuery({
    queryKey: ["nurse-inpatients"],
    queryFn: () => api.hospital.queue.list({ status: "consulting" }),
    refetchInterval: 120_000,
    staleTime: 60_000,
  });
  const inpatients: any[] = Array.isArray(inpatientsData?.encounters) ? inpatientsData.encounters : [];

  const { data: critLabData, isLoading: critLoading, refetch: refetchCrit } = useQuery({
    queryKey: ["nurse-critical-labs"],
    queryFn: () => api.hospital.lab.critical(),
    refetchInterval: 120_000,
    staleTime: 60_000,
  });
  const critFlags: any[] = Array.isArray(critLabData?.critical_results) ? critLabData.critical_results : [];

  const totalBeds = useMemo(() => wards.reduce((s, w) => s + (w.total_beds ?? w.bed_count ?? 0), 0), [wards]);
  const occupiedBeds = useMemo(() => wards.reduce((s, w) => s + (w.occupied_beds ?? 0), 0), [wards]);
  const availableBeds = totalBeds - occupiedBeds;

  function doRefresh() { void refetchWards(); void refetchInpatients(); void refetchCrit(); }

  return (
    <motion.div className="p-6 space-y-6" {...motionTransitions.fadeInUp}>
      <AlertBanner />

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <HeartPulse className="h-6 w-6 text-blue-600" /> Nurse Dashboard
          </h1>
          <p className="text-sm text-muted-foreground">{today}</p>
        </div>
        <Button variant="outline" size="sm" className="gap-2" onClick={doRefresh}>
          <RefreshCw className="h-3.5 w-3.5" /> Refresh
        </Button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {[
          { label: "Inpatients",    value: inpatients.length, icon: Activity,     color: "text-blue-700",   bg: "bg-blue-50" },
          { label: "Beds Occupied", value: occupiedBeds,      icon: BedDouble,    color: "text-orange-700", bg: "bg-orange-50" },
          { label: "Beds Available",value: availableBeds,     icon: BedDouble,    color: "text-green-700",  bg: "bg-green-50" },
          { label: "Critical Flags",value: critFlags.length,  icon: AlertTriangle,color: critFlags.length > 0 ? "text-red-700" : "text-muted-foreground", bg: critFlags.length > 0 ? "bg-red-50" : "bg-muted/30" },
        ].map(k => (
          <Card key={k.label} className={cn("border-border/60", k.bg)}>
            <CardContent className="pt-4 pb-3">
              <div className="flex justify-between items-start">
                <div>
                  <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">{k.label}</p>
                  <p className={cn("text-2xl font-bold mt-0.5", k.color)}>{k.value}</p>
                </div>
                <k.icon className={cn("w-5 h-5 mt-1 shrink-0", k.color)} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Ward Bed Status */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <BedDouble className="h-4 w-4 text-blue-500" />
            Ward Bed Status
            <span className="ml-auto text-xs text-muted-foreground font-normal">Click a ward to see beds</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {wardsLoading ? (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : wards.length === 0 ? (
            <p className="text-center py-8 text-sm text-muted-foreground">No wards configured</p>
          ) : wards.map((w: any) => <WardRow key={w.id} ward={w} />)
          }
        </CardContent>
      </Card>

      {/* Critical Labs + Fluid Alerts */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">

        {/* Critical Lab Flags */}
        <Card>
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <AlertTriangle className={cn("h-4 w-4", critFlags.length > 0 ? "text-red-500" : "text-muted-foreground")} />
              Critical Lab Flags
              {critFlags.length > 0 && (
                <span className="rounded-full bg-red-100 text-red-700 text-[10px] font-semibold px-2 py-0.5">{critFlags.length}</span>
              )}
            </CardTitle>
            <Button variant="ghost" size="sm" asChild className="h-7 text-xs gap-1">
              <Link to="/hospital/lab"><ArrowRight className="h-3 w-3" /> Lab</Link>
            </Button>
          </CardHeader>
          <CardContent className="p-0">
            {critLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : critFlags.length === 0 ? (
              <p className="px-4 py-6 text-sm text-center text-muted-foreground">No critical flags</p>
            ) : (
              <ul className="divide-y divide-border">
                {critFlags.slice(0, 8).map((f: any) => (
                  <li key={f.id} className="flex items-center justify-between gap-3 px-4 py-2.5">
                    <div>
                      <p className="text-xs font-medium text-red-700">{f.test_name ?? `Result #${f.lab_order_id}`}</p>
                      <p className="text-[10px] text-muted-foreground">
                        Patient #{f.patient_id} · {fmtDate(f.resulted_at)}
                      </p>
                    </div>
                    <Badge variant="outline" className="text-[10px] bg-red-50 text-red-700 border-red-300 shrink-0">CRITICAL</Badge>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Active Inpatients Quick Links */}
        <Card>
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Droplets className="h-4 w-4 text-blue-500" />
              Active Inpatients
            </CardTitle>
            <Button variant="ghost" size="sm" asChild className="h-7 text-xs gap-1">
              <Link to="/hospital/nursing"><ArrowRight className="h-3 w-3" /> Nursing Station</Link>
            </Button>
          </CardHeader>
          <CardContent className="p-0">
            {inpatients.length === 0 ? (
              <p className="px-4 py-6 text-sm text-center text-muted-foreground">No active inpatients</p>
            ) : (
              <ul className="divide-y divide-border">
                {inpatients.slice(0, 8).map((enc: any) => (
                  <li key={enc.id} className="flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-muted/40 transition-colors">
                    <div>
                      <p className="text-xs font-medium">{enc.patient_name ?? enc.mrn ?? `Patient #${enc.patient_id}`}</p>
                      <p className="text-[10px] text-muted-foreground">{enc.department ?? "—"} · {enc.ward_name ?? enc.bed_number ?? ""}</p>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {enc.mrn && (
                        <Button variant="outline" size="sm" asChild className="h-6 px-2 text-xs border-primary/40 text-primary">
                          <Link to={`/hospital/patients/${enc.mrn}`}>CPRS</Link>
                        </Button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Quick Links */}
      <div className="flex flex-wrap gap-3">
        {[
          { label: "Nursing Station", href: "/hospital/nursing", color: "border-primary/40 text-primary" },
          { label: "Wards & Beds",    href: "/hospital/wards",   color: "" },
          { label: "Clinical Queue",  href: "/hospital/queue",   color: "" },
          { label: "Laboratory",      href: "/hospital/lab",     color: "" },
        ].map(l => (
          <Button key={l.href} variant="outline" size="sm" asChild className={cn("gap-1.5", l.color)}>
            <Link to={l.href}>{l.label} <ArrowRight className="h-3 w-3" /></Link>
          </Button>
        ))}
      </div>
    </motion.div>
  );
}
