# Phase D — final extraction findings

**Date:** 2026-08-29
**Source:** `data-assimilation/Docs/NEw Dump/db_drmnigeria-20260125.sql.gz` (654 MB)
**Full table inventory:** `HOPE_TABLE_INVENTORY.md` (506 tables)

---

## The headline: the dump read found no new rows, and was still worth doing

The hypothesis was that `tariff_lists` had been truncated — 434 rows staged
against 1,578 referenced by the pricing grid. A complete re-read returned
**434 rows again**. The table was never truncated and **that hypothesis was
wrong**.

But the 17,401 rows that would not resolve were `is_deleted='0'` with
create_times as recent as the ones that did — which does not fit "references
deleted services" either. Testing that contradiction produced the real answer:

> **`tariff_amounts.tariff_list_id` is polymorphic**, discriminated by
> `service_category_id`.
>
> | category | points at | rows | resolve |
> |---|---|---|---|
> | 3 — Radiology | `radiologies.id` | 7,519 | **100%** |
> | 26 — Laboratory | `laboratories.id` | 9,584 | **74%** |
> | everything else | `tariff_lists.id` | 6,872 | — |

Resolution went from **6,872 (28%) to 21,463 (88%)** of priced rows, covering
**113 payers and 807 services** — without extracting a single new row.

The pass cost **14.4 hours**, far beyond the 30–45 minutes estimated. It earned
that cost by *disproving* a hypothesis rather than by returning data.

---

## What loaded

| | before | after |
|---|---|---|
| Patient insurance policies | 0 | **21,761** |
| Patients with an insurance number | 0 | **18,124** |
| Lab tests priced | 20 | **281 of 288** |
| Radiology studies priced | no column | **209 of 211** |
| Per-payer rates | 28,750 | **49,330** |
| Encounters linked to a department | 0 | **269,422** |
| Active HMOs | 208 (46 demo) | **162, all real** |

### Insurance — the client asked twice, in both meetings

`royan_patient_insurance` had **0 rows**, which is why the HMO dashboard showed
nothing. Hope's `new_insurances` (162,991 rows) had been staged months ago and
never loaded.

**The key was not what its name said.** `patient_uid` sounds like an MRN. It
holds `persons.id`:

```
patient_uid -> persons.patient_uid (the MRN)  ...      0 / 18,126
patient_uid -> persons.id                     ... 18,126 / 18,126  (100%)
```

Trusting the column name would have loaded zero rows while reporting success.

162,991 raw rows carry ~4 historical revisions per patient; deduplicated to the
latest per (patient, payer) with a real number, that is **21,776 policies across
18,126 patients**. 21,761 loaded — 15 skipped because their Hope payer does not
exist in `royan_hmos`, and a membership number filed against a guessed payer is
worse than one that is absent.

`priority` is the literal `'P'` on all 162,991 rows so it cannot mark the primary
policy; the loader marks the most recent per patient. **Primaries = patients
exactly (18,124), with zero patients holding two.**

### Base prices now mean something

Migration 188 used "the max observed charge" as list price because the payer
dimension had been flattened. Hope has an explicit self-pay tariff —
**`tariff_standard_id = 7`, "Private"** — and that is now the source: 247 of 271
lab tests and 334 of 434 services carry one.

**Radiology has no Private tariff at all (0 of 211)**, so its base price is the
modal price across payers. The column comment records that it is an
approximation rather than an exact list price.

---

## What genuinely does not exist in Hope

Stated plainly so nobody hunts for it again.

**HMO codes.** The client asked "what about the code?" `tariff_standards` has 170
rows in which **only `name` is populated** — `payer_id`, `type`, `contact`,
`org_ext_id` and `code_name` are empty on every real row. The one
apparently-populated row is a CSV header imported as data (`name='name'`,
`type='Type'`); it was correctly filtered out before loading. Codes must be
entered by staff.

**Ambulance transactional data.** Five table names guessed (`ambulances`,
`ambulance_services`, `ambulance_bookings`, `ambulance_charges`,
`ambulance_trips`) — **none exist**. Ambulance survives only as two priced
services (₦80,000 long distance / ₦60,000 short). There is no dispatch, trip or
vehicle record to migrate.

**Staff attendance / timesheets.** Ten names guessed (`attendances`,
`timesheets`, `staff_attendances`, `employee_attendances`, `user_attendances`,
`time_sheets`, `shifts`, `duty_rosters`, `staffs`, `staff`) — only
`duty_rosters` exists, and it is **empty**. So the clock-out problem has no
legacy data behind it; it is purely the three code defects recorded in the plan.

---

## Known limitations, recorded not hidden

**2,810 priced rows (12%) still do not resolve.** They point at ids absent from
`tariff_lists`, `laboratories` and `radiologies` alike. Most carry
`service_category_id` values outside the three known kinds. Left unresolved
rather than force-matched.

