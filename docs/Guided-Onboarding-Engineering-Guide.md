# Guided Onboarding: Welcome Tour and "Show me how"

**Engineering design guide for adding in-app training to a web application**

This guide explains how we designed two connected training features. It is written so another team can build them
in any product and stack. The examples use React and TypeScript, but the ideas carry over to other stacks.

| Feature | Question it answers | When it runs |
|---|---|---|
| **Welcome tour** ("your day") | *What does my working day look like in this system?* | Once, on a person's first sign-in. It can be replayed. |
| **Show me how** (walkthroughs) | *How do I serve one customer / patient / case through this part of the system?* | On demand, from a button on the page it teaches. |

---

## 1. Principles

These are the rules that shaped every decision below. If you remember nothing else, remember these.

1. **Teach the job, not the menu.** A list of pages ("this is Reports, this is Settings") teaches nothing. A tour
   should follow the order the work happens in a typical day for that role. A walkthrough should follow one case
   (a customer, a patient, an order) through a department, from arrival to hand-off.
2. **Train on the real screen.** Steps run over the live page, not on screenshots or a separate sandbox. The
   learner sees exactly what they will use tomorrow.
3. **Never let training change real data.** Any control that commits something to a record (save, sign, approve,
   pay, dispense, submit) is highlighted but marked "look, do not press". Only harmless controls are clickable
   during training.
4. **Learn by doing.** Where it is safe, a step moves on when the learner presses the highlighted control, rather
   than when they read and press Next.
5. **Content is data, checked by tests.** Tours and walkthroughs are plain data files. Automated tests stop them
   drifting from the product: missing anchors, pages a role cannot open, unsafe steps.
6. **One source of truth for access.** Training never shows a page the person cannot open. It uses the same
   permission rules as the navigation menu.
