import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DetailSheet } from "@/components/workspace/DetailSheet";
import { act, Amount, CsvButton, Empty, ErrorNote, Loading, Section, Stat, useBooks } from "@/components/books/kit";
import { books, Dict, fmtDate, naira, num, today } from "@/lib/books-api";
import { askConfirm } from "@/lib/ask";


/** Where the store screens read and write: Roy Books (finance's view, can put a store in the books) or the departments'
 *  own Department stores page (/stock/stores - the people who keep the stock). */
export type StoreApi = { prefix: string; get: (path: string, params?: Dict) => Promise<any>; post: (path: string, body: Dict) => Promise<any>; finance: boolean };
export const BOOKS_STORE_API: StoreApi = { prefix: "books", get: (p, params) => books.get(p, params), post: (p, b) => books.post(p, b), finance: true };
export const StoreApiContext = createContext<StoreApi>(BOOKS_STORE_API);
function useStore<T = any>(key: unknown[], path: string, params?: Dict, enabled = true) {
  const api = useContext(StoreApiContext);
  return useQuery<T>({ queryKey: [api.prefix, path, ...key, params], queryFn: () => api.get(path, params), enabled, staleTime: 0 });
}

export const DEPT_LABEL: Record<string, string> = {
  PHARMACY: "Pharmacy", LAB: "Laboratory", UROLOGY: "Urology", WARD: "Ward", THEATRE: "Theatre",
  PHYSIOTHERAPY: "Physiotherapy", CENTRAL_STORES: "Central stores", IMMUNISATION: "Immunisation",
};
const MOVES: { value: string; label: string; hint: string }[] = [
  { value: "ISSUE", label: "Used / issued", hint: "Stock used in the department - reduces the shelf" },
  { value: "COUNT", label: "Counted", hint: "Enter the quantity counted on the shelf; the difference is adjusted" },
  { value: "RECEIVE", label: "Received", hint: "A delivery into the store - adds to the shelf" },
  { value: "EXPIRED", label: "Expired", hint: "Write off expired stock" },
  { value: "DAMAGED", label: "Damaged", hint: "Write off damaged stock" },
  { value: "RETURN_TO_SUPPLIER", label: "Returned to supplier", hint: "Goes back to the supplier (record the supplier's credit in Purchases)" },
  { value: "CORRECTION", label: "Correction (+/-)", hint: "A signed correction, e.g. -2 or 5" },
];

/** The department every Stock tab reads: Pharmacy and each department store (listed even while empty). */
export function DeptBar({ value, onChange }: { value: string; onChange: (d: string) => void }) {
  const { data } = useStore<Dict>(["departments"], "/inventory/departments");
  const depts: Dict[] = [{ department: "PHARMACY", name: "Pharmacy" }, ...(data?.departments ?? [])];
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-muted-foreground">Department</span>
      {depts.map((d) => (
        <button key={d.department} onClick={() => onChange(d.department)}
                className={`rounded-full border px-3 py-1 text-sm ${value === d.department ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted"}`}>
          {d.name ?? DEPT_LABEL[d.department] ?? d.department}{d.batches ? <span className="ml-1 text-xs opacity-70">{d.batches}</span> : null}
        </button>
      ))}
    </div>
  );
}

