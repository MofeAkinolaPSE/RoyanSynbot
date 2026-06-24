"""
EOS Tool Manifest — Single Source of Truth
===========================================
This file is the *only* place where intent keywords, handler names, agent
mappings, and tool-registry names are declared.  Both ``service.py`` and
``app.py`` import from here; nothing is duplicated.

No FastAPI, no DB imports — pure data structures so this module is safe to
import from anywhere without circular-dependency risk.
"""
from __future__ import annotations

from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# 1.  AVAILABLE AGENTS
#     Maps agent name → human-readable description shown in /eos/agents and
#     in the LLM parse prompt.
# ---------------------------------------------------------------------------
AVAILABLE_AGENTS: Dict[str, str] = {
    "financial_agent":            "Financial analysis, billing revenue, cashflow, AR/AP trends",
    "inventory_agent":            "Pharmacy stock levels, medical supply movements, expiry tracking",
    "audit_intelligence":         "Audit schedule analysis, overdue audits, compliance calendar, department audit risk",
    "deviation_capa":             "Clinical incident reports, CAPA actions, investigation workflow, non-conformances",
    "maintenance_tracker":        "Hospital equipment maintenance schedules, calibration status, facilities uptime",
    "revenue_agent":              "Revenue forecasts, billing performance, ward profitability",
    "enterprise_risk_agent":      "Clinical risk assessment, patient safety signals, mitigation strategies",
    "process_optimization_agent": "Workflow efficiency, queue bottlenecks, patient flow optimization",
    "import_agent":               "Supply import status, procurement tracking, medical supply customs",
    "hr_agent":                   "Staff payroll, absences, shift scheduling, workforce analytics",
    "crm_agent":                  "Patient engagement, outreach, appointment conversion, CRM analytics",
    "supplier_agent":             "Medical supplier performance, scorecard, delivery metrics",
    "digital_twin_agent":         "Hospital digital twin system health, anomalies, dependency graph",
    "capability_agent":           "Capability gap detection, system improvement proposals",
    # Hospital-domain agents (Phase 5)
    "patient_flow_agent":         "Monitor patient queue bottlenecks, triage delays, wait time alerts",
    "bed_capacity_agent":         "Ward occupancy, bed availability, discharge predictions",
    "clinical_compliance_agent":  "NDPA 2023, clinical audit, medical record integrity, patient data protection",
    "lab_turnaround_agent":       "Laboratory TAT alerts, result delays, pending lab orders",
    "billing_reconciliation_agent": "Unpaid bills, insurance claim status, payment reconciliation",
    # Diagnostics agent (data pipeline health)
    "diagnostics_agent":          "Page data health validator — confirms all dashboard pages receive live backend data; surfaces broken data pipelines per page",
}


