import { useNavigate } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import { ChevronRight } from "lucide-react";
import { getNavEntryByHref } from "@/lib/nav-access";

export function QuickAccessCard({ href }: { href: string }) {
  const navigate = useNavigate();
  const entry = getNavEntryByHref(href);
  if (!entry) return null;
  const Icon = entry.icon;

  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={() => navigate(href)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") navigate(href); }}
      className="cursor-pointer hover:border-primary/50 hover:shadow-sm transition-all group"
    >
      <CardContent className="flex items-center gap-3 p-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="h-4 w-4" />
        </div>
        <span className="flex-1 min-w-0 text-sm font-medium truncate">{entry.label}</span>
        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground group-hover:translate-x-0.5 transition-transform" />
      </CardContent>
    </Card>
  );
}
