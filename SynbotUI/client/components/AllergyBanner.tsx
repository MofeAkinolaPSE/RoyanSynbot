import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

interface AllergyBannerProps {
  allergies: string[] | null | undefined;
  className?: string;
}

export function AllergyBanner({ allergies, className }: AllergyBannerProps) {
  if (!allergies?.length) return null;

  return (
    <div
      className={cn(
        "flex items-start gap-2.5 rounded-lg border border-red-300 bg-red-50 px-4 py-2.5 text-sm",
        "dark:border-red-800/60 dark:bg-red-950/30",
        className,
      )}
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600 dark:text-red-400" />
      <p className="text-red-800 dark:text-red-300">
        <span className="font-semibold">ALLERGIES: </span>
        {allergies.join(" · ")}
      </p>
    </div>
  );
}