# ---------------------------------------------------------------------------
# 2.  ACTION INTENTS
#     Intents that trigger a real action (email, calendar, task, etc.)
#     rather than running the analytics pipeline.
#
#     Each entry:
#       keywords  – lowercase substrings; if ANY appear in the question the
#                   intent is detected without calling the LLM parser.
#       handler   – name of the async function in service.py.
#       description – shown in the LLM parse prompt.
# ---------------------------------------------------------------------------
ACTION_INTENTS: Dict[str, Dict] = {
    "send_email": {
        "keywords": [
            "send email",
            "email the",
            "send an email",
            "notify the",
            "message the",
            "drop an email",
            "send a message to",
            "send a note to",
            "notify our",
            "email our",
            "contact the",
        ],
        "handler": "_handle_send_email_action",
        "description": "Send an email to an internal department or contact",
    },
    "send_whatsapp": {
        "keywords": [
            "send whatsapp",
            "whatsapp the",
            "send a whatsapp",
            "text the",
            "send a text to",
            "ping the",
            "whatsapp message",
        ],
        "handler": "_handle_send_whatsapp_action",
        "description": "Send a WhatsApp message to an internal department or staff member",
    },
    "schedule_meeting": {
        "keywords": [
            "schedule a meeting",
            "set up a meeting",
            "book a meeting",
            "arrange a meeting",
            "schedule a call",
            "create a meeting",
            "book a call",
            "setup a meeting",
            "schedule meeting",
            "update the calendar",
            "add to the calendar",
            "add to calendar",
        ],
        "handler": "_handle_schedule_meeting_action",
        "description": "Create a calendar event or schedule a meeting",
    },
    "create_task": {
        "keywords": [
            "create a task",
            "create task",
            "add a task",
            "add task",
            "new task",
            "remind me to",
            "set a reminder",
            "todo",
            "to-do",
            "make a note to",
        ],
        "handler": "_handle_task_creation",
        "description": "Create a task or reminder in the task management system",
    },
    "generate_report": {
        "keywords": [
            "generate report",
            "send me a report",
            "export report",
            "pdf report",
            "send report",
            "create a report",
            "pull a report",
            "download report",
            "generate the report",
            # Domain-specific trigger phrases
            "sales report",
            "weekly sales",
            "pipeline report",
            "payroll report",
            "staff payroll",
            "p&l report",
            "profit and loss",
            "profit & loss",
            "ar aging",
            "accounts receivable report",
            "aging report",
            "frontdesk report",
            "daily operations report",
            "deviation report",
            "audit report",
            "compliance report",
            "inventory report",
            "maintenance report",
            "executive summary report",
            "board report",
        ],
        "handler": "_handle_generate_report_action",
        "description": "Generate and return a structured report (P&L, payroll, compliance, sales, inventory, AR aging, etc.)",
    },
    "book_appointment": {
        "keywords": [
            "book appointment",
            "schedule appointment",
            "make an appointment",
            "book a doctor",
            "see a doctor",
            "book consultation",
            "reserve a slot",
            "book a visit",
            "schedule a visit",
            "book a check-up",
        ],
        "handler": "_handle_book_appointment_action",
        "description": "Book a patient appointment with a doctor or department",
        "required_roles": {"doctor", "nurse", "ops", "admin", "management"},
    },
    "check_bed_availability": {
        "keywords": [
            "bed availability",
            "available beds",
            "ward capacity",
            "admit patient",
            "inpatient bed",
            "ward bed",
            "free beds",
        ],
        "handler": "_handle_check_bed_availability_action",
        "description": "Check ward bed availability and occupancy status",
        "required_roles": {"nurse", "doctor", "admin", "management", "ops"},
    },
    "request_lab_order": {
        "keywords": [
            "request lab",
            "order lab test",
            "lab order",
            "blood test order",
            "diagnostic test",
            "send to lab",
            "lab request",
        ],
        "handler": "_handle_request_lab_order_action",
        "description": "Create a laboratory test order for a patient",
        "required_roles": {"doctor", "nurse", "admin", "management"},
    },
    "discharge_patient": {
        "keywords": [
            "discharge patient",
            "patient discharge",
            "process discharge",
            "clear patient",
            "patient going home",
        ],
        "handler": "_handle_discharge_patient_action",
        "description": "Process a patient discharge from the ward",
        "required_roles": {"doctor", "admin", "management"},
    },
    "run_diagnostics": {
        "keywords": [
            "run diagnostics",
            "run the diagnostic",
            "check page data",
            "data health",
            "page health",
            "validate pages",
            "system health check",
            "data pipeline check",
            "which pages have data",
            "dashboard health",
            "use the diagnostic agent",
            "check the agent",
            "diagnostic report",
            "pipeline health",
        ],
        "handler": "_handle_run_diagnostics_action",
        "description": "Run the page data validation agent to check which dashboards are receiving real live data",
    },
    "generate_billing_summary": {
        "keywords": [
            "billing summary",
            "patient bill",
            "generate bill",
            "patient invoice",
            "billing statement",
            "hospital bill",
            "treatment cost",
        ],
        "handler": "_handle_generate_billing_summary_action",
        "description": "Generate a billing summary or invoice for a patient encounter",
        "required_roles": {"admin", "finance", "management"},
    },
}

# Convenience: flat keyword → intent_type lookup built from ACTION_INTENTS
# (used by _detect_action_intent in app.py so keywords live in exactly one place)
ACTION_KEYWORD_MAP: Dict[str, str] = {
    kw: intent
    for intent, cfg in ACTION_INTENTS.items()
    for kw in cfg["keywords"]
}

# Ordered detection: more-specific phrases first prevents short substrings from
# shadowing longer, more-specific ones at detection time.
ORDERED_ACTION_KEYWORDS: List[tuple[str, str]] = sorted(
    ACTION_KEYWORD_MAP.items(),
    key=lambda item: -len(item[0]),
)


