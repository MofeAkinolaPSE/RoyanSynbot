import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Boxes, Syringe, Package, Truck, TrendingUp, TrendingDown } from "lucide-react";
import { RiskTierBadge } from "@/components/pharmacy/pharmacy-shared";
import { cn } from "@/lib/utils";

const CATEGORY_ICON: Record<string, typeof Boxes> = {
  vaccine: Syringe,
  consumable: Package,
  drug: Boxes,
  other: Boxes,
};

export interface DrugCard {
  formulary_id: number;
  drug_name: string;
  brand_name?: string | null;
  category?: string | null;
  form?: string | null;
  strength?: string | null;
  total_qty_on_hand: number;
  batch_count: number;
  nearest_expiry?: string | null;
  stock_value: number;
  risk_tier: "CRITICAL" | "WARNING" | "MONITOR" | "ADEQUATE";
  stock_coverage_days?: number | null;
  recommended_reorder_qty?: number | null;
  demand_confidence: "estimated" | "no_recent_demand";
  demand_direction: "rising" | "falling" | "stable";
}

function daysUntil(iso?: string | null): number | null {
  if (!iso) return null;
  return Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000);
}

export function DrugInventoryCard({ card, onOpen, onReorder }: {
  card: DrugCard;
  onOpen: (card: DrugCard) => void;
  onReorder: (card: DrugCard) => void;
}) {
  const Icon = CATEGORY_ICON[card.category ?? "drug"] ?? Boxes;
  const expiryDays = daysUntil(card.nearest_expiry);
  const expiryUrgent = expiryDays !== null && expiryDays <= 30;
  const showReorder = card.risk_tier === "CRITICAL" || card.risk_tier === "WARNING";

  return (
    <Card
      className="cursor-pointer transition-colors hover:border-primary/40 hover:bg-muted/30"
      onClick={() => onOpen(card)}
    >
      <CardContent className="pt-4 space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-2 min-w-0">
            <Icon className="h-4 w-4 mt-0.5 shrink-0 text-muted-foreground" />
            <div className="min-w-0">
              <p className="text-sm font-semibold leading-tight truncate">{card.drug_name}</p>
              {(card.form || card.strength) && (
                <p className="text-xs text-muted-foreground truncate">
                  {[card.form, card.strength].filter(Boolean).join(" · ")}
                </p>
              )}
            </div>
          </div>
          <RiskTierBadge tier={card.risk_tier} />
        </div>

        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold tabular-nums">{card.total_qty_on_hand.toLocaleString()}</span>
          <span className="text-xs text-muted-foreground">
            in stock · {card.batch_count} batch{card.batch_count === 1 ? "" : "es"}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {card.nearest_expiry && (
            <Badge variant="outline" className={cn("gap-1", expiryUrgent && "text-amber-500 border-amber-400/40")}>
              Exp {card.nearest_expiry}{expiryDays !== null && expiryDays >= 0 ? ` (${expiryDays}d)` : ""}
            </Badge>
          )}
          {card.demand_confidence === "estimated" && card.demand_direction !== "stable" && (
            <Badge variant="outline" className="gap-1 text-muted-foreground">
              {card.demand_direction === "rising"
                ? <TrendingUp className="h-3 w-3 text-blue-400" />
                : <TrendingDown className="h-3 w-3 text-orange-400" />}
              {card.demand_direction}
            </Badge>
          )}
          {card.demand_confidence === "no_recent_demand" && (
            <Badge variant="outline" className="text-muted-foreground">No recent usage</Badge>
          )}
        </div>

        {showReorder && (
          <Button
            size="sm"
            variant="outline"
            className="w-full gap-1.5 text-xs h-7 border-amber-400/40 text-amber-500 hover:bg-amber-500/10"
            onClick={(e) => { e.stopPropagation(); onReorder(card); }}
          >
            <Truck className="h-3.5 w-3.5" />
            Prompt Reorder{card.recommended_reorder_qty ? ` — ${card.recommended_reorder_qty}` : ""}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
