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
//
// Shape (Oct 2026): most walkthroughs follow ONE PATIENT through a department -
// how that team receives the patient, serves them and hands them on - moving
// across the pages involved (navigateTo). The visit order they teach is Royan's:
// front desk -> vitals -> doctor -> cashier -> lab / Scancare / pharmacy ->
// discharge. Anything that writes to a real record stays observe-only.
export const WALKTHROUGHS: Walkthrough[] = [
  // ───────────────────────────────────────────────────────────────────────────
  {
    id: "journey-hospital",
    title: "Follow a patient through Royan",
    summary: "One visit, end to end: front desk, vitals, doctor, cashier, lab, Scancare, pharmacy, discharge - and where it lands in the books.",
    roles: ["management", "admin"],
    homeRoute: "/executive",
    estMinutes: 6,
    steps: [
      {
        title: "The patient arrives at the Front Desk",
        body: "The desk searches for the patient (or registers them), chooses the payer - Private or HMO - picks a doctor who is on seat today and issues a queue ticket.",
        navigateTo: "/hospital/front-desk",
        anchor: "frontdesk-rooms",
        action: "observe",
        cue: "Each morning the desk puts every doctor in a consulting room here.",
      },
      {
        title: "Vitals, then the doctor",
        body: "On Queue & Flow the patient waits for vitals; the nurse records them and the patient moves to Ready for doctor. Nobody pays before seeing the doctor.",
        navigateTo: "/hospital/queue",
        anchor: "queue-stages",
        action: "click",
        cue: "Click a stage to see who is waiting there",
      },
      {
        title: "The consultation",
        body: "The doctor sees the patient on My Dashboard, writes the SOAP note with an ICD-10 diagnosis, and orders lab tests, scans and drugs from the Orders tab.",
        navigateTo: "/hospital/doctor",
        anchor: "doctor-my-patients",
        action: "observe",
        cue: "A doctor's patients for today.",
      },
      {
        title: "The cashier",
        body: "After the doctor the patient pays for the consultation and what was ordered. HMO patients pay only for what the HMO team marked not covered.",
        navigateTo: "/hospital/billing",
        anchor: "billing-bills-tab",
        action: "observe",
        cue: "Every bill, paid or owing.",
      },
      {
        title: "Lab, Scancare and pharmacy",
        body: "Once the bill is paid, the lab takes the sample, Scancare does the scan and the pharmacy dispenses. Results come back to the doctor as the printed Scancare report.",
        navigateTo: "/hospital/lab",
        anchor: "lab-worklist",
        action: "observe",
        cue: "The lab's order queue.",
      },
      {
        title: "HMO patients",
        body: "The HMO Desk checks what each HMO covers before the claims form goes out; the patient signs the form on the signature pad.",
        navigateTo: "/hospital/hmo",
        anchor: "hmo-desk-tab",
        action: "observe",
        cue: "Today's HMO patients.",
      },
      {
        title: "Discharge and the books",
        body: "The patient leaves from Done - pay & discharge on the queue. Every bill, payment, HMO claim and dispensed drug has already posted to Roy Books; the Executive Overview shows the day.",
        navigateTo: "/executive",
      },
    ],
  },

  // ───────────────────────────────────────────────────────────────────────────
  {
    id: "find-register-patient",
    title: "Serving a patient at the front desk",
    summary: "Put doctors in rooms, find or register the patient, check them in to a doctor, answer pharmacy approvals.",
    roles: ["receptionist", "ops", "nurse", "admin", "management"],
    homeRoute: "/hospital/front-desk",
    estMinutes: 4,
    steps: [
      {
        title: "Before the first patient: doctors to rooms",
        body: "As each doctor arrives, click Assign a doctor next to a room on Consulting rooms today and type their name. Only doctors on seat are offered at check-in.",
        navigateTo: "/hospital/front-desk",
        anchor: "frontdesk-rooms",
        action: "observe",
        cue: "Assign a doctor next to each room.",
      },
      {
        title: "A patient walks in: search first",
        body: "Type the name, phone number or MRN. Most patients are already here, with records from as far back as 2016.",
        anchor: "frontdesk-search",
        action: "click",
        cue: "Click in the search box",
      },
      {
        title: "Not found? Try another spelling, then New patient",
        body: "Try a different spelling or the phone number first - a duplicate record splits the patient's history in two. Only then click New patient at the top, register them, and come back to check them in.",
      },
      {
        title: "Choose payer, doctor and priority",
        body: "Pick the visit type and the Payer: Private, or HMO / Insurance (the card number fills from their record). Choose the doctor - each shows their room and how many are waiting - then the Priority and the complaint.",
        anchor: "frontdesk-doctor",
        action: "click",
        cue: "Click to see the doctors on seat",
      },
      {
        title: "Click Register Encounter & Issue Ticket",
        body: "The patient goes on the queue with a number and appears on the chosen doctor's dashboard. If the button reads Already on the queue, they are already checked in today.",
        anchor: "frontdesk-register",
        action: "observe",
        caution: true,
        cue: "This creates a real registration. Look, then come back.",
      },
      {
        title: "Where the patient goes next",
        body: "Vitals with the nurse, then the doctor. They pay at the cashier after the doctor, not here. Display board at the top shows the waiting room their number and room.",
      },
      {
        title: "Pharmacy approvals",
        body: "When the pharmacy asks the desk to approve a drug it appears under Pharmacy approvals waiting: tick to approve, cross to reject.",
        anchor: "frontdesk-approvals",
        action: "observe",
        cue: "Requests from the pharmacy land here.",
      },
    ],
  },

  // ───────────────────────────────────────────────────────────────────────────
  {
    id: "journey-nurse",
    title: "Serving a patient as a nurse",
    summary: "Take the patient's vitals, send them to the doctor, and look after admissions and the nursing record.",
    roles: ["nurse", "ops", "admin", "management"],
    homeRoute: "/hospital/queue",
    estMinutes: 3,
    steps: [
      {
        title: "Find the patients waiting for vitals",
        body: "Queue & Flow lists today's outpatients by stage. Waiting for vitals is your list; the front desk's check-ins land here.",
        navigateTo: "/hospital/queue",
        anchor: "queue-stages",
        action: "click",
        cue: "Click Waiting for vitals",
      },
      {
        title: "Click Vitals on the patient",
        body: "It opens the vitals form. Nothing is saved until you press Save & Confirm Vitals.",
        anchor: "queue-vitals",
        action: "click",
        cue: "Click Vitals",
      },
      {
        title: "Save & Confirm Vitals",
        body: "Fill in what you measured and save. The doctor sees the vitals in the consultation at once, and the patient moves to Ready for doctor.",
      },
      {
        title: "Send the patient to the doctor",
        body: "The patient's chosen doctor sees them on My Dashboard. If no doctor was chosen at the desk, Doctor on the patient's row assigns one.",
      },
      {
        title: "Admissions and the ward",
        body: "When a doctor requests an admission it appears at the Nursing Station. On Wards & Beds pick a free bed and Confirm Admission; Free Bed after discharge.",
        navigateTo: "/hospital/nurse",
      },
      {
        title: "The nursing record",
        body: "Open a patient for Notes, Vitals, Flowsheet, Fluid Balance, Care Plans and MAR. Show me how inside the record walks you through it.",
      },
    ],
  },

  // ───────────────────────────────────────────────────────────────────────────
  {
    id: "journey-doctor",
    title: "Seeing a patient as a doctor",
    summary: "From your dashboard to the note, orders, the cashier and the results - one patient end to end.",
    roles: ["doctor", "admin", "management"],
    homeRoute: "/hospital/doctor",
    estMinutes: 5,
    steps: [
      {
        title: "Your patients for today",
        body: "My patients shows today's appointments, the patients checked in to you, results to review and who you have finished. The nurse's vitals are already recorded.",
        navigateTo: "/hospital/doctor",
        anchor: "doctor-my-patients",
        action: "observe",
        cue: "Begin next to a patient opens the consultation.",
      },
      {
        title: "Click Begin",
        body: "The consultation opens: Summary, Vitals, Results, Notes, Orders, Prescribe and Referral. Read the vitals first.",
      },
      {
        title: "Write the note",
        body: "Notes: Subjective, Objective, Assessment, Plan. Each section stays open while you type; Continue moves you on. Add diagnosis searches in words and fills the ICD-10 code. The note's own Show me how covers it in detail.",
      },
      {
        title: "Order what the patient needs",
        body: "Orders: Order Lab Test, Order Radiology, Order Medication, Book Surgery. An HMO patient shows what their HMO covers at the top; Request HMO approval asks for a service it does not.",
        anchor: "consult-orders-tab",
        action: "click",
        cue: "Click Orders",
      },
      {
        title: "End the consultation",
        body: "End consultation sends the patient on: they pay at the cashier, then go to lab, Scancare or the pharmacy. End - see again with results brings them back to you when the results are in.",
        anchor: "consult-end",
        action: "observe",
        caution: true,
        cue: "This moves the patient on. Look, do not press during training.",
      },
      {
        title: "Review the results",
        body: "Returned results show on My Dashboard and in the consultation's Results tab, each with View report - the printable Scancare report sheet.",
        anchor: "consult-results-tab",
        action: "click",
        cue: "Click Results",
      },
      {
        title: "Open a result as the printed report",
        body: "View report shows the result with the patient's details on the Scancare letterhead; Print prints it. Print all lab results gives the visit on one sheet.",
        anchor: "view-report",
        action: "click",
        cue: "Click View report",
      },
    ],
  },

  // ───────────────────────────────────────────────────────────────────────────
  {
    id: "soap-note",
    title: "Writing a SOAP note",
    summary: "Fill each section, add a diagnosis, order from the Plan, then sign.",
    roles: ["doctor", "admin", "management"],
    homeRoute: "/hospital/queue",
    estMinutes: 5,
    steps: [
      {
        title: "Work through the four sections",
        body:
          "Subjective, Objective, Assessment and Plan. Every section is open to write in; a section stays open while you type, and Continue to the next section moves you on when you are ready.",
        anchor: "soap-stepper",
        action: "observe",
        cue: "Click any section in this bar to jump to it.",
      },
      {
        title: "Fill in the Chief Complaint",
        body:
          "Type the main complaint in Chief Complaint. History of Presenting Complaint and Review of Systems are optional. Continue to Objective when you are done.",
        anchor: "soap-chief-complaint",
        action: "observe",
        cue: "Type the complaint here.",
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
        title: "A note needs a diagnosis to be signed",
        body:
          "You can write the Plan at any time, but the note cannot be signed until Assessment has at least one diagnosis. A plan without a recorded diagnosis is a clinical and medico-legal gap.",
        anchor: "soap-plan-section",
        action: "observe",
        cue: "Plan: what you will do, plus orders.",
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
    id: "cashier-payment",
    title: "Serving a patient at the cashier",
    summary: "The patient comes from the doctor: take the payment, print the receipt, release the services, handle HMO not-covered items.",
    roles: ["cashier", "finance", "admin", "management"],
    homeRoute: "/hospital/billing",
    estMinutes: 3,
    steps: [
      {
        title: "Find the patient's bill",
        body: "The patient comes to you after the doctor. Bills lists every bill; the consultation and everything ordered are on it - Royan's and, separately, Scancare's.",
        navigateTo: "/hospital/billing",
        anchor: "billing-bills-tab",
        action: "click",
        cue: "Click Bills",
      },
      {
        title: "Open the bill",
        body: "Click the patient's bill. It shows each service, what the HMO covers (if any), what the patient owes and what is paid.",
      },
      {
        title: "Record Payment",
        body: "The amount owed is filled in. Choose Cash, POS, Transfer or Card and save, then Receipt or Print Invoice for the patient. Once paid, lab, Scancare and the pharmacy can serve them.",
        anchor: "billing-record-payment",
        action: "observe",
        caution: true,
        cue: "This records real money. Look, do not press during training.",
      },
      {
        title: "Part payment",
        body: "If the patient can only pay part and must be seen now, Release services lets lab, scan and pharmacy go ahead; the balance stays on their account.",
      },
      {
        title: "HMO patients",
        body: "An HMO visit's bill shows What the HMO covers. A service the HMO team marked not covered is the patient's to pay here; Request HMO approval asks the HMO team to get it approved instead.",
        anchor: "hmo-services-check",
        action: "observe",
        cue: "Only on an HMO patient's bill.",
      },
      {
        title: "Corrections",
        body: "A discount is requested here and approved by an administrator. A wrong bill is voided with a reason; its orders can then be billed again.",
      },
    ],
  },

  // ───────────────────────────────────────────────────────────────────────────
  {
    id: "hmo-services",
    title: "Serving an HMO patient",
    summary: "Check what the HMO covers, answer approval requests, and get the claims form signed and checked.",
    roles: ["hmo", "finance", "admin", "management"],
    homeRoute: "/hospital/hmo",
    estMinutes: 3,
    steps: [
      {
        title: "Today's HMO patients",
        body: "HMO Desk lists every HMO patient on the queue: where they are, what was ordered and what the pharmacy has given.",
        navigateTo: "/hospital/hmo",
        anchor: "hmo-desk-tab",
        action: "click",
        cue: "Click HMO Desk",
      },
      {
        title: "Open the patient",
        body: "Click the patient. Their card number, diagnosis, drugs, bills and the claims form are on one panel.",
      },
      {
        title: "Mark what the HMO covers",
        body: "Under Services - what the HMO covers, mark each service Covered or Not covered. Not covered moves it to the patient to pay; it is held at lab, scan or pharmacy until paid and stays off the claim. Unmarked, the HMO pays in full.",
        anchor: "hmo-services-check",
        action: "observe",
        cue: "Covered / Not covered on each service.",
      },
      {
        title: "Answer approval requests",
        body: "When the doctor or cashier requests approval for a not-covered service, ask the HMO, then record HMO approved with the authorisation code (it goes back on the claim) or HMO declined (the patient pays).",
      },
      {
        title: "The claims form",
        body: "Open Royan claims form prints the visit's claim. The patient signs on the signature pad; then I have checked the claims form.",
      },
    ],
  },

  // ───────────────────────────────────────────────────────────────────────────
  {
    id: "lab-verify",
    title: "Serving a patient in the lab",
    summary: "From the doctor's order to the sample, the result, verification and the printed report.",
    roles: ["lab", "admin", "management"],
    homeRoute: "/hospital/lab",
    estMinutes: 4,
    steps: [
      {
        title: "The order arrives",
        body: "Order Queue: a doctor's order appears as soon as it is placed. STAT and urgent orders sort to the top.",
        navigateTo: "/hospital/lab",
        anchor: "lab-worklist",
        action: "click",
        cue: "Click Order Queue",
      },
      {
        title: "Find the patient's order",
        body: "Type the patient's name, the test or the order number, then click the order to open it.",
        anchor: "lab-order-status",
        action: "click",
        cue: "Click in the search box",
      },
      {
        title: "Take and receive the sample",
        body: "Collect Specimen, then Receive Specimen (Reject Specimen if it is unusable). A private patient who has not paid is held - send them to the cashier first.",
      },
      {
        title: "Open the Result tab",
        body: "The test's lines are already there - investigation, units and normal range from its template.",
        anchor: "lab-result-tab",
        action: "click",
        cue: "Click Result",
      },
      {
        title: "Type only the values",
        body: "Enter the observed value on each line and Save Result. Values outside the range print in red. Edit lines unlocks the lines for an exception.",
        anchor: "lab-result-lines",
        action: "observe",
        cue: "One value per line.",
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
        title: "The printed report",
        body: "View report shows the result on the Scancare report sheet with the patient's details; Print prints it for the patient.",
        anchor: "view-report",
        action: "click",
        cue: "Click View report",
      },
      {
        title: "Critical values",
        body: "Turnaround & Critical flags values outside the critical range. Phone the requesting doctor as well; the flag does not replace the call.",
        anchor: "lab-result-entry",
        action: "click",
        cue: "Click Turnaround & Critical",
      },
    ],
  },

  // ───────────────────────────────────────────────────────────────────────────
  {
    id: "scancare-report",
    title: "Serving a patient at Scancare",
    summary: "From the doctor's request (or a walk-in) to the scan, the pre-filled report, verification and the printed report.",
    roles: ["radiology", "admin", "management"],
    homeRoute: "/hospital/radiology",
    estMinutes: 4,
    steps: [
      {
        title: "The request arrives",
        body: "Worklist shows the studies doctors have ordered. A patient who comes straight to Scancare is registered with Walk-in study.",
        navigateTo: "/hospital/radiology",
        anchor: "radiology-worklist-tab",
        action: "click",
        cue: "Click Worklist",
      },
      {
        title: "Do the scan",
        body: "Open the study: Schedule, then Start Scan. A private patient who has not paid is held - send them to the cashier (or Billing & cashier here) first.",
      },
      {
        title: "The report is already written",
        body: "The Report tab opens with Scancare's standard report for that study and this patient's indication. Fill in every ___ (measurements) and change what differs; Common phrases for this study adds a phrase with one click.",
        anchor: "radiology-report-text",
        action: "observe",
        cue: "Fill the ___ blanks for this patient.",
      },
      {
        title: "Save, then verify",
        body: "Save Report, then Verify & Finalize. A finalized report can only be corrected with Amend Report; the original stays on record.",
        anchor: "radiology-verify-button",
        action: "observe",
        caution: true,
        cue: "Verifying finalizes the report. Do not verify a real report during training.",
      },
      {
        title: "The printed report",
        body: "View report (print) shows the scan on the Scancare report sheet; Print prints it for the patient. The doctor sees the same report.",
        anchor: "view-report",
        action: "click",
        cue: "Click View report",
      },
    ],
  },

  // ───────────────────────────────────────────────────────────────────────────
  {
    id: "dispensing",
    title: "Serving a patient at the pharmacy",
    summary: "The prescription arrives, you check it, dispense what the doctor prescribed and keep stock right.",
    roles: ["pharmacist", "admin", "management"],
    homeRoute: "/hospital/pharmacy",
    estMinutes: 4,
    steps: [
      {
        title: "The prescription arrives",
        body: "Prescriptions: anything a doctor prescribes appears here at once. To Dispense lists what is waiting.",
        navigateTo: "/hospital/pharmacy",
        anchor: "pharmacy-queue",
        action: "click",
        cue: "Click Prescriptions",
      },
      {
        title: "Open the patient's prescription",
        body: "It opens on Dispense. Drug, dose, route and frequency are exactly as the doctor chose them.",
      },
      {
        title: "Check what is filled in",
        body: "The quantity the doctor prescribed and the drug's unit price are already filled in. Keep Auto (FEFO) for the batch, change the quantity for a part supply, and tick Counselling given.",
        anchor: "pharmacy-dispense-form",
        action: "observe",
        cue: "Check, do not retype.",
      },
      {
        title: "Ask about allergies: an empty list is not a clear patient",
        body:
          "No allergy history came across from the old system. An empty allergy list means nobody recorded one; it does not mean the patient has none. Ask, and record any allergy you find.",
      },
      {
        title: "Click Dispense",
        body: "Stock is taken from the batch and the dispensing posts to the books. An allergy or interaction warning stops you first; Override & Dispense records your reason.",
        anchor: "pharmacy-dispense-button",
        action: "observe",
        caution: true,
        cue: "This gives out real stock. Look, do not press during training.",
      },
      {
        title: "Held prescriptions",
        body: "A private patient who has not paid is held - send them to the cashier first. A drug the HMO team marked not covered is held until the patient pays or the HMO approves it.",
      },
      {
        title: "Keep stock right",
        body: "Inventory Workspace shows live stock, batches, expiry dates and low-stock flags; the Reorder plan says what to order.",
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

/** Every walkthrough any of these roles may use (a person with several roles gets them all). */
export function getWalkthroughsForRoles(roles: string[]): Walkthrough[] {
  const have = new Set(roles.map((r) => r.toLowerCase()));
  return WALKTHROUGHS.filter((w) => !w.roles || w.roles.some((r) => have.has(r)));
}

export function getWalkthroughsForRoute(route: string, role: string): Walkthrough[] {
  return getWalkthroughsForRole(role).filter((w) => w.homeRoute === route);
}

export function getWalkthroughById(id: string): Walkthrough | undefined {
  return WALKTHROUGHS.find((w) => w.id === id);
}
