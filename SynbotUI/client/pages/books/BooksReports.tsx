import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowUpRight, ChevronRight, FileSpreadsheet, Printer, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { BooksShell } from "@/components/books/BooksShell";
import { sourceTarget, useDrill } from "@/components/books/drill-context";
import { AccountPick, Amount, BankSelect, CustomerPick, DateRange, Empty, ErrorNote, Loading, ProductPick, Section, SupplierPick, useBooks } from "@/components/books/kit";
import { Dict, downloadCsv, fmtDate, num, today, yearStart } from "@/lib/books-api";

type Param = "range" | "asOf" | "account" | "bank" | "customer" | "supplier" | "sku" | "withBalance" | "search" | "payerType";
/** `hope`: the report reads Hope's charge lines, so it opens on the last month (or as-at date) Hope data reaches. */
type Entry = { name: string; desc?: string; id?: string; hope?: "month" | "asOf" } &
  ({ key: string; params?: Param[]; fixed?: Dict } | { to: string } | { na: string });

const NO_SO = "Royan does not use sales orders, quotes or proposals (none in its Sage company).";
const NO_JOBS = "Royan's Sage job / project file is empty — no project costing.";
const NO_TIME = "Time & expense tickets are not used at Royan.";
const NO_PAYROLL = "Payroll was never run in Sage (its employee file is empty); salaries were paid as cash disbursements — see Expense Analysis (6200 Salaries) and Payments by Payee. Payroll in Roy Books waits for the Nigerian statutory rules (PAYE, pension, NHF).";
const NO_ASSEMBLY = "Assemblies, bills of materials and work tickets are not used in a hospital pharmacy.";
const SAGE_RANGE = { from: "2010-01-01", to: "2024-12-31" };

/** What Finance sees by default: what Royan asked for (the HMO / private split, HMO bills, claims ageing, Hope vs Sage),
 *  the statements, and the reports that have data today. Everything else stays in the full Sage catalogue below, hidden
 *  until asked for. Every table drills to the record behind each figure. */
