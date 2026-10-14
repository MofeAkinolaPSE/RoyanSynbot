import { ReactNode, useEffect } from "react";
import { NavLink, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { BookOpen, CalendarRange } from "lucide-react";
import { PageHeader } from "@/components/workspace/PageHeader";
import { fmtDate } from "@/lib/books-api";
import { useBooks } from "./kit";
import { DrillProvider } from "./lineage";

const NAV = [
  { to: "/finance/books", label: "Control Tower", end: true },
  { to: "/hospital/billing", label: "Billing & Cashier" },
  { to: "/finance/books/sales", label: "Receivables (Patients & HMOs)" },
  { to: "/finance/books/purchases", label: "Purchases & Payables" },
  { to: "/finance/books/stock", label: "Stock" },
  { to: "/finance/books/banking", label: "Banking" },
  { to: "/finance/books/ledger", label: "Journals & Ledger" },
  { to: "/finance/books/statements", label: "Financial Statements" },
  { to: "/finance/books/reports", label: "Report Center" },
  { to: "/finance/books/assets", label: "Fixed Assets" },
  { to: "/finance/books/close", label: "Close & Controls" },
  { to: "/finance/books/setup", label: "Setup" },
];

// The companies kept in Roy Books. Scancare (imaging) is a separate business with its own books; every scan billed,
// even one a Royan doctor ordered, is Scancare's sale. Finance › Scancare Books opens these screens on Scancare.
export const COMPANIES = [
  { code: "RHL", label: "Royan Hospital", books: "Roy Books" },
  { code: "SCN", label: "Scancare", books: "Scancare Books" },
];

export function currentCompany(): string {
  try { return localStorage.getItem("roy_books_entity") || "RHL"; } catch { return "RHL"; }
}

/** Switch every Roy Books screen to another company's books (?company=SCN in a link does the same). */
export function useCompanySwitch() {
  const qc = useQueryClient();
  return (code: string) => {
    try {
      if (code === "RHL") localStorage.removeItem("roy_books_entity");
      else localStorage.setItem("roy_books_entity", code);
    } catch { /* storage blocked: stays on Royan */ }
    void qc.resetQueries({ queryKey: ["books"] });
  };
}

function CompanySwitch() {
  const [params, setParams] = useSearchParams();
  const switchTo = useCompanySwitch();
  const wanted = params.get("company");
  useEffect(() => {
    if (wanted && wanted !== currentCompany()) switchTo(wanted);
    if (wanted) { params.delete("company"); setParams(params, { replace: true }); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wanted]);
  const cur = wanted ?? currentCompany();
  return (
    <span className="inline-flex rounded-full border p-0.5 text-xs">
      {COMPANIES.map((c) => (
        <button key={c.code} type="button" onClick={() => switchTo(c.code)}
          className={`rounded-full px-3 py-1 ${cur === c.code ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>
          {c.label}
        </button>
      ))}
    </span>
  );
}

/** Frame shared by every Roy Books screen: title, company, open period, section nav. */
export function BooksShell({ title, subtitle, actions, children }: { title: string; subtitle?: string; actions?: ReactNode; children: ReactNode }) {
  const { data: ctx } = useBooks<any>(["context"], "/context");
  const company = COMPANIES.find((c) => c.code === (ctx?.entity?.code ?? currentCompany())) ?? COMPANIES[0];
  const period = ctx?.period;
  return (
    <DrillProvider>
    <div className="books-compact space-y-5 p-4 md:p-8">
      <PageHeader icon={BookOpen} title={title}
                  subtitle={subtitle ? `${company.books} · ${subtitle}` : (ctx?.entity ? `${ctx.entity.name} · ${company.books}` : company.books)}
                  actions={<>
                    <CompanySwitch />
                    {period && (
                      <span className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs">
                        <CalendarRange className="h-3.5 w-3.5" />
                        {period.name} · {period.status.toLowerCase()}
                      </span>
                    )}
                    {ctx?.settings && (ctx.settings.cutover_date ? (
                      <span className="inline-flex items-center rounded-full border px-3 py-1 text-xs text-muted-foreground">
                        Live since {fmtDate(ctx.settings.cutover_date)}
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs text-amber-800 dark:bg-amber-500/10 dark:text-amber-300"
                            title="Hospital bills, payments and dispensing start posting once a cut-over date is set (Setup › Settings)">
                        Not live yet: set the cut-over date
                      </span>
                    ))}
                    {actions}
                  </>} />
      <nav className="-mx-1 flex gap-1 overflow-x-auto border-b pb-px">
        {NAV.map((n) => company.code === "SCN" && n.to === "/hospital/billing" ? { ...n, to: "/hospital/radiology?tab=billing", label: "Scancare Billing & Cashier" } : n).map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end}
                   className={({ isActive }) => `whitespace-nowrap rounded-t-md px-3 py-2 text-sm ${isActive ? "border-b-2 border-primary font-semibold text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
            {n.label}
          </NavLink>
        ))}
      </nav>
      {children}
    </div>
    </DrillProvider>
  );
}
