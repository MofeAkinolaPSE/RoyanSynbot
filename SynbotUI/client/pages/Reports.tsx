import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  BarChart3,
  Activity,
  FileDown,
  Users,
  BedDouble,
  DollarSign,
  TrendingUp,
  Building2,
  RefreshCw,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AlertBanner } from "@/components/AlertBanner";
import { api } from "@/lib/api-client";

const motionTransitions = {
  fadeInUp: {
    initial: { opacity: 0, y: 18 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.35, ease: "easeOut" },
  },
};

type Tab = "disease" | "hmis" | "financial" | "demographics" | "beds" | "nhia";

const TABS: { key: Tab; label: string; icon: React.ElementType }[] = [
  { key: "disease",      label: "Disease Burden",     icon: Activity },
  { key: "hmis",         label: "HMIS",               icon: BarChart3 },
  { key: "financial",    label: "Financial",           icon: DollarSign },
  { key: "demographics", label: "Demographics",        icon: Users },
  { key: "beds",         label: "Bed Occupancy",       icon: BedDouble },
  { key: "nhia",         label: "NHIA Export",         icon: FileDown },
];

function KpiCard({
  label,
  value,
  sub,
  icon: Icon,
  color = "blue",
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon: React.ElementType;
  color?: string;
}) {
  const colors: Record<string, string> = {
    blue:   "bg-blue-50 text-blue-600",
    green:  "bg-green-50 text-green-600",
    orange: "bg-orange-50 text-orange-600",
    purple: "bg-purple-50 text-purple-600",
    teal:   "bg-teal-50 text-teal-600",
  };
  return (
    <Card>
      <CardContent className="p-4 flex items-center gap-4">
        <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${colors[color] ?? colors.blue}`}>
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <div className="text-2xl font-bold">{value}</div>
          <div className="text-xs text-muted-foreground">{label}</div>
          {sub && <div className="text-[13px] text-muted-foreground/70">{sub}</div>}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Disease Burden ──────────────────────────────────────────────────────────
function DiseaseBurdenTab() {
  const [startDate, setStartDate] = useState("");
  const [endDate,   setEndDate]   = useState("");

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["reports-disease", startDate, endDate],
    queryFn:  () => api.hospitalReports.diseaseBurden({ start_date: startDate || undefined, end_date: endDate || undefined }),
  });

  const top = data?.top_diagnoses ?? [];
  const max = top[0]?.count ?? 1;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} className="w-40 h-8 text-sm" placeholder="Start date" />
        <Input type="date" value={endDate}   onChange={e => setEndDate(e.target.value)}   className="w-40 h-8 text-sm" placeholder="End date" />
        <Button size="sm" variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isFetching ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-2">
        {top.length === 0 && !isFetching && (
          <p className="text-sm text-muted-foreground py-8 text-center">No diagnosis data found for the selected period.</p>
        )}
        {top.map((d: any, i: number) => (
          <div key={d.icd10_code} className="flex items-center gap-3 rounded-lg border p-3">
            <span className="w-5 text-xs font-bold text-muted-foreground">{i + 1}</span>
            <div className="flex-1">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium">{d.icd10_code}</span>
                <span className="text-xs text-muted-foreground">{d.count} encounters · {d.pct}%</span>
              </div>
              <div className="h-2 rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full rounded-full bg-blue-500 transition-all"
                  style={{ width: `${(d.count / max) * 100}%` }}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        Based on {data?.total_encounters_sampled ?? 0} encounters sampled.
      </p>
    </div>
  );
}

// ── HMIS ────────────────────────────────────────────────────────────────────
function HMISTab() {
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["reports-hmis", month],
    queryFn:  () => api.hospitalReports.hmis(month),
  });

  const enc  = data?.encounters  ?? {};
  const appt = data?.appointments ?? {};
  const beds = data?.beds         ?? {};

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Input type="month" value={month} onChange={e => setMonth(e.target.value)} className="w-40 h-8 text-sm" />
        <Button size="sm" variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isFetching ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="Total Encounters"    value={enc.total ?? 0}     icon={Activity}  color="blue" />
        <KpiCard label="OPD Visits"          value={enc.opd ?? 0}       icon={Users}     color="green" />
        <KpiCard label="IPD Admissions"      value={enc.ipd ?? 0}       icon={BedDouble} color="purple" />
        <KpiCard label="Bed Occupancy"       value={`${beds.occupancy_rate ?? 0}%`} icon={BedDouble} color="orange" sub={`${beds.occupied ?? 0} / ${beds.total ?? 0} beds`} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Encounters by Type</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {Object.entries(enc.by_type ?? {}).map(([k, v]) => (
              <div key={k} className="flex justify-between text-sm">
                <span className="capitalize text-muted-foreground">{k.replace("_", " ")}</span>
                <span className="font-medium">{v as number}</span>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Appointments</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Total</span>
              <span className="font-medium">{appt.total ?? 0}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">No-show Rate</span>
              <Badge variant="outline" className="text-orange-600 border-orange-300">{appt.no_show_rate ?? 0}%</Badge>
            </div>
            {Object.entries(appt.by_status ?? {}).map(([k, v]) => (
              <div key={k} className="flex justify-between text-sm">
                <span className="capitalize text-muted-foreground">{k.replace("_", " ")}</span>
                <span className="font-medium">{v as number}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ── Financial Summary ────────────────────────────────────────────────────────
function FinancialTab() {
  const [startDate, setStartDate] = useState("");
  const [endDate,   setEndDate]   = useState("");

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["reports-financial", startDate, endDate],
    queryFn:  () => api.hospitalReports.financialSummary({ start_date: startDate || undefined, end_date: endDate || undefined }),
  });

  const inv  = data?.invoiced  ?? {};
  const coll = data?.collected ?? {};

  const fmt = (n: number) => "₦" + (n ?? 0).toLocaleString();

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} className="w-40 h-8 text-sm" />
        <Input type="date" value={endDate}   onChange={e => setEndDate(e.target.value)}   className="w-40 h-8 text-sm" />
        <Button size="sm" variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isFetching ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="Total Invoiced"    value={fmt(inv.total ?? 0)}     icon={DollarSign} color="blue" />
        <KpiCard label="Total Collected"   value={fmt(coll.total ?? 0)}    icon={TrendingUp} color="green" />
        <KpiCard label="HMO Portion"       value={fmt(inv.hmo_portion ?? 0)} icon={Building2} color="purple" />
        <KpiCard label="Collection Rate"   value={`${coll.collection_rate ?? 0}%`} icon={BarChart3} color="orange" sub={`${inv.pending_invoices ?? 0} pending invoices`} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">By Invoice Status</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {Object.entries(inv.by_status ?? {}).map(([k, v]) => (
              <div key={k} className="flex justify-between text-sm">
                <span className="capitalize text-muted-foreground">{k}</span>
                <span className="font-medium">{fmt(v as number)}</span>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Collections by Payment Method</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {Object.entries(coll.by_method ?? {}).map(([k, v]) => (
              <div key={k} className="flex justify-between text-sm">
                <span className="capitalize text-muted-foreground">{k}</span>
                <span className="font-medium">{fmt(v as number)}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ── Demographics ─────────────────────────────────────────────────────────────
function DemographicsTab() {
  const { data, isFetching } = useQuery({
    queryKey: ["reports-demographics"],
    queryFn:  () => api.hospitalReports.patientDemographics(),
  });

  const total  = data?.total_patients ?? 0;
  const ageMap = data?.by_age_band ?? {};
  const genMap = data?.by_gender    ?? {};
  const maxAge = Math.max(1, ...Object.values(ageMap) as number[]);

  const genderColors: Record<string, string> = {
    male: "bg-blue-500", female: "bg-pink-500", other: "bg-purple-500", unknown: "bg-gray-400",
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              Age Distribution <Badge variant="outline">{total} patients</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {Object.entries(ageMap)
              .sort((a, b) => String(a[0]).localeCompare(String(b[0])))
              .map(([band, cnt]) => (
              <div key={band} className="flex items-center gap-3">
                <span className="w-12 text-xs text-muted-foreground">{band}</span>
                <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                  <div className="h-full rounded-full bg-blue-500" style={{ width: `${((cnt as number) / maxAge) * 100}%` }} />
                </div>
                <span className="w-8 text-right text-xs font-medium">{cnt as number}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Gender Distribution</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {Object.entries(genMap).map(([gender, cnt]) => (
              <div key={gender} className="flex items-center gap-3">
                <div className={`h-3 w-3 rounded-full ${genderColors[gender] ?? "bg-gray-400"}`} />
                <span className="flex-1 text-sm capitalize">{gender}</span>
                <span className="text-sm font-medium">{cnt as number}</span>
                <span className="text-xs text-muted-foreground">
                  ({total ? Math.round(((cnt as number) / total) * 100) : 0}%)
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ── Bed Occupancy ─────────────────────────────────────────────────────────────
function BedOccupancyTab() {
  const { data, isFetching, refetch } = useQuery({
    queryKey: ["reports-beds"],
    queryFn:  () => api.hospitalReports.bedOccupancy(),
  });

  const wards   = data?.wards ?? [];
  const overall = data?.overall_occupancy_pct ?? 0;
  const totalB  = data?.total_beds ?? 0;
  const totalO  = data?.total_occupied ?? 0;

  const pctColor = (pct: number) =>
    pct >= 90 ? "bg-red-500" : pct >= 70 ? "bg-orange-500" : "bg-green-500";

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <KpiCard label="Total Beds"     value={totalB}           icon={BedDouble} color="blue" />
        <KpiCard label="Occupied"       value={totalO}           icon={BedDouble} color="orange" />
        <KpiCard label="Overall Rate"   value={`${overall}%`}   icon={BarChart3} color={overall >= 90 ? "orange" : "green"} />
      </div>

      <div className="space-y-2">
        {wards.map((w: any) => (
          <div key={w.ward_name} className="flex items-center gap-3 rounded-lg border p-3">
            <div className="flex-1">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium">{w.ward_name}</span>
                <span className="text-xs text-muted-foreground">
                  {w.occupied}/{w.total} · {w.occupancy_pct}%
                </span>
              </div>
              <div className="h-2 rounded-full bg-muted overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${pctColor(w.occupancy_pct)}`}
                  style={{ width: `${w.occupancy_pct}%` }}
                />
              </div>
            </div>
            <Badge variant="outline" className="text-xs capitalize">{w.ward_type}</Badge>
          </div>
        ))}
      </div>

      <Button size="sm" variant="outline" onClick={() => refetch()} disabled={isFetching}>
        <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isFetching ? "animate-spin" : ""}`} /> Refresh
      </Button>
    </div>
  );
}

// ── NHIA Export ──────────────────────────────────────────────────────────────
function NHIATab() {
  const [startDate, setStartDate] = useState("");
  const [endDate,   setEndDate]   = useState("");
  const [fetched,   setFetched]   = useState(false);

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["reports-nhia", startDate, endDate],
    queryFn:  () => api.hospitalReports.nhiaExport({ start_date: startDate || undefined, end_date: endDate || undefined }),
    enabled:  fetched,
  });

  const handleExport = () => {
    setFetched(true);
    setTimeout(() => refetch(), 50);
  };

  const handleDownloadCSV = () => {
    if (!data?.records?.length) return;
    const headers = ["encounter_id","patient_id","encounter_date","encounter_type","diagnoses","total_amount","hmo_amount","patient_copay","billing_status"];
    const rows = data.records.map((r: any) => [
      r.encounter_id, r.patient_id, r.encounter_date, r.encounter_type,
      Array.isArray(r.diagnoses) ? r.diagnoses.join("|") : r.diagnoses,
      r.total_amount, r.hmo_amount, r.patient_copay, r.billing_status,
    ]);
    const csv = [headers, ...rows].map(r => r.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = `nhia_export_${startDate || "all"}_to_${endDate || "all"}.csv`;
    a.click(); URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <Card className="border-blue-200 bg-blue-50/40">
        <CardContent className="pt-4 pb-4">
          <p className="text-sm text-blue-800 font-medium mb-1">NHIA / HMIS Export</p>
          <p className="text-xs text-blue-700">
            Generate encounter + billing data in NHIA-compatible format. Set a date range and click Export to fetch records. Use Download CSV for offline submission.
          </p>
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-2 items-end">
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Start Date</label>
          <Input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} className="w-40 h-8 text-sm" />
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">End Date</label>
          <Input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} className="w-40 h-8 text-sm" />
        </div>
        <Button size="sm" onClick={handleExport} disabled={isFetching}>
          <FileDown className="h-3.5 w-3.5 mr-1.5" /> {isFetching ? "Fetching…" : "Export"}
        </Button>
        {data?.records?.length > 0 && (
          <Button size="sm" variant="outline" onClick={handleDownloadCSV}>
            <FileDown className="h-3.5 w-3.5 mr-1.5" /> Download CSV
          </Button>
        )}
      </div>

      {data && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Badge variant="secondary">{data.record_count} records</Badge>
            <span className="text-xs text-muted-foreground">Generated: {new Date(data.export_generated_at).toLocaleString()}</span>
          </div>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-muted/50">
                  {["Enc. ID","Patient ID","Date","Type","Diagnoses","Total","HMO","Copay","Status"].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-medium text-muted-foreground">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(data.records as any[]).slice(0, 50).map((r: any) => (
                  <tr key={r.encounter_id} className="border-t hover:bg-muted/30">
                    <td className="px-3 py-2">{r.encounter_id}</td>
                    <td className="px-3 py-2">{r.patient_id}</td>
                    <td className="px-3 py-2">{r.encounter_date}</td>
                    <td className="px-3 py-2 capitalize">{r.encounter_type}</td>
                    <td className="px-3 py-2">{Array.isArray(r.diagnoses) ? r.diagnoses.join(", ") : r.diagnoses || "—"}</td>
                    <td className="px-3 py-2">₦{(r.total_amount ?? 0).toLocaleString()}</td>
                    <td className="px-3 py-2">₦{(r.hmo_amount ?? 0).toLocaleString()}</td>
                    <td className="px-3 py-2">₦{(r.patient_copay ?? 0).toLocaleString()}</td>
                    <td className="px-3 py-2"><Badge variant="outline" className="text-[12px]">{r.billing_status}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.records.length > 50 && (
            <p className="text-xs text-muted-foreground">Showing first 50 of {data.record_count} records. Download CSV for full export.</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function Reports() {
  const [tab, setTab] = useState<Tab>("disease");

  return (
    <motion.div {...motionTransitions.fadeInUp} className="space-y-4 p-4 md:p-6">
      <AlertBanner />

      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Reports & Analytics</h1>
          <p className="text-sm text-muted-foreground">Disease burden, HMIS statistics, financial summaries, NHIA export</p>
        </div>
      </div>

      {/* Tab pills */}
      <div className="flex flex-wrap gap-1.5">
        {TABS.map(t => {
          const Icon = t.icon;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                tab === t.key
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {t.label}
            </button>
          );
        })}
      </div>

      <Card>
        <CardContent className="pt-5">
          {tab === "disease"      && <DiseaseBurdenTab />}
          {tab === "hmis"         && <HMISTab />}
          {tab === "financial"    && <FinancialTab />}
          {tab === "demographics" && <DemographicsTab />}
          {tab === "beds"         && <BedOccupancyTab />}
          {tab === "nhia"         && <NHIATab />}
        </CardContent>
      </Card>
    </motion.div>
  );
}
