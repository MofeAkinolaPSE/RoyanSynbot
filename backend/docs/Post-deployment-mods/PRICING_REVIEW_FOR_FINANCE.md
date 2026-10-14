# Pricing review — for Royan finance

**Prepared:** 29 August 2026  
**From:** Synbot migration team  
**Action needed:** confirm or correct each price below.

Everything here came out of the Hope migration. None of it is a software
fault — it is what the old system actually held. We have loaded a working
value in every case so the hospital can bill today, but each one is a
judgement we made on your behalf. We would rather you corrected them here
than found them on a patient's invoice.

Mark this document up however is easiest and send it back.

---

## Summary — four separate things to decide

| # | Issue | Size | What we did | Decision needed |
|---|---|---|---|---|
| 1 | Two test payers still switched on | 1,670 prices, **0 patients** | Left them on | Switch off? |
| 2 | Staff schemes priced near zero | 13,634 prices, 209 patients | Left as-is | Confirm this is the staff benefit |
| 3 | Hope held two prices for the same thing | **47 services** | Took the higher | Confirm or correct each |
| 4 | Prices that look wrong | **69 services** | Loaded as-is | Confirm or correct |

Two further items are informational only and need nothing from you — they are
at the end.

---

## 1. Two test payers are still switched on

Both are named as tests. Neither has a single patient attached. Between them
they carry 1,670 prices that appear in reports and dropdowns alongside real
payers.

| Payer | Prices held | Patients | Recommend |
|---|---|---|---|
| testtariff | 920 | **0** | Switch off |
| TESTING ONLY HMO- NOT REAL | 750 | **0** | Switch off |

**We have not switched these off.** They are trivial to disable and equally
trivial to restore, but that is your call, not ours.

---

## 2. Staff schemes are priced at ₦1 to ₦10 — is that deliberate?

Three staff tariffs carry thousands of prices at or below ₦10. Our reading is
that this is the **staff benefit** — employees get medication at a nominal
charge — and not a data fault. Unlike the test payers, these have real
patients attached.

| Scheme | Prices at ₦10 or below | Total prices | Patients |
|---|---|---|---|
| ROYAN STAFF | 11968 | 196064 | 176 |
| PLACEWARE STAFF | 1274 | 28938 | 26 |
| SCANCARE STAFF | 392 | 7420 | 7 |

**Please confirm.** If it is the staff benefit, nothing changes and we will
note it so nobody flags it again. If those figures are wrong, they are
currently billing staff at a few naira per item.

---

## 3. Hope held two prices for the same service and payer — 47 services

For these, the old system contains **more than one price for the same service
and the same payer**, with nothing to say which is current. In several cases
both were entered on the same day.

**We used the higher price every time.** If we under-charge an HMO, the
shortfall shows up weeks later in reconciliation and is hard to recover. If we
over-charge, it surfaces immediately and is corrected on the spot. Neither is
good; the second is recoverable.

Worst disagreements first.

### ADMISSION CATEGORY D-Severe

*service · 1 payer · range ₦100 to ₦100,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| ROYAN STAFF | ₦100 and ₦100,000 | **₦100,000** | |

### ADMISSION CATEGORY C-Major

*service · 9 payers · range ₦100 to ₦100,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| ROYAN STAFF | ₦100 and ₦250 and ₦50,000 | **₦50,000** | |
| Private | ₦500 and ₦100,000 | **₦100,000** | |
| MONTHLY BILLING PATIENT | ₦500 and ₦100,000 | **₦100,000** | |
| RETAINERSHIP- NAMPAK | ₦500 and ₦100,000 | **₦100,000** | |
| RETAINERSHIP- GOLD VALLEY SCHOOL | ₦500 and ₦100,000 | **₦100,000** | |
| RETAINERSHIP- JOHN HOLTS | ₦500 and ₦100,000 | **₦100,000** | |
| RETAINERSHIP- DELIGHTFUL AFFAIRS LTD | ₦500 and ₦100,000 | **₦100,000** | |
| AKINOLA FAMILY | ₦500 and ₦100,000 | **₦100,000** | |
| SCANCARE STAFF | ₦100 and ₦250 | **₦250** | |

### ADMISSION CATEGORY B-Intermediate stay

*service · 1 payer · range ₦100 to ₦25,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| ROYAN STAFF | ₦100 and ₦25,000 | **₦25,000** | |

### ADMISSION CATEGORY A-Anticipated short stay

