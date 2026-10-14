import { useSearchParams } from "react-router-dom";
import { Boxes } from "lucide-react";
import { PageHeader } from "@/components/workspace/PageHeader";
import { DepartmentStock, DeptBar, StoreApiContext, type StoreApi } from "@/components/books/DepartmentStock";
import { api } from "@/lib/api-client";

// The departments keep their own stock (finance meeting, Oct 2026): this is their page. Same screens and stock ledger
// as Roy Books › Stock, read and written through /stock/stores; putting a store in the books stays with finance.
const STORES_API: StoreApi = {
  prefix: "stores",
  get: (path, params) => api.hospital.stores.get(path, params),
  post: (path, body) => api.hospital.stores.post(path, body),
  finance: false,
};

export default function DepartmentStores() {
  const [params, setParams] = useSearchParams();
  const dept = params.get("dept") ?? "IMMUNISATION";
  const setDept = (d: string) => { const p = new URLSearchParams(params); p.set("dept", d); setParams(p, { replace: true }); };
  return (
    <StoreApiContext.Provider value={STORES_API}>
      <div className="space-y-5">
        <PageHeader icon={Boxes} title="Department stores"
                    subtitle="Each department's stock: vaccines, lab reagents, urology and ward consumables. Receive, use, count and write off here; finance sees every movement in Roy Books." />
        <DeptBar value={dept} onChange={setDept} />
        <DepartmentStock dept={dept} onAdjustPharmacy={() => undefined} onItem={() => undefined} />
      </div>
    </StoreApiContext.Provider>
  );
}
