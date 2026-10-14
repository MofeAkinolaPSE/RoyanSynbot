/**
 * Task walkthroughs — Tier 2 of in-app training.
 *
 * The role tour (tour-config.ts) answers "where are my pages". These answer
 * "how do I do this", which is the harder question and the one the SOAP note
 * actually raises. They are invoked on demand from a "Show me how" control, not
 * forced on first login.
 *
 * ANCHORING: steps target a `data-tour-id` attribute rather than a CSS class or
 * DOM path, so a restyle cannot silently break a walkthrough. A step whose
 * anchor is missing from the page degrades to a plain explanation rather than
 * pointing at nothing — the content still teaches, it just cannot highlight.
 */

export type WalkthroughStep = {
  title: string;
  body: string;
  /** `data-tour-id` of the element to highlight. Omit for a plain step. */
  anchor?: string;
  /** Optional route to move to before showing this step. */
  navigateTo?: string;
  /**
   * What the learner should do here.
   *
   * "click"   — the highlighted control is safe to press. The step advances
   *             when they actually press it, so the walkthrough is driven by
   *             doing rather than by reading and clicking Next.
   * "observe" — default. Look, do not press. Used where the control commits
   *             something (signing, verifying, dispensing) and pressing it
   *             during training would write to a real record.
   */
  action?: "click" | "observe";
  /**
   * Marks a control that commits an irreversible clinical action. Renders the
   * spotlight amber instead of blue and states plainly not to press it now.
   * Always pair with action: "observe".
   */
  caution?: boolean;
  /** Short imperative shown under the body, e.g. "Open the Notes tab". */
  cue?: string;
};

export type Walkthrough = {
  id: string;
  title: string;
  /** One line, shown in the training menu. */
  summary: string;
  /** Roles this is offered to. Undefined = everyone. */
  roles?: string[];
  /** Route where the "Show me how" control appears. */
  homeRoute?: string;
  estMinutes: number;
  steps: WalkthroughStep[];
};

