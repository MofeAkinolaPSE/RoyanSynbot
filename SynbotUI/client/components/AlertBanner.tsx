import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, X } from "lucide-react";
import { api } from "@/lib/api-client";
import { useAuth } from "@/components/AuthProvider";

export const ALERT_ROLES = ["admin", "management", "finance", "ops"];
import { cn } from "@/lib/utils";

interface AlertBannerProps {
  className?: string;
}

export function AlertBanner({ className }: AlertBannerProps) {
  const [dismissed, setDismissed] = useState<Set<string | number>>(new Set());

  const { roles } = useAuth();
  const { data } = useQuery({
    queryKey: ["clinical-alert-banner"],
    queryFn: () => api.dashboard.alerts(),
    enabled: roles.some((r) => ALERT_ROLES.includes(r)),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const alerts = (Array.isArray(data) ? data : []).filter(
    (a: any) =>
      (a.level === "critical" || a.severity === "critical" || a.priority === "high") &&
      !dismissed.has(a.id ?? a.message),
  );

  if (!alerts.length) return null;

  return (
    <div className={cn("space-y-1 mb-4", className)}>
      {alerts.map((alert: any, idx: number) => {
        const key = alert.id ?? alert.message ?? idx;
        return (
          <div
            key={key}
            className="flex items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-2.5"
          >
            <AlertTriangle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
            <p className="flex-1 text-sm font-medium text-destructive">
              {alert.message || alert.title || alert.description || "Critical alert"}
            </p>
            <button
              onClick={() => setDismissed((prev) => new Set([...prev, key]))}
              className="text-destructive/60 hover:text-destructive transition-colors shrink-0"
              aria-label="Dismiss alert"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
