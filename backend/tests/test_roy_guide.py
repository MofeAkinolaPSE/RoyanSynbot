"""Roy's system guide: parsing, coverage of the real sidebar, help routing,
section selection, the dynamic length budget, and /chat behaviour."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.services import roy_guide  # noqa: E402

NAV_ITEMS = ROOT.parent / "SynbotUI" / "client" / "lib" / "nav-items.ts"


# ── The guide itself ─────────────────────────────────────────────────────────

def test_guide_loads_with_unique_ids_and_content():
    sections = roy_guide.load_guide()
    assert len(sections) >= 40
    ids = [s.id for s in sections]
    assert len(ids) == len(set(ids)), "duplicate section ids"
    for s in sections:
        assert s.keywords, f"{s.id} has no keywords"
        assert len(s.body) > 40, f"{s.id} has no real body"
    for required in roy_guide.ALWAYS_IN_HELP:
        assert any(s.id == required for s in sections)


@pytest.mark.skipif(not NAV_ITEMS.exists(), reason="frontend not checked out next to backend")
def test_every_sidebar_page_is_in_the_guide():
    """If a page is added to the sidebar without a guide section, Roy will tell
    staff it does not exist. Add a section to src/knowledge/roy_feature_guide.md."""
    hrefs = set(re.findall(r'href:\s*"(/[^"]*)"', NAV_ITEMS.read_text(encoding="utf-8")))
    assert hrefs
    missing = sorted(h for h in hrefs if not any(s.matches_route(h) for s in roy_guide.load_guide()))
    assert not missing, f"sidebar pages with no Roy guide section: {missing}"


def test_route_patterns_match_parameterised_urls():
    chart = next(s for s in roy_guide.load_guide() if s.id == "patient-chart")
    assert chart.matches_route("/hospital/patients/RH16-27")
    assert not chart.matches_route("/hospital/patients")


# ── Help detection ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("q", [
    "How do I register a patient?",
    "how to generate a bill",
    "Where can I find the lab results?",
    "where is the discharge button",
    "Which page do I use for leave?",
    "Can I edit a signed note?",
    "Is there a way to print an invoice?",
    "Does the system have telemedicine?",
    "I can't find the pharmacy inventory",
    "show me how to dispense",
    "what can you do",
    "can I save what I typed as a template",
    "I keep typing the same examination for every patient, is there a faster way?",
])
def test_help_questions_detected(q):
    assert roy_guide.is_help_question(q)


@pytest.mark.parametrize("q", [
    "How many patients are waiting?",
    "Where is patient Adebayo?",
    "What is the outstanding balance for RH16-27?",
    "Send an email to finance about the audit",
    "hello",
    "how are we doing today",
    "can you create a task for Dr Bello",
])
def test_data_and_action_questions_not_detected(q):
    assert not roy_guide.is_help_question(q)


# ── Section selection ────────────────────────────────────────────────────────

@pytest.mark.parametrize("q,expected", [
    ("how do I check in a walk-in patient", "front-desk"),
    ("how do I correct a mistake in a signed note", "note-addendum"),
    ("where do I verify a lab result", "lab"),
    ("how do I record a payment and print a receipt", "billing"),
    ("how do I apply for leave", "my-workspace"),
    ("why is the plan section locked on my soap note", "soap-note"),
    ("how do I admit a patient to a bed", "wards-beds"),
    ("how do I mark a patient as arrived for their appointment", "appointments"),
    ("how do I create my own template?", "personal-templates"),
    ("I keep typing the same examination every time", "personal-templates"),
    ("how do I share my template with other doctors", "personal-templates"),
])
def test_top_section(q, expected):
    top = roy_guide.score_sections(q)
    assert top and top[0][1].id == expected, [s.id for _, s in top[:3]]


def test_help_context_marks_pages_outside_the_users_role():
    ctx = roy_guide.build_guide_context("how do I record a payment", {"doctor"})
    assert "Billing & Cashier" in ctx
    assert "NOT available to this user" in ctx
    assert "Record Payment" not in ctx, "steps for a page the user cannot open are withheld"
    menu = ctx.split("PAGES ON THIS USER'S MENU:")[1]
    assert "Billing & Cashier" not in menu
    assert "Queue & Flow" in menu


def test_help_context_always_carries_honesty_sections_and_current_page():
    ctx = roy_guide.build_guide_context("how does this work", {"lab"}, "/hospital/lab")
    assert "CURRENT PAGE: the user is on Lab & Diagnostics" in ctx
    assert "Things the system does not do" in ctx
    assert "What Roy can and cannot do from chat" in ctx


def test_conversational_question_only_gets_guide_on_a_strong_match():
    small_talk = roy_guide.build_guide_context("good morning", {"doctor"}, help_mode=False)
    assert "### " not in small_talk, "no full section for a greeting"
    assert "- Queue & Flow" in small_talk, "but the real page names are always there"
    assert "Correcting a signed note" in roy_guide.build_guide_context(
        "I made a mistake in a signed note, the addendum is confusing", {"doctor"}, help_mode=False
    )


def test_sanitize_page():
    assert roy_guide.sanitize_page("/hospital/lab?tab=orders") == "/hospital/lab"
    assert roy_guide.sanitize_page("javascript:alert(1)") is None
    assert roy_guide.sanitize_page("/x<script>") is None
    assert roy_guide.sanitize_page(None) is None


# ── Dynamic length ───────────────────────────────────────────────────────────

def test_budget_scales_with_question_shape():
    small = roy_guide.response_budget("thanks", "conversational")
    count = roy_guide.response_budget("How many patients are waiting?", "conversational")
    where = roy_guide.response_budget("Where is the leave button?", "guide")
    howto = roy_guide.response_budget("How do I write a SOAP note?", "guide")
    report = roy_guide.response_budget("inventory report", "report")
    assert small.max_words <= 30
    assert count.max_words < where.max_words < howto.max_words < report.max_words
    assert howto.min_words >= 30, "how-to answers must not be one-liners"


def test_count_question_gets_a_short_answer_even_when_routed_as_a_report():
    count = roy_guide.response_budget("How many patients are waiting for the nurse?", "report")
    listing = roy_guide.response_budget("How many patients are waiting, by ward?", "report")
    assert count.max_words <= 60
    assert listing.max_words > 120


def test_budget_respects_brief_and_detailed_requests():
    base = roy_guide.response_budget("How do I book an appointment?", "guide")
    brief = roy_guide.response_budget("Briefly, how do I book an appointment?", "guide")
    detail = roy_guide.response_budget("How do I book an appointment, step by step in detail?", "guide")
    assert brief.max_words < base.max_words < detail.max_words
    assert base.max_tokens > base.max_words  # token cap leaves headroom over the word budget


# ── /chat behaviour ──────────────────────────────────────────────────────────

@pytest.fixture()
def chat_client(monkeypatch):
    from fastapi.testclient import TestClient
    import app as app_module

    captured: dict = {}

    def fake_llm(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(app_module, "verify_jwt", lambda request: {"sub": "u1", "roles": ["doctor"]})
    monkeypatch.setattr(app_module, "get_embedding", lambda question: None)
    monkeypatch.setattr(app_module, "get_chat_history", lambda **kwargs: [])
    monkeypatch.setattr(app_module, "save_chat_history", lambda **kwargs: None)
    monkeypatch.setattr(app_module.llm_client, "generate_response", fake_llm)

    def no_orchestration(**kwargs):
        raise AssertionError("help questions must not run the agent orchestration")

    monkeypatch.setattr(app_module, "_run_orchestration_plan", no_orchestration)
    client = TestClient(app_module.app)
    return client, captured


def _ask(client, question, **extra):
    return client.post(
        "/chat",
        json={"question": question, "mode": "assistant", **extra},
        headers={"Authorization": "Bearer test"},
    )


def test_how_to_question_containing_an_action_phrase_is_answered_from_the_guide(chat_client):
    client, captured = chat_client
    r = _ask(client, "How do I generate a bill for my patient?", page="/hospital/queue")
    assert r.status_code == 200
    assert "requires one of these roles" not in r.json()["answer"]
    assert "SYSTEM GUIDE" in captured["context"]
    assert "CURRENT PAGE: the user is on Queue & Flow" in captured["context"]
    assert "tutor for this app" in captured["instruction"]
    assert captured["max_tokens"] and captured["max_tokens"] < 1000


def test_unhandled_action_is_not_claimed_as_done(chat_client):
    client, captured = chat_client
    r = _ask(client, "discharge patient RH16-27 now")
    assert r.status_code == 200
    assert "You cannot do that from chat, and nothing has been done" in captured["instruction"]
    assert "Things the system does not do" in captured["context"]
    assert "FULL built-in ability" not in captured["instruction"]


def test_action_keywords_match_whole_words_only():
    import app as app_module

    detect = app_module._detect_action_intent
    # "ping the" used to match inside "typing the" and fire a WhatsApp send.
    assert detect("I keep typing the same examination for every patient") is None
    assert detect("what is the context the doctor gave?") is None
    assert detect("ping the lab about the sample") == "send_whatsapp"
    assert detect("text the nurse on duty") == "send_whatsapp"
    assert detect("send emails to finance about the audit") == "send_email"
