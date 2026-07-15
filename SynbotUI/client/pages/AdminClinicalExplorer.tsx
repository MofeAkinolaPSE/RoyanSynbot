import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Tabs, TabsContent, TabsList, TabsTrigger,
} from "@/components/ui/tabs";
import {
  Search, Loader2, RefreshCcw, Database, Network, ShieldCheck, ExternalLink,
} from "lucide-react";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

// Sections of the Patient Context Engine payload that carry a Hope
// external_source/external_id pair worth tracing back to source.
const TRACEABLE_SECTIONS: { key: string; label: string }[] = [
  { key: "encounters", label: "Encounters" },
  { key: "lab_orders", label: "Lab Orders" },
  { key: "prescriptions", label: "Prescriptions" },
  { key: "bills", label: "Billing" },
  { key: "radiology", label: "Radiology" },
];

function coverageBadgeClass(pct: number | null) {
  if (pct === null) return "text-slate-500 bg-slate-50 border-slate-300";
  if (pct >= 90) return "text-emerald-700 bg-emerald-50 border-emerald-300";
  if (pct >= 50) return "text-amber-700 bg-amber-50 border-amber-300";
  return "text-red-700 bg-red-50 border-red-300";
}

function coverageDot(pct: number | null) {
  if (pct === null) return "⚪";
  if (pct >= 90) return "🟢";
  if (pct >= 50) return "🟡";
  return "🔴";
}

