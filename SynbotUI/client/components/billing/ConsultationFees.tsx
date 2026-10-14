import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Loader2, Stethoscope, Upload, Plus } from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { askText } from "@/lib/ask";

/** Read a simple CSV (first row = headers). Quoted fields with commas are supported. */
function parseCsv(text: string): Record<string, string>[] {
  const rows: string[][] = [];
  let cur: string[] = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (ch === '"') quoted = false;
      else field += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") { cur.push(field); field = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      cur.push(field); field = "";
      if (cur.some((c) => c.trim())) rows.push(cur);
      cur = [];
    } else field += ch;
  }
  cur.push(field);
  if (cur.some((c) => c.trim())) rows.push(cur);
  const [head, ...body] = rows;
  return (body ?? []).map((r) => Object.fromEntries((head ?? []).map((h, i) => [h.trim(), (r[i] ?? "").trim()])));
}

const PAY_FIRST = [
  { value: "private_outpatient", label: "Private outpatients pay before lab, scan and pharmacy" },
  { value: "all_but_hmo", label: "Everyone except HMO pays first" },
  { value: "off", label: "Off: services are not held for payment" },
];

/**
 * Consultation fees: what the front desk bills before the patient sees the doctor. One price per specialty (first
 * visit and follow-up), a doctor's own fee where they charge differently, the new-patient registration fee, and
 * whether lab / scan / pharmacy wait for payment. Upload a CSV price list to set many at once.
 */