# ---------------------------------------------------------------------------
# 3.  DATA INTENTS
#     Intents that run the analytics pipeline (parse → decompose → agents →
#     tool-registry → synthesize).
#
#     Each entry:
#       keywords   – fallback keyword detection phrases
#       agents     – agent names to dispatch (registry name used in get_agent())
#       tools      – tool_registry tool names to call for extra context
#       description – shown in the LLM parse prompt
# ---------------------------------------------------------------------------
DATA_INTENTS: Dict[str, Dict] = {
    "financial_review": {
        "keywords": ["revenue", "profit", "cashflow", "p&l", "ar ", "ap ", "financial", "accounts receivable", "accounts payable"],
        "agents": ["financial_agent", "revenue_agent"],
        "tools": ["getFinancialKpis", "getArTrendSummary"],
        "description": "Financial performance review: P&L, cashflow, AR/AP trends",
    },
    "inventory_audit": {
        "keywords": ["stock", "inventory", "expir", "quantity", "sku", "availability"],
        "agents": ["inventory_agent"],
        "tools": ["getLatestInventorySnapshot", "getExpiringInventory"],
        "description": "Inventory levels, stock status, expiry tracking",
    },
    "compliance_check": {
        "keywords": ["sop", "standard operating", "procedure", "compliance", "audit", "ndpa", "patient data", "clinical audit", "record integrity"],
        "agents": ["clinical_compliance_agent", "audit_intelligence"],
        "tools": [],
        "description": "Clinical compliance, NDPA 2023, SOP adherence, patient data protection",
    },
    "audit_review": {
        "keywords": ["audit schedule", "audit calendar", "overdue audit", "upcoming audit", "audit risk"],
        "agents": ["audit_intelligence", "clinical_compliance_agent"],
        "tools": [],
        "description": "Audit schedule analysis: overdue, upcoming, department risk",
    },
    "deviation_review": {
        "keywords": ["deviation", "capa", "non-conformance", "nonconformance", "corrective action", "incident report", "clinical incident"],
        "agents": ["deviation_capa", "clinical_compliance_agent"],
        "tools": [],
        "description": "Clinical incident reports, CAPA workflow, non-conformance review",
    },
    "maintenance_check": {
        "keywords": ["maintenance", "calibration", "equipment", "breakdown", "facilities", "generator", "medical equipment"],
        "agents": ["maintenance_tracker"],
        "tools": [],
        "description": "Hospital equipment maintenance schedules, calibration, facilities uptime",
    },
    "patient_flow": {
        "keywords": ["queue", "wait time", "patient flow", "triage", "outpatient queue", "opd queue", "bottleneck", "waiting"],
        "agents": ["patient_flow_agent", "process_optimization_agent"],
        "tools": [],
        "description": "Patient queue management, triage delays, wait time analysis",
    },
    "bed_management": {
        "keywords": ["bed", "ward", "inpatient", "occupancy", "admission", "discharge", "bed count", "ward round"],
        "agents": ["bed_capacity_agent"],
        "tools": [],
        "description": "Ward occupancy, bed availability, discharge predictions",
    },
    "lab_status": {
        "keywords": ["lab result", "lab order", "pending lab", "laboratory", "test result", "diagnostic result", "tat", "turnaround"],
        "agents": ["lab_turnaround_agent"],
        "tools": [],
        "description": "Lab order status, pending results, turnaround time alerts",
    },
    "billing_review": {
        "keywords": ["billing", "unpaid bill", "insurance claim", "hmo", "payment reconciliation", "revenue", "billing report"],
        "agents": ["billing_reconciliation_agent", "financial_agent"],
        "tools": ["getFinancialKpis"],
        "description": "Hospital billing review, unpaid bills, insurance claims, payment reconciliation",
    },
    "risk_assessment": {
        "keywords": ["risk", "threat", "vulnerability", "risk register", "risk signals"],
        "agents": ["enterprise_risk_agent"],
        "tools": ["getRiskSignals"],
        "description": "Risk assessment, mitigation strategies, risk heatmap",
    },
    "forecast": {
        "keywords": ["forecast", "predict", "projection", "demand forecast", "stock forecast"],
        "agents": ["financial_agent", "inventory_agent"],
        "tools": ["getOpsKpis"],
        "description": "Demand and financial forecasting",
    },
    "capacity_analysis": {
        "keywords": ["delivery", "shipment", "supply chain", "capacity", "medical supply"],
        "agents": ["inventory_agent", "supplier_agent"],
        "tools": [],
        "description": "Medical supply chain capacity, delivery ops, stock utilization",
    },
    "optimization": {
        "keywords": ["optimize", "efficiency", "bottleneck", "workflow", "process improvement"],
        "agents": ["process_optimization_agent"],
        "tools": [],
        "description": "Workflow efficiency, process bottleneck analysis",
    },
    "status_update": {
        "keywords": [],  # Default fallback — no keywords
        "agents": ["financial_agent"],
        "tools": ["getExecutiveSummary"],
        "description": "General status or business health update",
    },
    "hr_query": {
        "keywords": ["payroll", "salary", "absences", "staff performance", "workforce", "hr report", "overtime"],
        "agents": ["hr_agent"],
        "tools": [],
        "description": "HR analytics: payroll summary, staff absences, workforce metrics",
    },
    "crm_analytics": {
        "keywords": ["crm", "leads", "pipeline", "customer risk", "sales rep", "conversion rate", "crm stats"],
        "agents": ["crm_agent"],
        "tools": [],
        "description": "CRM analytics: lead scoring, pipeline health, customer risk",
    },
    "supplier_performance": {
        "keywords": ["supplier", "vendor performance", "supplier scorecard", "supplier metrics", "procurement performance"],
        "agents": ["supplier_agent"],
        "tools": [],
        "description": "Supplier scorecard, delivery performance, procurement metrics",
    },
    "digital_twin_status": {
        "keywords": ["digital twin", "system health", "twin anomalies", "dependency graph", "twin status"],
        "agents": ["digital_twin_agent"],
        "tools": [],
        "description": "Digital twin system health, open anomalies, inter-system dependencies",
    },
    "executive_overview": {
        "keywords": ["executive overview", "executive brief", "board report", "leadership summary", "business health", "kpi overview"],
        "agents": ["financial_agent", "inventory_agent", "enterprise_risk_agent"],
        "tools": ["getExecutiveSummary", "getRiskSignals", "getRecommendations"],
        "description": "Full executive overview across all business domains",
    },
    "system_diagnostics": {
        "keywords": [
            "run diagnostics", "check page data", "data health", "page health",
            "validate pages", "dashboard health", "pipeline health", "which pages have data",
            "diagnostic agent", "data pipeline check", "diagnostic report",
        ],
        "agents": ["diagnostics_agent"],
        "tools": ["runPageDiagnostics"],
        "description": "Page data health validation — checks all dashboard pages for live backend data",
    },
}