// Copy rule: each step title says what to do; the body says where, what to
// press and what happens next, in one or two short sentences. Keep a reason only
// when it changes behaviour (safety, medico-legal, duplicates). Name controls
// exactly as they appear on screen. Roy's chat guide
// (backend/src/knowledge/roy_feature_guide.md) describes the same tasks; keep the
// two in step.
export const WALKTHROUGHS: Walkthrough[] = [
  // ───────────────────────────────────────────────────────────────────────────
  {
    id: "soap-note",
    title: "Writing a SOAP note",
    summary: "Fill each section in order, add a diagnosis, order from the Plan, then sign.",
    roles: ["doctor", "admin", "management"],
    homeRoute: "/hospital/queue",
    estMinutes: 5,
    steps: [
      {
        title: "Work through the four sections in order",
        body:
          "Subjective, then Objective, Assessment and Plan. Each section opens when the one before it is complete. A locked section tells you what it is waiting for.",
        anchor: "soap-stepper",
        action: "observe",
        cue: "Check which sections are open and which are locked.",
      },
      {
        title: "Fill in the Chief Complaint",
        body:
          "Type the main complaint in Chief Complaint. This opens Objective. History of Presenting Complaint and Review of Systems are optional.",
        anchor: "soap-chief-complaint",
        action: "observe",
        cue: "Type a complaint here and watch Objective open.",
      },
      {
        title: "Insert phrases with the template button",
        body:
          "Click the template button on a section, tick the phrases you want, and insert them. Your own templates are listed above the shared ones.",
        anchor: "soap-template-subjective",
        action: "click",
        cue: "Click the template button",
      },
      {
        title: "Fill the blanks before inserting",
        body:
          "A phrase with a blank shows a box to type in; a phrase with a choice shows a dropdown. Fill them, insert, and edit the text in the note as normal.",
      },
      {
        title: "Record the examination",
        body:
          "Write general findings here, then each system below. Click Findings for templates by organ system, or All systems Negative for a normal review.",
        anchor: "soap-objective-general",
        action: "observe",
        cue: "General findings first, then each system below.",
      },
      {
        title: "Add a diagnosis by searching in words",
        body:
          "Click Add diagnosis and type the condition, for example 'malaria'. Pick the match and the ICD-10 code fills in automatically. You never type a code.",
        anchor: "soap-add-diagnosis",
        action: "click",
        cue: "Click Add diagnosis",
      },
      {
        title: "Plan opens once a diagnosis is recorded",
        body:
          "Plan stays locked until Assessment has at least one diagnosis. A plan without a recorded diagnosis is a clinical and medico-legal gap.",
        anchor: "soap-plan-section",
        action: "observe",
        cue: "Plan stays closed until Assessment has a diagnosis.",
      },
      {
        title: "Place orders from the Plan",
        body:
          "Choose Medication, Allergy, Immunisation, Lab, Radiology or Procedure, and pick from the catalogue. Orders are held with the note and sent only when you sign.",
        anchor: "soap-order-bar",
        action: "click",
        cue: "Click any order type to open its dialog",
      },
      {
        title: "Sign the note",
        body:
          "Click Sign note. The note saves first, then the orders are sent. After signing, nobody can edit the note, including administrators. Corrections are made with an addendum.",
        anchor: "soap-sign-button",
        action: "observe",
        caution: true,
        cue: "Signing locks the note permanently and sends the orders.",
      },
    ],
  },

  // ───────────────────────────────────────────────────────────────────────────
  {
    id: "note-addendum",
    title: "Correcting a signed note",
    summary: "Add an addendum: click Amend, write the correction and a reason, sign it.",
    roles: ["doctor", "nurse", "admin", "management"],
    homeRoute: "/hospital/queue",
    estMinutes: 2,
    steps: [
      {
        title: "Signed notes cannot be edited",
        body:
          "Nobody can edit or delete a signed note, including administrators and IT. To correct one, you add an addendum beneath it.",
      },
      {
        title: "Click Amend on the note",
        body:
          "Find the signed note and click Amend. This opens the addendum. The original note is not changed.",
        anchor: "note-amend-button",
        action: "click",
        cue: "Click Amend",
      },
      {
        title: "Write the correction and a short reason",
        body:
          "Write the correction, then a one-line reason, for example 'wrong dose recorded' or 'result received after signing'. Click Sign addendum.",
        anchor: "addendum-reason",
        action: "observe",
        cue: "One line is enough.",
      },
      {
        title: "The addendum appears under the original",
        body:
          "Both show together, with your name and the time on the addendum. You can add more than one addendum to the same note.",
      },
    ],
  },

  // ───────────────────────────────────────────────────────────────────────────
  {
    id: "personal-template",
    title: "Creating your own template",
    summary: "Save phrases you write often as a template, then insert them with one click.",
    roles: ["doctor", "admin"],
    homeRoute: "/hospital/queue",
    estMinutes: 3,
    steps: [
      {
        title: "Open the template button on the section",
        body:
          "Click Template on the section you are writing. On Subjective and Objective it is a menu: choose Note templates.",
        anchor: "soap-template-subjective",
        action: "click",
        cue: "Click Template",
      },
      {
        title: "Click New template",
        body:
          "New template is at the bottom left of the template window. Nothing is saved until you click Save template.",
        anchor: "note-template-new",
        action: "click",
        cue: "Click New template",
      },
      {
        title: "Name it",
        body:
          "Use a name you will recognise in the list, for example 'Routine antenatal review'.",
        anchor: "note-template-name",
        action: "observe",
        cue: "Type a name here.",
      },
      {
        title: "Write one phrase per line, in the right section",
        body:
          "There is a box for Subjective, Objective, Assessment and Plan; fill only the ones you need. Each line becomes a phrase you can tick. Type ?? where a detail changes per patient. Use what I've written in this section copies in the text from your note.",
        anchor: "note-template-phrases",
        action: "observe",
        cue: "One line = one phrase. ?? = a blank to fill per patient.",
      },
      {
        title: "Keep it private or share it",
        body:
          "Leave Share with other doctors off and only you see it. Turn it on and every doctor can use it, but only you can change it.",
      },
      {
        title: "Click Save template",
        body:
          "It appears at the top of your template list, marked Yours, in each section you wrote phrases for. Select it and use Edit or Delete to change it later. Notes already written with it are not affected.",
        anchor: "note-template-save",
        action: "observe",
        cue: "Click Save template when you are ready.",
      },
    ],
  },

  // ───────────────────────────────────────────────────────────────────────────
  {
    id: "lab-verify",
    title: "From sample to verified result",
    summary: "Open the order, collect and receive the sample, record the result, verify.",
    roles: ["lab", "admin", "management"],
    homeRoute: "/hospital/lab",
    estMinutes: 3,
    steps: [
      {
        title: "Open the Order Queue",
        body:
          "Click Order Queue. A doctor's order appears here as soon as it is placed. STAT and urgent orders sort to the top.",
        anchor: "lab-worklist",
        action: "click",
        cue: "Click Order Queue",
      },
      {
        title: "Search for the order",
        body:
          "Type the patient's name, the test or the order number to find it. Click the order to open it.",
        anchor: "lab-order-status",
        action: "click",
        cue: "Click in the search box",
      },
      {
        title: "Move the sample through its steps",
        body:
          "In the open order, click Collect Specimen, then Receive Specimen, then Record Result. Use Reject Specimen if the sample is unusable. Each step is timed, and those times build the turnaround figures.",
      },
      {
        title: "Check critical results",
        body:
          "Click Turnaround & Critical. Values outside the reference range are flagged here. Phone the requesting doctor about a critical value as well; the flag does not replace the call.",
        anchor: "lab-result-entry",
        action: "click",
        cue: "Click Turnaround & Critical",
      },
      {
        title: "Click Verify & Authenticate to release the result",
        body:
          "A result is not visible to the requesting doctor until it is verified. Check the values before you verify. If a verified result is wrong, use Amend Result; the original stays on record.",
        anchor: "lab-verify-button",
        action: "observe",
        caution: true,
        cue: "Verifying releases the result to the doctor. Do not verify a real result during training.",
      },
      {
        title: "Past results are already on the chart",
        body:
          "Results from the old system are on each patient's chart, under the Labs tab, so doctors can compare with earlier values.",
      },
    ],
  },

  // ───────────────────────────────────────────────────────────────────────────
  {
    id: "find-register-patient",
    title: "Finding and registering a patient",
    summary: "Search first, then register today's visit and issue a ticket.",
    roles: ["receptionist", "ops", "nurse", "admin", "management"],
    homeRoute: "/hospital/front-desk",
    estMinutes: 3,
    steps: [
      {
        title: "Search for the patient first",
        body:
          "Type the name, phone number or MRN. Most patients are already in the system, with records from as far back as 2016.",
        anchor: "frontdesk-search",
        action: "click",
        cue: "Click in the search box",
      },
      {
        title: "Try another spelling before creating a new record",
        body:
          "If nothing matches, try a different spelling or search by phone. A duplicate record splits the patient's history in two and is hard to undo.",
      },
      {
        title: "New patient? Click Register new patient →",
        body:
          "Only if they are genuinely not found, click Register new patient → under the search. It opens PCE / Patients, where you create the record.",
      },
      {
        title: "Choose the visit type, priority and complaint",
        body:
          "Pick the visit type (for example Walk-In / Outpatient or Emergency), choose Normal or Urgent, and type the chief complaint.",
      },
      {
        title: "Click Register Encounter & Issue Ticket",
        body:
          "This puts the patient on the clinical queue with a number, and the nurses see them immediately. If the button reads Already on the queue, they are already checked in today.",
        anchor: "frontdesk-register",
        action: "observe",
        caution: true,
        cue: "This creates a real registration. Look, then come back.",
      },
      {
        title: "Check HMO cover before they go through",
        body:
          "Check the patient's HMO cover on their record now. Sorting it out after treatment is much harder.",
      },
    ],
  },

  // ───────────────────────────────────────────────────────────────────────────
  {
    id: "dispensing",
    title: "Dispensing a prescription",
    summary: "Open the prescription, check allergies, dispense, and check stock.",
    roles: ["pharmacist", "admin", "management"],
    homeRoute: "/hospital/pharmacy",
    estMinutes: 3,
    steps: [
      {
        title: "Open the Prescriptions tab",
        body:
          "Click Prescriptions. Anything a doctor prescribes appears here when they sign the note, split into pending, partially dispensed and dispensed.",
        anchor: "pharmacy-queue",
        action: "click",
        cue: "Click Prescriptions",
      },
      {
        title: "Open a prescription and click Dispense",
        body:
          "Drug, dose, route and frequency are exactly as the doctor chose them from fixed lists. Check them, then click Dispense.",
      },
      {
        title: "Ask about allergies: an empty list is not a clear patient",
        body:
          "No allergy history came across from the old system. An empty allergy list means nobody recorded one; it does not mean the patient has none. Ask, and record any allergy you find.",
      },
      {
        title: "Act on allergy and interaction warnings",
        body:
          "Once an allergy is recorded, a matching drug raises a warning. To go ahead anyway, use Override & Dispense, which records your reason.",
      },
      {
        title: "Check stock in the Inventory Workspace",
        body:
          "Click Inventory Workspace to see live stock, batches, expiry dates and low-stock flags. A drug's Pricing tab shows cost against sale price per batch.",
        anchor: "pharmacy-inventory-link",
        action: "click",
        cue: "Click Inventory Workspace",
      },
    ],
  },

  // ───────────────────────────────────────────────────────────────────────────
  {
    id: "nursing-record",
    title: "The nursing record and observation chart",
    summary: "Record vitals, write notes, and read the patient's full nursing history.",
    roles: ["nurse", "admin", "management"],
    homeRoute: "/hospital/nursing",
    estMinutes: 3,
    steps: [
      {
        title: "Record vitals on the Vitals tab",
        body:
          "Click Vitals, then Record Vitals. Once saved, the vitals appear in the doctor's consultation immediately; there is nothing else to send.",
        anchor: "nursing-vitals-tab",
        action: "click",
        cue: "Click Vitals",
      },
      {
        title: "Read the full history on the Notes tab",
        body:
          "Click Notes. It shows every nursing note for this patient across every visit, including notes from the old system.",
        anchor: "nursing-notes-tab",
        action: "click",
        cue: "Click Notes",
      },
      {
        title: "Write your note and click Save note",
        body:
          "Type your observation in your own words. Nursing notes do not have to follow the Subjective-Objective-Assessment-Plan order. Nothing is saved until you click Save note.",
        anchor: "nursing-note-input",
        action: "observe",
        cue: "You can type here. Nothing is saved until you click Save note.",
      },
      {
        title: "Use the Flowsheet for hourly observations",
        body:
          "Click Flowsheet for the hourly observation chart, grouped by day. Fluid Balance, Care Plans and MAR each have their own tab.",
        anchor: "nursing-flowsheet-tab",
        action: "click",
        cue: "Click Flowsheet",
      },
      {
        title: "Correct a signed note with an addendum",
        body:
          "A signed nursing note cannot be edited. Click Amend on it and add a correction. Both versions stay visible, each with a name on it.",
      },
    ],
  },
];

export function getWalkthroughsForRole(role: string): Walkthrough[] {
  return WALKTHROUGHS.filter((w) => !w.roles || w.roles.includes(role));
}

export function getWalkthroughsForRoute(route: string, role: string): Walkthrough[] {
  return getWalkthroughsForRole(role).filter((w) => w.homeRoute === route);
}

export function getWalkthroughById(id: string): Walkthrough | undefined {
  return WALKTHROUGHS.find((w) => w.id === id);
}
