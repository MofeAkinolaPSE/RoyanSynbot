import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * The row-per-record table the Laboratory page uses, made reusable.
 *
 * That page was singled out as the one that reads well — a row per item, the
 * key facts in columns, and the whole row opening the record. Everywhere else
 * on the chart used stacked bordered cards, which cost about three times the
 * vertical space and made two records hard to compare at a glance.
 *
 * Deliberately not a data grid: no sorting, filtering or virtualisation. These
 * lists are short and per-patient, and a grid would bring configuration nobody
 * needs.
 */

export type RecordColumn<T> = {
  header: string;
  /** Tailwind width class, e.g. "w-[110px]". Omit for a flexible column. */
  width?: string;
  className?: string;
  cell: (row: T) => React.ReactNode;
};

export function RecordTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  accent,
  emptyIcon,
  emptyLabel = "Nothing recorded",
  className,
}: {
  columns: RecordColumn<T>[];
  rows: T[];
  rowKey: (row: T, i: number) => string | number;
  onRowClick?: (row: T) => void;
  /** Left-border class per row, e.g. urgency or abnormality. */
  accent?: (row: T) => string | undefined;
  emptyIcon?: React.ReactNode;
  emptyLabel?: string;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                {columns.map((c) => (
                  <TableHead key={c.header} className={cn(c.width, c.className)}>
                    {c.header}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={columns.length} className="py-10 text-center text-muted-foreground">
                    {emptyIcon && <div className="mx-auto mb-2 opacity-30">{emptyIcon}</div>}
                    {emptyLabel}
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((row, i) => (
                  <TableRow
                    key={rowKey(row, i)}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                    className={cn(
                      "border-l-2",
                      accent?.(row) ?? "border-l-transparent",
                      onRowClick && "cursor-pointer transition-colors hover:bg-muted/50",
                    )}
                  >
                    {columns.map((c) => (
                      <TableCell key={c.header} className={c.className}>
                        {c.cell(row)}
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * The two-line cell the lab table uses everywhere: the thing itself, with its
 * identifier or qualifier beneath in muted mono.
 */
export function CellStack({
  primary,
  secondary,
  mono = false,
  muted = false,
}: {
  primary: React.ReactNode;
  secondary?: React.ReactNode;
  mono?: boolean;
  muted?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className={cn("text-sm font-medium leading-tight", muted && "italic text-muted-foreground")}>
        {primary}
      </div>
      {secondary != null && secondary !== "" && (
        <div className={cn("text-xs text-muted-foreground", mono && "font-mono")}>{secondary}</div>
      )}
    </div>
  );
}
