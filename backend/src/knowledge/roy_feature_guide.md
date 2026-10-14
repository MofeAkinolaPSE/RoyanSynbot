# Roy Feature Guide

This file is Roy's map of the RoyanHealth app. Roy reads it at chat time to tell
staff exactly where a page, tab or button is, and to say honestly when the
system does not have something. If it is not in here, Roy will say he cannot
find it, so keep this file current.

How to maintain it:
- One `## ` section per page or task. The lines directly under the heading are
  metadata (`id`, `menu`, `route`, `roles`, `keywords`), then a blank line, then
  the body.
- `menu` is the sidebar path exactly as the user sees it, using ` > ` for groups.
- `route` must match the URL in SynbotUI/client/App.tsx. Several routes are
  comma-separated. `tests/test_roy_guide.py` fails if a sidebar page in
  SynbotUI/client/lib/nav-items.ts has no section here.
- `roles` copies the roles in nav-items.ts. `everyone` means no restriction.
- `keywords` are the words staff actually use when they ask. Add the phrase a
  confused colleague used, not the official name.
- Write the body as directions: page, then tab, then button, using the labels
  exactly as they appear on screen. Mark anything irreversible.

## What Roy can and cannot do from chat
id: roy-capabilities
menu: Ask Synbot (or the chat bubble on any page)
route: /synbot
roles: everyone
keywords: roy, what can you do, can you, chat, ask synbot, synbot, assistant, email, whatsapp, meeting, task, reminder, report, replenish, do it for me, help me

Roy can do these from chat:
- Send an email to an internal department. Roy shows a draft first; reply "send it" to send or tell him what to change.
- Send a WhatsApp message.
- Schedule a meeting.
- Create a task.
- Generate a structured report.
- Trigger stock replenishment.
- Answer questions about your own appointments, recent patients and open tasks, and look up hospital data your role can see.
- Explain where anything is in the system and how to do it.

Roy cannot do these from chat (do them on the page; Roy will give you the steps):
- Prescribe, order labs or imaging, or book surgery. Use the consultation workspace.
- Discharge, admit, triage or call a patient. Use Queue & Flow or Wards & Beds.
- Book, arrive or cancel appointments. Use Diary > Appointments.
- Generate a bill, take a payment or submit an HMO claim. Use Roy Books > Billing & Cashier, or Generate Bill on the queue.
- Sign, edit or amend clinical notes.

## Finding your way around
id: navigation
menu: Sidebar (left side of every page)
route: none
roles: everyone
keywords: menu, sidebar, navigate, navigation, lost, can't find, cannot find, missing page, don't see, not on my menu, home, tour, take the tour, onboarding, sign out, log out, logout, dark mode, light mode, theme, show me how, help button, training, walkthrough, folder, folders, where did it go, moved, new menu

- The sidebar is a short list of folders, grouped by the job you do. Click a folder to open it:
  - **My Workspace**: your own day. Doctors see **My Dashboard**, nurses see **Nursing Station**, everyone else sees **Tasks, inbox & messages**; plus **Appointments**, **My Schedule** and the **Hospital Calendar**.
  - **Patients & Flow**: Front Desk, Patients (PCE), Queue & Flow, Wards & Beds.
  - **Clinical Services**: Lab & Diagnostics, Radiology, Surgical Theatre, Specialist Clinics, MCH / OB-GYN, Immunisation.
  - **Pharmacy**: Dispensing, Inventory, Quality Control, Reorder plan & orders, Supplier records.
  - **Quality & Compliance**: Quality & Safety, Audits & Maintenance, Compliance.
  - **Reports**: Write a report, Report library, Analytics.
  - **Management**: Executive Overview, Admin Dashboard, Patient Relations, Digital Engagement, Clinical Data Explorer.
  - **Roy Books**, **HR**, **Users & Access** (User Access, Staff Registrations, Audit Log) and **System**.
- Your sidebar only shows what your role opens. If a page a colleague mentions is missing, your role does not include it. Ask an administrator to change your access in **Users & Access > User Access**.
- **ROY Workstation** at the top is home. Click it any time you are lost.
- To replay the introduction tour: click the **⋮** button next to "Roy" at the bottom of the sidebar, then **Take the tour again**.
- The same **⋮** menu has **Settings** (admins), **Light mode / Dark mode** and **Sign out**.
- **Show me how** buttons give a guided walkthrough on Front Desk, Lab & Diagnostics, Pharmacy > Dispensing, the nursing record, and the SOAP note.

## ROY Workstation (home page)
id: workstation
menu: ROY Workstation
route: /
roles: everyone
keywords: workstation, home, home page, start page, landing page, main page, dashboard, live queue

- Your home page. The panels show what is happening across the hospital now.
- **Live Queue** jumps to the live patient queue. **Open** on any panel opens its full page.
- Click **Refresh** to reload the figures.

## My Workspace (your day, tasks, messages, leave)
id: my-workspace
menu: My Workspace > Tasks, inbox & messages (doctors: My Dashboard; nurses: Nursing Station)
route: /workspace
roles: everyone
keywords: my workspace, workspace, my day, my work, tasks, task, to do, todo, reminder, reminders, note, inbox, requests, messages, message a colleague, chat with colleague, team, progress, work clock, clock in, clock out, time tracker, leave, apply for leave, request leave, staff dashboard, collaboration

Your own day: **My Day**, **My Work**, **Inbox**, **Messages**, **Team**, **Progress**.
- Doctors and nurses do not have a separate page: these tabs are built into **My Dashboard** (doctors) and **Nursing Station** (nurses), after the **My patients** / **Nursing station** tab. Everyone else opens **My Workspace > Tasks, inbox & messages**.
- Add something: click **Task**, **Reminder** or **Note** at the top. Ask a colleague for something: **Ask** (it lands in their Inbox). **Message** opens a conversation. **Leave** requests leave.
- Work for your role (patients waiting, results to review, stock to act on, HMO follow-ups) appears under **My Day**. **Take it** turns one into your task; it closes by itself when the record is dealt with.
- Time worked is on the **Progress** tab. The work clock (Start work / Break / End work) is on My Day.

