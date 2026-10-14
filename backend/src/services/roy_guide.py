"""Roy's system guide, help-question routing and dynamic response length.

Roy used to answer "where is / how do I" questions from the model's imagination:
nothing in his prompt described the app's pages, tabs or buttons, so he guessed,
and the guesses read as fact. This module grounds those answers in
src/knowledge/roy_feature_guide.md, a hand-maintained map of the UI.

Everything here is in-process string work over a file read once at import, so
it adds no database calls and no network round trips to /chat. The only cost is
the prompt tokens of the few sections a question selects.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("roy_guide")

GUIDE_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "roy_feature_guide.md"

MAX_SECTIONS = 3
# Below this score a conversational question only *mentions* a feature in
# passing ("the queue is long today"), so the guide stays out of its prompt.
CONVERSATIONAL_ATTACH_SCORE = 2.5

# Sections pulled into every help answer: what Roy can do from chat, and the
# list of things the system does not do, which is what lets him say "no, we
# don't have that" instead of improvising a feature.
ALWAYS_IN_HELP = ("roy-capabilities", "not-available")


# ── Guide model ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GuideSection:
    id: str
    title: str
    menu: str
    routes: tuple[str, ...]
    roles: frozenset[str]          # empty = everyone
    keywords: tuple[str, ...]
    body: str
    _route_res: tuple[re.Pattern, ...] = field(default=(), compare=False, repr=False)

    def available_to(self, roles: Iterable[str]) -> bool:
        user_roles = {r.lower() for r in roles}
        return not self.roles or "admin" in user_roles or bool(self.roles & user_roles)

    def matches_route(self, path: str) -> bool:
        return any(rx.fullmatch(path) for rx in self._route_res)

    def render(self, roles: Iterable[str]) -> str:
        head = f"### {self.title}\nSidebar: {self.menu}"
        if not self.available_to(roles):
            # Steps are withheld, not just flagged: told "don't list the steps", the
            # model still listed them under "when you get access" while they sat in
            # its context.
            return (
                f"{head}\nACCESS: NOT available to this user. Their role cannot use it "
                f"(needs: {', '.join(sorted(self.roles))}). An administrator can grant access. "
                "Steps are not shown because this user cannot follow them."
            )
        return f"{head}\n{self.body}"


def _route_regex(route: str) -> re.Pattern:
    # "/hospital/patients/:mrn" -> r"/hospital/patients/[^/]+"
    parts = [("[^/]+" if p.startswith(":") else re.escape(p)) for p in route.split("/")]
    return re.compile("/".join(parts) + "/?")


def parse_guide(text: str) -> list[GuideSection]:
    sections: list[GuideSection] = []
    chunks = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    for chunk in chunks:
        title, _, rest = chunk.partition("\n")
        meta: dict[str, str] = {}
        lines = rest.split("\n")
        i = 0
        while i < len(lines) and lines[i].strip():
            key, sep, value = lines[i].partition(":")
            if not sep:
                break
            meta[key.strip().lower()] = value.strip()
            i += 1
        body = "\n".join(lines[i:]).strip()
        if "id" not in meta:
            logger.warning("Roy guide section %r has no id; skipped", title)
            continue
        routes = tuple(
            r.strip() for r in meta.get("route", "").split(",")
            if r.strip().startswith("/")
        )
        roles_raw = meta.get("roles", "everyone").lower()
        roles = frozenset() if roles_raw in {"", "everyone"} else frozenset(
            r.strip() for r in roles_raw.split(",") if r.strip()
        )
        sections.append(GuideSection(
            id=meta["id"],
            title=title.strip(),
            menu=meta.get("menu", ""),
            routes=routes,
            roles=roles,
            keywords=tuple(k.strip().lower() for k in meta.get("keywords", "").split(",") if k.strip()),
            body=body,
            _route_res=tuple(_route_regex(r) for r in routes),
        ))
    return sections


@lru_cache(maxsize=1)
def load_guide() -> tuple[GuideSection, ...]:
    try:
        return tuple(parse_guide(GUIDE_PATH.read_text(encoding="utf-8")))
    except Exception as exc:  # a missing guide must never take /chat down
        logger.error("Roy feature guide could not be loaded from %s: %s", GUIDE_PATH, exc)
        return ()


def _section(section_id: str) -> GuideSection | None:
    return next((s for s in load_guide() if s.id == section_id), None)


# ── Help-question detection ──────────────────────────────────────────────────

# UI nouns that turn an ambiguous "where is the …" into a navigation question.
# "Where is patient Adebayo?" stays a data question; "where is the discharge
# button?" is a help question.
_UI_NOUNS = (
    r"(page|tab|button|menu|sidebar|section|screen|setting|settings|option|form|"
    r"link|feature|module|dashboard|panel|icon|field|template|walkthrough)"
)

_HELP_PATTERNS = re.compile(
    r"|".join([
        r"\bhow (do|can|would|should) (i|we|you|one)\b",
        r"\bhow to\b",
        r"\bhow does (the|this|a)\b",
        r"\bwhere (do|can|would|should) (i|we)\b",
        r"\bwhere('?s| is| are) (the|my|our)\b.*\b" + _UI_NOUNS,
        r"\b(which|what) (page|tab|button|menu|screen|section)\b",
        r"\bwhat does (the|this)\b.*\b" + _UI_NOUNS + r"\b.*\bdo\b",
        r"\bwhat is the\b.*\b" + _UI_NOUNS + r"\b.*\bfor\b",
        r"\b(show|teach|walk) me( through)?\b",
        r"\bshow me how\b",
        r"\bguide me\b",
        r"\bsteps? (to|for)\b",
        r"\bis there (a|an|any) (way|page|button|feature|option|place|screen|tab|report|function)\b",
        r"\b(does|do) (the|this|our) (system|app|platform|software|roy|synbot)\b",
        r"\bdo we have (a|an|any)\b.*\b(page|feature|module|button|option|function|screen|report)\b",
        r"\bcan (i|we|you) (still )?(edit|delete|undo|change|unsign|cancel|reverse|amend|correct)\b",
        # "I"/"we" only: "can you create a task" is a request for Roy to act, not a how-to.
        r"\b(can|could) (i|we) (create|make|save|build|add|share|set up|customi[sz]e)\b",
        r"\b(i )?(can'?t|cannot|couldn'?t|unable to) (find|see|locate|open|access)\b",
        r"\bi('?m| am) (lost|stuck|new here)\b",
        r"\bwhat can you do\b",
        r"\bis there (a|an) (faster|quicker|easier|better|simpler|shorter) way\b",
        r"\b(faster|quicker|easier) way to\b",
        r"\bwhat (pages|modules|features) (do i|can i)\b",
    ]),
    re.IGNORECASE,
)


def is_help_question(question: str) -> bool:
    """True when the user wants to know how to use the app, not what the data says."""
    return bool(_HELP_PATTERNS.search(question or ""))


# ── Section selection ────────────────────────────────────────────────────────

_WORD_RE_CACHE: dict[str, re.Pattern] = {}
_STOP = frozenset({"a", "an", "the", "to", "of", "in", "on", "for", "my", "i", "is", "it", "and", "or"})


def _word_in(text: str, word: str) -> bool:
    rx = _WORD_RE_CACHE.get(word)
    if rx is None:
        rx = _WORD_RE_CACHE[word] = re.compile(r"\b" + re.escape(word) + r"(s|es|ed|ing)?\b")
    return bool(rx.search(text))


def _keyword_weight(text: str, keyword: str) -> float:
    """1 for a single word, more for a longer (more specific) phrase. A phrase
    whose words all appear, but not side by side, earns most of its weight:
    "a mistake in a signed note" should still find "signed note"."""
    words = [w for w in re.split(r"[\s/]+", keyword) if w]
    full = 1.0 + 0.75 * (len(words) - 1)
    if len(words) == 1:
        return full if _word_in(text, keyword) else 0.0
    if keyword in text:
        return full
    content = [w for w in words if w not in _STOP]
    # Scattered words only count when at least two of them carry meaning: "to do" has one ("do"),
    # which matched every "how do I ..." question and pulled them all towards My Workspace.
    if len(content) >= 2 and all(_word_in(text, w) for w in content):
        return 0.7 * full
    return 0.0


def score_sections(question: str, page: str | None = None) -> list[tuple[float, GuideSection]]:
    text = " ".join(re.sub(r"[^\w&'\- ]", " ", (question or "").lower()).split())
    scored: list[tuple[float, GuideSection]] = []
    for sec in load_guide():
        score = 0.0
        for kw in sec.keywords:
            score += _keyword_weight(text, kw)
        if page and sec.matches_route(page):
            score += 1.5
        if score > 0:
            scored.append((score, sec))
    scored.sort(key=lambda x: -x[0])
    return scored


def page_section(page: str | None) -> GuideSection | None:
    if not page:
        return None
    return next((s for s in load_guide() if s.matches_route(page)), None)


def sanitize_page(page: object) -> str | None:
    if not isinstance(page, str):
        return None
    page = page.split("?")[0].split("#")[0].strip()
    if not page.startswith("/") or len(page) > 200 or not re.fullmatch(r"[\w/\-:.]*", page):
        return None
    return page


def build_guide_context(
    question: str,
    roles: Iterable[str],
    page: str | None = None,
    *,
    help_mode: bool = True,
    extra_ids: Iterable[str] = (),
) -> str:
    """The SYSTEM GUIDE block for the prompt.

    Help questions get the matching sections in full. Other questions get full
    sections only on a strong match, but always get the user's page list, so
    when a data answer says "see it on …" the page named is a real one (Roy once
    sent a nurse to a "Patient Flow page" that does not exist)."""
    roles = set(roles or ())
    scored = score_sections(question, page)
    if not help_mode:
        scored = [x for x in scored if x[0] >= CONVERSATIONAL_ATTACH_SCORE]

    chosen: list[GuideSection] = [s for _, s in scored[:MAX_SECTIONS]]
    here = page_section(page)
    if help_mode and here and here not in chosen and not scored:
        # Vague question ("how does this work?") on a known page: teach the page.
        chosen.append(here)
    wanted_extra = list(extra_ids) + (list(ALWAYS_IN_HELP) if help_mode else [])
    for sid in wanted_extra:
        sec = _section(sid)
        if sec and sec not in chosen:
            chosen.append(sec)

    parts = [
        "SYSTEM GUIDE: the source of truth for what exists in this app and where it is. "
        "Pages, tabs and buttons not listed here must not be presented as existing."
    ]
    if here:
        parts.append(f"CURRENT PAGE: the user is on {here.title} ({page}).")
    parts.extend(sec.render(roles) for sec in chosen)

    menu = [
        f"- {s.menu}" for s in load_guide()
        if s.routes and s.menu and s.menu != "none" and s.available_to(roles)
    ]
    if menu:
        parts.append(
            "PAGES ON THIS USER'S MENU:\n" + "\n".join(dict.fromkeys(menu))
        )
    return "\n\n".join(parts)


# ── Dynamic response length ──────────────────────────────────────────────────

@dataclass(frozen=True)
class ResponseBudget:
    min_words: int
    max_words: int
    label: str

    @property
    def max_tokens(self) -> int:
        # ~1.3 tokens per English word plus markdown/number overhead; the
        # headroom means the cap only bites on a runaway answer, never mid-step.
        return int(self.max_words * 1.7) + 80

    def instruction(self) -> str:
        return (
            f"LENGTH: this is a {self.label}. Aim for {self.min_words} to {self.max_words} words and never "
            f"exceed {self.max_words}. The upper number is a ceiling, not a target: if the honest answer is "
            "a sentence, give a sentence. Do not pad, but do not drop a step or the one reason the user "
            "needs in order to act. "
        )


_SMALL_TALK = re.compile(
    r"^(hi|hello|hey|good (morning|afternoon|evening)|thanks|thank you|thx|ok(ay)?|cool|great|"
    r"nice|bye|goodbye|how are you|you there)\b[\s\w!.,?']{0,25}$",
    re.IGNORECASE,
)
_SHORTER = re.compile(
    r"\b(briefly|brief|quick(ly)?|short(ly)?|in short|one line|one sentence|tl;?dr|just tell me|"
    r"in a word|summari[sz]e it)\b",
    re.IGNORECASE,
)
_LONGER = re.compile(
    r"\b(in detail|detailed|elaborate|explain (fully|everything|in depth)|step[- ]by[- ]step|"
    r"walk me through|everything about|full explanation|thoroughly)\b",
    re.IGNORECASE,
)
_YES_NO_START = re.compile(
    r"^(is|are|does|do|did|can|could|has|have|was|were|will|should|am)\b", re.IGNORECASE
)
_HOW_TO = re.compile(
    r"\b(how (do|can|would|should|to)|steps?|walk me|show me how|set up|setup|process for)\b",
    re.IGNORECASE,
)
_WHERE = re.compile(r"\b(where|which (page|tab|button|menu)|find|locate)\b", re.IGNORECASE)
_WHY = re.compile(
    r"\b(why|explain|difference between|compare|what happens|reason)\b", re.IGNORECASE
)
_LIST_ASK = re.compile(
    r"\b(report|list|breakdown|summary|summari[sz]e|table|by (ward|department|doctor|day|month)|each)\b",
    re.IGNORECASE,
)
_COUNT = re.compile(r"\b(how many|how much|what time|when (is|was|did)|what is the (total|number))\b",
                    re.IGNORECASE)


def response_budget(question: str, intent: str) -> ResponseBudget:
    """How long this reply should be, from the shape of the question.

    The model is bad at judging length on its own: with one fixed "1 to 3
    sentences" rule, how-to answers lose their steps and yes/no answers still
    get a paragraph. The budget is set per question and stated explicitly.
    """
    q = (question or "").strip()

    if intent == "report" and _COUNT.search(q) and not _LIST_ASK.search(q):
        # Data is fetched as for a report, but a count is answered with the number.
        budget = ResponseBudget(5, 60, "direct factual answer")
    elif intent == "report":
        budget = ResponseBudget(150, 900, "structured report")
    elif _SMALL_TALK.match(q):
        return ResponseBudget(3, 30, "quick social reply")
    elif intent == "guide":
        if _HOW_TO.search(q):
            budget = ResponseBudget(35, 170, "how-to answer with steps")
        elif _YES_NO_START.match(q):
            budget = ResponseBudget(10, 80, "yes/no answer about the system")
        elif _WHERE.search(q):
            budget = ResponseBudget(12, 70, "where-to-find answer")
        else:
            budget = ResponseBudget(20, 120, "explanation of a feature")
    elif _COUNT.search(q):
        budget = ResponseBudget(5, 50, "direct factual answer")
    elif _WHY.search(q):
        budget = ResponseBudget(40, 170, "explanation")
    elif _YES_NO_START.match(q):
        budget = ResponseBudget(5, 60, "yes/no answer")
    else:
        budget = ResponseBudget(15, 100, "conversational answer")

    lo, hi = budget.min_words, budget.max_words
    if _SHORTER.search(q):
        lo, hi = max(3, lo // 2), max(25, hi // 2)
    elif _LONGER.search(q):
        lo, hi = int(lo * 1.3), int(hi * 1.6)
    if len(q.split()) > 40:  # a long, multi-part question deserves room
        hi = int(hi * 1.25)
    return ResponseBudget(lo, hi, budget.label)


# ── Prompt blocks ────────────────────────────────────────────────────────────

# Roy's voice. Distilled from docs/Roy conversational guide (ACE behaviour and
# grounding notes): answer first, honest evidence states, no assistant filler.
ROY_VOICE = (
    "HOW YOU TALK: Put the answer in your first sentence. Do not restate the question. Never open with "
    "'Certainly', 'Absolutely', 'Great question', 'I'd be happy to', 'Based on the information provided' "
    "or 'As an AI', and never close with 'I hope this helps' or 'Let me know if you need anything else'. "
    "After the answer, add only the support the user needs: the reason, the evidence or the steps. Add a "
    "next step only when there is one. "
    "Match the reader: with doctors and nurses be clinical and concise, at the front desk give plain steps, "
    "for finance put the numbers first, for administrators be precise about source and status. "
    "Never blur what the records show with what you are estimating. "
    "An empty field is missing data, not a negative fact: say 'no allergy is recorded', never 'the patient "
    "has no allergies'. If a lookup failed or returned nothing, say in one sentence that you could not "
    "confirm it, never that the thing does not exist, and point to the page where they can see it live. "
    "Never mention 'the context', 'the profile', tools, agents, prompts or internal names such as "
    "patient_flow_agent. "
    "Ask one short clarifying question only when two readings would change the answer (for example, two "
    "patients with the same name). Otherwise take the obvious reading and answer. Use the recent "
    "conversation to resolve 'that patient', 'the second one' or 'his bill'. "
)

# What Roy can actually execute from chat. Keep in step with the handlers wired
# in app.py's _ACTION_DISPATCH (CHAT_EXECUTABLE_ACTIONS below).
CHAT_EXECUTABLE_ACTIONS = frozenset({
    "send_email", "send_whatsapp", "schedule_meeting", "create_task",
    "generate_report", "trigger_replenishment",
})

ROY_CAPABILITIES = (
    "WHAT YOU CAN DO FROM CHAT: send internal emails (you show a draft and the user confirms), send "
    "WhatsApp messages, schedule meetings, create tasks, generate reports and trigger stock "
    "replenishment. Do these when asked, and do not claim you can't. Everything else, including "
    "prescribing, ordering labs or imaging, discharging, admitting, triaging, booking appointments, "
    "generating bills, taking payments and signing notes, is done by the user on its page. You cannot do "
    "those from chat. Never say or imply that you did one. Give the exact steps from the SYSTEM GUIDE "
    "instead. "
)

GUIDE_INSTRUCTION = (
    "The user is asking how to use the system: where something is, how to do a task, or whether a "
    "feature exists. Act as their tutor for this app. "
    "Answer only from the SYSTEM GUIDE in the context. It is the source of truth for pages, tabs and "
    "buttons. "
    "Give the sidebar path first (for example: Sidebar > Diary > Appointments). Write page, tab and "
    "button names in **bold**, exactly as the guide spells them. "
    "For a task with more than two actions, use short numbered steps, one per line, each starting with a "
    "verb. Do not use headings. "
    "For 'where is …', answer in one or two lines: the menu path and the button. "
    "For 'can I …', 'is there …' or 'do we have …', start with Yes or No. "
    "If the feature is marked NOT available to this user, or the guide says it is for roles the user does not "
    "have, answer in one or two sentences: say it is not available to them, say who does it, and say an "
    "administrator can grant access. Do not list the steps, not even as 'if you get access'. "
    "If the guide does not cover what they asked, say so honestly, for example: 'I don't think we have that "
    "in the system. I can't find it on any page.' Then point to the closest thing the guide does have, or "
    "suggest asking an administrator. Never invent a page, tab, button, menu item, shortcut or setting, and "
    "never describe how a feature 'would' work. "
    "If the guide mentions a 'Show me how' or 'Help' walkthrough for the task, add one short line at the "
    "end pointing to it. "
    "If a CURRENT PAGE is given and is relevant, speak from it: 'On this page, click …'. Say this once; do "
    "not repeat a step you have already given. "
    "Speak as someone who knows the app. Never mention 'the guide', 'the system guide', 'the context' or "
    "'documentation', and refer to yourself as 'I', never 'Roy'. Mention what you cannot do from chat only "
    "when the user asked you to do it. Add nothing the guide does not say, such as which other roles do a "
    "step. "
)

CONVERSATIONAL_GUIDE_NOTE = (
    "The context includes a SYSTEM GUIDE excerpt listing the pages on this user's menu. If you point the user "
    "to a page, tab or button, use only names that appear in the SYSTEM GUIDE, spelled the same way, in "
    "**bold**. Never invent a page or button name. "
)


def unsupported_action_instruction(action_type: str) -> str:
    label = action_type.replace("_", " ")
    return (
        f"The user asked you to {label} for them from chat. You cannot do that from chat, and nothing has "
        "been done. Say so in one short sentence without apologising at length, then give the exact steps "
        "from the SYSTEM GUIDE for them to do it themselves. Never say or imply the action was carried out. "
    )
