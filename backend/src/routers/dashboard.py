from fastapi import APIRouter, Depends, HTTPException, Request, Response
from typing import Dict, Any, List
from src.middleware import verify_jwt, require_role
from src.services.intelligence import (
    get_inventory_dashboard,
    get_workforce_dashboard,
    get_active_alerts,
    generate_executive_briefing
)
from src.services.crm import get_crm_stats
from src.services.sage_adapter.service import kpis as finance_kpis
from src.services.hospital_ops import (
    get_patient_flow_kpis,
    get_queue_by_department,
    get_daily_clinical_stats,
    get_patient_flow_by_hour,
)
import logging

router = APIRouter(prefix="/dashboard", tags=["dashboard", "intelligence"])
audit_logger = logging.getLogger("audit")

# --- Dependencies ---

def require_management(request: Request) -> Dict[str, Any]:
    """Roles: admin, management, finance (for specific views)."""
    payload = verify_jwt(request)
    roles = payload.get("roles", [])
    allowed = {"admin", "management", "finance", "ops"} 
    
    if not any(r in allowed for r in roles):
        raise HTTPException(403, "Insufficient privileges for dashboard access")
    return payload

def require_clinical(request: Request) -> Dict[str, Any]:
    """Roles: admin, management, ops, nurse, doctor — for hospital operational data."""
    payload = verify_jwt(request)
    roles = payload.get("roles", [])
    allowed = {"admin", "management", "ops", "nurse", "doctor"}
    if not any(r in allowed for r in roles):
        raise HTTPException(403, "Hospital dashboard access requires clinical or management role")
    return payload

def require_executive(request: Request) -> Dict[str, Any]:
    """Strategic View: Admin, Management only."""
    payload = verify_jwt(request)
    roles = payload.get("roles", [])
    allowed = {"admin", "management"}
    if not any(r in allowed for r in roles):
        raise HTTPException(403, "Executive Briefing is restricted")
    return payload

# --- Endpoints ---

@router.get("/hospital-status")
def hospital_status(response: Response, user: Dict[str, Any] = Depends(verify_jwt)):
    # Counts only (waiting, seen, wait time, per department / hour) - no patient details - so every
    # signed-in member of staff can see the hospital's pulse. It was limited to clinical roles, which
    # left the Front Desk's own KPI cards at zero for receptionists.
    """
    Live hospital operational status: patient flow KPIs, queue by department,
    daily clinical stats, and per-hour encounter distribution for the chart.
    Primary data source for the Hospital Command Center dashboard.
    """
    response.headers["Cache-Control"] = "no-store, no-cache"
    def build():
        return {
            "data": {
                **get_patient_flow_kpis(),
                "queue_by_department": get_queue_by_department(),
                "clinical_today":      get_daily_clinical_stats(),
                "flow_by_hour":        get_patient_flow_by_hour(),
            }
        }
    try:
        # Every page's top bar asks for this; five seconds shared across workers keeps it live
        # while 50 laptops don't each run the four counts.
        from src.cache import shared_response
        return shared_response("dashboard:hospital-status", 5, build)
    except Exception as e:
        logging.error(f"Hospital status dashboard error: {e}")
        raise HTTPException(500, "Failed to load hospital status")


@router.get("/finance")
def dashboard_finance(response: Response, user: Dict[str, Any] = Depends(require_management)):
    """Finance specific dashboard data."""
    if "finance" not in user.get("roles", []) and "admin" not in user.get("roles", []) and "management" not in user.get("roles", []):
         raise HTTPException(403, "Role not authorized for Finance view")
    response.headers["Cache-Control"] = "no-store, no-cache"
    try:
        return {"data": finance_kpis()}
    except Exception as e:
        logging.error(f"Finance dashboard error: {e}")
        raise HTTPException(500, "Failed to load finance metrics")

@router.get("/inventory")
def dashboard_inventory(response: Response, user: Dict[str, Any] = Depends(require_management)):
    """Inventory specific dashboard data."""
    response.headers["Cache-Control"] = "no-store, no-cache"
    return {"data": get_inventory_dashboard()}

@router.get("/workforce")
def dashboard_workforce(response: Response, user: Dict[str, Any] = Depends(require_management)):
    """Workforce specific dashboard data."""
    response.headers["Cache-Control"] = "no-store, no-cache"
    return {"data": get_workforce_dashboard()}

@router.get("/crm")
def dashboard_crm(response: Response, user: Dict[str, Any] = Depends(require_management)):
    """CRM specific dashboard data."""
    response.headers["Cache-Control"] = "no-store, no-cache"
    return {"data": get_crm_stats()}

@router.get("/alerts")
def list_alerts(response: Response, user: Dict[str, Any] = Depends(require_management)):
    """Active system alerts."""
    response.headers["Cache-Control"] = "no-store, no-cache"
    return {"data": get_active_alerts()}

def require_overview(request: Request) -> Dict[str, Any]:
    """Executive overview: admin, management and finance (reportGUide.md s11)."""
    payload = verify_jwt(request)
    if not {"admin", "management", "finance"} & set(payload.get("roles") or []):
        raise HTTPException(403, "The executive overview is for management and finance")
    return payload


@router.get("/executive")
def executive_overview(response: Response, refresh: bool = False, user: Dict[str, Any] = Depends(require_overview)):
    """The hospital on one page, composed from each module's hub service (services/executive.py).
    Cached five minutes; ?refresh=true rebuilds it."""
    from src.cache import shared_response
    from src.services import executive
    response.headers["Cache-Control"] = "no-store, no-cache"
    # one build shared by every worker, not one per worker
    return shared_response("executive:overview", 300, lambda: executive.overview(refresh=refresh), refresh=refresh)


@router.get("/executive-briefing")
def executive_briefing(response: Response, user: Dict[str, Any] = Depends(require_executive)):
    """
    High-value unified report.
    Audited access.
    """
    audit_logger.info({"event": "executive_briefing_access", "user": user.get("sub")})
    response.headers["Cache-Control"] = "no-store, no-cache"
    try:
        return {"data": generate_executive_briefing()}
    except Exception as e:
        logging.error(f"Briefing generation failed: {e}")
        raise HTTPException(500, "Failed to generate briefing")