/** Stock by department: every item on the chosen department's shelves; click a row (or Adjust) to work with it. */
export function DepartmentStock({ dept, onAdjustPharmacy, onItem }: { dept: string; onAdjustPharmacy: (p: Dict) => void; onItem: (sku: string) => void }) {
  const qc = useQueryClient();
  const api = useContext(StoreApiContext);
  const { data, isLoading, error } = useStore<Dict>(["departments"], "/inventory/departments");
  const [adjusting, setAdjusting] = useState<Dict | null>(null);
  const [adding, setAdding] = useState(false);
  const depts: Dict[] = data?.departments ?? [];
  const cur = depts.find((d) => d.department === dept);
  const confirm = async () => {
    if (!(await askConfirm(`Put ${DEPT_LABEL[dept] ?? dept} stock in the books?\nOnly after the store has been counted. The unexpired stock on the shelves (${naira(Number(cur?.value ?? 0) - Number(cur?.expired_value ?? 0))}) is posted to inventory; from then on every movement posts a journal.`))) return;
    if (await act(() => books.post(`/inventory/departments/${dept}/confirm`, {}), "Stock put in the books")) qc.invalidateQueries({ queryKey: [api.prefix] });
  };
  return (
    <div className="space-y-4">
      {isLoading && <Loading />}<ErrorNote error={error} />
      <div className="flex justify-end">
        <Button size="sm" variant="outline" onClick={() => setAdding(true)}><Plus className="mr-1 h-4 w-4" />Add item to {dept === "PHARMACY" ? "a store" : DEPT_LABEL[dept] ?? dept}</Button>
      </div>
      {dept === "PHARMACY" ? (api.finance ? <PharmacyStock position={data?.pharmacy} onAdjust={onAdjustPharmacy} onItem={onItem} /> : (
        <div className="rounded-lg border px-4 py-3 text-sm">Pharmacy stock is kept in <a className="font-medium text-primary underline" href="#/hospital/pharmacy/inventory">Pharmacy › Inventory</a>. Choose a department above for its store.</div>
      )) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="On the shelves (cost)" value={<Amount value={cur?.value} bold />} sub={`${num(cur?.items)} items · ${num(cur?.batches)} batches`} />
            <Stat label="Expired" value={<Amount value={cur?.expired_value} bold />} sub={`${num(cur?.expired_batches)} batches`} tone={Number(cur?.expired_value) > 0 ? "bad" : undefined} />
            <Stat label="In the books" value={cur?.in_books ? "Yes" : "Not yet"} tone={cur?.in_books ? "good" : "warn"}
                  sub={cur?.in_books ? "every movement posts a journal" : "count the store, then put it in the books"} />
            <Stat label="Last movement" value={cur?.last_movement ? fmtDate(cur.last_movement) : "—"} />
          </div>
          {Number(cur?.batches ?? 0) === 0 && (
            <div className="rounded-lg border px-4 py-3 text-sm">
              Nothing is recorded on the {DEPT_LABEL[dept] ?? dept} shelves yet. Add each item with <span className="font-medium">Add item</span> (or count the store),
              then put the store in the books.
            </div>
          )}
          {!cur?.in_books && cur && Number(cur.batches) > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm dark:border-amber-500/40 dark:bg-amber-500/10">
              <span>These figures came from Hope's {DEPT_LABEL[dept] ?? dept} store and have not been counted. Count each item (Adjust › Counted), write off what has expired, then put the store in the books.</span>
              {api.finance ? <Button size="sm" onClick={confirm}>Put in the books</Button>
                : <span className="text-xs text-muted-foreground">Finance puts the store in the books after the count.</span>}
            </div>
          )}
          <DeptItems dept={dept} onAdjust={setAdjusting} />
          <DeptUsage dept={dept} />
        </>
      )}
      <DeptAdjust item={adjusting} onClose={() => setAdjusting(null)} />
      <DeptAdd open={adding} dept={dept === "PHARMACY" ? "LAB" : dept} onClose={() => setAdding(false)} />
    </div>
  );
}