## Admin Dashboard
id: admin-dashboard
menu: Management > Admin Dashboard
route: /hospital/admin-dashboard
roles: admin, management
keywords: admin dashboard, hospital overview, at a glance, how is the hospital, waiting times, bed occupancy, alerts, pending registrations

- The whole hospital at a glance: patients waiting, average wait, bed occupancy, pending labs and prescriptions, and alerts.
- **Open Staff Registrations** takes you to staff waiting for approval.

## My Dashboard (doctors)
id: doctor-dashboard
menu: My Workspace > My Dashboard
route: /hospital/doctor
roles: doctor, admin, management
keywords: my dashboard, doctor dashboard, my patients, patients waiting for me, my appointments, today's appointments, results to review, lab results to review, image results, begin consultation, telemedicine, video call, join call, virtual consult

My Dashboard is a doctor's whole day on one page. The first tab, **My patients**, is the clinical view; the other tabs are your workspace (**My Day**, **My Work**, **Inbox**, **Messages**, **Team**, **Progress**).
- **My patients** shows today's appointments, your active encounters, lab and imaging results to review, and patients completed today.
- Start a consultation: click **Begin** next to the patient. Telemedicine: **Join** next to the video appointment.
- A patient appears here when the front desk checks them in to you, or when they are assigned to you at **Start Consultation** on the queue.
- Your appointments and schedule are in the same folder: **My Workspace > Appointments / My Schedule**.

## Nursing Station
id: nursing-station
menu: My Workspace > Nursing Station
route: /hospital/nurse, /hospital/nursing
roles: nurse, admin, ops, doctor, management, physiotherapist
keywords: nursing station, nurse station, nurse dashboard, ward round, handover, admission requests, critical flags, inpatients, waiting for nurse, bedside, vitals, nursing notes, flowsheet, observation chart, fluid balance, care plan, mar, medication administration

The Nursing Station is a nurse's whole day on one page. The first tab, **Nursing station**, is the ward; the other tabs are your workspace (**My Day**, **My Work**, **Inbox**, **Messages**, **Team**, **Progress**).
- The ward tab shows admission requests waiting on you, **Waiting for Nurse**, **Inpatients**, **Beds Available** and **Critical Flags**.
- Record vitals quickly: click **Vitals** on the patient, fill in, then **Save & Confirm Vitals**.
- Open a patient for their nursing record: **Detail**, **Notes**, **Vitals**, **Flowsheet**, **Fluid Balance**, **Care Plans**, **MAR** and **Charges**. Nursing notes are free text; you are never forced through a diagnosis.
- Guided walkthrough: **Show me how** inside the nursing record.

## Front Desk: checking a patient in
id: front-desk
menu: Patients & Flow > Front Desk
route: /hospital/front-desk, /hospital/display
roles: admin, ops, receptionist, management, nurse
keywords: front desk, reception, check in, check-in, checkin, register visit, register encounter, issue ticket, ticket, queue number, walk-in, walk in, arrival, arrived, new visit, display board, queue display, tv screen, doctor on seat, which doctor, assign room, consulting room, room board, pharmacy approval, approve drug, priority, assign a doctor, doctor to a room, doctors today, on seat

1. Search for the patient by name, phone or MRN. Try more than one spelling before deciding they are new; **New patient** at the top opens registration.
2. Pick the patient, then the visit type and department.
3. Choose the **Payer**: **Private** or **HMO / Insurance** (the membership number is filled from their record).
4. **Doctor** (optional): the list shows doctors on seat today - in a consulting room, clocked in, or on today's roster - with their room and how many patients are waiting for them. Search finds any doctor; **All doctors** shows everyone. Choosing a doctor fills in their consulting room. Leave it empty to send the patient to triage first.
5. Set the **Priority** (**Normal**, **Urgent** or **Emergency**) and the chief complaint, then **Register Encounter & Issue Ticket**. A patient sent to a doctor appears on that doctor's **My Dashboard** at once.
- **Consulting rooms today** (right): as each doctor arrives, click **Assign a doctor** next to a room and type their name. That puts them on seat for check-in. The cross frees the room.
- **Pharmacy approvals waiting** is always on the right. When pharmacy asks the desk to approve a drug it appears there: tick to approve, cross to reject.
- If the button says **Already on the queue**, the patient already has an open visit. Do not register them twice.
- **Display board** opens the waiting-room screen.

## PCE / Patients: finding or registering a patient
id: patients
menu: Patients & Flow > Patients (PCE)
route: /hospital/patients
roles: admin, ops, nurse, doctor, receptionist, management, physiotherapist
keywords: patients, pce, patient list, find patient, search patient, look up patient, new patient, register patient, create patient, add patient, duplicate, mrn, patient record

- Search by name, phone or MRN, then click the patient to open their chart.
- New patient: click **Register Patient**, fill in the form, and save. Search first: about 60,000 patients from the old system are already here, and a duplicate splits their history.
- Registering a patient does not put them on the queue. Check them in at **Front Desk** for today's visit.

## The patient chart (PCE)
id: patient-chart
menu: PCE / Patients > click a patient
route: /hospital/patients/:mrn
roles: admin, ops, nurse, doctor, receptionist, management, physiotherapist
keywords: patient chart, chart, patient record, full record, history, past visits, previous visits, old results, old lab results, previous results, past results, lab history, result history, trend, cover sheet, problems, problem list, meds, medications list, orders, notes, old notes, previous notes, labs, surgery, consent, specialist, allergy, add allergy, upload document, documents, referral letter, letter, follow-up, edit patient, patient details, demographics, immunisation record, new encounter

