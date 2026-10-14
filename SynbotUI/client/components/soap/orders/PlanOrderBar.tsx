import { useState } from "react";
import {
  FlaskConical, Pill, Scan, ShieldAlert, Syringe, Stethoscope, X, AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { DraftOrder } from "@/lib/soap-gate";
import { OrderDialog, type OrderKind } from "./OrderDialog";

const ORDER_BUTTONS: { kind: OrderKind; label: string; icon: typeof Pill }[] = [
  { kind: "medication", label: "Medication", icon: Pill },
  { kind: "allergy", label: "Allergy", icon: ShieldAlert },
  { kind: "immunization", label: "Immunisation", icon: Syringe },
  { kind: "lab", label: "Lab Orders", icon: FlaskConical },
  { kind: "radiology", label: "Radiology Orders", icon: Scan },
  { kind: "procedure", label: "Procedure", icon: Stethoscope },
];

const KIND_COLORS: Record<OrderKind, string> = {
  medication: "bg-blue-500/15 text-blue-700 dark:text-blue-400 border-blue-500/30",
  allergy: "bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/30",
  immunization: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30",
  lab: "bg-purple-500/15 text-purple-700 dark:text-purple-400 border-purple-500/30",
  radiology: "bg-cyan-500/15 text-cyan-700 dark:text-cyan-400 border-cyan-500/30",
  procedure: "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30",
};

/**
 * The six Plan buttons from Royan's legacy SOAP screen, in the same 2x3
 * arrangement: Medication / Allergy / Add Immunization on the first row,
 * Lab Orders / Radiology Orders / Procedure on the second.
 *
 * Orders are STAGED, not fired on click. They submit only when the note is
 * signed, and the note POSTs first — it is the legal record, and a failed lab
 * POST must never cost the clinician their documentation. Staged orders are
 * also serialised into the plan text (lib/soap-format.ts) because
 * royan_encounter_notes has no order-linkage column and the note has to stand
 * alone as a readable record.
 */
export function PlanOrderBar({
  orders,
  onAdd,
  onRemove,
  patientSex,
  allergies,
  disabled,
}: {
  orders: DraftOrder[];
  onAdd: (order: DraftOrder) => void;
  onRemove: (tempId: string) => void;
  patientSex?: string | null;
  allergies?: string[] | null;
  disabled?: boolean;
}) {
  const [openKind, setOpenKind] = useState<OrderKind | null>(null);

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-3 gap-1.5">
        {ORDER_BUTTONS.map(({ kind, label, icon: Icon }) => (
          <Button
            key={kind}
            type="button"
            variant="outline"
            size="sm"
            disabled={disabled}
            onClick={() => setOpenKind(kind)}
            className="h-7 justify-start gap-1.5 px-2 text-xs"
          >
            <Icon className="h-3 w-3 shrink-0" />
            <span className="truncate">{label}</span>
          </Button>
        ))}
      </div>

      {orders.length > 0 && (
        <div className="space-y-1 rounded-md border bg-muted/20 p-1.5">
          <div className="px-0.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Staged orders ({orders.length}) — submitted when you sign
          </div>
          {orders.map((o) => (
            <div key={o.tempId} className="flex items-center gap-1.5 rounded border bg-background px-1.5 py-1 text-xs">
              <Badge variant="outline" className={cn("shrink-0 text-xs capitalize", KIND_COLORS[o.kind])}>
                {o.kind}
              </Badge>
              <span className="min-w-0 flex-1 truncate">{o.label}</span>
              <button
                type="button"
                aria-label={`Remove ${o.label}`}
                onClick={() => onRemove(o.tempId)}
                className="shrink-0 text-muted-foreground hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {allergies && allergies.length > 0 && openKind === "medication" && (
        <p className="flex items-center gap-1 text-xs text-red-600">
          <AlertTriangle className="h-3 w-3" /> Allergies: {allergies.join(" · ")}
        </p>
      )}

      {openKind && (
        <OrderDialog
          kind={openKind}
          open
          onOpenChange={(v) => !v && setOpenKind(null)}
          patientSex={patientSex}
          allergies={allergies}
          onStage={(o) => {
            onAdd(o);
            setOpenKind(null);
          }}
        />
      )}
    </div>
  );
}
