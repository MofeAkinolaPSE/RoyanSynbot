# In-App Training — Implementation Plan

**Status:** All three tiers DONE (2026-08-24). Shipped for go-live, not deferred.
Video prompt pack delivered separately as `VIDEO_PROMPT_PACK.md`.
**Target:** usable before go-live Friday, with the deeper tiers landing after.

---

## Why in-app rather than video

A recorded walkthrough is stale the moment a screen changes — and we changed a great
many screens over the last week. The in-app tour is generated from `NAV_ITEMS`, the
same array that renders the sidebar, so it physically cannot drift out of sync or
show a page the viewer has no permission to open.

The video pack still has a job (the group session, and the "why" narrative). But the
thing staff will actually rely on at 2pm on a busy Tuesday is help that lives inside
the product.

---

## What already exists

Genuinely useful groundwork is in place:

| Piece | File | State |
|---|---|---|
| Role-filtered step builder | `client/lib/tour-config.ts` | Works. Filters `NAV_ITEMS` by `canViewByRoles` — same logic as the sidebar |
| Tour runner | `client/components/tour/TourProvider.tsx` | Dialog-based, navigates page to page, next/back/skip |
| Step renderer | `client/components/tour/TourStep.tsx` | Works |
| Progress persistence | `api.staff.updateTourState` | Stores `completed` / `skipped` / `current_step` |
| Trigger | `client/components/Layout.tsx:87` | Fires once on first login |

**The gap is content and reach, not architecture.**

---

## The three real problems

### 1. Two-thirds of the app is invisible to the tour
Only **19 of 51** nav entries have a `tourDescription`. `getTourStepsForRole()`
silently drops any entry without one, so most of the system is never introduced —
including several screens we built this month.

### 2. It runs exactly once, then is unreachable forever
`startTourIfNeeded` returns early if `completed` or `skipped` is set. There is no
"show me again". A nurse who skipped it on day one while a patient was waiting has
no way back. This is the single highest-value fix and it is small.

### 3. It orients, but never teaches a task
The current tour says *where* things are. It cannot say *how* to do the SOAP note,
which is the most-changed and least-familiar workflow in the system. Knowing the
Queue page exists does not tell a doctor why Plan is locked.

---

## Proposed design — three tiers

### Tier 1 · Orientation — ✅ DONE
*"Here are your pages and what each is for."*

- **All 42 tourable pages now have descriptions** (26 written, 18 rewritten). Coverage
  went 19/51 → 42/42. Each is 2-3 sentences: what the page is, what you do there, and
  where it matters, the caveat worth knowing.
- Descriptions carry the honest caveats inline — the allergy gap on Pharmacy, the
  verify gate on Lab, "search before you create" on Front Desk, "nursing notes are
  not gated" on Nursing Station.
- Step counter was **already implemented** in `TourStep.tsx` ("Step 3 of 11"). My
  original plan item was wrong; no work needed.

**Problem found while previewing, and fixed:** tour length was wildly uneven because
`getTourStepsForRole` selected on *role visibility*, which is not the same thing as
onboarding priority. Admin got **42 steps**, Ops 23, Nurse 19, Doctor 18 — long
enough that people skip, and skipping is sticky. Lab and Radiology got 3.