*service · 2 payers · range ₦100 to ₦30,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| ROYAN STAFF | ₦100 and ₦15,000 | **₦15,000** | |
| Private | ₦2,000 and ₦30,000 | **₦30,000** | |

### ANTENATAL CONSULTATION -PER PREGNANCY ( INITIAL VISIT)

*service · 10 payers · range ₦800 to ₦55,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| OCEANIC | ₦800 and ₦45,000 | **₦45,000** | |
| MANSARD | ₦1,000 and ₦55,000 | **₦55,000** | |
| HEALTH-PARTNER | ₦1,000 and ₦45,000 | **₦45,000** | |
| PRO-HEALTH | ₦1,000 and ₦45,000 | **₦45,000** | |
| KBL | ₦800 and ₦30,000 | **₦30,000** | |
| ANCHOR | ₦1,000 and ₦35,000 | **₦35,000** | |
| WELLNESS / INVESTCORP HMO | ₦1,500 and ₦45,000 | **₦45,000** | |
| GREENBAY / ASTER HEALTH | ₦1,500 and ₦40,000 | **₦40,000** | |
| MULTISHIELD | ₦1,500 and ₦40,000 | **₦40,000** | |
| IHMS | ₦1,500 and ₦22,000 | **₦22,000** | |

### UROLOGIST CONSULTATION FIRST VISIT

*service · 1 payer · range ₦700 to ₦25,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| PRO-HEALTH | ₦700 and ₦25,000 | **₦25,000** | |

### PAP SMEAR

*service · 37 payers · range ₦1,000 to ₦40,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| GREENBAY / ASTER HEALTH | ₦1,000 and ₦2,000 and ₦20,000 | **₦20,000** | |
| NOVO | ₦1,000 and ₦2,000 and ₦18,000 | **₦18,000** | |
| RODING HEALTH CARE | ₦1,000 and ₦15,000 | **₦15,000** | |
| THEBE | ₦1,000 and ₦15,000 | **₦15,000** | |
| IHMS | ₦1,000 and ₦15,000 | **₦15,000** | |
| IVES | ₦1,500 and ₦20,000 | **₦20,000** | |
| Private | ₦3,000 and ₦40,000 | **₦40,000** | |
| SCANCARE STAFF | ₦1,500 and ₦20,000 | **₦20,000** | |
| ROYAN STAFF | ₦1,500 and ₦20,000 | **₦20,000** | |
| PLACEWARE STAFF | ₦1,500 and ₦20,000 | **₦20,000** | |
| FOUNTAIN HEALTHCARE LTD | ₦1,500 and ₦20,000 | **₦20,000** | |
| HEALTH CARE | ₦1,350 and ₦15,000 | **₦15,000** | |
| CKLINE / DISTINCT HEALTH LIMITED | ₦1,500 and ₦15,000 | **₦15,000** | |
| MEDIPLAN | ₦1,500 and ₦15,000 | **₦15,000** | |
| MH | ₦2,000 and ₦20,000 | **₦20,000** | |
| REDCARE | ₦2,000 and ₦20,000 | **₦20,000** | |
| WELLNESS / INVESTCORP HMO | ₦2,000 and ₦20,000 | **₦20,000** | |
| OCEANIC | ₦2,000 and ₦20,000 | **₦20,000** | |
| HEALTH-PARTNER | ₦2,000 and ₦20,000 | **₦20,000** | |
| FIRST PEAK HEALTHCARE | ₦1,500 and ₦15,000 | **₦15,000** | |
| Hygeia HMO | ₦2,000 and ₦20,000 | **₦20,000** | |
| RELIANCE HMO | ₦2,000 and ₦20,000 | **₦20,000** | |
| MANSARD | ₦2,000 and ₦18,000 | **₦18,000** | |
| LIFECARE | ₦2,000 and ₦18,000 | **₦18,000** | |
| LIBERTY BLUE | ₦1,600 and ₦14,000 | **₦14,000** | |
| GNI. GREAT NIGERIA INSURANCE | ₦2,000 and ₦15,000 | **₦15,000** | |
| SWIFT | ₦2,000 and ₦15,000 | **₦15,000** | |
| MONTHLY BILLING PATIENT | ₦3,000 and ₦20,000 | **₦20,000** | |
| RETAINERSHIP- NAMPAK | ₦3,000 and ₦20,000 | **₦20,000** | |
| RETAINERSHIP- GOLD VALLEY SCHOOL | ₦3,000 and ₦20,000 | **₦20,000** | |
| RETAINERSHIP- JOHN HOLTS | ₦3,000 and ₦20,000 | **₦20,000** | |
| RETAINERSHIP- DELIGHTFUL AFFAIRS LTD | ₦3,000 and ₦20,000 | **₦20,000** | |
| AKINOLA FAMILY | ₦3,000 and ₦20,000 | **₦20,000** | |
| RETAINERSHIP- CHARIOT PROPERTIES LTD | ₦3,000 and ₦20,000 | **₦20,000** | |
| NONSUCH | ₦2,000 and ₦12,750 | **₦12,750** | |
| ANCHOR | ₦3,000 and ₦15,000 | **₦15,000** | |
| PRO-HEALTH | ₦15,000 and ₦20,000 | **₦20,000** | |

