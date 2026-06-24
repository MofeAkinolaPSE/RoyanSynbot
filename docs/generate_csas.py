"""
Generates Word documents for:
  - Neurolayer-Consultant-Rate-Card.docx
  - CSA-Lawyer.docx
  - CSA-FSE.docx
  - CSA-Marketing.docx

Run: python docs/generate_csas.py
"""
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

DOCS_DIR = r"C:\Users\DELL\Desktop\Moe\RoyanSynbot\docs"

# ── Shared helpers ─────────────────────────────────────────────────────────────
def new_doc():
    doc = Document()
    for section in doc.sections:
        section.top_margin    = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin   = Inches(1.25)
        section.right_margin  = Inches(1.25)
    s = doc.styles["Normal"]
    s.font.name = "Times New Roman"
    s.font.size = Pt(11)
    return doc

def sf(run, bold=False, italic=False, size=11):
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.bold   = bold
    run.italic = italic

def divider(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after  = Pt(2)
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bot = OxmlElement("w:bottom")
    bot.set(qn("w:val"), "single"); bot.set(qn("w:sz"), "6")
    bot.set(qn("w:space"), "1");    bot.set(qn("w:color"), "auto")
    pBdr.append(bot); pPr.append(pBdr)

def h1(doc, text, center=False):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after  = Pt(4)
    if center: p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(text); sf(r, bold=True, size=13)

def h2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after  = Pt(4)
    r = p.add_run(text); sf(r, bold=True, size=11)

def para(doc, text="", sb=5, sa=5, indent=0):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(sb)
    p.paragraph_format.space_after  = Pt(sa)
    p.paragraph_format.left_indent  = Inches(indent)
    r = p.add_run(text); sf(r)
    return p

def bold_inline(doc, pairs, sb=5, sa=5):
    """pairs = list of (text, is_bold)"""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(sb)
    p.paragraph_format.space_after  = Pt(sa)
    for text, bold in pairs:
        r = p.add_run(text); sf(r, bold=bold)
    return p

def clause(doc, num, text, bold_phrases=None):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(5)
    p.paragraph_format.space_after  = Pt(5)
    full = f"{num}  {text}"
    if not bold_phrases:
        r = p.add_run(full); sf(r)
    else:
        remaining = full
        for bp in bold_phrases:
            idx = remaining.find(bp)
            if idx < 0: continue
            if idx: r = p.add_run(remaining[:idx]); sf(r)
            r = p.add_run(bp); sf(r, bold=True)
            remaining = remaining[idx+len(bp):]
        if remaining: r = p.add_run(remaining); sf(r)
    return p

def sub(doc, letter, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after  = Pt(4)
    p.paragraph_format.left_indent  = Inches(0.25)
    r = p.add_run(f"({letter})  {text}"); sf(r)

def table(doc, headers, rows, col_widths=None):
    t = doc.add_table(rows=1+len(rows), cols=len(headers))
    t.style = "Table Grid"
    hrow = t.rows[0]
    for i, h in enumerate(headers):
        cell = hrow.cells[i]
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p = cell.paragraphs[0]
        r = p.add_run(h); sf(r, bold=True, size=10)
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after  = Pt(3)
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), "E8E8E8"); tcPr.append(shd)
    for ri, row_data in enumerate(rows):
        row = t.rows[ri+1]
        for ci, val in enumerate(row_data):
            cell = row.cells[ci]
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(3)
            p.paragraph_format.space_after  = Pt(3)
            if val.startswith("**") and val.endswith("**"):
                r = p.add_run(val[2:-2]); sf(r, bold=True, size=10)
            else:
                r = p.add_run(val); sf(r, size=10)
    if col_widths:
        for i, w in enumerate(col_widths):
            for row in t.rows:
                row.cells[i].width = Inches(w)
    return t

def sig_block(doc, party_label):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    r = p.add_run(f"SIGNED {party_label}"); sf(r, bold=True)
    for label in ["Signature:", "Name:", "Designation:", "Date:"]:
        p2 = doc.add_paragraph()
        p2.paragraph_format.space_before = Pt(10)
        r1 = p2.add_run(f"{label}  "); sf(r1, bold=True)
        r2 = p2.add_run("_" * 45); sf(r2)

def sig_block_consultant(doc, name_placeholder):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    r = p.add_run(f"SIGNED by {name_placeholder} (Consultant)"); sf(r, bold=True)
    for label in ["Signature:", "Name:", "Date:"]:
        p2 = doc.add_paragraph()
        p2.paragraph_format.space_before = Pt(10)
        r1 = p2.add_run(f"{label}  "); sf(r1, bold=True)
        r2 = p2.add_run("_" * 45); sf(r2)

