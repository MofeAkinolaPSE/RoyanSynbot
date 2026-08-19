import { useState } from "react";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ArrowDownUp, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export interface Batch {
  id: number;
  batch_number: string;
  quantity_on_hand: number;
  quantity_received: number;
  unit_cost: number;
  supplier?: string | null;
  location?: string | null;
  received_at?: string | null;
  expiry_date?: string | null;
}

function isExpired(iso?: string | null): boolean {
  if (!iso) return false;
  return new Date(iso).getTime() < Date.now();
}
function isExpiringSoon(iso?: string | null): boolean {
  if (!iso) return false;
  const days = (new Date(iso).getTime() - Date.now()) / 86_400_000;
  return days >= 0 && days <= 30;
}

export function BatchTable({ batches, onAdjust, adjustingId }: {
  batches: Batch[];
  onAdjust: (batch: Batch, adjustment: number, reason: string) => void;
  adjustingId?: number | null;
}) {
  const [drafts, setDrafts] = useState<Record<number, string>>({});

  if (batches.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No batches recorded yet.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="whitespace-nowrap">Batch</TableHead>
            <TableHead className="whitespace-nowrap">On Hand</TableHead>
            <TableHead className="whitespace-nowrap">Expiry</TableHead>
            <TableHead className="whitespace-nowrap">Location</TableHead>
            <TableHead className="whitespace-nowrap">Adjust</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {batches.map((b) => {
            const expired = isExpired(b.expiry_date);
            const soon = !expired && isExpiringSoon(b.expiry_date);
            const draft = drafts[b.id] ?? "";
            const busy = adjustingId === b.id;
            return (
              <TableRow key={b.id} className={cn(b.quantity_on_hand <= 0 && "opacity-50", expired && "bg-red-500/5")}>
                <TableCell className="font-mono text-xs">{b.batch_number}</TableCell>
                <TableCell className="text-sm font-semibold tabular-nums">{b.quantity_on_hand}</TableCell>
                <TableCell className="text-xs">
                  <div className="flex flex-col gap-1">
                    <span className="text-muted-foreground">{b.expiry_date ?? "—"}</span>
                    {expired && <Badge variant="outline" className="w-fit text-red-500 border-red-400/40">Expired</Badge>}
                    {soon && <Badge variant="outline" className="w-fit text-amber-500 border-amber-400/40">Expiring soon</Badge>}
                  </div>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">{b.location ?? "—"}</TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    <Input
                      value={draft}
                      onChange={(e) => setDrafts((d) => ({ ...d, [b.id]: e.target.value }))}
                      placeholder="+/-"
                      className="h-7 w-16 text-xs"
                    />
                    <Button
                      size="sm" variant="ghost" className="h-7 px-2 text-xs gap-1"
                      disabled={!draft.trim() || busy}
                      onClick={() => {
                        const n = Number(draft);
                        if (!Number.isFinite(n) || n === 0) return;
                        onAdjust(b, n, "manual_adjustment");
                        setDrafts((d) => ({ ...d, [b.id]: "" }));
                      }}
                    >
                      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ArrowDownUp className="h-3.5 w-3.5" />}
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
