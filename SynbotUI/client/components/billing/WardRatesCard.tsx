import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { BedDouble, Loader2, AlertTriangle, Check, ChevronDown
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
 * Nightly bed rate per ward.
 *
 * "we need to make sure that each room has a tariff, so every time a patient is
 * assigned to the room, that is also added to their billing."
 *
 * An unpriced ward bills every admission at zero and nothing else in the app
 * would show it, so unpriced wards are called out here rather than left to be
 * discovered on a discharge invoice.
 *
 * Rates are entered by Royan, not migrated. Hope priced 15 named rooms
 * (Room102, Neonatal Room3...) but the live configuration has 24 beds numbered
 * 1-10 within six wards, with nothing linking the two. Guessing which ward maps
 * to which room price would put a wrong number on a real invoice.
 */
const naira = (v: any) => `₦${Number(v ?? 0).toLocaleString()}`;

export function WardRatesCard() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [open, setOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["ward-rates"],
    queryFn: () => api.hospital.billing.wardRates(),
  });
  const wards: any[] = data?.wards ?? [];
  const unpriced = data?.unpriced ?? 0;

  const save = useMutation({
    mutationFn: ({ id, rate }: { id: number; rate: number }) =>
      api.hospital.billing.setWardRate(id, rate),
    onSuccess: (_r, v) => {
      setEdits((e) => {
        const next = { ...e };
        delete next[v.id];
        return next;
      });
      void qc.invalidateQueries({ queryKey: ["ward-rates"] });
      toast({ title: "Rate saved" });
    },
    onError: (e: any) =>
      toast({ title: "Could not save", description: e?.message, variant: "destructive" }),
  });

  return (
    <Card className={cn(unpriced > 0 && "border-amber-500/40")}>
      <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="w-full text-left">
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-2 hover:bg-muted/30">
        <BedDouble className="h-4 w-4 text-muted-foreground" />
        <CardTitle className="text-sm">Nightly bed rates</CardTitle>
        {unpriced > 0 && (
          <Badge variant="outline" className="border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400">
            {unpriced} unpriced
          </Badge>
        )}
        <ChevronDown className={cn("ml-auto h-4 w-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
      </CardHeader>
      </CollapsibleTrigger>
      <CollapsibleContent>

      <CardContent className="space-y-2 pt-0">
        {unpriced > 0 && (
          <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
            <AlertTriangle className="mr-1 inline h-3.5 w-3.5" />
            An unpriced ward charges nothing for the bed. Admissions there will show
            the nights stayed at ₦0 until a rate is set.
          </p>
        )}

        {isLoading ? (
          <div className="flex justify-center py-6">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : (
          wards.map((w) => {
            const current = Number(w.daily_rate ?? 0);
            const draft = edits[w.id];
            const dirty = draft !== undefined && draft !== String(current);
            return (
              <div key={w.id} className="flex items-center gap-2">
                <span className="w-[150px] shrink-0 truncate text-xs font-medium">{w.name}</span>
                <div className="relative flex-1">
                  <span className="absolute left-2 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">₦</span>
                  <Input
                    type="number" min="0" step="1000"
                    className="h-8 pl-6 text-xs"
                    placeholder="Not set"
                    value={draft ?? (current > 0 ? String(current) : "")}
                    onChange={(e) => setEdits((s) => ({ ...s, [w.id]: e.target.value }))}
                  />
                </div>
                <Button
                  size="icon" variant={dirty ? "default" : "ghost"}
                  className="h-8 w-8 shrink-0"
                  aria-label={`Save rate for ${w.name}`}
                  disabled={!dirty || save.isPending}
                  onClick={() => save.mutate({ id: w.id, rate: Number(draft) })}
                >
                  <Check className="h-3.5 w-3.5" />
                </Button>
              </div>
            );
          })
        )}

        {!isLoading && wards.length > 0 && (
          <p className="pt-1 text-xs text-muted-foreground">
            Charged per night from admission. A bed can override its ward's rate for
            a private room. Current rates: {wards.filter((w) => Number(w.daily_rate) > 0)
              .map((w) => `${w.name} ${naira(w.daily_rate)}`).join(" · ") || "none set"}
          </p>
        )}
      </CardContent>
      </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}