def footer_line(doc, ref):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"{ref}  |  © 2026 Neurolayer. All rights reserved.")
    sf(r, italic=True, size=9)

def title_block(doc, title, ref):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(title); sf(r, bold=True, size=15)
    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2.paragraph_format.space_after = Pt(10)
    r2 = p2.add_run(ref); sf(r2, bold=True, size=11)
    divider(doc)

def parties_block(doc, consultant_label, consultant_desc):
    bold_inline(doc, [
        ("THIS AGREEMENT is made this [  ] day of [  ] 2026.", False)
    ], sb=12)
    para(doc, "BETWEEN", sb=10, sa=2)
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    r1 = p.add_run("NEUROLAYER"); sf(r1, bold=True)
    r2 = p.add_run(' (hereinafter referred to as the "'); sf(r2)
    r3 = p.add_run("Company"); sf(r3, bold=True)
    r4 = p.add_run('"), a technology company specialising in AI-powered software systems, '
        'of 64 Aina Street, Ojodu, Lagos, Nigeria.'); sf(r4)
    para(doc, "AND", sb=8, sa=2)
    p2 = doc.add_paragraph()
    p2.paragraph_format.space_before = Pt(6)
    r5 = p2.add_run(consultant_label); sf(r5, bold=True)
    r6 = p2.add_run(' (hereinafter referred to as the "'); sf(r6)
    r7 = p2.add_run("Consultant"); sf(r7, bold=True)
    r8 = p2.add_run(f'"), {consultant_desc}.'); sf(r8)
    para(doc, "", sb=12)
    divider(doc)
    p3 = doc.add_paragraph()
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p3.paragraph_format.space_before = Pt(10)
    r9 = p3.add_run("NOW IT IS HEREBY AGREED AS FOLLOWS:"); sf(r9, bold=True)
    divider(doc)