const ESSENTIAL: { area: string; items: Entry[] }[] = [
  { area: "Royan's requests: HMO & private", items: [
    { name: "HMO vs Private by month", key: "payer-mix", params: ["range"], fixed: { from: "2025-01-01" },
      desc: "What was billed to HMOs, private patients, staff schemes and corporates each month (Hope's charge lines). Click a month for its departments." },
    { name: "Services by payer — what went to HMOs and private, at what cost", key: "services-by-payer", params: ["range"], fixed: { from: "2025-01-01" },
      desc: "Per department; click one for every service in it." },
    { name: "HMO monthly bills (patients per HMO)", key: "hmo-monthly-bill", params: ["range", "payerType"], hope: "month",
      desc: "Every HMO / corporate payer for the period; click one for its bill — each patient, visit and line — to print or send." },
    { name: "HMO claims ageing", key: "hmo-claims-ageing", params: ["asOf"], hope: "asOf",
      desc: "What each HMO still owes: Hope's bills to it less everything received on its Sage accounts, oldest first." },
    { name: "HMO billing: Hope vs Sage (per HMO, per year)", key: "hmo-billing-reconciliation", params: ["range"], fixed: { from: "2016-01-01" } },
    { name: "HMO claims register", key: "hmo-claims-register", params: ["range"], fixed: { from: "2016-01-01" } },
    { name: "Hope vs Sage — revenue reconciliation", key: "hope-sage-reconciliation", params: ["range"], fixed: { from: "2024-01-01" } },
    { name: "Daily revenue & collections", key: "daily-revenue", params: ["range"], hope: "month" },
    { name: "Discounts, waivers & write-offs", key: "discounts-waivers", params: ["range"], fixed: { from: "2016-01-01" } },
    { name: "Collections by payer type (Sage receipts)", id: "ess-collections", key: "collections-by-payer-type", params: ["range"], fixed: { from: "2024-01-01" } },
    { name: "Credit Control — debtors, alerts & risk", to: "/finance/ar" },
  ] },
  { area: "Financial Statements", items: [
    { name: "Income Statement", to: "/finance/books/statements?tab=pl" },
    { name: "Balance Sheet", to: "/finance/books/statements?tab=bs" },
    { name: "Cash Flow", to: "/finance/books/statements?tab=cf" },
    { name: "Income Statement by Year", id: "ess-income-years", key: "income-by-year", params: ["range"], fixed: { from: "2015-01-01" } },
    { name: "Income — 12 Period", id: "ess-income-12", key: "income-12-period", params: ["range"], fixed: { from: "2024-01-01", to: "2024-12-31" } },
    { name: "Revenue by Service Line (ledger)", id: "ess-rev-line", key: "revenue-by-service-line", params: ["range"], fixed: { from: "2024-01-01", to: "2024-12-31" } },
    { name: "General Ledger Trial Balance", to: "/finance/books/ledger?tab=tb" },
    { name: "General Ledger (Sage layout)", id: "ess-gl", key: "general-ledger", params: ["range", "account"], fixed: { from: "2024-12-01", to: "2024-12-31" },
      desc: "Exactly as Sage prints it: by Account ID, month by month - Beginning Balance, transactions, Current Period Change, Ending Balance." },
    { name: "Journals by type (Sales, Cash Receipts, Disbursements, General, Fixed Assets …)", to: "/finance/books/ledger?tab=by-type" },
    { name: "Chart of Accounts with balances", to: "/finance/books/ledger?tab=coa" },
    { name: "GL Account Summary", id: "ess-gls", key: "gl-account-summary", params: ["range"], fixed: { from: "2024-01-01", to: "2024-12-31" } },
  ] },
  { area: "Receivables (patients, HMOs, companies)", items: [
    { name: "Invoice Register (every invoice, last and next number)", to: "/finance/books/sales?tab=register" },
    { name: "Customer Ledgers (Sage layout, A-Z)", id: "ess-ledgers", key: "customer-ledgers", params: ["range", "customer"], fixed: { from: "2024-01-01", to: "2024-12-31" } },
    { name: "Customer Sales History", id: "ess-sales-hist", key: "sales-history-by-customer", params: ["range", "customer"], fixed: { from: "2010-01-01" } },
    { name: "Invoice Register (Sage 2010–2024)", id: "ess-sage-inv", key: "sage-invoice-register", params: ["range", "customer"], fixed: SAGE_RANGE },
    { name: "Cash Receipts (Sage 2010–2024)", id: "ess-sage-rec", key: "sage-receipts-register", params: ["range", "customer", "bank"], fixed: SAGE_RANGE },
  ] },
  { area: "Spending & Suppliers", items: [
    { name: "Expense Analysis by Year", id: "ess-exp", key: "expense-analysis", params: ["range"], fixed: { from: "2020-01-01" } },
    { name: "Payments by Payee", id: "ess-payee", key: "payments-by-payee", params: ["range"], fixed: { from: "2023-01-01" } },
    { name: "Cash Disbursements Journal", to: "/finance/books/ledger?tab=by-type&kind=cash-disbursements" },
    { name: "Purchases from Suppliers (Hope 2016 →)", id: "ess-po", key: "purchase-order-history", params: ["range", "supplier"], fixed: { from: "2024-01-01" } },
  ] },
  { area: "Banking", items: [
    { name: "Account Register", id: "ess-register", key: "account-register", params: ["range", "account"], fixed: { from: "2024-01-01" } },
    { name: "Bank Deposit Report", id: "ess-deposits", key: "bank-deposit-report", params: ["range"], fixed: { from: "2024-01-01" } },
    { name: "Bank reconciliation — open items (Sage)", id: "ess-recon", key: "sage-reconciliation" },
  ] },
  { area: "Sage History & Tie-out", items: [
    { name: "Data issues - Sage, Hope, books and shelves compared", to: "/finance/books/close?tab=data-issues" },
    { name: "Stock: ledger vs books vs pharmacy shelf", to: "/finance/books/stock?tab=reconciliation" },
    { name: "Fixed assets in the books", to: "/finance/books/assets?tab=books" },
    { name: "Tie-out: Sage Trial Balance vs Roy Books", id: "ess-tie", key: "sage-tie-out" },
    { name: "Find a transaction (any Sage or Roy Books line)", id: "ess-find", key: "transaction-detail", params: ["range", "search"], fixed: { from: "2010-01-01" } },
    { name: "Chart of Accounts", id: "ess-coa", key: "chart-of-accounts", params: ["asOf"] },
    ...[["balance-sheet", "Balance Sheet"], ["trial-balance", "General Ledger Trial Balance"], ["aged-receivables", "Aged Receivables"]].map(([n, t]) => (
      { name: `As delivered by Sage: ${t}`, id: `ess-delivered-${n}`, key: "sage-delivered", fixed: { name: n } } as Entry)),
  ] },
];

/** The full Sage 50 Reports & Forms catalogue (all 131 report types) plus the earlier hospital views, kept so nothing
 *  the finance team relied on is missing; hidden until asked for. Types Royan never used in Sage say why. */