// ── Patient drill-down dialog ────────────────────────────────────────────────
function PatientDrillDialog({ mrn, onClose }: { mrn: string | null; onClose: () => void }) {
  const { data, isFetching } = useQuery({
    queryKey: ["clinical-explorer-profile", mrn],
    queryFn: () => api.hospital.patients.profile(mrn as string),
    enabled: !!mrn,
  });

  const patient = data ?? {};

  return (
    <Dialog open={!!mrn} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {patient.first_name ? `${patient.first_name} ${patient.last_name}` : mrn}
            <span className="ml-2 text-xs font-normal text-muted-foreground">{mrn}</span>
          </DialogTitle>
        </DialogHeader>
        {isFetching ? (
          <div className="flex items-center justify-center py-10 text-muted-foreground text-sm gap-2">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading patient record…
          </div>
        ) : (
          <div className="space-y-4 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-xs font-medium text-muted-foreground">Hope source</p>
                <p>{patient.external_source ?? "— not from Hope —"}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground">Hope external ID</p>
                <p className="font-mono text-xs">{patient.external_id ?? "—"}</p>
              </div>
            </div>

            {TRACEABLE_SECTIONS.map(({ key, label }) => {
              const rows: any[] = patient[key] ?? [];
              if (!rows.length) return null;
              return (
                <div key={key}>
                  <p className="text-xs font-medium text-muted-foreground mb-1">
                    {label} <span className="text-muted-foreground/70">({rows.length})</span>
                  </p>
                  <div className="overflow-x-auto rounded border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="text-xs">Record</TableHead>
                          <TableHead className="text-xs">Hope source</TableHead>
                          <TableHead className="text-xs">External ID</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {rows.slice(0, 5).map((r: any) => (
                          <TableRow key={r.id}>
                            <TableCell className="text-xs">
                              {r.test_name || r.drug_name || r.bill_number || r.department || r.encounter_type || `#${r.id}`}
                            </TableCell>
                            <TableCell className="text-xs">{r.external_source ?? "—"}</TableCell>
                            <TableCell className="text-xs font-mono">{r.external_id ?? "—"}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ── Search tab ────────────────────────────────────────────────────────────────
function SearchTab({ onSelectMrn }: { onSelectMrn: (mrn: string) => void }) {
  const [query, setQuery] = useState("");
  const [drillMrn, setDrillMrn] = useState<string | null>(null);

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["clinical-explorer-search", query],
    queryFn: () => api.hospital.patients.search(query),
    enabled: query.trim().length >= 2,
  });
  const patients: any[] = data?.patients ?? [];

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          Patient Search
          <span className="ml-auto text-xs text-muted-foreground font-normal">
            {query.trim().length >= 2 ? `${patients.length} match(es)` : "type to search"}
          </span>
        </CardTitle>
        <div className="flex items-center gap-2 pt-1">
          <div className="relative flex-1 max-w-sm">
            <Search className="h-3.5 w-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Name, MRN, phone, or HMO ID…"
              className="pl-7 h-8 text-sm"
            />
          </div>
          <Button size="sm" variant="outline" className="h-8 px-2 text-xs gap-1" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCcw className={cn("h-3 w-3", isFetching && "animate-spin")} /> Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                {["MRN", "Name", "DOB", "Phone", "HMO", "Status", ""].map((h) => (
                  <TableHead key={h} className="text-xs">{h}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.trim().length < 2 ? (
                <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground text-sm">Enter at least 2 characters to search</TableCell></TableRow>
              ) : patients.length === 0 ? (
                <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground text-sm">No matching patients</TableCell></TableRow>
              ) : patients.map((p) => (
                <TableRow key={p.id} className="cursor-pointer hover:bg-muted/40" onClick={() => setDrillMrn(p.mrn)}>
                  <TableCell className="text-xs font-mono">{p.mrn}</TableCell>
                  <TableCell className="text-sm font-medium">{p.first_name} {p.last_name}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{p.date_of_birth ?? "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{p.phone ?? "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{p.hmo_provider ?? "—"}</TableCell>
                  <TableCell><Badge variant="outline" className="text-[10px] capitalize">{p.current_status ?? "—"}</Badge></TableCell>
                  <TableCell>
                    <Button
                      size="sm" variant="ghost" className="h-7 px-2 text-xs gap-1"
                      onClick={(e) => { e.stopPropagation(); onSelectMrn(p.mrn); }}
                    >
                      <Network className="h-3 w-3" /> Tree
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
      <PatientDrillDialog mrn={drillMrn} onClose={() => setDrillMrn(null)} />
    </Card>
  );
}

// ── Relationship Tree tab ────────────────────────────────────────────────────
function RelationshipTreeTab({ mrn, onMrnChange }: { mrn: string; onMrnChange: (v: string) => void }) {
  const [input, setInput] = useState(mrn);

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["clinical-explorer-tree", mrn],
    queryFn: () => api.hospital.patients.relationshipTree(mrn),
    enabled: !!mrn,
  });
  const relations: any[] = data?.relations ?? [];
  const maxCount = Math.max(1, ...relations.map((r) => r.count ?? 0));

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          Relationship Tree
          {mrn ? <span className="ml-auto text-xs text-muted-foreground font-normal">{mrn}</span> : null}
        </CardTitle>
        <div className="flex items-center gap-2 pt-1">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onMrnChange(input.trim())}
            placeholder="Enter MRN…"
            className="h-8 text-sm max-w-xs"
          />
          <Button size="sm" variant="outline" className="h-8 px-2 text-xs" onClick={() => onMrnChange(input.trim())}>
            Load
          </Button>
          {mrn ? (
            <Button size="sm" variant="outline" className="h-8 px-2 text-xs gap-1" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCcw className={cn("h-3 w-3", isFetching && "animate-spin")} /> Refresh
            </Button>
          ) : null}
        </div>
      </CardHeader>
      <CardContent>
        {!mrn ? (
          <p className="text-center py-8 text-muted-foreground text-sm">Search a patient or enter an MRN to see everything linked to them across the clinical graph.</p>
        ) : isFetching ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground text-sm gap-2">
            <Loader2 className="h-4 w-4 animate-spin" /> Walking the FK graph…
          </div>
        ) : relations.length === 0 ? (
          <p className="text-center py-8 text-muted-foreground text-sm">No linked records found for this patient.</p>
        ) : (
          <div className="space-y-2">
            {relations.map((r) => (
              <div key={`${r.table}.${r.column}`} className="flex items-center gap-3">
                <span className="text-xs font-mono w-56 truncate shrink-0" title={r.table}>{r.table}</span>
                <div className="flex-1 h-2 rounded bg-muted overflow-hidden">
                  <div
                    className="h-full bg-blue-500/70 rounded"
                    style={{ width: `${Math.max(4, (r.count / maxCount) * 100)}%` }}
                  />
                </div>
                <span className="text-xs font-medium tabular-nums w-12 text-right">{r.count}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Data Quality tab ─────────────────────────────────────────────────────────
function ScoreTile({ label, value, suffix = "" }: { label: string; value: number | string; suffix?: string }) {
  return (
    <div className="rounded-lg border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold tabular-nums">{value}{suffix}</p>
    </div>
  );
}

function DataQualityTab() {
  const { toast } = useToast();
  const [running, setRunning] = useState(false);
  const { data, isFetching, refetch } = useQuery({
    queryKey: ["clinical-explorer-integrity"],
    queryFn: () => api.audit.integrity(),
  });

  const metrics = data?.metrics ?? {};
  const coverage: any[] = data?.supporting_refs?.find((r: any) => r.type === "relationship_coverage")?.data ?? [];
  const violations: any[] = data?.supporting_refs?.find((r: any) => r.type === "cardinality_violations")?.data ?? [];
  const risks: string[] = data?.risks ?? [];

  async function runAudit() {
    setRunning(true);
    try {
      await api.audit.run();
      toast({ title: "Integrity audit complete" });
      void refetch();
    } catch (e: any) {
      toast({ title: "Audit failed", description: e.message, variant: "destructive" });
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-emerald-600" /> Integrity Score
            <Button size="sm" onClick={runAudit} disabled={running} className="ml-auto h-7 px-2 text-xs gap-1">
              {running ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCcw className="h-3 w-3" />}
              Run Full Audit
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isFetching && !data ? (
            <div className="flex items-center justify-center py-6 text-muted-foreground text-sm gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading latest audit…
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <ScoreTile label="Overall Score" value={metrics.overall_score ?? "—"} />
                <ScoreTile label="Orphan Health" value={metrics.orphan_health ?? "—"} />
                <ScoreTile label="Cardinality Health" value={metrics.cardinality_health ?? "—"} />
                <ScoreTile label="Mean Coverage" value={metrics.mean_relationship_coverage_pct ?? "—"} suffix="%" />
              </div>
              {risks.length > 0 && (
                <div className="space-y-1 mb-2">
                  {risks.map((r, i) => (
                    <p key={i} className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">{r}</p>
                  ))}
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">Relationship Coverage</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  {["", "Referencing Table", "Column", "→ Referenced Table", "Linked / Total", "Coverage"].map((h) => (
                    <TableHead key={h} className="text-xs">{h}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {coverage.length === 0 ? (
                  <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground text-sm">No coverage data yet — run the audit</TableCell></TableRow>
                ) : coverage.map((c: any) => (
                  <TableRow key={`${c.referencing_table}.${c.referencing_column}`}>
                    <TableCell className="text-sm">{coverageDot(c.coverage_pct)}</TableCell>
                    <TableCell className="text-xs font-mono">{c.referencing_table}</TableCell>
                    <TableCell className="text-xs font-mono text-muted-foreground">{c.referencing_column}</TableCell>
                    <TableCell className="text-xs font-mono">{c.referenced_table}</TableCell>
                    <TableCell className="text-xs tabular-nums">{c.linked_rows ?? "—"} / {c.total_rows ?? "—"}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className={cn("text-[10px]", coverageBadgeClass(c.coverage_pct))}>
                        {c.coverage_pct !== null ? `${c.coverage_pct}%` : "n/a"}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">Cardinality Violations</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  {["Table", "Patient/Encounter Mismatches"].map((h) => (
                    <TableHead key={h} className="text-xs">{h}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {violations.length === 0 ? (
                  <TableRow><TableCell colSpan={2} className="text-center py-8 text-muted-foreground text-sm">No cardinality data yet — run the audit</TableCell></TableRow>
                ) : violations.map((v: any) => (
                  <TableRow key={v.table}>
                    <TableCell className="text-xs font-mono">{v.table}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className={cn("text-[10px]", v.patient_encounter_mismatches ? "text-red-700 bg-red-50 border-red-300" : "text-emerald-700 bg-emerald-50 border-emerald-300")}>
                        {v.patient_encounter_mismatches ?? 0}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────
export default function AdminClinicalExplorer() {
  const [activeTab, setActiveTab] = useState("search");
  const [treeMrn, setTreeMrn] = useState("");

  function goToTree(mrn: string) {
    setTreeMrn(mrn);
    setActiveTab("tree");
  }

  return (
    <motion.div className="p-6 space-y-6" {...motionTransitions.fadeInUp}>
      <div className="flex items-center gap-2">
        <Database className="h-5 w-5 text-blue-500" />
        <h1 className="text-lg font-semibold">Clinical Data Explorer</h1>
        <span className="ml-4 text-xs text-muted-foreground flex items-center gap-1">
          <ExternalLink className="h-3 w-3" /> Reconstruct and verify the complete patient story — Synbot Data Intelligence Layer.
        </span>
      </div>
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="search">Search</TabsTrigger>
          <TabsTrigger value="tree">Relationship Tree</TabsTrigger>
          <TabsTrigger value="quality">Data Quality</TabsTrigger>
        </TabsList>
        <TabsContent value="search" className="mt-4">
          <SearchTab onSelectMrn={goToTree} />
        </TabsContent>
        <TabsContent value="tree" className="mt-4">
          <RelationshipTreeTab mrn={treeMrn} onMrnChange={setTreeMrn} />
        </TabsContent>
        <TabsContent value="quality" className="mt-4">
          <DataQualityTab />
        </TabsContent>
      </Tabs>
    </motion.div>
  );
}
