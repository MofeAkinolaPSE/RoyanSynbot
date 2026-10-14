# Training Video Prompt Pack — Royan Hospital / Synbot

Prompts for generating role-based onboarding videos. Written to be pasted into a
video generation tool (Synthesia, HeyGen, Descript, Runway) or handed to whoever
records the screen, with minimal editing.

**Scope note.** These videos are the *supporting* layer. The primary training is
in the app: the role tour on first login, and seven "Show me how" walkthroughs on
the screens they teach. Videos cover what a walkthrough cannot — the *why*, the
change from Hope, and the tone. Do not duplicate the walkthroughs step for step;
point at them instead.

**Total runtime: ~24 minutes across 6 videos.** Nobody watches a 40-minute system
video. Each of these is short enough to re-watch before a shift.

---

## Rules that apply to every video

Paste this block ahead of any individual prompt below.

```
STYLE AND CONSTRAINTS

Audience: hospital staff at Royan Hospital, Lagos, Nigeria. Mixed comfort with
computers. Many have used the previous system ("Hope") for years, some for a
decade. They are not beginners at their job. They are beginners at this software
only. Never talk down to them.

Tone: calm, direct, collegial. A competent colleague showing you around, not a
salesperson and not a lecturer. Short sentences.

Language: British/Nigerian English spelling. Naira as the currency. Say
"theatre" rather than "operating room".

Pace: slow enough to follow a click. Pause after each action.

Do NOT:
- promise features that do not exist
- say "simply", "just", or "easy" — if it were easy there would be no video
- show fake data realistic enough to be mistaken for a real record
- use a real patient name, hospital number, phone number or photograph

DO:
- use obviously fictional patients, e.g. "TEST PATIENT — TRAINING"
- state plainly when an action is permanent
- name each screen out loud on arrival, so viewers can find it later
- end by pointing at the "Show me how" button on that screen
```

---

## Video 1 — "What has changed, and what has not" (3 min, everyone)

Watched once, by all staff, before their role video.

```
Create a 3-minute orientation video for hospital staff moving from their old
system ("Hope") to a new one ("Synbot").

Open by addressing the real anxiety directly, within the first fifteen seconds:
"Your patients' history did not disappear. It is all here."

Cover, in this order:

1. THE RECORD CAME WITH US. Years of visits, results, notes, bills and
   admissions were carried across. If a patient was seen here before, their
   history is on their chart. Show a chart with history going back several
   years. This is the most important message in the video — some staff are
   quietly assuming they are starting from zero, and will not say so.

2. WHAT IS GENUINELY NEW: notes are written in a set order and are signed. Once
   signed they cannot be edited by anyone, and corrections are added underneath
   as an addendum. Say clearly that this protects staff rather than polices
   them: a record that cannot be quietly altered is a record that defends you.

3. WHAT IS THE SAME: the work. Same patients, same wards, same clinics, same
   colleagues. The shape of your day does not change.

4. WHERE HELP LIVES: the tour on first login, and the "Show me how" button on
   whichever screen you are stuck on. Show it being clicked once.

5. TWO HONEST WARNINGS, stated plainly rather than buried at the end:
   - Allergy lists start empty for every patient. The old system never recorded
     allergies at all. An empty list means NOBODY HAS ASKED YET. It does not
     mean the patient has no allergies. Ask, and record what you are told.
   - Documents from the old system are listed but cannot be opened. The files
     themselves were not part of what we received. The entry tells you the
     document exists so you can ask records for it.

Close: "Nothing here is a test. From Friday, this is the record."
```

---

## Video 2 — Doctors: the consultation note (6 min)

The longest video, because it carries the biggest behaviour change.

```
Create a 6-minute video for doctors on writing a consultation note in Synbot.

Frame it around one realistic outpatient consultation from start to finish. Use
a fictional patient clearly marked as training data.

Cover:

1. THE NOTE HAS FOUR SECTIONS IN ORDER — Subjective, Objective, Assessment,
   Plan. Each opens once the one before it has what it needs. Show a closed
   section and read out the line that says what is missing.

   Address the objection head-on rather than avoiding it: "This will feel slower
   for your first two or three notes. It stops being slower once the templates
   are yours."

2. SUBJECTIVE IS SEPARATED. Chief complaint is its own field and is required.
   History of presenting complaint is free text — write exactly what you would
   have written before. Review of systems is optional.

3. TEMPLATES ARE NOT TEXT BLOCKS. This is the part most worth the runtime.
   Open the template picker from one section, then open the SAME template from
   another section and show it offering different content. Pick two or three
   phrases, fill the blanks, show them compose into prose that can then be
   edited freely.

   Say: "You are not filling in a form. You are picking the sentences that
   apply, then writing whatever else you want."

4. YOUR OWN TEMPLATES COME FIRST. Show a personal template sitting above the
   shared ones. Anything you type twice is worth saving once.

5. DIAGNOSIS: SEARCH WORDS, NOT CODES. Type "malaria", pick from the list, the
   code attaches itself. Show that the code cannot be typed over. State the
   principle: no doctor should be expected to know the code.

6. PLAN AND ORDERING. Show the six order buttons. Show that orders are staged
   and only sent when the note is signed.

7. SIGNING. Slow down here. Signing locks the text permanently. Show the
   confirmation, then show adding an addendum, and show the original text still
   sitting unchanged above the correction.

Close by pointing at "Show me how" on the consultation screen, which walks the
same ground at the viewer's own pace.
```

