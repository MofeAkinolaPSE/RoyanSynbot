"""Reports about one record (s12), User Access (s4) and the Executive overview (s11)."""
import pytest

from src.fin.db import q1
from src.services import executive, record_reports, report_subjects as rs, user_access
from .conftest import needs_applied_migration, user

FAKE = "\n\n".join  # joined section bodies


def _fake_llm(monkeypatch):
    def write(system, prompt):
        assert "Use only the facts" in system
        head = prompt.split("RECORD:", 1)[0]               # the numbered section list comes before the record
        titles = [line.split(". ", 1)[1].split(" - ")[0] for line in head.splitlines() if line[:2].rstrip(".").isdigit()]
        return FAKE(f"## {t}\n\nWritten from the record." for t in titles)
    monkeypatch.setattr(record_reports, "_llm", write)


def test_catalog_follows_roles():
    nurse = {t["type"] for t in rs.catalog(["nurse"])["types"]}
    fin = {t["type"] for t in rs.catalog(["finance"])["types"]}
    assert "incident" in nurse and "hmo_account" not in nurse and "clinical_summary" in nurse
    assert "hmo_account" in fin and "clinical_summary" not in fin
    with pytest.raises(PermissionError):
        rs.list_subjects(["nurse"], "payer")


def test_incident_report_written_from_the_record_only(conn, monkeypatch):
    _fake_llm(monkeypatch)
    iid = q1(conn, """INSERT INTO royan_incident_reports (category, severity, description, ward)
                      VALUES ('patient_fall', 'minor', 'Flow test: patient slipped near bed 4', 'Flow ward') RETURNING id::text AS id""")["id"]
    qa = user("quality_assurance")
    assert any(s["id"] == iid for s in rs.list_subjects(qa["roles"], "incident", "Flow test"))
    d = rs.dossier(qa["roles"], "incident", "incident", iid)
    assert "Root cause" in d["gaps"] and any(f["label"] == "Severity" for f in d["facts"])
    with pytest.raises(ValueError):
        rs.dossier(qa["roles"], "audit", "incident", iid)
    rep = record_reports.generate(qa, "incident", "incident", iid, "Ward manager asked for this")
    assert rep["status"] == "complete" and not rep["needs_signoff"]
    assert "## Appendix: Record details" in rep["full_report"] and "Ward manager asked" in rep["full_report"]
    assert "not written" not in rep["full_report"]
    assert any(r["id"] == rep["id"] for r in record_reports.library(qa, "incident", iid))
    with pytest.raises(LookupError):                       # finance cannot open incident reports
        record_reports.get(user("finance"), rep["id"])


def test_clinical_summary_is_a_draft_until_a_doctor_approves(conn, monkeypatch):
    _fake_llm(monkeypatch)
    enc = q1(conn, "SELECT id::text AS id FROM royan_encounters ORDER BY created_at DESC LIMIT 1")
    if not enc:
        pytest.skip("no encounters")
    doc = user("doctor")
    rep = record_reports.generate(doc, "clinical_summary", "encounter", enc["id"])
    assert rep["status"] == "draft" and rep["needs_signoff"] and "Draft - not valid" in rep["full_report"]
    with pytest.raises(PermissionError):
        record_reports.approve(user("nurse"), rep["id"])
    ok = record_reports.approve(doc, rep["id"])
    assert ok["status"] == "approved" and "Draft - not valid" not in ok["full_report"]


def test_writer_failure_is_loud(conn, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    iid = q1(conn, """INSERT INTO royan_incident_reports (category, description) VALUES ('other', 'Flow test: writer down')
                      RETURNING id::text AS id""")["id"]
    with pytest.raises(record_reports.ReportError):
        record_reports.generate(user("quality_assurance"), "incident", "incident", iid)
    assert q1(conn, "SELECT COUNT(*) AS n FROM royan_record_reports WHERE subject_id=%s", (iid,))["n"] == 0


def test_user_access_roles_profile_and_guards(conn, make_user):
    admin = make_user("admin")
    target = make_user("viewer")
    with pytest.raises(user_access.AccessError):
        user_access.set_roles(admin["sub"], target["sub"], ["nurse"], "")
    with pytest.raises(user_access.AccessError):
        user_access.set_roles(admin["sub"], target["sub"], ["sales"], "legacy role")
    out = user_access.set_roles(admin["sub"], target["sub"], ["nurse", "receptionist", "viewer"], "joined the ward")
    assert out["roles"] == ["nurse", "receptionist"]
    s = q1(conn, "SELECT role FROM royan_staff WHERE user_id=%s", (target["sub"],))
    assert s and s["role"] == "nurse"                       # HR profile exists; team follows the roles
    with pytest.raises(user_access.AccessError):
        user_access.set_roles(admin["sub"], admin["sub"], ["finance"], "oops")
    listed = next(u for u in user_access.users() if u["id"] == target["sub"])
    assert listed["has_profile"] and listed["team"] == "Nursing"


def test_executive_overview_is_composed_and_every_item_links(conn):
    needs_applied_migration()
    d = executive.overview(refresh=True)
    assert not d["unavailable"], d["unavailable"]
    for a in d["attention"]:
        assert a["level"] in ("critical", "action", "info") and a["link"].startswith("/")
    shelf = q1(conn, "SELECT COALESCE(SUM(quantity_on_hand*unit_cost),0) v FROM royan_inventory_batches WHERE quantity_on_hand > 0")["v"]
    assert round(d["finance"]["stock"]["shelf_value"], 2) == round(float(shelf), 2)
    assert 0 <= (d["quality"]["compliance_score"]) <= 100
    b = d["billing"]
    assert round(sum(m["total"] for m in b["months"]), 2) == round(b["billed_12m"], 2)
