import { AlertTriangle, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface InlineWarningProps {
  message: string;
  severity?: "warning" | "critical";
  className?: string;
}

export function InlineWarning({ message, severity = "warning", className }: InlineWarningProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium",
        severity === "critical"
          ? "bg-destructive/10 text-destructive border border-destructive/20"
          : "bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border border-yellow-500/20",
        className,
      )}
    >
      {severity === "critical" ? (
        <AlertCircle className="h-3 w-3 shrink-0" />
      ) : (
        <AlertTriangle className="h-3 w-3 shrink-0" />
      )}
      {message}
    </span>
  );
}