### SURGEON CONSULTATION (INITIAL VISIT)

*service · 3 payers · range ₦500 to ₦12,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| GNI. GREAT NIGERIA INSURANCE | ₦500 and ₦10,000 | **₦10,000** | |
| ANCHOR | ₦700 and ₦12,000 | **₦12,000** | |
| KBL | ₦500 and ₦5,000 | **₦5,000** | |

### Room106

*service · 4 payers · range ₦1,000 to ₦18,500*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| Private | ₦1,000 and ₦18,500 | **₦18,500** | |
| MONTHLY BILLING PATIENT | ₦1,000 and ₦14,000 | **₦14,000** | |
| RETAINERSHIP- JOHN HOLTS | ₦1,000 and ₦8,000 | **₦8,000** | |
| NOVO | ₦4,000 and ₦5,500 | **₦5,500** | |

### General Ward

*service · 1 payer · range ₦200 to ₦3,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| Private | ₦200 and ₦3,000 | **₦3,000** | |

### SURGEON FOLLOW UP VISIT

*service · 3 payers · range ₦500 to ₦7,500*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| GNI. GREAT NIGERIA INSURANCE | ₦500 and ₦7,500 | **₦7,500** | |
| ANCHOR | ₦700 and ₦7,500 | **₦7,500** | |
| KBL | ₦500 and ₦2,500 | **₦2,500** | |

### PHYSICIAN CONSULTATION FIRST VISIT

*service · 2 payers · range ₦550 to ₦7,500*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| RODING HEALTH CARE | ₦550 and ₦7,500 | **₦7,500** | |
| THEBE | ₦550 and ₦7,500 | **₦7,500** | |

### BLOOD FILM COMMENT

*lab · 1 payer · range ₦1,000 to ₦9,500*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| Private | ₦1,000 and ₦9,500 | **₦9,500** | |

### GROUPING & CROSSMATCHING ONE PINT OF RHESUS POSITIVE BLOOD

*lab · 1 payer · range ₦17,000 to ₦150,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| Private | ₦17,000 and ₦150,000 | **₦150,000** | |

### C-PEPTIDE

*lab · 1 payer · range ₦15,000 to ₦118,800*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| Private | ₦15,000 and ₦118,800 | **₦118,800** | |

### PAEDIATRICIAN FOLLOW UP VISIT

*service · 3 payers · range ₦800 to ₦7,500*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| OCEANIC | ₦800 and ₦5,000 | **₦5,000** | |
| WELLNESS / INVESTCORP HMO | ₦1,500 and ₦5,000 | **₦5,000** | |
| MANSARD | ₦3,000 and ₦7,500 | **₦7,500** | |

### URINE CULTURE AND SENSITIVITY

*lab · 1 payer · range ₦3,000 to ₦15,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| Private | ₦3,000 and ₦15,000 | **₦15,000** | |

### ELISA HIV TEST

*lab · 1 payer · range ₦5,000 to ₦20,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| Private | ₦5,000 and ₦20,000 | **₦20,000** | |

### GENERAL CONSULTATION

*service · 7 payers · range ₦750 to ₦5,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| Private | ₦1,500 and ₦5,000 | **₦5,000** | |
| MONTHLY BILLING PATIENT | ₦1,500 and ₦5,000 | **₦5,000** | |
| RETAINERSHIP- JOHN HOLTS | ₦1,500 and ₦5,000 | **₦5,000** | |
| SCANCARE STAFF | ₦750 and ₦1,500 | **₦1,500** | |
| ROYAN STAFF | ₦750 and ₦1,500 | **₦1,500** | |
| PLACEWARE STAFF | ₦750 and ₦1,500 | **₦1,500** | |
| testtariff | ₦1,000 and ₦1,500 | **₦1,500** | |