Open it from **PCE / Patients** (search, then click the patient), or **PCE** / **Open Full Chart** from the queue or consultation.
Tabs across the top: **Cover Sheet**, **Problems**, **Meds**, **Orders**, **Notes**, **Labs**, **Surgery**, **Consent**, **Specialist**.
- Everything back to 2016 is on the chart, including records migrated from the old system.
- Past and current lab results, with trends: the **Labs** tab. Past notes: the **Notes** tab. Past operations: the **Surgery** tab. Earlier visits: the **Cover Sheet**.
- Add an allergy: **Add Allergy**. Add a problem: **Add Problem**.
- Prescribe: **Write Prescription** / **Prescribe**. Order a lab: **Add Lab Order**.
- Start a visit from the chart: **New Encounter**.
- Letters: **Referral Letter** or **Generate Letter**. Follow-up: **Book Follow-up**.
- Consent: **Record Consent**, then **Save Consent**.
- Documents: **Upload Document**.
- Change name, phone or other details: **Edit Patient Info**, then **Save Changes**.
- Bills for this patient: **View Billing**.
- Uploaded files (scans, PDFs) migrated from the old system are listed but cannot be opened. Only the list came across. This applies to document files only. Migrated notes, lab results and imaging reports open normally.

## Queue & Flow: moving a patient through the visit
id: queue
menu: Patients & Flow > Queue & Flow
route: /hospital/queue
roles: admin, ops, nurse, doctor, management, physiotherapist
keywords: queue, queue and flow, patient flow, waiting list, triage, triage level, vitals, call patient, call into room, consulting room, start consultation, assign doctor, consult, workspace, generate bill, discharge, discharge patient, send home, open encounter, results ready, billing pending

Each patient row shows the next action for their current stage:
- **Awaiting triage**: click **Triage**, choose the level (**Immediate (Red)**, **Urgent (Orange)**, **Less Urgent**, **Non Urgent**), then **Confirm Triage**.
- **Triaged**: click **Vitals** to record vitals (**Save & Confirm Vitals**), or **Consult** to send them to a doctor.
- **Nurse assessment**: click **Call**, pick the room, then **Call into [room]**.
- **Called**: click **Start**. In the **Start Consultation** dialog, pick the doctor. This is what puts the patient on that doctor's My Dashboard.
- **Consulting, lab or pharmacy**: click **Workspace** to reopen the consultation.
- **Billing pending**: click **Generate Bill**, or **Discharge** to choose the destination (**Home**, **Admit to Ward**, **Referred**, and so on) and **Confirm Discharge**.
- Open a visit for someone not yet on the queue: **Open Encounter** at the top.
- The stages, in order: registered, triaged, nurse assessment, called, consulting, lab ordered, pharmacy, billing pending, discharged.

## The consultation workspace
id: consultation
menu: Queue & Flow > Start / Workspace, or My Dashboard > Begin
route: /hospital/queue
roles: doctor, admin, management
keywords: consultation, consult, consultation workspace, encounter, see patient, order lab, order lab test, lab request, order imaging, x-ray, scan request, radiology request, prescription, write prescription, prescribe, book surgery, theatre booking, request admission, admit patient, referral, referral letter, end consultation, finish consultation, pause, save note, save vitals, open full chart

Open it from **Queue & Flow** (**Start** or **Workspace** on the patient) or **My Dashboard** (**Begin**).
- Notes: write the SOAP note (see the SOAP note section) or click **Save Note**.
- Vitals: **Save Vitals**.
- Orders: **Order Lab Test**, **Order Imaging**, **Write Prescription**, **Book Surgery**.
- Admit: **Request Admission**. The request goes to the Nursing Station and Wards & Beds.
- Referral: **Generate Referral Letter**.
- **Pause** and **Resume** hold a consultation. **Call Patient** recalls them.
- **Open Full Chart** opens the patient's chart.
- Finish: **End Consultation**, or **Discharge**.

## Writing a SOAP note
id: soap-note
menu: Consultation workspace > note
route: /hospital/queue
roles: doctor, admin, management
keywords: soap, soap note, clinical note, consultation note, write note, chief complaint, history of presenting complaint, review of systems, examination, findings, assessment, diagnosis, add diagnosis, icd, icd-10, icd code, plan, locked section, section locked, can't open plan, plan locked, objective locked, sign note, signing, template, templates, smart phrase, all systems negative, order bar

Sections unlock in order: Subjective, Objective, Assessment, Plan.
1. **Subjective**: fill in **Chief Complaint**. This unlocks Objective. History of Presenting Complaint and Review of Systems are optional.
2. **Objective**: general examination first, then systems. The **Findings** button has templates by organ system, including **All systems Negative**.
3. **Assessment**: click **Add diagnosis** and search in words (for example "malaria"). The ICD-10 code fills itself. You never type a code. This unlocks Plan.
4. **Plan**: write the plan and use the order bar: **Medication**, **Allergy**, **Immunisation**, **Lab**, **Radiology**, **Procedure**. Orders are held until you sign.
5. Click **Sign note**. The note saves first, then the orders go out. Signing locks the note permanently.
- Every section has a **Template** button. Your own templates are listed first. To make one, click **New template** in that window.
- If Objective or Plan is locked, the section says why: no chief complaint, or no diagnosis yet.
- Guided walkthrough: the **Help** button on the note.

## Correcting a signed note (addendum)
id: note-addendum
menu: Patient chart > Notes, or the consultation workspace
route: /hospital/patients/:mrn
roles: doctor, nurse, admin, management
keywords: edit note, edit signed note, change note, correct note, correction, mistake in note, wrong note, delete note, undo sign, unsign, amend, amendment, addendum