# ══════════════════════════════════════════════════════════════════════════════
# DOCUMENT 1 — RATE CARD
# ══════════════════════════════════════════════════════════════════════════════
def build_rate_card():
    doc = new_doc()
    title_block(doc, "NEUROLAYER — INTERNAL CONSULTANT RATE CARD",
                "Version 1.0 | Effective: 2026 | Confidential — Internal Use Only")

    h1(doc, "REVENUE ALLOCATION MODEL (5-BUCKET RULE)")
    para(doc, "On every client payment received, funds are allocated in this order before any distribution:")
    table(doc,
        ["Bucket", "Allocation", "Purpose"],
        [
            ["Consultant Costs",      "~20%",  "Pay the team per deliverables in this rate card"],
            ["Operations",            "5%",    "Tools, API costs, licences, equipment"],
            ["Business Reserve",      "10%",   "Float fund — covers 1 month of costs if client delays"],
            ["Growth / Reinvestment", "10%",   "Legal filings, marketing, tooling, development"],
            ["Founder's Profit",      "~55%",  "Moe's draw after all above are funded"],
        ],
        col_widths=[1.8, 1.0, 4.2]
    )
    para(doc, sb=6)
    bold_inline(doc, [
        ("Payment Timing Rule: ", True),
        ("All consultant payments are made within 5 business days of Neurolayer receiving the corresponding client payment.", False)
    ])
    bold_inline(doc, [
        ("WHT Policy: ", True),
        ("5% Withholding Tax is deducted from each payment and remitted to FIRS. Rates below are gross — net payment = rate × 95%.", False)
    ])

    divider(doc)
    h1(doc, "LAWYER — RATE CARD")
    table(doc,
        ["Service", "Gross Fee"],
        [
            ["Full client contract bundle (SIA + NDA + addendum)", "₦100,000"],
            ["Single document (amendment or standalone NDA)",       "₦35,000"],
            ["Retainer schedule drafting (Schedule B)",             "Included in bundle"],
            ["Legal advisory / dispute instance",                   "₦50,000"],
            ["Annual contract review or renewal",                   "₦25,000"],
            ["Company registration (CAC filing)",                   "₦75,000"],
        ],
        col_widths=[4.5, 2.5]
    )
    bold_inline(doc, [("Payment trigger: ", True),
        ("On client contract execution (Mobilisation Fee received).", False)], sb=8)

    divider(doc)
    h1(doc, "FULL STACK ENGINEER (FSE) — RATE CARD")
    table(doc,
        ["Service", "Gross Fee", "Scope"],
        [
            ["New client — platform deployment, configuration & customisation", "₦350,000",
             "Docker, .env config, DB migrations, nginx/TLS, Go-Live handover. Excludes custom dev, third-party integrations, training beyond Go-Live."],
            ["Data migration / DAL execution (per client)", "₦100,000",
             "ETL pipeline from legacy system. Includes discovery, mapping, bulk load, verification."],
            ["Monthly maintenance — active retainer client", "₦80,000/month",
             "Maintenance window, patches, DB optimisation, backup testing, health monitoring, P1–P3 SLA."],
            ["Feature sprint (agreed scope, 1–2 weeks)", "₦60,000/sprint",
             "Scoped feature set agreed in writing before sprint. Scope change = new agreement."],
            ["Emergency hotfix — P1 outside maintenance window", "₦30,000/instance",
             "Critical system restoration outside normal scope."],
        ],
        col_widths=[2.0, 1.2, 3.8]
    )
    bold_inline(doc, [("New client payment split: ", True),
        ("40% at Mobilisation Fee | 40% at Milestone Fee | 20% at Go-Live Fee.", False)], sb=8)
    bold_inline(doc, [("Tool coverage (paid by Neurolayer): ", True),
        ("GitHub Copilot ~$10/month. Other tools by written request.", False)])

    divider(doc)
    h1(doc, "MARKETING ANALYST — RATE CARD")
    table(doc,
        ["Service", "Gross Fee"],
        [
            ["Client acquisition bonus — signed contract < ₦2M",        "₦75,000"],
            ["Client acquisition bonus — signed contract ₦2M–₦5M",     "₦150,000"],
            ["Client acquisition bonus — signed contract > ₦5M",        "₦200,000"],
            ["Pitch deck / proposal per RFP",                           "₦40,000"],
            ["Monthly market intelligence report",                       "₦30,000/month"],
            ["Monthly campaign execution (lead gen, outreach, content)", "₦50,000/month"],
        ],
        col_widths=[4.5, 2.5]
    )
    bold_inline(doc, [("Payment trigger: ", True),
        ("Acquisition bonus on Mobilisation Fee receipt. Monthly at end of calendar month from retainer revenue.", False)], sb=8)

    divider(doc)
    h1(doc, "PROJECT P&L REFERENCE")
    h2(doc, "New Client — ₦3.5M (e.g. Royan Hospital)")
    table(doc,
        ["Item", "Amount"],
        [
            ["Lawyer (contract bundle)",             "₦100,000"],
            ["FSE (deployment + DAL)",               "₦450,000"],
            ["Marketing (₦2M–₦5M acquisition bonus)","₦150,000"],
            ["Operations (5%)",                      "₦175,000"],
            ["Business reserve (10%)",               "₦350,000"],
            ["Growth / reinvestment (10%)",          "₦350,000"],
            ["**Moe's profit**",                     "**₦1,925,000**"],
        ],
        col_widths=[4.5, 2.5]
    )
    doc.add_paragraph()
    h2(doc, "Monthly Retainer — ₦400K/month (2 clients)")
    table(doc,
        ["Item", "Per Client", "Both Clients"],
        [
            ["FSE maintenance",       "₦80,000",  "₦160,000"],
            ["Operations",            "₦20,000",  "₦40,000"],
            ["Business reserve (10%)","₦20,000",  "₦40,000"],
            ["Growth (10%)",          "₦20,000",  "₦40,000"],
            ["**Moe's monthly draw**","**₦60,000**","**₦120,000**"],
        ],
        col_widths=[3.0, 1.5, 2.5]
    )

    divider(doc)
    footer_line(doc, "Neurolayer Internal Rate Card — Confidential")
    path = f"{DOCS_DIR}\\Neurolayer-Consultant-Rate-Card.docx"
    doc.save(path)
    print(f"Saved: {path}")


# ══════════════════════════════════════════════════════════════════════════════
# DOCUMENT 2 — CSA LAWYER
# ══════════════════════════════════════════════════════════════════════════════
def build_csa(ref, consultant_label, consultant_desc, clauses_fn, out_filename):
    doc = new_doc()
    title_block(doc, "CONSULTANT SERVICES AGREEMENT", ref)
    parties_block(doc, consultant_label, consultant_desc)
    clauses_fn(doc)
    divider(doc)
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    r = p.add_run("IN WITNESS WHEREOF the Parties have executed this Agreement on the date first above written.")
    sf(r, bold=True)
    divider(doc)
    sig_block(doc, "for and on behalf of NEUROLAYER (Company)")
    divider(doc)
    sig_block_consultant(doc, consultant_label)
    divider(doc)
    footer_line(doc, ref)
    path = f"{DOCS_DIR}\\{out_filename}"
    doc.save(path)
    print(f"Saved: {path}")