### BLOOD GROUP AND GENOTYPE

*lab · 1 payer · range ₦1,500 to ₦5,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| RETAINERSHIP- NAMPAK | ₦1,500 and ₦5,000 | **₦5,000** | |

### Hb Genotype

*lab · 1 payer · range ₦2,000 to ₦5,500*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| Private | ₦2,000 and ₦5,500 | **₦5,500** | |

### PROLACTIN

*lab · 1 payer · range ₦6,000 to ₦15,500*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| Private | ₦6,000 and ₦15,500 | **₦15,500** | |

### PHYSIOTHERAPIST

*service · 5 payers · range ₦3,000 to ₦7,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| Private | ₦3,000 and ₦7,000 | **₦7,000** | |
| MONTHLY BILLING PATIENT | ₦3,000 and ₦7,000 | **₦7,000** | |
| RETAINERSHIP- NAMPAK | ₦3,000 and ₦7,000 | **₦7,000** | |
| RETAINERSHIP- GOLD VALLEY SCHOOL | ₦3,000 and ₦7,000 | **₦7,000** | |
| RETAINERSHIP- JOHN HOLTS | ₦3,000 and ₦7,000 | **₦7,000** | |

### EYE SWAB M/C/S

*lab · 1 payer · range ₦3,000 to ₦7,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| Private | ₦3,000 and ₦7,000 | **₦7,000** | |

### CATHETER SPECIMEN URINE CSU

*lab · 1 payer · range ₦3,000 to ₦7,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| Private | ₦3,000 and ₦7,000 | **₦7,000** | |

### DCT(Direct coomb`s test)

*lab · 1 payer · range ₦3,500 to ₦8,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| Private | ₦3,500 and ₦8,000 | **₦8,000** | |

### CLOTTING PROFILE (PT/PTTCONTROL/PT/INR)

*lab · 1 payer · range ₦15,000 to ₦32,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| Private | ₦15,000 and ₦32,000 | **₦32,000** | |

### PRIMARY SUTURE

*service · 1 payer · range ₦2,500 to ₦5,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| MEDIPLAN | ₦2,500 and ₦5,000 | **₦5,000** | |

### Sputum M/C/S

*lab · 1 payer · range ₦1,000 to ₦2,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| NOVO | ₦1,000 and ₦2,000 | **₦2,000** | |

### GYNAECOLOGIST CONSULTATION (Initial)

*service · 7 payers · range ₦10,000 to ₦40,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| Private | ₦20,000 and ₦40,000 | **₦40,000** | |
| MONTHLY BILLING PATIENT | ₦20,000 and ₦40,000 | **₦40,000** | |
| RETAINERSHIP- NAMPAK | ₦12,500 and ₦20,000 | **₦20,000** | |
| RETAINERSHIP- GOLD VALLEY SCHOOL | ₦12,500 and ₦20,000 | **₦20,000** | |
| AKINOLA FAMILY | ₦12,500 and ₦20,000 | **₦20,000** | |
| GNI. GREAT NIGERIA INSURANCE | ₦10,000 and ₦13,000 | **₦13,000** | |
| MANSARD | ₦10,000 and ₦13,000 | **₦13,000** | |

### EAR SWAB M/C/S

*lab · 2 payers · range ₦1,000 to ₦2,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| GREENBAY / ASTER HEALTH | ₦1,000 and ₦2,000 | **₦2,000** | |
| NOVO | ₦1,000 and ₦2,000 | **₦2,000** | |

### BLOOD PREGNANCY TEST

*lab · 1 payer · range ₦1,000 to ₦2,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| RETAINERSHIP- NAMPAK | ₦1,000 and ₦2,000 | **₦2,000** | |

### ADENOIDECTOMY

*service · 1 payer · range ₦175,000 to ₦350,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| ROYAN STAFF | ₦175,000 and ₦350,000 | **₦350,000** | |

### AMBULANCE SERVICES (LONG DISTANCE)

*service · 1 payer · range ₦30,000 to ₦60,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| ROYAN STAFF | ₦30,000 and ₦60,000 | **₦60,000** | |

### ANA (ANTI - NUCLEAR ANTIBODY)

