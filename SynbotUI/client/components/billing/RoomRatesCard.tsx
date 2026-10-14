import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { DoorOpen, Loader2, Check, AlertTriangle, ChevronDown
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Collapsible, CollapsibleContent, CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

/**
 * Nightly rates, at the level that actually bills.
 *
 * The inpatient charge resolves bed → room → ward, most specific first. Since
 * migration 209 gave beds real rooms, 19 of the 21 rooms carry Royan's own
 * prices (Room102 = ₦40,000), so the ROOM rate is what almost every bed uses.
 *
 * WardRatesCard edits the ward, which is only the fallback — an admin could
 * change a ward rate, see the number save, and find the bill unchanged because
 * the room rate still won. This edits the level that decides the charge, and
 * says which rooms are unpriced, because an unpriced room bills a bed-night at
 * nothing.
 */
const naira = (v: any) => `₦${Number(v ?? 0).toLocaleString()}`;

export function RoomRatesCard() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [open, setOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["room-rates"],
    queryFn: () => api.hospital.billing.listRooms(),
  });
  const rooms: any[] = data?.rooms ?? [];
  const unpriced = rooms.filter((r) => !Number(r.daily_rate)).length;

  const save = useMutation({
    mutationFn: ({ id, rate }: { id: number; rate: number }) =>
      api.hospital.billing.setRoomRate(id, rate),
    onSuccess: (_r, v) => {
      setEdits((e) => {
        const next = { ...e };
        delete next[v.id];
        return next;
      });
      void qc.invalidateQueries({ queryKey: ["room-rates"] });
      void qc.invalidateQueries({ queryKey: ["inpatient-queue"] });
      toast({ title: "Room rate saved" });
    },
    onError: (e: any) =>
      toast({ title: "Could not save", description: e?.message, variant: "destructive" }),
  });

  return (
    <Card className={cn(unpriced > 0 && "border-amber-500/40")}>
      <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="w-full text-left">
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-2 hover:bg-muted/30">
        <DoorOpen className="h-4 w-4 text-muted-foreground" />
        <CardTitle className="text-sm font-semibold">Room rates (per night)</CardTitle>
        {unpriced > 0 && (
          <Badge variant="outline" className="border-amber-500/40 bg-amber-500/10 text-xs text-amber-700 dark:text-amber-400">
            {unpriced} unpriced
          </Badge>
        )}
        {isLoading && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
        <ChevronDown className={cn("ml-auto h-4 w-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
      </CardHeader>
      </CollapsibleTrigger>
      <CollapsibleContent>

      <CardContent className="space-y-2">
        {unpriced > 0 && (
          <p className="flex items-start gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            A room with no rate bills each night at ₦0. Set one before a patient is
            admitted to it.
          </p>
        )}

        {rooms.length === 0 && !isLoading ? (
          <p className="py-3 text-center text-xs text-muted-foreground">No rooms configured.</p>
        ) : (
          <ul className="space-y-1">
            {rooms.map((r: any) => {
              const pending = edits[r.id];
              const dirty = pending !== undefined && Number(pending) !== Number(r.daily_rate ?? 0);
              return (
                <li key={r.id} className="flex items-center gap-2 border-b border-border/30 py-1 last:border-0">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium">{r.name}</p>
                    <p className="text-xs text-muted-foreground">{r.ward_name ?? "—"}</p>
                  </div>
                  <span className={cn("w-24 text-right text-xs tabular-nums",
                    !Number(r.daily_rate) && "text-amber-600")}>
                    {Number(r.daily_rate) ? naira(r.daily_rate) : "not set"}
                  </span>
                  <Input
                    type="number" min="0" step="500"
                    className="h-7 w-28 text-xs"
                    placeholder="New rate"
                    value={pending ?? ""}
                    onChange={(e) => setEdits((x) => ({ ...x, [r.id]: e.target.value }))}
                  />
                  <Button
                    size="icon" variant="ghost" className="h-7 w-7"
                    aria-label={`Save rate for ${r.name}`}
                    disabled={!dirty || save.isPending}
                    onClick={() => save.mutate({ id: r.id, rate: Number(pending) })}
                  >
                    <Check className="h-3.5 w-3.5" />
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
      </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}
