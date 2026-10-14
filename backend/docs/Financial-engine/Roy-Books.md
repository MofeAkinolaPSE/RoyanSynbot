# Roy Books — Royan Hospital's finance hub (replaces Sage 50)

Roy Books is the double-entry finance module inside SynbotHealth. It replaces Royan's Sage 50 as the hospital's financial system of record and becomes the one place Finance works from:
- billing and the cashier
- patient, HMO and corporate receivables
- suppliers and payables
- pharmacy stock valuation
- banking, the general ledger and fixed assets
- budgets, month-end close and the financial statements

It is the ACE Books engine ([ACE-Books.md](ACE-Books.md)) carried over as §13 of that document prescribes: the kernel, engine rules, consistency contract and lineage layer are unchanged, and the parties, posting rules, stock and roles are adapted for a hospital. The ACE meeting minutes and study documents guided the design; **every Royan-specific choice below is a default to confirm with Royan's finance department** (§10).

---

## 1. In one paragraph

Every money- or stock-affecting event in the hospital becomes one document in Roy Books, for example:
- a bill raised
- a cashier payment
- an approved discount
- a waiver, write-off or correction-pen adjustment
- a drug dispensed
- stock received or adjusted by the pharmacy

That document posts one balanced journal through the one posting service. It posts in its own transaction, after the ward, till or pharmacy has already saved its work, so a books problem never blocks patient care or the cashier. Reports, statements, ageing and the Control Tower read only those journals and subledgers. Any figure opens the record behind it, down to the hospital bill, the patient and the drug batch.

## 2. How Roy Books connects to the rest of SynbotHealth