# Merged list of all intent type strings for the LLM parse prompt
ALL_INTENT_TYPES: List[str] = list(ACTION_INTENTS.keys()) + list(DATA_INTENTS.keys())

# ---------------------------------------------------------------------------
# 4.  TASK_MAPPING
#     Maps intent_type → list of {agent, action} task descriptors fed to
#     TaskDecomposer.  Uses the DATA_INTENTS agent lists as source of truth.
# ---------------------------------------------------------------------------
def build_task_mapping() -> Dict[str, List[Dict[str, str]]]:
    """Build the TASK_MAPPING dict from DATA_INTENTS — no duplication."""
    mapping: Dict[str, List[Dict[str, str]]] = {}

    for intent_type, cfg in DATA_INTENTS.items():
        tasks = []
        for agent_name in cfg.get("agents", []):
            # derive a sensible default action name from the agent name
            action = {
                "financial_agent":              "get_summary",
                "revenue_agent":                "get_trends",
                "inventory_agent":              "get_stock_levels",
                "clinical_compliance_agent":    "get_compliance_status",
                "audit_intelligence":           "get_audit_status",
                "deviation_capa":               "get_open_deviations",
                "maintenance_tracker":          "get_overdue",
                "enterprise_risk_agent":        "assess_risks",
                "process_optimization_agent":   "analyze_workflows",
                "hr_agent":                     "get_summary",
                "crm_agent":                    "get_summary",
                "supplier_agent":               "get_metrics",
                "digital_twin_agent":           "get_state",
                "capability_agent":             "get_proposals",
                "patient_flow_agent":           "get_queue_status",
                "bed_capacity_agent":           "get_occupancy",
                "lab_turnaround_agent":         "get_pending_results",
                "billing_reconciliation_agent": "get_unpaid_summary",
            }.get(agent_name, "analyze")
            tasks.append({"agent": agent_name, "action": action})
        mapping[intent_type] = tasks

    # Action intents produce no agent tasks (handled directly)
    for intent_type in ACTION_INTENTS:
        mapping[intent_type] = []

    return mapping


TASK_MAPPING: Dict[str, List[Dict[str, str]]] = build_task_mapping()

# ---------------------------------------------------------------------------
# 5.  DEPARTMENT CONTACT MAP
#     Used by send_email / send_whatsapp handlers to resolve dept → address.
#     Loaded from config.yaml at runtime; this dict provides the key synonyms.
# ---------------------------------------------------------------------------
DEPARTMENT_SYNONYMS: Dict[str, List[str]] = {
    "administration": ["admin", "administration", "management"],
    "billing":        ["billing", "finance", "accounts", "payments"],
    "laboratory":     ["lab", "laboratory", "diagnostics"],
    "pharmacy":       ["pharmacy", "dispensary"],
    "emergency":      ["emergency", "a&e", "accident", "casualty"],
    "operations":     ["operations", "ops", "facilities"],
    "maintenance":    ["maintenance", "engineering", "facilities"],
    "general":        ["general", "reception", "front desk", "helpdesk"],
    "hr":             ["hr", "human resources", "people", "staff"],
}