function PharmacyStock({ position, onAdjust, onItem }: { position?: Dict; onAdjust: (p: Dict) => void; onItem: (sku: string) => void }) {
  const [search, setSearch] = useState("");
  const { data, isLoading, error } = useBooks<Dict[]>(["stock-status"], "/reports/stock-status");
  const rows = useMemo(() => (data ?? []).filter((r) => (Number(r.on_hand) !== 0 || Number(r.shelf_on_hand) !== 0) &&
    (!search || `${r.sku} ${r.name}`.toLowerCase().includes(search.toLowerCase()))), [data, search]);
  return (
    <>
      {position && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Stat label="In the books (FIFO cost)" value={<Amount value={position.books_value} bold />} sub={`${num(position.books_products)} products`} />
          <Stat label="On the shelves (cost)" value={<Amount value={position.shelf_value} bold />} sub={`${num(position.shelf_batches)} batches`} />
          <Stat label="Books less shelves" value={<Amount value={position.difference} bold />} tone={Math.abs(Number(position.difference)) >= 1 ? "bad" : "good"}
                sub={Math.abs(Number(position.difference)) >= 1 ? "explain with a count or adjustment" : "books and shelves agree"} />
          <Stat label="Expired on the shelf" value={<Amount value={position.expired_value} bold />} tone={Number(position.expired_value) > 0 ? "bad" : undefined}
                sub={`${naira(position.expiring_90_value)} more within 90 days`} />
        </div>
      )}
      <Section title={`Pharmacy stock (${rows.length})`} actions={<CsvButton filename="pharmacy-stock.csv" rows={rows} />}>
        <Input className="mb-3 h-9 max-w-xs" placeholder="Search SKU or product" value={search} onChange={(e) => setSearch(e.target.value)} />
        {isLoading && <Loading />}<ErrorNote error={error} />
        {data && (rows.length === 0 ? <Empty>No pharmacy stock.</Empty> : (
          <Table>
            <TableHeader><TableRow>
              <TableHead>SKU</TableHead><TableHead>Product</TableHead><TableHead className="text-right">In books</TableHead><TableHead className="text-right">Value</TableHead>
              <TableHead className="text-right">On shelves</TableHead><TableHead>Nearest expiry</TableHead><TableHead />
            </TableRow></TableHeader>
            <TableBody>{rows.map((r) => (
              <TableRow key={r.sku}>
                <TableCell className="cursor-pointer font-mono text-xs underline-offset-2 hover:underline" onClick={() => onItem(r.sku)}>{r.sku}</TableCell>
                <TableCell className="max-w-[260px] truncate">{r.name}</TableCell>
                <TableCell className={`text-right ${Number(r.on_hand) < 0 ? "text-red-600" : ""}`}>{num(r.on_hand)}</TableCell>
                <TableCell className="text-right"><Amount value={r.value} blankZero /></TableCell>
                <TableCell className="text-right text-muted-foreground">{num(r.shelf_on_hand)}{Number(r.shelf_expired_qty) > 0 && <span className="ml-1 text-xs text-red-600">({num(r.shelf_expired_qty)} expired)</span>}</TableCell>
                <TableCell className={(r.nearest_expiry ?? r.shelf_nearest_expiry) && (r.nearest_expiry ?? r.shelf_nearest_expiry) < today() ? "text-red-600" : ""}>
                  {(r.nearest_expiry ?? r.shelf_nearest_expiry) ? fmtDate(r.nearest_expiry ?? r.shelf_nearest_expiry) : "—"}
                </TableCell>
                <TableCell><Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => onAdjust({ sku: r.sku, name: r.name, on_hand: r.on_hand })}>Adjust</Button></TableCell>
              </TableRow>
            ))}</TableBody>
          </Table>
        ))}
      </Section>
    </>
  );
}

function DeptItems({ dept, onAdjust }: { dept: string; onAdjust: (r: Dict) => void }) {
  const [search, setSearch] = useState("");
  const [expired, setExpired] = useState("all");
  const { data, isLoading, error } = useStore<Dict[]>(["dept-items", dept], `/inventory/departments/${dept}`);
  const rows = (data ?? []).filter((r) => (!search || `${r.item_name} ${r.item_code ?? ""} ${r.batch_number ?? ""}`.toLowerCase().includes(search.toLowerCase()))
    && (expired === "all" || (expired === "expired" ? r.expired : !r.expired)));
  return (
    <Section title={`${DEPT_LABEL[dept] ?? dept} stock (${rows.length})`} actions={<CsvButton filename={`${dept.toLowerCase()}-stock.csv`} rows={rows} />}>
      <div className="mb-3 flex flex-wrap gap-2">
        <Input className="h-9 max-w-xs" placeholder="Search item or batch" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="h-9 rounded-md border bg-background px-2 text-sm" value={expired} onChange={(e) => setExpired(e.target.value)}>
          <option value="all">All batches</option><option value="good">In date</option><option value="expired">Expired</option>
        </select>
      </div>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {data && (rows.length === 0 ? <Empty>Nothing on this store's shelves.</Empty> : (
        <Table>
          <TableHeader><TableRow>
            <TableHead>Item</TableHead><TableHead>Batch</TableHead><TableHead>Expiry</TableHead><TableHead className="text-right">Qty</TableHead>
            <TableHead className="text-right">Unit cost</TableHead><TableHead className="text-right">Value</TableHead><TableHead />
          </TableRow></TableHeader>
          <TableBody>{rows.map((r) => (
            <TableRow key={r.id} className={`cursor-pointer hover:bg-muted/50 ${r.expired ? "text-red-600" : ""}`} onClick={() => onAdjust(r)}>
              <TableCell className="max-w-[280px] truncate">{r.item_name}{r.item_code && <span className="block font-mono text-xs text-muted-foreground">{r.item_code}</span>}</TableCell>
              <TableCell className="font-mono text-xs">{r.batch_number ?? "—"}</TableCell>
              <TableCell>{r.expiry_date ? fmtDate(r.expiry_date) : "—"}</TableCell>
              <TableCell className="text-right">{num(r.quantity)}</TableCell>
              <TableCell className="text-right">{r.unit_cost ? <Amount value={r.unit_cost} /> : <span className="text-xs text-amber-600">no cost</span>}</TableCell>
              <TableCell className="text-right"><Amount value={r.value} blankZero /></TableCell>
              <TableCell><Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => onAdjust(r)}>Adjust</Button></TableCell>
            </TableRow>
          ))}</TableBody>
        </Table>
      ))}
    </Section>
  );
}