| Hospital module | Becomes in Roy Books | Rule |
|---|---|---|
| **Billing & Cashier** (`routers/billing_hospital.py`) — bill raised | Invoice for the **patient's share** (`BILLING`, numbered with the bill number) and, if an HMO covers part, a second invoice to the **HMO** (`BILLING_HMO`, 60-day terms). Revenue is split **by service line** (consultation, lab, radiology, pharmacy, ward, nursing, procedure, maternity, other) with the department on each line | Posted by `integrations.after_commit("BILL", id)` after the bill is saved |
| Bill discount (at billing, or approved by admin later) | Credit note to **Discounts Allowed** (49000). A *pending* discount is not booked | `BILL_DISCOUNT` |
| Cashier payment (cash / card / transfer / other) | Receipt into the bank/cash account set for that method, allocated to the bill's invoice. It keeps the printed **RHR receipt number**, and any overpayment stays on the patient's account as a deposit | `PAYMENT` |
| Payment method `waiver` / `hmo` | Waiver → credit note to **Patient Waivers**. HMO → the patient's share is **moved to their HMO** (credit note plus invoice to the HMO) | `PAYMENT` |
| Waive bill / write off bill | Credit note for what is still owed → **Patient Waivers** (63000) / **Bad Debts** (63100) | `BILL_WAIVER` / `BILL_WRITEOFF` |
| Correction pen (`royan_bill_adjustments`) | Reduction → credit note (Returns & Allowances). Reallocation → moved to the named payer (the patient's HMO, a named HMO, or a corporate account). Refund → a **refund** document paid out of the patient's credit. Reversal of a reduction → the charge is raised again | `BILL_ADJUSTMENT` |
| **Pharmacy dispensing** (`routers/pharmacy_dispensing.py`) | Cost of drugs dispensed (DR 50000 / CR 12000) from the **batch actually dispensed** (FIFO cost), linked to the patient, so a recall lists every patient who received a batch. A restocked return brings the cost back | `DISPENSING` / `DISPENSE_RETURN` |
| **Pharmacy stock received** (`routers/pharmacy_inventory.py`) | DR Pharmacy stock / CR **Goods Received Not Invoiced** (21100) at the batch's unit cost. The supplier's bill later clears 21100 | `PHARMACY_RECEIPT` |
| Pharmacy batch adjust / dispose | A **draft** stock adjustment that Finance approves (maker-checker). Approval never moves the pharmacy's stock a second time | `PHARMACY_ADJUST` |
| Roy Books supplier bills, adjustments and counts | Mirrored into the pharmacy's live batches (`royan_inventory_batches`), one way | `inventory._mirror_ops` |
| **Patients / HMOs** (`royan_patients`, `royan_hmos`) | One AR account per debtor (`fin_customers`), created the first time they owe anything. Name, MRN and contact are always read live from the clinical master (`fin_v_customers`) | One master per party |
| **Suppliers** | `suppliers` — the table the Suppliers router always expected. It never existed in this database, so that page was silently writing nowhere. Now one master for Procurement and Roy Books | Created in migration 220 |
| **Drug formulary** | Roy Books products (sku = formulary code, `fin_products.formulary_id`) | `hospital.ensure_product` |
| Hope (legacy HMS) | History only: supplier purchase lines and revenue/receipt views. **Never posts, never a balance** | §6 |
| Sage 50 | One-time transfer at cut-over: chart of accounts, trial balance, open receivables and payables | §7 |

Every hook is idempotent on its source and recorded in `fin_source_postings`. Failures appear in **Close & Controls › Hospital postings** with Retry and Exclude. The `OPERATIONS_POSTED` control also catches bills, payments and dispenses since go-live that were never attempted. Nothing posts until a **cut-over date** is set, and anything dated before it is inside the Sage opening balances. Hope-imported rows never post.

## 3. Engine rules (unchanged from ACE — must never change)

One posting path, database-enforced balance / period / immutability, reversals instead of edits, idempotency, subledgers reconciling to their controls, maker-checker, `Decimal` money. See ACE-Books.md §3.

Hospital addition: receivables have **two control accounts**, 11000 Patients and 11100 HMOs. The `AR_RECONCILES` control checks their sum against the open-item subledger.

## 4. Overlap register (one fact, one place)

| Purpose | Screens | Status |
|---|---|---|
| Raise a patient charge | Billing & Cashier; Roy Books manual invoice | Billing is the recording path; the manual invoice form tells staff to use it and warns about bills not yet in the books ✅ |
| Take money | Billing & Cashier payment; Roy Books receipt | The till posts its own receipt. Roy Books receipts are for HMO remittances, corporate payments and deposits ✅ |
| Refunds | Correction pen; Roy Books refund | The correction pen posts the refund; the Roy Books form is for refunds outside a bill ✅ |
| Discount approval | Admin discount card (Billing) | Approval posts the credit note; no second place records it ✅ |
| Vendor payments | Old Finance › Vendor Payments (a table that did not exist) | Redirects to Roy Books › Purchases › Payments ✅ |
| Budgets | Old Finance › Budget (`fin_budget_targets`, empty) | Redirects to Roy Books › Setup › Budgets ✅ |
| Analytics / reports | Old Finance › Analytics / Reports | Redirect to Control Tower / Report Center ✅ |
| Receivables ageing, credit risk | Credit Control & Alerts (`/finance/ar`, `routers/finance.py`) | ⚠️ **Still reads the legacy billing aggregates.** Rewire it to `fin/readmodel.py` once the books are live, as ACE did |
| Executive / Workstation finance tiles | `sage_adapter.kpis`, `routers/finance.py` | ⚠️ Same follow-up: delegate to `readmodel` after go-live |
| Stock on hand | Pharmacy › Inventory (live batches); Roy Books › Stock (valued FIFO) | Kept in step one way; the valued figure is the books' ✅ |
| HMO claims | HMO & Coverage (`royan_insurance_claims`); Roy Books HMO invoices | ⚠️ Claim status is not yet driven by the HMO invoice being paid; disallowances are posted as credit notes by Finance (§10) |

## 5. Lineage

`RecordView` / `DrillProvider` / `Facts` / `Totals` / `useListFilter` come from ACE unchanged.

Hospital views:
- **Invoice** shows the hospital bill behind it: bill number, encounter, HMO cover, discount status, a link to the printed bill, and its credit notes.
- **Patient / payer** shows type, MRN, balance, overdue, terms, any bills not yet in the books, invoices, receipts and refunds.
- **Drug** shows movements, batches, the patients dispensed it, and its Hope purchase history.
- **Batch** shows the recall list.
- **Supplier** shows bills, payments, and what was received from them in Hope.

## 6. What data we hold and where it came from

| Data | Source | Loaded into | Status |
|---|---|---|---|
| Chart of accounts | **Royan's Sage chart** (140 accounts, 22 bank/cash accounts) | `fin_accounts` | **Loaded**; 31 posting rules re-pointed to it (HMO revenue 4050, Main Hospital 4100, Lab 4200, Immunisation 4000, AR 1100, AP 2000 …). 83 unused template accounts retired; 5 kept where Sage has no equivalent (Patient Waivers 63000, Stock Adjustments 58500, Stock on Loan 12990, Goods Received Not Invoiced 21100, Asset Disposal 90000) |
| Opening balances | Sage GL Trial Balance at **31 Dec 2024** | Opening journal JV-000001 | **Loaded**: ₦1,232,922,551.01 each side |
| GL history 2009 → 2024 | Sage General Ledger | `fin_sage_gl_lines` (190,396 lines, 88,062 entries: CDJ 80,262 · GENJ 48,919 · SJ 32,603 · CRJ 28,612) | **Loaded**. Ties to the trial balance on all 113 accounts; balance sheet ₦716,031,593.99 and 2024 net income ₦99,548,450.93 equal Sage's |
| Sage invoices | Invoice Register (2010 → 2024) | `fin_sage_invoices` | **16,292 invoices, ₦2,179,322,968.13**; 95% linked to their sales entry |
| Sage receipts | Cash Receipts Journal | `fin_sage_receipts` + invoices each settled | **12,026 receipts, ₦2,179,322,968.13** (equals the invoices, year by year) |
| Sage customers | Customer List | `fin_sage_customers` → debtor accounts | **274**: 51 matched to the hospital's HMO register (2 exact, 49 by name, reviewed), 59 corporate, 164 private / sundry |
| Sage vendors | Vendor List | `suppliers.sage_vendor_id` | **14**: 5 merged with Hope suppliers, 9 new |
| Bank reconciliation | Account Reconciliation (Stanbic IBTC 1040) | `fin_sage_recon_items` | 1,916 open items Sage never cleared (deposits in transit ₦116.4M, outstanding cheques ₦128.6M) |
| Sage reports as delivered | Balance Sheet, Cash Flow, GL Account Summary, Trial Balance, Aged Receivables, Items Sold, Account Reconciliation, COA, Customer List, Vendor List | `fin_sage_reports` | Kept for tie-out and audit (Report Center › Sage History) |
| Suppliers | Hope `inventory_suppliers` | `suppliers` (`external_vendor_id = HOPE:<id>`) | **124 loaded** |
| Purchase history | Hope purchase orders + GRN lines (2016 → Jan 2026) | `fin_hist_purchase_lines` | **17,161 lines, ₦362,193,644.20**; 96% tied to a drug through the pharmacy's own batch record (`po_item:<id>`) |
| Products | Pharmacy formulary | `fin_products` | **815 synced** |
| Opening pharmacy stock | Live batches with stock and a unit cost (536 batches, ~₦50.7M) | FIFO layers + batches, no journal | Loader ready (Setup › Sage transfer & opening stock › *Load pharmacy stock*). Run at cut-over; tested to reconcile to the kobo |
| Revenue history 2016 → 2026 | Hope billing lines | `fin_v_hope_revenue_monthly` (view, lines above ₦50M excluded as mis-keyed and counted separately) | Available (`/fin/history/revenue`) |
| Receipts history | Hope cashier payments | `fin_v_hope_receipts_monthly` (view) | Available (`/fin/history/receipts`) |
| Open receivables / payables | Sage Aged Receivables | — | Sage's aged receivables are all zero (every invoice was receipted); no supplier invoices exist in Royan's Sage |

**What Hope cannot give us, and why:** Hope has no general ledger, payroll, expense or bank-reconciliation tables (all 506 dump tables were scanned). Its "balances" are unusable:
- bank accounts at `2147483647`, the Int32 maximum
- `PatientCard` receipts of ₦400bn in 2019 and ₦672bn in 2020 (card numbers keyed into the amount)
- 259K bills all "pending", because Hope payments carry no bill reference

Its chart of accounts is an Indian template (CGHS, TPAs). So Hope provides masters and history; Sage provides the money.

Staged in the Hope dump but not yet used: pharmacy sales returns (4,942 + 7,449 lines), tariff price-change log (7,668), stock adjustments (620), discount request history (2,082).

## 7. Sage history and the exports

**How the history works.** The trial balance at 31 Dec 2024 is the books' opening position. Underneath it, all 190,396 Sage GL lines are held line for line. `fin_v_ledger` reads the history plus every Roy Books journal, except the opening journal the history replaces (switched on only when the load ties out exactly, `fin_settings.history_replaces_opening`).

Statements, the trial balance, account drill-downs and the Report Center therefore work for **any year from 2010**, and every Sage figure opens its entry, invoice, receipt and customer. Sage closes each year's profit into retained earnings without journal lines; the balance sheet shows it as "retained earnings brought forward". Bank reconciliation, controls and year-end close read the books only.

**How Sage entries are grouped:**
- Sales and cash-receipt entries are exact: journal, date, reference and customer. All 16,284 sales and 12,019 receipt entries balance.
- Sage's GL export drops the transaction reference on most disbursement and general-journal lines. Those are paired by date and equal amount (bank credit ↔ expense debit), and the entry key marks it (`|#n`).

**The 13 exports received** (`sage-exports/`, as at 31 Dec 2024): Chart of Accounts, GL Trial Balance, General Ledger, Gl account summary, Balance Sheet, Cash flow, AR (Aged Receivables), Invoice Register, Cash Receipts Journal, items sold to customers, Customer list, Vendor list, Account Reconciliation. Load with:
```
python -m src.fin.sage_import --dir docs/Financial-engine/sage-exports [--dry-run]
```

**Second batch (2 Oct 2026, `sage-exports/new-exports/`):**
- **General Journal:** the same 48,919 lines as the GENJ lines of the General Ledger, with the same 43,118 lines without a reference. It confirms the ledger is complete but adds no references, so disbursements stay paired by amount. The importer now cross-checks it on every load.
- **Vendor Ledgers:** every vendor at ₦0, so Royan's Sage kept no supplier invoices. Suppliers were paid straight from the cash-disbursements journal, and Hope holds the purchase side (17,161 goods-received lines).
- **Balance Sheet / Budget:** the budget column is all zero, so no budget was ever set in Sage.
- **Hope has no general journal, disbursements or supplier ledger either.** Its "voucher entries" are patient charges, and its "voucher payments" are 526 patient-card refunds. Only Sage has those records.

**Still worth having:** the 2025 and 2026 Sage exports once Finance finishes them (upload them in Roy Books, §7a), and the fixed asset register (the GL carries ₦531.4M of fixed assets at cost with no per-asset list).

**Report coverage:** by default the Report Center shows the reports Royan uses and has data for (§7b). The full list of 131 Sage 50 report types is one click away ("Show the other … Sage 50 report types"). Each type either opens a Roy Books report or says why it isn't used at Royan.

New history-aware reports:
- Tie-out vs the Sage trial balance
- Sage invoice and receipt registers
- Sales history and transaction history per patient/payer
- Collections by payer type
- Income statement by year
- Transaction detail search
- Payments by payee
- Expense analysis
- Bank deposits
- The Sage reconciliation items
- Every Sage report as delivered

## 7a. Uploading later Sage exports (2025, 2026 …)

**Setup › Sage uploads** works in three steps: upload, check, load.
1. **Upload:** Finance uploads Excel exports under any file names. Each one is recognised by its worksheet name or header row. A report that isn't uploaded is taken from the last set that loaded (kept on the backend's data volume, `FIN_DATA_DIR/sage/current`).
2. **Check:** a full dry run (`sage_import.run(..., dry_run=True)`). It rebuilds the history, ties every account to the uploaded trial balance and balance sheet, then rolls back.
3. **Load:** only a set that ties can be loaded.

