"""Gap-free document numbers per entity and document type.

The UPDATE ... RETURNING takes a row lock, so concurrent postings queue for
the next number instead of colliding; a rolled-back transaction gives its
number back.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.fin.db import q, q1

DEFAULT_PREFIX = {
    "JOURNAL": "JV-",
    "SALES_INVOICE": "SI-",
    "CREDIT_NOTE": "CN-",
    "RECEIPT": "RCP-",
    "REFUND": "RF-",
    "BILL": "BILL-",
    "DEBIT_NOTE": "DN-",
    "SUPPLIER_PAYMENT": "PV-",
    "CASH_VOUCHER": "CV-",
    "INVENTORY": "STK-",
    "STOCK_LOAN": "LN-",
    "RECALL": "RC-",
    "STOCK_COUNT": "SC-",
    "ASSET": "FA-",
    "DEPRECIATION": "DEP-",
    "RECONCILIATION": "REC-",
    "DATA_CORRECTION": "FIX-",
}


def next_number(conn, entity_id: str, doc_type: str) -> str:
    row = q1(conn, """
        INSERT INTO fin_number_sequences (legal_entity_id, doc_type, prefix, next_value)
        VALUES (%s, %s, %s, 2)
        ON CONFLICT (legal_entity_id, doc_type)
        DO UPDATE SET next_value = fin_number_sequences.next_value + 1
        RETURNING prefix, next_value - 1 AS value, pad
    """, (entity_id, doc_type, DEFAULT_PREFIX.get(doc_type, doc_type[:3] + "-")))
    return f"{row['prefix']}{int(row['value']):0{int(row['pad'])}d}"


def next_preview(conn, entity_id: str, doc_type: str) -> str:
    """The number the next document of this type will take (nothing is reserved)."""
    row = q1(conn, "SELECT prefix, next_value, pad FROM fin_number_sequences WHERE legal_entity_id=%s AND doc_type=%s",
             (entity_id, doc_type))
    if not row:
        return f"{DEFAULT_PREFIX.get(doc_type, doc_type[:3] + '-')}{1:06d}"
    return f"{row['prefix']}{int(row['next_value']):0{int(row['pad'])}d}"


def last_invoice(conn, entity_id: str) -> Optional[Dict[str, Any]]:
    """The last invoice raised - in Roy Books (including hospital bills posted to the books) or, before that, Sage -
    so staff know where numbering stands each morning."""
    roy = q1(conn, """SELECT i.invoice_number AS number, i.invoice_date AS date, c.name AS customer, i.total, i.id::text AS id
                      FROM fin_sales_invoices i LEFT JOIN fin_v_customers c ON c.id=i.customer_id
                      WHERE i.legal_entity_id=%s AND i.status NOT IN ('DRAFT') AND i.invoice_number NOT LIKE '%%-VOID%%'
                      ORDER BY i.created_at DESC LIMIT 1""", (entity_id,))
    if roy:
        return {**roy, "source": "roy"}
    sage = q1(conn, """SELECT invoice_number AS number, invoice_date AS date, customer_name AS customer, amount AS total,
                              id::text AS id FROM fin_sage_invoices WHERE legal_entity_id=%s AND invoice_number IS NOT NULL
                       ORDER BY invoice_date DESC, row_no DESC LIMIT 1""", (entity_id,))
    return {**sage, "source": "sage"} if sage else None


def release_if_last(conn, ctx, doc_type: str, number: str, table: str, column: str, row_id: str) -> Optional[str]:
    """A voided document gives its number back when it is the last one issued, so the next document takes it and
    the sequence has no gap. The voided record keeps everything else and is renamed "<number>-VOID" (it stays in
    the audit trail and the registers). A number with later documents after it is not reused - that would leave a
    gap elsewhere. Returns the voided record's new name, or None when the number was not released."""
    from src.fin import audit
    from src.fin.db import ex
    seq = q1(conn, """SELECT prefix, next_value, pad FROM fin_number_sequences WHERE legal_entity_id=%s AND doc_type=%s
                      FOR UPDATE""", (ctx.entity_id, doc_type))
    if not seq:
        return None
    prefix, pad = seq["prefix"] or "", int(seq["pad"] or 0)
    raw = str(number)
    if not raw.startswith(prefix) or not raw[len(prefix):].isdigit():
        return None   # e.g. a hospital bill number: not from this sequence
    value = int(raw[len(prefix):])
    if f"{prefix}{value:0{pad}d}" != raw or int(seq["next_value"]) != value + 1:
        return None   # not the last number issued
    renamed, k = f"{raw}-VOID", 1
    while q1(conn, f"SELECT 1 FROM {table} WHERE {column}=%s AND legal_entity_id=%s", (renamed, ctx.entity_id)):
        k += 1   # the number was voided before
        renamed = f"{raw}-VOID-{k}"
    ex(conn, f"UPDATE {table} SET {column}=%s WHERE id=%s", (renamed, row_id))
    ex(conn, "UPDATE fin_number_sequences SET next_value=%s WHERE legal_entity_id=%s AND doc_type=%s", (value, ctx.entity_id, doc_type))
    audit.record(conn, ctx, "DOCUMENT_NUMBER_RELEASED", table, row_id, ref=raw, metadata={"renamed_to": renamed, "next_number": raw})
    return renamed
