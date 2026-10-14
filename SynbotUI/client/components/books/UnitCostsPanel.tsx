import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Amount, CsvButton, Empty, ErrorNote, Loading, Section, Stat, useBooks } from "@/components/books/kit";
import { books, Dict, fmtDate, naira, num } from "@/lib/books-api";
import { useToast } from "@/hooks/use-toast";

/**
 * Unit costs of the pharmacy's batches (finance meeting: unit cost and valuation must be visible and enterable).
 * Every batch on the shelf with its unit cost, value and whether the books hold it. A batch with no cost was left out
 * of the go-live opening stock: entering its cost here brings it into the books at that cost (Dr Inventory /
 * Cr Beginning Balance Equity, like the opening stock). A batch the books already value is changed by a stock
 * adjustment instead, so the books never change value silently. Shown in Roy Books > Stock and in Pharmacy > Inventory.
 */
export function UnitCostsPanel() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [filter, setFilter] = useState("");
  const [show, setShow] = useState("nocost");
  const [cost, setCost] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const { data, isLoading, error } = useBooks<Dict>(["count-overview"], "/inventory/counts/overview");
  const all: Dict[] = data?.lines ?? [];
  const rows = all.filter((r) => (!filter || `${r.product_name} ${r.batch_number} ${r.sku}`.toLowerCase().includes(filter.toLowerCase()))
    && (show === "" || (show === "nocost" ? r.no_cost : !r.no_cost)));
  const sm = data?.summary;

  const save = async (r: Dict) => {
    const v = cost[r.ops_batch_id];
    if (!v || Number(v) <= 0) { toast({ title: "Enter a unit cost above zero", variant: "destructive" }); return; }
    setBusy(String(r.ops_batch_id));
    try {
      const res: Dict = await books.post(`/inventory/batches/${r.ops_batch_id}/unit-cost`, { unit_cost: Number(v) });
      toast({ title: `${r.product_name}: ${naira(res.unit_cost)} each`, description: `${num(res.quantity)} on the shelf, ${naira(res.value)} added to the books (${res.journal}).` });
      setCost((c) => { const n = { ...c }; delete n[r.ops_batch_id]; return n; });
      void qc.invalidateQueries({ queryKey: ["books"] });
    } catch (e: any) {
      toast({ title: "Could not set the cost", description: e?.message, variant: "destructive" });
    } finally {
      setBusy(null);
    }
  };

  return (
    <Section title="Unit costs" actions={<CsvButton filename="unit-costs.csv" rows={rows} />}>
      {isLoading && <Loading />}<ErrorNote error={error} />
      {sm && (
        <div className="mb-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Batches on the shelf" value={String(sm.lines)} sub={`${sm.items} items`} />
          <Stat label="Shelf value (at unit cost)" value={naira(sm.shelf_value)} />
          <Stat label="In the books" value={naira(sm.book_value)} sub={`${sm.not_in_books} batches not in the books`} />
          <Stat label="Without a unit cost" value={String(sm.no_cost_lines)} tone={sm.no_cost_lines ? "warn" : "good"}
                sub={sm.no_cost_lines ? "left out of the stock value - enter their cost" : "every batch is costed"} />
        </div>
      )}
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <Input className="h-9 w-64 border" placeholder="Drug, batch or code" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <select className="h-9 rounded-md border bg-background px-2 text-sm" value={show} onChange={(e) => setShow(e.target.value)}>
          <option value="nocost">Without a unit cost</option><option value="costed">With a unit cost</option><option value="">All batches</option>
        </select>
        <p className="text-sm text-foreground/75">A cost entered here brings the batch into the books at that cost. To change a cost the books already hold, use an adjustment.</p>
      </div>
      {data && (rows.length === 0 ? <Empty>{show === "nocost" ? "Every batch on the shelf has a unit cost." : "No batches match."}</Empty> : (
        <Table>
          <TableHeader><TableRow>
            <TableHead>Drug</TableHead><TableHead>Batch</TableHead><TableHead>Expiry</TableHead><TableHead className="text-right">On the shelf</TableHead>
            <TableHead className="text-right">Unit cost</TableHead><TableHead className="text-right">Value</TableHead><TableHead>In the books</TableHead><TableHead />
          </TableRow></TableHeader>
          <TableBody>{rows.slice(0, 1000).map((r) => (
            <TableRow key={r.ops_batch_id}>
              <TableCell>{r.product_name}{r.strength ? ` ${r.strength}` : ""}<div className="font-mono text-xs text-foreground/70">{r.sku}</div></TableCell>
              <TableCell className="font-mono text-xs">{r.batch_number}</TableCell>
              <TableCell className={`whitespace-nowrap ${r.expired ? "text-red-600" : ""}`}>{fmtDate(r.expiry_date)}</TableCell>
              <TableCell className="text-right">{num(r.shelf_qty)}</TableCell>
              <TableCell className="text-right">{r.no_cost ? <span className="font-medium text-amber-700">none</span> : <Amount value={r.unit_cost} />}</TableCell>
              <TableCell className="text-right"><Amount value={r.shelf_value} blankZero /></TableCell>
              <TableCell>{r.batch_status === "NOT IN BOOKS" ? <span className="text-amber-700">not yet</span> : `yes (${num(r.book_qty)})`}</TableCell>
              <TableCell className="whitespace-nowrap">
                {r.no_cost && (
                  <div className="flex items-center gap-1.5">
                    <Input type="number" min="0" step="0.01" className="h-8 w-28" placeholder="₦ each"
                           value={cost[r.ops_batch_id] ?? ""} onChange={(e) => setCost((c) => ({ ...c, [r.ops_batch_id]: e.target.value }))} />
                    <Button size="sm" className="h-8" disabled={busy === String(r.ops_batch_id)} onClick={() => void save(r)}>Set</Button>
                  </div>
                )}
              </TableCell>
            </TableRow>
          ))}</TableBody>
        </Table>
      ))}
    </Section>
  );
}
