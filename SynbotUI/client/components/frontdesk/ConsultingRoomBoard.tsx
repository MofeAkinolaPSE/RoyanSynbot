import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { DoorOpen, Loader2, X, UserCog } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

/**
 * Which doctor is in which consulting room today.
 *
 * Asked for: "once the doctor registers and signs up, they are assigned a room
 * by the front desk... the front desk wants that ability to designate what
 * consulting rooms belong to a particular doctor on the ground."
 *
 * Assignment is per DAY. Room allocation follows the shift rota, so yesterday's
 * arrangement must not silently apply this morning — the board starts empty each
 * day rather than showing a stale allocation as if it were current.
 */

/** Named in full so ward rooms (Room101, Room103) can never be confused. */
export const CONSULTING_ROOMS = [
  "Consulting Room 1",
  "Consulting Room 2",
  "Consulting Room 3",
  "Consulting Room 4",
  "Consulting Room 5",
];

export function ConsultingRoomBoard() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [pendingRoom, setPendingRoom] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["room-assignments"],
    queryFn: () => api.hospital.queue.listRoomAssignments(),
    refetchInterval: 60_000,
  });
  const assignments: any[] = data?.assignments ?? [];

  const { data: staffData } = useQuery({
    queryKey: ["staff-directory"],
    queryFn: () => api.staff.list(),
    staleTime: 5 * 60_000,
  });
  const doctors: any[] = (Array.isArray(staffData) ? staffData : []).filter(
    (x: any) => x.role === "doctor",
  );

  const assignMut = useMutation({
    mutationFn: (p: { doctor_id: string; room: string }) => api.hospital.queue.assignRoom(p),
    onSuccess: () => {
      setPendingRoom(null);
      void qc.invalidateQueries({ queryKey: ["room-assignments"] });
      toast({ title: "Room assigned" });
    },
    onError: (e: any) =>
      toast({ title: "Could not assign", description: e?.message, variant: "destructive" }),
  });

  const clearMut = useMutation({
    mutationFn: (id: number) => api.hospital.queue.clearRoomAssignment(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["room-assignments"] });
      toast({ title: "Room freed" });
    },
  });

  const byRoom = new Map(assignments.map((a) => [String(a.room).toLowerCase(), a]));

  return (
    <Card>
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-2">
        <DoorOpen className="h-4 w-4 text-muted-foreground" />
        <CardTitle className="text-sm">Consulting rooms today</CardTitle>
        {assignments.length > 0 && (
          <Badge variant="outline" className="text-xs">{assignments.length} assigned</Badge>
        )}
      </CardHeader>

      <CardContent className="space-y-2 pt-0">
        {isLoading ? (
          <div className="flex justify-center py-6">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : (
          CONSULTING_ROOMS.map((room) => {
            const held = byRoom.get(room.toLowerCase());
            const isPending = pendingRoom === room;
            return (
              <div
                key={room}
                className={cn(
                  "flex items-center gap-2 rounded-md border px-3 py-2",
                  held ? "border-primary/30 bg-primary/5" : "border-dashed",
                )}
              >
                <span className="w-[130px] shrink-0 text-xs font-medium">{room}</span>

                {held ? (
                  <>
                    <span className="min-w-0 flex-1 truncate text-sm">
                      {held.doctor_name ?? "Assigned"}
                    </span>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-6 w-6 shrink-0"
                      aria-label={`Free ${room}`}
                      onClick={() => clearMut.mutate(held.id)}
                      disabled={clearMut.isPending}
                    >
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  </>
                ) : isPending ? (
                  <Select
                    onValueChange={(v) => assignMut.mutate({ doctor_id: v, room })}
                    disabled={assignMut.isPending}
                  >
                    <SelectTrigger className="h-7 flex-1 text-xs">
                      <SelectValue placeholder="Choose a doctor…" />
                    </SelectTrigger>
                    <SelectContent>
                      {doctors.length === 0 ? (
                        <div className="px-2 py-3 text-center text-xs text-muted-foreground">
                          No doctors on the staff register
                        </div>
                      ) : (
                        doctors.map((d: any) => (
                          <SelectItem key={d.id} value={d.id}>
                            {d.full_name}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 flex-1 justify-start gap-1.5 text-xs text-muted-foreground"
                    onClick={() => setPendingRoom(room)}
                  >
                    <UserCog className="h-3.5 w-3.5" /> Assign a doctor
                  </Button>
                )}
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}