*lab · 1 payer · range ₦15,000 to ₦25,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| Private | ₦15,000 and ₦25,000 | **₦25,000** | |

### Room 101

*service · 1 payer · range ₦5,000 to ₦8,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| NOVO | ₦5,000 and ₦8,000 | **₦8,000** | |

### Room105

*service · 1 payer · range ₦5,000 to ₦8,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| NOVO | ₦5,000 and ₦8,000 | **₦8,000** | |

### Room1

*service · 1 payer · range ₦4,000 to ₦5,500*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| NOVO | ₦4,000 and ₦5,500 | **₦5,500** | |

### Room104

*service · 1 payer · range ₦4,000 to ₦5,500*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| NOVO | ₦4,000 and ₦5,500 | **₦5,500** | |

### Room2

*service · 1 payer · range ₦4,000 to ₦5,500*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| NOVO | ₦4,000 and ₦5,500 | **₦5,500** | |

### ALBUMIN

*lab · 1 payer · range ₦1,500 to ₦2,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| RETAINERSHIP- NAMPAK | ₦1,500 and ₦2,000 | **₦2,000** | |

### FBC/MP

*lab · 3 payers · range ₦2,500 to ₦3,200*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| GREENBAY / ASTER HEALTH | ₦2,500 and ₦3,200 | **₦3,200** | |
| NOVO | ₦2,500 and ₦3,200 | **₦3,200** | |
| HEALTH-PARTNER | ₦2,500 and ₦3,000 | **₦3,000** | |

### FBC/MP/ WIDAL

*lab · 1 payer · range ₦3,100 to ₦3,900*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| NOVO | ₦3,100 and ₦3,900 | **₦3,900** | |

### FBC

*lab · 2 payers · range ₦2,000 to ₦2,500*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| GREENBAY / ASTER HEALTH | ₦2,000 and ₦2,500 | **₦2,500** | |
| NOVO | ₦2,000 and ₦2,500 | **₦2,500** | |

### SEMINAL FLUID ANALYSIS (SFA)

*lab · 1 payer · range ₦2,500 to ₦3,000*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| NOVO | ₦2,500 and ₦3,000 | **₦3,000** | |

### General ward R1

*service · 1 payer · range ₦3,000 to ₦3,500*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| NOVO | ₦3,000 and ₦3,500 | **₦3,500** | |

### General ward R2

*service · 1 payer · range ₦3,000 to ₦3,500*

| Payer | Hope holds | We used | Your correction |
|---|---|---|---|
| NOVO | ₦3,000 and ₦3,500 | **₦3,500** | |

---

## 4. Prices that look wrong — 69 services

These are live now. They may be perfectly correct: cancer drugs and major
surgery genuinely do cost this much, and a private room genuinely is many
times a general ward bed. But each one is far enough from its neighbours to
deserve a second look.

Placeholder prices (₦10 and under) are excluded here so the list reflects
genuine disagreement rather than the issue in section 2.

