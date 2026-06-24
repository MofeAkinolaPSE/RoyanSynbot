from .base_agent import BaseAgent, Insight

# Import all agent implementations so they register with the agent registry on package import
from . import inventory_agent  # noqa: F401
from . import financial_agent  # noqa: F401
from . import revenue_agent  # noqa: F401
from . import enterprise_risk_agent  # noqa: F401
from . import process_optimization_agent  # noqa: F401
from . import import_clearance_agent  # noqa: F401
from . import expiry_monitoring_agent  # noqa: F401
from . import maintenance_agent  # noqa: F401
from . import digital_twin_monitor_agent  # noqa: F401
from . import capability_discovery_agent  # noqa: F401
# EOS action agents — must be imported here so @register_agent fires at startup
from . import email_agent  # noqa: F401
from . import calendar_agent  # noqa: F401
from . import report_generation_agent  # noqa: F401
# Hospital domain agents (Phase 5)
from . import patient_flow_agent  # noqa: F401
from . import bed_capacity_agent  # noqa: F401
from . import clinical_compliance_agent  # noqa: F401
from . import lab_turnaround_agent  # noqa: F401
from . import billing_reconciliation_agent  # noqa: F401

__all__ = ["BaseAgent", "Insight"]