**All pricing ambiguities are now itemised in `PRICING_REVIEW_FOR_FINANCE.md`**
— a document written for Royan's finance team, listing every affected service by
name with the prices Hope held, what we chose, and a blank column for their
correction. Four decisions are needed: two test payers still switched on (1,670
prices, zero patients), three staff schemes priced at N1-N10 (probably the staff
benefit, needs confirming), 47 services with conflicting prices, and 69 with
implausibly wide spreads.

A finding worth noting from building it: **1,424 of 49,330 payer rates (2.9%) are
placeholders of N10 or less**, and 950 of those belong to two test payers. Once
placeholders are excluded, services with a >50x spread drop from 342 to **69** —
the grid is far sounder than the raw spread suggested.

**131 of 21,245 (payer, target) groups carry conflicting charges.** "Latest Hope
id wins" looked obvious and was wrong: General Ward has two Private rows created
the *same day*, ₦3,000 and ₦200, so id order picks ₦200 for a ward day. The
loader now takes the **highest** charge — under-charging an HMO is harder to
correct after the fact than over-charging, which surfaces immediately — and
reports the count. Median spread among the conflicting groups is 6.7×, worst
1000×. **These deserve a human eye before they drive billing.**

**Room tariffs are priced but rooms are not modelled.** `rooms.tariff_list_id`
resolves for all 17 rooms, and ward services are priced (40 of 43), but
`royan_wards`/`royan_beds` carry no room identity — 17 real rooms appear in
charge history with nowhere to live. Modelling the room as a first-class entity
is an implementation item, not an extraction one.

**102 of 1,221 catalogue services remain unpriced** (down from 905 — see the
pharmacy section below). What is left is non-drug pharmacy lines with no
formulary entry (blood products, "Prescription Medicine", consumables), 17 lab
and 13 imaging rows whose names do not match their own catalogue exactly, and
the two outliers deliberately excluded.

---

## A counting bug worth recording

`load_tariff_pricing` first reported `base_service: 312` when the true figure was
**0**. `_exec_with_savepoint` returns whether the statement *ran*, not whether it
changed anything, and the service UPDATE carries an "only if unpriced" guard —
migration 197 had already priced 317 of the 400 matching services.

The obvious fix, reading `cur.rowcount` after the call, reported 0 for
*everything* — because `RELEASE SAVEPOINT` executes last and the rowcount
reflects the release. `_exec_with_savepoint_rc()` now captures it between execute
and release, which is the only correct point.

---

## Pharmacy pricing (migrations 202-203) — no dump data required

Catalogue coverage went **316 of 1,221 (26%) to 1,119 of 1,221 (92%)**.

| category | priced | of |
|---|---|---|
| pharmacy | 817 | 864 |
| consultation | 130 | 138 |
| ward | 40 | 43 |
| procedure | 82 | 93 |
| lab | 23 | 40 |
| imaging | 18 | 31 |
| misc | 9 | 12 |

### max(mrp) was the wrong aggregate, and one drug proved it

RANFERON CAP carries five rates:

```
714,286,000,000.00   batch med-262    expired 2017   <- typo
           125.00    batch A14        expires 2026
            95.00    batch 333        expires 2024
            38.00    batch IVES-261   expired 2017
            30.00    batch dist-260   expired 2017
```

`max()` prices an iron supplement at N714 billion. The **current batch** (latest
expiry) gives N125 — the price actually in force — and that is the rule used.

A blanket price cap would also have been wrong: **Pembrolizumab (Keytruda) at
N2,400,000 and Bevacizumab at N645,100 are real oncology prices**, and any cap
low enough to catch the typos would have discarded them.

**Two rows deliberately left unpriced**, because no correct value could be
derived: `GLOVE STERILE 7.5` (N10,001,000, single rate, no sane alternative) and
`LEVAMISOLE TAB (KETRAX) 47.2MG` (N0.20). An absent price prompts someone to
enter one; a wrong price bills a patient.

### A modelling problem, surfaced not papered over

Lab tests and imaging studies exist in **two catalogues at once** —
`royan_lab_catalog` / `royan_radiology_catalog` (read by the worklists) and
`royan_service_catalog` (read by `calculate_coverage` and the HMO catalogue).
Pricing one left the other at zero, so the same test quoted differently
depending on which side asked.

Migration 203 bridges the 28 of 58 rows that match by **exact name**. The other
30 do not match and were left alone: fuzzy-matching test names is how a "FULL
BLOOD COUNT" ends up billed as a "BLOOD CULTURE". The duplication itself is a
schema problem for a later phase, not something to hide behind a looser join.

### End-to-end proof

Patient 67797, HMO "MH", membership `MH/CONOIL/086/G-C`:

| service | list price | negotiated rate |
|---|---|---|
| BCG-HBV-OPV VACCINE | N10,000 | **N3,000** |
| CERVICAL CANCER VACCINE | N70,000 | **N10,000** |
| CHICKEN POX VACCINE | N37,500 | **N8,000** |

Before this phase the patient had no insurance record, the services had no list
price, and no payer rate existed — every quote resolved to N0.