The "as at" date is the end of the last month the General Ledger reaches.
- **A newer trial balance rolls the opening journal forward** while the books aren't live: the old opening is reversed and the new one posted. `fin_v_ledger` hides both openings and the reversal while the history replaces them.
- **Accounts Finance added in Sage** join the chart.
- **Once the books are live, history stops at the cut-over:** Sage lines on or after it are skipped and never shown, so nothing is counted twice.

API: `GET/POST /fin/sage/uploads`, `GET /fin/sage/uploads/{id}`, `POST …/check`, `POST …/load`, `DELETE …`. Uploading or checking needs `migration.stage`; loading needs `migration.load`.

## 7b. Who paid: HMO / private, Hope and Sage together (`payers.py`)

Royan asked to "separate the HMO services so that we know what services went to HMO and at what cost, what services went to private and at what cost". The meetings also asked for HMO monthly bills, an HMO claims ageing report, daily and departmental revenue, and the discount approval trail.
- **Hope** priced every line against the patient's payer (its "tariff standard").
- **Sage** only has totals: HMO invoices in the sales journal, and private takings as general journals.

**Data (migration 223):**
- **`fin_hope_charges`:** 767,858 Hope lines from May 2016 to Jan 2026, loaded by `python -m src.fin.hope_charges --staging …`:

  | Source | Lines |
  |---|---|
  | Services | 225,495 |
  | Pharmacy | 261,914 |
  | Lab | 194,626 |
  | Radiology | 55,866 |
  | Ward | 29,957 |

  Each line keeps its gross, discount, cash and card paid at the till, visit, MRN and patient. Thirteen mis-keyed lines (₦1bn+ each, up to ₦2×10²⁶) are skipped and listed.
- **`fin_hope_payers`:** the 170 Hope payers, typed by name, and Finance can re-type any in **Setup › Payers** (a manual choice survives reloads):
  - PRIVATE: 2
  - HMO: 87
  - CORPORATE (retainerships, monthly-billing families, schools, churches): 69
  - STAFF: 3
  - INTERNAL (9 "For Scancare only – … paid by Royan" payers): Scancare work Royan pays for, so not a receivable
- **`fin_hope_payer_accounts`:** each Sage HMO or corporate account belongs to one payer. It matches by the same HMO record, the same name, or similar distinctive words, allowing for Sage's typos ("Achor" → Anchor, "Multisheild", "Lifeworh"). 61 accounts are linked to 55 payers. One payer can have several accounts; Mansard, for example, was billed both as an HMO and under NHIS.

