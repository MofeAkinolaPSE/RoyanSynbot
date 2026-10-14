import { cn } from "@/lib/utils";
export { SectionLabel } from "@/components/shared/panel-shared";
// Re-exported so existing call sites keep their import path.
export { DetailRow } from "@/components/shared/panel-shared";

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