Added `tourEssential` to `NavItem`, marked the 13 daily-spine pages, and taught
`tour-config.ts` a rule that behaves at both extremes: **≤ 8 visible pages → show them
all** (a lab scientist's "full" tour is already short); **more → show the spine only**.
`getFullTourStepsForRole()` exposes the complete list for the replayable path.

Result: Doctor 9 · Nurse 10 · Admin 13 · Pharmacist 5 · Lab 3 · Management 11.

**Replay entry point — DONE.** Added `startTour(role, {full?})` alongside the existing
`startTourIfNeeded`, plus "Take the tour again" in the sidebar user menu (hidden when
a role has no tour). Deliberately a **separate method rather than a `force` flag**: the
first-run path resumes saved progress and writes back to it, while a replay always
starts at step one and writes nothing. Conflating them would mean someone re-watching
the tour silently rewound their own recorded progress.

### Tier 2 · Task walkthroughs — ✅ DONE
*"Do this with me, on a real screen."*

**Built:** `lib/walkthroughs.ts` (content), `components/tour/WalkthroughPlayer.tsx`
(spotlight runner), `components/tour/ShowMeHow.tsx` (launcher), and 18 `data-tour-id`
anchors across the SOAP composer, note list, addendum dialog, nursing panel, lab
workspace, front desk and pharmacy.

**All 7 walkthroughs written, 39 steps total.** Launcher is live on the SOAP composer;
adding it elsewhere is a one-line import per page.

Design decisions worth keeping:
- **Read-only by default.** The player points and explains; it never clicks, types or
  submits for the user. Staff rehearse against live clinical data, and a training tool
  that quietly writes to a patient record is worse than no training tool. The card
  carries a "Nothing is saved" badge.
- **Anchors are `data-tour-id`, not CSS selectors**, so a restyle cannot break a
  walkthrough.
- **Missing anchors degrade, never break.** If a step's element is on another tab the
  card still shows, minus the spotlight, with "That control is on another tab or
  screen — open it to see it highlighted."
- **`walkthroughs.spec.ts` guards the rot.** It fails if any anchor has no matching
  `data-tour-id`, if a `homeRoute` is not a real route in `App.tsx`, or if the
  patient-safety caveats (allergy, no-edit, verify gate) are ever edited out of the
  copy. It caught 12 unplaced anchors on first run, which is exactly its job.

Priority order, by how new and how risky the workflow is:

| # | Walkthrough | Role | Why it matters |
|---|---|---|---|
| 1 | **Writing a SOAP note** | Doctor | Most-changed screen. Covers gating, section templates, diagnosis auto-coding, staged orders, signing |
| 2 | **Correcting a signed note** | Doctor, Nurse | Staff will assume they are stuck. The addendum route must be discoverable *before* they need it |
| 3 | **Building your own template** | Doctor | The MD's own request. Highest compounding time-saving in the system |
| 4 | **Lab result → verify** | Lab | The verify gate is a safety control; staff must understand nothing reaches the doctor until they release it |
| 5 | **Register / find a patient** | Front desk | Duplicate MRNs are the most expensive mistake at that desk, and they are silent |
| 6 | **Dispensing a prescription** | Pharmacy | Queue states plus the allergy caveat |
| 7 | **Nursing note + flowsheet** | Nurse | Newly surfaced; nobody has seen these screens before |

**Effort:** moderate. Needs a step type that anchors to a DOM element rather than a
route. Suggest a `data-tour-id` attribute convention on target elements so
walkthroughs never depend on CSS selectors that a restyle would break.

### Tier 3 · Contextual help — ✅ DONE
*"What is this?"*

**14 hints, all mounted, in `client/lib/help-hints.ts` + `components/help/HelpHint.tsx`.**

Originally scoped as post-go-live. Brought forward once "training" became "we are
live on Friday": with no classroom window, the explanation has to be standing next
to the control at 9am on Friday, not waiting in a backlog.

**Popover, not tooltip.** A tooltip needs a hover, and a large share of this gets
read on a tablet at a bedside where there is no hover. Tap, click and keyboard all
work.

**Copy lives in a registry, not in JSX.** The same explanation appears on more than
one screen (an empty allergy list means the same thing everywhere), a reviewer can
read all of it in one file, and the safety-critical wording is pinned by a spec.

**Four are marked `safetyCritical`** — they render amber rather than muted, and
`help-hints.spec.ts` fails if their wording is softened:

| Hint | Guards against |
|---|---|
| `allergies-empty` | reading a blank list as a clearance |
| `note-signed-lock` | believing a signed note can be edited |
| `lab-verify-gate` | assuming an entered result reached the doctor |
| `pharmacy-allergy-warning` | reading a warning as a block, or as permission |

**The spec guards both directions** — a hint defined but never mounted is
documentation, not help; a mounted id with no registry entry renders nothing where
staff expect an explanation. Both fail the build.

#### A real fix found while doing this

The allergy cover-sheet widget read **`emptyLabel="No known allergies"`**. In
clinical use "no known allergies" is an assertion that someone asked and the
patient reported none. Nobody asked — Hope carried across **zero** per-patient
allergy records, so this rendered on effectively all 60,929 charts, telling every
clinician a negative finding that had never been established.

Changed to **"None recorded yet — ask the patient"**, with the safety-critical
hint beside it. This was a wording bug with a clinical edge, and it would have
gone live on Friday.

---

## Progressive framing — "growing with the system"

Rather than a separate curriculum, let the tiers carry the progression:

- **Week 1** — Tier 1 on first login. Complete one patient journey end to end. Do not optimise.
- **Weeks 2–3** — Tier 2 prompts appear for the workflows that role actually uses. This is when template-building lands, because it only makes sense once they have felt the repetition.
- **Month 2+** — Tier 3 answers the residual questions. Tour stays replayable for new starters and returning staff.

Optionally, a **"Training" entry in the user menu** listing that role's walkthroughs,
so nothing is ever locked behind a moment that has passed.

---

## Open question worth deciding: a practice patient

Staff will not want to rehearse on a real record — correctly, since signed notes
cannot be deleted. Options:

- **A. Designated practice patient** — one clearly-marked dummy record staff can
  freely use. Cheap. Risk: practice data mixed into live tables, and someone
  eventually books a real appointment against it.
- **B. Training mode flag** — writes suppressed or routed elsewhere. Clean, but
  touches every write path. Too large before Friday.
- **C. Do nothing** — walkthroughs are read-only and explicitly say "we won't save
  anything".

**Recommendation: C for go-live, A shortly after** with a loud visual marker on the
record. B is the right long-term answer but not a pre-go-live change to the clinical
write path.

---

## Suggested sequencing

**Before Friday**
1. Tier 1 content — 32 descriptions
2. Replay entry point + step counter
3. Tier 2 walkthrough #1 (SOAP note) and #2 (addendum) — the two that will otherwise
   generate the most support questions in week one

**Week after go-live**
4. Remaining Tier 2 walkthroughs, in the priority order above
5. Training menu listing available walkthroughs

**Ongoing**
6. ~~Tier 3~~ — done ahead of schedule, see above. What remains is *revising* it
   from real questions once staff are actually using the system.
7. Practice patient (option A)

---

## Honest caveats to build into the content

These will be asked, and answering them upfront buys credibility:

1. **Allergy records start empty.** Hope never held per-patient allergies. An empty
   list means *never recorded*, not *no allergies*. Must be stated in the pharmacy
   and doctor walkthroughs — it is a patient-safety point, not a footnote.
2. **Legacy documents are listed but cannot be opened** — see `DOCUMENT_RECOVERY.md`.
   Staff will click one. Say it first.
3. **The SOAP gate feels slow on day one.** Acknowledge it, show the Quick Note
   escape hatch for emergencies, explain why the gate exists.
4. **Signed notes cannot be edited by anyone** — not admin, not IT. Say it early and
   confidently; it is the claim most likely to be doubted and the one that matters
   most if a record is ever produced in court.
