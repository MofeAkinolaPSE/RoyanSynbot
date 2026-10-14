import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export interface CatalogOption {
  id: string | number;
  label: string;
  sublabel?: string;
  raw?: any;
}

/**
 * Async catalog search on Command + Popover.
 *
 * Replaces the hand-rolled `<Input>` + `<div className="max-h-28 overflow-y-auto">`
 * result lists that were duplicated across the OPD panel (lab search, drug
 * search) and PatientProfile (ICD-10). command.tsx and popover.tsx were already
 * installed and used almost nowhere.
 *
 * Free text remains allowed by default (`allowFreeText`): the catalogs are real
 * but not exhaustive — 211 radiology studies and 112 procedures will not cover
 * every case, and blocking an order because the catalog lacks an entry would
 * make the system worse than the free-text field it replaced.
 */
export function CatalogCombobox({
  value,
  onChange,
  onSelect,
  queryKey,
  fetcher,
  mapResults,
  placeholder = "Search…",
  emptyLabel = "No matches in the catalog",
  minChars = 2,
  allowFreeText = true,
  disabled,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  /** Fired with the full row when a catalog entry is picked. */
  onSelect?: (opt: CatalogOption) => void;
  queryKey: string;
  fetcher: (q: string) => Promise<any>;
  mapResults: (data: any) => CatalogOption[];
  placeholder?: string;
  emptyLabel?: string;
  minChars?: number;
  allowFreeText?: boolean;
  disabled?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const { data, isFetching } = useQuery({
    queryKey: [queryKey, query],
    queryFn: () => fetcher(query),
    enabled: open && query.trim().length >= minChars,
    staleTime: 300_000,
  });

  const options = data ? mapResults(data) : [];

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className={cn("h-9 w-full justify-between font-normal", !value && "text-muted-foreground", className)}
        >
          <span className="truncate">{value || placeholder}</span>
          <ChevronsUpDown className="ml-2 h-3.5 w-3.5 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            placeholder={placeholder}
            value={query}
            onValueChange={(v) => {
              setQuery(v);
              if (allowFreeText) onChange(v);
            }}
          />
          <CommandList>
            {isFetching && (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
              </div>
            )}
            {!isFetching && query.trim().length < minChars && (
              <p className="px-3 py-4 text-xs text-muted-foreground">
                Type at least {minChars} characters to search.
              </p>
            )}
            {!isFetching && query.trim().length >= minChars && options.length === 0 && (
              <CommandEmpty>
                {emptyLabel}
                {allowFreeText && query.trim() && (
                  <span className="mt-1 block text-xs">
                    "{query.trim()}" will be used as typed.
                  </span>
                )}
              </CommandEmpty>
            )}
            {options.length > 0 && (
              <CommandGroup>
                {options.map((o) => (
                  <CommandItem
                    key={o.id}
                    value={String(o.id)}
                    onSelect={() => {
                      onChange(o.label);
                      onSelect?.(o);
                      setOpen(false);
                    }}
                    className="text-xs"
                  >
                    <Check className={cn("mr-2 h-3.5 w-3.5", value === o.label ? "opacity-100" : "opacity-0")} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">{o.label}</span>
                      {o.sublabel && (
                        <span className="block truncate text-xs text-muted-foreground">{o.sublabel}</span>
                      )}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
