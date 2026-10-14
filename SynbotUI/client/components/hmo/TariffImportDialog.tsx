import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Upload, Loader2, CheckCircle2, AlertTriangle, FileSpreadsheet,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

/**
 * Upload an HMO's tariff spreadsheet, review it, then commit.
 *
 * "each HMO provider has an Excel file that shows all the tariffs for all the
 * services that HMO provides with the pricing... if there's a tariff change, we
 * can just upload the new Excel file."
 *
 * Uploading writes NOTHING. It returns a preview, and a second explicit action
 * commits it. One import sets negotiated prices for hundreds of services at
 * once, so a misread column would otherwise mis-price an entire payer silently
 * until an invoice was disputed.
 *
 * Unmatched rows are shown and excluded rather than fuzzy-matched: guessing
 * which catalogue entry a tariff line means is how a cheap test inherits an
 * expensive test's price.
 */
const naira = (v: any) => `₦${Number(v ?? 0).toLocaleString()}`;

export function TariffImportDialog({
  hmo,
  open,
  onOpenChange,
}: {
  hmo: { id: number | string; name?: string };
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<any | null>(null);

  const upload = useMutation({
    mutationFn: (file: File) => api.hospital.coverage.previewTariffImport(hmo.id, file),
    onSuccess: (d) => setPreview(d),
    onError: (e: any) =>
      toast({ title: "Could not read that file", description: e?.message, variant: "destructive" }),
  });

  const commit = useMutation({
    mutationFn: () =>
      api.hospital.coverage.commitTariffImport(
        hmo.id,
        (preview?.rows ?? [])
          .filter((r: any) => r.matched)
          .map((r: any) => ({ id: r.id, column: r.column, price: r.price })),
      ),
    onSuccess: (d: any) => {
      toast({
        title: `${d.written} price${d.written === 1 ? "" : "s"} updated`,
        description: d.failed ? `${d.failed} could not be written.` : undefined,
      });
      void qc.invalidateQueries({ queryKey: ["hmo-services"] });
      void qc.invalidateQueries({ queryKey: ["service-payer-prices"] });
      setPreview(null);
      onOpenChange(false);
    },
    onError: (e: any) =>
      toast({ title: "Import failed", description: e?.message, variant: "destructive" }),
  });

  const rows: any[] = preview?.rows ?? [];
  const matched = rows.filter((r) => r.matched);

  const reset = () => { setPreview(null); if (fileRef.current) fileRef.current.value = ""; };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) reset(); onOpenChange(o); }}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileSpreadsheet className="h-4 w-4 text-primary" />
            Import tariff — {hmo.name}
          </DialogTitle>
          <DialogDescription>
            Upload the payer's spreadsheet. Nothing is saved until you review what
            it found and confirm.
          </DialogDescription>
        </DialogHeader>

        {!preview ? (
          <div className="space-y-3 py-2">
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xlsm"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) upload.mutate(f);
              }}
            />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={upload.isPending}
              className="flex w-full flex-col items-center gap-2 rounded-lg border-2 border-dashed py-10 transition-colors hover:border-primary/50 hover:bg-muted/40"
            >
              {upload.isPending ? (
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              ) : (
                <Upload className="h-6 w-6 text-muted-foreground" />
              )}
              <span className="text-sm font-medium">
                {upload.isPending ? "Reading…" : "Choose a spreadsheet"}
              </span>
              <span className="text-xs text-muted-foreground">.xlsx up to 5 MB</span>
            </button>
            <p className="text-xs text-muted-foreground">
              The sheet needs a column naming the service and a column with the
              price. Title rows above the headings are skipped automatically, and
              amounts written as <span className="font-mono">8,000</span> or{" "}
              <span className="font-mono">₦8,000</span> are read correctly.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2 text-xs">
              <Badge variant="outline" className="gap-1">
                <CheckCircle2 className="h-3 w-3 text-green-600" />
                {preview.matched} matched
              </Badge>
              {preview.new > 0 && <Badge variant="outline">{preview.new} new</Badge>}
              {preview.changed > 0 && (
                <Badge variant="outline" className="border-blue-500/40 text-blue-700 dark:text-blue-400">
                  {preview.changed} changed
                </Badge>
              )}
              {preview.unmatched > 0 && (
                <Badge variant="outline" className="border-amber-500/40 text-amber-700 dark:text-amber-400">
                  {preview.unmatched} unmatched
                </Badge>
              )}
              {preview.unreadable_price > 0 && (
                <Badge variant="outline" className="border-amber-500/40 text-amber-700 dark:text-amber-400">
                  {preview.unreadable_price} unreadable price
                </Badge>
              )}
              <span className="ml-auto text-muted-foreground">
                headings on row {preview.parsed_from_row}
              </span>
            </div>

            {preview.unmatched > 0 && (
              <p className="flex items-start gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                {preview.unmatched} row{preview.unmatched === 1 ? "" : "s"} name a service
                that is not in the catalogue and will be skipped. Add them to the
                catalogue first if they should be priced.
              </p>
            )}

            <div className="max-h-[320px] overflow-y-auto rounded-md border">
              <Table>
                <TableHeader className="sticky top-0 bg-background">
                  <TableRow>
                    <TableHead>Service in the sheet</TableHead>
                    <TableHead>Matched to</TableHead>
                    <TableHead className="text-right">Current</TableHead>
                    <TableHead className="text-right">New</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((r, i) => (
                    <TableRow key={i} className={cn(!r.matched && "opacity-50")}>
                      <TableCell className="text-xs">{r.name}</TableCell>
                      <TableCell className="text-xs">
                        {r.matched ? (
                          <span className="text-muted-foreground">
                            {r.matched_name}{" "}
                            <Badge variant="outline" className="ml-1 text-xs">{r.kind}</Badge>
                          </span>
                        ) : (
                          <span className="text-amber-600">not in the catalogue</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right text-xs tabular-nums text-muted-foreground">
                        {r.current_price != null ? naira(r.current_price) : "—"}
                      </TableCell>
                      <TableCell className="text-right text-xs font-medium tabular-nums">
                        {r.matched ? naira(r.price) : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )}

        <DialogFooter>
          {preview && (
            <>
              <Button variant="ghost" onClick={reset}>Choose another file</Button>
              <Button
                disabled={commit.isPending || matched.length === 0}
                onClick={() => commit.mutate()}
              >
                {commit.isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                Apply {matched.length} price{matched.length === 1 ? "" : "s"}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