| Service | Type | Payers | Lowest | Highest | Ratio | Your comment |
|---|---|---|---|---|---|---|
| VITAMIN BCO INJ | pharmacy | 71 | ₦49.50 | ₦500,900 | 10119x | |
| ADMISSION CATEGORY D-Severe | ward | 13 | ₦100 | ₦300,000 | 3000x | |
| ADMISSION CATEGORY C-Major | ward | 31 | ₦100 | ₦150,000 | 1500x | |
| ADMISSION CATEGORY B-Intermediate stay | ward | 13 | ₦100 | ₦75,000 | 750x | |
| Implanon 68mg Implant | pharmacy | 41 | ₦25 | ₦15,000 | 600x | |
| AMOX/ CLAV 228MG/5ML SUSP | pharmacy | 75 | ₦12 | ₦6,800 | 567x | |
| DICLOFENAC 50MG TAB | pharmacy | 75 | ₦20 | ₦11,111 | 556x | |
| ADMISSION CATEGORY A-Anticipated short stay | ward | 26 | ₦100 | ₦45,000 | 450x | |
| MUPRIOCIN CREAM | pharmacy | 5 | ₦18 | ₦6,500 | 361x | |
| INSULIN MIXTARD100IU (FLEXPEN) | pharmacy | 47 | ₦50 | ₦16,500 | 330x | |
| CORD CLAMP | pharmacy | 38 | ₦23 | ₦7,500 | 326x | |
| INSULIN LANTUS SOLOSTAR | pharmacy | 45 | ₦125 | ₦38,000 | 304x | |
| GAUZE BANDAGE BIG | pharmacy | 49 | ₦50 | ₦15,000 | 300x | |
| HCG 5000I.U INJ | pharmacy | 47 | ₦50 | ₦15,000 | 300x | |
| JADELLE | pharmacy | 59 | ₦50 | ₦15,000 | 300x | |
| PHENOBARBITONE 30MG TAB | pharmacy | 51 | ₦11 | ₦3,000 | 273x | |
| Vancomycin 1g inj | pharmacy | 26 | ₦125 | ₦24,000 | 192x | |
| LIVOLIN TAB | pharmacy | 37 | ₦90 | ₦15,000 | 167x | |
| GLYCERYLTRINIRATE 0.4MG SPRAY | pharmacy | 45 | ₦50 | ₦8,000 | 160x | |
| ARISTOBET-N EYE/EAR/NASAL DROP | pharmacy | 29 | ₦20 | ₦3,000 | 150x | |
| DULCOLAX 10MG SUPPOSTORIES | pharmacy | 51 | ₦25 | ₦3,500 | 140x | |
| PARACETAMOL 125MG/5ML SYRUP | pharmacy | 79 | ₦50 | ₦7,000 | 140x | |
| RANITIDINE 50MG INJ | pharmacy | 51 | ₦40 | ₦5,500 | 138x | |
| OVARIAN CYSTECTOMY | consultation | 35 | ₦40,000 | ₦5,500,000 | 138x | |
| METOCHLORPROMIDE 10MG INJ | pharmacy | 60 | ₦11 | ₦1,455 | 132x | |
| INSULIN SYRINGE 100I.U | pharmacy | 40 | ₦50 | ₦6,500 | 130x | |
| NITROFURANTOIN 100MG TAB | pharmacy | 79 | ₦12 | ₦1,500 | 125x | |
| VITAMIN C INJ | pharmacy | 70 | ₦22 | ₦2,500 | 114x | |
| SOLUSET | pharmacy | 61 | ₦66.50 | ₦7,500 | 113x | |
| OXYTOCIN INJ 10IU/ML | pharmacy | 57 | ₦80 | ₦9,000 | 113x | |
| ONE TOUCH ULTRA STRIPS | pharmacy | 38 | ₦50 | ₦5,500 | 110x | |
| AMPICLOX 500MG CAP | pharmacy | 65 | ₦11 | ₦1,200 | 109x | |
| WHITE PLASTER | pharmacy | 45 | ₦50 | ₦5,000 | 100x | |
| SCALPVEIN | pharmacy | 27 | ₦50 | ₦5,000 | 100x | |
| URINE BAG | pharmacy | 41 | ₦50 | ₦5,000 | 100x | |
| CATHETHER 18FR | pharmacy | 47 | ₦200 | ₦20,000 | 100x | |
| EXAMINATION GLOVE (LATEX) | pharmacy | 36 | ₦15 | ₦1,500 | 100x | |
| PARACETAMOL 1G INFUS (SUREX) | pharmacy | 73 | ₦250 | ₦25,000 | 100x | |
| PREMATURE/INCUBATOR ADMISSION | ward | 14 | ₦15,000 | ₦1,500,000 | 100x | |
| ONCOLOGY CONSULTATION (INITIAL VISIT) | consultation | 19 | ₦1,000 | ₦100,000 | 100x | |
| CERVICAL POLYPECTOMY | consultation | 32 | ₦3,000 | ₦300,000 | 100x | |
| DICLOFENAC SODIUM 75MG INJ | pharmacy | 71 | ₦50 | ₦4,500 | 90x | |
| CHLOROQUINE  322mg/5ml INJ | pharmacy | 65 | ₦29 | ₦2,500 | 86x | |
| QUININE 600MG/2ML INJ | pharmacy | 28 | ₦12 | ₦1,000 | 83x | |
| TRAMADOL INJ 100MG | pharmacy | 52 | ₦50 | ₦4,000 | 80x | |
| ZOLADEX 10.8MG INJ | pharmacy | 17 | ₦2,000 | ₦150,150 | 75x | |
| ANTENATAL CONSULTATION -PER PREGNANCY ( INITIAL VISIT) | consultation | 48 | ₦1,000 | ₦75,000 | 75x | |
| UROLOGIST CONSULTATION FIRST VISIT | consultation | 38 | ₦700 | ₦52,500 | 75x | |
| ERYTHROMYCIN 125MG/5ML SUSP | pharmacy | 66 | ₦50 | ₦3,500 | 70x | |
| VITAMIN K3 25MG/2ML INJ | pharmacy | 58 | ₦47.50 | ₦3,300 | 69x | |
| ELBOW GLOVE | pharmacy | 48 | ₦37 | ₦2,500 | 68x | |
| ORAL CONTRACEPTIVES | pharmacy | 59 | ₦15 | ₦1,000 | 67x | |
| AMPICILLIN CAP 250MG | pharmacy | 48 | ₦13.50 | ₦900 | 67x | |
| GENTIMICIN CREAM | pharmacy | 52 | ₦28.50 | ₦1,800 | 63x | |
| RANFERON TONIC | pharmacy | 52 | ₦47.50 | ₦3,000 | 63x | |
| LACTULOSE SOLUTION 10G/15ML | pharmacy | 25 | ₦125 | ₦7,800 | 62x | |
| YEAST TAB | pharmacy | 49 | ₦11.25 | ₦700 | 62x | |
| ADRENALIN 1MG/ML INJ | pharmacy | 50 | ₦50 | ₦3,050 | 61x | |
| COPPER T (IUCD) | pharmacy | 43 | ₦250 | ₦15,000 | 60x | |
| PROMETHAZINE INJ 50MG/2ML | pharmacy | 79 | ₦50 | ₦3,000 | 60x | |
| SURGEON CONSULTATION (INITIAL VISIT) | consultation | 43 | ₦500 | ₦30,000 | 60x | |
| FANSIDAR SUSP 525MG/5ML | pharmacy | 57 | ₦50 | ₦3,000 | 60x | |
| PIRITON SYRUP 2MG/5ML | pharmacy | 74 | ₦50 | ₦3,000 | 60x | |
| LEVAMISOLE TAB  (KETRAX) 47.2MG | pharmacy | 29 | ₦43 | ₦2,500 | 58x | |
| AMPICLOX SUSP 250MG/5ML | pharmacy | 63 | ₦50 | ₦2,800 | 56x | |
| METOCLOPRAMIDE 10MG TAB | pharmacy | 51 | ₦18 | ₦1,001 | 56x | |
| CLOTRIMAXOLE CREAM | pharmacy | 71 | ₦50 | ₦2,750 | 55x | |
| AMINOPHYLLINE INJ 250MG | pharmacy | 53 | ₦66 | ₦3,500 | 53x | |
| PAP SMEAR | lab | 61 | ₦1,000 | ₦52,500 | 53x | |

