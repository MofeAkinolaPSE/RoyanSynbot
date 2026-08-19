import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { cn } from "@/lib/utils";

interface BackButtonProps {
  /** Where to go if there's no in-app history to go back to (e.g. a bare/bookmarked deep link). */
  fallback: string;
  children?: React.ReactNode;
  iconOnly?: boolean;
  className?: string;
  variant?: "ghost" | "outline";
  size?: "sm" | "default" | "icon";
}

export function BackButton({ fallback, children, iconOnly, className, variant = "ghost", size }: BackButtonProps) {
  const resolvedSize = size ?? (iconOnly ? "icon" : "sm");
  const navigate = useNavigate();

  const handleClick = () => {
    const canGoBack = ((window.history.state as any)?.idx ?? 0) > 0;
    if (canGoBack) navigate(-1);
    else navigate(fallback);
  };

  return (
    <Button variant={variant} size={resolvedSize} className={cn(!iconOnly && "gap-1.5", className)} onClick={handleClick}>
      <ArrowLeft className="h-3.5 w-3.5" />
      {!iconOnly && (children ?? "Back")}
    </Button>
  );
}