export function ConsultationFees() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const { data, isLoading } = useQuery({ queryKey: ["consultation-tariffs"], queryFn: () => api.hospital.billing.consultationTariffs() });
  const [edits, setEdits] = useState<Record<string, Record<string, string>>>({});
  const [docEdits, setDocEdits] = useState<Record<string, Record<string, string>>>({});
  const [regPrice, setRegPrice] = useState<string | null>(null);
  const [signers, setSigners] = useState<Record<string, string>>({});
  const refresh = () => void qc.invalidateQueries({ queryKey: ["consultation-tariffs"] });
  const fail = (e: any) => toast({ title: "Could not save", description: e?.message, variant: "destructive" });

  const saveTariff = useMutation({
    mutationFn: (v: { id: number | "new"; p: Record<string, any> }) => api.hospital.billing.saveConsultationTariff(v.id, v.p),
    onSuccess: (_r, v) => { toast({ title: "Consultation fee saved" }); setEdits((e) => { const n = { ...e }; delete n[String(v.id)]; return n; }); refresh(); },
    onError: fail,
  });
  const saveDoctor = useMutation({
    mutationFn: (v: { id: string; p: Record<string, any> }) => api.hospital.billing.saveDoctorFee(v.id, v.p),
    onSuccess: (_r, v) => { toast({ title: "Doctor's fee saved" }); setDocEdits((e) => { const n = { ...e }; delete n[v.id]; return n; }); refresh(); },
    onError: fail,
  });
  const saveSettings = useMutation({
    mutationFn: (p: Record<string, any>) => api.hospital.billing.saveBillingSettings(p),
    onSuccess: () => { toast({ title: "Saved" }); setRegPrice(null); refresh(); },
    onError: fail,
  });
  const importMut = useMutation({
    mutationFn: (rows: Record<string, string>[]) => api.hospital.billing.importConsultationTariffs(rows),
    onSuccess: (r: any) => { toast({ title: `Price list loaded: ${r.imported?.length ?? 0} specialties`, description: r.skipped?.length ? `${r.skipped.length} rows skipped (no specialty)` : undefined }); refresh(); },
    onError: fail,
  });

  if (isLoading) return <Card><CardContent className="py-8 text-center"><Loader2 className="mx-auto h-5 w-5 animate-spin" /></CardContent></Card>;
  const tariffs: any[] = data?.tariffs ?? [];
  const doctors: any[] = data?.doctors ?? [];
  const val = (id: string, k: string, fallback: any) => edits[id]?.[k] ?? (fallback ?? "");
  const set = (id: string, k: string, v: string) => setEdits((e) => ({ ...e, [id]: { ...(e[id] ?? {}), [k]: v } }));
  const dval = (id: string, k: string, fallback: any) => docEdits[id]?.[k] ?? (fallback ?? "");
  const dset = (id: string, k: string, v: string) => setDocEdits((e) => ({ ...e, [id]: { ...(e[id] ?? {}), [k]: v } }));
  const n = (v: any) => (v === "" || v === undefined || v === null ? null : Number(v));

  const onFile = async (f?: File | null) => {
    if (!f) return;
    const rows = parseCsv(await f.text());
    if (!rows.length) { toast({ title: "The file has no rows", variant: "destructive" }); return; }
    importMut.mutate(rows);
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base"><Stethoscope className="h-4 w-4" /> Consultation fees</CardTitle>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" className="gap-1.5" onClick={async () => {
              const name = await askText("Name of the new specialty / clinic");
              if (name && name.trim()) saveTariff.mutate({ id: "new", p: { specialty: name.trim() } });
            }}><Plus className="h-3.5 w-3.5" /> Specialty</Button>
            <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted/40">
              {importMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />} Upload price list (CSV)
              <input type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => { void onFile(e.target.files?.[0]); e.target.value = ""; }} />
            </label>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          The front desk bills these before the doctor. CSV columns: specialty, initial_fee, follow_up_fee, follow_up_days.
          A visit within the follow-up days of the last consultation is billed as a follow-up.
        </p>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label className="text-xs">New patient registration ({data?.registration?.name ?? "not set"})</Label>
            <div className="flex gap-2">
              <Input type="number" min="0" className="h-8 text-xs" value={regPrice ?? String(data?.registration?.base_price ?? "")}
                onChange={(e) => setRegPrice(e.target.value)} />
              <Button size="sm" className="h-8" disabled={regPrice === null || saveSettings.isPending}
                onClick={() => saveSettings.mutate({ registration_price: Number(regPrice) })}>Save</Button>
            </div>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Pay before services</Label>
            <Select value={data?.pay_first ?? "off"} onValueChange={(v) => saveSettings.mutate({ pay_first: v })}>
              <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>{PAY_FIRST.map((p) => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        </div>

        {/* printed on every invoice and receipt until staff signatures are on file; the cashier is whoever took the payment */}
        <div className="space-y-1.5 rounded-md border p-3">
          <Label className="text-xs font-semibold">Signatories on invoices and receipts ("Name, title")</Label>
          <div className="grid gap-2 sm:grid-cols-3">
            {([["signatory_bill_manager", "Bill Manager (blank = whoever raised the bill)"], ["signatory_med_supdt", "Medical Superintendent"],
               ["signatory_authorised", "Authorised Signatory"]] as const).map(([k, label]) => (
              <div key={k} className="space-y-1">
                <span className="text-xs text-foreground/75">{label}</span>
                <Input className="h-8 text-xs" placeholder="e.g. Dr A. Bello, Medical Superintendent"
                  value={signers[k] ?? data?.signatories?.[k] ?? ""} onChange={(e) => setSigners((x) => ({ ...x, [k]: e.target.value }))} />
              </div>
            ))}
          </div>
          <Button size="sm" className="h-8" disabled={!Object.keys(signers).length || saveSettings.isPending}
            onClick={() => saveSettings.mutate(signers, { onSuccess: () => setSigners({}) })}>Save signatories</Button>
        </div>

        <div className="rounded-md border overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">Specialty</TableHead>
                <TableHead className="text-xs">First visit (₦)</TableHead>
                <TableHead className="text-xs">Follow-up (₦)</TableHead>
                <TableHead className="text-xs">Follow-up days</TableHead>
                <TableHead className="text-xs">Clinic code</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {tariffs.map((t) => {
                const id = String(t.id);
                const dirty = !!edits[id];
                return (
                  <TableRow key={t.id}>
                    <TableCell className="text-xs font-medium">{t.specialty}</TableCell>
                    <TableCell><Input type="number" min="0" className="h-7 w-28 text-xs" value={val(id, "initial_price", t.initial_price)} onChange={(e) => set(id, "initial_price", e.target.value)} /></TableCell>
                    <TableCell><Input type="number" min="0" className="h-7 w-28 text-xs" value={val(id, "follow_up_price", t.follow_up_price)} onChange={(e) => set(id, "follow_up_price", e.target.value)} /></TableCell>
                    <TableCell><Input type="number" min="0" className="h-7 w-20 text-xs" value={val(id, "follow_up_days", t.follow_up_days)} onChange={(e) => set(id, "follow_up_days", e.target.value)} /></TableCell>
                    <TableCell><Input className="h-7 w-24 text-xs" value={val(id, "department_code", t.department_code)} onChange={(e) => set(id, "department_code", e.target.value)} /></TableCell>
                    <TableCell>
                      <Button size="sm" className="h-7 text-xs" disabled={!dirty || saveTariff.isPending} onClick={() => saveTariff.mutate({
                        id: t.id, p: {
                          ...(edits[id].initial_price !== undefined ? { initial_price: n(edits[id].initial_price) } : {}),
                          ...(edits[id].follow_up_price !== undefined ? { follow_up_price: n(edits[id].follow_up_price) } : {}),
                          ...(edits[id].follow_up_days !== undefined ? { follow_up_days: n(edits[id].follow_up_days) } : {}),
                          ...(edits[id].department_code !== undefined ? { department_code: edits[id].department_code || null } : {}),
                        },
                      })}>Save</Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>

        <div>
          <p className="mb-2 text-sm font-medium">Doctors</p>
          <p className="mb-2 text-xs text-muted-foreground">Each doctor's specialty sets their fee. Enter a fee only where a doctor charges differently.</p>
          <div className="rounded-md border overflow-x-auto max-h-[420px] overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Doctor</TableHead>
                  <TableHead className="text-xs">Specialty</TableHead>
                  <TableHead className="text-xs">Own first-visit fee</TableHead>
                  <TableHead className="text-xs">Own follow-up fee</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {doctors.length === 0 && <TableRow><TableCell colSpan={5} className="text-xs text-muted-foreground">No active doctors on the staff list.</TableCell></TableRow>}
                {doctors.map((d) => {
                  const id = d.doctor_id;
                  const tariffId = dval(id, "tariff_id", d.tariff_id ? String(d.tariff_id) : "");
                  return (
                    <TableRow key={id}>
                      <TableCell className="text-xs">{d.full_name}<span className="block text-muted-foreground">{d.staff_specialty ?? d.department ?? ""}</span></TableCell>
                      <TableCell>
                        <Select value={tariffId || "auto"} onValueChange={(v) => dset(id, "tariff_id", v === "auto" ? "" : v)}>
                          <SelectTrigger className="h-7 w-44 text-xs"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="auto">From staff record / clinic</SelectItem>
                            {tariffs.map((t) => <SelectItem key={t.id} value={String(t.id)}>{t.specialty}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </TableCell>
                      <TableCell><Input type="number" min="0" placeholder="specialty fee" className="h-7 w-28 text-xs" value={dval(id, "initial_fee", d.initial_fee)} onChange={(e) => dset(id, "initial_fee", e.target.value)} /></TableCell>
                      <TableCell><Input type="number" min="0" placeholder="specialty fee" className="h-7 w-28 text-xs" value={dval(id, "follow_up_fee", d.follow_up_fee)} onChange={(e) => dset(id, "follow_up_fee", e.target.value)} /></TableCell>
                      <TableCell>
                        <Button size="sm" className="h-7 text-xs" disabled={!docEdits[id] || saveDoctor.isPending} onClick={() => saveDoctor.mutate({
                          id, p: { tariff_id: tariffId ? Number(tariffId) : null, initial_fee: n(dval(id, "initial_fee", d.initial_fee)), follow_up_fee: n(dval(id, "follow_up_fee", d.follow_up_fee)) },
                        })}>Save</Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
