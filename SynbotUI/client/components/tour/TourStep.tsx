import { motion } from "framer-motion";
import type { TourStep as TourStepType } from "@/lib/tour-config";

export function TourStepContent({ step, index, total }: { step: TourStepType; index: number; total: number }) {
  const Icon = step.icon;
  return (
    <motion.div
      key={step.href}
      initial={{ opacity: 0, x: 12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-3"
    >
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Step {index + 1} of {total}
          </p>
          <p className="text-base font-semibold">{step.label}</p>
        </div>
      </div>
      <p className="text-sm text-muted-foreground">{step.description}</p>
    </motion.div>
  );
}
