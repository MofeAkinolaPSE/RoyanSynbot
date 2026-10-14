import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Loader2, Plus, ReceiptText, X } from "lucide-react";
import { api } from "@/lib/api-client";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { BillingWorkspacePanel } from "@/components/billing/BillingWorkspacePanel";
import { BillBadge } from "@/components/billing/billing-shared";

const naira = (v: any) => `₦${Number(v ?? 0).toLocaleString("en-NG", { maximumFractionDigits: 2 })}`;
const STATUSES = ["all", "pending", "partial", "paid", "void"];

/** Scancare's own billing: its invoices (SCB- series, Scancare's books), receive payment, print. Scans the hospital's
 *  doctors order arrive here by themselves; walk-in clients are billed from New walk-in. */
export function ScancareBilling() {
  const [status, setStatus] = useState("all");
  const [panel, setPanel] = useState<{ bill: any; receive: boolean } | null>(null);
  const [walkIn, setWalkIn] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["hospital-bills", "SCANCARE", status],
    queryFn: () => api.hospital.billing.listBills({ entity: "SCANCARE", status: status === "all" ? undefined : status, limit: 200 }),
    refetchInterval: 30_000,
  });
  const bills: any[] = data?.bills ?? (Array.isArray(data) ? data : []);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {STATUSES.map((s) => (
          <button key={s} onClick={() => setStatus(s)}
                  className={cn("rounded-full border px-3 py-1 text-xs capitalize", status === s ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted")}>{s}</button>
        ))}
        <Button size="sm" className="ml-auto gap-1.5" onClick={() => setWalkIn(true)}><Plus className="h-3.5 w-3.5" /> New walk-in</Button>
      </div>
      <Card><CardContent className="p-0">
        {isLoading ? <div className="flex justify-center py-12"><Loader2 className="h-5 w-5 animate-spin" /></div> : (
          <Table>
            <TableHeader><TableRow>
              <TableHead>Invoice</TableHead><TableHead>Client</TableHead><TableHead>Source</TableHead><TableHead className="text-right">Total</TableHead>
              <TableHead className="text-right">To pay</TableHead><TableHead>Status</TableHead><TableHead>Date</TableHead><TableHead />
            </TableRow></TableHeader>
            <TableBody>
              {bills.length === 0 && <TableRow><TableCell colSpan={8} className="py-10 text-center text-muted-foreground">No Scancare invoices{status !== "all" ? ` that are ${status}` : ""}.</TableCell></TableRow>}
              {bills.map((b) => (
                <TableRow key={b.id} className="cursor-pointer hover:bg-muted/50" onClick={() => setPanel({ bill: b, receive: false })}>
                  <TableCell className="font-mono text-xs">{b.bill_number}</TableCell>
                  <TableCell className="text-sm">{b.patient_name ?? `#${b.patient_id}`}{b.patient_mrn && <span className="block font-mono text-xs text-muted-foreground">{b.patient_mrn}</span>}</TableCell>
                  <TableCell className="text-xs">{b.encounter_id ? "Referred by Royan" : "Walk-in"}</TableCell>
                  <TableCell className="text-right">{naira(b.subtotal)}</TableCell>
                  <TableCell className={cn("text-right font-semibold", Number(b.outstanding) > 0 ? "text-red-600" : "text-green-600")}>{naira(b.outstanding)}</TableCell>
                  <TableCell><BillBadge status={b.status} /></TableCell>
                  <TableCell className="text-xs text-muted-foreground">{b.billed_at ? new Date(b.billed_at).toLocaleDateString() : "—"}</TableCell>
                  <TableCell className="whitespace-nowrap text-right" onClick={(e) => e.stopPropagation()}>
                    {["pending", "partial"].includes(b.status) && Number(b.outstanding) > 0 && (
                      <Button size="sm" className="h-7 px-2 text-xs" onClick={() => setPanel({ bill: b, receive: true })}>Receive</Button>)}
                    <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => window.open(`#/hospital/billing/${b.id}/invoice`, "_blank")}>Invoice</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent></Card>
      {panel && <BillingWorkspacePanel key={`${panel.bill.id}:${panel.receive}`} bill={panel.bill} receive={panel.receive} onClose={() => setPanel(null)} />}
      <WalkInBill open={walkIn} onClose={(bill) => { setWalkIn(false); if (bill) setPanel({ bill, receive: true }); }} />
    </div>
  );
}

/** A client walks in: find them (or register them in a few fields), pick the studies, raise one Scancare invoice. */
function WalkInBill({ open, onClose }: { open: boolean; onClose: (bill?: any) => void }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [q, setQ] = useState("");
  const [client, setClient] = useState<any | null>(null);
  const [newClient, setNewClient] = useState<{ first_name: string; last_name: string; phone: string; gender: string; date_of_birth: string } | null>(null);
  const [studyQ, setStudyQ] = useState("");
  const [studies, setStudies] = useState<any[]>([]);
  const [referredBy, setReferredBy] = useState("");
  const [indication, setIndication] = useState("");
  const reset = () => { setQ(""); setClient(null); setNewClient(null); setStudyQ(""); setStudies([]); setReferredBy(""); setIndication(""); };
  const found = useQuery({ queryKey: ["scancare-client", q], queryFn: () => api.hospital.patients.search(q), enabled: open && q.trim().length >= 2 && !client });
  const cat = useQuery({ queryKey: ["radiology-catalog-search", studyQ], queryFn: () => api.hospital.clinical.searchRadiologyCatalog(studyQ || undefined), enabled: open });
  const matches: any[] = found.data?.patients ?? (Array.isArray(found.data) ? found.data : []);
  const catalogue: any[] = (cat.data?.tests ?? []).filter((t: any) => !studies.some((s) => s.id === t.id));
  const total = studies.reduce((n, s) => n + Number(s.base_price ?? s.price ?? 0), 0);
  const save = useMutation({
    mutationFn: async () => {
      let patient = client;
      if (!patient && newClient) {
        const r = await api.hospital.patients.register({ ...newClient, date_of_birth: newClient.date_of_birth || undefined, address: undefined });
        if (r?.duplicate) throw new Error(`Already registered: ${(r.matches ?? []).map((m: any) => `${m.name} (${m.mrn})`).join(", ")}. Search for them instead.`);
        patient = r.patient;
      }
      if (!patient?.id) throw new Error("Choose or register the client");
      return api.hospital.radiology.scancareWalkIn({ patient_id: patient.id, studies: studies.map((s) => s.id),
        referred_by: referredBy.trim() || undefined, clinical_indication: indication.trim() || undefined });
    },
    onSuccess: (r: any) => {
      toast({ title: `Scancare invoice ${r.bill?.bill_number ?? ""} raised`, description: `${naira(r.bill?.patient_balance)} to pay` });
      void qc.invalidateQueries({ queryKey: ["hospital-bills"] });
      void qc.invalidateQueries({ queryKey: ["radiology-orders"] });
      reset();
      onClose(r.bill);
    },
    onError: (e: any) => toast({ title: "Could not raise the invoice", description: e?.message, variant: "destructive" }),
  });
  const ready = (client || (newClient && newClient.first_name.trim() && newClient.last_name.trim() && newClient.phone.trim())) && studies.length > 0;
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) { reset(); onClose(); } }}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader><DialogTitle>New Scancare walk-in</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label className="text-xs">Client</Label>
            {client ? (
              <div className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
                <span>{client.first_name} {client.last_name} <span className="font-mono text-xs text-muted-foreground">{client.mrn}</span></span>
                <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => setClient(null)}><X className="h-3.5 w-3.5" /></Button>
              </div>
            ) : newClient ? (
              <div className="grid grid-cols-2 gap-2 rounded-md border p-3">
                <Input placeholder="First name" value={newClient.first_name} onChange={(e) => setNewClient({ ...newClient, first_name: e.target.value })} />
                <Input placeholder="Last name" value={newClient.last_name} onChange={(e) => setNewClient({ ...newClient, last_name: e.target.value })} />
                <Input placeholder="Phone" value={newClient.phone} onChange={(e) => setNewClient({ ...newClient, phone: e.target.value })} />
                <select className="h-9 rounded-md border bg-background px-2 text-sm" value={newClient.gender} onChange={(e) => setNewClient({ ...newClient, gender: e.target.value })}>
                  <option value="female">Female</option><option value="male">Male</option></select>
                <div className="col-span-2 flex items-center gap-2"><Label className="text-xs">Date of birth</Label>
                  <Input type="date" className="w-44" value={newClient.date_of_birth} onChange={(e) => setNewClient({ ...newClient, date_of_birth: e.target.value })} />
                  <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setNewClient(null)}>Search instead</Button></div>
              </div>
            ) : (
              <>
                <Input placeholder="Search name, phone or hospital number" value={q} onChange={(e) => setQ(e.target.value)} />
                {matches.slice(0, 6).map((p) => (
                  <button key={p.id} className="block w-full rounded-md border px-3 py-1.5 text-left text-sm hover:bg-muted" onClick={() => setClient(p)}>
                    {p.first_name} {p.last_name} <span className="font-mono text-xs text-muted-foreground">{p.mrn} · {p.phone ?? ""}</span></button>
                ))}
                <Button size="sm" variant="outline" onClick={() => setNewClient({ first_name: "", last_name: "", phone: "", gender: "female", date_of_birth: "" })}>
                  <Plus className="mr-1 h-3.5 w-3.5" /> New client
                </Button>
              </>
            )}
          </div>
          <div className="space-y-2">
            <Label className="text-xs">Studies</Label>
            {studies.map((s) => (
              <div key={s.id} className="flex items-center justify-between rounded-md border px-3 py-1.5 text-sm">
                <span>{s.name}</span><span className="flex items-center gap-2">{naira(s.base_price ?? s.price)}
                  <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => setStudies(studies.filter((x) => x.id !== s.id))}><X className="h-3.5 w-3.5" /></Button></span>
              </div>
            ))}
            <Input placeholder="Search the radiology tariff (e.g. ultrasound pelvis)" value={studyQ} onChange={(e) => setStudyQ(e.target.value)} />
            <div className="max-h-40 overflow-y-auto rounded-md border">
              {catalogue.slice(0, 30).map((t) => (
                <button key={t.id} className="flex w-full justify-between px-3 py-1.5 text-left text-sm hover:bg-muted" onClick={() => setStudies([...studies, t])}>
                  <span>{t.name}</span><span className="text-muted-foreground">{naira(t.base_price ?? t.price)}</span></button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Input placeholder="Referred by (optional)" value={referredBy} onChange={(e) => setReferredBy(e.target.value)} />
            <Input placeholder="Clinical indication (optional)" value={indication} onChange={(e) => setIndication(e.target.value)} />
          </div>
        </div>
        <DialogFooter className="items-center">
          <span className="mr-auto text-sm font-semibold">Total {naira(total)}</span>
          <Button disabled={!ready || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}<ReceiptText className="mr-1 h-4 w-4" /> Raise Scancare invoice
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
