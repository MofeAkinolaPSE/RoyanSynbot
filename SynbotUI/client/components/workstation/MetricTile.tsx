import { useNavigate } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { ChevronRight, type LucideIcon } from "lucide-react";

interface MetricTileProps {
  label: string;
  value: string | number | undefined;
  icon: LucideIcon;
  color?: string;
  loading?: boolean;
  sub?: string;
  /**
   * Where this number lives in full. A metric the reader cannot open is a
   * dead end — they see "12 waiting" and have to go hunting for the twelve.
   */
  href?: string;
  /** For in-page targets (switch a tab, open a panel) rather than a route. */
  onClick?: () => void;
}

export function MetricTile({
  label, value, icon: Icon, color = "text-primary", loading, sub, href, onClick,
}: MetricTileProps) {
  const navigate = useNavigate();
  const activate = href ? () => navigate(href) : onClick;

  return (
    <Card
      {...(activate
        ? {
            role: "button" as const,
            tabIndex: 0,
            onClick: activate,
            // Keyboard parity with QuickAccessCard: a card that only responds
            // to a mouse is invisible to anyone tabbing through the page.
            onKeyDown: (e: React.KeyboardEvent) => {
              if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(); }
            },
          }
        : {})}
      className={cn(
        activate && "cursor-pointer transition-all hover:border-primary/50 hover:shadow-sm group",
      )}
    >
      <CardContent className="pt-4 pb-3">
        <div className="flex items-start justify-between">
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">{label}</p>
            <div className={cn("text-2xl font-bold mt-0.5 tabular-nums", color)}>
              {loading ? <Skeleton className="h-7 w-14" /> : value ?? "—"}
            </div>
            {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <Icon className={cn("h-4 w-4 mt-0.5", color)} />
            {activate && (
              <ChevronRight className="h-3.5 w-3.5 mt-0.5 text-muted-foreground opacity-0 transition-all group-hover:opacity-100 group-hover:translate-x-0.5" />
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
