import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

interface MetricTileProps {
  label: string;
  value: string | number | undefined;
  icon: LucideIcon;
  color?: string;
  loading?: boolean;
  sub?: string;
}

export function MetricTile({ label, value, icon: Icon, color = "text-primary", loading, sub }: MetricTileProps) {
  return (
    <Card>
      <CardContent className="pt-4 pb-3">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">{label}</p>
            <div className={cn("text-2xl font-bold mt-0.5 tabular-nums", color)}>
              {loading ? <Skeleton className="h-7 w-14" /> : value ?? "—"}
            </div>
            {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
          </div>
          <Icon className={cn("h-4 w-4 mt-0.5 shrink-0", color)} />
        </div>
      </CardContent>
    </Card>
  );
}
