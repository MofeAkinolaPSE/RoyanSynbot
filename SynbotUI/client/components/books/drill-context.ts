/**
 * Financial lineage: any figure in Roy Books can open the record behind it
 * (report -> account -> ledger line -> journal -> source document -> party /
 * product / batch) in a sheet on top of the current page, without navigating
 * away. Pages get it for free via BooksShell's <DrillProvider>.
 */
import { createContext, useContext } from "react";

export type DrillType =
  | "journal" | "account" | "invoice" | "receipt" | "creditnote" | "bill" | "payment" | "debitnote"
  | "voucher" | "customer" | "supplier" | "product" | "batch" | "adjustment" | "loan" | "asset" | "refund"
  | "sagevoucher" | "sageinvoice" | "sagereceipt" | "visit"
  /** a Data issue (Close & Controls) - also the source of every FIX- correcting journal */
  | "dataissue";

export type DrillTarget = { type: DrillType; id: string; label?: string };

export const DrillContext = createContext<{ open: (t: DrillTarget) => void } | null>(null);

export function useDrill() {
  return useContext(DrillContext);
}

/** Map a posting source (journal or stock movement) to the document it came from. */
export const SOURCE_TYPES: Record<string, DrillType> = {
  SALES_INVOICE: "invoice",
  CUSTOMER_RECEIPT: "receipt",
  CREDIT_NOTE: "creditnote",
  CUSTOMER_REFUND: "refund",
  SAGE_GL: "sagevoucher",
  SUPPLIER_BILL: "bill",
  SUPPLIER_PAYMENT: "payment",
  DEBIT_NOTE: "debitnote",
  CASH_VOUCHER: "voucher",
  STOCK_ADJUSTMENT: "adjustment",
  STOCK_LOAN: "loan",
  FIXED_ASSET: "asset",
  FIXED_ASSET_DISPOSAL: "asset",
  DATA_CORRECTION: "dataissue",
};

/** A ledger / journal line: Sage history opens its Sage entry; a Roy Books line opens its source document or journal. */
export function lineTarget(l: { origin?: string; source_type?: string | null; source_id?: string | null; journal_id?: string | null;
                                 journal_number?: string | null; reference?: string | null }): DrillTarget | null {
  if (l.origin === "SAGE" || l.source_type === "SAGE_GL") return l.source_id ? { type: "sagevoucher", id: String(l.source_id), label: l.reference ?? undefined } : null;
  return sourceTarget(l.source_type, l.source_id) ?? (l.journal_id ? { type: "journal", id: String(l.journal_id), label: l.journal_number ?? undefined } : null);
}

export function sourceTarget(sourceType?: string | null, sourceId?: string | null): DrillTarget | null {
  if (!sourceType || !sourceId) return null;
  const t = SOURCE_TYPES[sourceType];
  // Stock-loan movements reference the loan number, not its id - the loan sheet resolves both.
  return t ? { type: t, id: String(sourceId) } : null;
}
