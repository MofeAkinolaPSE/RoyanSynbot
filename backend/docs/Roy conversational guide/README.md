# Roy conversational guide: how it is implemented

The notes in this folder (00–05 and `chatupgradecontext/`) are the research. This
page explains where it lives in code.

## Where things are

| What | File |
|---|---|
| **Roy Feature Guide**: every page, tab and button, by role. Roy reads it at chat time. | `backend/src/knowledge/roy_feature_guide.md` |
| Help-question detection, section selection, word budgets, voice rules | `backend/src/services/roy_guide.py` |
| Wiring into `/chat` | `backend/app.py` (`_classify_query_intent`, `_build_chat_instruction`, `chat`) |
| Tests, including a check that every sidebar page has a guide section | `backend/tests/test_roy_guide.py` |

The guide lives under `src/`, not here, because the Docker image only copies
`src/` and `.dockerignore` drops `*.md`. There is an explicit exception for
`src/knowledge/*.md`.

## How a question is handled

1. **Help question** ("how do I…", "where is the … button", "can I edit…", "is there a…").
   Roy skips the agents and action handlers and answers from the 3 best-matching
   guide sections, plus "What Roy can and cannot do" and "Things the system does
   not do". Pages outside the user's role are marked, so Roy says "that's not on
   your menu" instead of giving steps they can't follow. The page the user is on
   is sent from the chat bubble, so "how does this work?" is answered for that page.
2. **Action Roy can't do from chat** (discharge, order lab, book appointment,
   generate bill). Roy says plainly that nothing was done and gives the steps.
   Before this change these reached the model, which had been told it could do
   them, and it replied as if it had.
3. **Data and conversational questions** get the user's real page list, so any
   page Roy names exists, and full guide sections when the question clearly
   names a feature.

## Dynamic length

`response_budget()` sets a word range per question, states it in the prompt, and
caps tokens as a backstop. Reports are not capped.

| Question | Words |
|---|---|
| "thanks" | 3–30 |
| "how many…" (even when data is fetched) | 5–60 |
| "where is…" | 12–70 |
| "can I / is there…" | 10–80 |
| "how do I…" | 35–170 |
| "why / explain…" | 40–170 |
| report or list | 150–900 |

"Briefly" halves the range. "In detail" or "step by step" raises it by about 1.5×.

## Keeping it honest

When a page or button is added, renamed or removed, update
`roy_feature_guide.md` in the same change. Use the label exactly as it appears
on screen. If a sidebar page has no section, `test_every_sidebar_page_is_in_the_guide`
fails. Add the words staff actually used to the section's `keywords:` line. When
Roy says "I don't think we have that" about something that does exist, the fix
is a guide section, not a prompt change.