Signed notes cannot be edited or deleted by anyone, including administrators. You add a correction instead:
1. Find the signed note and click **Amend**.
2. Write the correction and a one-line reason (for example "wrong dose recorded").
3. Click **Sign addendum**.
- The addendum shows directly under the original, with your name and the time. You can add more than one.
- Guided walkthrough: **Show me how** > "Correcting a signed note".

## Creating your own note templates
id: personal-templates
menu: Consultation workspace > SOAP note > Template > New template
route: /hospital/queue
roles: doctor, admin
keywords: my template, my templates, personal template, own template, create template, new template, make a template, build a template, save template, save as template, edit template, change template, delete template, share template, shared template, reuse text, phrases, type the same thing, typing the same, keep typing, same every time, retyping, smart phrases

Create one:
1. In the SOAP note, click **Template** on the section you are writing. On Subjective and Objective it is a menu: choose **Note templates**.
2. Click **New template** (bottom left of the template window).
3. Type a **Template name**.
4. Write phrases in the **Subjective**, **Objective**, **Assessment** and **Plan** boxes, one phrase per line. Fill only the boxes you need. Type **??** where a detail changes per patient (for example "Pain in the ?? knee for ?? days").
5. Optional: **Use what I've written in this section** copies in what you already typed in that section of the note.
6. Leave **Share with other doctors** off to keep it private, or turn it on so every doctor can use it. Only you can change it either way.
7. Click **Save template**.
Using and changing it:
- Your templates are listed first in the template window, marked **Yours**. Colleagues' shared ones are marked **shared**.
- Select one of yours, then **Edit** (then **Save changes**) or **Delete**. Notes already written with it do not change.
- Hospital (system) templates cannot be edited.
- Only doctors can create templates. **New template** always shows; if saving says the login is not linked to a staff record, an administrator has to link it.
- Guided walkthrough: the **Help** button on the note > "Creating your own template".

## Appointments
id: appointments
menu: My Workspace > Appointments
route: /hospital/appointments
roles: admin, ops, nurse, doctor, receptionist, management
keywords: appointment, appointments, book appointment, booking, make an appointment, reschedule, cancel appointment, no show, mark arrived, arrived, slots, slot management, clinic diary, doctor availability, available slot, next slot

- A doctor sees **My appointments**: only the patients booked into their own slots. The front desk, nurses, operations and management see every doctor's appointments.
- Book: **Book Appointment**, choose the patient and a free slot. Mark **Arrived** when they come in - that puts them straight onto the clinical queue.
- Slots belong to a doctor: when creating a slot, choose the doctor from the list (not typed), so the appointments booked into it appear on that doctor's My Appointments and My Schedule.
- **Next available slot** finds the soonest free slot. Cancel, no-show and complete are on each appointment.
- The whole hospital's diary (every doctor, theatre, audits, leave) is the **Hospital Calendar**.

## My Schedule
id: my-schedule
menu: My Workspace > My Schedule
route: /calendar/tasks
roles: admin, ops, nurse, doctor, management
keywords: my schedule, my calendar, schedule task, schedule a task, my diary, calendar tasks

Your own diary - nobody else's:
- the appointments booked to see you (doctors),
- the tasks assigned to you or that you created,
- the events you are invited to or created.
Add a task or event from the page; a task you create without choosing someone is yours. The whole hospital's diary is the **Hospital Calendar** (management and operations).

## Hospital Calendar
id: hospital-calendar
menu: Hospital Calendar (standalone, for management and operations)
route: /calendar
roles: admin, management, ops, quality_assurance, hr, finance
keywords: hospital calendar, calendar, theatre calendar, audits calendar, equipment servicing, expiring drugs, staff leave calendar, deliveries, hmo follow-ups, move event, reschedule

Everything happening across the hospital on one calendar: every doctor's appointments, theatre, audits, equipment servicing, maintenance, drugs expiring, staff leave, stock deliveries and HMO follow-ups. Each entry is the real record - drag an audit, service, maintenance job, delivery or follow-up to another day and the record moves with it. For your own day use **My Workspace > My Schedule**.

## Lab & Diagnostics
id: lab
menu: Clinical Services > Lab & Diagnostics
route: /hospital/lab
roles: admin, ops, nurse, doctor, lab, management
keywords: lab, laboratory, lab worklist, worklist, lab orders, order queue, sample, specimen, collect specimen, receive specimen, reject specimen, result, enter result, record result, verify, verify result, authenticate, release result, amend result, send out, reference range, test catalogue, turnaround, tat, critical value, critical result, stat, result template

Tabs: **Order Queue**, **Test Catalogue**, **Reference Ranges**, **Turnaround & Critical**.
Doctors' orders land on **Order Queue** immediately. STAT and urgent sort to the top. Open an order, then:
1. **Collect Specimen**, then **Receive Specimen** (or **Reject Specimen** with a reason).
2. **Record Result**. Values outside the reference range are flagged.
3. **Verify & Authenticate**. This releases the result to the doctor, who cannot see it until you verify.
- Wrong verified result: **Amend Result**. It keeps the original on record.
- Sending a test to an outside lab: **Send Out**.
- Critical values are flagged on **Turnaround & Critical**. Still phone the requesting doctor.
- Reusable result layouts: **Result Templates**.
- Guided walkthrough: **Show me how** at the top of the page.

## Pharmacy: dispensing
id: pharmacy-dispensing
menu: Pharmacy > Dispensing
route: /hospital/pharmacy
roles: admin, ops, nurse, doctor, pharmacist, management
keywords: pharmacy, dispense, dispensing, prescription queue, prescriptions, pending dispense, partially dispensed, override, allergy warning, drug interaction, return, returns, drug return, discount, request discount, signature, administer

