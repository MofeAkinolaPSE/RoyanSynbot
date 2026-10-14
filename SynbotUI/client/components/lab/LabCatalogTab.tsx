import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, Loader2, Plus, Search, AlertTriangle, Pencil } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { LabTestPanel } from "@/components/lab/LabTestPanel";

/**
 * The test catalogue: what the lab offers, what each test costs, and how to add
 * one.
 *
 * "we need to see the different types of tests, and the cost of those tests, and
 * have the ability to add a new test and the information that comes along with
 * the test."
 *
 * Only a typeahead search endpoint existed before, which serves an order form
 * and nothing else — there was no way to review the catalogue or extend it.
 * Prices became real data in migration 200 (281 of 288 tests).
 */
const naira = (v: any) =>
  Number(v) > 0 ? `₦${Number(v).toLocaleString()}` : null;

const BLANK = {
  name: "", code: "", category: "haematology", specimen_type: "blood",
  unit: "", reference_range: "", turnaround_hours: "", base_price: "",
};

export function LabCatalogTab() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("all");
  const [editing, setEditing] = useState<any | null>(null);
  // The full workspace for one test. The dialog below stays for CREATING a
  // test, which has no panel to open until it exists.
  const [openTest, setOpenTest] = useState<number | null>(null);
  const [form, setForm] = useState<Record<string, string>>({ ...BLANK });

  const { data, isLoading } = useQuery({
    queryKey: ["lab-catalog", q, category],
    queryFn: () =>
      api.hospital.lab.listCatalog({
        q: q || undefined,
        category: category === "all" ? undefined : category,
      }),
  });

  const tests: any[] = data?.tests ?? [];
  const categories: string[] = data?.categories ?? [];

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, any> = {
        name: form.name.trim(),
        code: form.code.trim() || undefined,
        category: form.category || undefined,
        specimen_type: form.specimen_type || undefined,
        unit: form.unit.trim() || undefined,
        reference_range: form.reference_range.trim() || undefined,
        turnaround_hours: form.turnaround_hours ? Number(form.turnaround_hours) : undefined,
        base_price: form.base_price ? Number(form.base_price) : undefined,
      };
      return editing?.id
        ? api.hospital.lab.updateCatalogEntry(editing.id, body)
        : api.hospital.lab.createCatalogEntry(body);
    },
    onSuccess: () => {
      setEditing(null);
      setForm({ ...BLANK });
      void qc.invalidateQueries({ queryKey: ["lab-catalog"] });
      toast({ title: editing?.id ? "Test updated" : "Test added to the catalogue" });
    },
    onError: (e: any) =>
      toast({ title: "Could not save", description: e?.message, variant: "destructive" }),
  });

  const openNew = () => { setForm({ ...BLANK }); setEditing({}); };
  const openEdit = (t: any) => {
    setForm({
      name: t.name ?? "", code: t.code ?? "", category: t.category ?? "haematology",
      specimen_type: t.specimen_type ?? "blood", unit: t.unit ?? "",
      reference_range: t.reference_range ?? "",
      turnaround_hours: t.turnaround_hours != null ? String(t.turnaround_hours) : "",
      base_price: t.base_price != null ? String(t.base_price) : "",
    });
    setEditing(t);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search tests…" className="h-9 pl-8 text-sm"
          />
        </div>
        <Select value={category} onValueChange={setCategory}>
          <SelectTrigger className="h-9 w-[190px] text-sm"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All categories</SelectItem>
            {categories.map((c) => (
              <SelectItem key={c} value={c} className="capitalize">{c}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button size="sm" className="gap-1.5" onClick={openNew}>
          <Plus className="h-3.5 w-3.5" /> Add test
        </Button>
      </div>

      {Number(data?.unpriced) > 0 && (
        <p className="flex items-start gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {data.unpriced} test{data.unpriced === 1 ? "" : "s"} have no price and will bill at ₦0.
        </p>
      )}

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Test</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Specimen</TableHead>
                  <TableHead>Reference range</TableHead>
                  <TableHead>TAT</TableHead>
                  <TableHead>Price</TableHead>
                  <TableHead className="w-[60px]" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  <TableRow>
                    <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                      <Loader2 className="mr-2 inline h-5 w-5 animate-spin" />Loading…
                    </TableCell>
                  </TableRow>
                ) : tests.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                      No tests match.
                    </TableCell>
                  </TableRow>
                ) : (
                  tests.map((t) => (
                    <TableRow
                      key={t.id}
                      onClick={() => setOpenTest(t.id)}
                      className="cursor-pointer hover:bg-muted/40"
                    >
                      <TableCell>
                        <div className="text-sm font-medium">{t.name}</div>
                        {t.code && <div className="font-mono text-xs text-muted-foreground">{t.code}</div>}
                      </TableCell>
                      <TableCell className="text-xs capitalize text-muted-foreground">{t.category ?? "—"}</TableCell>
                      <TableCell className="text-xs capitalize text-muted-foreground">{t.specimen_type ?? "—"}</TableCell>
                      <TableCell className="max-w-[220px] truncate text-xs text-muted-foreground">
                        {t.reference_range ?? "—"}
                        {t.unit ? ` (${t.unit})` : ""}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {t.turnaround_hours != null ? `${t.turnaround_hours}h` : "—"}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-sm tabular-nums">
                        {naira(t.base_price) ?? (
                          <span className="text-xs text-amber-600">not priced</span>
                        )}
                      </TableCell>
                      <TableCell className="w-[60px]">
                        <Button
                          size="icon" variant="ghost" className="h-7 w-7"
                          aria-label={`Configure ${t.name}`}
                          onClick={(e) => { e.stopPropagation(); setOpenTest(t.id); }}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {openTest != null && (
        <LabTestPanel testId={openTest} onClose={() => setOpenTest(null)} />
      )}

      <Dialog open={!!editing} onOpenChange={(o) => { if (!o) setEditing(null); }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FlaskConical className="h-4 w-4 text-primary" />
              {editing?.id ? "Edit test" : "Add a test"}
            </DialogTitle>
            <DialogDescription>
              Everything here appears on the order form and the bill, so a missing
              price means the test is charged at nothing.
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2 space-y-1">
              <Label className="text-xs">Test name *</Label>
              <Input
                value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                className="h-8 text-sm" placeholder="e.g. Serum Electrolytes"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Short code</Label>
              <Input
                value={form.code} onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))}
                className="h-8 text-sm" placeholder="E/U/CR"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Price (₦)</Label>
              <Input
                type="number" min="0" step="100" value={form.base_price}
                onChange={(e) => setForm((f) => ({ ...f, base_price: e.target.value }))}
                className="h-8 text-sm"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Category</Label>
              <Input
                value={form.category} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
                className="h-8 text-sm"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Specimen</Label>
              <Input
                value={form.specimen_type}
                onChange={(e) => setForm((f) => ({ ...f, specimen_type: e.target.value }))}
                className="h-8 text-sm"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Unit</Label>
              <Input
                value={form.unit} onChange={(e) => setForm((f) => ({ ...f, unit: e.target.value }))}
                className="h-8 text-sm" placeholder="mmol/L"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Turnaround (hours)</Label>
              <Input
                type="number" min="0" value={form.turnaround_hours}
                onChange={(e) => setForm((f) => ({ ...f, turnaround_hours: e.target.value }))}
                className="h-8 text-sm"
              />
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-xs">Reference range</Label>
              <Input
                value={form.reference_range}
                onChange={(e) => setForm((f) => ({ ...f, reference_range: e.target.value }))}
                className="h-8 text-sm" placeholder="Male: 40-52, Female: 36-48"
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
            <Button
              disabled={save.isPending || form.name.trim().length < 2}
              onClick={() => save.mutate()}
            >
              {save.isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              {editing?.id ? "Save changes" : "Add test"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
