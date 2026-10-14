/**
 * Hospital calendar (reportGUide.md s10): one month view over the real records - appointments, theatre,
 * audits, equipment servicing, maintenance, drugs expiring, staff leave, stock deliveries, HMO follow-ups.
 * It owns no events of its own. Dragging an entry to another day (or picking a date in its panel) moves
 * the record itself, so this page and the record's own page always agree. Each person sees only the
 * sources their roles open.
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, ChevronLeft, ChevronRight, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/workspace/PageHeader";
import { DetailSheet } from "@/components/workspace/DetailSheet";
import { api } from "@/lib/api-client";
import { fmtDay } from "./ReportComposer";

type Dict = Record<string, any>;
const COLOR: Record<string, string> = {
  appointment: "bg-sky-500", theatre: "bg-violet-500", audit: "bg-indigo-500", equipment: "bg-teal-500", maintenance: "bg-cyan-600",
  expiry: "bg-amber-500", delivery: "bg-emerald-500", leave: "bg-pink-500", follow_up: "bg-orange-500",
};
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export default function HospitalCalendar() {
  const qc = useQueryClient();
  const [month, setMonth] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [open, setOpen] = useState<Dict | null>(null);
  const [drag, setDrag] = useState<Dict | null>(null);
  const [moveTo, setMoveTo] = useState("");

  // the grid runs Monday..Sunday and covers whole weeks
  const start = useMemo(() => { const d = new Date(month); d.setDate(1 - ((d.getDay() + 6) % 7)); return d; }, [month]);
  const days = useMemo(() => Array.from({ length: 42 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d; }), [start]);
  const from = iso(days[0]), to = iso(days[41]);
  const q = useQuery({ queryKey: ["hospital-calendar", from, to], queryFn: () => api.hospitalCalendar.feed(from, to) });
  const sources: Dict[] = q.data?.sources ?? [];
  const byDay = useMemo(() => {
    const m: Record<string, Dict[]> = {};
    for (const e of q.data?.events ?? []) {
      if (hidden.has(e.source)) continue;
      const s = new Date(e.date + "T12:00:00"), end = e.end ? new Date(e.end + "T12:00:00") : s;
      for (let d = new Date(s); d <= end && d <= days[41]; d.setDate(d.getDate() + 1)) (m[iso(d)] ??= []).push(e);
    }
    return m;
  }, [q.data, hidden, days]);

  const move = useMutation({
    mutationFn: ({ e, date }: { e: Dict; date: string }) => api.hospitalCalendar.reschedule(e.source, e.id, date),
    onSuccess: (_r, v) => { toast.success(`Moved to ${fmtDay(v.date)} - the record itself was updated`); setOpen(null); void qc.invalidateQueries({ queryKey: ["hospital-calendar"] }); },
    onError: (err: any) => toast.error(err?.message || "Could not move it"),
  });
  const today = iso(new Date());

  return (
    <div className="flex flex-col gap-4">
      <PageHeader icon={CalendarDays} title="Hospital calendar"
        subtitle="Every entry is a real record - move one and the record moves with it"
        actions={<div className="flex items-center gap-1">
          <Button size="icon" variant="outline" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}><ChevronLeft className="h-4 w-4" /></Button>
          <Button size="sm" variant="outline" onClick={() => { const d = new Date(); setMonth(new Date(d.getFullYear(), d.getMonth(), 1)); }}>Today</Button>
          <Button size="icon" variant="outline" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}><ChevronRight className="h-4 w-4" /></Button>
        </div>} />
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-2 text-lg font-semibold">{month.toLocaleDateString("en-GB", { month: "long", year: "numeric" })}</span>
        {sources.map((s) => (
          <button key={s.key} onClick={() => setHidden((h) => { const n = new Set(h); n.has(s.key) ? n.delete(s.key) : n.add(s.key); return n; })}
                  className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs ${hidden.has(s.key) ? "opacity-40" : ""}`}>
            <span className={`h-2 w-2 rounded-full ${COLOR[s.key] ?? "bg-slate-400"}`} />{s.label}
          </button>
        ))}
        {q.isFetching && <span className="text-xs text-muted-foreground">loading...</span>}
      </div>
      {q.error && <p className="text-sm text-destructive">{(q.error as any)?.message}</p>}
      <div className="overflow-x-auto rounded-xl border bg-card">
        <div className="grid min-w-[720px] grid-cols-7 border-b text-xs font-medium text-muted-foreground">
          {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <div key={d} className="px-2 py-1.5">{d}</div>)}
        </div>
        <div className="grid min-w-[720px] grid-cols-7">
          {days.map((d) => {
            const k = iso(d);
            const ev = byDay[k] ?? [];
            const inMonth = d.getMonth() === month.getMonth();
            return (
              <div key={k}
                   onDragOver={(e) => { if (drag) e.preventDefault(); }}
                   onDrop={(e) => { e.preventDefault(); if (drag && k !== drag.date) move.mutate({ e: drag, date: k }); setDrag(null); }}
                   className={`min-h-[104px] border-b border-r p-1 ${inMonth ? "" : "bg-muted/30"} ${k < today ? "" : ""}`}>
                <div className={`mb-1 text-right text-xs ${k === today ? "font-bold text-primary" : inMonth ? "" : "text-muted-foreground"}`}>{d.getDate()}</div>
                <div className="space-y-0.5">
                  {ev.slice(0, 4).map((e) => (
                    <button key={e.key + k} draggable={e.movable && k === e.date} onDragStart={() => setDrag(e)} onDragEnd={() => setDrag(null)}
                            onClick={() => { setOpen(e); setMoveTo(e.date); }}
                            className={`flex w-full items-center gap-1 truncate rounded px-1 py-0.5 text-left text-xs hover:bg-muted ${e.tone === "danger" ? "text-red-600" : ""} ${e.movable ? "cursor-grab" : ""}`}
                            title={`${e.title}${e.detail ? " - " + e.detail : ""}`}>
                      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${COLOR[e.source] ?? "bg-slate-400"}`} />
                      {e.time && <span className="text-muted-foreground">{e.time}</span>}<span className="truncate">{e.title}</span>
                    </button>
                  ))}
                  {ev.length > 4 && <button className="px-1 text-xs text-primary hover:underline" onClick={() => setOpen({ day: k, list: ev })}>+{ev.length - 4} more</button>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <p className="text-xs text-muted-foreground">Audits, equipment servicing, maintenance jobs, stock deliveries and HMO follow-ups can be dragged to another day. Appointments, theatre and leave are changed on their own pages.</p>

      <DetailSheet open={!!open} onOpenChange={(o) => !o && setOpen(null)} title={open?.list ? fmtDay(open.day) : open?.title ?? ""} icon={CalendarDays}
        description={open?.list ? `${open.list.length} entries` : open ? `${sources.find((s) => s.key === open.source)?.label ?? open.source} · ${fmtDay(open.date)}${open.end && open.end !== open.date ? ` to ${fmtDay(open.end)}` : ""}` : undefined}>
        {open?.list ? (
          <ul className="divide-y">{open.list.map((e: Dict) => (
            <li key={e.key}><button className="w-full py-2 text-left text-sm hover:text-primary" onClick={() => { setOpen(e); setMoveTo(e.date); }}>
              <span className={`mr-2 inline-block h-2 w-2 rounded-full ${COLOR[e.source]}`} />{e.time ? `${e.time} ` : ""}{e.title}</button></li>
          ))}</ul>
        ) : open && (
          <div className="space-y-4 text-sm">
            {open.detail && <p>{open.detail}</p>}
            {open.status && <p className="text-muted-foreground">Status: {String(open.status).replace(/_/g, " ")}</p>}
            {open.link && <Link to={open.link} className="inline-flex items-center gap-1 text-primary hover:underline">Open the record <ExternalLink className="h-3.5 w-3.5" /></Link>}
            {open.movable && (
              <div className="space-y-1.5 rounded-lg border p-3">
                <Label>Move to</Label>
                <div className="flex gap-2">
                  <Input type="date" min={today} value={moveTo} onChange={(e) => setMoveTo(e.target.value)} />
                  <Button disabled={!moveTo || moveTo === open.date || move.isPending} onClick={() => move.mutate({ e: open, date: moveTo })}>Move</Button>
                </div>
                <p className="text-xs text-muted-foreground">This changes the date on the record itself.</p>
              </div>
            )}
          </div>
        )}
      </DetailSheet>
    </div>
  );
}