Tabs: **Prescriptions** and **Returns**.
- Prescriptions arrive automatically when a doctor signs the note. Open one and click **Dispense**.
- If an allergy or interaction warning appears, **Override & Dispense** records your reason.
- Return: **Record Return**. Price reduction: **Request Discount** (sent for approval).
- **Capture Signature** records the collector's signature.
- Allergy lists start empty for migrated patients. Empty means never recorded, not "no allergies". Ask the patient.
- **Inventory Workspace** opens stock.
- Guided walkthrough: **Show me how** at the top of the page.

## Pharmacy: inventory and stock
id: pharmacy-inventory
menu: Pharmacy > Inventory
route: /hospital/pharmacy/inventory
roles: admin, ops, nurse, doctor, pharmacist, management
keywords: inventory, stock, stock level, drug stock, out of stock, low stock, expired, expiry, expiring, batch, batches, replenishment, reorder, trending, stock report, stock value, pricing, margin, cost price, sale price

Tabs: **Stock**, **Expired Stock**, **Replenishment**, **Trending**, **Report**.
- Filter by **Drugs**, **Consumables**, **Vaccines**; status shows **Critical**, **Warning**, **Monitor**, **Adequate**.
- Batches and expiry dates are on each item. Per-batch cost, sale price and margin are on the drug's **Pricing** tab.
- What to reorder: the **Replenishment** tab here, or **Procurement & Stores > Reorder plan & orders**.

## Pharmacy: quality control
id: quality-control
menu: Pharmacy > Quality Control
route: /quality-control
roles: admin, ops, pharmacist, management, quality_assurance
keywords: quality control, qc, deviation, batch release, register batch, recall, initiate recall, cold chain, temperature log, log reading, approve batch, reject batch, escalate, expired batch, dispose, disposal, missing expiry, medication error, medication incident

Pharmacy quality control on the live batches.
- **Expired stock**: batches past expiry still on the shelf. Dispose of them here (quantity and reason are recorded for NAFDAC).
- **Expiring soon**: everything that expires in the next 90 days, soonest first.
- **Missing expiry / cost**: batches with no expiry date (they cannot be watched for expiry) or no unit cost (left out of the stock value). Correct them on Pharmacy > Inventory.
- **Medication incidents**: incidents in the medication-error category, each with **Report**. Record a new one on Quality & Safety.
- **Recalls**: opened on the batch in Roy Books > Stock, which freezes it and traces every patient who received it.

## Radiology
id: radiology
menu: Clinical Services > Radiology
route: /hospital/radiology
roles: admin, ops, nurse, doctor, radiology, management
keywords: radiology, imaging, x-ray, xray, ultrasound, scan, ct, mri, echo, ecg, radiology worklist, radiology report, submit report, verify report, finalize report, amend report, start scan, schedule scan, modality

Tabs: **Worklist** and **TAT & Volume**.
Open a request, then **Schedule**, **Start Scan**, **Submit Report**, and **Verify & Finalize**.
- Change a finalized report: **Amend Report**.
- Older imaging and reports are on the patient's chart, not on this worklist.

## Surgical Theatre
id: theatre
menu: Clinical Services > Surgical Theatre
route: /hospital/theatre
roles: admin, ops, nurse, doctor, management
keywords: theatre, surgery, operation, surgical list, theatre schedule, book surgery, pre-op, checklist, who checklist, anaesthetic record, operative notes, op note, recovery, post-op, post op

Tabs: **Daily Schedule** and **All Cases**.
- Book a case from the consultation (**Book Surgery**), choosing from the procedure catalogue.
- Run the case in order: **Start Pre-Op** and **Save Checklist**, **Move to Theatre**, **Save Anaesthetic Record**, **Record Operative Notes**, **Send to Recovery**, **Record Post-Op Notes** (then **Save Post-Op Record**), **Mark Completed**.
- **Verify Operative Notes** locks them. Change them afterwards with **Amend Operative Notes**.

## Specialist Clinics
id: specialist-clinics
menu: Clinical Services > Specialist Clinics
route: /hospital/specialist
roles: admin, ops, nurse, doctor, management
keywords: specialist clinic, specialist note, specialty template, cardiology clinic, specialist consultation, clinic template

- Structured note templates by specialty. Choose the specialty and patient, then **Write Note**.
- Use these where a clinic has its own format instead of the general SOAP note.

## MCH / OB-GYN (antenatal, delivery, newborn)
id: mch
menu: Clinical Services > MCH / OB-GYN
route: /hospital/mch
roles: admin, ops, nurse, doctor, management
keywords: mch, maternity, antenatal, anc, anc visit, pregnancy, pregnant, booking visit, edd, delivery, record delivery, labour, birth, newborn, baby, newborn assessment, miscarriage, obstetrics, gynaecology, ob-gyn

Tabs: **ANC Register** and **Delivery Stats**.
- Antenatal visit: open the mother, then **Log Visit** and **Save Visit**.
- Delivery: **Record Delivery**. Then **+ Newborn Assessment** and **Save Assessment**. Registering the baby creates their own patient record linked to the mother.
- Outcomes: **Mark Referred** or **Mark Miscarriage**.

## Immunisation
id: immunisation
menu: Clinical Services > Immunisation
route: /hospital/immunisation, /hospital/immunisation/:patientId
roles: admin, ops, nurse, doctor, management
keywords: immunisation, immunization, vaccine, vaccination, vaccines due, overdue vaccines, baby vaccines, record dose, register baby, vaccination schedule, epi

- Filters: **All**, **Due Soon**, **Overdue**, **On Schedule**, **Complete**, **No record**.
- New child: **New Baby**, then **Register Baby**.
- Record a vaccine: **View Record** on the child, then **Record Dose(s)** and **Save Dose(s)**. Off-schedule vaccines: **Add Other Vaccine**.

