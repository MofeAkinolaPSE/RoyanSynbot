import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FlaskConical, Loader2, Save, Tags, Activity, Clock, AlertTriangle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  WorkspaceSheet, PanelHeaderIdentity, SectionLabel, DetailRow,
} from "@/components/shared/panel-shared";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

/**
 * The lab's administrative workspace for one test.
 *
 * The catalogue lists what exists; this is where it gets configured. Built as a
 * workspace sheet rather than a form dialog so it matches every other panel in
 * the app — a lab manager already knows how to read it.
 *
 * Three tabs, because configuration alone is not enough to run a lab:
 *   Setup    — the test's definition, editable
 *   Pricing  — the list price AND every payer's negotiated rate (7,179 rates
 *              across 261 tests came out of migration 200)
 *   Activity — how often it is actually ordered, and how long it REALLY takes
 *              against its configured target. FBC is configured at 24h and
 *              measures 1.1h; that gap is the point.
 */
const naira = (v: any) => (Number(v) > 0 ? `₦${Number(v).toLocaleString()}` : null);

export function LabTestPanel({
  testId,
  onClose,
}: {
  testId: number | string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [tab, setTab] = useState("setup");
  const [form, setForm] = useState<Record<string, string>>({});

  const { data, isLoading } = useQuery({
    queryKey: ["lab-test-detail", testId],
    queryFn: () => api.hospital.lab.testDetail(testId),
  });

  const test = data?.test ?? {};
  const stats = data?.stats ?? {};
  const payers: any[] = data?.payer_prices ?? [];

  // Seed the form once the test arrives, not on every render.
  useEffect(() => {
    if (!test.id) return;
    setForm({
      name: test.name ?? "",
      code: test.code ?? "",
      category: test.category ?? "",
      specimen_type: test.specimen_type ?? "",
      unit: test.unit ?? "",
      reference_range: test.reference_range ?? "",
      turnaround_hours: test.turnaround_hours != null ? String(test.turnaround_hours) : "",
      base_price: test.base_price != null ? String(test.base_price) : "",
    });
  }, [test.id]);

  const save = useMutation({
    mutationFn: () =>
      api.hospital.lab.updateCatalogEntry(testId, {
        name: form.name?.trim(),
        code: form.code?.trim() || undefined,
        category: form.category?.trim() || undefined,
        specimen_type: form.specimen_type?.trim() || undefined,
        unit: form.unit?.trim() || undefined,
        reference_range: form.reference_range?.trim() || undefined,
        turnaround_hours: form.turnaround_hours ? Number(form.turnaround_hours) : undefined,
        base_price: form.base_price ? Number(form.base_price) : undefined,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["lab-test-detail", testId] });
      void qc.invalidateQueries({ queryKey: ["lab-catalog"] });
      toast({ title: "Test updated" });
    },
    onError: (e: any) =>
      toast({ title: "Could not save", description: e?.message, variant: "destructive" }),
  });

  const set = (k: string) => (e: any) => setForm((f) => ({ ...f, [k]: e.target.value }));

  // The number a lab manager opens this for: configured target vs reality.
  const tatGap =
    stats.avg_turnaround_hours != null && test.turnaround_hours
      ? Number(stats.avg_turnaround_hours) - Number(test.turnaround_hours)
      : null;

  return (
    <WorkspaceSheet
      onClose={onClose}
      header={
        <PanelHeaderIdentity
          icon={<FlaskConical className="h-5 w-5 text-primary" />}
          title={test.name ?? "Test"}
          badges={
            <>
              {test.code && (
                <Badge variant="outline" className="font-mono text-xs">{test.code}</Badge>
              )}
              {test.category && (
                <Badge variant="outline" className="text-xs capitalize">{test.category}</Badge>
              )}
              {!Number(test.base_price) && (
                <Badge variant="outline" className="border-amber-500/40 bg-amber-500/10 text-xs text-amber-700 dark:text-amber-400">
                  not priced
                </Badge>
              )}
            </>
          }
          subline={
            test.external_source
              ? "Migrated from Hope"
              : "Added in Synbot"
          }
        />
      }
      footer={
        tab === "setup" ? (
          <Button
            size="sm" className="gap-1.5 ml-auto"
            disabled={save.isPending || !(form.name ?? "").trim()}
            onClick={() => save.mutate()}
          >
            {save.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
            Save changes
          </Button>
        ) : undefined
      }
    >
      <Tabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-1 flex-col">
        <TabsList className="mx-5 mt-3 h-auto shrink-0 flex-wrap border border-border bg-muted">
          <TabsTrigger value="setup">Setup</TabsTrigger>
          <TabsTrigger value="pricing">
            Pricing{payers.length > 0 ? ` (${payers.length})` : ""}
          </TabsTrigger>
          <TabsTrigger value="activity">Activity</TabsTrigger>
        </TabsList>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {isLoading ? (
            <div className="flex justify-center py-10">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <>
              <TabsContent value="setup" className="mt-0 space-y-3">
                <section>
                  <SectionLabel icon={<FlaskConical className="h-3.5 w-3.5" />} label="Definition" />
                  <div className="grid grid-cols-2 gap-3">
                    <div className="col-span-2 space-y-1">
                      <Label className="text-xs">Test name</Label>
                      <Input value={form.name ?? ""} onChange={set("name")} className="h-8 text-sm" />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Short code</Label>
                      <Input value={form.code ?? ""} onChange={set("code")} className="h-8 text-sm" />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Category</Label>
                      <Input value={form.category ?? ""} onChange={set("category")} className="h-8 text-sm" />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Specimen</Label>
                      <Input value={form.specimen_type ?? ""} onChange={set("specimen_type")} className="h-8 text-sm" />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Unit</Label>
                      <Input value={form.unit ?? ""} onChange={set("unit")} className="h-8 text-sm" />
                    </div>
                    <div className="col-span-2 space-y-1">
                      <Label className="text-xs">Reference range</Label>
                      <Input value={form.reference_range ?? ""} onChange={set("reference_range")} className="h-8 text-sm" />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Target turnaround (hours)</Label>
                      <Input type="number" min="0" value={form.turnaround_hours ?? ""} onChange={set("turnaround_hours")} className="h-8 text-sm" />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">List price (₦)</Label>
                      <Input type="number" min="0" step="100" value={form.base_price ?? ""} onChange={set("base_price")} className="h-8 text-sm" />
                    </div>
                  </div>
                </section>
              </TabsContent>

              <TabsContent value="pricing" className="mt-0 space-y-3">
                <section>
                  <SectionLabel icon={<Tags className="h-3.5 w-3.5" />} label="List price" />
                  <DetailRow
                    label="Charged to a private patient"
                    value={naira(test.base_price) ?? "not set"}
                    accent={Number(test.base_price) ? "font-semibold" : "text-amber-600"}
                  />
                </section>

                <Separator />

                <section>
                  <SectionLabel icon={<Tags className="h-3.5 w-3.5" />} label="Negotiated payer rates" />
                  {payers.length === 0 ? (
                    <p className="py-4 text-center text-xs text-muted-foreground">
                      No payer has a negotiated rate for this test, so every HMO is
                      quoted the list price.
                    </p>
                  ) : (
                    <>
                      {payers.map((p) => {
                        const diff = Number(p.price) - Number(test.base_price || 0);
                        return (
                          <DetailRow
                            key={p.id}
                            label={p.hmo_name ?? `HMO ${p.hmo_id}`}
                            value={
                              `${naira(p.price)}${
                                Number(test.base_price) && diff !== 0
                                  ? `  (${diff > 0 ? "+" : ""}${Number(diff).toLocaleString()})`
                                  : ""
                              }`
                            }
                            accent={diff < 0 ? "text-amber-600" : undefined}
                          />
                        );
                      })}
                      <p className="mt-2 text-xs text-muted-foreground">
                        Amber means that payer pays less than the list price. Retired
                        payers are excluded — their historical rates are not billable.
                      </p>
                    </>
                  )}
                </section>
              </TabsContent>

              <TabsContent value="activity" className="mt-0 space-y-3">
                <section>
                  <SectionLabel icon={<Activity className="h-3.5 w-3.5" />} label="Ordering" />
                  <DetailRow label="Orders (recent sample)" value={stats.orders_total ?? 0} />
                  <DetailRow label="Last 30 days" value={stats.orders_30d ?? 0} />
                  <DetailRow label="Resulted" value={stats.resulted ?? 0} />
                  <DetailRow
                    label="Still outstanding"
                    value={stats.pending ?? 0}
                    accent={Number(stats.pending) > 0 ? "text-amber-600" : undefined}
                  />
                </section>

                <Separator />

                <section>
                  <SectionLabel icon={<Clock className="h-3.5 w-3.5" />} label="Turnaround" />
                  <DetailRow
                    label="Configured target"
                    value={test.turnaround_hours != null ? `${test.turnaround_hours} h` : "not set"}
                  />
                  <DetailRow
                    label="Actually measured"
                    value={
                      stats.avg_turnaround_hours != null
                        ? `${stats.avg_turnaround_hours} h`
                        : "not enough resulted orders"
                    }
                    accent={tatGap != null && tatGap > 0 ? "text-red-600 font-semibold" : undefined}
                  />
                  {tatGap != null && (
                    <p
                      className={cn(
                        "mt-2 flex items-start gap-1.5 rounded-md border px-3 py-2 text-xs",
                        tatGap > 0
                          ? "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-400"
                          : "border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-400",
                      )}
                    >
                      {tatGap > 0 && <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
                      {tatGap > 0
                        ? `Running ${tatGap.toFixed(1)} hours over the configured target.`
                        : `Beating the configured target by ${Math.abs(tatGap).toFixed(1)} hours — the target may be set too loosely.`}
                    </p>
                  )}
                </section>
              </TabsContent>
            </>
          )}
        </div>
      </Tabs>
    </WorkspaceSheet>
  );
}