---

## Video 3 — Nurses: vitals, notes and the chart (4 min)

```
Create a 4-minute video for nurses using Synbot at the ward and nurse station.

Cover:

1. VITALS REACH THE DOCTOR IMMEDIATELY. Record a set of vitals, then show them
   on the doctor's view. No paper hand-off, no waiting.

2. THE NOTES TAB HOLDS THE WHOLE RECORD for that patient across every visit,
   not only today's. Show scrolling back through earlier entries, including
   ones carried across from the old system.

3. NURSING NOTES ARE NOT GATED. State this explicitly, because nurses will hear
   about the doctors' strict note order and assume it applies to them. It does
   not. Write what you observed, in your own words, in any order.

4. THE FLOWSHEET is the hourly observation chart, grouped by date. Show a real
   decoded observation.

5. CORRECTIONS work exactly as they do for doctors: signed notes take an
   addendum, never an edit.

6. ALLERGIES. Restate the Video 1 warning for this role: the list starts empty
   because the old system held none. When a patient tells you about an allergy,
   record it — from that moment it warns everyone who prescribes.

Close on the "Show me how" button in the nursing panel.
```

---

## Video 4 — Front desk: finding and registering (3 min)

```
Create a 3-minute video for front desk and records staff.

Cover:

1. ALMOST EVERYONE IS ALREADY HERE. Around sixty thousand patients came across
   from the old system. Search before you register. Show a search by name, then
   by phone, then by hospital number.

2. WHAT A DUPLICATE ACTUALLY COSTS. Be concrete rather than scolding: a
   duplicate splits a patient's history in two, so the doctor sees half of it.
   Show what a split record looks like. This is the point of the whole video.

3. REGISTER THE VISIT, NOT THE PATIENT. For a returning patient you are opening
   a new encounter on an existing record.

4. CHECK HMO COVER BEFORE THEY GO THROUGH, not after. Show where cover and plan
   are displayed.

Close on "Show me how" on the Front Desk screen.
```

---

## Video 5 — Pharmacy: dispensing and stock (4 min)

```
Create a 4-minute video for pharmacy staff.

Cover:

1. PRESCRIPTIONS ARRIVE FROM THE CONSULTATION automatically. Show the queue
   filling as a doctor signs a note.

2. DOSAGE AND ROUTE ARE CHOSEN FROM LISTS, not typed. Fewer transcription
   errors, and the label reads the same every time.

3. THE ALLERGY WARNING IS A WARNING, NOT A BLOCK. Show it appearing. Say
   plainly: the system does not stop you, because there are real reasons to
   prescribe through a known allergy. It exists so the decision is made
   knowingly rather than missed.

4. ALLERGY RECORDS START EMPTY. This is the third time it appears across the
   pack, deliberately — for pharmacy it matters most. An empty list is not a
   clearance. Show recording one, then show it warning on the next prescription.

5. STOCK, BATCHES AND EXPIRY. Show the pricing tab: cost and selling price are
   held per batch, so margin can differ between two batches of the same drug.
   Show an expired batch flagged red, and say it must not be dispensed.

Close on "Show me how" on the Pharmacy screen.
```

---

## Video 6 — Laboratory: results and the verify gate (4 min)

```
Create a 4-minute video for laboratory staff.

Cover:

1. ORDERS ARRIVE ON THEIR OWN when a doctor signs a note. No phone call, no
   paper request.

2. WORK THE SAMPLE THROUGH ITS STATES — collected, received, in progress. Show
   each transition. The requesting doctor can see where the sample is, which
   cuts the "is it ready yet" calls.

3. ENTER THE RESULT AGAINST ITS REFERENCE RANGE. Show an out-of-range value
   being flagged.

4. VERIFY IS THE RELEASE STEP. This is the heart of the video. An entered
   result is NOT visible to the requesting doctor until it is verified. Say it
   twice. That gap is deliberate: it is the chance to catch a transcription
   error before anyone treats on it. A result sitting unverified is a result
   nobody is acting on.

5. HISTORICAL RESULTS ARE ALREADY HERE. Search a patient and show results
   predating go-live.

Close on "Show me how" on the Laboratory screen.
```

---

## Production notes

**Record against training data, never live.** Every frame is a screenshot that
will end up circulating on WhatsApp. Use patients named "TEST PATIENT — TRAINING".

**Record after Wednesday's meeting, not before.** Anything the client changes on
Wednesday invalidates footage shot before it.

**One presenter per role video where possible** — ideally someone from that
department rather than an IT presenter. Uptake is materially better when the
person on screen does the job.

**Subtitles on.** Wards are noisy and staff will watch without sound.

**Re-record triggers.** These go stale when the SOAP section order changes, the
six Plan order buttons change, or the verify gate moves. Nothing else in a
normal release should invalidate them.

---

## What these videos deliberately do not cover

Stated so nobody assumes it was overlooked:

- **Admin, billing, theatre, ANC and specialist clinics.** Smaller audiences, and
  those workflows were still settling at go-live. Cover them once stable.
- **Every screen in the app.** Six videos cover the daily spine. The rest is
  reachable through the role tour and the in-app help.
- **Anything the walkthroughs already do better.** A walkthrough runs on the real
  screen, at the viewer's pace, with the real buttons. Where the two overlap,
  point at the walkthrough.