## Wards & Beds
id: wards-beds
menu: Patients & Flow > Wards & Beds
route: /hospital/wards
roles: admin, ops, nurse, doctor, management, physiotherapist
keywords: ward, wards, bed, beds, free bed, empty bed, bed availability, available beds, occupancy, admit, admission, confirm admission, transfer, inpatient, bed maintenance, reserve bed, add ward, add bed

Tabs: **Ward Overview** and **Bed Detail**.
- Admitting: the doctor clicks **Request Admission** in the consultation. Then pick a free bed here and click **Confirm Admission**.
- Bed status: **Mark Available**, **Mark Maintenance**, **Mark Reserved**. Emptying a bed after discharge: **Free Bed**.
- From an occupied bed: **Vitals**, **Notes**, **Nursing record**, **Full record**.
- New wards and beds: **Add Ward** and **Add Bed**.

## Billing & Cashier
id: billing
menu: Roy Books > Billing & Cashier
route: /hospital/billing, /hospital/billing/:billId/invoice
roles: admin, finance
keywords: bill, billing, generate bill, create bill, invoice, print invoice, receipt, payment, take payment, record payment, cashier, pay, outstanding, balance, waive, write off, hmo claim, submit claim, claims, disputed bill, partial payment

Tabs: **Bills** and **HMO Claims**.
- Create a bill: on **Queue & Flow**, a patient in billing pending has **Generate Bill**. Add items with **Add Line (Consultation / Procedure / Misc)**, then **Generate Bill**.
- Take payment: open the bill, click **Record Payment**, then **Save**. Then **Receipt** or **Print Invoice**.
- HMO patients: **Submit HMO Claim**.
- Adjustments (need authority): **Waive** or **Write Off**.
- Doctors and nurses do not see this page. They hand over at the Generate Bill step on the queue.

## HMO & Coverage
id: hmo
menu: Roy Books > HMO & Coverage
route: /hospital/hmo
roles: admin, finance
keywords: hmo, insurance, coverage, cover, plan, hmo plan, tariff, hmo tariff, pre-authorisation, preauthorization, approval, hmo rules, nhis

- Set up HMO plans: **Add Plan**, then **Create Plan**. Coverage rules: **Add Rule**. Prices per HMO: **Tariff**.
- Filter by HMO and see its patients, admissions, appointments, billing, lab results and pharmacy.
- To check one patient's cover, look on their chart.

## Quality & Safety
id: quality-safety
menu: Quality & Compliance > Quality & Safety
route: /hospital/quality
roles: admin, ops, nurse, doctor, management, quality_assurance
keywords: incident, report incident, incident report, near miss, adverse event, fall, medication error, infection, infection control, hai, isolation, hefamaa, hefamaa checklist, patient safety, safety report

Tabs: **Incidents**, **Infection Control**, **HEFAMAA**.
- Report an incident: **Report Incident**, fill in date, time, department and description, then **Submit Report**.
- Infection: **Log Infection**.
- HEFAMAA checklist: open the **HEFAMAA** tab and click **Submit Checklist**.
- Report through this page rather than informally. The record protects the hospital and the staff involved.

## Reports
id: reports
menu: Reports > Write a report / Report library / Analytics
route: /reports/new, /reports/library, /hospital/reports
roles: admin, management, finance, quality_assurance, doctor, nurse, pharmacist, ops, receptionist
keywords: report, write a report, write report, create report, report library, saved reports, download report, word document, analytics, encounter report, incident report write-up, hmo account report, monthly report

- **Write a report** (/reports/new): pick the report type and the one record it is about (an incident, an audit, an HMO, a drug, an encounter, a month). Review the information gathered, then generate. **Download Word** saves it.
- **Report library**: reports already written. Open one or **Download Word**.
- **Analytics** (admin, management, finance, quality assurance): hospital-wide charts.
- The server decides which record types your role can report on.

## Digital Engagement (SMS, reminders, telemedicine)
id: engagement
menu: Management > Digital Engagement
route: /hospital/engagement
roles: admin, ops, management
keywords: sms, bulk sms, text message, reminder, send reminders, campaign, message template, telemedicine session, schedule session, video consult, patient communication, message logs

- Messages: **Send Message**, **Bulk SMS**, **Send Reminders**. Reusable wording: **New Template**, then **Save Template**. What was sent: **Message Logs**.
- Telemedicine: **New Session** or **Schedule Session**. Doctors join from **My Dashboard** with **Join**.

## Audits & Maintenance
id: audits-maintenance
menu: Quality & Compliance > Audits & Maintenance
route: /hospital/audits-maintenance
roles: admin, ops, quality_assurance, management
keywords: audit, audits, schedule audit, facility audit, maintenance, equipment, equipment servicing, maintenance task, repair, estate

Tabs: **Audits** and **Maintenance**.
- **Schedule Audit**, then **Start** and **Complete Audit**.
- **Add Maintenance Task**, then **Mark Complete** when done.

## Compliance & Audits
id: compliance
menu: Quality & Compliance > Compliance
route: /compliance
roles: admin, quality_assurance, management
keywords: compliance, ndpa, regulatory, governance, certificate, deviation report, recall, findings, observations, recommendations, ingest document, compliance score, hefamaa, audit trail

Where the hospital stands for HEFAMAA and NDPA, read live from the records.
- The **compliance score** is 100 less a deduction for each thing overdue or open today; **What is pulling the score down** lists each one and opens the page that fixes it.
- **HEFAMAA self-assessments**: recorded on Quality & Safety, listed here with their scores and follow-up dates.
- **Facility audits**: open audits (overdue ones in red) and those completed in the last six months, each with **Report**.
- **Audit trail**: whether the audit log is intact. Every action is recorded; clinical notes cannot be edited or deleted.

## Executive Overview
id: executive
menu: Management > Executive Overview
route: /executive, /executive/summary
roles: admin, management, finance
keywords: executive, executive overview, control centre, control center, kpis, hospital performance, profit, cash, revenue overview, what needs attention, executive report, board

