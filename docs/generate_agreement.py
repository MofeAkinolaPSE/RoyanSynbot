"""
Generates ROY-Software-Implementation-Agreement.docx
Run: python docs/generate_agreement.py
"""
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import copy

doc = Document()

# ── Page margins ──────────────────────────────────────────────────────────────
for section in doc.sections:
    section.top_margin    = Inches(1.0)
    section.bottom_margin = Inches(1.0)
    section.left_margin   = Inches(1.25)
    section.right_margin  = Inches(1.25)

# ── Styles helpers ────────────────────────────────────────────────────────────
NORMAL = doc.styles["Normal"]
NORMAL.font.name = "Times New Roman"
NORMAL.font.size = Pt(11)

def set_font(run, bold=False, italic=False, size=11, color=None):
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.bold  = bold
    run.italic = italic
    if color:
        run.font.color.rgb = RGBColor(*color)

def heading(text, level=1, center=False):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14 if level == 1 else 8)
    p.paragraph_format.space_after  = Pt(4)
    if center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    set_font(run, bold=True, size=13 if level == 1 else 11)
    return p

def body(text="", space_before=4, space_after=4, indent=0, bold_parts=None):
    """Add a paragraph; bold_parts is list of substrings to bold."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after  = Pt(space_after)
    p.paragraph_format.left_indent  = Inches(indent)
    if not bold_parts:
        run = p.add_run(text)
        set_font(run)
    else:
        # Interleave bold and normal runs
        remaining = text
        for bp in bold_parts:
            idx = remaining.find(bp)
            if idx == -1:
                continue
            if idx > 0:
                r = p.add_run(remaining[:idx])
                set_font(r)
            r = p.add_run(bp)
            set_font(r, bold=True)
            remaining = remaining[idx + len(bp):]
        if remaining:
            r = p.add_run(remaining)
            set_font(r)
    return p

def divider():
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after  = Pt(2)
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "auto")
    pBdr.append(bottom)
    pPr.append(pBdr)

def add_table(headers, rows, col_widths=None):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    # Header row
    hdr = table.rows[0]
    for i, h in enumerate(headers):
        cell = hdr.cells[i]
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p = cell.paragraphs[0]
        run = p.add_run(h)
        set_font(run, bold=True, size=10)
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after  = Pt(3)
        # shade header
        tc_pr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), "E8E8E8")
        tc_pr.append(shd)
    # Data rows
    for ri, row_data in enumerate(rows):
        row = table.rows[ri + 1]
        for ci, val in enumerate(row_data):
            cell = row.cells[ci]
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            p = cell.paragraphs[0]
            # Check if value should be bold (starts with **)
            if val.startswith("**") and val.endswith("**"):
                run = p.add_run(val[2:-2])
                set_font(run, bold=True, size=10)
            else:
                run = p.add_run(val)
                set_font(run, size=10)
            p.paragraph_format.space_before = Pt(3)
            p.paragraph_format.space_after  = Pt(3)
    # Column widths
    if col_widths:
        for i, w in enumerate(col_widths):
            for row in table.rows:
                row.cells[i].width = Inches(w)
    return table

def sig_block(party_label):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    r = p.add_run(f"SIGNED for and on behalf of {party_label}")
    set_font(r, bold=True)
    for label in ["Signature:", "Name:", "Designation:", "Date:"]:
        p2 = doc.add_paragraph()
        p2.paragraph_format.space_before = Pt(10)
        r1 = p2.add_run(f"{label}  ")
        set_font(r1, bold=True)
        r2 = p2.add_run("_" * 45)
        set_font(r2)

def clause_para(num, text, bold_parts=None):
    p = body(f"{num}  {text}", space_before=5, space_after=5, bold_parts=bold_parts)
    return p

def sub_para(letter, text, bold_parts=None):
    p = body(f"({letter})  {text}", space_before=4, space_after=4, indent=0.25, bold_parts=bold_parts)
    return p

def bullet(text, bold_parts=None):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after  = Pt(3)
    p.paragraph_format.left_indent  = Inches(0.3)
    if not bold_parts:
        run = p.add_run(text)
        set_font(run, size=10)
    else:
        remaining = text
        for bp in bold_parts:
            idx = remaining.find(bp)
            if idx == -1:
                continue
            if idx > 0:
                r = p.add_run(remaining[:idx])
                set_font(r, size=10)
            r = p.add_run(bp)
            set_font(r, bold=True, size=10)
            remaining = remaining[idx + len(bp):]
        if remaining:
            r = p.add_run(remaining)
            set_font(r, size=10)
    return p

# ════════════════════════════════════════════════════════════════════════════
# TITLE BLOCK
# ════════════════════════════════════════════════════════════════════════════
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(4)
r = p.add_run("SOFTWARE IMPLEMENTATION AGREEMENT")
set_font(r, bold=True, size=16)

p2 = doc.add_paragraph()
p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
p2.paragraph_format.space_after = Pt(12)
r2 = p2.add_run("Contract Reference: NL-ROY-2026-001")
set_font(r2, bold=True, size=12)

divider()

# ── Parties ───────────────────────────────────────────────────────────────────
p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(12)
r = p.add_run("THIS AGREEMENT is made this [  ] day of [  ] 2026.")
set_font(r)

body("BETWEEN", space_before=10, space_after=2, bold_parts=["BETWEEN"])

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(6)
r1 = p.add_run("NEUROLAYER")
set_font(r1, bold=True)
r2 = p.add_run(' (hereinafter referred to as the "')
set_font(r2)
r3 = p.add_run("Service Provider")
set_font(r3, bold=True)
r4 = p.add_run('"), a technology company specialising in AI-powered software systems and enterprise automation solutions, of 64 Aina Street, Ojodu, Lagos, Nigeria.')
set_font(r4)

body("AND", space_before=8, space_after=2, bold_parts=["AND"])

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(6)
r1 = p.add_run("ROYAN HOSPITAL")
set_font(r1, bold=True)
r2 = p.add_run(' (hereinafter referred to as the "')
set_font(r2)
r3 = p.add_run("Client")
set_font(r3, bold=True)
r4 = p.add_run('"), a healthcare institution duly registered under the laws of the Federal Republic of Nigeria, of [Hospital Registered Address], Lagos, Nigeria.')
set_font(r4)

body(
    'The Service Provider and the Client shall jointly be referred to as the "Parties" and individually as a "Party."',
    space_before=10
)

divider()

# ── Recital ───────────────────────────────────────────────────────────────────
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(10)
r = p.add_run("NOW IT IS HEREBY AGREED AS FOLLOWS:")
set_font(r, bold=True)

divider()

# ════════════════════════════════════════════════════════════════════════════
# CLAUSE 1 — SCOPE OF SERVICES
# ════════════════════════════════════════════════════════════════════════════
heading("1.   SCOPE OF SERVICES")

clause_para("1.1", 'The Service Provider shall design, develop, configure, and deploy '
    'RoyanHealth — a proprietary, modular, AI-powered Hospital Management System (HMS) '
    'purpose-built for the Client — incorporating clinical, operational, and administrative '
    'capabilities across the full care continuum. The Platform shall be deployed entirely on '
    'the Client\'s on-premise server infrastructure in accordance with Schedule A of this '
    'Agreement. No recurring cloud hosting fees shall apply under this Agreement.',
    bold_parts=["RoyanHealth"])

clause_para("1.2", "The implementation shall encompass:")

sub_para("a", "Core Clinical Modules: Patient registration with automated Medical Record Number (MRN) "
    "generation, clinical queue management, outpatient and appointment scheduling, inpatient/ward "
    "management (Admission, Discharge, Transfer — ADT), emergency/A&E workflow, encounter documentation "
    "(SOAP format), ICD-10 diagnosis coding, and patient problem list management.",
    bold_parts=["Core Clinical Modules:"])

sub_para("b", "Diagnostic Modules: Laboratory Information Management System (LIMS) including order "
    "management, sample tracking, result entry, reference ranges, cumulative history, LOINC coding, "
    "critical result alerting, and lab turnaround time (TAT) monitoring; Radiology and Imaging Module "
    "including electronic imaging requests, report entry, DICOM/PACS integration stub, ECG and "
    "echocardiography report storage, and imaging TAT monitoring.",
    bold_parts=["Diagnostic Modules:"])

sub_para("c", "Pharmaceutical Module: Electronic prescription reception, drug inventory and stock "
    "management, drug-drug interaction (DDI) checking, allergy and contraindication checking, "
    "dispensing confirmation, outpatient and inpatient prescription tracking, automatic ward stock "
    "replenishment, drug return and wastage logging, and pharmacy revenue reporting.",
    bold_parts=["Pharmaceutical Module:"])

sub_para("d", "Nursing and Clinical Support: Digital vitals recording, nursing care plans, medication "
    "administration record (MAR), IV fluid and intake/output charting, pain score assessment, wound "
    "care documentation, and nursing shift handover reports.",
    bold_parts=["Nursing and Clinical Support:"])

sub_para("e", "Surgical Theatre Module: Theatre scheduling (elective and emergency), pre-operative "
    "assessment checklist, anaesthetic record, operative notes, post-operative recovery room "
    "monitoring, and surgical consent management.",
    bold_parts=["Surgical Theatre Module:"])

sub_para("f", "Maternal and Child Health (MCH) Module: Antenatal care (ANC) booking and visit "
    "tracking, growth chart and fundal height monitoring, partograph (labour progress), delivery "
    "record, newborn assessment, child immunisation schedule, gynaecology consultation notes, and "
    "family planning counselling records.",
    bold_parts=["Maternal and Child Health (MCH) Module:"])

sub_para("g", "Specialist Clinic Templates (14 specialties): Cardiology, Gastroenterology, Urology, "
    "Family Medicine/General Practice, Orthopaedics, Paediatrics, Chronic Disease (Diabetes, "
    "Hypertension), Physiotherapy and Rehabilitation, Ophthalmology, ENT, Dermatology, Oncology, "
    "Neurology, and Psychiatry/Mental Health.",
    bold_parts=["Specialist Clinic Templates (14 specialties):"])

sub_para("h", "Billing, Finance, and HMO Management: Automatic bill generation from clinical orders, "
    "itemised invoicing and discharge billing, HMO pre-authorisation requests, HMO claim submission "
    "and tracking, co-payment calculation, multiple payment methods (cash, POS, bank transfer), "
    "inpatient running bill with live balance, outstanding debt and credit management, fee schedule "
    "management, waiver and discount authorisation workflow, and indigent patient support tracking.",
    bold_parts=["Billing, Finance, and HMO Management:"])

sub_para("i", "Data Assimilation and Legacy Migration: A purpose-built Data Assimilation Layer (DAL) "
    "to extract, transform, and load the Client's existing historical data from DRM Hope (MySQL) into "
    "the RoyanHealth database. This includes all nine (9) active DRM Hope modules: Patient "
    "Registration, Outpatient/Appointment Scheduling, Inpatient/Ward Management, Pharmacy/Dispensing, "
    "Laboratory/LIMS, Radiology/Imaging Orders, Billing and Finance, HMO/Insurance Management, and "
    "Theatre/Surgical Management.",
    bold_parts=["Data Assimilation and Legacy Migration:"])

sub_para("j", "AI Clinical Assistant: An AI-powered clinical assistant (AskSynbot) supporting "
    "role-based interaction for clinical staff, including clinical decision support, end-of-shift "
    "briefings, and executive operations summaries.",
    bold_parts=["AI Clinical Assistant:"])

sub_para("k", "Digital Patient Engagement: Patient-facing Progressive Web App (PWA) portal for "
    "appointment booking, result viewing, and prescription history; SMS and WhatsApp appointment "
    "reminders; digital queue number delivery to patient devices; and QR kiosk self-check-in capability.",
    bold_parts=["Digital Patient Engagement:"])

sub_para("l", "Quality, Safety, and Compliance Tools: Incident reporting and root cause analysis "
    "(RCA), infection control surveillance, HEFAMAA regulatory inspection readiness checklist, and "
    "NHIA/HMIS regulatory report export.",
    bold_parts=["Quality, Safety, and Compliance Tools:"])

sub_para("m", "HR and Administration: Staff roster and duty scheduling, leave management, on-call "
    "scheduling, staff attendance tracking, and payroll data export.",
    bold_parts=["HR and Administration:"])

sub_para("n", "Reporting and Analytics: Real-time hospital operations dashboard, daily OPD/A&E "
    "attendance reports, inpatient census and bed occupancy, revenue reports (daily/monthly by "
    "department), HMO claims ageing report, pharmacy stock and consumption forecasting, laboratory "
    "TAT report, surgical throughput report, top diagnoses and disease burden report (ICD-10), and "
    "staff productivity report.",
    bold_parts=["Reporting and Analytics:"])

sub_para("o", "Hope Bridge Integration (Phase 2): Following initial deployment, a lightweight "
    "synchronisation bridge service (Hope Bridge) shall be configured to enable ongoing incremental "
    "data synchronisation from DRM Hope to RoyanHealth for new encounters, should the Client elect "
    "to continue operating DRM Hope concurrently.",
    bold_parts=["Hope Bridge Integration (Phase 2):"])

clause_para("1.3", "The full deliverable schedule is set out in Schedule A to this Agreement.",
    bold_parts=["Schedule A"])

divider()

# ════════════════════════════════════════════════════════════════════════════
# CLAUSE 2 — FEES AND PAYMENT
# ════════════════════════════════════════════════════════════════════════════
heading("2.   FEES AND PAYMENT")

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(5)
p.paragraph_format.space_after  = Pt(8)
r1 = p.add_run("2.1  The total implementation fee is ")
set_font(r1)
r2 = p.add_run("THREE MILLION, FIVE HUNDRED THOUSAND NAIRA (₦3,500,000)")
set_font(r2, bold=True)
r3 = p.add_run(", payable in three (3) tranches as follows:")
set_font(r3)

add_table(
    ["Tranche", "Amount", "Trigger"],
    [
        ["**Mobilisation Fee**",  "₦1,200,000", "Due upon execution of this Agreement"],
        ["**Milestone Fee**",     "₦1,300,000", "Due upon successful completion of the Data Assimilation phase and Client sign-off on UAT"],
        ["**Go-Live Fee**",       "₦1,000,000", "Due upon successful Go-Live and Client formal sign-off"],
    ],
    col_widths=[1.6, 1.4, 4.0]
)

body("The total fee is allocated across the implementation phases as follows for reference purposes:",
    space_before=10, space_after=6)

add_table(
    ["Phase", "Allocation"],
    [
        ["Development & Configuration (20+ modules, AI engine)", "₦1,500,000"],
        ["Data Assimilation & Legacy Migration",                  "₦500,000"],
        ["Deployment & Infrastructure Setup",                     "₦500,000"],
        ["UAT & Staff Training",                                  "₦500,000"],
        ["Post-Go-Live Support (2 months)",                       "₦500,000"],
        ["**Total**",                                             "**₦3,500,000**"],
    ],
    col_widths=[4.5, 1.5]
)

doc.add_paragraph()
clause_para("2.2", "The Mobilisation Fee authorises the Service Provider to commence all development, "
    "configuration, and data assimilation activities. It must be received within five (5) business "
    "days of contract execution. The Service Provider reserves the right to defer commencement until "
    "payment is confirmed.")

clause_para("2.3", "The Milestone Fee shall become due within seven (7) business days of the Service "
    "Provider issuing a milestone completion notice, to which the Client shall respond with written "
    "acceptance or a documented list of outstanding items within five (5) business days.")

clause_para("2.4", "The Go-Live Fee shall be settled within seven (7) business days of the Client's "
    "formal Go-Live sign-off.")

clause_para("2.5", "The Mobilisation Fee is non-refundable once development has commenced, except in "
    "the event of material breach by the Service Provider. All other tranches are due only upon "
    "successful achievement of the corresponding milestone.")

clause_para("2.6", "Overdue amounts shall attract interest at five percent (5%) per annum, calculated "
    "from the due date to the date of actual payment.")

clause_para("2.7", "All fees are quoted exclusive of any applicable taxes. If any withholding tax or "
    "statutory deduction is required by law, the Client shall gross up the payment such that the "
    "Service Provider receives the full stated amount net of such deduction.")

divider()

# ════════════════════════════════════════════════════════════════════════════
# CLAUSE 3 — PROJECT TIMELINE
# ════════════════════════════════════════════════════════════════════════════
heading("3.   PROJECT TIMELINE")

clause_para("3.1", "The Service Provider shall deliver the complete platform within eight (8) weeks "
    "of receipt of the Mobilisation Fee, subject to timely cooperation, data access, and "
    "infrastructure readiness from the Client.", bold_parts=["eight (8) weeks"])

clause_para("3.2", "The implementation shall be structured in the following phases:")

add_table(
    ["Phase", "Deliverable", "Target"],
    [
        ["Phase 1", "Foundation — core registration, queue, billing, HMO",        "Week 1–2"],
        ["Phase 2", "Data Assimilation — DAL extract, transform, load from DRM Hope", "Week 2–3"],
        ["Phase 3", "Clinical Modules I — Lab, Pharmacy, Nursing",                "Week 3–4"],
        ["Phase 4", "Clinical Modules II — Radiology, Theatre, MCH",              "Week 4–5"],
        ["Phase 5", "Specialist Clinic Templates (14 specialties)",               "Week 5–6"],
        ["Phase 6", "Digital Engagement — PWA Portal, SMS/WhatsApp, QR Kiosk",   "Week 6–7"],
        ["Phase 7", "Quality, HR, Reporting & Compliance Tools",                  "Week 7"],
        ["Phase 8", "UAT, Staff Training, Go-Live",                               "Week 8"],
    ],
    col_widths=[0.8, 4.7, 1.0]
)

doc.add_paragraph()
clause_para("3.3", "Any material scope change requested by the Client after execution of this "
    "Agreement shall be documented in a written change order signed by both Parties, and may "
    "result in a revised timeline and additional fees.")

clause_para("3.4", "Timely access by the Client to its DRM Hope server, database credentials, and "
    "IT infrastructure is a prerequisite for the Data Assimilation phase. Any delay caused by the "
    "Client's failure to provide such access shall extend the delivery timeline accordingly, with "
    "no penalty to the Service Provider.")

divider()

# ════════════════════════════════════════════════════════════════════════════
# CLAUSE 4 — INTELLECTUAL PROPERTY
# ════════════════════════════════════════════════════════════════════════════
heading("4.   INTELLECTUAL PROPERTY")

clause_para("4.1", "The RoyanHealth platform, including all underlying software architecture, AI "
    "models, algorithms, source code, database schema, and proprietary methods, remains the "
    "exclusive intellectual property of the Service Provider.")

clause_para("4.2", "Upon full payment of the total implementation fee, the Client is granted a "
    "perpetual, non-exclusive, non-transferable licence to use the Platform solely for its own "
    "internal clinical and administrative operations at its premises in Nigeria. This licence does "
    "not extend to any affiliate, subsidiary, or partner institution unless expressly agreed in "
    "writing.", bold_parts=["perpetual, non-exclusive, non-transferable licence"])

clause_para("4.3", "All patient data, clinical records, financial records, and other data generated "
    "by the Client through use of the Platform remain the exclusive property of the Client at all "
    "times. The Service Provider shall have no claim over such data and shall access it solely to "
    "the extent necessary to perform its obligations under this Agreement.",
    bold_parts=["exclusive property of the Client"])

clause_para("4.4", "The Client may not sublicense, resell, reverse-engineer, decompile, disassemble, "
    "or redistribute the Platform or any component thereof. The Client may not represent the "
    "Platform as its own proprietary system.")

clause_para("4.5", "Any customisations or enhancements developed by the Service Provider specifically "
    "for the Client under this Agreement shall be owned by the Service Provider, and the Client "
    "shall receive a licence to use such customisations on the same terms as the Platform licence "
    "in clause 4.2.")

divider()

# ════════════════════════════════════════════════════════════════════════════
# CLAUSE 5 — CONFIDENTIALITY AND DATA PROTECTION
# ════════════════════════════════════════════════════════════════════════════
heading("5.   CONFIDENTIALITY AND DATA PROTECTION")

clause_para("5.1", "Each Party shall hold all Confidential Information of the other Party in strict "
    "confidence and shall not disclose it to any third party without the prior written consent of "
    "the disclosing Party. This obligation survives the termination or expiry of this Agreement for "
    "a period of five (5) years.", bold_parts=["five (5) years"])

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(5)
r1 = p.add_run("5.2  ")
set_font(r1)
r2 = p.add_run('"Confidential Information"')
set_font(r2, bold=True)
r3 = p.add_run(" includes, without limitation: patient records and clinical data, proprietary "
    "software architecture, system source code, business strategies, financial information, AI "
    "models, and any information designated as confidential by the disclosing Party.")
set_font(r3)

clause_para("5.3", "Both Parties shall comply with the Nigeria Data Protection Act (NDPA) 2023 and "
    "all applicable regulations of the Nigeria Data Protection Commission (NDPC) in the performance "
    "of this Agreement. The Client, as the data controller of patient data, shall ensure that "
    "patients are duly informed of how their data is processed in accordance with the Platform.",
    bold_parts=["Nigeria Data Protection Act (NDPA) 2023"])

clause_para("5.4", "The Service Provider shall implement and maintain appropriate technical and "
    "organisational security measures to protect patient data processed during the implementation, "
    "including access controls, encrypted data transmission, and audit logging. Such measures shall "
    "meet the minimum standards required under the NDPA 2023.")

clause_para("5.5", "In the event of a data breach affecting patient data, the Service Provider shall "
    "notify the Client in writing within 72 hours of becoming aware of such breach, providing a "
    "description of the breach, the categories of data affected, and the remediation steps being "
    "taken.", bold_parts=["72 hours"])

clause_para("5.6", "Upon termination of this Agreement, the Service Provider shall, at the Client's "
    "written request, return or permanently delete all copies of the Client's data held by the "
    "Service Provider, except to the extent required for legal compliance.")

divider()

# ════════════════════════════════════════════════════════════════════════════
# CLAUSE 6 — WARRANTIES
# ════════════════════════════════════════════════════════════════════════════
heading("6.   WARRANTIES")

clause_para("6.1", "The Service Provider warrants that all services shall be performed diligently, "
    "professionally, and in accordance with industry standards for clinical health information "
    "systems.")

clause_para("6.2", "A ninety (90) day post-Go-Live warranty period shall apply, during which the "
    "Service Provider shall remedy, at no additional cost, any confirmed defects in the Platform "
    "that arise from errors in the Service Provider's development or configuration work.",
    bold_parts=["ninety (90) day"])

clause_para("6.3", "The warranty shall not apply to defects arising from:")
sub_para("a", "misuse, negligence, or unauthorised modifications to the Platform by the Client or its staff;")
sub_para("b", "failure of third-party software, hardware, or infrastructure not supplied by the Service Provider;")
sub_para("c", "data quality issues in the Client's legacy DRM Hope data that were not identified during the Data Assimilation phase;")
sub_para("d", "changes to the Client's operating environment made after Go-Live without the Service Provider's involvement.")

clause_para("6.4", "The Service Provider warrants that the Data Assimilation Layer shall transfer all "
    "extractable patient, clinical, and financial records from the Client's DRM Hope system into the "
    "RoyanHealth database with referential integrity intact, subject to the quality and completeness "
    "of data available in the Client's source system.")

clause_para("6.5", "The Service Provider does not warrant uninterrupted or error-free operation of "
    "the Platform, but shall use commercially reasonable efforts to maintain system availability "
    "during the support period.")

divider()

# ════════════════════════════════════════════════════════════════════════════
# CLAUSE 7 — LIMITATION OF LIABILITY
# ════════════════════════════════════════════════════════════════════════════
heading("7.   LIMITATION OF LIABILITY")

clause_para("7.1", "The Service Provider's total aggregate liability under this Agreement, whether "
    "in contract, tort, or otherwise, shall not exceed the total implementation fees actually paid "
    "by the Client at the time the claim arises.",
    bold_parts=["total implementation fees actually paid by the Client"])

clause_para("7.2", "Neither Party shall be liable for any indirect, consequential, incidental, or "
    "special damages, including but not limited to loss of revenue, loss of data, loss of clinical "
    "opportunity, or reputational harm, arising out of or in connection with this Agreement, even "
    "if advised of the possibility of such damages.")

clause_para("7.3", "Nothing in this Agreement shall limit or exclude liability for death or personal "
    "injury caused by negligence, fraud, or any liability that cannot lawfully be excluded.")

clause_para("7.4", "The Service Provider shall bear no liability for clinical decisions made by the "
    "Client's medical staff on the basis of information displayed by the Platform. The Platform is "
    "a management and administrative tool; clinical judgment remains the sole responsibility of "
    "licensed healthcare professionals.")

divider()

# ════════════════════════════════════════════════════════════════════════════
# CLAUSE 8 — SUPPORT AND MAINTENANCE
# ════════════════════════════════════════════════════════════════════════════
heading("8.   SUPPORT AND MAINTENANCE")

clause_para("8.1", "The Service Provider shall provide two (2) months of post-Go-Live support as "
    "part of the total implementation fee. This support period shall include:",
    bold_parts=["two (2) months"])

sub_para("a", "bug fixes for confirmed defects within the warranty scope of clause 6.2;")
sub_para("b", "performance fine-tuning and configuration adjustments;")
sub_para("c", "response to technical queries from the Client's IT administrator within one (1) business day;",
    bold_parts=["one (1) business day"])
sub_para("d", "assistance with any data reconciliation issues arising from the Data Assimilation phase.")

clause_para("8.2", "Following the expiry of the included support period, the Parties may negotiate a "
    "separate ongoing Maintenance and Support Agreement at terms to be agreed in writing.")

divider()

# ════════════════════════════════════════════════════════════════════════════
# CLAUSE 9 — TERMINATION
# ════════════════════════════════════════════════════════════════════════════
heading("9.   TERMINATION")

clause_para("9.1", "Either Party may terminate this Agreement by fourteen (14) days' written notice "
    "upon material breach by the other Party that remains unremedied within that notice period.",
    bold_parts=["fourteen (14) days"])

clause_para("9.2", "If the Client terminates this Agreement after development has commenced, the "
    "Mobilisation Fee shall remain non-refundable. Any Milestone Fee already paid shall be "
    "non-refundable in respect of work already delivered and accepted. The Go-Live Fee shall not "
    "become payable.")

clause_para("9.3", "If the Service Provider terminates this Agreement without cause or due to its "
    "own material breach, all fees paid shall be refunded to the Client in full within fourteen "
    "(14) days.", bold_parts=["fourteen (14) days"])

clause_para("9.4", "Termination shall not affect any rights or obligations accrued prior to the "
    "date of termination.")

divider()

# ════════════════════════════════════════════════════════════════════════════
# CLAUSE 10 — GOVERNING LAW AND DISPUTE RESOLUTION
# ════════════════════════════════════════════════════════════════════════════
heading("10.   GOVERNING LAW AND DISPUTE RESOLUTION")

clause_para("10.1", "This Agreement is governed by and construed in accordance with the laws of the "
    "Federal Republic of Nigeria.", bold_parts=["laws of the Federal Republic of Nigeria"])

clause_para("10.2", "Any dispute arising out of or in connection with this Agreement shall first be "
    "subject to good-faith negotiation between the Parties. A Party wishing to invoke this provision "
    "shall give written notice of the dispute, and the Parties shall meet (in person or virtually) "
    "within ten (10) business days to seek resolution.", bold_parts=["ten (10) business days"])

clause_para("10.3", "If the dispute remains unresolved after twenty-one (21) days of the written "
    "notice under clause 10.2, the matter shall be referred to binding arbitration in Lagos, "
    "Nigeria, under the Arbitration and Mediation Act 2023, before a single arbitrator appointed "
    "by the Chartered Institute of Arbitrators (Nigeria Branch). The language of arbitration shall "
    "be English.",
    bold_parts=["binding arbitration", "Arbitration and Mediation Act 2023"])

clause_para("10.4", "Nothing in this clause shall prevent either Party from seeking urgent "
    "injunctive or other equitable relief from a court of competent jurisdiction.")

divider()

# ════════════════════════════════════════════════════════════════════════════
# CLAUSE 11 — GENERAL
# ════════════════════════════════════════════════════════════════════════════
heading("11.   GENERAL")

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(5)
r1 = p.add_run("11.1  Entire Agreement.  ")
set_font(r1, bold=True)
r2 = p.add_run("This Agreement, together with Schedule A and Schedule B, constitutes the entire "
    "agreement between the Parties with respect to its subject matter and supersedes all prior "
    "negotiations, representations, proposals, and agreements, whether written or oral.")
set_font(r2)

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(5)
r1 = p.add_run("11.2  Amendment.  ")
set_font(r1, bold=True)
r2 = p.add_run("No amendment to this Agreement shall be valid unless made in writing and signed by "
    "authorised representatives of both Parties.")
set_font(r2)

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(5)
r1 = p.add_run("11.3  Assignment.  ")
set_font(r1, bold=True)
r2 = p.add_run("Neither Party may assign its rights or obligations under this Agreement without "
    "the prior written consent of the other Party, except that the Service Provider may assign its "
    "rights to a successor entity or affiliate upon written notice to the Client.")
set_font(r2)

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(5)
r1 = p.add_run("11.4  Notices.  ")
set_font(r1, bold=True)
r2 = p.add_run("Any notice under this Agreement shall be in writing and delivered by email (with "
    "read receipt) or courier to the addresses set out in this Agreement. Notices shall be deemed "
    "received on the day of delivery if by courier, or on the next business day if by email "
    "(provided no delivery failure notification is received).")
set_font(r2)

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(5)
r1 = p.add_run("11.5  Relationship.  ")
set_font(r1, bold=True)
r2 = p.add_run("Nothing in this Agreement creates a partnership, joint venture, agency, or "
    "employment relationship between the Parties. The Service Provider is an independent contractor.")
set_font(r2)

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(5)
r1 = p.add_run("11.6  Waiver.  ")
set_font(r1, bold=True)
r2 = p.add_run("No failure or delay by either Party in exercising any right under this Agreement "
    "shall constitute a waiver of that right.")
set_font(r2)

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(5)
r1 = p.add_run("11.7  Severability.  ")
set_font(r1, bold=True)
r2 = p.add_run("If any provision of this Agreement is held invalid, illegal, or unenforceable by "
    "a court or arbitrator of competent jurisdiction, the remaining provisions shall continue in "
    "full force and effect.")
set_font(r2)

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(5)
r1 = p.add_run("11.8  Force Majeure.  ")
set_font(r1, bold=True)
r2 = p.add_run("Neither Party shall be liable for any delay or failure to perform its obligations "
    "under this Agreement to the extent caused by circumstances beyond its reasonable control, "
    "including acts of God, government actions, power outages, or telecommunications failures, "
    "provided that the affected Party gives prompt written notice and uses reasonable efforts to "
    "resume performance.")
set_font(r2)

divider()

# ════════════════════════════════════════════════════════════════════════════
# CLAUSE 12 — MANAGED SERVICES RETAINER
# ════════════════════════════════════════════════════════════════════════════
heading("12.   MANAGED SERVICES RETAINER")

clause_para("12.1", "Upon expiry of the two (2) month post-Go-Live support period described in "
    "clause 8.1, the Client may engage the Service Provider on an ongoing Managed Services "
    "Retainer as set out in Schedule B to this Agreement. The scope, fees, support SLAs, AI/LLM "
    "usage policy, and strategic services of the retainer are fully defined in Schedule B.",
    bold_parts=["Schedule B"])

clause_para("12.2", "The retainer shall activate automatically at the conclusion of the included "
    "support period unless the Client gives written notice of non-renewal at least fourteen (14) "
    "days before the support period expires. Once activated, the retainer continues on a "
    "month-to-month basis, terminable by either Party on thirty (30) days' written notice.",
    bold_parts=["fourteen (14) days", "thirty (30) days"])

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(5)
r1 = p.add_run("12.3  The monthly retainer fee is ")
set_font(r1)
r2 = p.add_run("TWO HUNDRED THOUSAND NAIRA (₦200,000)")
set_font(r2, bold=True)
r3 = p.add_run(", invoiced on the first business day of each calendar month and due within seven "
    "(7) business days of the invoice date. Overdue amounts shall attract interest at five percent "
    "(5%) per annum from the due date to the date of payment.")
set_font(r3)

clause_para("12.4", "The retainer fee includes a monthly AI/LLM API usage allowance as specified "
    "in Schedule B, Part 4. Usage exceeding the included allowance shall be billed as a separate "
    "line item on the monthly invoice at cost plus a fifteen percent (15%) administration margin, "
    "supported by a usage statement from the Service Provider.",
    bold_parts=["Schedule B, Part 4"])

divider()

# ── Execution block ───────────────────────────────────────────────────────────
p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(14)
r = p.add_run("IN WITNESS WHEREOF the Parties have executed this Agreement on the date first above written.")
set_font(r, bold=True)

divider()

sig_block("NEUROLAYER (Service Provider)")
divider()
sig_block("ROYAN HOSPITAL (Client)")

# ════════════════════════════════════════════════════════════════════════════
# PAGE BREAK → SCHEDULE A
# ════════════════════════════════════════════════════════════════════════════
doc.add_page_break()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("SCHEDULE A — PLATFORM DELIVERABLES SUMMARY")
set_font(r, bold=True, size=14)

p2 = doc.add_paragraph()
p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
p2.paragraph_format.space_after = Pt(4)
r2 = p2.add_run("Contract Reference: NL-ROY-2026-001")
set_font(r2, bold=True, size=11)

body("The following modules and components shall be delivered, tested, and formally accepted by the "
     "Client at Go-Live:", space_before=8, space_after=8)

divider()

def sched_phase(title):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after  = Pt(4)
    r = p.add_run(title)
    set_font(r, bold=True, size=12)

def sched_bullet(label, detail):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after  = Pt(4)
    p.paragraph_format.left_indent  = Inches(0.2)
    r1 = p.add_run(f"{label} — ")
    set_font(r1, bold=True, size=10)
    r2 = p.add_run(detail)
    set_font(r2, size=10)

# PHASE 1
sched_phase("PHASE 1 — FOUNDATION (Weeks 1–2)")
sched_bullet("Module 1.1: Patient Registration",
    "automated MRN generation, duplicate detection, digital consent capture, HMO/insurance details, "
    "next-of-kin capture, returning patient lookup, QR self-check-in kiosk")
sched_bullet("Module 1.2: Clinical Queue Management",
    "real-time digital queue display, triage-based queue priority, multi-department routing, "
    "no-show tracking")
sched_bullet("Module 1.3: Appointment Scheduling",
    "doctor-specific scheduling, online booking portal, appointment reminders (SMS/WhatsApp), "
    "specialty clinic scheduling, daily appointment dashboard")
sched_bullet("Module 1.4: Hospital Billing",
    "automatic bill generation from clinical orders, itemised invoicing, HMO pre-authorisation, "
    "co-payment calculation, multiple payment methods (cash/POS/bank transfer), inpatient running "
    "bill, fee schedule management, waiver/discount authorisation workflow")
sched_bullet("Module 1.5: HMO and Insurance Management",
    "HMO coverage rules engine, claim submission and tracking, HMO claims ageing report, coverage "
    "authorisation workflow; initial configuration to include Royan Hospital's active HMO partners")

divider()

# PHASE 2
sched_phase("PHASE 2 — DATA ASSIMILATION (Weeks 2–3)")
sched_bullet("Module 2.1: Data Assimilation Layer (DAL)",
    "extraction of all historical records from DRM Hope MySQL (9 active modules), schema discovery "
    "and field mapping, raw data staging, transformation to RoyanHealth schema, bulk load with "
    "idempotent upsert, full audit trail per run")
sched_bullet("Module 2.2: Data Verification",
    "spot-check validation of migrated patient records, encounter history, billing records, and HMO "
    "data; Client sign-off on data accuracy before Go-Live")

divider()

# PHASE 3
sched_phase("PHASE 3 — CLINICAL MODULES I (Weeks 3–4)")
sched_bullet("Module 3.1: Laboratory Information Management System (LIMS)",
    "electronic lab orders, sample collection and tracking, result entry, reference ranges, critical "
    "result alerting, cumulative lab history, LOINC coding, send-out specimen tracking, lab TAT "
    "monitoring, lab workload reporting")
sched_bullet("Module 3.2: Pharmacy Management",
    "electronic prescription reception, drug inventory and stock management, DDI checking, "
    "allergy/contraindication checking, dispensing confirmation, inpatient MAR integration, ward "
    "stock replenishment, drug return/wastage logging, chronic repeat prescription management, "
    "pharmacy revenue reporting")
sched_bullet("Module 3.3: Nursing and Clinical Support",
    "digital vitals recording, nursing care plans, MAR, IV fluid/intake-output chart, pain score "
    "assessment, wound care documentation, nursing shift handover report")

divider()

# PHASE 4
sched_phase("PHASE 4 — CLINICAL MODULES II (Weeks 4–5)")
sched_bullet("Module 4.1: Radiology and Imaging",
    "electronic imaging requests, radiologist worklist, digital report entry, DICOM/PACS integration "
    "stub, ECG and echo report storage, imaging TAT monitoring, abnormal finding alerts, imaging "
    "workload and revenue reporting")
sched_bullet("Module 4.2: Surgical Theatre",
    "theatre scheduling (elective and emergency), pre-operative assessment checklist, anaesthetic "
    "record, operative notes, post-operative recovery monitoring, surgical consent management")
sched_bullet("Module 4.3: Maternal and Child Health (MCH/OB-GYN)",
    "ANC booking and visit tracking, growth chart and fundal height, partograph, delivery record, "
    "newborn assessment, child immunisation schedule, gynaecology notes, family planning records")

divider()

# PHASE 5
sched_phase("PHASE 5 — SPECIALIST CLINIC TEMPLATES (Weeks 5–6)")
sched_bullet("Module 5.1: 14 Specialty Templates",
    "Cardiology (ECG/Echo reporting), Gastroenterology, Urology, Family Medicine/GP, Orthopaedics, "
    "Paediatrics (growth chart, vaccination record), Chronic Disease (Diabetes/Hypertension), "
    "Physiotherapy and Rehabilitation (session notes, exercise plans), Ophthalmology, ENT, "
    "Dermatology, Oncology, Neurology, Psychiatry/Mental Health")
sched_bullet("Module 5.2: Intra-Hospital Referral",
    "GP to specialist referral workflow, referral letter generation and tracking")

divider()

# PHASE 6
sched_phase("PHASE 6 — DIGITAL PATIENT ENGAGEMENT (Weeks 6–7)")
sched_bullet("Module 6.1: Patient Portal (PWA)",
    "online registration/pre-registration, appointment booking, result viewing, prescription "
    "history, bill payment (Paystack/Flutterwave integration)")
sched_bullet("Module 6.2: SMS and WhatsApp Notifications",
    "appointment reminders, result-ready notification, digital queue number delivery, WhatsApp "
    "booking (Africa's Talking/Termii integration)")
sched_bullet("Module 6.3: Telemedicine Stub",
    "video consultation integration point (infrastructure only; full implementation subject to a "
    "separate agreement)")

divider()

# PHASE 7
sched_phase("PHASE 7 — QUALITY, HR, REPORTING & COMPLIANCE (Week 7)")
sched_bullet("Module 7.1: Quality and Safety",
    "incident reporting and RCA, infection control surveillance, HEFAMAA inspection readiness "
    "checklist, clinical audit management")
sched_bullet("Module 7.2: HR and Administration",
    "staff roster and duty scheduling, leave management, on-call scheduling, staff attendance "
    "tracking, payroll data export")
sched_bullet("Module 7.3: Reporting and Analytics",
    "real-time hospital operations dashboard, daily OPD/A&E attendance, inpatient census, revenue "
    "reports (daily/monthly by department), HMO claims ageing, pharmacy stock and forecasting, lab "
    "TAT report, surgical throughput, disease burden (ICD-10), staff productivity, NHIA/HMIS "
    "regulatory export")

divider()

# PHASE 8
sched_phase("PHASE 8 — UAT, TRAINING, AND GO-LIVE (Week 8)")
sched_bullet("User Acceptance Testing (UAT)",
    "with Client-designated clinical and administrative staff across all modules")
sched_bullet("Staff Training",
    "minimum two (2) structured sessions: (i) clinical staff (doctors, nurses, lab scientists, "
    "pharmacists); (ii) administrative and billing staff")
sched_bullet("Technical Handover Documentation",
    "system architecture guide, admin operations manual, user guides per module")
sched_bullet("Formal Go-Live Sign-off", "by the Client")

divider()

# INFRASTRUCTURE
sched_phase("INFRASTRUCTURE DELIVERABLES")
sched_bullet("On-premise Docker deployment", "on Client-supplied server hardware")
sched_bullet("PostgreSQL database", "with pgvector extension")
sched_bullet("Nginx reverse proxy", "with TLS/HTTPS (LAN certificate)")
sched_bullet("Environment security hardening", "firewall rules, role-based access controls")
sched_bullet("Automated daily database backup service", "")
sched_bullet("System health monitoring", "uptime and API response watchdog")

divider()

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(14)
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("Contract Reference: NL-ROY-2026-001  |  Prepared by Neurolayer  |  © 2026 Neurolayer. All rights reserved.")
set_font(r, italic=True, size=9)

# ════════════════════════════════════════════════════════════════════════════
# PAGE BREAK → SCHEDULE B
# ════════════════════════════════════════════════════════════════════════════
doc.add_page_break()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("SCHEDULE B — MANAGED SERVICES RETAINER")
set_font(r, bold=True, size=14)

p2 = doc.add_paragraph()
p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
p2.paragraph_format.space_after = Pt(4)
r2 = p2.add_run("Contract Reference: NL-ROY-2026-001")
set_font(r2, bold=True, size=11)

add_table(
    ["", ""],
    [
        ["**Monthly Fee**",     "₦200,000"],
        ["**Minimum Term**",    "Three (3) months from activation, thereafter month-to-month"],
        ["**Notice Period**",   "Thirty (30) days written notice by either Party"],
        ["**Activation**",      "Automatically follows expiry of the two (2) month included support period under Clause 8.1, unless the Client gives fourteen (14) days written notice of non-renewal before that period expires."],
    ],
    col_widths=[1.8, 5.2]
)

doc.add_paragraph()

# ── Part 1 ────────────────────────────────────────────────────────────────────
sched_phase("PART 1 — INFRASTRUCTURE & SECURITY")
add_table(
    ["Service", "Detail"],
    [
        ["Scheduled maintenance windows",  "Monthly — applied during agreed low-traffic hours with advance notice to Client IT"],
        ["Security patch deployment",      "Within 48 hours of critical release; within 7 days for standard patches"],
        ["Database optimisation",          "Monthly vacuum, index rebuild, and query performance review"],
        ["Backup restore testing",         "Monthly verified restore test; written results report delivered to Client IT"],
        ["Server health monitoring",       "24/7 uptime, API latency, disk, memory, and CPU alerts"],
        ["Incident response",              "Per SLA defined in Part 3 below"],
    ],
    col_widths=[2.2, 4.8]
)

doc.add_paragraph()

# ── Part 2 ────────────────────────────────────────────────────────────────────
sched_phase("PART 2 — PLATFORM UPDATES & PRODUCT")
add_table(
    ["Service", "Detail"],
    [
        ["Platform version updates",        "All RoyanHealth version updates included at no additional licence charge"],
        ["Regulatory compliance updates",   "NHIA rule changes, HEFAMAA requirements, NDPA amendments — deployed within 14 days of gazettal"],
        ["HMO payer rule updates",          "Coverage rules, tariff changes, and co-payment schedules updated per payer notification"],
        ["New module rollouts",             "Retainer clients receive all new platform modules at no additional licence fee"],
        ["Priority feature queue",          "Client feature requests are prioritised above non-retainer project backlogs"],
    ],
    col_widths=[2.2, 4.8]
)

doc.add_paragraph()

# ── Part 3 ────────────────────────────────────────────────────────────────────
sched_phase("PART 3 — SUPPORT SERVICE LEVEL AGREEMENT (SLA)")
add_table(
    ["Priority", "Definition", "Response Time", "Resolution Target"],
    [
        ["**P1 — Critical**", "System inaccessible, data loss risk, or clinical workflow blocked", "4 hours",         "24 hours"],
        ["**P2 — High**",     "Significant feature degraded; clinical workaround exists",          "1 business day",  "3 business days"],
        ["**P3 — Standard**", "Minor issue, cosmetic defect, or non-urgent request",               "2 business days", "7 business days"],
    ],
    col_widths=[1.4, 3.0, 1.3, 1.3]
)

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(6)
r1 = p.add_run("Support channels: ")
set_font(r1, bold=True, size=10)
r2 = p.add_run("WhatsApp (on-call), email, and phone. A named support contact is assigned to "
    "the Client for the duration of the retainer. Unlimited support tickets are included.")
set_font(r2, size=10)

doc.add_paragraph()

# ── Part 4 ────────────────────────────────────────────────────────────────────
sched_phase("PART 4 — AI & LLM API SERVICES")

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(5)
r1 = p.add_run("4.1  The monthly retainer fee includes an AI/LLM API usage allowance of ")
set_font(r1, size=10)
r2 = p.add_run("₦50,000 per month")
set_font(r2, bold=True, size=10)
r3 = p.add_run(", covering standard clinical assistant query volumes for a 20–50 bed hospital "
    "at current provider pricing. This allowance covers all AI-generated outputs from the "
    "RoyanHealth platform, including:")
set_font(r3, size=10)

for item in [
    "AskSynbot clinical assistant queries across all staff roles (doctors, nurses, pharmacists, lab scientists)",
    "AI-generated end-of-shift briefings and handover summaries",
    "Executive operations summaries",
    "Monthly hospital performance report generation",
]:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after  = Pt(2)
    p.paragraph_format.left_indent  = Inches(0.3)
    r = p.add_run(f"—  {item}")
    set_font(r, size=10)

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(6)
r = p.add_run("4.2  A usage statement shall be included with each monthly invoice, itemising "
    "total tokens consumed, cost incurred at the applicable provider rate, and the amount "
    "applied against the included allowance.")
set_font(r, size=10)

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(5)
r1 = p.add_run("4.3  Usage exceeding the ₦50,000 monthly allowance shall be billed as a "
    "separate line item at ")
set_font(r1, size=10)
r2 = p.add_run("actual API cost plus 15% administration margin")
set_font(r2, bold=True, size=10)
r3 = p.add_run(". The Service Provider shall notify the Client when cumulative monthly usage "
    "reaches 80% of the allowance.")
set_font(r3, size=10)

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(5)
r = p.add_run("4.4  The Service Provider reserves the right to switch LLM providers (e.g., "
    "DeepSeek, Anthropic, or equivalent open-weight models) at its discretion for performance "
    "or cost optimisation, provided that the quality and clinical relevance of AI-generated "
    "outputs is maintained. All pass-through API costs shall reflect actual provider invoices; "
    "the Service Provider shall not inflate provider costs beyond the stated 15% margin.")
set_font(r, size=10)

doc.add_paragraph()

# ── Part 5 ────────────────────────────────────────────────────────────────────
sched_phase("PART 5 — STRATEGIC TECHNOLOGY DIRECTION")

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(4)
p.paragraph_format.space_after  = Pt(6)
r1 = p.add_run("The Neurolayer Managed Services Retainer positions the Service Provider as the Client's ")
set_font(r1, size=10)
r2 = p.add_run("Technology Director on Retainer")
set_font(r2, bold=True, size=10)
r3 = p.add_run(" — a strategic partner, not an IT support vendor.")
set_font(r3, size=10)

add_table(
    ["Service", "Frequency", "Deliverable"],
    [
        ["Hospital Operations Report",
         "Monthly",
         "AI-generated analysis of OPD trends, billing efficiency, HMO claim rejection rate, pharmacy TAT, and top ICD-10 diagnoses. Delivered to MD/CEO and Hospital Administrator."],
        ["Quarterly Roadmap Review",
         "Quarterly",
         "Video or in-person session with hospital management. Service Provider presents upcoming platform capabilities; Client inputs on priorities. Meeting minutes circulated within 5 business days."],
        ["Compliance Audit Readiness Review",
         "Annual",
         "Assessment of HEFAMAA, NDPA, and NHIA readiness. Written findings report and remediation checklist delivered to hospital management."],
        ["AI Performance Review",
         "Quarterly",
         "Review of AskSynbot query accuracy, clinical relevance, and token efficiency. Fine-tuning recommendations documented and applied where feasible within the API allowance."],
        ["Annual Technology Strategy Note",
         "Annual",
         "Written briefing to hospital leadership on healthcare technology trends, regulatory outlook, and recommended platform investments for the coming year."],
    ],
    col_widths=[1.8, 1.0, 4.2]
)

doc.add_paragraph()

# ── Part 6 ────────────────────────────────────────────────────────────────────
sched_phase("PART 6 — EXCLUSIONS")

body("The following are not covered by the retainer and shall be quoted as separate engagements:",
    space_before=4, space_after=6)

for excl in [
    "Hardware procurement, repair, or replacement",
    "Network infrastructure (switches, cabling, wireless access points)",
    "New module development beyond the Schedule A scope",
    "Major custom third-party integrations (external LIMS, PACS, ERP, or payroll systems)",
    "Additional staff training sessions beyond those included in Phase 8 of Schedule A",
    "Full telemedicine implementation (referenced as a stub in Schedule A, Module 6.3)",
]:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after  = Pt(3)
    p.paragraph_format.left_indent  = Inches(0.2)
    r = p.add_run(f"—  {excl}")
    set_font(r, size=10)

divider()

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(14)
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("Schedule B forms part of Contract Reference NL-ROY-2026-001  |  © 2026 Neurolayer. All rights reserved.")
set_font(r, italic=True, size=9)

# ── Save ──────────────────────────────────────────────────────────────────────
out = r"C:\Users\DELL\Desktop\Moe\RoyanSynbot\docs\ROY-Software-Implementation-Agreement-v2.docx"
doc.save(out)
print(f"Saved: {out}")