---

## For information only — no decision needed

### Two items we refused to price

Both had a single price in Hope that we judged to be a typing error, with no
second value to fall back on. **They are unpriced in the system.** Whoever
bills them will be prompted to enter a price. If you tell us the right figures
we will load them.

| Item | Price in Hope | Why we refused |
|---|---|---|
| GLOVE STERILE 7.5 | ₦10,001,000 | ₦10m for one glove |
| LEVAMISOLE TAB (KETRAX) 47.2MG | ₦0.20 | Below any plausible price |

### One drug where we caught an error automatically

Worth knowing the safeguard works. RANFERON CAP carried five prices in Hope:

| Price | Batch | Expiry |
|---|---|---|
| ₦714,286,000,000 | med-262 | expired 2017 |
| ₦125 | A14 | 2026 |
| ₦95 | 333 | 2024 |
| ₦38 | IVES-261 | expired 2017 |
| ₦30 | dist-260 | expired 2017 |

Taking the highest would have priced an iron supplement at ₦714 billion.
Taking the **current batch** gives ₦125. That is the rule we use for all drug
pricing.

### Prices we could not attach to anything

2,810 price rows in Hope (12%) point at services that no longer exist in any
of its catalogues. We have ignored them rather than guess where they belong.
Nothing is lost — the services themselves are priced by other means.

---

## Where things stand

| | Before migration | Now |
|---|---|---|
| Services with a price | 316 of 1,221 (26%) | **1,119 of 1,221 (92%)** |
| Lab tests with a price | 20 of 288 | **281 of 288** |
| Imaging with a price | none | **209 of 211** |
| Payer-specific prices | 28,750 | **49,330** across 109 payers |
| Patients with insurance on file | 0 | **18,124** |

The items in this document are the remaining 8% — the cases where the old
system was ambiguous and someone has to decide.
