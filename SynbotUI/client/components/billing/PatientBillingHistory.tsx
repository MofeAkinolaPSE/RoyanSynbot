import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, Loader2, Receipt, CreditCard, FileText, Wallet } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RecordTable, CellStack } from "@/components/patient/RecordTable";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";

/**
 * Search any patient and read their complete billing history.
 *
 * Two gaps this closes:
 *
 *  1. The billing page had no search at all. Patient scoping only happened via
 *     a ?patient_id= link produced in one place on the patient chart, so you
 *     had to already be inside a chart to see anyone's bills.
 *
 *  2. The bills worklist deliberately excludes migrated rows
 *     (billing_hospital.py filters external_source IS NULL) so a decade of Hope
 *     history cannot masquerade as actionable work. That is the right rule for
 *     a worklist and the wrong one for "show me this patient's account", so
 *     this reads the archive endpoint instead.
 *
 * It also renders receipts and card transactions, which the patient chart has
 * been fetching over the wire and discarding — 50,820 and 29,357 rows with no
 * reader anywhere in the app.
 */

const naira = (v: any) =>
  v == null || v === "" ? "—" : `₦${Number(v).toLocaleString("en-NG")}`;

const fmtDate = (ts?: string | null) =>
  ts ? new Date(ts).toLocaleDateString("en-NG", { day: "numeric", month: "short", year: "numeric" }) : "—";

