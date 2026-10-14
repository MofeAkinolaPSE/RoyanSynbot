import type { LucideIcon } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

/**
 * Workspace standard — the one side-panel primitive (Modal/Panel
 * Priority: inline > side panel > modal dialog > new page). Standardizes
 * the width/scroll convention already used correctly once in this app
 * (SalesCRM.tsx's "Pre-call Intelligence Brief").
 */
export function DetailSheet({
  open,
  onOpenChange,
  title,
  description,
  icon: Icon,
  footer,
  children,
  size = "narrow",
}: {
  /** wide: more than half the screen (about two-thirds of a laptop) so tables show without sideways scrolling -
   *  every Roy Books panel; narrow (the default elsewhere): short forms */
  size?: "wide" | "narrow";
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  icon?: LucideIcon;
  footer?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className={`w-full overflow-y-auto sm:max-w-none ${size === "narrow" ? "sm:w-[50vw] sm:min-w-[600px]" : "sm:w-[92vw] lg:w-[68vw] sm:min-w-[720px] 2xl:max-w-[1500px]"}`}>
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            {Icon && <Icon className="h-5 w-5 text-primary" />}
            {title}
          </SheetTitle>
          {description && <SheetDescription>{description}</SheetDescription>}
        </SheetHeader>
        <div className="mt-4 space-y-4" data-books>{children}</div>
        {footer && <SheetFooter className="mt-6">{footer}</SheetFooter>}
      </SheetContent>
    </Sheet>
  );
}
