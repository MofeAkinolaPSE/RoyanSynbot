import { cn } from "@/lib/utils";

export interface HMO {
  id: number;
  name: string;
  code?: string;
  contact_phone?: string;
  contact_email?: string;
  is_active?: boolean;
  notes?: string;
}

export interface Service {
  id: number;
  service_code: string;
  name: string;
  category?: string;
  base_price?: number;
  is_active?: boolean;
}

export interface CoverageRule {
  id: number;
  hmo_id: number;
  service_id: number;
  coverage_type: string;
  coverage_value: number;
  requires_approval: boolean;
  limit_type: string;
  limit_value?: number;
  notes?: string;
}

export interface HMOPlan {
  id: number;
  hmo_id: number;
  name: string;
  plan_code?: string;
  is_active?: boolean;
  notes?: string;
}

// Matches backend COVERAGE_TYPES_ALLOWED / LIMIT_TYPES_ALLOWED (src/constants.py)
// and the royan_coverage_rules DB CHECK constraints exactly — the previous
// frontend vocab ("percentage", "per_year", "lifetime") didn't match either
// and 422'd on every submission using those values.
export const COVERAGE_TYPES = ["percent", "fixed", "none", "capitation"] as const;
export const LIMIT_TYPES = ["none", "per_visit", "per_month"] as const;

export function DetailRow({ label, value, mono = false }: {
  label: string; value?: string | number | null; mono?: boolean;
}) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="flex items-start justify-between gap-3 py-1 border-b border-border/30 last:border-0">
      <span className="text-xs text-muted-foreground shrink-0">{label}</span>
      <span className={cn("text-xs text-right font-medium", mono && "font-mono")}>{value}</span>
    </div>
  );
}

export function SectionLabel({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <span className="text-muted-foreground">{icon}</span>
      <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{label}</span>
    </div>
  );
}