7. **Fail softly.** If a highlighted element is not on screen (the panel isn't open, the layout changed), the step
   still shows its explanation and the learner can continue. Training never gets stuck.

---

## 2. Architecture overview

```text
                      ┌────────────────────────────┐
  Navigation config ──►  Access rules (who sees    │◄── used by the sidebar AND both training features
  (pages, roles)      │  which page)               │
                      └─────────────┬──────────────┘
                                    │
          ┌─────────────────────────┴──────────────────────────┐
          ▼                                                     ▼
┌───────────────────────┐                         ┌─────────────────────────────┐
│ Day scripts (data)     │                         │ Walkthrough scripts (data)  │
│ role -> ordered steps  │                         │ id -> steps with anchors     │
└──────────┬────────────┘                         └──────────────┬──────────────┘
           ▼                                                      ▼
┌───────────────────────┐   first sign-in /       ┌─────────────────────────────┐
│ TourProvider          │◄── "Take the tour again"│ WalkthroughProvider + Player │◄── "Show me how" button
│ floating card,        │                         │ spotlight, click-to-advance, │    placed on each page
│ opens each step's page│                         │ safety states                │
└──────────┬────────────┘                         └──────────────┬──────────────┘
           ▼                                                      ▼
   Progress saved per user                           Anchors: data-tour-id="..." on
   (completed / skipped / step)                      the real UI elements
```

**Modules to build**

| Module | Responsibility |
|---|---|
| `nav-config` | Pages, their routes and the roles allowed to see them (you probably have this already). |
| `nav-access` | `canView(roles, route)`. It is shared by the sidebar, route guards and training. |
| `day-tours` (data) | One "typical day" script per role. |
| `walkthroughs` (data) | One script per task or customer journey. |
| `TourProvider` | Runs the welcome tour, saves progress, and handles replay. |
| `WalkthroughProvider` | Holds the active walkthrough, its step, and whether it is minimised. |
| `WalkthroughPlayer` | Draws the spotlight and the step card, detects clicks, and navigates. |
| `ShowMeHow` | The button placed on a page; it lists the walkthroughs available to the person. |
| Tests | Keep the scripts honest (section 8). |

---

## 3. Data model

### 3.1 Welcome tour: a day script

```ts
export type DayStep = {
  title: string;      // what this part of the day is: "Check a customer in"
  href: string;       // the page this step opens
  body: string;       // one or two sentences: when in the day, and why
  points?: string[];  // what to press there, in order, using the exact on-screen names
};

// One script per role. A role with no script falls back to "pages this role can see".
export const DAYS: Record<string, DayStep[]> = {
  front_desk: [ /* rooms -> check-in -> new records -> bookings -> ... */ ],
  manager:    [ /* the whole system, one stop per core area */ ],
};
```

Design notes:

- **Steps are ordered by the day, not by the menu.** Example for a front desk: get set up in the morning, serve
  the first customer, handle exceptions, end-of-day tasks.
- **Managers and executives get a whole-system tour**: one stop per core area, each stop saying what to look at
  there. Administrators get the manager tour plus administration (users, audit, system health).
- **Shared closing steps** (your own workspace, where to get help) are defined once and reused across roles.
- **Use 6–10 steps for a front-line role and up to about 15 for a whole-system tour.** Above that, people skip.

### 3.2 Show me how: a walkthrough

```ts
export type WalkthroughStep = {
  title: string;               // the action: "Search for the customer first"
  body: string;                // where, what to press, what happens next
  anchor?: string;             // data-tour-id of the element to highlight; omit for a text-only step
  navigateTo?: string;         // route to open before showing the step (journeys cross pages)
  action?: "click" | "observe";// click = the step advances when the learner presses the control
  caution?: boolean;           // the control commits a real action: amber highlight, never clickable
  cue?: string;                // a short instruction: "Click in the search box"
};

export type Walkthrough = {
  id: string;
  title: string;               // "Serving a customer at the front desk"
  summary: string;             // one line, shown in the Show me how menu
  roles?: string[];            // who it is offered to (undefined = everyone)
  homeRoute?: string;          // the page whose Show me how button offers it
  estMinutes: number;
  steps: WalkthroughStep[];
};
```

### 3.3 Two kinds of walkthrough

| Kind | Shape | Example |
|---|---|---|
| **Journey** (the main kind) | Follows one case through a department, crossing pages with `navigateTo`. | "Serving a patient at the pharmacy": the prescription arrives, you check what is filled in, dispense, handle held items, check stock. |
| **Task** | One focused procedure on one screen. | "Correcting a signed record", "Creating your own template". |

There is also one **end-to-end journey** for managers. It follows a single case through every department in order,
so leadership sees how the whole system fits together.

### 3.4 Anchors

Highlight targets are marked in the UI with a stable attribute:

```tsx
<button data-tour-id="checkout-record-payment">Record Payment</button>
<div data-tour-id="frontdesk-rooms"><RoomBoard /></div>   // wrap a component you can't edit
```

Use `data-tour-id` rather than CSS classes or DOM paths. That way a redesign cannot silently break a walkthrough,
and the tests can find every anchor in the source code.

---

## 4. Welcome tour: behaviour

### 4.1 When it starts

- On **first sign-in**, for every account. That includes accounts created by an administrator, not only people who
  completed a sign-up form. This is easy to get wrong: if the tour only runs after a profile-setup screen, users
  created by an administrator never see it.
- Do not start it if the saved state says `completed` or `skipped`.
- **Replay:** add a "Take the tour again" entry in the user menu. A replay never overwrites the saved state.

```ts
type TourState = { completed?: boolean; skipped?: boolean; current_step?: number }; // stored per user, server side
```

Saving `current_step` lets a person who closes the browser halfway resume where they left off.

### 4.2 Which role's tour

People often hold several roles. Pick one with an explicit priority list, ordered from most senior or broadest to
most specific:

```ts
const PRIORITY = ["admin", "manager", "specialist", "front_desk", /* ... */ "read_only"];
export const primaryTourRole = (roles: string[]) =>
  PRIORITY.find((r) => roles.includes(r)) ?? roles[0] ?? "viewer";
```

Never use `roles[0]`. Its order is arbitrary, and a chief could get the cashier's tour.

### 4.3 Presentation

- **Use a floating card in a corner, not a modal.** A modal hides the page the step is about. The card leaves the
  page usable, so people can try things as they read.
- **Each step opens its page** (navigate to `href` when the step changes), so the real screen is behind the card.
- The card shows:
  - a progress bar;
  - "Step 3 of 8 · *Page name*" (the page name teaches where things live);
  - the step title, the body, and the `points` as a checklist;
  - Skip / Back / Next / Finish.
- Make the content area scroll inside the card (cap it at about 55% of the viewport height), so long steps never
  push the buttons off screen.
- Give it `role="dialog"`, `aria-modal="false"`, an `aria-label`, and a close button with an accessible name.

### 4.4 Safety net

At render time, drop any step whose page the role cannot open (`canView(role, step.href)`). The tests should also
catch this. The runtime filter means a permission change can never send someone to a page they will be bounced
from.

---

## 5. Show me how: behaviour

### 5.1 The button

- Place `<ShowMeHow only={[...ids]} />` next to the page title of each page it teaches.
- Offer every walkthrough that **any** of the person's roles may use, not just their first role.
- With one walkthrough available, show a single button. With several, show a dropdown listing the title, the
  one-line summary, and "N min · N steps".

### 5.2 The player

**Spotlight.** Draw four dimmed panels around the target, rather than one overlay with a hole. Nothing sits on top of
the target, so it stays fully readable and clickable. Make the panels `pointer-events: none` so the page can still
be scrolled and used.

**Highlight ring.** Add a ring around the target and a gentle pulse that stays in place: animate opacity or a
shadow. Do **not** use a scale animation such as a "ping" effect. On wide elements, scaling draws a large rectangle
offset from the target.

**Step card.** Position the card next to the target, flipping above or below to fit the viewport. Keep a fixed
width (about 420px, capped at the viewport width minus a margin).

- **Header (one line):** "*walkthrough name* · step 2 of 7". The name is truncated if long, and the line doubles
  as a button that opens the step list. Below it, the step title.
- **Body:** readable size (14px).
- **Cue box:**
  - **Click step:** blue, with a pointer icon, the cue text and "show me", which scrolls to the target and pulses
    it.
  - **Caution step:** amber, "Look, do not press." plus the cue.
  - **Observe step:** neutral, an eye icon and the cue.
- **Missing anchor:** if the target isn't on screen, show "That control is not on screen right now — open the tab or
  screen it lives on and it will light up."
- **Footer:**
  - a short note: "You are on the real page: safe clicks only — nothing is saved unless you save it";
  - Back, and Next / Skip / Done.
  - Let the note wrap. Keep the buttons from shrinking, so nothing overflows the card.

**Controls.** Minimise (keeps your place), close, and the step list to jump to any step.

**Navigation.** When a step has `navigateTo`, navigate once on entering the step (keyed by step index), then measure
the anchor after the page settles. Re-measure on scroll and resize.

### 5.3 Click to advance

For `action: "click"` steps, attach a one-time click listener to the anchor element. When the learner presses it,
advance to the next step. The Next button reads **Skip** on these steps, so nobody is ever stuck.

### 5.4 The safety model

| Step type | Highlight | Clickable? | Card says |
|---|---|---|---|
| `observe` (default) | Blue | No auto-advance | Neutral cue |
| `click` | Blue, pulsing | Yes, and the step advances on press | "Click …" |
| `caution` | **Amber** | **Never** | "Look, do not press. This commits a real action." |

Rules, enforced by tests:

- `caution` is always `observe`.
- Every control that commits to a record has `caution` set.
- A `click` step must have an anchor and a cue.

Training happens on live data, so this table is the core safety mechanism of the whole feature.

---

## 6. Writing the content

### 6.1 Copy rules

- **The title says what to do:** "Search for the customer first", not "Search".
- **The body says where, what to press and what happens next,** in one or two short sentences. Keep a reason only
  when it changes behaviour (safety, legal, avoiding duplicates).
- **Name controls exactly as they appear on screen,** including capitalisation: "Record Payment", not "the payment
  button".
- **Write the hand-off into journeys:** where the case goes next and who takes it from there. That is what makes it
  a journey and not a page tour.
- **Put safety-critical caveats in the text, word for word,** and test for them. For example: "an empty allergy
  list does not mean the patient has none", or "a result is not visible until it is verified".

### 6.2 How to design a journey

1. Walk the real process with the team: where does the case arrive, and what makes it the team's turn?
2. List the screens in the order they are used.
3. For each screen, list what the person does: the safe clicks and the committing actions.
4. Add the exceptions they meet daily (held items, missing information, corrections).
5. End with the hand-off: where the case goes next.
6. Mark every committing control as `caution`.
7. Add `data-tour-id` anchors for each highlighted element.

### 6.3 Keep three sources in step

If the product also has an AI assistant or a help centre, its knowledge base should describe the same tasks with the
same control names. Put a comment at the top of each data file naming the other two, and update all three whenever
the UI changes.

---

## 7. Integration checklist

- [ ] One access function (`canView`) used by the sidebar, route guards and both training features.
- [ ] Per-user tour state on the server: `completed`, `skipped`, `current_step`, plus a PATCH endpoint.
- [ ] The tour starts on first sign-in for every account, after authentication and once the profile is loaded.
- [ ] `primaryTourRole()` with an explicit priority list.
- [ ] "Take the tour again" in the user menu (replay never writes state).
- [ ] `TourProvider` (a floating card that navigates to each step) mounted inside the router.
- [ ] `WalkthroughProvider` and `WalkthroughPlayer`, rendered in a portal on the document body.
- [ ] A `ShowMeHow` button on each page that has a walkthrough.
- [ ] `data-tour-id` anchors on every highlighted element.
- [ ] An optional admin "Preview onboarding as role X" panel, to review each role's tour without new accounts.
- [ ] Tests (section 8) run in CI.

---

## 8. Tests that keep it honest

Training content goes stale silently. These checks catch it in CI:

| Test | Catches |
|---|---|
| Every walkthrough anchor exists as `data-tour-id="…"` somewhere in the source | A step that highlights nothing after a UI change. |
| Every `homeRoute` / `navigateTo` is a real route | A button that never appears, or navigation to nowhere. |
| Every role on the access page has a day script | New roles getting a generic or empty tour. |
| Every day step's page is viewable by that role | A tour that bounces people off pages. |
| The tour shown equals the day script (not the page list) | A fallback silently replacing the scripted tour. |
| `caution` steps are never `click` | Inviting trainees to commit real actions. |
| The named committing anchors are `caution` + `observe` | A lost caution flag on a sign / pay / submit control. |
| Every `click` step has an anchor and a cue | A step the learner cannot complete. |
| Every anchored walkthrough has at least one `click` step | A walkthrough that is a slideshow. |
| Required safety phrases are present in specific walkthroughs | A rewrite that drops a safety caveat. |
| Steps have a meaningful title (more than 5 characters) and body (more than 30) | Placeholder or one-word steps. |
| A person with every role can see every page | Role combinations taking access away. |
| Multi-role → priority role (`["cashier","manager"]` → `manager`) | The wrong tour for senior staff. |

Anchor test sketch:

```ts
const source = readAllSourceFiles("src");            // every .ts/.tsx except tests
const missing = WALKTHROUGHS.flatMap((w) =>
  w.steps.filter((s) => s.anchor && !source.includes(`data-tour-id="${s.anchor}"`))
         .map((s) => `${w.id} -> ${s.anchor}`));
expect(missing).toEqual([]);
```

---

## 9. Pitfalls we hit

| Pitfall | Fix |
|---|---|
| The tour only started after a sign-up form, so administrator-created users never saw it | Start it on the first authenticated load whenever the state isn't completed or skipped. |
| The tour picked `roles[0]`, so senior multi-role staff got a junior role's tour | Use an explicit priority list. |
| The "Show me how" list only checked the first role | Offer walkthroughs for any of the person's roles. |
| The tour was a list of pages in menu order | Script a typical day per role. |
| A modal tour hid the page being explained | Use a floating card, and navigate to each step's page behind it. |
| A scale ("ping") pulse drew an oversized box offset from wide targets | Pulse opacity or shadow in place. |
| A long walkthrough title wrapped the header; a badge pushed buttons off the card | One-line truncated header; the footer note wraps and the buttons don't shrink. |
| The content described the old UI after a redesign | Data files, anchor tests, and the three-sources rule (section 6.3). |
| Anchors on elements inside closed panels | Accept a graceful text-only step; say which tab or panel to open. |

---

## 10. Suggested build order

1. **Shared access function, and anchors on two or three key elements.**
2. **Walkthrough player** with one task walkthrough, covering spotlight, card, click-to-advance, caution states and
   the missing-anchor fallback.
3. **The test suite (section 8)**, before writing more content.
4. **Department journeys:** one per team, written with that team.
5. **Welcome tour:** day scripts per role, the floating card, saved state, and replay.
6. **Manager end-to-end journey** and the admin preview panel.
7. **Content review with real users:** watch two or three people per role use it, then fix the copy.