- The hospital on one page: billing (HMO vs private), profit and cash from Roy Books, what HMOs owe, today's patients and beds, pharmacy stock, quality, and staff.
- A ranked list shows what needs attention. Every figure opens the page that owns it.
- **Executive report** produces a written summary.

## Roy Books (finance hub)
id: roy-books
menu: Roy Books > Control Tower, Receivables, Purchases & Payables, Stock & Pharmacy Valuation, Banking, Journals & Ledger, Financial Statements, Report Center, Fixed Assets, Close & Controls, Setup
route: /finance/books, /finance/books/sales, /finance/books/purchases, /finance/books/stock, /finance/books/banking, /finance/books/ledger, /finance/books/statements, /finance/books/reports, /finance/books/assets, /finance/books/close, /finance/books/setup
roles: admin, finance, management, pharmacist, quality_assurance
keywords: roy books, books, finance, accounting, one-off payee, payee, pay to the order of, pay someone without a supplier, invoice number, which invoice number, start invoicing, continue numbering, ledger, general ledger, journal, journals, journals by type, sales journal, cash receipts journal, cash disbursements journal, purchase journal, general journal, cost of goods sold journal, fixed assets journal, trial balance, profit and loss, p&l, balance sheet, financial statements, receivables, payables, supplier payment, vendor payment, pay supplier, one-off payment, pay someone, payment window, bank, banking, bank reconciliation, fixed assets, assets in the books, depreciation, asset register, month end, period close, year end, budget, chart of accounts, sage, control tower, valuation, invoice register, last invoice, next invoice number, record receipt, void invoice, delete entry, delete journal, data issues, stock count, opening stock, csv, export