export function DeptAdjust({ item: given, onClose }: { item: Dict | null; onClose: () => void }) {
  const qc = useQueryClient();
  const api = useContext(StoreApiContext);
  // the batch being worked on (an item can have several batches on the shelf); its full record is loaded
  const [batchId, setBatchId] = useState<number | null>(null);
  useEffect(() => setBatchId(given?.id ?? null), [given?.id]);
  const { data: full } = useStore<Dict>(["dept-item", batchId], `/inventory/department-stock/${batchId}`, undefined, !!given && batchId != null);
  const item: Dict | null = given ? { ...given, ...(full ?? {}) } : null;
  const [f, setF] = useState({ move_type: "ISSUE", quantity: "", unit_cost: "", reason: "", batch_number: "", expiry_date: "" });
  const [busy, setBusy] = useState(false);
  const { data: history } = useStore<Dict[]>(["dept-moves", item?.id], `/inventory/department-stock/${item?.id}/moves`, undefined, !!item);
  const move = MOVES.find((m) => m.value === f.move_type)!;
  const q = Number(f.quantity || 0);
  const cur = Number(item?.quantity ?? 0);
  const after = f.move_type === "COUNT" ? q : f.move_type === "RECEIVE" ? cur + Math.abs(q)
    : f.move_type === "CORRECTION" ? cur + q : cur - Math.abs(q);
  const cost = Number(f.unit_cost || item?.unit_cost || 0);
  const submit = async () => {
    setBusy(true);
    const r = await act(() => api.post(`/inventory/department-stock/${item!.id}/adjust`, {
      move_type: f.move_type, quantity: f.quantity, reason: f.reason, unit_cost: f.unit_cost || undefined,
      batch_number: f.batch_number || undefined, expiry_date: f.expiry_date || undefined }), "Stock updated");
    setBusy(false);
    if (r) { qc.invalidateQueries({ queryKey: [api.prefix] }); setF({ move_type: "ISSUE", quantity: "", unit_cost: "", reason: "", batch_number: "", expiry_date: "" }); onClose(); }
  };
  return (
    <DetailSheet open={!!item} onOpenChange={(o) => !o && onClose()} title={item ? `Adjust: ${item.item_name}` : ""}
                 description={item ? `${DEPT_LABEL[item.department] ?? item.department} · batch ${item.batch_number ?? "—"} · ${num(item.quantity)} on the shelf` : undefined}
                 footer={<Button disabled={busy || !f.quantity || !f.reason.trim() || after < 0 || after === cur} onClick={submit}>{busy ? "Saving…" : "Save movement"}</Button>}>
      {item && (
        <div className="space-y-3">
          {(full?.batches ?? []).length > 1 && (
            <div className="space-y-1"><Label className="text-xs">Batch</Label>
              <select className="h-9 w-full rounded-md border bg-background px-2 text-sm" value={String(batchId ?? "")} onChange={(e) => setBatchId(Number(e.target.value))}>
                {full!.batches.map((b: Dict) => <option key={b.id} value={b.id}>{b.batch_number ?? "no batch no."} · expires {b.expiry_date ? fmtDate(b.expiry_date) : "—"} · {num(b.quantity)} on the shelf</option>)}
              </select></div>
          )}
          <div className="grid grid-cols-3 gap-2 rounded-md border px-3 py-2 text-xs">
            <div>On the shelf<div className="text-sm font-semibold">{num(item.quantity)}</div></div>
            <div>Unit cost<div className="text-sm font-semibold">{item.unit_cost ? naira(item.unit_cost) : "none"}</div></div>
            <div>In the books<div className="text-sm font-semibold">{item.in_books ? "Yes" : "Not yet"}</div></div>
          </div>
          <div className="space-y-1"><Label className="text-xs">What happened</Label>
            <select className="h-9 w-full rounded-md border bg-background px-2 text-sm" value={f.move_type} onChange={(e) => setF({ ...f, move_type: e.target.value })}>
              {MOVES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            <p className="text-xs text-muted-foreground">{move.hint}</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1"><Label className="text-xs">{f.move_type === "COUNT" ? "Quantity counted" : "Quantity"}</Label>
              <Input type="number" value={f.quantity} onChange={(e) => setF({ ...f, quantity: e.target.value })} /></div>
            <div className="space-y-1"><Label className="text-xs">Unit cost {f.move_type === "RECEIVE" ? "" : "(blank = current)"}</Label>
              <Input type="number" placeholder={item.unit_cost ? String(item.unit_cost) : "0"} value={f.unit_cost} onChange={(e) => setF({ ...f, unit_cost: e.target.value })} /></div>
          </div>
          {f.move_type === "RECEIVE" && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1"><Label className="text-xs">Batch (if new)</Label><Input value={f.batch_number} onChange={(e) => setF({ ...f, batch_number: e.target.value })} /></div>
              <div className="space-y-1"><Label className="text-xs">Expiry</Label><Input type="date" value={f.expiry_date} onChange={(e) => setF({ ...f, expiry_date: e.target.value })} /></div>
            </div>
          )}
          <div className="space-y-1"><Label className="text-xs">Reason</Label><Input placeholder="e.g. Used for FBC runs this week, monthly count" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></div>
          {f.quantity && (
            <div className={`rounded-md border px-3 py-2 text-sm ${after < 0 ? "border-red-400 text-red-600" : ""}`}>
              {num(cur)} → <span className="font-semibold">{num(after)}</span> on the shelf · {naira(Math.abs(after - cur) * cost)} at cost
              {item.in_books ? " · posts a journal" : " · not in the books yet"}
            </div>
          )}
          <div>
            <p className="mb-1 text-sm font-medium">Movements</p>
            {(history ?? []).length === 0 ? <p className="text-xs text-muted-foreground">No movements yet.</p> : (
              <Table>
                <TableHeader><TableRow><TableHead>Date</TableHead><TableHead>What</TableHead><TableHead className="text-right">Change</TableHead><TableHead className="text-right">After</TableHead><TableHead>Reason</TableHead></TableRow></TableHeader>
                <TableBody>{(history ?? []).map((m) => (
                  <TableRow key={m.id}><TableCell className="whitespace-nowrap text-xs">{fmtDate(m.created_at)}</TableCell>
                    <TableCell className="text-xs">{m.move_type.replace(/_/g, " ").toLowerCase()}{m.journal_number ? ` · ${m.journal_number}` : ""}</TableCell>
                    <TableCell className="text-right text-xs">{num(m.quantity)}</TableCell><TableCell className="text-right text-xs">{num(m.quantity_after)}</TableCell>
                    <TableCell className="max-w-[160px] truncate text-xs">{m.reason}</TableCell></TableRow>
                ))}</TableBody>
              </Table>
            )}
          </div>
        </div>
      )}
    </DetailSheet>
  );
}

