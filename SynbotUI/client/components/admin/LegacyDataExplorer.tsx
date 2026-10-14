import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Archive, Loader2, Search, CalendarClock, Database } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";

/**
 * Read-only access to Hope data that has no home of its own.
 *
 * Two things landed in the migration with endpoints but no screen:
 *
 *   royan_hope_reference_archive — 501,227 rows across 105 legacy tables, kept
 *     as jsonb so nothing was lost. It is a lookup of last resort: when someone
 *     asks "what did Hope have for X", this is where to look.
 *
 *   royan_doctor_schedule_blocks — 749 availability blocks from 2014-2016.
 *     Deliberately NOT presented as a live timetable: the dates are a decade
 *     old and 9 doctors appear in them. It is reference for rebuilding clinic
 *     hours, not something to schedule against.
 *
 * Read-only on purpose. This is the record of what the old system held; editing
 * it would make it something else.
 */
export function LegacyDataExplorer() {
  const [table, setTable] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const directory = useQuery({
    queryKey: ["hope-archive-directory"],
    queryFn: () => api.hospital.clinical.hopeArchive(),
  });

  const rows = useQuery({
    queryKey: ["hope-archive-rows", table],
    queryFn: () => api.hospital.clinical.hopeArchive(table!, 50),
    enabled: !!table,
  });

  const schedule = useQuery({
    queryKey: ["doctor-schedule"],
    queryFn: () => api.hospital.clinical.doctorSchedule(),
  });

  const tables: any[] = directory.data?.source_tables ?? [];
  const shown = tables.filter((t) =>
    !filter || String(t.source_table).toLowerCase().includes(filter.toLowerCase()),
  );
  const blocks: any[] = schedule.data?.blocks ?? [];

  return (
    <Card>
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-2">
        <Database className="h-4 w-4 text-muted-foreground" />
        <CardTitle className="text-sm font-semibold">Legacy data (read-only)</CardTitle>
      </CardHeader>

      <CardContent>
        <Tabs defaultValue="archive">
          <TabsList className="mb-3 h-auto flex-wrap border border-border bg-muted">
            <TabsTrigger value="archive">
              Hope archive{tables.length ? ` (${tables.length} tables)` : ""}
            </TabsTrigger>
            <TabsTrigger value="schedule">
              Doctor availability{blocks.length ? ` (${blocks.length})` : ""}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="archive" className="mt-0 space-y-2">
            <p className="text-xs text-muted-foreground">
              Everything from the old system that has no dedicated screen — kept
              verbatim so nothing was lost in the migration. Use it to answer
              "what did Hope hold for this?".
            </p>

            {!table ? (
              <>
                <div className="relative">
                  <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={filter} onChange={(e) => setFilter(e.target.value)}
                    placeholder="Find a table…" className="h-8 pl-8 text-sm"
                  />
                </div>
                {directory.isLoading ? (
                  <div className="flex justify-center py-6">
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  </div>
                ) : (
                  <div className="grid max-h-64 grid-cols-2 gap-1 overflow-y-auto sm:grid-cols-3">
                    {shown.map((t: any) => (
                      <button
                        key={t.source_table}
                        onClick={() => setTable(t.source_table)}
                        className="flex items-center justify-between gap-2 rounded border px-2 py-1 text-left text-xs transition-colors hover:bg-muted/60"
                      >
                        <span className="min-w-0 truncate font-mono">{t.source_table}</span>
                        <span className="shrink-0 text-muted-foreground">
                          {Number(t.rows).toLocaleString()}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="ghost" className="h-7 px-2 text-xs"
                    onClick={() => setTable(null)}>
                    ← All tables
                  </Button>
                  <Badge variant="outline" className="font-mono text-xs">{table}</Badge>
                  <span className="ml-auto text-xs text-muted-foreground">
                    first 50 rows
                  </span>
                </div>
                {rows.isLoading ? (
                  <div className="flex justify-center py-6">
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  </div>
                ) : (
                  <div className="max-h-72 space-y-1 overflow-y-auto">
                    {(rows.data?.rows ?? []).map((r: any, i: number) => (
                      <pre
                        key={i}
                        className="overflow-x-auto rounded border bg-muted/40 p-2 text-xs"
                      >
                        {JSON.stringify(r.payload ?? r, null, 1)}
                      </pre>
                    ))}
                  </div>
                )}
              </>
            )}
          </TabsContent>

          <TabsContent value="schedule" className="mt-0 space-y-2">
            {/* Stated up front: this is not a live timetable and must not be
                mistaken for one. */}
            <p className="flex items-start gap-1.5 rounded-md border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
              <CalendarClock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              Availability blocks from the old system, dated 2014–2016. Historical
              reference for rebuilding clinic hours — not a schedule anyone is
              working to.
            </p>
            {schedule.isLoading ? (
              <div className="flex justify-center py-6">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : blocks.length === 0 ? (
              <p className="py-4 text-center text-xs text-muted-foreground">
                No availability blocks recorded.
              </p>
            ) : (
              <div className="max-h-72 overflow-y-auto">
                <ul className="space-y-1">
                  {blocks.slice(0, 60).map((b: any) => (
                    <li key={b.id} className="flex items-center gap-2 border-b border-border/30 py-1 text-xs last:border-0">
                      <span className="w-24 shrink-0 font-mono text-muted-foreground">
                        Dr ref {b.doctor_ref ?? "—"}
                      </span>
                      <span className="min-w-0 flex-1 truncate">{b.purpose || "—"}</span>
                      <span className="shrink-0 text-muted-foreground">
                        {b.start_time ?? ""}{b.end_time ? `–${b.end_time}` : ""}
                      </span>
                      <span className="w-20 shrink-0 text-right text-muted-foreground">
                        {b.starts_at ? new Date(b.starts_at).toLocaleDateString() : "—"}
                      </span>
                      {b.is_recurring && (
                        <Badge variant="outline" className="shrink-0 text-xs">recurring</Badge>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