export function PatientBillingHistory({
  initialPatientId,
}: {
  initialPatientId?: number;
}) {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [patient, setPatient] = useState<any | null>(
    initialPatientId ? { id: initialPatientId } : null,
  );
  const [section, setSection] = useState<"transactions" | "summaries" | "receipts" | "cards">("transactions");

  const { data: searchData, isFetching: searching } = useQuery({
    queryKey: ["billing-patient-search", debounced],
    queryFn: () => api.hospital.patients.search(debounced),
    enabled: !patient && debounced.trim().length >= 2,
  });
  const results: any[] = Array.isArray(searchData) ? searchData : (searchData?.patients ?? []);

  const { data, isLoading } = useQuery({
    queryKey: ["billing-history", patient?.id],
    queryFn: () => api.hospital.clinical.listBillingHistory(patient.id),
    enabled: !!patient?.id,
  });

  const transactions: any[] = data?.transactions ?? [];
  const summaries: any[] = data?.summaries ?? [];
  const receipts: any[] = data?.receipts ?? [];
  const cards: any[] = data?.card_transactions ?? [];

  // Outstanding is the sum of what the record still shows as pending. It is a
  // prompt to check the account, not a figure to hand the patient.
  const outstanding = summaries.reduce((n, s) => n + Number(s.amount_pending ?? 0), 0);
  const billed = summaries.reduce((n, s) => n + Number(s.total_amount ?? s.net_amount ?? 0), 0);

  if (!patient) {
    return (
      <Card>
        <CardContent className="space-y-3 p-6">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              autoFocus
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setDebounced(e.target.value);
              }}
              placeholder="Search a patient by name, MRN or phone…"
              className="pl-8"
            />
          </div>

          {searching && (
            <div className="flex justify-center py-6">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          )}

          {!searching && debounced.trim().length >= 2 && results.length === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No patient matches that search.
            </p>
          )}

          {results.length > 0 && (
            <ul className="divide-y rounded-md border">
              {results.slice(0, 20).map((p: any) => (
                <li key={p.id}>
                  <button
                    onClick={() => setPatient(p)}
                    className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition-colors hover:bg-muted/50"
                  >
                    <span className="text-sm font-medium">
                      {p.first_name} {p.last_name}
                    </span>
                    <span className="font-mono text-xs text-muted-foreground">{p.mrn}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {debounced.trim().length < 2 && (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Search a patient to see their full account, including bills from before go-live.
            </p>
          )}
        </CardContent>
      </Card>
    );
  }

  const SECTIONS = [
    { key: "transactions" as const, label: "Transactions", icon: Receipt, count: transactions.length },
    { key: "summaries" as const, label: "Bill summaries", icon: FileText, count: summaries.length },
    { key: "receipts" as const, label: "Receipts", icon: Wallet, count: receipts.length },
    { key: "cards" as const, label: "Card / instruments", icon: CreditCard, count: cards.length },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <p className="text-sm font-semibold">
            {patient.first_name ? `${patient.first_name} ${patient.last_name}` : `Patient ${patient.id}`}
          </p>
          {patient.mrn && <p className="font-mono text-xs text-muted-foreground">{patient.mrn}</p>}
        </div>
        <Button variant="outline" size="sm" onClick={() => { setPatient(null); setQuery(""); setDebounced(""); }}>
          Change patient
        </Button>
        <div className="ml-auto flex gap-4 text-right">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Total billed</p>
            <p className="text-lg font-bold tabular-nums">{naira(billed)}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Outstanding</p>
            <p className={cn("text-lg font-bold tabular-nums", outstanding > 0 && "text-amber-600")}>
              {naira(outstanding)}
            </p>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {SECTIONS.map((sec) => (
          <button
            key={sec.key}
            onClick={() => setSection(sec.key)}
            className={cn(
              "flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors",
              section === sec.key
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border hover:bg-muted",
            )}
          >
            <sec.icon className="h-3 w-3" />
            {sec.label}
            <Badge variant="outline" className="ml-0.5 h-5 border-current px-1 text-xs font-normal">
              {sec.count}
            </Badge>
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : section === "transactions" ? (
        <RecordTable
          rows={transactions}
          rowKey={(r: any, i) => r.id ?? i}
          emptyIcon={<Receipt className="h-6 w-6" />}
          emptyLabel="No billing transactions recorded"
          columns={[
            { header: "Bill", cell: (r: any) => <CellStack primary={r.bill_number ?? "—"} secondary={r.remark} mono /> },
            { header: "Description", cell: (r: any) => r.particulars ?? r.description ?? "—" },
            { header: "Amount", width: "w-[130px]", className: "tabular-nums", cell: (r: any) => naira(r.amount) },
            { header: "Mode", width: "w-[120px]", className: "capitalize text-muted-foreground", cell: (r: any) => r.payment_mode ?? "—" },
            { header: "Date", width: "w-[130px]", className: "text-muted-foreground", cell: (r: any) => fmtDate(r.billed_at ?? r.created_at) },
          ]}
        />
      ) : section === "summaries" ? (
        <RecordTable
          rows={summaries}
          rowKey={(r: any, i) => r.id ?? i}
          emptyIcon={<FileText className="h-6 w-6" />}
          emptyLabel="No bill summaries recorded"
          accent={(r: any) => (Number(r.amount_pending ?? 0) > 0 ? "border-l-amber-500" : undefined)}
          columns={[
            { header: "Bill", cell: (r: any) => <CellStack primary={r.bill_number ?? "—"} secondary={r.bill_type} mono /> },
            { header: "Total", width: "w-[130px]", className: "tabular-nums", cell: (r: any) => naira(r.total_amount ?? r.net_amount) },
            { header: "Paid", width: "w-[130px]", className: "tabular-nums", cell: (r: any) => naira(r.amount_paid) },
            {
              header: "Outstanding",
              width: "w-[130px]",
              cell: (r: any) => (
                <span className={cn("tabular-nums", Number(r.amount_pending ?? 0) > 0 && "font-semibold text-amber-600")}>
                  {naira(r.amount_pending)}
                </span>
              ),
            },
            { header: "Date", width: "w-[130px]", className: "text-muted-foreground", cell: (r: any) => fmtDate(r.billed_at ?? r.created_at) },
          ]}
        />
      ) : section === "receipts" ? (
        <RecordTable
          rows={receipts}
          rowKey={(r: any, i) => r.id ?? i}
          emptyIcon={<Wallet className="h-6 w-6" />}
          emptyLabel="No receipts recorded"
          columns={[
            { header: "Receipt", cell: (r: any) => <CellStack primary={r.receipt_number ?? "—"} secondary={r.remark} mono /> },
            { header: "Amount", width: "w-[130px]", className: "tabular-nums", cell: (r: any) => naira(r.amount) },
            { header: "Mode", width: "w-[120px]", className: "capitalize text-muted-foreground", cell: (r: any) => r.payment_mode ?? "—" },
            { header: "Received", width: "w-[130px]", className: "text-muted-foreground", cell: (r: any) => fmtDate(r.received_at ?? r.created_at) },
          ]}
        />
      ) : (
        <RecordTable
          rows={cards}
          rowKey={(r: any, i) => r.id ?? i}
          emptyIcon={<CreditCard className="h-6 w-6" />}
          emptyLabel="No card transactions recorded"
          columns={[
            { header: "Reference", cell: (r: any) => <CellStack primary={r.card_number ?? r.reference ?? "—"} secondary={r.remark} mono /> },
            { header: "Amount", width: "w-[130px]", className: "tabular-nums", cell: (r: any) => naira(r.amount) },
            { header: "Type", width: "w-[120px]", className: "capitalize text-muted-foreground", cell: (r: any) => r.transaction_type ?? "—" },
            { header: "Date", width: "w-[130px]", className: "text-muted-foreground", cell: (r: any) => fmtDate(r.transacted_at ?? r.created_at) },
          ]}
        />
      )}
    </div>
  );
}