def lawyer_clauses(doc):
    h1(doc, "1.   ENGAGEMENT")
    clause(doc, "1.1", "The Company engages the Consultant as an independent legal counsel on a "
        "non-exclusive, per-deliverable basis. The Consultant shall provide legal services as "
        "requested from time to time in accordance with this Agreement.")
    clause(doc, "1.2", "This Agreement does not constitute a contract of employment, partnership, "
        "or joint venture. The Consultant is an independent contractor solely responsible for "
        "their own tax affairs, except as provided in clause 3.4.")
    divider(doc)

    h1(doc, "2.   SCOPE OF SERVICES & RATE CARD")
    clause(doc, "2.1", "The Consultant shall provide legal services from the following schedule:")
    table(doc,
        ["Service", "Gross Fee"],
        [
            ["Full client contract bundle (SIA + NDA + any addendum)", "₦100,000 per client"],
            ["Single document — amendment or standalone NDA",           "₦35,000"],
            ["Retainer schedule drafting (e.g., Schedule B to SIA)",    "Included in bundle fee"],
            ["Legal advisory or dispute instance",                       "₦50,000"],
            ["Annual contract review or renewal",                        "₦25,000"],
            ["Company registration (CAC filing)",                        "₦75,000"],
        ],
        col_widths=[4.5, 2.5]
    )
    doc.add_paragraph()
    clause(doc, "2.2", "Work is requested in writing (email or WhatsApp). The Consultant confirms "
        "acceptance and estimated delivery within two (2) business days.")
    clause(doc, "2.3", "Fees may be renegotiated by mutual written agreement. No rate change applies "
        "to work already in progress.")
    divider(doc)

    h1(doc, "3.   PAYMENT TERMS")
    clause(doc, "3.1", "The Consultant shall submit a written invoice upon completion of each deliverable.")
    clause(doc, "3.2", "Payment shall be made within five (5) business days of the Company receiving "
        "the corresponding client payment (e.g., for a client contract bundle, payment is triggered "
        "by the client's Mobilisation Fee settlement). Where not tied to a client milestone, payment "
        "is due within ten (10) business days of invoice.", bold_phrases=["five (5) business days"])
    clause(doc, "3.3", "All payments are by bank transfer. No cash payments.")
    clause(doc, "3.4", "Withholding Tax (WHT) at five percent (5%) shall be deducted from each "
        "payment and remitted to FIRS. Net payment = gross fee × 95%. WHT credit notes shall be "
        "provided.", bold_phrases=["five percent (5%)"])
    divider(doc)

    h1(doc, "4.   INTELLECTUAL PROPERTY")
    clause(doc, "4.1", "All work product — including contract templates, legal documents, draft "
        "agreements, and written opinions — is the sole property of the Company upon creation.",
        bold_phrases=["sole property of the Company"])
    clause(doc, "4.2", "The Consultant irrevocably assigns all intellectual property rights in "
        "such work product to the Company, effective retroactively to cover all prior work.")
    clause(doc, "4.3", "The Consultant warrants that all work product is original and does not "
        "infringe third-party intellectual property rights.")
    divider(doc)

    h1(doc, "5.   CONFIDENTIALITY")
    clause(doc, "5.1", "The Consultant shall hold all Confidential Information in strict confidence "
        "for five (5) years following termination.", bold_phrases=["five (5) years"])
    clause(doc, "5.2", '"Confidential Information" includes client identities, commercial terms, '
        "software architecture, business strategy, financial data, and all information designated "
        "as confidential.", bold_phrases=['"Confidential Information"'])
    clause(doc, "5.3", "The Consultant shall comply with the Nigeria Data Protection Act (NDPA) "
        "2023 with respect to any patient or clinical data encountered.",
        bold_phrases=["Nigeria Data Protection Act (NDPA) 2023"])
    divider(doc)

    h1(doc, "6.   NON-SOLICITATION")
    clause(doc, "6.1", "During the term and for twelve (12) months following termination, the "
        "Consultant shall not directly solicit, contract with, or provide services to any client "
        "introduced through the Company's engagements, without prior written consent.",
        bold_phrases=["twelve (12) months"])
    divider(doc)

    h1(doc, "7.   NO EQUITY OR PROFIT SHARE")
    clause(doc, "7.1", "This Agreement does not create any equity interest, profit-sharing, or "
        "ownership stake in the Company. The Consultant's sole entitlement is the fees in clause 2.1.")
    divider(doc)

    h1(doc, "8.   TERMINATION & HANDOVER")
    clause(doc, "8.1", "Either Party may terminate by thirty (30) days' written notice.",
        bold_phrases=["thirty (30) days"])
    clause(doc, "8.2", "Upon termination, the Consultant shall: (a) complete and deliver all "
        "outstanding work within ten (10) business days; (b) transfer all files and correspondence; "
        "(c) return or destroy all Company Confidential Information.")
    clause(doc, "8.3", "The Company shall pay all fees for work completed to termination date.")
    divider(doc)

    h1(doc, "9.   GOVERNING LAW AND DISPUTES")
    clause(doc, "9.1", "This Agreement is governed by the laws of the Federal Republic of Nigeria.",
        bold_phrases=["laws of the Federal Republic of Nigeria"])
    clause(doc, "9.2", "Disputes shall first be subject to good-faith negotiation. If unresolved "
        "within fourteen (14) days, the matter shall be referred to a single arbitrator under the "
        "Arbitration and Mediation Act 2023, in Lagos, Nigeria.",
        bold_phrases=["Arbitration and Mediation Act 2023"])
    divider(doc)

    h1(doc, "10.   GENERAL")
    p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(5)
    r1 = p.add_run("10.1  Entire Agreement.  "); sf(r1, bold=True)
    r2 = p.add_run("This Agreement supersedes all prior discussions on its subject matter."); sf(r2)
    p2 = doc.add_paragraph(); p2.paragraph_format.space_before = Pt(5)
    r3 = p2.add_run("10.2  Amendment.  "); sf(r3, bold=True)
    r4 = p2.add_run("No amendment is valid unless made in writing and signed by both Parties."); sf(r4)
    p3 = doc.add_paragraph(); p3.paragraph_format.space_before = Pt(5)
    r5 = p3.add_run("10.3  Assignment.  "); sf(r5, bold=True)
    r6 = p3.add_run("The Consultant may not subcontract without prior written consent."); sf(r6)