Bills, cashier payments, HMO claims and pharmacy stock post here automatically once the go-live date is set. Sage's history (2010 to its last export) is in the same ledger, so any report can start in 2010 and end today.
- **Control Tower**: finance overview. A yellow banner means **Data issues** are open.
- **Receivables (Patients & HMOs)**: **Invoice register** is the one list of every invoice (Sage's and Roy Books', paid or not), with the **last invoice raised** and the **next invoice number** at the top and a Status filter (open, paid, void, draft). Click an invoice, then **Record receipt** to take payment against it. **Receipts** lists Roy Books receipts and, tagged Sage, Sage's. **Aged receivables** and every name list are A to Z.
- **Void an invoice**: open it and press **Void**; you are asked for a reason. Stock and postings are reversed. If it was the last number issued, the next invoice reuses the number and the voided one is renamed "-VOID".
- **Purchases & Payables**: **Pay supplier** opens the Payment window (like Sage's Payments screen): tick **Pay** on the bills being paid; the **Apply to expenses / assets** tab codes amounts to an expense or a fixed-asset account (it shows the asset account's value before and after). **One-off payment** pays anyone with no supplier record ("Pay to the order of"). A bill's panel has **Pay this bill**.
- **Stock & Pharmacy Valuation**: **Ledger · books · shelf** compares the inventory accounts, Roy Books' valued stock and the pharmacy's shelves; **Stock counts** shows every batch on the shelf (expiry, cost, last counted) before counting.
- **Banking**: bank accounts and reconciliation.
- **Journals & Ledger**: **Journal entries** (each journal; Sage's general-journal entries tagged Sage), **Journals by type** (Sales, Cash Receipts, Cash Disbursements, Purchases, Cost of Goods Sold, General, Inventory Adjustments, Fixed Assets - Sage's column layout, any period), **General ledger** (one account in Sage's layout: monthly beginning balance, every line, running balance; search as you type), **Trial balance**, **Chart of accounts** (balance at any date from the whole ledger, entries, first and last entry; click a balance for its lines).
- **Delete entry**: open a journal posted by mistake and press **Delete entry** (asks for a reason). The exact reversal is posted on the same date, every report returns to how it was, and the pair disappears from the ledger detail (it stays in Journal entries and the audit trail). Documents (invoices, receipts, payments) are voided instead.
- **Financial Statements**: P&L, balance sheet, cash flow. **Report Center**: Royan's reports first (HMO vs private, HMO monthly bills, claims ageing, Hope vs Sage), then statements, receivables, spending, banking, Sage history; **Show the other Sage 50 report types** reveals the rest.
- **Fixed Assets**: **Assets in the books** shows every fixed-asset account from the ledger - cost, accumulated depreciation, net book value and every purchase (search "generator", "ambulance", "2021"); **Add to register** starts a depreciation schedule without a new journal. **Depreciation register**, **Depreciation**, **Categories**.
- **Close & Controls**: **Data issues** lists every difference between Sage, Hope, the books and the shelves (e.g. no books after Sage's last export, pharmacy stock not in the books, payers with no Sage account) with what to do: accept with a reason, link a payer's Sage account, or post a correcting journal (numbered FIX-). **Check again** re-runs it. Also month-end: **Close period**, **Year-end close**, **Reopen**.
- **Setup**: chart of accounts, posting rules, settings (go-live date), budgets (rename, copy, delete, reopen), **Sage uploads** (upload the next Sage export: upload, Check, Load), **Payers (HMO / private)**.
- **CSV** buttons download exactly the table on screen (same columns, names not ids, amounts as numbers).

## Credit Control & Alerts
id: credit-control
menu: Roy Books > Credit Control & Alerts
route: /finance/ar, /finance/reports/ar/:bucket
roles: admin, finance, management
keywords: credit control, ar, accounts receivable, aging, ageing, overdue, debtors, who owes, collection, payment matching, run match, alert rules, alerts, hmo debt

- What HMOs and corporate payers owe, aged (Hope's billing less what Sage shows they paid; the books once live). The list is A to Z.
- The red **N active alerts - open** badge opens the alert worklist; each debtor has **Statement**, **Record receipt**, **Account** and **HMO bill**. **Show all** lists every alert; **Alert rules** opens the rules tab (**New Rule**, then **Create Rule**).
- Tabs: Invoice Match, P&L, Cash Flow (a run-rate forecast), Credit Risk.

## Fee Schedule and Payment Gateway
id: fees-payments
menu: Roy Books > Fee Schedule, Roy Books > Payment Gateway
route: /admin/fee-schedule, /admin/payments
roles: admin, finance
keywords: fee schedule, price list, tariff, service price, consultation fee, add service, change price, payment gateway, online payment, card payment, verify payment, paystack, flutterwave

- **Fee Schedule**: the hospital price list. **Add Service** for a new item.
- **Payment Gateway**: online payments. **Initiate Payment**, then **Verify** to confirm one arrived.

## HR
id: hr
menu: HR
route: /hr, /hospital/hr
roles: admin, hr, management
keywords: hr, human resources, staff records, staff directory, add staff, shift, shifts, roster, shift roster, leave approval, timesheet, timesheets, payroll, salary, payslip

Tabs: **Overview**, **Staff directory**, **Shift roster**, **Leave**, **Timesheets**, **Payroll**.
- New employee: **Add staff record**.
- Staff request their own leave from **My Workspace > Leave**. HR approves it here on **Leave**.
- Payroll posts to Roy Books.

## Procurement & Stores
id: procurement
menu: Pharmacy > Reorder plan & orders / Supplier records
route: /procurement, /operations/suppliers
roles: admin, ops, pharmacist, finance, quality_assurance, management
keywords: procurement, purchase, purchase order, stock order, order stock, reorder, reorder plan, what to order, supplier, suppliers, add supplier, supplier metrics, stores, delivery, receive stock

Tabs on Reorder plan & orders: **Reorder plan**, **Stock orders**, **Suppliers**.
- **Reorder plan** works out what to order from actual pharmacy use: **Order now**, **Order soon**, **Enough**, **May expire before use**.
- **Stock orders** run from request to delivery and close by themselves when the stock is received.
- **Supplier records** (admin and ops): **Add Supplier**, then **Create**. Performance: **View Metrics**.

## Patient Relations (HMO and corporate payers)
id: patient-relations
menu: Management > Patient Relations
route: /relations
roles: admin, finance, management
keywords: patient relations, crm, payer, payers, hmo relationship, corporate client, follow up hmo, hmo contacts, call log, who is slipping

- Every HMO and corporate payer: services billed, what they owe and how late, and contacts.
- Record a call or meeting: **Log**. Finish a follow-up: **Done**. Follow-ups you set appear on **My Workspace > My Day**.

## Administration: users and registrations
id: admin-users
menu: Users & Access > User Access / Staff Registrations / Audit Log
route: /admin/users, /admin/registrations
roles: admin
keywords: user access, new user, create account, add user, staff account, role, change role, permissions, access, reset password, forgot password, password, staff registration, approve registration, approve staff, reject registration, sign up, register account, duplicate staff, hr record, link login, already in hr, approve, registered, registration, approve doctor, new staff, onboarding staff

- New staff account: **User Access**, then **New user**. Tick every role the person needs (access is the union); the preview shows exactly which menus they will see. A reason is required.
- Change someone's access: **Edit access**. Password: **Password**. Deactivate: **Deactivate**.
- Self-registered staff: **Staff Registrations**, then **Approve** or **Reject**. When approving, the system looks for the person in HR first: if HR already has them (same email, or the same name), the login is attached to that existing record - HR never holds the same person twice. Only someone genuinely new gets a new HR record.
- Every login has its HR record from the start, so the person appears in HR and on the Team tab straight away.
- Forgotten password (non-admins): ask an administrator to reset it.

## Administration: system tools
id: admin-tools
menu: System > Workflow / Reliability Console / Agent Stack / Settings; Management > Clinical Data Explorer; Users & Access > Audit Log
route: /workflow, /admin/reliability, /admin/clinical-explorer, /admin/audit-log, /settings, /agents, /agents/:name
roles: admin, management, ops
keywords: workflow, automation, reliability, reliability console, errors, system health, something broken, bug, clinical data explorer, query data, audit log, who did what, activity log, settings, profile, notifications, agents, agent stack

- **Reliability Console** (admin): system health and errors. Start here if something behaves oddly.
- **Audit Log** (admin): who did what and when.
- **Clinical Data Explorer** (admin, management, ops): read-only search across clinical data, including migrated records. **Run Full Audit** checks data health.
- **Workflow** (admin): automated processes.
- **Agent Stack** (admin, management): the background agents and what each monitors.
- **Settings** (admin): profile, preferences and notifications.

## Things the system does not do
id: not-available
menu: none
route: none
roles: everyone
keywords: can i edit, can i delete, delete, undo, unsign, edit signed, open old document, legacy document, old files, allergy history, type icd code, see other pages, not available, doesn't exist, does not exist, is there a way

Say these plainly when asked:
- Signed clinical notes cannot be edited or deleted by anyone. Use an addendum (**Amend**).
- Document files (scans, PDFs) migrated from the old Hope system are listed but cannot be opened. Only the list came across. Migrated notes, lab results and imaging reports do open.
- No allergy history came from the old system. An empty allergy list means "never recorded".
- Shared hospital (system) note templates cannot be edited. Doctors create their own instead (**Template** > **New template**).
- You do not type ICD-10 codes. You search the diagnosis in words and the code fills itself.
- Roy cannot prescribe, order tests, discharge, admit, book appointments or create bills from chat. Those are done on their pages.
- You cannot see pages outside your role. An administrator changes access in **User Access**.
- A verified lab result or finalized radiology report is not deleted. It is amended (**Amend Result** / **Amend Report**) and the original stays on record.