function DeptAdd({ open, dept, onClose }: { open: boolean; dept: string; onClose: () => void }) {
  const qc = useQueryClient();
  const api = useContext(StoreApiContext);
  const blank = { department: dept, item_name: "", item_code: "", batch_number: "", expiry_date: "", quantity: "", unit_cost: "", reorder_level: "" };
  const [f, setF] = useState(blank);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    const r = await act(() => api.post(`/inventory/departments/${f.department || dept}/items`, { ...f, department: undefined,
      expiry_date: f.expiry_date || undefined, quantity: f.quantity || undefined, unit_cost: f.unit_cost || undefined, reorder_level: f.reorder_level || undefined }), "Item added");
    setBusy(false);
    if (r) { qc.invalidateQueries({ queryKey: [api.prefix] }); setF(blank); onClose(); }
  };
  return (
    <DetailSheet open={open} onOpenChange={(o) => !o && onClose()} title="Add an item to a department store"
                 footer={<Button disabled={busy || !f.item_name.trim()} onClick={submit}>{busy ? "Saving…" : "Add item"}</Button>}>
      <div className="space-y-3">
        <div className="space-y-1"><Label className="text-xs">Department</Label>
          <select className="h-9 w-full rounded-md border bg-background px-2 text-sm" value={f.department || dept} onChange={(e) => setF({ ...f, department: e.target.value })}>
            {Object.entries(DEPT_LABEL).filter(([k]) => k !== "PHARMACY").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <p className="text-xs text-muted-foreground">Pharmacy stock is received in Pharmacy › Inventory.</p>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1"><Label className="text-xs">Item</Label><Input value={f.item_name} onChange={(e) => setF({ ...f, item_name: e.target.value })} /></div>
          <div className="space-y-1"><Label className="text-xs">Code</Label><Input value={f.item_code} onChange={(e) => setF({ ...f, item_code: e.target.value })} /></div>
          <div className="space-y-1"><Label className="text-xs">Batch</Label><Input value={f.batch_number} onChange={(e) => setF({ ...f, batch_number: e.target.value })} /></div>
          <div className="space-y-1"><Label className="text-xs">Expiry</Label><Input type="date" value={f.expiry_date} onChange={(e) => setF({ ...f, expiry_date: e.target.value })} /></div>
          <div className="space-y-1"><Label className="text-xs">Quantity on the shelf</Label><Input type="number" value={f.quantity} onChange={(e) => setF({ ...f, quantity: e.target.value })} /></div>
          <div className="space-y-1"><Label className="text-xs">Unit cost</Label><Input type="number" value={f.unit_cost} onChange={(e) => setF({ ...f, unit_cost: e.target.value })} /></div>
          <div className="space-y-1"><Label className="text-xs">Reorder level</Label><Input type="number" value={f.reorder_level} onChange={(e) => setF({ ...f, reorder_level: e.target.value })} /></div>
        </div>
      </div>
    </DetailSheet>
  );
}


