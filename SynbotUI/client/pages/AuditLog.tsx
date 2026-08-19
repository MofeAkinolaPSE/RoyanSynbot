import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { ClipboardList, RefreshCw, Loader2, Search } from "lucide-react";
import { api } from "@/lib/api-client";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";
import { cn } from "@/lib/utils";

const EVENT_CLASS_COLORS: Record<string, string> = {
  security:       "bg-red-500/20 text-red-700 dark:text-red-400 border-red-500/30",
  data_ingestion: "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  identity:       "bg-purple-500/20 text-purple-700 dark:text-purple-400 border-purple-500/30",
  workflow:       "bg-green-500/20 text-green-700 dark:text-green-400 border-green-500/30",
  analytics:      "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
  system:         "bg-slate-500/20 text-slate-700 dark:text-slate-400 border-slate-500/30",
};

function fmtDateTime(ts?: string) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("en-NG", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function AuditLog() {
  const [search, setSearch] = useState("");
  const [eventClass, setEventClass] = useState("all");

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["audit-log"],
    queryFn: () => api.audit.logs(),
    staleTime: 30_000,
    refetchInterval: 120_000,
  });

  const allLogs: any[] = Array.isArray(data) ? data : [];

  const filtered = allLogs.filter(log => {
    const matchClass = eventClass === "all" || log.event_class === eventClass;
    const matchSearch = !search.trim() ||
      (log.event_type ?? "").toLowerCase().includes(search.toLowerCase()) ||
      (log.actor_id ?? "").toLowerCase().includes(search.toLowerCase()) ||
      (log.subject_type ?? "").toLowerCase().includes(search.toLowerCase());
    return matchClass && matchSearch;
  });

  return (
    <motion.div className="space-y-6" {...motionTransitions.fadeInUp}>
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Audit Log</h1>
          <p className="text-sm text-muted-foreground">System-wide activity trail</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refetch()} disabled={isFetching} className="gap-2">
          <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} /> Refresh
        </Button>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Object.entries(
          allLogs.reduce((acc: Record<string, number>, l) => {
            const cls = l.event_class ?? "system";
            acc[cls] = (acc[cls] ?? 0) + 1;
            return acc;
          }, {})
        ).slice(0, 4).map(([cls, count]) => (
          <Card key={cls}>
            <CardContent className="pt-5">
              <p className="text-xs text-muted-foreground capitalize">{cls.replace(/_/g, " ")}</p>
              <p className="text-2xl font-bold">{count}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            className="pl-9 h-8 text-sm"
            placeholder="Search event type, actor, subject..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <Select value={eventClass} onValueChange={setEventClass}>
          <SelectTrigger className="w-40 h-8 text-xs">
            <SelectValue placeholder="All classes" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All classes</SelectItem>
            {Object.keys(EVENT_CLASS_COLORS).map(c => (
              <SelectItem key={c} value={c}>{c.replace(/_/g, " ").replace(/\b\w/g, x => x.toUpperCase())}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-xs text-muted-foreground self-center">{filtered.length} events</span>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead>
                  <TableHead>Event Type</TableHead>
                  <TableHead>Class</TableHead>
                  <TableHead>Actor</TableHead>
                  <TableHead>Subject</TableHead>
                  <TableHead>Outcome</TableHead>
                  <TableHead>Details</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="py-12 text-center text-muted-foreground">
                      <ClipboardList className="mx-auto mb-2 h-6 w-6 opacity-30" />No audit events found
                    </TableCell>
                  </TableRow>
                ) : filtered.map((log: any, idx) => (
                  <TableRow key={log.id ?? idx}>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      {fmtDateTime(log.created_at ?? log.event_time)}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{log.event_type ?? "—"}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className={cn("text-[12px] capitalize", EVENT_CLASS_COLORS[log.event_class ?? "system"] ?? "")}>
                        {(log.event_class ?? "system").replace(/_/g, " ")}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-[120px] truncate">{log.actor_id ?? "—"}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {log.subject_type && <span className="capitalize">{log.subject_type}</span>}
                      {log.subject_id && <span className="font-mono ml-1">#{log.subject_id.toString().slice(0, 8)}</span>}
                      {!log.subject_type && "—"}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={cn("text-[12px]",
                        log.outcome === "success" ? "border-green-500/30 text-green-700 dark:text-green-400 bg-green-500/10" :
                        log.outcome === "failure" ? "border-red-500/30 text-red-700 dark:text-red-400 bg-red-500/10" :
                        "border-slate-500/30 text-slate-700 dark:text-slate-400"
                      )}>
                        {log.outcome ?? "—"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-[160px] truncate">
                      {log.details ? JSON.stringify(log.details).slice(0, 60) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}