def fse_clauses(doc):
    h1(doc, "1.   ENGAGEMENT")
    clause(doc, "1.1", "The Company engages the Consultant as an independent Full Stack Engineer "
        "on a non-exclusive, per-deliverable basis to provide software engineering services as "
        "requested from time to time.")
    clause(doc, "1.2", "This Agreement does not constitute employment, partnership, or joint "
        "venture. The Consultant is an independent contractor.")
    divider(doc)

    h1(doc, "2.   SCOPE OF SERVICES & RATE CARD")
    clause(doc, "2.1", "The Consultant shall provide services from the following schedule:")
    table(doc,
        ["Service", "Gross Fee", "Scope Definition"],
        [
            ["New client — platform deployment, configuration & customisation", "₦350,000",
             "Docker deployment, .env config, DB migrations, nginx/TLS setup, Go-Live handover. Excludes custom features, third-party integrations beyond agreed scope, or training beyond Go-Live."],
            ["Data migration / DAL execution (per client)", "₦100,000",
             "ETL pipeline from legacy MySQL to RoyanHealth DB: schema discovery, mapping, bulk load, spot-check verification."],
            ["Monthly maintenance — active retainer client", "₦80,000/month",
             "Maintenance window, security patches, DB optimisation, backup restore testing, server health monitoring, P1–P3 issue resolution."],
            ["Feature sprint (agreed scope, 1–2 weeks)", "₦60,000/sprint",
             "Scoped feature set agreed in writing before sprint begins. Scope change requires new written agreement."],
            ["Emergency hotfix — P1 outside maintenance window", "₦30,000/instance",
             "Critical system restoration outside normal maintenance scope."],
        ],
        col_widths=[1.8, 1.1, 4.1]
    )
    doc.add_paragraph()
    clause(doc, "2.2", "Work is requested in writing with a clear scope statement. Consultant "
        "confirms acceptance and timeline within two (2) business days.")
    clause(doc, "2.3", "Out-of-scope work must be quoted and approved in writing before commencing.")
    divider(doc)

    h1(doc, "3.   PAYMENT TERMS")
    clause(doc, "3.1", "The Consultant submits a written invoice upon completion of each deliverable "
        "(or at month-end for monthly maintenance).")
    bold_inline(doc, [("3.2  New client project — milestone-linked payment: ", True)], sb=5, sa=2)
    sub(doc, "a", "40% (₦140,000) within 5 business days of Company receiving client Mobilisation Fee")
    sub(doc, "b", "40% (₦140,000) within 5 business days of Company receiving client Milestone Fee")
    sub(doc, "c", "20% (₦70,000) within 5 business days of Company receiving client Go-Live Fee")
    clause(doc, "3.3", "Monthly maintenance fees are paid within five (5) business days of the "
        "Company receiving the client's retainer invoice settlement for the corresponding month.",
        bold_phrases=["five (5) business days"])
    clause(doc, "3.4", "Withholding Tax at five percent (5%) is deducted from each payment and "
        "remitted to FIRS. Net payment = gross × 95%. WHT credit notes provided.",
        bold_phrases=["five percent (5%)"])
    clause(doc, "3.5", "All payments are by bank transfer. No cash payments.")
    divider(doc)

    h1(doc, "4.   TOOL COVERAGE")
    clause(doc, "4.1", "The Company shall cover the following tools for the Consultant's work:")
    table(doc,
        ["Tool", "Monthly Cost", "Policy"],
        [
            ["GitHub Copilot",     "~$10 (≈₦16,000)", "Paid by Company; licence assigned to Consultant for duration of engagement"],
            ["Other agreed tools", "By request",       "Requires written approval before purchase; licence remains Company property"],
        ],
        col_widths=[1.8, 1.4, 3.8]
    )
    clause(doc, "4.2", "Upon termination, all Company-paid tool licences must be transferred to "
        "Company admin accounts within five (5) business days.")
    divider(doc)

    h1(doc, "5.   ACCESS & CREDENTIALS")
    clause(doc, "5.1", "The Consultant shall ensure the Company has admin-level access to all "
        "repositories, deployment servers, cloud accounts, and tools at all times. The Consultant "
        "shall never be the sole key holder to any Company or client system.",
        bold_phrases=["admin-level access"])
    clause(doc, "5.2", "All source code shall be committed to Company-controlled GitHub repositories. "
        "No code shall be stored solely on the Consultant's personal devices or private repositories.")
    divider(doc)

    h1(doc, "6.   INTELLECTUAL PROPERTY")
    clause(doc, "6.1", "All work product — including source code, scripts, database schemas, "
        "configuration files, and documentation — is the sole property of the Company upon creation.",
        bold_phrases=["sole property of the Company"])
    clause(doc, "6.2", "The Consultant irrevocably assigns all intellectual property rights in "
        "work product to the Company, retroactively covering all prior work.")
    clause(doc, "6.3", "The Consultant warrants that all work product is original and free of "
        "incompatible open-source licence obligations.")
    divider(doc)

    h1(doc, "7.   CONFIDENTIALITY")
    clause(doc, "7.1", "The Consultant shall hold all Confidential Information in strict confidence "
        "for five (5) years following termination.", bold_phrases=["five (5) years"])
    clause(doc, "7.2", '"Confidential Information" includes source code, client identities, patient '
        "data, clinical records, system architecture, API keys, credentials, and business strategy.")
    clause(doc, "7.3", "The Consultant shall comply with the Nigeria Data Protection Act (NDPA) "
        "2023 with respect to any patient data encountered.",
        bold_phrases=["Nigeria Data Protection Act (NDPA) 2023"])
    divider(doc)

    h1(doc, "8.   NON-SOLICITATION")
    clause(doc, "8.1", "During the term and for twelve (12) months following termination, the "
        "Consultant shall not directly solicit, contract with, or provide services to any client "
        "introduced through the Company's engagements, without prior written consent.",
        bold_phrases=["twelve (12) months"])
    divider(doc)

    h1(doc, "9.   NO EQUITY OR PROFIT SHARE")
    clause(doc, "9.1", "This Agreement creates no equity interest, profit-sharing, or ownership "
        "stake in the Company. The Consultant's sole entitlement is the fees in clause 2.1.")
    divider(doc)

    h1(doc, "10.   TERMINATION & HANDOVER")
    clause(doc, "10.1", "Either Party may terminate by thirty (30) days' written notice.",
        bold_phrases=["thirty (30) days"])
    clause(doc, "10.2", "Upon notice of termination, the Consultant shall:")
    sub(doc, "a", "Complete all in-progress work within the notice period")
    sub(doc, "b", "Transfer all credentials, access tokens, repository permissions, and documentation to Company accounts within five (5) business days of termination date")
    sub(doc, "c", "Provide up to thirty (30) days of handover support at the standard maintenance rate (₦80,000/month pro-rated)")
    sub(doc, "d", "Return or securely delete all Company and client Confidential Information from personal devices")
    clause(doc, "10.3", "The Company shall pay all fees for work completed to termination date.")
    divider(doc)

    h1(doc, "11.   GOVERNING LAW AND DISPUTES")
    clause(doc, "11.1", "This Agreement is governed by the laws of the Federal Republic of Nigeria.")
    clause(doc, "11.2", "Disputes shall first be subject to good-faith negotiation. If unresolved "
        "within fourteen (14) days, the matter shall be referred to a single arbitrator under the "
        "Arbitration and Mediation Act 2023, in Lagos, Nigeria.",
        bold_phrases=["Arbitration and Mediation Act 2023"])
    divider(doc)

    h1(doc, "12.   GENERAL")
    p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(5)
    r1 = p.add_run("12.1  Entire Agreement.  "); sf(r1, bold=True)
    r2 = p.add_run("This Agreement supersedes all prior discussions on its subject matter."); sf(r2)
    p2 = doc.add_paragraph(); p2.paragraph_format.space_before = Pt(5)
    r3 = p2.add_run("12.2  Amendment.  "); sf(r3, bold=True)
    r4 = p2.add_run("No amendment is valid unless made in writing and signed by both Parties."); sf(r4)
    p3 = doc.add_paragraph(); p3.paragraph_format.space_before = Pt(5)
    r5 = p3.add_run("12.3  Assignment.  "); sf(r5, bold=True)
    r6 = p3.add_run("The Consultant may not subcontract without prior written consent."); sf(r6)


