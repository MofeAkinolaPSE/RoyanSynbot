import { useQuery } from "@tanstack/react-query";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api-client";

interface StaffPickerProps {
  value: string;
  onChange: (staffId: string, staff: any) => void;
  placeholder?: string;
}

// A <Select>, not a debounced search picker — GET /staff returns the whole
// active roster in one shot (a handful of rows in practice), unlike the
// thousands-row patient directory the search-picker pattern elsewhere this
// session was built for.
export function StaffPicker({ value, onChange, placeholder = "Select staff member" }: StaffPickerProps) {
  const { data } = useQuery({
    queryKey: ["hr-staff-list"],
    queryFn: () => api.staff.list(),
    staleTime: 60_000,
  });
  const staff: any[] = (Array.isArray(data) ? data : []).filter((s: any) => s.is_active !== false);

  return (
    <Select value={value} onValueChange={v => onChange(v, staff.find(s => s.id === v))}>
      <SelectTrigger className="bg-background border-border text-foreground h-8 text-sm">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent className="bg-popover border-border">
        {staff.map((s: any) => (
          <SelectItem key={s.id} value={s.id}>
            {s.full_name}{s.designation ? ` (${s.designation})` : ""}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
