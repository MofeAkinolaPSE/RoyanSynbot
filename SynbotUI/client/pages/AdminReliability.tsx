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
import { CheckCircle2, XCircle, Clock, Loader2, RefreshCcw, Bug } from "lucide-react";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

type Decision = "approved" | "rejected" | "implemented" | "deferred";

function confidenceBadgeClass(score: number) {
  if (score >= 0.8) return "text-red-700 bg-red-50 border-red-300";
  if (score >= 0.6) return "text-amber-700 bg-amber-50 border-amber-300";
  return "text-slate-600 bg-slate-50 border-slate-300";
}

// ── Proposals tab ───────────────────────────────────────────────────────────
function ProposalsTab() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [reviewing, setReviewing] = useState<any | null>(null);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  const { data, refetch, isFetching } = useQuery({
    queryKey: ["capability-proposals"],
    queryFn: () => api.capability.proposals(100),
    refetchInterval: 60_000,
  });
  const proposals: any[] = data?.proposals ?? [];

  const closeDialog = () => {
    setReviewing(null);
    setDecision(null);
    setNotes("");
  };

  async function submitDecision() {
    if (!reviewing || !decision) return;
    setSaving(true);
    try {
      await api.capability.updateProposalStatus(reviewing.id, { status: decision, notes: notes || undefined });
      toast({ title: `Proposal ${decision}`, description: reviewing.capability_name });
      closeDialog();
      void refetch();
      void qc.invalidateQueries({ queryKey: ["capability-signals"] });
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
          Capability Proposals
          <span className="ml-auto text-xs text-muted-foreground font-normal">{proposals.length} active</span>
          <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCcw className={cn("h-3 w-3", isFetching && "animate-spin")} /> Refresh
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                {["Capability", "Problem", "Confidence", "Status", "Detected", "Actions"].map((h) => (
                  <TableHead key={h} className="text-xs">{h}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {proposals.length === 0 ? (
                <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground text-sm">No active proposals</TableCell></TableRow>
              ) : proposals.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="text-sm font-medium max-w-[220px] truncate" title={p.capability_name}>{p.capability_name}</TableCell>
                  <TableCell className="text-xs text-muted-foreground max-w-[320px] truncate" title={p.problem}>{p.problem}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={cn("text-xs", confidenceBadgeClass(p.confidence_score ?? 0))}>
                      {Math.round((p.confidence_score ?? 0) * 100)}%
                    </Badge>
                  </TableCell>
                  <TableCell><Badge variant="outline" className="text-xs capitalize">{p.status}</Badge></TableCell>
                  <TableCell className="text-xs text-muted-foreground">{new Date(p.created_at).toLocaleString()}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1" onClick={() => { setReviewing(p); setDecision("approved"); }}>
                        <CheckCircle2 className="h-3 w-3" /> Approve
                      </Button>
                      <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1 text-destructive" onClick={() => { setReviewing(p); setDecision("rejected"); }}>
                        <XCircle className="h-3 w-3" /> Reject
                      </Button>
                      <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1" onClick={() => { setReviewing(p); setDecision("deferred"); }}>
                        <Clock className="h-3 w-3" /> Defer
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
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="capitalize">{decision} — {reviewing?.capability_name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">Problem</p>
              <p>{reviewing?.problem}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">Opportunity</p>
              <p>{reviewing?.opportunity}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">Estimated impact</p>
              <p>{reviewing?.estimated_impact}</p>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium">Notes (optional)</label>
              <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Review notes…" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={closeDialog}>Cancel</Button>
            <Button onClick={submitDecision} disabled={saving} variant={decision === "rejected" ? "destructive" : "default"}>
              {saving ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
              Confirm
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ── Raw Signals tab (read-only diagnostic view) ─────────────────────────────
function SignalsTab() {
  const { data, isFetching, refetch } = useQuery({
    queryKey: ["capability-signals"],
    queryFn: () => api.capability.signals(200),
    refetchInterval: 60_000,
  });
  const signals: any[] = data?.signals ?? [];

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          Raw Signals
          <span className="ml-auto text-xs text-muted-foreground font-normal">{signals.length} tracked</span>
          <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCcw className={cn("h-3 w-3", isFetching && "animate-spin")} /> Refresh
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                {["Type", "Component", "Description", "Frequency", "Last Seen"].map((h) => (
                  <TableHead key={h} className="text-xs">{h}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {signals.length === 0 ? (
                <TableRow><TableCell colSpan={5} className="text-center py-8 text-muted-foreground text-sm">No signals recorded</TableCell></TableRow>
              ) : signals.map((s) => (
                <TableRow key={s.id}>
                  <TableCell><Badge variant="outline" className="text-xs">{s.signal_type}</Badge></TableCell>
                  <TableCell className="text-sm">{s.component || "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground max-w-[400px] truncate" title={s.description}>{s.description}</TableCell>
                  <TableCell className="text-sm font-medium">{s.frequency}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{new Date(s.last_seen_at).toLocaleString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────
export default function AdminReliability() {
  const { toast } = useToast();
  const qc = useQueryClient();
  const [discovering, setDiscovering] = useState(false);

  async function runDiscovery() {
    setDiscovering(true);
    try {
      const result = await api.capability.discover();
      toast({ title: "Discovery cycle complete", description: `${result.proposals_created} new proposal(s) created` });
      void qc.invalidateQueries({ queryKey: ["capability-proposals"] });
      void qc.invalidateQueries({ queryKey: ["capability-signals"] });
    } catch (e: any) {
      toast({ title: "Failed", description: e.message, variant: "destructive" });
    } finally {
      setDiscovering(false);
    }
  }

  return (
    <motion.div className="p-6 space-y-6" {...motionTransitions.fadeInUp}>
      <div className="flex items-center gap-2">
        <Bug className="h-5 w-5 text-blue-500" />
        <h1 className="text-lg font-semibold">Reliability Console</h1>
        <span className="ml-4 text-xs text-muted-foreground">
          Log-watcher, digital twin, and maintenance findings for engineering review — not shown to hospital staff.
        </span>
        <Button size="sm" onClick={runDiscovery} disabled={discovering} className="ml-auto gap-1">
          {discovering ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
          Run Discovery Now
        </Button>
      </div>
      <Tabs defaultValue="proposals">
        <TabsList>
          <TabsTrigger value="proposals">Proposals</TabsTrigger>
          <TabsTrigger value="signals">Raw Signals</TabsTrigger>
        </TabsList>
        <TabsContent value="proposals" className="mt-4">
          <ProposalsTab />
        </TabsContent>
        <TabsContent value="signals" className="mt-4">
          <SignalsTab />
        </TabsContent>
      </Tabs>
    </motion.div>
  );
}