**Reports (Report Center › Royan's requests):**
- HMO vs Private by month (click a month for its departments)
- Services by payer (click a department for each service)
- HMO monthly bills: click a payer for its bill, showing each patient, member no., visit and line
- HMO claims ageing
- HMO billing: Hope vs Sage per HMO and year
- HMO claims register
- Hope vs Sage revenue reconciliation
- Daily revenue & collections
- Discounts, waivers & write-offs
- Collections by payer type

Every visit opens a **Hope visit** drill-down (patient, payer, every charge line), and every HMO opens its Roy Books account with its Sage invoices and receipts.

**What the numbers say (2024):**
- **HMOs:** Hope billed HMOs ₦160.4m (including corporates) against Sage HMO revenue (4050) of ₦171.1m. They reconcile within timing and NHIS capitation.
- **Private:** Hope billed ₦530.6m against Sage private revenue of ₦338.6m.
  - Hope's tills collected ₦378.5m.
  - ₦93.5m of the Hope figure is Scancare's own walk-in lab and imaging customers. **Confirm with Finance whether that income is Royan's or Scancare's** (§10).
- **Claims ageing:** billed (Hope) less every receipt on the payer's Sage accounts since Hope started, applied to the oldest month first.
  - Anything an HMO paid beyond its billed lines (capitation, advances) is shown separately, not netted.
  - **Owed at 25 Jan 2026: ₦222.4m.** Most of it is 2025 billing, because Sage receipts stop at Dec 2024.
  - **At 31 Dec 2024 it was ₦97.2m,** mainly family and monthly-billing credit accounts that never had a Sage account. The largest are Akinola Family (₦32.5m) and Monthly Billing Patient (₦20.0m).

**HMO claims follow the HMO invoice** (`hospital.sync_hmo_claim`, called whenever an invoice's settlement changes):
- When the HMO share's invoice (source `BILLING_HMO`) is part paid or part disallowed, the claim becomes `approved` with the accepted amount.
- Paid in full: `paid`, settled on the last receipt.
- Wholly credited: `rejected`.
- A voided receipt moves the claim back.
- If no claim was submitted, one is recorded (`external_source='roy-books'`).

## 7c. Credit Control and the dashboards (`credit.py`)

Credit Control (`/finance/ar`), the Executive dashboard, the KPI watchdog, intelligence and Ask Synbot's tools read the finance functions in `services/sage_adapter`. Those functions now delegate to `fin/credit.py`:
- **Debtors:** HMO and corporate debt from `payers.hmo_ageing`, in the four Credit Control bands.
  - Once the books are live, debt up to the day before go-live comes from Hope, and debt from go-live onwards from the books' own open items.
  - Private patients pay at the till; Hope's line-level "unpaid" flags for them are unreliable (pharmacy is settled on the final bill), so they are not chased.
- **P&L:** from `fin_v_ledger`. Its 2024 totals are ₦509.7m revenue and ₦99.5m net profit, the same as Sage.
- **Cash:** the ledger's cash and bank accounts.
- **Run-rate cash forecast:** takings from the tills, spending from the ledger excluding depreciation, and HMO debt under 90 days.
- **Credit risk:** the page's own scoring rules, applied to these debtors.
- **Invoice match:** Sage invoices against the receipts that name them, plus Roy Books invoices.

"As of" is the last day Hope data reaches until the books are live, and every response says which source it used. The AR alert tables (`fin_ar_alert_rules`, `fin_ar_alert_events`) never existed, so they were created; a rule now records one open alert per debtor until acknowledged.

## 7d. The ACE Books implementation standard, applied to Roy Books (Oct 2026)

Source: `financemeetings/ACE Books → Roy Books implementation standard (Oct 2026 rounds).docx`, the two client meetings of 7 Oct 2026 and the Sage Payments screenshot. ACE Books' code (`Chat Assisant placeware x1`) is the reference. Each feature was rebuilt on Roy's own ledger view (`fin_v_ledger`), not on ACE's Sage tables, because Royan's Sage history is stored differently.

**Ledger and journals** (migration 229, `journal_map.py`, `journals.py`)
- **One journal code per posting.** `journal_map.SOURCE_JOURNAL` and the database function `fin_journal_code()` hold the same table, and a test keeps them equal. In Royan's terms:
  - a hospital bill is Sales (SJ), dispensing is Cost of Goods Sold (COGS), and goods received into the pharmacy are Purchases (PJ);
  - payroll is General (GENJ) and its payment is Cash Disbursements (CDJ);
  - bank vouchers split by kind: spend → CDJ, receive → CRJ, transfer → GENJ;
  - Data-issue corrections are ADJ, listed in the General Journal.
- **The ledger view carries `jrnl` and `hidden` on every line.** Sage lines keep Sage's own code.
- **Journals & Ledger has five tabs:**
  - **Journal entries:** Roy Books journals plus Sage's general-journal entries, tagged Sage.
  - **Journals by type:** the 8 books in Sage's column layouts. The list comes from `/ledger/journals`; it is never typed twice.
  - **General ledger:** one account in Sage's layout (monthly Beginning Balance, lines, running balance, Current Period Change), with search as you type.
  - **Trial balance.**
  - **Chart of accounts:** whole-ledger balance at any date, entries, and first and last entry.
  - The Statements page's old Journals tab now points to Journals by type.
- **Delete entry** posts the exact reversal on the same date. The pair is `hidden` from ledger detail but still nets in every balance. Voided documents behave the same way.

**Documents**
- **Invoice register** (`sales.invoice_register`) is the one invoice list: Sage invoices plus Roy Books invoices (hospital bills, HMO shares, drafts, voids). It shows the last invoice raised and the next number, and has a status filter.
  - Royan's Sage invoice numbers are per-HMO codes ("RELIANCE24"), not a running sequence, so ACE's "continue Sage's numbering" does not apply. Hospital bills keep their bill numbers.
- **Void gives the number back** when it was the last one issued: the voided record becomes `<n>-VOID`, then `-VOID-2` on a repeat (`numbering.release_if_last`). This applies to invoices, receipts, supplier payments and vouchers.
- **Record receipt** sits on every invoice with a balance. The receipt form accepts `?customer=`.
- **Receipts and supplier payments lists include Sage's history.** Sage cash disbursements count as payments, since Royan's Sage kept no supplier invoices.
- **Payment window** (`components/books/payment-window.tsx`, Sage's Payments screen):
  - **Supplier mode:** tick **Pay** on the bills being paid.
  - **One-off payee:** pay anyone, with no supplier record needed.
  - **Expense or asset lines:** each line shows the asset account's value before and after the payment.
  - **Asset register:** an asset line is registered with funding POSTED, so no second journal is posted. Its `voucher:<id>:<n>` reference is translated to the ledger line, so Assets in the books shows it as registered.
  - **Pay this bill** on a bill opens the window with that bill ticked.

**Fixed assets.** **Assets in the books** (`assets.asset_history`) reads every fixed-asset account from the ledger. At 31 Dec 2024: cost ₦531.36m, accumulated depreciation ₦103.31m, net book value ₦428.05m, across 6 accounts. Every purchase is searchable, and **Add to register** pre-fills the register form.

**Stock** (`hospital.stock_reconciliation`, `hospital.count_overview`)
- **Ledger · books · shelf:** the inventory accounts show ₦0 and Roy Books stock is ₦0, while the pharmacy shelf holds ₦50.75m in 536 batches (54 with no cost, 17 expired).
  - Royan's Sage expensed drugs when bought (5000 Direct cost of drugs), so opening stock must be loaded at go-live with a matching opening entry.
- **Stock counts** opens on every shelf batch, showing expiry, cost, value, what the books hold and when it was last counted.

**Data issues** (migration 230, `data_issues.py`, Close & Controls › Data issues, banner on the Control Tower). Detection runs on "Check again" and after every load. Resolutions are: accept (with a reason), link a payer's Sage account, post a correcting journal (FIX-nnnnnn, which opens both ways), or reopen. 8 October run, 24 open:

| Issue | Found |
|---|---|
| No books after 31 Dec 2024 | ₦1.04bn of Hope billing after it |
| Pharmacy stock not in the books | ₦50.7m |
| 9 payers with no Sage account | ₦94.2m |
| Hope vs Sage private gaps | 8 years |
| HMO billed in Hope but not invoiced in Sage | 2 payers |
| Expired stock still on the shelf | |
| Stock with no unit cost | |
| Sage invoices not matched to their receipts | |

The trial balance vs history check found nothing, because the history ties.

**Shared UX**
- **In-app dialogs:** `lib/ask.tsx` (`askText` / `askConfirm`, `<AskHost />` in App.tsx) replaced all 22 `window.prompt` / `window.confirm` calls in Roy Books, Sage uploads, billing and the correction pen.
- **Wide side panels:** `DetailSheet size="wide"` is used on every Roy Books and Credit Control panel. Clinical panels keep the narrow default.
- **CSV:** `CsvButton` exports the table on screen; Report Center keeps its own column list.
- **A–Z:** aged reports, name-keyed reports and the Credit Control list are alphabetical.
- **Credit Control alerts** form a worklist: Statement, Record receipt, Account, HMO bill, plus Show all and Alert rules.
- **Budgets:** rename, copy, delete and reopen.

**Also:** the migration runner commits `ALTER TYPE … ADD VALUE` first, and Roy's chat guide (`knowledge/roy_feature_guide.md`) describes the new screens.

**Parity checklist (Roy Books, 8 Oct 2026)**
- **Done:**
  - one ledger from 2010;
  - trial balance equals Sage;
  - no placeholder numbers;
  - finance pop-ups replaced;
  - wide panels and on-screen CSV;
  - void reissues the last number;
  - invoice register with last and next number;
  - record receipt from an invoice;
  - A–Z order;
  - Payment window (supplier, one-off, WHT, asset line → register, no second journal);
  - assets in the books equals the balance sheet;
  - chart-of-accounts history;
  - 8 journals by type that balance;
  - delete entry;
  - data issues with lineage and corrections;
  - Credit Control worklist;
  - every list with Sage history;
  - stock count overview;
  - budget actions;
  - migration runner;
  - assistant guide.
- **Not applicable to Royan:**
  - continuing Sage's invoice sequence (it has none);
  - lot letters and pack batch numbers on printed invoices (a Placeware pharma-distribution need);
  - the Frontdesk QC sign-off (Placeware);
  - ACE's roll-forward journals (Roy's Sage upload rolls the opening forward instead, §7a).
- **Not yet done:**
  - the full returns-outward page (the API to apply supplier credit exists);
  - recalls per invoice;
  - a printed Roy Books invoice in the client's template (hospital bills print from Billing);
  - scheduled backups (the stack has its own backup container);
  - the security-header review;
  - 9 browser pop-ups in clinical panels.

Tests: `tests/fin/test_journal_map.py` covers:
- every posting source has a journal;
- each code belongs to exactly one report;
- SQL and Python agree;
- vouchers land in their own journals;
- delete entry hides the pair and restores balances;
- void number release, including VOID-2;
- an asset paid by voucher is registered once with no second journal.

55 finance tests and 146 frontend tests pass.

## 7e. Live from the EMR: stage billing, the cashier, Scancare (finance meeting, 10 Oct 2026)

**Books live.** `POST /fin/setup/go-live` (`hospital.go_live`) set the cut-over to **10 Oct 2026**, loaded the
pharmacy's batches as opening stock (JV-000002, ₦50.7m) and from then on every bill, receipt, void and dispensing posts
by itself. Before this the cut-over was empty, so every hook skipped: that is why the GL, P&L and balance sheet never moved.

**Workflow (pay before services).** Front desk → cashier → doctor → cashier → services.
- *Front desk* (`POST /queue/encounters`): bills registration (new patients, ₦7,500) + the consultation, priced
  doctor's own fee → specialty tariff → staff specialty → clinic → General Practice; follow-up price inside the
  specialty's follow-up days. The form shows the price before registering (`GET /billing_hospital/consultation-quote`).
- *Doctor* ends the consultation (or `POST /queue/encounters/{id}/send-to-cashier`): everything ordered and not yet
  billed is billed - lab + drugs on a **Royan** bill, scans on a **Scancare** bill (`services/stage_billing.py`).
  Each line carries `source/source_id`, so nothing is billed twice.
- *Services*: lab sample collection, starting a scan and dispensing return **402** for a private outpatient whose bill
  is unpaid. Cleared by: paid / waived; part-paid and *released* by the cashier; a supervisor release with a reason
  (`POST /billing_hospital/releases`); HMO, staff scheme and admitted patients are never held; orders placed before
  `pay_first_since` are not held. Mode in `royan_billing_settings.pay_first` (Fee Schedule › Consultation fees).

**Corrections at the cashier.** Void a receipt (reason) → the bill goes back to what the remaining receipts cover,
Roy Books voids its receipt; record the right one. Void a bill (only with no standing receipts) → Roy Books voids the
invoice(s); its orders become billable again. Waiver / HMO transfers are corrected with the correction pen.
Patient account tab: every bill (debit) and receipt (credit) with a running balance, per company.

**Documents** (`/hospital/billing/:id/invoice`): the Royan invoice (Sr No / Item / CGHS code / Rate / Qty / Amount,
amount in words, Amount Paid, Balance, signatories), `?receipt=ID` the Royan receipt (Total Bill, Total Paid,
Previous, Balance, "Received with thanks…"), `?claims=1` the HMO claims form with the patient's signature from the
pharmacy tablet (signature pad in the pharmacy panel). Scancare bills print the same layout on Scancare's letterhead.

**Scancare.** A second company (`SCN`) with its own chart and books. `integrations.entity_for` routes a bill, its
receipts and voids to the company on the bill (`royan_billing.entity`). Finance › Scancare Books opens every Roy Books
screen on Scancare (`?company=SCN`, company switch in the header). The Scancare workspace (sidebar "Scancare
(Radiology)") has its own dashboard (`GET /radiology/scancare/overview`: studies, walk-ins vs referrals, queue,
report time, billed / collected / outstanding, payer mix, top studies, revenue in its books; Hope history toggle) and
a *To bill* list with **Bill study** for walk-ins (`POST /radiology/orders/{id}/bill`).

**Department stock.** `royan_department_stock` (migration 233) holds stores other than the pharmacy. Loaded from
Hope's Lab (146 batches, ₦3.31m, 116 expired) and Urology (87 batches, ₦3.54m) stores by
`scripts/load_hope_department_stock.py`. Hope last maintained them in 2019–2020, so they are shown on Stock ›
"Stock by department" but **not** put in the ledger until a stock count confirms them.

**Later trial balances.** With the books already open, loading another trial balance (Setup › Migration) posts the
difference between finance's figures and the books at its date (`migration._true_up_tb`, source ref `TB-TRUE-UP`):
balance-sheet accounts cumulative, income/expense year to date, retained earnings including unclosed prior profit.
This is how finance's reconciled 2025 year-end and the balances at go-live come in. Setup › *What data we have*
shows each source's dates and the gaps (ledger 1 Jan 2025 – 9 Oct 2026; Hope activity after 25 Jan 2026).

**Data notes.** Royan's Sage never carried debtors or creditors (both control accounts are nil across 2010–2024), so
aged receivables/payables start from go-live. Two price lists exist: `royan_fee_schedule` (Fee Schedule page) and
`royan_service_catalog` (what billing uses); consultation prices are edited through Consultation fees, which writes the
catalogue.

**Round 2 (same day).** HMO claims marked *paid* in Billing › Claims post the HMO's receipt against its invoice
(`CLAIM_PAYMENT`, into the transfer account); recording the remittance in Roy Books instead updates the claim, so
either side works. POS is a payment method (posts to the POS account). The cashier's *Receive* button fills the
outstanding amount (change it for a part payment) and prints the receipt. Every customer and supplier is a ledger:
Receivables › Customer ledgers and Purchases › Supplier ledgers (`/fin/ledgers/customers|suppliers`) with
invoiced / received / credited / balance and Owing / Paid in full / In credit, each with Receive / Pay. WHT is picked
as a rate and worked out on the invoices ticked (`components/books/wht.tsx`); discounts take a % (cashier) or "10%"
(invoice lines). Stock › By department: Pharmacy plus every department store, each row with *Adjust*; department
movements are their own ledger (`royan_department_stock_moves`, `fin/dept_stock.py`, migrations 234–235) and post
journals (INAJ) once the store is counted and *Put in the books*. Close › Exceptions can be resolved with a note.

**Round 3 (walk-through fixes).** Date filters keep a half-typed year instead of falling back to today (one fix in
`kit.tsx DateRange`, used by every page) and offer This month / This year / Last year / All. Account panels say when an
account was last used and jump there; voided pairs stay hidden in ledger detail (the agreed "delete entry" rule) with
a count and *Show them*. Customer ledgers have three sources never added together: Roy Books, each patient's Hope
history (bills less Hope receipts - unreconciled), HMOs & companies before go-live (Hope billing less Sage receipts,
`fin/ledgers.py`); Aged receivables shows the pre-go-live payer aging under the books' own. Hope's goods-received
records (7,556, 2016-Apr 2026, ₦346.9m) load into `fin_hope_purchases` (`scripts/load_hope_purchases.py`): Purchases ›
Purchase history, supplier ledgers, purchase register and items-purchased reports. Sage never had a purchases,
cost-of-sales or inventory-adjustment journal (suppliers were paid from the cash book), so those journals start at
go-live. Scancare: own bill/receipt series (SCB-/SCR-, migration 237), own Billing & cashier tab with New walk-in
(`POST /radiology/scancare/walk-in`, bills without an encounter - migration 239), standalone sidebar entry; the
hospital billing list shows Royan's bills unless switched. Stock: every product has a department (migration 238);
every Stock tab follows one department switcher (Pharmacy, Laboratory, Immunisation, Urology, Ward, Theatre,
Physiotherapy, Central stores); a counted store becomes products + FIFO layers so valuation/batches/activity read it.
Departments run their own stores at Pharmacy › Department stores (`/stock/stores`, `routers/department_stores.py`) -
Immunisation and Lab have a stock button; putting a store in the books stays with finance. Banking accounts can be
removed (deleted if never used, otherwise closed). Report Center tables are compact (no sideways scroll).

**Round 4.** General Ledger, Customer Ledgers and Vendor Ledgers follow Sage 50's layout (template
`financemeetings/Gl.xlsx` - a vaccine distributor's Sage export used for its layout only, not loaded): Account ID ·
Account Description · Date · Reference · Jrnl · Trans Description · Debit Amt · Credit Amt · Balance; per account (by ID)
or customer / vendor (A-Z), month by month Beginning Balance → transactions → Current Period Change, then Ending
Balance (`fin/sage_gl.py`, `/fin/ledgers/sage-gl`, `/fin/ledgers/customer-gl`; Report Center general-ledger /
customer-ledgers / vendor-ledgers). A patient's ledger from the hospital's records uses the same layout. Report Center
lists and every ledger list read A-Z. Empty ranges explain the 1 Jan 2025 - 9 Oct 2026 gap (Sage history ends 2024).
Scancare is its own set of books on every page; Hope history (patients, pre-go-live HMO balances, Hope purchases,
Hope cashier takings) shows in Royan's books only. Scancare Books' "Billing & Cashier" opens Scancare's billing.
Go-live test data (8 TEST patients, 9 bills, 42 journals) was purged at the owner's request (backup
before_test_purge.dump); next numbers RHB-2026-294645 / RHR-2026-000001 / SCB-/SCR-2026-000001 / JV-000003.

**Round 5 (client GL, 10 Oct 2026).** `financemeetings/GLroyan.xlsx` - Royan's own Sage General Ledger 2009-2024 - ties
to the books exactly: 121 accounts, 190,396 lines, every debit and credit total, and every 2024 ending balance on Sage's
basis. Nothing new to load. Sage closes "Equity - gets closed" accounts (3940 Capital's in Bank, ₦20.56m in 2017) into
retained earnings with income and expense; the balance sheet, retained-earnings statement and Sage-layout ledgers now do
the same (`journals._closed_into`), so 3910 reads -₦510,617,303.50 and 3940 nil at 31 Dec 2024, as Sage prints them
(test_sage_closing.py). The Sage-layout GL prints every account ever used, as Sage does. Side panels open at half the
screen or more (DetailSheet, PANEL_WIDTH).

## 8. Where things live

- **Database:**
  - `219_fin_core.sql` — the kernel, unchanged; settings renamed to `auto_post_operations` and gained `receipt_accounts`
  - `220_fin_modules.sql` — parties, suppliers, subledgers, refunds, source links
  - `221_roy_books_hospital_seed.sql` — `fin_seed_hospital_template()`, Hope history table and views
  - `223_roy_books_payers_uploads.sql` — Hope charges and payers, payer ↔ Sage accounts, Sage uploads, AR alerts, `fin_v_ledger` with roll-forward and cut-over
  - `229_roy_books_journals_assets.sql` — `fin_journal_code()`, `fin_v_ledger.jrnl / hidden`, `fin_fixed_assets.source_line / funding`
  - `230_roy_books_data_issues.sql` — `fin_data_issues`, `fin_data_issue_actions`
- **Backend** (`backend/src/fin/`, router `/fin`):
  - ACE modules, adapted
  - `hospital.py` — products, batches, opening stock, party search
  - `integrations.py` — the hospital hooks
  - `hope_history.py`, `hope_charges.py`, `sage_import.py` — loaders; `sage_uploads.py` — Finance's uploads; `sage_history.py` — Sage record views
  - `payers.py` — HMO / private reports and the Hope visit drill-down; `credit.py` — Credit Control and dashboard read model
  - `journal_map.py`, `journals.py` — journal codes, journals by type, Sage-layout account ledger, chart history; `data_issues.py` — the Data issues register
  - `222_roy_books_sage_history.sql` — Sage history tables and `fin_v_ledger`
  - Hooks in `routers/billing_hospital.py`, `pharmacy_dispensing.py`, `pharmacy_inventory.py`
- **Frontend:**
  - `lib/books-api.ts`, `components/books/*`, `components/workspace/{DetailSheet,FilterBar,PageHeader}.tsx`, `pages/books/*` (routes `#/finance/books/*`, lazy-loaded)
  - Sidebar group **Roy Books** holds every finance screen: Billing & Cashier, HMO & Coverage, Credit Control, Fee Schedule and Payment Gateway, plus the Books pages. Stock is also visible to pharmacists and QA.
- **Infrastructure:** `deploy/nginx/nginx.conf` proxies `/fin/` (25 MB uploads, 900 s timeout); `vite.config.ts` proxies `/fin` in dev.
- **Roles** (`fin/context.py`):
  - admin: everything
  - finance: bookkeeping and close
  - management: reports, approvals, reopen, settings
  - pharmacist: stock, counts, adjustments (maker), recalls, batch status
  - quality_assurance: recalls and batch status
  - ops / procurement: read payables and stock

## 9. Go-live runbook

1. **Done (1 Oct 2026):** Royan's Sage chart, opening trial balance at 31 Dec 2024 and full history are loaded and tie out (§6–7). **Next, Finance brings 2025 (and 2026) up to date in Sage and uploads the exports in Setup › Sage uploads (§7a).** The opening rolls forward to the last year end. Then set the go-live date in Setup › Settings, the day after the last Sage year end. Load the Sage set *before* setting the go-live date.
2. **Setup › Posting rules**: re-point any rule whose template account differs from Royan's chart (receivables, service-line revenue, Goods Received Not Invoiced, waivers, bad debts). **Setup › Settings**: confirm which bank/cash account receives cash, card and transfer at the till.
3. **Setup › Sage transfer & opening stock › Load pharmacy stock** as at the day before cut-over. Then compare the inventory GL with the valued stock in Close & Controls, and book any difference with the accountant.
4. Register fixed assets as opening balances (Fixed Assets).
5. Deploy: `docker compose build backend frontend && docker compose up -d backend frontend`. The entrypoint applies migrations 219–221. Load Hope history on the dev machine (`python -m src.fin.hope_history --staging …`) before taking the database dump that goes to the server.
6. Prove the live path: raise one real bill with an HMO share, take a payment, dispense a drug. Check the Control Tower, the patient's and the HMO's statements, and the drug's batch.
7. Close each month from Close & Controls › Periods.

## 10. Confirm with Royan's finance department

These are sensible hospital defaults, not yet confirmed:
- **When revenue is recognised:** at bill creation. Should inpatient charges accrue daily instead?
- **HMO terms:** 60 days by default, editable per HMO. Are HMOs billed per encounter (as now) or in monthly batches?
- **Claim disallowances:** how are they agreed and booked (credit note to 49100), and should a disallowance be re-billed to the patient?
- **Deposits and advances:** they sit as unapplied credit on the patient's account. Should they go to a liability account (21500) instead?
- **Refunds:** paid from the cash till by default; which account really pays them?
- **Service lines and departments:** does the chart split revenue the way their management accounts do (e.g. maternity, physiotherapy, dental)?
- **Consultant fees, payroll, PAYE/pension/NHF:** accounts exist but no workflow yet; payroll needs the Nigerian statutory research ACE flagged.
- **VAT / WHT:** HMOs deducting WHT is supported on receipts. VAT is refused until its treatment is confirmed.
- **Purchasing:** is a PO → GRN → invoice flow wanted? Pharmacy receipts already use Goods Received Not Invoiced.
- **Approval thresholds** for journals, discounts and write-offs.
- **Scancare:** are the "Scancare Radiology and Lab" walk-in customers billed through Hope Royan's income or Scancare's (₦93.5m in 2024)? Are the "For Scancare only – … paid by Royan" lines a cost to Royan?
- **Payer types:** check Setup › Payers, especially family and monthly-billing accounts (Akinola Family, Monthly Billing Patient, LAP with Dr Ekweme). Are they credit customers who owe money, or are they settled some other way?
- **HMO claims:** the HMO reconciles in its own portal. Should remittance advice be entered against each HMO invoice (driving the claim status), or one receipt per HMO per month?

## 11. How it was verified

- **Golden tests** (`backend/tests/fin/`): the **27 ACE tests** pass unchanged against Royan's schema, plus **14 hospital tests** (`test_hospital_flows.py`) and **7 payer / claim / upload tests** (`test_royan_payers.py`). The payer tests cover the claim moving with the HMO invoice (part paid, paid, voided, wholly disallowed, recorded when never submitted), payer typing, FIFO ageing, and recognising Sage exports by content. The hospital tests cover:
  - the patient / HMO split by service line
  - idempotency and before-cut-over skipping
  - receipts by method, overpayment as credit
  - discounts, pending discounts, waivers and write-offs
  - HMO transfer, reduction → refund, reallocation to a corporate
  - dispensing cost by batch and the recall trace, restocked returns
  - Goods Received Not Invoiced and draft pharmacy adjustments
  - opening stock reconciled to the kobo against every live batch

  After every event the balance sheet balances and AR, AP and inventory agree with their controls.
  ```
  FIN_TEST_DATABASE_URL=postgresql://postgres:<pw>@localhost:5433/synbot_health JWT_SECRET=<32+ chars> \
    python -m pytest tests/fin -q -p no:cacheprovider
  ```
- **API smoke:** the real backend image with the new source, on the Royan network. All 57 endpoints the pages call return 200, and 31 of the 32 Report Center reports do. The account register rightly asks for an account.
- **Frontend:** `tsc` is clean for every Roy Books file, all 142 unit tests pass (navigation guard, render-safety), and `vite build` succeeds with every Books page in its own chunk.


**HMO desk (Oct 2026).** `/hospital/hmo/desk` (Finance › HMO Desk): only the HMO patients on the live queue
(`GET /coverage/hmo-desk?days=N`, native encounters only), with HMO + card number, stage, labs back, drugs dispensed
(pharmacy sign-off shows as it happens), bills / HMO share / patient owes, claims-form signature and the officer's
check (`POST /coverage/hmo-desk/{encounter}/signature`, `/verify`; columns on `royan_encounters`, migration 241).
The patient signs once per visit (HMO desk or pharmacy pad); the claims form prints `claim_signature_url`, else the
drug-collection signature. Diagnoses on the form come from `royan_clinical_diagnoses`, else the SOAP notes'
`icd10_codes` (`billing_hospital.visit_diagnoses`). Bills carry `payer_type`, `hmo_name`, `membership_id`
(`?payer=hmo` filter). Invoice/receipt signatories: Bill Manager / Med. Supdt. / Authorised Signatory are billing
settings (`signatory_*`, "Name, title"); the cashier is whoever took the payment (`_people` resolves user ids to staff).
Signatures live in `src/signatures.py` → `/app/data/signatures` (persistent volume; the old in-image folder was wiped
on every deploy). HMO default (decided 12 Oct 2026): with no coverage rule the HMO pays in full (`coverage_type`
`default_full`, warning `hmo_default_full_cover`); a rule overrides it. The HMO team confirms eligibility and the
patient's package on the HMO's own platform; Roy exposes the claims form and the patient's signature. HMO Desk is
the first tab of HMO Desk & Coverage (`/hospital/hmo`, `/hospital/hmo/desk` redirects). Roles added (migration 242):
`hmo`, `cashier`, `store`, `auditor` (auditor-only accounts are refused every write in `verify_jwt`). Med. Supdt. and
Authorised Signatory fall back to whoever handled billing until named in billing settings. The swarm compose mounts
`backend_data:/app/data` too.


**Go-live end-to-end run (12 Oct 2026).** `python backend/tests/e2e_golive.py` drives a private and an HMO patient
from registration to discharge (room assignment, desk priority = triage, vitals, SOAP + ICD-10, lab, Scancare scan,
cashier, results review, dispensing + signature, HMO Desk / claims form / verify, discharge) plus a Scancare walk-in,
and checks Roy Books (bills, receipts, dispensing posted; HMO invoices to the HMO receivable; Scancare in SCN).
90/90 passed. Test patients are `ZZTEST E2E ...`; remove a run with the purge in the session notes (restores stock and
cost layers, continues numbering from the last real document). Fixed in that run: room assignment 500 (assigned_by is
a royan_staff FK), doctors signed in now count as on seat (presence), the doctor's room for the day comes with the
patient, dispensing the last prescription moves the visit to pay & discharge, voided consultations no longer make the
next visit a follow-up, name search keeps best-match order.
