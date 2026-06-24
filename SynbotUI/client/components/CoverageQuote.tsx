import { useQuery } from "@tanstack/react-query";
import { ShieldCheck, ShieldOff, AlertTriangle, Loader2 } from "lucide-react";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";

export interface CoverageQuoteProps {
  patientId: string | number;
  serviceId?: number;
  serviceCode?: string;
  serviceName?: string;
  category?: string;
  amount?: number;
  className?: string;
}

interface QuoteData {
  service: { name: string; category: string; base_price: number };
  insurance: { active: boolean; hmo_name?: string; plan_name?: string };
  gross_amount: number;
  covered_amount: number;
  patient_amount: number;
  coverage_type: string;
  coverage_value: number;
  requires_approval: boolean;
  limit_exceeded: boolean;
  warnings: string[];
}

function naira(n: number) {
  return `₦${n.toLocaleString("en-NG", { minimumFractionDigits: 0 })}`;
}

export function CoverageQuote({
  patientId,
  serviceId,
  serviceCode,
  serviceName,
  category = "misc",
  amount,
  className,
}: CoverageQuoteProps) {
  const pid = Number(patientId);
  const hasService = !!(
    serviceId ||
    (serviceCode && serviceCode.trim()) ||
    (serviceName && serviceName.trim())
  );
  const enabled = !isNaN(pid) && pid > 0 && hasService;

  const { data, isLoading, isError } = useQuery<QuoteData>({
    queryKey: ["coverage-quote", pid, serviceId, serviceCode, serviceName, category, amount],
    queryFn: async () => {
      const res = await api.hospital.coverage.quote({
        patient_id: pid,
        service_id: serviceId,
        service_code: serviceCode || undefined,
        service_name: serviceName || undefined,
        category,
        amount,
      });
      return (res as any).quote as QuoteData;
    },
    enabled,
    staleTime: 60_000,
    retry: false,
  });

  if (!enabled) return null;

  if (isLoading) {
    return (
      <div className={cn("flex items-center gap-2 rounded-lg border border-border/50 bg-muted/20 px-3 py-2 text-xs text-muted-foreground", className)}>
        <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />
        Checking HMO coverage…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className={cn("flex items-center gap-2 rounded-lg border border-border/50 bg-muted/10 px-3 py-2 text-xs text-muted-foreground", className)}>
        <ShieldOff className="h-3.5 w-3.5 shrink-0" />
        Coverage check unavailable
      </div>
    );
  }

  const noInsurance = data.warnings.includes("no_active_insurance");
  const noRule = data.warnings.includes("no_matching_coverage_rule");

  const coverageLabel =
    data.coverage_type === "percent" ? `${data.coverage_value}% covered` :
    data.coverage_type === "fixed"   ? `${naira(data.coverage_value)} fixed` :
    data.coverage_type === "capitation" ? "100% Capitation" :
    "Not covered";

  if (noInsurance) {
    return (
      <div className={cn("flex items-center gap-2 rounded-lg border border-slate-500/20 bg-slate-500/5 px-3 py-2.5 text-xs text-muted-foreground", className)}>
        <ShieldOff className="h-3.5 w-3.5 shrink-0" />
        No active HMO coverage for this patient
      </div>
    );
  }

  if (noRule) {
    return (
      <div className={cn("flex items-center gap-2 rounded-lg border border-yellow-500/20 bg-yellow-500/5 px-3 py-2.5 text-xs text-yellow-400", className)}>
        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
        <span>
          <strong>{data.insurance.hmo_name}</strong> — no coverage rule for this service
        </span>
      </div>
    );
  }

  const borderCls = data.requires_approval
    ? "border-orange-500/30"
    : "border-green-500/30";
  const bgCls = data.requires_approval
    ? "bg-orange-500/5"
    : "bg-green-500/5";
  const headerCls = data.requires_approval
    ? "text-orange-400"
    : "text-green-400";
  const HeaderIcon = data.requires_approval ? AlertTriangle : ShieldCheck;

  return (
    <div className={cn("rounded-lg border overflow-hidden text-xs", borderCls, bgCls, className)}>
      {/* HMO header row */}
      <div className={cn("flex items-center gap-2 px-3 py-2 font-medium", headerCls)}>
        <HeaderIcon className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate">
          {data.insurance.hmo_name}
          {data.insurance.plan_name ? ` · ${data.insurance.plan_name}` : ""}
        </span>
        <span className="ml-auto shrink-0">{coverageLabel}</span>
      </div>

      {/* HMO / Patient split */}
      <div className="grid grid-cols-2 divide-x divide-border/50 border-t border-border/50">
        <div className="px-3 py-2 text-center">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">HMO Pays</p>
          <p className="font-semibold text-green-400">{naira(data.covered_amount)}</p>
        </div>
        <div className="px-3 py-2 text-center">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Patient Pays</p>
          <p className={cn("font-semibold", data.patient_amount > 0 ? "text-foreground" : "text-green-400")}>
            {naira(data.patient_amount)}
          </p>
        </div>
      </div>

      {/* Approval warning */}
      {data.requires_approval && (
        <div className="border-t border-orange-500/30 px-3 py-2 text-orange-300">
          Pre-authorization required — obtain HMO approval code before proceeding
        </div>
      )}

      {/* Limit warning */}
      {data.limit_exceeded && !data.requires_approval && (
        <div className="border-t border-yellow-500/30 px-3 py-2 text-yellow-300">
          Coverage limit applied — patient co-pay reflects the cap
        </div>
      )}
    </div>
  );
}
