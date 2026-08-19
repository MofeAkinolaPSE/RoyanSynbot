import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { Badge } from "@/components/ui/badge";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { cn } from "@/lib/utils";

const ACCENT = "#14AAF5";

interface DispensingEvent {
  dispensed_at?: string | null;
  quantity_dispensed?: number | null;
}

interface Demand {
  current_window_qty: number;
  prior_window_qty: number;
  direction: "rising" | "falling" | "stable";
  confidence: "estimated" | "no_recent_demand";
}

function bucketByDay(events: DispensingEvent[], days = 30) {
  const buckets = new Map<string, number>();
  const now = new Date();
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    buckets.set(d.toISOString().slice(0, 10), 0);
  }
  for (const e of events) {
    if (!e.dispensed_at) continue;
    const key = e.dispensed_at.slice(0, 10);
    if (buckets.has(key)) {
      buckets.set(key, (buckets.get(key) ?? 0) + Number(e.quantity_dispensed ?? 0));
    }
  }
  return Array.from(buckets.entries()).map(([date, qty]) => ({
    date: date.slice(5), // MM-DD
    qty,
  }));
}

export function DispensingTrendChart({ events, demand }: { events: DispensingEvent[]; demand: Demand }) {
  const data = bucketByDay(events);
  const hasSignal = demand.confidence === "estimated" || events.length > 0;

  const DirIcon = demand.direction === "rising" ? TrendingUp : demand.direction === "falling" ? TrendingDown : Minus;
  const dirColor = demand.direction === "rising" ? "text-blue-700 dark:text-blue-400" : demand.direction === "falling" ? "text-orange-700 dark:text-orange-400" : "text-muted-foreground";

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-muted-foreground">Dispensing activity — last 30 days</p>
        {demand.confidence === "estimated" ? (
          <Badge variant="outline" className={cn("gap-1 text-xs", dirColor)}>
            <DirIcon className="h-3 w-3" />
            {demand.current_window_qty} this window vs {demand.prior_window_qty} prior ({demand.direction})
          </Badge>
        ) : (
          <Badge variant="outline" className="text-xs text-muted-foreground">Insufficient usage history</Badge>
        )}
      </div>

      {hasSignal ? (
        <div className="h-[180px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" opacity={0.5} />
              <XAxis dataKey="date" fontSize={10} tickLine={false} axisLine={false} stroke="hsl(var(--muted-foreground))" interval={4} />
              <YAxis fontSize={10} tickLine={false} axisLine={false} width={28} stroke="hsl(var(--muted-foreground))" allowDecimals={false} />
              <Tooltip
                contentStyle={{ fontSize: "12px", borderRadius: "8px" }}
                formatter={(v: number) => [`${v} units`, "Dispensed"]}
                labelFormatter={(l) => `Day ${l}`}
              />
              <Line
                type="monotone" dataKey="qty" stroke={ACCENT} strokeWidth={2}
                dot={false} activeDot={{ r: 4, fill: ACCENT }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="flex h-[120px] items-center justify-center rounded-md border border-dashed text-xs text-muted-foreground">
          Not enough dispensing history yet to chart a trend.
        </div>
      )}
    </div>
  );
}
