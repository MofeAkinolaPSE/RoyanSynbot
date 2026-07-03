"""
extract.py
----------
Step 1 of the VistA Pipeline.

Parses the VistA monograph DOCX, extracts each module's heading + full
body text, and serialises the raw data to a JSON file for downstream
processing by the LLM feature-extraction step.

Usage:
    python -m scripts.vista_pipeline.extract
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[3]           # …/RoyanSynbot
MONOGRAPH  = REPO_ROOT / "backend" / "docs" / "vista_res" / "vista_monograph_0723_r.docx"
OUTPUT_DIR = REPO_ROOT / "backend" / "docs" / "vista_res" / "pipeline_output"

# The parent heading that contains all module entries
MODULES_PARENT_TEXT = "4. The VistA Modules"
# Heading levels we treat as "module" boundaries
MODULE_HEADING_STYLE = "Heading 3"

# ---------------------------------------------------------------------------
# VA-specific modules that are irrelevant to a civilian Nigerian hospital.
# These are filtered out after extraction to keep the output clean.
# ---------------------------------------------------------------------------
VA_SPECIFIC_MODULES: frozenset[str] = frozenset({
    "Above PAR (APAR)",
    "Automated Medical Information Exchange (AMIE)",
    "Beneficiary Travel",
    "Blind Rehabilitation/VIST",
    "Compensation and Pension Record Interchange (CAPRI)",
    "Fugitive Felon Program (FFP)",
    "Home Telehealth/Integrated Home Telehealth (IHTA)",
    "Homeless Management Information (HMIS)",
    "Hospital Inquiry (HINQ)",
    "Income Verification Match (IVM)",
    "Methicillin Resistant Staphylococcus Aureus Program Tools (MRSA-PT)",
    "National Utilization Management Integration (NUMI)",
    "Network Health Exchange (NHE)",
    "Occupational Health Recordkeeping System (OHRS)",
    "Remote Order Entry System (ROES)",
    "Spinal Cord Injury and Disorders Outcomes (SCIDO)",
    "Traumatic Brain Injury Registry (TBI)",
    "Veterans Crisis Line (VCL)",
    "Veterans Health Identification Card (VHIC)",
    "Veterans Personal Finance System (VPFS)",
    "Veterans Point of Service",
    "Virtual Electronic eHealth Exchange (VLER)",
    "Wounded, Injured and Ill Veterans",
    "Enrollment Application System",
    "Enrollment Application System: Long Term Care (LTC) Copayment",
    "Enrollment System",
    "CMOP (Consolidated Mail Output Pharmacy) Pharmaceutical System (CPS)",
    "Consolidated Mail Output Pharmacy (CMOP)",
    "Electronic Claims Management Engine (ECME) (AKA: ePharmacy)",
    "Decision Support System (DSS) Extracts",
    "Fee Basis",
    "Fee Basis Claims Archive (FBCA)",
    "Fat Client Kernel Authentication and Authorization (FatKAAT)",
    "Joint Longitudinal Viewer (JLV)",
    "My HealtheVet",
    "Virtual Patient Record (VPR)",
    "VistAWeb",
    "Web VistA Remote Access Management (WebVRAM)",
    "Capacity Management Tools",
    "Advanced Prosthetics Acquisition Tool (APAT)",
    "Prosthetics",
    "Remote Procedure Call Broker (RPC)",
    "M-to-M Broker",
    "SlotMaster (Kernel ZSLOT)",
    "Statistical Analysis of Global Growth (SAGG)",
    "Resource Usage Monitor (RUM)",
    "Electronic Error and Enhancement Reporting (E3R)",
    "Enterprise Exception Log Services (EELS)",
    "National Patch Module (NPM)",
    "Generic Code Sheet",
})


# ---------------------------------------------------------------------------
# Domain category mapping (module name → domain)
# Applied as a best-effort tag; LLM step may refine.
# ---------------------------------------------------------------------------
DOMAIN_MAP: dict[str, str] = {
    # Patient management
    "Admission, Discharge, Transfer (ADT)/Registration": "Patient Management",
    "Master Patient Index (MPI)": "Patient Management",
    "Duplicate Record Merge": "Patient Management",
    "Patient Data Exchange (PDX)": "Patient Management",
    "Patient Record Flags (PRF)": "Patient Management",
    "Patient Representative": "Patient Management",
    "Patient Advocate Tracking System (PATS)": "Patient Management",
    "Record Tracking": "Patient Management",
    "Scheduling": "Patient Management",
    "Patient Centered Management Module (PCMM Web)": "Patient Management",
    "Primary Care Management Module": "Patient Management",
    "National Provider Identifier (NPI)": "Patient Management",
    # Clinical documentation / CPRS
    "VistA - CPRS: Order Entry/Results Reporting": "Clinical Documentation",
    "VistA - CPRS: Problem List": "Clinical Documentation",
    "VistA - CPRS: Health Summary": "Clinical Documentation",
    "VistA - CPRS: Clinical Reminders": "Clinical Documentation",
    "VistA - CPRS: Consult/Request Tracking": "Clinical Documentation",
    "VistA - CPRS: Text Integration Utilities (TIU)": "Clinical Documentation",
    "VistA - CPRS: Women's Health": "Clinical Documentation",
    "CPRS: Adverse Reaction Tracking (ART)": "Clinical Documentation",
    "CPRS: Authorization/Subscription (ASU)": "Clinical Documentation",
    "Group Notes": "Clinical Documentation",
    "Incomplete Records Tracking (IRT)": "Clinical Documentation",
    "Release of Information (ROI)": "Clinical Documentation",
    "Health Data Informatics": "Clinical Documentation",
    "Health Data Repository": "Clinical Documentation",
    "Virtual Patient Record (VPR)": "Clinical Documentation",
    "DocManager": "Clinical Documentation",
    # Nursing
    "Nursing": "Nursing",
    "Vitals/Measurements": "Nursing",
    "Intake and Output": "Nursing",
    "Shift Handoff Tool": "Nursing",
    "Bed Management Solution (BMS)": "Nursing",
    "Care Management": "Nursing",
    # Pharmacy
    "Pharmacy: Bar Code Medication Administration (BCMA)": "Pharmacy",
    "Bar Code Medication Administration (BCMA) Backup Utility": "Pharmacy",
    "Pharmacy: Inpatient Medications": "Pharmacy",
    "Pharmacy: Inpatient Medications - Intravenous (IV)": "Pharmacy",
    "Pharmacy: Inpatient Medications - Unit Dose (UD)": "Pharmacy",
    "Pharmacy: Outpatient Pharmacy": "Pharmacy",
    "Pharmacy: Controlled Substances": "Pharmacy",
    "Pharmacy: Drug Accountability/Inventory Interface": "Pharmacy",
    "Pharmacy: Automatic Replenishment/Ward Stock (AR/WS)": "Pharmacy",
    "Pharmacy: National Drug File (NDF)": "Pharmacy",
    "Pharmacy: Pharmacy Benefits Management (PBM)": "Pharmacy",
    "Pharmacy: Pharmacy Data Management (PDM)": "Pharmacy",
    "Pharmacy: Pharmacy Enterprise Customization System (PECS)": "Pharmacy",
    "Pharmacy: Pharmacy Product System - National Registries (PSS-N)": "Pharmacy",
    "Pharmacy: Medication Order Check Healthcare Application (MOCHA)": "Pharmacy",
    # Laboratory
    "VistA – Laboratory": "Laboratory",
    "VistA - Laboratory: Anatomic Pathology (AP)": "Laboratory",
    "VistA - Laboratory: Blood Bank": "Laboratory",
    "VistA - Laboratory: Electronic Data Interchange": "Laboratory",
    "VistA - Laboratory: Point of Care": "Laboratory",
    "VistA - Laboratory: Universal Interface": "Laboratory",
    "National Laboratory Tests Documents and LOINC Request Form": "Laboratory",
    # Radiology / Imaging
    "Radiology/Nuclear Medicine": "Radiology & Imaging",
    "VistA Imaging System": "Radiology & Imaging",
    "Clinical Procedures": "Radiology & Imaging",
    # Emergency
    "Emergency Department Integration Software (EDIS)": "Emergency Department",
    "Automated Information Collection System (AICS)": "Emergency Department",
    # Surgery
    "Surgery": "Surgery",
    "VistA Chemotherapy Manager (VCM)": "Surgery",
    "Oncology": "Surgery",
    # Mental health
    "Mental Health": "Mental Health",
    "Mental Health Suite": "Mental Health",
    # Billing & Finance
    "Accounts Receivable (AR)": "Billing & Finance",
    "Integrated Billing (IB)": "Billing & Finance",
    "Integrated Funds Distribution, Control Point Activity, Accounting and Procurement (IFCAP)": "Billing & Finance",
    "Patient Care Encounter (PCE)": "Billing & Finance",
    "Encoder Product Suite (EPS)": "Billing & Finance",
    "Diagnostic Related Grouper (DRG)": "Billing & Finance",
    "Event Capture System": "Billing & Finance",
    "Insurance Capture Buffer": "Billing & Finance",
    "Maximo (Max)": "Billing & Finance",
    # Administration & HR
    "Personnel and Accounting Integrated Data (PAID)": "HR & Administration",
    "Engineering (AEMS/MERS)": "HR & Administration",
    "Equipment /Turn-In Request": "Equipment Management",
    "Nutrition and Food Service (N&FS)": "Support Services",
    "Social Work": "Support Services",
    "Library": "Support Services",
    "Voluntary Service System": "Support Services",
    "Survey Generator": "Support Services",
    # Infection / Quality
    "Occurrence Screen": "Quality & Safety",
    "Quality Management Integration Module": "Quality & Safety",
    "Incident Reporting": "Quality & Safety",
    "Automated Safety Incident Surveillance Tracking System (ASISTS)": "Quality & Safety",
    "Emerging Pathogens Initiative (EPI)": "Quality & Safety",
    "Clinical Case Registries (CCR)": "Quality & Safety",
    "Clinical Case Registries: Hepatitis C (HepC)": "Quality & Safety",
    "Clinical Case Registries: Human Immunodeficiency Virus (HIV)": "Quality & Safety",
    "VistA - Clinical Case Registries": "Quality & Safety",
    # Specialty
    "Dental Record Manager (DRM) Plus": "Specialty Services",
    "Medicine": "Specialty Services",
    "Home Based Primary Care (HBPC)": "Specialty Services",
    "Functional Independence Measures (FIM)": "Specialty Services",
    "Quality Audiology and Speech Analysis and Reporting (QUASAR)": "Specialty Services",
    "Resident Assessment Instrument/Minimum Data Set (RAI/MDS)": "Specialty Services",
    "Clinical Monitoring System": "Specialty Services",
    "Telecare Record Manager (TRM)": "Specialty Services",
    "Clinical Information Support System (CISS)": "Specialty Services",
    "Caribou Community Living Care (CLC) Suite (Caribou)": "Specialty Services",
    # Infrastructure / interoperability
    "Kernel": "Infrastructure",
    "Kernel Toolkit": "Infrastructure",
    "Kernel Authentication & Authorization for Java 2 Enterprise Edition (KAAJEE)": "Infrastructure",
    "Kernel Delphi Components (KDC)": "Infrastructure",
    "Kernel Unwinder": "Infrastructure",
    "VA FileMan": "Infrastructure",
    "Health Level 7 (HL7) (VistA Messaging)": "Infrastructure",
    "Health Level Seven Optimized (HLO) (VistA Messaging)": "Infrastructure",
    "Electronic Signature (Esig)": "Infrastructure",
    "Single Sign On/User Context (SSO/UC)": "Infrastructure",
    "Identity Management (IdM) Service": "Infrastructure",
    "Cross Application Integration Protocol (CAIP)": "Infrastructure",
    "Medical Domain Web Services (MDWS)": "Infrastructure",
    "VistALink": "Infrastructure",
    "XML Parser": "Infrastructure",
    "Remote Procedure Call Broker (RPC)": "Infrastructure",
    "FileMan Delphi Components (FDMC)": "Infrastructure",
    "List Manager": "Infrastructure",
    "Mailman": "Infrastructure",
    "Standards and Terminology Services (STS)": "Infrastructure",
    "Lexicon Utility": "Infrastructure",
    "VistA Data Extraction Framework (VDEF)": "Infrastructure",
    "Enterprise Health Management Platform": "Infrastructure",
    "Repositories: Administrative Data Repository (ADR)": "Infrastructure",
    "Repositories: Clinical Data Repository/Health Data Repository (CHDR)": "Infrastructure",
    "Health Information Technology Sharing (HITS): Bi-Directional Health Information Exchange (BHIE) and Legacy Viewer Sustainment (LVS)": "Infrastructure",
    "Health Information Technology Sharing (HITS): Clinical Health Data Repository (CHDR)": "Infrastructure",
    "Health Information Technology Sharing (HITS): Federal Health Information Exchange (FHIE)": "Infrastructure",
    "Health Information Technology Sharing (HITS): Global War on Terror": "Infrastructure",
    "Health Information Technology Sharing (HITS): Laboratory Data Sharing and Interoperability (LDSI)": "Infrastructure",
    "HOWDY Computerized Login Process": "Infrastructure",
    "M-to-M Broker": "Infrastructure",
    "Mobile Electronic Documentation": "Infrastructure",
}


def _heading_level(style_name: str) -> int:
    """Return numeric heading level from a style name like 'Heading 3'."""
    m = re.search(r"(\d+)", style_name)
    return int(m.group(1)) if m else 99


def _is_module_section_start(para, in_module_section: bool) -> bool | None:
    """
    Returns True if this paragraph starts the Module section,
    False if it ends it (higher-level heading encountered while inside),
    None if no state change.
    """
    if not para.style.name.startswith("Heading"):
        return None
    text = para.text.strip()
    lvl  = _heading_level(para.style.name)
    if MODULES_PARENT_TEXT in text and lvl == 2:
        return True
    if in_module_section and lvl <= 2 and MODULES_PARENT_TEXT not in text:
        return False
    return None


def extract_modules(docx_path: Path) -> list[dict]:
    """
    Walk the DOCX and return a list of dicts, one per VistA module:

        {
          "name":        str,
          "raw_text":    str,   # concatenated body paragraphs
          "domain":      str,   # best-effort category
          "va_specific": bool,
        }
    """
    doc = Document(str(docx_path))
    paragraphs = doc.paragraphs

    modules: list[dict] = []
    current_module: dict | None = None
    in_module_section = False

    for para in paragraphs:
        style  = para.style.name
        text   = para.text.strip()

        state_change = _is_module_section_start(para, in_module_section)
        if state_change is True:
            in_module_section = True
            continue
        if state_change is False:
            # Save last module
            if current_module:
                modules.append(current_module)
                current_module = None
            in_module_section = False
            continue

        if not in_module_section:
            continue

        if style == MODULE_HEADING_STYLE and text:
            # Save previous module
            if current_module:
                modules.append(current_module)
            current_module = {
                "name":        text,
                "raw_text":    "",
                "domain":      DOMAIN_MAP.get(text, "Uncategorized"),
                "va_specific": text in VA_SPECIFIC_MODULES,
            }
        elif current_module and text:
            current_module["raw_text"] += text + "\n"

    # Don't forget the last module if doc ends in module section
    if current_module:
        modules.append(current_module)

    log.info("Extracted %d modules (%d VA-specific filtered)",
             len(modules),
             sum(1 for m in modules if m["va_specific"]))
    return modules


def save_raw_modules(modules: list[dict], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "01_raw_modules.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(modules, f, indent=2, ensure_ascii=False)
    log.info("Raw modules saved → %s", out)
    return out


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    modules = extract_modules(MONOGRAPH)
    saved   = save_raw_modules(modules, OUTPUT_DIR)

    # Quick summary
    from collections import Counter
    domain_counts = Counter(m["domain"] for m in modules if not m["va_specific"])
    print(f"\n✓  Total modules extracted : {len(modules)}")
    print(f"   VA-specific (skipped)   : {sum(1 for m in modules if m['va_specific'])}")
    print(f"   Civilian-relevant       : {sum(1 for m in modules if not m['va_specific'])}")
    print(f"\n   Domain breakdown:")
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        print(f"     {count:3d}  {domain}")
    print(f"\n   Output → {saved}")