def marketing_clauses(doc):
    h1(doc, "1.   ENGAGEMENT")
    clause(doc, "1.1", "The Company engages the Consultant as an independent Marketing Analyst "
        "on a non-exclusive, per-deliverable basis to provide marketing and business development "
        "services as requested from time to time.")
    clause(doc, "1.2", "This Agreement does not constitute employment, partnership, or joint venture. "
        "The Consultant is an independent contractor.")
    divider(doc)

    h1(doc, "2.   SCOPE OF SERVICES & RATE CARD")
    clause(doc, "2.1", "The Consultant shall provide services from the following schedule:")
    table(doc,
        ["Service", "Gross Fee"],
        [
            ["Client acquisition bonus — signed contract < ₦2,000,000",        "₦75,000"],
            ["Client acquisition bonus — signed contract ₦2,000,000–₦5,000,000","₦150,000"],
            ["Client acquisition bonus — signed contract > ₦5,000,000",         "₦200,000"],
            ["Pitch deck / proposal per RFP or prospect",                        "₦40,000"],
            ["Monthly market intelligence report",                               "₦30,000/month"],
            ["Monthly campaign execution (lead gen, outreach, content)",         "₦50,000/month"],
        ],
        col_widths=[4.5, 2.5]
    )
    doc.add_paragraph()
    clause(doc, "2.2", '"Client acquisition" for the bonus means: the Consultant identified the '
        "prospect, initiated or materially contributed to outreach, and the prospect subsequently "
        "executed a signed Services Agreement with the Company. Introductions made independently "
        "by the Company do not qualify.")
    clause(doc, "2.3", "Work is requested in writing. Consultant confirms acceptance within two "
        "(2) business days.")
    divider(doc)

    h1(doc, "3.   PAYMENT TERMS")
    clause(doc, "3.1", "Acquisition bonus: paid within five (5) business days of the Company "
        "receiving the client's Mobilisation Fee.", bold_phrases=["five (5) business days"])
    clause(doc, "3.2", "Pitch deck / proposal: paid within ten (10) business days of delivery, "
        "regardless of prospect conversion.")
    clause(doc, "3.3", "Monthly services: paid at end of each calendar month from retainer revenue. "
        "Company shall notify Consultant in advance if monthly services cannot be funded in a given month.")
    clause(doc, "3.4", "Withholding Tax at five percent (5%) is deducted from each payment and "
        "remitted to FIRS. Net payment = gross × 95%. WHT credit notes provided.",
        bold_phrases=["five percent (5%)"])
    clause(doc, "3.5", "All payments by bank transfer. No cash payments.")
    divider(doc)

    h1(doc, "4.   INTELLECTUAL PROPERTY")
    clause(doc, "4.1", "All work product — including pitch decks, proposals, market reports, "
        "campaign assets, content, brand materials, and client research — is the sole property "
        "of the Company upon creation.", bold_phrases=["sole property of the Company"])
    clause(doc, "4.2", "The Consultant irrevocably assigns all intellectual property rights in "
        "work product to the Company, retroactively covering all prior work.")
    divider(doc)

    h1(doc, "5.   CONFIDENTIALITY")
    clause(doc, "5.1", "The Consultant shall hold all Confidential Information in strict confidence "
        "for five (5) years following termination.", bold_phrases=["five (5) years"])
    clause(doc, "5.2", '"Confidential Information" includes prospect lists, client identities and '
        "commercial terms, pricing structures, product roadmaps, business strategy, and financial data.")
    divider(doc)

    h1(doc, "6.   NON-SOLICITATION & NON-COMPETE")
    clause(doc, "6.1", "During the term and for twelve (12) months following termination, the "
        "Consultant shall not directly solicit, contract with, or provide marketing services to "
        "any client introduced through the Company's engagements, without prior written consent.",
        bold_phrases=["twelve (12) months"])
    clause(doc, "6.2", "During the term, the Consultant shall not provide marketing or business "
        "development services to any direct competitor (i.e., any company building or selling "
        "AI-powered hospital or pharmaceutical management software in Nigeria) without prior "
        "written disclosure and approval.")
    divider(doc)

    h1(doc, "7.   NO EQUITY OR PROFIT SHARE")
    clause(doc, "7.1", "This Agreement creates no equity interest, profit-sharing, or ownership "
        "stake in the Company. The Consultant's sole entitlement is the fees in clause 2.1.")
    divider(doc)

    h1(doc, "8.   TERMINATION & HANDOVER")
    clause(doc, "8.1", "Either Party may terminate by thirty (30) days' written notice.",
        bold_phrases=["thirty (30) days"])
    clause(doc, "8.2", "Upon termination, the Consultant shall: (a) deliver all in-progress work "
        "within ten (10) business days; (b) transfer all prospect data, campaign accounts, CRM "
        "access, and brand assets to Company-designated accounts; (c) return or destroy all "
        "Company Confidential Information.")
    clause(doc, "8.3", "Acquisition bonuses for prospects actively in negotiation at termination "
        "who subsequently sign within sixty (60) days shall remain payable at the applicable rate.")
    divider(doc)

    h1(doc, "9.   GOVERNING LAW AND DISPUTES")
    clause(doc, "9.1", "This Agreement is governed by the laws of the Federal Republic of Nigeria.")
    clause(doc, "9.2", "Disputes shall first be subject to good-faith negotiation. If unresolved "
        "within fourteen (14) days, referred to a single arbitrator under the Arbitration and "
        "Mediation Act 2023, in Lagos, Nigeria.",
        bold_phrases=["Arbitration and Mediation Act 2023"])
    divider(doc)

    h1(doc, "10.   GENERAL")
    p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(5)
    r1 = p.add_run("10.1  Entire Agreement.  "); sf(r1, bold=True)
    r2 = p.add_run("This Agreement supersedes all prior discussions on its subject matter."); sf(r2)
    p2 = doc.add_paragraph(); p2.paragraph_format.space_before = Pt(5)
    r3 = p2.add_run("10.2  Amendment.  "); sf(r3, bold=True)
    r4 = p2.add_run("No amendment is valid unless in writing and signed by both Parties."); sf(r4)
    p3 = doc.add_paragraph(); p3.paragraph_format.space_before = Pt(5)
    r5 = p3.add_run("10.3  Assignment.  "); sf(r5, bold=True)
    r6 = p3.add_run("The Consultant may not subcontract without prior written consent."); sf(r6)


# ── Run all ───────────────────────────────────────────────────────────────────
build_rate_card()

build_csa(
    ref="Contract Reference: NL-CSA-LAW-2026-001",
    consultant_label="[Lawyer Full Name]",
    consultant_desc="a legal practitioner licensed under the laws of the Federal Republic of Nigeria, "
                    "of [Consultant Address], Nigeria",
    clauses_fn=lawyer_clauses,
    out_filename="CSA-Lawyer.docx"
)

build_csa(
    ref="Contract Reference: NL-CSA-FSE-2026-001",
    consultant_label="[Engineer Full Name]",
    consultant_desc="a software engineer, of [Consultant Address], Nigeria",
    clauses_fn=fse_clauses,
    out_filename="CSA-FSE.docx"
)

build_csa(
    ref="Contract Reference: NL-CSA-MKT-2026-001",
    consultant_label="[Marketing Analyst Full Name]",
    consultant_desc="a marketing professional, of [Consultant Address], Nigeria",
    clauses_fn=marketing_clauses,
    out_filename="CSA-Marketing.docx"
)

print("\nAll documents generated successfully.")
