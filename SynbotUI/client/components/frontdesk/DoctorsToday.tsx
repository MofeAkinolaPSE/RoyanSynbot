/**
 * Doctors on seat today - the front desk's view of who can see patients now.
 *
 * "On seat" = in a consulting room today, on the work clock, or on today's roster, and not on leave
 * (GET /queue/doctors-today). The desk assigns each arriving doctor a room on the board; at check-in
 * the clerk then picks the doctor the patient is going to, and the room follows. Searching is always
 * possible, and "all doctors" covers a doctor who is in but not yet on the board.
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DoorOpen, Search, Stethoscope, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { CONSULTING_ROOMS } from "./ConsultingRoomBoard";

export type DoctorToday = {
  id: string; full_name: string; department?: string; specialty?: string; room?: string | null;
  on_clock: boolean; rostered: boolean; on_leave: boolean; on_seat: boolean; waiting: number; starts?: string; ends?: string;
};

export function useDoctorsToday() {
  return useQuery({ queryKey: ["doctors-today"], queryFn: () => api.hospital.queue.doctorsToday(), refetchInterval: 60_000 });
}

function status(d: DoctorToday) {
  if (d.on_leave) return { label: "on leave", cls: "text-muted-foreground" };
  if (d.room) return { label: d.room, cls: "text-primary" };
  if (d.on_clock) return { label: "clocked in", cls: "text-emerald-600" };
  if (d.rostered) return { label: `rostered${d.starts ? ` ${String(d.starts).slice(0, 5)}` : ""}`, cls: "text-sky-600" };
  return { label: "not in today", cls: "text-muted-foreground" };
}

/** The check-in picker: doctors on seat first; search reaches every doctor. */
export function DoctorPicker({ value, onChange }: { value: string; onChange: (d: DoctorToday | null) => void }) {
  const q = useDoctorsToday();
  const [search, setSearch] = useState("");
  const [all, setAll] = useState(false);
  const list: DoctorToday[] = q.data?.doctors ?? [];
  const onSeat = list.filter((d) => d.on_seat);
  const shown = useMemo(() => {
    const base = all || search ? list : onSeat;
    const s = search.trim().toLowerCase();
    return base.filter((d) => !s || `${d.full_name} ${d.department ?? ""} ${d.specialty ?? ""} ${d.room ?? ""}`.toLowerCase().includes(s)).slice(0, 30);
  }, [list, onSeat, all, search]);
  const chosen = list.find((d) => d.id === value);

  if (chosen) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-primary/40 bg-primary/5 px-3 py-2">
        <Stethoscope className="h-4 w-4 text-primary" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{chosen.full_name}</div>
          <div className="text-xs text-muted-foreground">{chosen.room ?? "no room assigned"} · {chosen.waiting} waiting for them today</div>
        </div>
        <Button size="icon" variant="ghost" className="h-7 w-7" aria-label="Change doctor" onClick={() => onChange(null)}><X className="h-3.5 w-3.5" /></Button>
      </div>
    );
  }
  return (
    <div className="space-y-2 rounded-md border p-2.5">
      <div className="flex items-center gap-2">
        <div className="relative flex-1"><Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          <Input className="h-8 pl-8 text-sm" placeholder="Search doctor, specialty or room" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
        <button type="button" onClick={() => setAll((v) => !v)} className={cn("shrink-0 rounded-full border px-2.5 py-1 text-xs", all ? "border-primary text-primary" : "text-muted-foreground")}>
          {all ? "All doctors" : `On seat (${onSeat.length})`}
        </button>
      </div>
      {q.isLoading ? <p className="py-2 text-xs text-muted-foreground">Loading doctors...</p>
        : shown.length === 0 ? (
          <p className="py-2 text-xs text-muted-foreground">
            {onSeat.length === 0 && !all && !search
              ? "No doctor is on seat yet today. Assign rooms on the board as doctors arrive, or search all doctors."
              : "No doctor matches."}
          </p>
        ) : (
          <div className="grid max-h-56 gap-1 overflow-y-auto sm:grid-cols-2">
            {shown.map((d) => {
              const st = status(d);
              return (
                <button key={d.id} type="button" disabled={d.on_leave} onClick={() => onChange(d)}
                        className="flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-left hover:border-primary/50 hover:bg-muted/40 disabled:opacity-50">
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm">{d.full_name}</div>
                    <div className={cn("truncate text-xs", st.cls)}>{st.label}{d.specialty ? <span className="text-muted-foreground"> · {d.specialty}</span> : null}</div>
                  </div>
                  {d.waiting > 0 && <Badge variant="outline" className="shrink-0 text-xs">{d.waiting}</Badge>}
                </button>
              );
            })}
          </div>
        )}
    </div>
  );
}

