import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { naira } from "@/lib/books-api";

/** Nigerian withholding tax rates in common use (5% supplies / contracts, 10% professional fees, rent...). */
export const WHT_RATES = ["2.5", "5", "7.5", "10", "15", "20"];

/**
 * Withholding tax picked as a rate, not typed: choose the rate and the tax is worked out on the gross being settled
 * (the invoices or bills ticked). "Custom" lets an odd amount be typed. The parent uses the result to set the net
 * cash amount, so nobody adds and subtracts by hand.
 */
export function WhtPicker({ gross, value, onChange, label = "Withholding tax (WHT)" }: {
  gross: number; value: string; onChange: (wht: string) => void; label?: string;
}) {
  const [rate, setRate] = useState<string>(Number(value) > 0 ? "custom" : "");
  useEffect(() => {
    if (!rate) { if (Number(value) !== 0) onChange(""); return; }
    if (rate === "custom") return;
    const w = Math.round(gross * Number(rate)) / 100;
    if (w.toFixed(2) !== Number(value || 0).toFixed(2)) onChange(w > 0 ? w.toFixed(2) : "");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rate, gross]);
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <div className="flex gap-2">
        <select className="h-9 rounded-md border bg-background px-2 text-sm" value={rate} onChange={(e) => setRate(e.target.value)}>
          <option value="">None</option>
          {WHT_RATES.map((r) => <option key={r} value={r}>{r}%</option>)}
          <option value="custom">Other amount…</option>
        </select>
        <Input className="h-9" type="number" value={value} readOnly={rate !== "custom"} placeholder="0"
               onChange={(e) => onChange(e.target.value)} />
      </div>
      {rate && rate !== "custom" && <p className="text-xs text-muted-foreground">{rate}% of {naira(gross)} = {naira(Number(value || 0))}</p>}
    </div>
  );
}
