import { type LucideIcon, Plus, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface CoverSheetWidgetProps {
  title: string;
  icon: LucideIcon;
  count?: number;
  isLoading?: boolean;
  isEmpty?: boolean;
  emptyLabel?: string;
  onAdd?: () => void;
  addLabel?: string;
  onViewAll?: () => void;
  viewAllLabel?: string;
  children?: React.ReactNode;
  className?: string;
}

/**
 * One CPRS cover-sheet card shell — a compact, independently-scrollable
 * widget with a header (icon, title, count badge, optional add action) and
 * a bounded-height body. Shared across all 9 cover-sheet widgets so the page
 * doesn't repeat the same wrapper markup 9 times, and so future cover-sheet
 * work (more widgets are coming) has one place to adjust the shell.
 */
export function CoverSheetWidget({
  title,
  icon: Icon,
  count,
  isLoading,
  isEmpty,
  emptyLabel = "Nothing to show",
  onAdd,
  addLabel = "Add",
  onViewAll,
  viewAllLabel = "View all",
  children,
  className,
}: CoverSheetWidgetProps) {
  return (
    <Card className={cn("flex flex-col", className)}>
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-2 pt-3 px-3">
        <Icon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <CardTitle className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {title}
        </CardTitle>
        {typeof count === "number" && (
          <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4 font-normal">
            {count}
          </Badge>
        )}
        {onAdd && (
          <Button
            size="icon"
            variant="ghost"
            className="ml-auto h-5 w-5 shrink-0"
            onClick={onAdd}
            aria-label={addLabel}
            title={addLabel}
          >
            <Plus className="h-3.5 w-3.5" />
          </Button>
        )}
      </CardHeader>
      <CardContent className="px-3 pb-2 flex-1 flex flex-col min-h-0">
        <div className="max-h-44 overflow-y-auto pr-0.5 flex-1">
          {isLoading ? (
            <div className="flex items-center justify-center py-6 text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            </div>
          ) : isEmpty ? (
            <p className="text-xs text-muted-foreground italic py-3 text-center">{emptyLabel}</p>
          ) : (
            children
          )}
        </div>
        {onViewAll && !isEmpty && !isLoading && (
          <button
            type="button"
            onClick={onViewAll}
            className="mt-1.5 text-[11px] text-primary hover:underline self-start shrink-0"
          >
            {viewAllLabel}
          </button>
        )}
      </CardContent>
    </Card>
  );
}