const CATALOG: { area: string; items: Entry[] }[] = [
  { area: "Hospital Finance", items: [
    { name: "Revenue by Service Line", key: "revenue-by-service-line", params: ["range"], desc: "Net revenue per income head and month, straight from the ledger (Sage history and Roy Books)." },
    { name: "Collections by Payer Type (HMO / private / sundries)", key: "collections-by-payer-type", params: ["range"], desc: "Money received per month by who paid." },
    { name: "HMO Receivables (aged, per HMO)", key: "hmo-receivables", params: ["asOf"] },
    { name: "Cashier Collections (per day & method)", key: "cashier-collections", params: ["range"] },
    { name: "Refunds paid", to: "/finance/books/sales?tab=refunds" },
    { name: "Patient & Payer Accounts", key: "customer-list", params: ["asOf", "withBalance"] },
  ] },
  { area: "Sage History (2009–2024) & Tie-out", items: [
    { name: "Tie-out: Sage Trial Balance vs Roy Books", key: "sage-tie-out", desc: "Every account at 31 Dec 2024: Sage's figure, Roy Books' figure computed from the history, and the difference." },
    { name: "Invoice Register (Sage 2010–2024)", id: "sage-invoices", key: "sage-invoice-register", params: ["range", "customer"], fixed: SAGE_RANGE },
    { name: "Cash Receipts (Sage 2010–2024)", id: "sage-receipts", key: "sage-receipts-register", params: ["range", "customer", "bank"], fixed: SAGE_RANGE },
    { name: "Income Statement by Year (2010 → today)", id: "sage-income-years", key: "income-by-year", params: ["range"], fixed: { from: "2015-01-01" } },
    { name: "Sage bank reconciliation — open items", key: "sage-reconciliation" },
    ...[["balance-sheet", "Balance Sheet"], ["cash-flow", "Cash Flow"], ["gl-account-summary", "GL Account Summary"], ["trial-balance", "General Ledger Trial Balance"],
        ["aged-receivables", "Aged Receivables"], ["items-sold", "Items Sold to Customers"], ["account-reconciliation", "Account Reconciliation"],
        ["chart-of-accounts", "Chart of Accounts"], ["customer-list", "Customer List"], ["vendor-list", "Vendor List"],
        ["general-journal", "General Journal"], ["vendor-ledgers", "Vendor Ledgers (all nil — Sage kept no supplier invoices)"],
        ["balance-sheet-budget", "Balance Sheet / Budget (no budget was set)"]].map(([n, t]) => (
      { name: `As delivered by Sage: ${t}`, id: `sage-delivered-${n}`, key: "sage-delivered", fixed: { name: n } } as Entry)),
  ] },
  { area: "Accounts Receivable: Customers and Sales", items: [
    { name: "Aged Receivables", to: "/finance/books/sales?tab=aging" },
    { name: "Cash Receipts Journal", to: "/finance/books/ledger?tab=by-type&kind=cash-receipts" },
    { name: "Contact List", key: "contact-list" },
    { name: "Customer Ledgers", id: "ar-ledgers", key: "customer-ledgers", params: ["range", "customer"], fixed: { from: "2024-01-01", to: "2024-12-31" }, desc: "Sage's layout, customers A-Z: Sage history and Roy Books." },
    { name: "Customer List", key: "customer-list", id: "ar-customer-list", params: ["asOf", "withBalance"] },
    { name: "Customer Management Detail", key: "customer-management-detail", params: ["asOf"] },
    { name: "Customer Master File List", key: "customer-list", id: "ar-master", params: ["asOf", "withBalance"], desc: "Every debtor account with terms and credit limit." },
    { name: "Customer Sales History", key: "sales-history-by-customer", params: ["range", "customer"], fixed: { from: "2010-01-01" } },
    { name: "Customer Transaction History", key: "customer-transaction-history", params: ["range", "customer"], fixed: { from: "2010-01-01" } },
    { name: "Invoice Register (Roy Books)", key: "invoice-register", params: ["range"] },
    { name: "Invoice Register (Sage 2010–2024)", id: "ar-sage-invoices", key: "sage-invoice-register", params: ["range", "customer"], fixed: SAGE_RANGE },
    { name: "Items Sold to Customers", key: "items-sold-to-customers", params: ["range"], desc: "Roy Books stock items billed. Royan's Sage sold services, not items (see 'As delivered by Sage: Items Sold to Customers')." },
    { name: "Picklist Report", na: NO_SO }, { name: "Proposal Register", na: NO_SO }, { name: "Proposal Report", na: NO_SO },
    { name: "Prospect List", na: "Prospects are not kept in finance; patients come from the hospital register." },
    { name: "Quote Register", na: NO_SO }, { name: "Sales Backorder Report", na: NO_SO },
    { name: "Sales Journal", to: "/finance/books/ledger?tab=by-type&kind=sales" },
    { name: "Sales Order Journal", na: NO_SO }, { name: "Sales Order Register", na: NO_SO }, { name: "Sales Order Report", na: NO_SO },
    { name: "Sales Rep Reports", na: "Royan has no sales representatives." },
    { name: "Sales Taxes", na: "Medical services are VAT-exempt; Royan's Sage records no sales tax." },
    { name: "Taxable / Exempt Sales", na: "Medical services are VAT-exempt; Royan's Sage records no sales tax." },
  ] },
  { area: "Accounts Payable: Vendors and Purchases", items: [
    { name: "1099 Vendor Report", na: "A United States tax form — not applicable in Nigeria." },
    { name: "Aged Payables", to: "/finance/books/purchases?tab=aging" },
    { name: "Cash Disbursements Journal", to: "/finance/books/ledger?tab=by-type&kind=cash-disbursements", desc: "Includes Sage's 80,000+ disbursement lines 2010–2024." },
    { name: "Cash Requirements", key: "cash-requirements", params: ["asOf"] },
    { name: "Check Register", key: "check-register", params: ["range"] },
    { name: "Electronic Payment Register", id: "ap-electronic", key: "payments-by-payee", params: ["range"], fixed: { from: "2010-01-01" } },
    { name: "Items Purchased from Vendors", key: "items-purchased-from-vendors", params: ["range"] },
    { name: "Purchase Journal", to: "/finance/books/ledger?tab=by-type&kind=purchases" },
    { name: "Purchase Order Journal", id: "ap-po-journal", key: "purchase-order-history", params: ["range", "supplier"], fixed: { from: "2016-01-01" } },
    { name: "Purchase Order Register", key: "purchase-order-history", params: ["range", "supplier"], fixed: { from: "2016-01-01" } },
    { name: "Purchase Order Report", id: "ap-po-report", key: "items-purchased-from-vendors", params: ["range"] },
    { name: "Vendor Insurance Report", na: "Supplier insurance policies are not tracked." },
    { name: "Vendor Ledgers", key: "vendor-ledgers", params: ["range", "supplier"] },
    { name: "Vendor List", key: "vendor-list" },
    { name: "Vendor Management Detail", id: "ap-mgmt", key: "cash-requirements", params: ["asOf"] },
    { name: "Vendor Master File List", id: "ap-master", key: "vendor-list" },
    { name: "Vendor Transaction History", key: "payments-by-payee", params: ["range"], fixed: { from: "2010-01-01" }, desc: "Royan's Sage kept no supplier ledger; payments are taken from its cash-disbursements journal." },
  ] },
  { area: "Payroll: Employee Information and Earnings", items: [
    { name: "Salary & staff costs (from the ledger)", id: "pay-costs", key: "expense-analysis", params: ["range"], fixed: { from: "2019-01-01" } },
    ...["Current Earnings Report", "Employee Compensation Report", "Employee List", "Exception Report", "Payroll Check Register", "Payroll Journal",
        "Payroll Register", "Payroll Tax Report", "Quarterly Earnings Report", "Tax Liability Report", "Vacation and Sick Time Report",
        "Yearly Earnings Report"].map((n) => ({ name: n, na: NO_PAYROLL } as Entry)),
  ] },
  { area: "General Ledger: Account Information", items: [
    { name: "Account Variance", to: "/finance/books/statements?tab=budget" },
    { name: "Account Variance — Dual Budgets", to: "/finance/books/statements?tab=budget" },
    { name: "Budget", to: "/finance/books/setup?tab=budgets" },
    { name: "Cash Account Register", key: "account-register", params: ["range", "account"], fixed: { from: "2024-01-01" } },
    { name: "Chart of Accounts", key: "chart-of-accounts", params: ["asOf"] },
    { name: "General Journal", to: "/finance/books/ledger?tab=by-type&kind=general" },
    { name: "General Ledger", key: "general-ledger", params: ["range", "account"], fixed: { from: "2024-12-01", to: "2024-12-31" } },
    { name: "General Ledger Trial Balance", to: "/finance/books/ledger?tab=tb" },
    { name: "Transaction Detail By Status", id: "gl-detail-status", key: "transaction-detail", params: ["range", "search"], fixed: { from: "2010-01-01" } },
    { name: "Transaction Detail Report", key: "transaction-detail", params: ["range", "search"], fixed: { from: "2010-01-01" }, desc: "Find any Sage or Roy Books line by name, reference, description or amount." },
    { name: "Working Trial Balance", key: "working-trial-balance", params: ["asOf"] },
  ] },
  { area: "Financial Statements", items: [
    { name: "Balance Sheet", to: "/finance/books/statements?tab=bs" },
    { name: "Balance Sheet / Budget", to: "/finance/books/statements?tab=budget" },
    { name: "Cash Flow", to: "/finance/books/statements?tab=cf" },
    { name: "GL Account Summary", key: "gl-account-summary", params: ["range"] },
    { name: "Income — 12 Period", key: "income-12-period", params: ["range"] },
    { name: "Income 2 Years", id: "fs-income-2", key: "income-by-year", params: ["range"], fixed: { from: "2023-01-01" } },
    { name: "Income Statement", to: "/finance/books/statements?tab=pl" },
    { name: "Income / 2 Budgets — Period", to: "/finance/books/statements?tab=budget" },
    { name: "Income / 2 Budgets — YTD", to: "/finance/books/statements?tab=budget" },
    { name: "Income / Budget", to: "/finance/books/statements?tab=budget" },
    { name: "Income / Budget — Period", to: "/finance/books/statements?tab=budget" },
    { name: "Income / Budget — YTD", to: "/finance/books/statements?tab=budget" },
    { name: "Income / Earnings", to: "/finance/books/statements?tab=re" },
    { name: "Retained Earnings", to: "/finance/books/statements?tab=re" },
    { name: "Statement of Changes in Financial Position", to: "/finance/books/statements?tab=cf" },
    { name: "Statement of Financial Position", key: "financial-position", params: ["asOf"] },
    { name: "Statement of Revenue & Expenditure", id: "fs-rev-exp", key: "income-by-year", params: ["range"], fixed: { from: "2020-01-01" } },
  ] },
  { area: "Inventory: Items and Services", items: [
    { name: "Assemblies Adjustment Journal", na: NO_ASSEMBLY }, { name: "Assembly List", na: NO_ASSEMBLY },
    { name: "Bill of Materials Report", na: NO_ASSEMBLY },
    { name: "Buyer Report", id: "inv-buyer", key: "items-purchased-from-vendors", params: ["range"], desc: "Which supplier each drug is bought from." },
    { name: "Component Use List", na: NO_ASSEMBLY },
    { name: "Cost of Goods Sold Journal (cost of drugs dispensed)", to: "/finance/books/ledger?tab=by-type&kind=cogs" },
    { name: "Inventory Adjustment Journal", to: "/finance/books/ledger?tab=by-type&kind=inventory-adjustments" },
    { name: "Inventory Profitability Report", key: "inventory-profitability", params: ["range"] },
    { name: "Inventory Reorder Worksheet", key: "reorder-worksheet" },
    { name: "Inventory Stock Status Report", to: "/finance/books/stock?tab=status" },
    { name: "Inventory Unit Activity Report", to: "/finance/books/stock?tab=activity" },
    { name: "Inventory Valuation Report", to: "/finance/books/stock?tab=valuation" },
    { name: "Item Costing Report", key: "item-costing", params: ["range", "sku"] },
    { name: "Item List", id: "inv-list", key: "item-master" },
    { name: "Item Master List", key: "item-master" },
    { name: "Item Price List", id: "inv-price", key: "item-master" },
    { name: "Physical Inventory List (count sheet)", key: "physical-inventory-list" },
    { name: "Serial Number History Report", na: "Drugs are tracked by batch and expiry, not serial number (see Batches & Expiry)." },
    { name: "Shipment Register", na: "Royan does not ship goods." },
    { name: "Work Ticket Register", na: NO_ASSEMBLY },
  ] },
  { area: "Job Reports: Project Information", items: ["Cost Code List", "Estimated Job Expenses", "Estimated Job Revenue", "Job Costs by Type", "Job Estimates",
    "Job Ledger", "Job List", "Job Master File List", "Job Profitability Report", "Job Register", "Job Retainage Report", "Phase List",
    "Unbilled Job Expense", "Work in Progress"].map((n) => ({ name: n, na: NO_JOBS } as Entry)) },
  { area: "Account Reconciliation: Banking", items: [
    { name: "Account Reconciliation", to: "/finance/books/banking?tab=reconcile" },
    { name: "Account Register", id: "bank-register", key: "account-register", params: ["range", "account"], fixed: { from: "2024-01-01" } },
    { name: "Bank Deposit Report", key: "bank-deposit-report", params: ["range"], fixed: { from: "2024-01-01" } },
    { name: "Deposits in Transit (Sage baseline)", id: "bank-dit", key: "sage-reconciliation" },
    { name: "Other Outstanding Items", key: "outstanding-items", params: ["asOf", "bank"] },
    { name: "Outstanding Checks", id: "bank-checks", key: "outstanding-items", params: ["asOf", "bank"] },
  ] },
  { area: "Time / Expense Reports", items: ["Aged Tickets", "Employee Time", "Expense Ticket Register", "Payroll Time Sheet", "Reimbursable Employee Expense",
    "Ticket Listing by Customer", "Tickets Recorded By", "Tickets Used in Invoicing", "Tickets by Item ID", "Time Ticket Register"].map((n) => ({ name: n, na: NO_TIME } as Entry)) },
  { area: "Analysis", items: [
    { name: "Expense Analysis by Year", key: "expense-analysis", params: ["range"], fixed: { from: "2020-01-01" } },
    { name: "Payments by Payee", key: "payments-by-payee", params: ["range"], fixed: { from: "2020-01-01" } },
  ] },
];