/** Today's board: which doctor is in which consulting room. Assigning a doctor puts them on seat. */
export function RoomBoard() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const q = useDoctorsToday();
  const [picking, setPicking] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const list: DoctorToday[] = q.data?.doctors ?? [];
  const byRoom = new Map(list.filter((d) => d.room).map((d) => [String(d.room).toLowerCase(), d]));
  const rooms = q.data ? Array.from(new Set([...CONSULTING_ROOMS, ...list.filter((d) => d.room).map((d) => d.room as string)])) : CONSULTING_ROOMS;
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["doctors-today"] }); void qc.invalidateQueries({ queryKey: ["room-assignments"] }); };
  const assignments = useQuery({ queryKey: ["room-assignments"], queryFn: () => api.hospital.queue.listRoomAssignments() });
  const idFor = (room: string) => (assignments.data?.assignments ?? []).find((a: any) => String(a.room).toLowerCase() === room.toLowerCase())?.id;

  const assign = useMutation({
    mutationFn: (p: { doctor_id: string; room: string }) => api.hospital.queue.assignRoom(p),
    onSuccess: () => { setPicking(null); setSearch(""); refresh(); toast({ title: "Room assigned - the doctor is now on seat" }); },
    onError: (e: any) => toast({ title: "Could not assign", description: e?.message, variant: "destructive" }),
  });
  const clear = useMutation({
    mutationFn: (id: number) => api.hospital.queue.clearRoomAssignment(id),
    onSuccess: () => { refresh(); toast({ title: "Room freed" }); },
  });
  const candidates = list.filter((d) => !d.room && !d.on_leave && (!search || d.full_name.toLowerCase().includes(search.toLowerCase())))
    .sort((a, b) => Number(b.on_clock || b.rostered) - Number(a.on_clock || a.rostered)).slice(0, 12);

  return (
    <Card>
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-2">
        <DoorOpen className="h-4 w-4 text-muted-foreground" />
        <CardTitle className="text-sm">Consulting rooms today</CardTitle>
        <Badge variant="outline" className="ml-auto text-xs">{q.data?.on_seat ?? 0} doctors on seat</Badge>
      </CardHeader>
      <CardContent className="space-y-1.5 pt-0">
        {rooms.map((room) => {
          const held = byRoom.get(room.toLowerCase());
          return (
            <div key={room} className={cn("rounded-md border px-3 py-2", held ? "border-primary/30 bg-primary/5" : "border-dashed")}>
              <div className="flex items-center gap-2">
                <span className="w-32 shrink-0 text-xs font-medium">{room}</span>
                {held ? (
                  <>
                    <span className="min-w-0 flex-1 truncate text-sm">{held.full_name}{held.waiting ? <span className="text-xs text-muted-foreground"> · {held.waiting} waiting</span> : null}</span>
                    <Button size="icon" variant="ghost" className="h-6 w-6" aria-label={`Free ${room}`} disabled={clear.isPending}
                            onClick={() => { const id = idFor(room); if (id) clear.mutate(id); }}><X className="h-3.5 w-3.5" /></Button>
                  </>
                ) : (
                  <Button variant="ghost" size="sm" className="h-7 flex-1 justify-start text-xs text-muted-foreground"
                          onClick={() => { setPicking(picking === room ? null : room); setSearch(""); }}>Assign a doctor</Button>
                )}
              </div>
              {picking === room && !held && (
                <div className="mt-2 space-y-1">
                  <Input className="h-8 text-sm" autoFocus placeholder="Type the doctor's name" value={search} onChange={(e) => setSearch(e.target.value)} />
                  {candidates.map((d) => (
                    <button key={d.id} type="button" disabled={assign.isPending} onClick={() => assign.mutate({ doctor_id: d.id, room })}
                            className="flex w-full items-center justify-between rounded px-2 py-1 text-left text-sm hover:bg-muted">
                      <span className="truncate">{d.full_name}</span><span className={cn("text-xs", status(d).cls)}>{status(d).label}</span>
                    </button>
                  ))}
                  {candidates.length === 0 && <p className="px-2 text-xs text-muted-foreground">No doctor matches.</p>}
                </div>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
