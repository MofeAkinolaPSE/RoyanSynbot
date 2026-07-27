import { useMemo, useState } from "react";
import { Search, Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useNavigate } from "react-router-dom";
import { useIsMobile } from "@/hooks/use-mobile";
import { motion } from "framer-motion";
import { motionTransitions } from "@/lib/motion";

const DEPARTMENTS = ["Lab", "Pharmacy", "Radiology", "General"];

const FinanceReports = () => {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const [searchAR, setSearchAR] = useState("");
  const [searchInventory, setSearchInventory] = useState("");
  const [tab, setTab] = useState("ar");

  // Department Summary filters
  const [deptDateFrom, setDeptDateFrom] = useState("");
  const [deptDateTo, setDeptDateTo] = useState("");
  const [deptFilter, setDeptFilter] = useState<string>("all");

  const { data: deptSummaryData, isLoading: deptLoading, error: deptError } = useQuery({
    queryKey: ["finance-department-summary", deptDateFrom, deptDateTo, deptFilter],
    queryFn: () => api.finance.departmentSummary({
      date_from: deptDateFrom || undefined,
      date_to: deptDateTo || undefined,
      department: deptFilter !== "all" ? deptFilter : undefined,
    }),
    enabled: tab === "department",
  });
  const departments: any[] = Array.isArray(deptSummaryData?.departments) ? deptSummaryData.departments : [];

  // HMO Monthly Segregation
  const [segMonth, setSegMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const { data: segData, isLoading: segLoading, error: segError } = useQuery({
    queryKey: ["finance-hmo-segregation", segMonth],
    queryFn: () => api.finance.hmoMonthlySegregation(segMonth),
    enabled: tab === "hmo-segregation",
  });
  const hmoRows: any[] = Array.isArray(segData?.hmos) ? segData.hmos : [];

  const [encounterLookupId, setEncounterLookupId] = useState("");
  const [encounterDetailOpen, setEncounterDetailOpen] = useState(false);
  const { data: encounterDetailData, isFetching: encounterDetailLoading } = useQuery({
    queryKey: ["finance-hmo-encounter-detail", encounterLookupId],
    queryFn: () => api.finance.hmoEncounterDetail(encounterLookupId),
    enabled: encounterDetailOpen && !!encounterLookupId,
  });
  const { data: arAgingRaw, isLoading: arLoading, error: arError } = useQuery({
    queryKey: ["reports-ar-aging"],
    queryFn: () => api.finance.arAging(),
    refetchInterval: 60000,
  });

  const { data: stockRows, isLoading: invLoading, error: invError } = useQuery({
    queryKey: ["reports-inventory"],
    queryFn: () => api.inventory.stock(),
    refetchInterval: 60000,
  });

  // Normalize AR aging buckets into table-friendly rows (no per-customer granularity available yet)
  const arAgingData = useMemo(
    () => {
      const source = (arAgingRaw as any)?.aging ?? arAgingRaw;
      if (
        !source ||
        typeof source !== "object" ||
        typeof (source as any)["0_30"] !== "number" ||
        typeof (source as any)["31_60"] !== "number" ||
        typeof (source as any)["61_90"] !== "number" ||
        typeof (source as any)["91_plus"] !== "number"
      ) {
        return [];
      }
      const buckets = source as Record<string, number>;
      return [
        { id: 1, customer: "All Customers", amount: buckets["0_30"], bucket: "0-30 days", days: "0-30", dueDate: "-" },
        { id: 2, customer: "All Customers", amount: buckets["31_60"], bucket: "31-60 days", days: "31-60", dueDate: "-" },
        { id: 3, customer: "All Customers", amount: buckets["61_90"], bucket: "61-90 days", days: "61-90", dueDate: "-" },
        { id: 4, customer: "All Customers", amount: buckets["91_plus"], bucket: "90+ days", days: "90+", dueDate: "-" },
      ];
    },
    [arAgingRaw]
  );

  const inventoryData = useMemo(
    () => {
      if (!Array.isArray(stockRows)) return [];
      const rows = stockRows;
      return rows.map((r: any) => ({
        sku: r.sku,
        name: r.name,
        quantity: Number(r.current_stock ?? r.quantity),
        unitCost: Number(r.unit_cost),
        valuation: r.valuation != null
          ? Number(r.valuation)
          : Number(r.unit_cost) * Number(r.current_stock ?? r.quantity),
        status: ((): "optimal" | "low" | "out" => {
          const qty = Number(r.current_stock ?? r.quantity);
          if (r.status === "optimal" || r.status === "low" || r.status === "out") {
            return r.status;
          }
          if (qty <= 0) return "out";
          if (qty < 10) return "low";
          return "optimal";
        })(),
      })).filter((r: any) =>
        typeof r.sku === "string" &&
        typeof r.name === "string" &&
        Number.isFinite(r.quantity) &&
        Number.isFinite(r.unitCost) &&
        Number.isFinite(r.valuation)
      );
    },
    [stockRows]
  );

  const arPayloadInvalid = !arLoading && !arError && arAgingData.length === 0;
  const inventoryPayloadInvalid = !invLoading && !invError && !Array.isArray(stockRows);

  const filteredAR = arAgingData.filter(
    (item) =>
      item.customer.toLowerCase().includes(searchAR.toLowerCase()) ||
      item.bucket.toLowerCase().includes(searchAR.toLowerCase())
  );

  const filteredInventory = inventoryData.filter(
    (item) =>
      item.name.toLowerCase().includes(searchInventory.toLowerCase()) ||
      item.sku.toLowerCase().includes(searchInventory.toLowerCase())
  );

  const handleExportCSV = (dataType: "ar" | "inventory") => {
    const data = dataType === "ar" ? filteredAR : filteredInventory;
    const headers =
      dataType === "ar"
        ? ["Customer", "Amount (₦)", "Bucket", "Days Overdue", "Due Date"]
        : ["SKU", "Name", "Quantity", "Unit Cost (₦)", "Valuation (₦)"];

    let csv = headers.join(",") + "\n";
    data.forEach((item) => {
      if (dataType === "ar") {
        const row = [
          item.customer,
          item.amount,
          item.bucket,
          item.days,
          item.dueDate,
        ];
        csv += row.join(",") + "\n";
      } else {
        const row = [
          item.sku,
          item.name,
          item.quantity,
          item.unitCost,
          item.valuation,
        ];
        csv += row.join(",") + "\n";
      }
    });

    const element = document.createElement("a");
    element.setAttribute("href", "data:text/csv;charset=utf-8," + encodeURI(csv));
    element.setAttribute("download", `${dataType}-report-${Date.now()}.csv`);
    element.click();
  };

  const arBuckets = {
    "0-30 days": arAgingData.find((a) => a.bucket === "0-30 days")?.amount,
    "31-60 days": arAgingData.find((a) => a.bucket === "31-60 days")?.amount,
    "61-90 days": arAgingData.find((a) => a.bucket === "61-90 days")?.amount,
    "90+ days": arAgingData.find((a) => a.bucket === "90+ days")?.amount,
  };

  const getArBucketClass = (bucket: string) => {
    if (bucket === "0-30 days") return "bg-success/15 text-success";
    if (bucket === "90+ days") return "bg-destructive/10 text-destructive";
    return "bg-warning/15 text-warning";
  };

  const getInventoryStatusClass = (status: string) => {
    if (status === "optimal") return "bg-success/15 text-success";
    if (status === "low") return "bg-warning/15 text-warning";
    return "bg-destructive/10 text-destructive";
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={motionTransitions.standard}
      className="space-y-8"
    >
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-foreground">Finance Reports</h1>
        <p className="text-muted-foreground mt-2">
          Detailed financial tables with search, filters, and export capabilities
        </p>
      </div>

      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList className="grid w-full max-w-2xl grid-cols-4">
          <TabsTrigger value="ar">AR Aging</TabsTrigger>
          <TabsTrigger value="inventory">Inventory</TabsTrigger>
          <TabsTrigger value="department">Department Summary</TabsTrigger>
          <TabsTrigger value="hmo-segregation">HMO Segregation</TabsTrigger>
        </TabsList>

        {/* AR Aging Tab */}
        <TabsContent value="ar" className="space-y-4">
          <div className="pw-surface-interactive p-6 space-y-4">
            {arError && <p className="text-sm text-destructive">Data error: {(arError as Error).message || "Failed to load AR aging."}</p>}
            {arPayloadInvalid && <p className="text-sm text-destructive">Data error: malformed AR aging payload.</p>}
            {/* Summary Buckets */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
              {Object.entries(arBuckets).map(([bucket, amount]) => (
                <div
                  key={bucket}
                  className="rounded-xl border border-border/50 bg-muted/30 p-3 text-center"
                >
                  <p className="text-xs font-semibold text-muted-foreground uppercase">
                    {bucket}
                  </p>
                  <p className="text-2xl font-bold text-foreground mt-1">
                    {typeof amount === "number" ? `₦${Number(amount).toLocaleString()}` : "Data error"}
                  </p>
                </div>
              ))}
            </div>

            {/* Search and Export */}
            <div className="flex gap-2 flex-col sm:flex-row sm:items-center">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder="Search by customer or bucket..."
                  value={searchAR}
                  onChange={(e) => setSearchAR(e.target.value)}
                  className="pl-10"
                />
              </div>
              <Button
                variant="outline"
                onClick={() => handleExportCSV("ar")}
              >
                <Download className="w-4 h-4 mr-2" />
                Export CSV
              </Button>
            </div>

            {/* Table */}
            {isMobile ? (
              <div className="space-y-3">
                {filteredAR.length > 0 ? (
                  filteredAR.map((item) => (
                    <div
                      key={item.id}
                      className="rounded-xl border border-border/60 bg-muted/20 p-4 space-y-2 cursor-pointer"
                      onClick={() => {
                        const bucketParam = encodeURIComponent(item.bucket);
                        navigate(`/finance/reports/ar/${bucketParam}`);
                      }}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="font-semibold text-foreground">{item.customer}</p>
                        <p className="font-mono font-semibold text-foreground">₦{item.amount.toLocaleString()}</p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <span className={`rounded px-2 py-1 text-xs font-medium ${getArBucketClass(item.bucket)}`}>
                          {item.bucket}
                        </span>
                        <span className="rounded px-2 py-1 text-xs font-medium bg-muted text-muted-foreground">
                          {item.days}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground">Due date: {item.dueDate}</p>
                    </div>
                  ))
                ) : (
                  <p className="text-center text-muted-foreground py-8">No results found</p>
                )}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="sticky left-0 z-10 min-w-[180px] bg-muted/90">Customer</TableHead>
                      <TableHead className="text-right min-w-[140px]">Amount (₦)</TableHead>
                      <TableHead className="min-w-[120px]">Bucket</TableHead>
                      <TableHead className="text-center min-w-[110px]">Days Range</TableHead>
                      <TableHead className="min-w-[100px]">Due Date</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredAR.length > 0 ? (
                      filteredAR.map((item) => (
                        <TableRow
                          key={item.id}
                          className="cursor-pointer hover:bg-muted/40"
                          onClick={() => {
                            const bucketParam = encodeURIComponent(item.bucket);
                            navigate(`/finance/reports/ar/${bucketParam}`);
                          }}
                        >
                          <TableCell className="sticky left-0 z-10 bg-background font-medium">
                            {item.customer}
                          </TableCell>
                          <TableCell className="text-right font-mono">
                            {item.amount.toLocaleString()}
                          </TableCell>
                          <TableCell>
                            <span
                              className={`rounded px-2 py-1 text-xs font-medium ${getArBucketClass(item.bucket)}`}
                            >
                              {item.bucket}
                            </span>
                          </TableCell>
                          <TableCell className="text-center">{item.days}</TableCell>
                          <TableCell className="text-sm text-muted-foreground">
                            {item.dueDate}
                          </TableCell>
                        </TableRow>
                      ))
                    ) : (
                      <TableRow>
                        <TableCell colSpan={5} className="text-center py-8">
                          <p className="text-muted-foreground">
                            No results found
                          </p>
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            )}

            <p className="text-xs text-muted-foreground">
              Showing {filteredAR.length} of {arAgingData.length} records
            </p>
          </div>
        </TabsContent>

        {/* Inventory Tab */}
        <TabsContent value="inventory" className="space-y-4">
          <div className="pw-surface-interactive p-6 space-y-4">
            {invError && <p className="text-sm text-destructive">Data error: {(invError as Error).message || "Failed to load inventory."}</p>}
            {inventoryPayloadInvalid && <p className="text-sm text-destructive">Data error: malformed inventory payload.</p>}
            {/* Status Summary */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
              <div className="rounded-xl border border-success/30 bg-success/15 p-3">
                <p className="text-xs font-semibold text-success uppercase">
                  Optimal Stock
                </p>
                <p className="text-2xl font-bold text-success mt-1">
                  {inventoryData.filter((i) => i.status === "optimal").length}
                </p>
              </div>
              <div className="rounded-xl border border-warning/30 bg-warning/15 p-3">
                <p className="text-xs font-semibold text-warning uppercase">
                  Low Stock
                </p>
                <p className="text-2xl font-bold text-warning mt-1">
                  {inventoryData.filter((i) => i.status === "low").length}
                </p>
              </div>
              <div className="rounded-xl border border-info/30 bg-info/15 p-3">
                <p className="text-xs font-semibold text-info uppercase">
                  Total SKUs
                </p>
                <p className="text-2xl font-bold text-info mt-1">
                  {inventoryData.length}
                </p>
              </div>
              <div className="rounded-xl border border-secondary/30 bg-secondary/15 p-3">
                <p className="text-xs font-semibold text-secondary uppercase">
                  Total Value
                </p>
                <p className="text-2xl font-bold text-secondary mt-1">
                  ₦
                  {(
                    inventoryData.reduce((sum, i) => sum + i.valuation, 0) /
                    1000000
                  ).toFixed(1)}
                  M
                </p>
              </div>
            </div>

            {/* Search and Export */}
            <div className="flex gap-2 flex-col sm:flex-row sm:items-center">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder="Search by SKU or product name..."
                  value={searchInventory}
                  onChange={(e) => setSearchInventory(e.target.value)}
                  className="pl-10"
                />
              </div>
              <Button
                variant="outline"
                onClick={() => handleExportCSV("inventory")}
              >
                <Download className="w-4 h-4 mr-2" />
                Export CSV
              </Button>
            </div>

            {/* Table */}
            {isMobile ? (
              <div className="space-y-3">
                {filteredInventory.length > 0 ? (
                  filteredInventory.map((item) => (
                    <div key={item.sku} className="rounded-xl border border-border/60 bg-muted/20 p-4 space-y-2">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-semibold text-foreground">{item.name}</p>
                          <p className="text-xs font-mono text-muted-foreground">{item.sku}</p>
                        </div>
                        <span className={`rounded px-2 py-1 text-xs font-medium ${getInventoryStatusClass(item.status)}`}>
                          {item.status === "optimal"
                            ? "Optimal"
                            : item.status === "low"
                              ? "Low Stock"
                              : "Out of Stock"}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <p className="text-muted-foreground">Qty: <span className="font-medium text-foreground">{item.quantity.toLocaleString()}</span></p>
                        <p className="text-muted-foreground">Unit: <span className="font-mono text-foreground">₦{item.unitCost.toLocaleString()}</span></p>
                      </div>
                      <p className="text-xs text-muted-foreground">Valuation: <span className="font-mono text-foreground">₦{item.valuation.toLocaleString()}</span></p>
                    </div>
                  ))
                ) : (
                  <p className="text-center text-muted-foreground py-8">No results found</p>
                )}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="sticky left-0 z-10 min-w-[130px] bg-muted/90">SKU</TableHead>
                      <TableHead className="min-w-[220px]">Product Name</TableHead>
                      <TableHead className="text-right min-w-[100px]">Quantity</TableHead>
                      <TableHead className="text-right min-w-[140px]">Unit Cost (₦)</TableHead>
                      <TableHead className="text-right min-w-[150px]">Valuation (₦)</TableHead>
                      <TableHead className="min-w-[120px]">Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredInventory.length > 0 ? (
                      filteredInventory.map((item) => (
                        <TableRow key={item.sku}>
                          <TableCell className="sticky left-0 z-10 bg-background font-mono text-sm">
                            {item.sku}
                          </TableCell>
                          <TableCell className="font-medium">{item.name}</TableCell>
                          <TableCell className="text-right">
                            {item.quantity.toLocaleString()}
                          </TableCell>
                          <TableCell className="text-right font-mono">
                            {item.unitCost.toLocaleString()}
                          </TableCell>
                          <TableCell className="text-right font-mono">
                            {item.valuation.toLocaleString()}
                          </TableCell>
                          <TableCell>
                            <span
                              className={`rounded px-2 py-1 text-xs font-medium ${getInventoryStatusClass(item.status)}`}
                            >
                              {item.status === "optimal"
                                ? "Optimal"
                                : item.status === "low"
                                  ? "Low Stock"
                                  : "Out of Stock"}
                            </span>
                          </TableCell>
                        </TableRow>
                      ))
                    ) : (
                      <TableRow>
                        <TableCell colSpan={6} className="text-center py-8">
                          <p className="text-muted-foreground">
                            No results found
                          </p>
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            )}

            <p className="text-xs text-muted-foreground">
              Showing {filteredInventory.length} of {inventoryData.length}{" "}
              products
            </p>
          </div>
        </TabsContent>

        {/* Department Summary Tab */}
        <TabsContent value="department" className="space-y-4">
          <div className="pw-surface-interactive p-6 space-y-4">
            {deptError && <p className="text-sm text-destructive">Data error: {(deptError as Error).message || "Failed to load department summary."}</p>}
            <div className="flex gap-2 flex-col sm:flex-row sm:items-end">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">From</label>
                <Input type="date" value={deptDateFrom} onChange={e => setDeptDateFrom(e.target.value)} />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">To</label>
                <Input type="date" value={deptDateTo} onChange={e => setDeptDateTo(e.target.value)} />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Department</label>
                <Select value={deptFilter} onValueChange={setDeptFilter}>
                  <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All departments</SelectItem>
                    {DEPARTMENTS.map(d => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {deptLoading ? (
              <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
            ) : (
              <div className="space-y-4">
                {departments.length === 0 ? (
                  <p className="text-center text-muted-foreground py-8">No billed line items in this range</p>
                ) : departments.map((dept: any) => (
                  <div key={dept.department} className="rounded-xl border border-border/50 p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold text-foreground">{dept.department}</h3>
                      <span className="font-mono font-semibold">₦{Number(dept.total_gross).toLocaleString()}</span>
                    </div>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Payer Type</TableHead>
                          <TableHead className="text-right">Gross</TableHead>
                          <TableHead className="text-right">Covered</TableHead>
                          <TableHead className="text-right">Patient Due</TableHead>
                          <TableHead className="text-right">Lines</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {(dept.by_payer ?? []).map((p: any) => (
                          <TableRow key={p.payer_type}>
                            <TableCell className="capitalize">
                              <Badge variant="outline">{p.payer_type}</Badge>
                            </TableCell>
                            <TableCell className="text-right font-mono">₦{Number(p.gross).toLocaleString()}</TableCell>
                            <TableCell className="text-right font-mono">₦{Number(p.covered).toLocaleString()}</TableCell>
                            <TableCell className="text-right font-mono">₦{Number(p.patient_due).toLocaleString()}</TableCell>
                            <TableCell className="text-right">{p.line_count}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                ))}
                {departments.length > 0 && (
                  <p className="text-sm font-semibold text-right">
                    Grand total: ₦{Number(deptSummaryData?.grand_total_gross ?? 0).toLocaleString()}
                  </p>
                )}
              </div>
            )}
          </div>
        </TabsContent>

        {/* HMO Monthly Segregation Tab */}
        <TabsContent value="hmo-segregation" className="space-y-4">
          <div className="pw-surface-interactive p-6 space-y-4">
            {segError && <p className="text-sm text-destructive">Data error: {(segError as Error).message || "Failed to load HMO segregation."}</p>}
            <div className="flex gap-2 flex-col sm:flex-row sm:items-end sm:justify-between">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Month</label>
                <Input type="month" value={segMonth} onChange={e => setSegMonth(e.target.value)} className="w-40" />
              </div>
              <div className="flex gap-2 items-end">
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Encounter ID</label>
                  <Input value={encounterLookupId} onChange={e => setEncounterLookupId(e.target.value)}
                    placeholder="e.g. 854415" className="w-36" />
                </div>
                <Button variant="outline" disabled={!encounterLookupId}
                  onClick={() => setEncounterDetailOpen(true)}>
                  View Encounter Detail
                </Button>
              </div>
            </div>

            {segLoading ? (
              <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>HMO Provider</TableHead>
                    <TableHead className="text-right">Patients</TableHead>
                    <TableHead className="text-right">Total Claimed</TableHead>
                    <TableHead className="text-right">Total Approved</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {hmoRows.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} className="text-center py-8 text-muted-foreground">
                        No HMO claims for this month
                      </TableCell>
                    </TableRow>
                  ) : hmoRows.map((h: any) => (
                    <TableRow key={h.hmo_provider}>
                      <TableCell className="font-medium">{h.hmo_provider}</TableCell>
                      <TableCell className="text-right">{h.patient_count}</TableCell>
                      <TableCell className="text-right font-mono">₦{Number(h.total_claimed).toLocaleString()}</TableCell>
                      <TableCell className="text-right font-mono">₦{Number(h.total_approved).toLocaleString()}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        </TabsContent>
      </Tabs>

      {/* Encounter Billing Detail Dialog — the per-encounter drug-level popup */}
      <Dialog open={encounterDetailOpen} onOpenChange={setEncounterDetailOpen}>
        <DialogContent className="sm:max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Encounter #{encounterLookupId} — Billing Detail</DialogTitle>
          </DialogHeader>
          {encounterDetailLoading ? (
            <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : encounterDetailData ? (
            <div className="space-y-3">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Item</TableHead>
                    <TableHead>Dept</TableHead>
                    <TableHead className="text-right">Gross</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(encounterDetailData.items ?? []).map((item: any) => (
                    <TableRow key={item.id}>
                      <TableCell>{item.description}</TableCell>
                      <TableCell><Badge variant="outline">{item.department}</Badge></TableCell>
                      <TableCell className="text-right font-mono">₦{Number(item.gross_amount).toLocaleString()}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="text-sm text-right space-y-1">
                <p>Total gross: <span className="font-mono font-semibold">₦{Number(encounterDetailData.total_gross ?? 0).toLocaleString()}</span></p>
                <p>Covered: <span className="font-mono">₦{Number(encounterDetailData.total_covered ?? 0).toLocaleString()}</span></p>
                <p>Patient due: <span className="font-mono">₦{Number(encounterDetailData.total_patient_due ?? 0).toLocaleString()}</span></p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-6">No billed items found for this encounter.</p>
          )}
        </DialogContent>
      </Dialog>
    </motion.div>
  );
};

export default FinanceReports;
