import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  CreditCard,
  CheckCircle2,
  Clock,
  XCircle,
  RefreshCw,
  Plus,
  ExternalLink,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { AlertBanner } from "@/components/AlertBanner";
import { api } from "@/lib/api-client";

const motionTransitions = {
  fadeInUp: {
    initial: { opacity: 0, y: 18 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.35, ease: "easeOut" },
  },
};

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  initiated: { label: "Initiated",  className: "bg-blue-50   text-blue-700   border-blue-200" },
  pending:   { label: "Pending",    className: "bg-yellow-50 text-yellow-700 border-yellow-200" },
  success:   { label: "Success",    className: "bg-green-50  text-green-700  border-green-200" },
  failed:    { label: "Failed",     className: "bg-red-50    text-red-700    border-red-200" },
  reversed:  { label: "Reversed",   className: "bg-gray-50   text-gray-700   border-gray-200" },
};

const GATEWAY_BADGE: Record<string, string> = {
  paystack:    "bg-teal-50 text-teal-700 border-teal-200",
  flutterwave: "bg-orange-50 text-orange-700 border-orange-200",
  stripe:      "bg-purple-50 text-purple-700 border-purple-200",
};

function KpiCard({ label, value, sub, icon: Icon, color = "blue" }: {
  label: string; value: string | number; sub?: string; icon: React.ElementType; color?: string;
}) {
  const colors: Record<string, string> = {
    blue:   "bg-blue-50 text-blue-600",
    green:  "bg-green-50 text-green-600",
    orange: "bg-orange-50 text-orange-600",
    red:    "bg-red-50 text-red-600",
  };
  return (
    <Card>
      <CardContent className="p-4 flex items-center gap-4">
        <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${colors[color] ?? colors.blue}`}>
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <div className="text-2xl font-bold">{value}</div>
          <div className="text-xs text-muted-foreground">{label}</div>
          {sub && <div className="text-[13px] text-muted-foreground/70">{sub}</div>}
        </div>
      </CardContent>
    </Card>
  );
}

const emptyForm = {
  gateway: "paystack",
  amount: "",
  email: "",
  patient_id: "",
  encounter_id: "",
  description: "",
  callback_url: "",
};

export default function PaymentGateway() {
  const { toast } = useToast();
  const qc        = useQueryClient();

  const [filterStatus,  setFilterStatus]  = useState("all");
  const [filterGateway, setFilterGateway] = useState("all");
  const [showInitiate,  setShowInitiate]  = useState(false);
  const [form, setForm] = useState({ ...emptyForm });
  const [gatewayData,  setGatewayData]   = useState<any>(null);
  const [verifyRef,    setVerifyRef]      = useState("");

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["payments-list", filterStatus, filterGateway],
    queryFn:  () => api.payments.list({
      status:  filterStatus  !== "all" ? filterStatus  : undefined,
      gateway: filterGateway !== "all" ? filterGateway : undefined,
    }),
  });

  const txns = data?.transactions ?? [];

  const successCount  = txns.filter((t: any) => t.status === "success").length;
  const pendingCount  = txns.filter((t: any) => ["initiated","pending"].includes(t.status)).length;
  const failedCount   = txns.filter((t: any) => t.status === "failed").length;
  const totalReceived = txns
    .filter((t: any) => t.status === "success")
    .reduce((s: number, t: any) => s + (t.amount || 0), 0);

  const initiateMut = useMutation({
    mutationFn: (p: Record<string, any>) => api.payments.initiate(p),
    onSuccess: (res) => {
      setGatewayData(res.gateway_data);
      qc.invalidateQueries({ queryKey: ["payments-list"] });
      toast({ title: "Payment initiated", description: `Reference: ${res.reference}` });
    },
    onError: (e: any) => toast({ variant: "destructive", title: "Failed", description: e?.message }),
  });

  const verifyMut = useMutation({
    mutationFn: (ref: string) => api.payments.verify(ref),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["payments-list"] });
      toast({ title: "Verified", description: `Status: ${res.status}` });
    },
    onError: (e: any) => toast({ variant: "destructive", title: "Verify failed", description: e?.message }),
  });

  const handleInitiate = () => {
    const payload: Record<string, any> = {
      gateway:     form.gateway,
      amount:      Number(form.amount),
      email:       form.email,
      description: form.description || undefined,
      callback_url: form.callback_url || undefined,
    };
    if (form.patient_id)   payload.patient_id   = Number(form.patient_id);
    if (form.encounter_id) payload.encounter_id = Number(form.encounter_id);
    initiateMut.mutate(payload);
  };

  const f = (s: string | undefined) => STATUS_BADGE[s ?? ""] ?? { label: s ?? "", className: "bg-muted text-foreground border-border" };

  return (
    <motion.div {...motionTransitions.fadeInUp} className="space-y-4 p-4 md:p-6">
      <AlertBanner />

      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Payment Gateway</h1>
          <p className="text-sm text-muted-foreground">Paystack &amp; Flutterwave transactions — initiate, verify, and track</p>
        </div>
        <Button size="sm" onClick={() => { setShowInitiate(true); setGatewayData(null); setForm({ ...emptyForm }); }}>
          <Plus className="h-4 w-4 mr-1.5" /> Initiate Payment
        </Button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="Total Received"  value={"₦" + totalReceived.toLocaleString()} icon={CreditCard}  color="green" />
        <KpiCard label="Successful"      value={successCount}  icon={CheckCircle2} color="green"  sub="transactions" />
        <KpiCard label="Pending"         value={pendingCount}  icon={Clock}        color="orange" sub="awaiting confirmation" />
        <KpiCard label="Failed"          value={failedCount}   icon={XCircle}      color="red"    sub="transactions" />
      </div>

      {/* Verify bar */}
      <Card>
        <CardContent className="pt-4 pb-4 flex flex-wrap gap-2 items-end">
          <div>
            <Label className="text-xs mb-1 block">Verify by Reference</Label>
            <Input
              value={verifyRef}
              onChange={e => setVerifyRef(e.target.value)}
              placeholder="ROY-XXXXXXXXXXXX"
              className="w-56 h-8 text-sm font-mono"
            />
          </div>
          <Button
            size="sm" variant="outline"
            onClick={() => { if (verifyRef.trim()) verifyMut.mutate(verifyRef.trim()); }}
            disabled={verifyMut.isPending || !verifyRef.trim()}
          >
            <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${verifyMut.isPending ? "animate-spin" : ""}`} />
            Verify
          </Button>
        </CardContent>
      </Card>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <Select value={filterStatus} onValueChange={setFilterStatus}>
          <SelectTrigger className="h-8 w-36 text-sm"><SelectValue placeholder="Status" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {["initiated","pending","success","failed","reversed"].map(s => (
              <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={filterGateway} onValueChange={setFilterGateway}>
          <SelectTrigger className="h-8 w-36 text-sm"><SelectValue placeholder="Gateway" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All gateways</SelectItem>
            <SelectItem value="paystack">Paystack</SelectItem>
            <SelectItem value="flutterwave">Flutterwave</SelectItem>
            <SelectItem value="stripe">Stripe</SelectItem>
          </SelectContent>
        </Select>
        <Button size="sm" variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isFetching ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/40">
                  {["Reference","Gateway","Amount","Email","Patient","Status","Initiated","Actions"].map(h => (
                    <th key={h} className="px-4 py-2.5 text-left font-medium text-muted-foreground text-xs">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {txns.length === 0 && !isFetching && (
                  <tr><td colSpan={8} className="text-center py-10 text-muted-foreground text-sm">No transactions found.</td></tr>
                )}
                {txns.map((t: any) => {
                  const st = f(t.status);
                  return (
                    <tr key={t.id} className="border-b hover:bg-muted/20">
                      <td className="px-4 py-2.5 font-mono text-xs">{t.reference}</td>
                      <td className="px-4 py-2.5">
                        <Badge variant="outline" className={`text-[12px] ${GATEWAY_BADGE[t.gateway] ?? ""}`}>
                          {t.gateway}
                        </Badge>
                      </td>
                      <td className="px-4 py-2.5 font-medium">₦{(t.amount ?? 0).toLocaleString()}</td>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground">{t.email}</td>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground">{t.patient_id ?? "—"}</td>
                      <td className="px-4 py-2.5">
                        <Badge variant="outline" className={`text-[12px] ${st.className}`}>{st.label}</Badge>
                      </td>
                      <td className="px-4 py-2.5 text-xs text-muted-foreground">
                        {t.initiated_at ? new Date(t.initiated_at).toLocaleDateString() : "—"}
                      </td>
                      <td className="px-4 py-2.5">
                        <Button
                          size="sm" variant="ghost" className="h-7 px-2 text-xs"
                          onClick={() => verifyMut.mutate(t.reference)}
                          disabled={verifyMut.isPending}
                        >
                          <RefreshCw className="h-3 w-3 mr-1" /> Verify
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Initiate Dialog */}
      <Dialog open={showInitiate} onOpenChange={setShowInitiate}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Initiate Payment</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Gateway</Label>
              <Select value={form.gateway} onValueChange={v => setForm(f => ({ ...f, gateway: v }))}>
                <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="paystack">Paystack</SelectItem>
                  <SelectItem value="flutterwave">Flutterwave</SelectItem>
                  <SelectItem value="stripe">Stripe</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Amount (₦)</Label>
                <Input
                  type="number" value={form.amount}
                  onChange={e => setForm(f => ({ ...f, amount: e.target.value }))}
                  className="h-9" placeholder="5000"
                />
              </div>
              <div>
                <Label className="text-xs">Patient Email</Label>
                <Input
                  value={form.email}
                  onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                  className="h-9" placeholder="patient@email.com"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Patient ID (optional)</Label>
                <Input
                  type="number" value={form.patient_id}
                  onChange={e => setForm(f => ({ ...f, patient_id: e.target.value }))}
                  className="h-9" placeholder="123"
                />
              </div>
              <div>
                <Label className="text-xs">Encounter ID (optional)</Label>
                <Input
                  type="number" value={form.encounter_id}
                  onChange={e => setForm(f => ({ ...f, encounter_id: e.target.value }))}
                  className="h-9" placeholder="456"
                />
              </div>
            </div>
            <div>
              <Label className="text-xs">Description</Label>
              <Input
                value={form.description}
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                className="h-9" placeholder="Consultation fee"
              />
            </div>

            {gatewayData && !gatewayData.stub && (
              <div className="rounded-lg border bg-green-50 p-3 text-sm">
                <p className="font-medium text-green-700 mb-1">Payment link generated</p>
                <a
                  href={gatewayData.authorization_url || gatewayData.link}
                  target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-blue-600 underline"
                >
                  Open checkout <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            )}
            {gatewayData?.stub && (
              <div className="rounded-lg border bg-yellow-50 p-3 text-xs text-yellow-700">
                <p className="font-medium mb-0.5">Stub mode — no live keys configured</p>
                <p>Reference: <span className="font-mono">{gatewayData.reference || gatewayData.tx_ref}</span></p>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" size="sm" onClick={() => setShowInitiate(false)}>Cancel</Button>
              <Button
                size="sm"
                onClick={handleInitiate}
                disabled={initiateMut.isPending || !form.amount || !form.email}
              >
                {initiateMut.isPending ? "Initiating…" : "Initiate"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}