// every list reads A-Z, as Sage lists its reports
const az = (a: { area: string; items: Entry[] }) => ({ ...a, items: [...a.items].sort((x, y) => x.name.localeCompare(y.name)) });
const ALL = [...ESSENTIAL, ...CATALOG].flatMap((a) => a.items.map((i) => ({ ...i, area: a.area })));
const entryId = (e: Entry) => ("key" in e ? e.id ?? e.key : e.name);

export default function BooksReports() {
  const [params, setParams] = useSearchParams();
  const [filter, setFilter] = useState("");
  const key = params.get("r");
  const current = ALL.find((e) => "key" in e && entryId(e) === key) as (Entry & { key: string; params?: Param[]; fixed?: Dict; area: string }) | undefined;
  const set = (patch: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => (v ? p.set(k, v) : p.delete(k)));
    setParams(p, { replace: true });
  };
  const showAll = params.get("all") === "1";
  const shown = (showAll ? [...ESSENTIAL, ...CATALOG.map((a) => ({ area: `Sage 50 — ${a.area}`, items: a.items }))] : ESSENTIAL).map(az);
  const essentialCount = ESSENTIAL.reduce((n, a) => n + a.items.length, 0);
  const hiddenCount = CATALOG.reduce((n, a) => n + a.items.length, 0);
  return (
    <BooksShell title="Report Center" subtitle={showAll
      ? `Royan's reports plus every Sage 50 report type (${hiddenCount}); those Royan never used in Sage say why`
      : `${essentialCount} reports Royan uses, HMO & private first. The other Sage 50 report types are hidden until asked for.`}>
      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <Section className="self-start lg:sticky lg:top-4">
          <div className="relative mb-3"><Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input className="h-9 pl-8" placeholder="Find a report" value={filter} onChange={(e) => setFilter(e.target.value)} /></div>
          <div className="max-h-[70vh] space-y-4 overflow-y-auto pr-1">
            {shown.map((a) => {
              const items = a.items.filter((i) => !filter || `${a.area} ${i.name}`.toLowerCase().includes(filter.toLowerCase()));
              if (!items.length) return null;
              return (
                <div key={a.area}>
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{a.area}</div>
                  <ul className="space-y-0.5">
                    {items.map((i) => (
                      <li key={i.name}>
                        {"key" in i ? (
                          <button onClick={() => set({ r: entryId(i), month: null, customer_id: null, from: null, to: null, search: null, payer: null, name: null, as_of: null })}
                                  className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted ${key === entryId(i) ? "bg-muted font-semibold" : ""}`}>
                            {i.name}<ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-50" />
                          </button>
                        ) : "to" in i ? (
                          <Link to={i.to} className="flex items-center justify-between rounded-md px-2 py-1.5 text-sm hover:bg-muted">{i.name}<ArrowUpRight className="h-3.5 w-3.5 shrink-0 opacity-50" /></Link>
                        ) : (
                          <div className="rounded-md px-2 py-1.5 text-sm text-muted-foreground/70" title={i.na}>{i.name}<div className="text-xs">{i.na}</div></div>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
            <div className="border-t pt-3 text-xs text-muted-foreground">
              <button className="text-primary hover:underline" onClick={() => set({ all: showAll ? null : "1" })}>
                {showAll ? "Show only Royan's reports" : `Show the other ${hiddenCount} Sage 50 report types`}</button>
              {!showAll && <p className="mt-1">Hidden because Royan has no data for them yet or never used them in Sage. Ask to have one added.</p>}
            </div>
          </div>
        </Section>
        <div className="min-w-0">
          {current ? <ReportView key={entryId(current)} entry={current} params={params} set={set} /> : (
            <Section title="Choose a report">
              <p className="text-sm text-muted-foreground">
                Reports on the left marked <ChevronRight className="inline h-3.5 w-3.5" /> open here as tables you can filter, download (CSV opens in Excel) and print.
                Those marked <ArrowUpRight className="inline h-3.5 w-3.5" /> are the full financial statements and working screens.
                Every underlined figure or reference opens the record behind it — invoice, patient or payer, drug, batch, journal, account — so you can follow a number back to where it came from.
              </p>
            </Section>
          )}
        </div>
      </div>
    </BooksShell>
  );
}

function ReportView({ entry, params, set }: { entry: { key: string; name: string; params?: Param[]; desc?: string; fixed?: Dict; hope?: "month" | "asOf" }; params: URLSearchParams; set: (p: Record<string, string | null>) => void }) {
  const drill = useDrill();
  const { data: cov } = useBooks<Dict>(["hope-coverage"], "/hope/coverage", undefined, !!entry.hope);
  const hopeTo: string | undefined = cov?.hope_to ? String(cov.hope_to).slice(0, 10) : undefined;
  const [search, setSearch] = useState("");
  const [picked, setPicked] = useState<Record<string, Dict | null>>({});
  const ps = entry.params ?? [];
  const fixed = entry.fixed ?? {};
  const hopeFrom = entry.hope === "month" && hopeTo ? `${hopeTo.slice(0, 7)}-01` : undefined;
  const from = params.get("from") ?? fixed.from ?? hopeFrom ?? yearStart();
  const to = params.get("to") ?? fixed.to ?? (entry.hope ? hopeTo : undefined) ?? today();
  const [searchInput, setSearchInput] = useState(params.get("search") ?? "");
  const q: Dict = { from, to, as_of: params.get("as_of") ?? (entry.hope === "asOf" ? hopeTo : undefined) ?? today(), month: params.get("month") ?? undefined,
    customer_id: params.get("customer_id") ?? undefined, supplier_id: params.get("supplier_id") ?? undefined,
    account_id: params.get("account_id") ?? undefined, bank_account_id: params.get("bank_account_id") ?? undefined,
    sku: params.get("sku") ?? undefined, with_balance: params.get("with_balance") ?? undefined,
    name: fixed.name ?? params.get("name") ?? undefined, search: params.get("search") ?? undefined,
    payer: params.get("payer") ?? undefined, payer_type: params.get("payer_type") ?? undefined };
  const waitCoverage = !!entry.hope && !cov && !params.get("from") && !params.get("as_of");
  const needsAccount = ps.includes("account") && entry.key === "account-register" && !q.account_id;
  const needsSearch = ps.includes("search") && !(q.search && q.search.length >= 2);
  const needsCustomer = entry.key === "customer-transaction-history" && !q.customer_id;
  const { data, isLoading, error } = useBooks<Dict>(["report-center", entry.key, q], `/report-center/${entry.key}`, q, !needsAccount && !needsSearch && !needsCustomer && !waitCoverage);
  const rows: Dict[] = useMemo(() => {
    const r = data?.rows ?? [];
    if (!search) return r;
    const s = search.toLowerCase();
    return r.filter((x) => Object.values(x).some((v) => v != null && String(v).toLowerCase().includes(s)));
  }, [data, search]);
  const cols: Dict[] = data?.columns ?? [];
  const click = (c: Dict, row: Dict) => {
    const id = row[c.id];
    if (id == null || id === "") return;
    if (c.link === "drill:month") return set({ month: String(id), customer_id: null });
    if (c.link === "drill:customer") return set({ customer_id: String(id) });
    if (c.link === "drill:payer") return set({ payer: String(id) });
    if (c.link === "drill:name") return set({ name: String(id) });
    if (!drill) return;
    if (c.link === "source") { const t = sourceTarget(row.source_type, String(id)); if (t) drill.open(t); return; }
    if (c.link === "doc") return drill.open({ type: row.link, id: String(id), label: row.number });
    drill.open({ type: c.link, id: String(id), label: row[c.key] != null ? String(row[c.key]) : undefined });
  };
  const cell = (c: Dict, row: Dict) => {
    const v = row[c.key];
    const content = c.type === "money" ? (v == null ? "" : <Amount value={v} />) : c.type === "qty" ? (v == null ? "" : num(v, Number(v) % 1 ? 2 : 0))
      : c.type === "date" ? fmtDate(v) : c.type === "datetime" ? (v ? new Date(v).toLocaleString("en-GB") : "") : v == null ? "" : String(v);
    if (c.link && row[c.id] != null && row[c.id] !== "" && content !== "") {
      return <button className="text-left text-primary underline-offset-2 hover:underline" onClick={() => click(c, row)}>{content}</button>;
    }
    return content;
  };
  const sa = entry.key === "sales-analysis";
  const drilled = !sa && !!(q.month || q.payer || (!fixed.name && q.name));
  return (
    <Section title={data?.title ?? entry.name}
             actions={<>
               <Button size="sm" variant="outline" disabled={!rows.length}
                       onClick={() => downloadCsv(`${entry.key}-${q.as_of ?? to}.csv`, rows, cols.map((c) => ({ key: c.key, label: c.label })))}>
                 <FileSpreadsheet className="mr-1.5 h-4 w-4" />Download (Excel CSV)</Button>
               <Button size="sm" variant="outline" onClick={() => window.print()}><Printer className="mr-1.5 h-4 w-4" />Print / PDF</Button>
             </>}>
      <div className="mb-3 space-y-3">
        {data?.subtitle && <p className="text-sm text-muted-foreground">{data.subtitle}</p>}
        {entry.desc && <p className="text-xs text-muted-foreground">{entry.desc}</p>}
        <div className="flex flex-wrap items-end gap-3">
          {ps.includes("range") && <DateRange from={from} to={to} onChange={(f, t) => set({ from: f ?? from, to: t })} />}
          {ps.includes("asOf") && <DateRange single to={q.as_of} onChange={(_, t) => set({ as_of: t })} />}
          {ps.includes("account") && <div className="w-72"><AccountPick label="Account" value={picked.account ?? null}
            onChange={(a) => { setPicked({ ...picked, account: a }); set({ account_id: a?.id ?? null }); }} /></div>}
          {ps.includes("bank") && <div className="w-64"><BankSelect label="Bank account (all if blank)" value={q.bank_account_id ?? ""} onChange={(v) => set({ bank_account_id: v || null })} /></div>}
          {ps.includes("customer") && <div className="w-64"><CustomerPick label="Patient / payer (all if blank)" value={picked.customer ?? null}
            onChange={(c) => { setPicked({ ...picked, customer: c }); set({ customer_id: c ? String(c.id) : null }); }} /></div>}
          {ps.includes("supplier") && <div className="w-64"><SupplierPick label="Vendor (all if blank)" value={picked.supplier ?? null}
            onChange={(s) => { setPicked({ ...picked, supplier: s }); set({ supplier_id: s ? String(s.id) : null }); }} /></div>}
          {ps.includes("sku") && <div className="w-64"><ProductPick label="Item (all if blank)" value={picked.sku ?? null}
            onChange={(p) => { setPicked({ ...picked, sku: p }); set({ sku: p?.sku ?? null }); }} /></div>}
          {ps.includes("search") && <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); set({ search: searchInput || null }); }}>
            <div className="w-72"><Input className="h-9" placeholder="Name, reference, description or amount" value={searchInput} onChange={(e) => setSearchInput(e.target.value)} /></div>
            <Button size="sm" type="submit">Search</Button></form>}
          {ps.includes("payerType") && !q.payer && <div className="space-y-1"><div className="text-xs text-muted-foreground">Payers</div>
            <select className="h-9 rounded-md border bg-background px-2 text-sm" value={q.payer_type ?? ""} onChange={(e) => set({ payer_type: e.target.value || null })}>
              <option value="">HMOs, corporates & staff schemes</option><option value="HMO">HMOs only</option><option value="CORPORATE">Corporate / retainership</option>
              <option value="STAFF">Staff schemes</option></select></div>}
          {ps.includes("withBalance") && <label className="flex items-center gap-1 pb-2 text-xs"><input type="checkbox" checked={!!q.with_balance}
            onChange={(e) => set({ with_balance: e.target.checked ? "true" : null })} />only with a balance</label>}
          <div className="relative ml-auto w-56"><Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input className="h-9 pl-8" placeholder="Filter rows" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
        </div>
        {drilled && (
          <div className="flex flex-wrap items-center gap-1 text-sm">
            <button className="text-primary hover:underline" onClick={() => set({ month: null, payer: null, name: null })}>{entry.name}</button>
            <ChevronRight className="h-3.5 w-3.5" /><span>{data?.title ?? q.month ?? q.name ?? `payer ${q.payer}`}</span>
          </div>
        )}
        {sa && (
          <div className="flex flex-wrap items-center gap-1 text-sm">
            <button className="text-primary hover:underline" onClick={() => set({ month: null, customer_id: null })}>All months</button>
            {q.month && <><ChevronRight className="h-3.5 w-3.5" /><button className="text-primary hover:underline" onClick={() => set({ customer_id: null })}>{q.month}</button></>}
            {q.customer_id && <><ChevronRight className="h-3.5 w-3.5" /><span>account #{q.customer_id}</span></>}
          </div>
        )}
      </div>
      {needsAccount && <Empty>Choose an account to see its register.</Empty>}
      {needsSearch && <Empty>Type at least two characters and press Search.</Empty>}
      {needsCustomer && <Empty>Choose a patient, HMO or company to see their history.</Empty>}
      {isLoading && !needsAccount && !needsSearch && !needsCustomer && <Loading />}<ErrorNote error={error} />
      {data && (rows.length === 0 ? (
        <Empty>No rows for this selection.{/sold|profitab|purchased|check|cashier/.test(entry.key)
          ? " This report reads Roy Books documents, which start at go-live; Sage history (2010–2024) is in the Sage reports." : ""}</Empty>
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow>{cols.map((c) => <TableHead key={c.key} className={`${["money", "qty"].includes(c.type) ? "text-right" : ""}`}>{c.label}</TableHead>)}</TableRow></TableHeader>
            <TableBody>
              {rows.slice(0, 2000).map((r, i) => (
                <TableRow key={i} className={r.name === "NET INCOME" || r.line?.startsWith?.("TOTAL") || r.kind === "END" ? "font-semibold"
                  : r.kind === "BEGIN" ? "border-t-2 bg-muted/30" : r.kind === "CHANGE" ? "text-muted-foreground" : ""}>
                  {cols.map((c) => <TableCell key={c.key} className={`${["money", "qty"].includes(c.type) ? "text-right" : ""} ${c.type === "date" ? "whitespace-nowrap" : ""} text-sm`}>
                    {data.layout === "sage" && ["account_id", "account_description"].includes(c.key) && r.kind !== "BEGIN" ? "" : cell(c, r)}</TableCell>)}
                </TableRow>
              ))}
              {Object.keys(data.totals ?? {}).length > 0 && !search && (
                <TableRow className="font-semibold">
                  {cols.map((c, i) => <TableCell key={c.key} className="text-right">{i === 0 ? <span className="float-left">Total</span> : data.totals[c.key] != null ? <Amount value={data.totals[c.key]} /> : ""}</TableCell>)}
                </TableRow>
              )}
            </TableBody>
          </Table>
          <p className="mt-2 text-xs text-muted-foreground">{rows.length.toLocaleString()} rows{rows.length > 2000 ? " — showing the first 2,000; the download contains all of them" : ""}.</p>
        </div>
      ))}
    </Section>
  );
}