/** What the department used - for Immunisation, the vaccines given (from the vaccination records), to set against stock. */
function DeptUsage({ dept }: { dept: string }) {
  const { data } = useStore<Dict>(["dept-usage", dept], `/inventory/departments/${dept}/usage`);
  const rows: Dict[] = data?.rows ?? [];
  if (!rows.length) return null;
  return (
    <Section title={data?.title ?? "Usage"} actions={<CsvButton filename={`${dept.toLowerCase()}-usage.csv`} rows={rows} />}>
      <p className="mb-2 text-xs text-muted-foreground">From the vaccination records. Each vaccine given should come off the store: record it with Adjust › Used / issued, or count the store.</p>
      <Table>
        <TableHeader><TableRow><TableHead>Vaccine</TableHead><TableHead className="text-right">Given (all time)</TableHead><TableHead className="text-right">This year</TableHead>
          <TableHead className="text-right">Last 90 days</TableHead><TableHead>Last given</TableHead></TableRow></TableHeader>
        <TableBody>{rows.map((r) => (
          <TableRow key={r.item}><TableCell className="max-w-[300px] truncate">{r.item}</TableCell><TableCell className="text-right">{num(r.given)}</TableCell>
            <TableCell className="text-right">{num(r.this_year)}</TableCell><TableCell className="text-right">{num(r.last_90_days)}</TableCell>
            <TableCell>{r.last_given ? fmtDate(r.last_given) : "—"}</TableCell></TableRow>
        ))}</TableBody>
      </Table>
    </Section>
  );
}
