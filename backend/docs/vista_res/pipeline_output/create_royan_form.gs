function myFunction() {
  /**
   * SynbotHealth — Royan Hospital System Requirements
   *
   * HOW TO USE:
   * 1. Go to https://script.google.com → New project
   * 2. Delete the placeholder code and paste this entire script
   * 3. Click ▶ Run
   * 4. First run: click "Review permissions" → pick your account → Allow
   * 5. Wait ~30 seconds → open "Execution log" → copy the form URLs
   */

  var BOT_NAME    = "SynbotHealth";
  var CLIENT_NAME = "Royan Hospital";

  function buildHospitalForm() {
    var form = FormApp.create("SynbotHealth — Royan Hospital System Requirements");
    form.setDescription("This questionnaire helps the SynbotHealth team understand exactly how Royan Hospital operates today — and where you want the system to take you. Answers will directly shape the modules we configure, the workflows we automate, and the integrations we prioritise. Estimated time: 25–35 minutes.");
    form.setCollectEmail(false);
    form.setIsQuiz(false);

    // ── Intro questions ───────────────────────────────────────
    form.addParagraphTextItem()
      .setTitle("Your full name");

    form.addMultipleChoiceItem()
      .setTitle("Your role at Royan Hospital")
      .setChoiceValues(["Hospital Director / CEO", "Chief Medical Officer / Medical Director", "Head of Nursing", "Head of IT / Systems", "Head of Finance / Billing", "Department Head (specify in notes)", "Other"]);

    form.addMultipleChoiceItem()
      .setTitle("Approximately how many inpatient beds does Royan Hospital currently operate?")
      .setChoiceValues(["Under 20", "20–50", "51–100", "101–200", "Over 200"]);

    form.addMultipleChoiceItem()
      .setTitle("Average number of OPD (outpatient) visits per day")
      .setChoiceValues(["Under 30", "30–80", "81–150", "151–300", "Over 300"]);

    form.addMultipleChoiceItem()
      .setTitle("Average number of A&E (emergency) presentations per day")
      .setChoiceValues(["Under 10", "10–25", "26–50", "Over 50"]);

    form.addMultipleChoiceItem()
      .setTitle("Is DRM Hope currently your Hospital Management System (HMS)?")
      .setChoiceValues(["Yes — DRM Hope is our current HMS", "Yes — DRM Hope is installed but not fully in use", "No — we use different software (please specify below)", "No — we do not currently use any HMS"]);

    form.addParagraphTextItem()
      .setTitle("If you use different HMS software, please name it (optional)");

    form.addMultipleChoiceItem()
      .setTitle("How many HMO / insurance providers does the hospital currently work with?")
      .setChoiceValues(["None", "1–3", "4–10", "More than 10"]);

    form.addMultipleChoiceItem()
      .setTitle("Target go-live timeline for SynbotHealth")
      .setChoiceValues(["ASAP (within 1 month)", "1–3 months", "3–6 months", "6–12 months", "Flexible / not yet decided"]);

    // ── Department sections ────────────────────────────────

    // 🪪 Patient Registration & Identity
    form.addPageBreakItem()
      .setTitle("🪪 Patient Registration & Identity")
      .setHelpText("Covers how patients are registered, identified, and tracked across all visits.");

    form.addMultipleChoiceItem()
      .setTitle("How are new patients currently registered at Royan Hospital?")
      .setChoiceValues(["Paper registration forms only", "Paper + Excel/spreadsheet", "Basic computer entry (no formal HMS)", "Dedicated HMS registration module"]);

    form.addMultipleChoiceItem()
      .setTitle("Are patients issued a unique Medical Record Number (MRN) that tracks them across all visits?")
      .setChoiceValues(["Yes, consistently", "Yes, but inconsistently applied", "No"]);

    form.addCheckboxItem()
      .setTitle("Which of the following registration capabilities do you want SynbotHealth to handle?")
      .setChoiceValues(["Automated MRN generation", "Digital registration form (no paper)", "Returning patient lookup", "Duplicate record detection", "Patient photo capture", "Next-of-kin & emergency contact capture", "HMO / insurance details at registration", "Patient consent form (digital)", "Patient-facing registration kiosk / QR self-check-in"]);

    form.addScaleItem()
      .setTitle("How high a priority is a streamlined registration process for your hospital?")
      .setBounds(1, 5)
      .setLabels("Low priority", "Top priority");

    form.addParagraphTextItem()
      .setTitle("Any specific registration pain points or requirements? (e.g. walk-in volume, language needs)");


    // 🔢 Queue Management & Appointments
    form.addPageBreakItem()
      .setTitle("🔢 Queue Management & Appointments")
      .setHelpText("Royan Hospital operates OPD with a queue system plus phone/online booking. This section covers how that flow is managed.");

    form.addMultipleChoiceItem()
      .setTitle("How is the OPD patient queue managed today?")
      .setChoiceValues(["Manual (paper tickets / verbal calling)", "Basic numbering system (printed tickets)", "Digital queue screen with number calling", "Fully integrated queue + appointment system"]);

    form.addCheckboxItem()
      .setTitle("Which appointment booking channels do you currently offer? (select all that apply)")
      .setChoiceValues(["Phone / front desk", "Walk-in (no appointment)", "WhatsApp booking", "Website / online form", "SynbotHealth AI chat booking"]);

    form.addCheckboxItem()
      .setTitle("Which queue & appointment features do you want SynbotHealth to provide?")
      .setChoiceValues(["Real-time digital queue display", "SMS/WhatsApp queue notifications", "Online appointment booking portal", "Doctor-specific scheduling", "Appointment reminders (SMS/email)", "Triage-based queue priority", "Multi-department queue routing", "No-show tracking & rescheduling", "Daily appointment dashboard for staff", "Specialty clinic scheduling (Cardiology, OB/GYN, etc.)"]);

    form.addScaleItem()
      .setTitle("How critical is improving queue and appointment management for Royan Hospital?")
      .setBounds(1, 5)
      .setLabels("Low priority", "Top priority");

    form.addParagraphTextItem()
      .setTitle("Describe your busiest OPD bottleneck — where does the queue typically break down?");


    // 🚨 Accident & Emergency (A&E)
    form.addPageBreakItem()
      .setTitle("🚨 Accident & Emergency (A&E)")
      .setHelpText("Royan Hospital runs a 24/7 A&E with ambulance services and emergency triage. This section covers the full emergency workflow.");

    form.addMultipleChoiceItem()
      .setTitle("How is A&E patient flow managed today?")
      .setChoiceValues(["Manual paper triage and records", "Paper triage + basic computer logging", "Semi-digital (some parts on software)", "Fully digital ED management"]);

    form.addCheckboxItem()
      .setTitle("Which A&E capabilities do you want SynbotHealth to support?")
      .setChoiceValues(["Digital triage assessment form", "Emergency queue bypass", "Real-time A&E patient tracking board", "ED-to-ward admission workflow", "Ambulance dispatch and arrival logging", "A&E disposition tracking", "Resuscitation and code alerts", "ED wait time monitoring", "Emergency medication administration log"]);

    form.addScaleItem()
      .setTitle("How critical is A&E digital management for your hospital?")
      .setBounds(1, 5)
      .setLabels("Low priority", "Top priority");

    form.addParagraphTextItem()
      .setTitle("Any specific A&E workflow challenges you want the system to solve?");


    // 🛏️ Inpatient Wards & Bed Management
    form.addPageBreakItem()
      .setTitle("🛏️ Inpatient Wards & Bed Management")
      .setHelpText("Covers admissions, ward rounds, daily nursing care, bed allocation, and discharge processes.");

    form.addMultipleChoiceItem()
      .setTitle("How are inpatient admissions and bed management handled today?")
      .setChoiceValues(["Fully manual (paper admission forms, notebook bed register)", "Paper-based with some Excel tracking", "Partial software (one area digital, rest manual)", "Fully digital admission and bed system"]);

    form.addCheckboxItem()
      .setTitle("Which inpatient / ward management features do you want?")
      .setChoiceValues(["Digital admission form (Admission, Discharge, Transfer — ADT)", "Real-time bed availability dashboard", "Ward round documentation", "Vitals recording (nursing)", "Fluid balance / intake & output tracking", "Inpatient medication administration record (MAR)", "Nursing shift handover notes", "Discharge planning & summary", "Inpatient investigation ordering", "Isolation / infection alert flags", "ICU / High-dependency unit tracking"]);

    form.addScaleItem()
      .setTitle("How critical is digital inpatient / ward management for your hospital?")
      .setBounds(1, 5)
      .setLabels("Low priority", "Top priority");

    form.addParagraphTextItem()
      .setTitle("Any specific inpatient workflow challenges? (e.g. bed allocation disputes, lost paper files)");


    // 📋 Clinical Documentation & Orders
    form.addPageBreakItem()
      .setTitle("📋 Clinical Documentation & Orders")
      .setHelpText("Covers how consultations are documented, diagnoses recorded, and orders for investigations or treatments are placed.");

    form.addMultipleChoiceItem()
      .setTitle("How do doctors currently document consultations and clinical notes?")
      .setChoiceValues(["Handwritten paper notes only", "Typed notes in Word / Google Docs", "EMR / clinical module in existing HMS", "Mixed (some digital, some paper)"]);

    form.addCheckboxItem()
      .setTitle("Which clinical documentation capabilities do you need?")
      .setChoiceValues(["Structured consultation note (SOAP format)", "Patient problem list", "Lab investigation ordering", "Radiology / imaging ordering", "Electronic prescription (Rx generation)", "Referral / consult request tracking", "Clinical reminders & alerts", "Patient health summary view", "Allergy and adverse drug reaction tracking", "Medical certificate generation", "Death certificate / summary generation", "ICD-10 / diagnosis coding"]);

    form.addScaleItem()
      .setTitle("How critical is digital clinical documentation for Royan Hospital?")
      .setBounds(1, 5)
      .setLabels("Low priority", "Top priority");

    form.addParagraphTextItem()
      .setTitle("Any specific documentation pain points? (e.g. lost files, illegible handwriting, slow referral process)");


    // 🧪 Laboratory & Diagnostics
    form.addPageBreakItem()
      .setTitle("🧪 Laboratory & Diagnostics")
      .setHelpText("Royan Hospital runs in-house laboratory services covering FBC, LFT, KFT, malaria, HIV, urine analysis, cultures, and more.");

    form.addMultipleChoiceItem()
      .setTitle("How are laboratory test orders and results managed today?")
      .setChoiceValues(["Manual paper request forms and paper results", "Paper requests, results typed into Excel", "Lab software (standalone, not connected to clinical system)", "Integrated lab module"]);

    form.addCheckboxItem()
      .setTitle("Which tests does your laboratory currently perform in-house? (select all that apply)")
      .setChoiceValues(["Full Blood Count (FBC)", "Liver Function Tests (LFT)", "Kidney Function Tests (KFT / U&E)", "Blood glucose / HbA1c", "Lipid profile / cholesterol", "Urine analysis (dipstick + microscopy)", "Malaria RDT / microscopy", "HIV screening", "Pregnancy test (urine / serum)", "Culture & sensitivity (microbiology)", "Blood grouping & cross-matching", "Hepatitis B & C serology", "Widal test (typhoid)", "Semen analysis", "Thyroid function tests (TFT)", "Hormonal assays (FSH, LH, Prolactin, etc.)", "Point-of-care testing (bedside glucometer, etc.)", "Send-out / outsourced tests (reference lab)"]);

    form.addCheckboxItem()
      .setTitle("Which laboratory management features do you want SynbotHealth to provide?")
      .setChoiceValues(["Electronic lab order from doctor's workstation", "Sample collection & tracking (specimen log)", "Digital result entry by lab scientist", "Critical result alerts", "Patient result notification (SMS)", "Reference range display", "Lab TAT (turnaround time) monitoring", "Cumulative result history view", "LOINC / standard test coding", "Send-out specimen tracking", "Lab workload reporting"]);

    form.addScaleItem()
      .setTitle("How critical is an integrated laboratory system for Royan Hospital?")
      .setBounds(1, 5)
      .setLabels("Low priority", "Top priority");

    form.addParagraphTextItem()
      .setTitle("Any lab-specific challenges? (e.g. lost results, delay in notifying doctors, paper result filing)");


    // 🩻 Radiology, Imaging & Cardiac Diagnostics
    form.addPageBreakItem()
      .setTitle("🩻 Radiology, Imaging & Cardiac Diagnostics")
      .setHelpText("Royan Hospital provides X-ray, Ultrasound, ECG, and Echocardiography. This section covers the imaging and diagnostic workflow.");

    form.addCheckboxItem()
      .setTitle("Which diagnostic imaging / cardiac equipment does Royan Hospital currently have? (select all that apply)")
      .setChoiceValues(["X-ray (conventional)", "Ultrasound machine", "ECG (electrocardiography)", "Echocardiography (Echo / cardiac ultrasound)", "Doppler ultrasound", "CT scan", "MRI", "Mammography", "Digital X-ray (DR/CR)", "Fluoroscopy", "Bone densitometry (DEXA scan)", "Endoscopy (upper GI / lower GI)"]);

    form.addMultipleChoiceItem()
      .setTitle("How are radiology / imaging requests and reports currently managed?")
      .setChoiceValues(["Paper request form; radiographer gives paper result", "Paper request; radiologist types report in Word", "Standalone radiology software (not connected to HMS)", "Integrated radiology module"]);

    form.addCheckboxItem()
      .setTitle("Which radiology & imaging management features do you need?")
      .setChoiceValues(["Electronic imaging request from doctor", "Digital radiology report entry", "DICOM image storage (PACS)", "ECG report storage and linking", "Echo / cardiac imaging report module", "Imaging TAT monitoring", "Abnormal finding alerts", "Image sharing with referring doctor", "Imaging workload & revenue reporting"]);

    form.addScaleItem()
      .setTitle("How critical is integrated radiology / imaging management for your hospital?")
      .setBounds(1, 5)
      .setLabels("Low priority", "Top priority");

    form.addParagraphTextItem()
      .setTitle("Any imaging workflow challenges? (e.g. lost films, delayed reports, no digital storage)");


    // 💊 Pharmacy & Medication Management
    form.addPageBreakItem()
      .setTitle("💊 Pharmacy & Medication Management")
      .setHelpText("Royan Hospital operates a full-service pharmacy dispensing to both inpatients and outpatients. This section covers all aspects of pharmacy management.");

    form.addMultipleChoiceItem()
      .setTitle("How is the pharmacy currently managed?")
      .setChoiceValues(["Fully manual (paper prescriptions, paper stock book)", "Paper prescriptions + basic Excel stock tracking", "Standalone pharmacy software (not connected to clinical system)", "Integrated pharmacy module"]);

    form.addCheckboxItem()
      .setTitle("Which pharmacy management features do you need SynbotHealth to provide?")
      .setChoiceValues(["Electronic prescription reception", "Drug inventory & stock management", "Drug-drug interaction checking", "Allergy / contraindication checking", "Dispensing confirmation & patient notification", "Outpatient prescription tracking", "Inpatient medication administration integration", "Controlled substance register", "Automatic ward stock replenishment", "Drug return / wastage logging", "Supplier purchase order management", "Chronic prescription / repeat refill management", "Pharmacy revenue reporting", "National Drug File / formulary management"]);

    form.addScaleItem()
      .setTitle("How critical is integrated pharmacy management for your hospital?")
      .setBounds(1, 5)
      .setLabels("Low priority", "Top priority");

    form.addParagraphTextItem()
      .setTitle("Any pharmacy-specific challenges? (e.g. stockouts, prescription errors, reconciliation difficulty)");


    // 🩺 Nursing & Patient Care
    form.addPageBreakItem()
      .setTitle("🩺 Nursing & Patient Care")
      .setHelpText("Covers all nursing documentation — vitals, care plans, medication administration, shift handover, and direct patient care tasks.");

    form.addMultipleChoiceItem()
      .setTitle("How are nursing records (vitals, care notes, MAR) documented today?")
      .setChoiceValues(["All paper (observation charts, nursing notes)", "Paper nursing notes + some Excel sheets", "Partial digital (e.g. vitals on a tablet, but MAR on paper)", "Mostly digital nursing module"]);

    form.addCheckboxItem()
      .setTitle("Which nursing management features do you need?")
      .setChoiceValues(["Digital vitals recording", "Nursing assessment form", "Nursing care plan", "Medication administration record (MAR)", "IV fluid / intake-output chart", "Pain score tracking", "Wound care documentation", "Nursing shift handover report", "Fall risk & pressure ulcer assessment", "Patient call / escalation system"]);

    form.addScaleItem()
      .setTitle("How critical is digital nursing documentation for your hospital?")
      .setBounds(1, 5)
      .setLabels("Low priority", "Top priority");

    form.addParagraphTextItem()
      .setTitle("Any nursing-specific pain points? (e.g. lost observation charts, MAR errors, handover gaps)");


    // 🔬 Surgical Services
    form.addPageBreakItem()
      .setTitle("🔬 Surgical Services")
      .setHelpText("Royan Hospital performs both elective and emergency surgery including breast, thyroid, colorectal, GI, hernia, and orthopaedic procedures.");

    form.addMultipleChoiceItem()
      .setTitle("How is the surgical theatre managed today?")
      .setChoiceValues(["Fully manual (paper registers, verbal scheduling)", "Paper forms + Excel theatre list", "Standalone surgical software", "Integrated surgical module in HMS"]);

    form.addMultipleChoiceItem()
      .setTitle("Approximate number of surgical cases per week")
      .setChoiceValues(["Under 5", "5–15", "16–30", "Over 30"]);

    form.addCheckboxItem()
      .setTitle("Which surgical management features do you need?")
      .setChoiceValues(["Surgical scheduling / theatre list", "Pre-operative assessment checklist", "Anaesthetic record", "Intraoperative nursing count (swabs/instruments)", "Operative notes (surgeon's report)", "Post-operative recovery room monitoring", "Surgical site infection tracking", "Surgical consent management", "Elective vs emergency theatre prioritisation", "Surgical outcome & complication recording"]);

    form.addScaleItem()
      .setTitle("How critical is a digital surgical management system for Royan Hospital?")
      .setBounds(1, 5)
      .setLabels("Low priority", "Top priority");

    form.addParagraphTextItem()
      .setTitle("Any surgical workflow challenges? (e.g. theatre scheduling conflicts, consent issues, missing operative notes)");


    // 🤱 Maternal & Child Health (MCH / OB-GYN)
    form.addPageBreakItem()
      .setTitle("🤱 Maternal & Child Health (MCH / OB-GYN)")
      .setHelpText("Royan Hospital's OB-GYN department manages antenatal care, delivery, postnatal, fertility, gynecological conditions, and pediatrics.");

    form.addMultipleChoiceItem()
      .setTitle("How is antenatal and maternal care documented today?")
      .setChoiceValues(["Antenatal card only (paper)", "Paper cards + ward register", "Partial digital", "Integrated MCH module"]);

    form.addCheckboxItem()
      .setTitle("Which Maternal & Child Health features do you need?")
      .setChoiceValues(["Antenatal booking form (ANC registration)", "Antenatal visit schedule & tracking", "Growth chart / fundal height tracking", "Partograph (labour progress monitoring)", "Delivery record", "Postnatal follow-up tracking", "Newborn care record", "Immunisation schedule (child health)", "Gynaecology consultation notes", "Family planning counselling record", "Physiotherapy referral from OB/GYN", "Feto-maternal surveillance record"]);

    form.addScaleItem()
      .setTitle("How critical is a dedicated Maternal & Child Health module for Royan Hospital?")
      .setBounds(1, 5)
      .setLabels("Low priority", "Top priority");

    form.addParagraphTextItem()
      .setTitle("Any specific MCH / OB-GYN workflow challenges?");


    // 🫀 Specialist Clinics
    form.addPageBreakItem()
      .setTitle("🫀 Specialist Clinics")
      .setHelpText("Royan Hospital runs specialist clinics in Cardiology, Gastroenterology, Urology, Orthopaedics, Pediatrics, and Family Medicine.");

    form.addCheckboxItem()
      .setTitle("Which specialist clinics are currently active at Royan Hospital?")
      .setChoiceValues(["Cardiology", "Gastroenterology", "Urology", "Family Medicine / General Practice", "Orthopaedics", "Pediatrics", "Chronic Disease Clinic (Diabetes, Hypertension)", "Physiotherapy & Rehabilitation", "Ophthalmology / Eye Clinic", "ENT (Ear, Nose & Throat)", "Dermatology", "Oncology", "Neurology", "Psychiatry / Mental Health", "Dental"]);

    form.addCheckboxItem()
      .setTitle("Which specialist clinic management features do you need?")
      .setChoiceValues(["Specialty-specific consultation note templates", "Specialty clinic appointment scheduling", "Chronic disease register / registry", "Recall and review scheduling", "Referral from GP to specialist within hospital", "Physiotherapy session notes & exercise plans", "Cardiology diagnostic report module (ECG / Echo)", "Paediatric growth chart (weight, height, head circumference)", "Vaccination record for paediatric patients"]);

    form.addScaleItem()
      .setTitle("How critical are specialty clinic management features for Royan Hospital?")
      .setBounds(1, 5)
      .setLabels("Low priority", "Top priority");

    form.addParagraphTextItem()
      .setTitle("Any specific specialist clinic challenges or planned new specialties?");


    // 💳 Billing, Finance & HMO
    form.addPageBreakItem()
      .setTitle("💳 Billing, Finance & HMO")
      .setHelpText("Royan Hospital manages billing in-house and works with multiple HMO / insurance providers. This section covers the full revenue cycle.");

    form.addMultipleChoiceItem()
      .setTitle("How is patient billing currently handled?")
      .setChoiceValues(["Manual paper bills / receipts", "Excel-based invoicing", "Standalone billing software (not connected to clinical system)", "Integrated billing module in HMS"]);

    form.addCheckboxItem()
      .setTitle("Which billing and finance features do you need SynbotHealth to provide?")
      .setChoiceValues(["Automatic bill generation from clinical orders", "HMO pre-authorisation request", "HMO claim submission & tracking", "Co-payment calculation", "Multiple payment method receipt (cash, POS, transfer)", "Inpatient running bill (live balance)", "Itemised invoice / discharge bill", "Outstanding debt / credit management", "Petty cash / staff cash drawer reconciliation", "Financial reporting (daily revenue, monthly P&L summary)", "Consultation fee schedule management", "Waiver / discount authorisation workflow", "Indigent patient support tracking"]);

    form.addParagraphTextItem()
      .setTitle("Please list the HMO / insurance providers you currently work with (e.g. Hygeia, Reliance, Leadway, NHIS)");

    form.addScaleItem()
      .setTitle("How critical is integrated billing and HMO management for your hospital?")
      .setBounds(1, 5)
      .setLabels("Low priority", "Top priority");

    form.addParagraphTextItem()
      .setTitle("Any billing pain points? (e.g. HMO claim rejections, revenue leakage, billing errors)");


    // 📁 Medical Records & Data Management
    form.addPageBreakItem()
      .setTitle("📁 Medical Records & Data Management")
      .setHelpText("Covers patient records storage, retrieval, privacy, and compliance with the Nigeria Data Protection Act 2023 (NDPA).");

    form.addMultipleChoiceItem()
      .setTitle("How are patient medical records currently stored?")
      .setChoiceValues(["Entirely paper files in a physical records room", "Mixed: some paper, some scanned documents", "Electronic records in an HMS", "Cloud-based electronic health records"]);

    form.addCheckboxItem()
      .setTitle("Which medical records and data management features do you need?")
      .setChoiceValues(["Unified electronic patient record (EPR)", "Document scanning and attachment", "Referral letter generation and tracking", "Patient record access audit log", "Patient data request workflow", "Records release / ROI authorisation", "NDPA 2023 compliance tools", "Deceased patient record management", "Cross-department record sharing", "Record backup and disaster recovery"]);

    form.addScaleItem()
      .setTitle("How critical is an integrated electronic medical records system for Royan Hospital?")
      .setBounds(1, 5)
      .setLabels("Low priority", "Top priority");

    form.addParagraphTextItem()
      .setTitle("Any records management pain points? (e.g. lost files, unauthorised access concerns, NDPA readiness)");


    // ✅ Quality, Safety & Compliance
    form.addPageBreakItem()
      .setTitle("✅ Quality, Safety & Compliance")
      .setHelpText("Covers incident reporting, infection control, audit management, and clinical governance.");

    form.addMultipleChoiceItem()
      .setTitle("How are clinical incidents and adverse events currently reported and managed?")
      .setChoiceValues(["Not formally tracked", "Verbal reporting to manager; paper log", "Paper incident forms", "Digital incident reporting system"]);

    form.addCheckboxItem()
      .setTitle("Which quality and safety features do you need?")
      .setChoiceValues(["Digital incident / adverse event report", "Root cause analysis tracking", "Infection control surveillance", "Hand hygiene and PPE audit tool", "Surgical site infection (SSI) monitoring", "Mortality and morbidity meeting records", "Clinical audit management", "Patient complaints and feedback tracking", "HEFAMAA / regulatory inspection readiness", "Equipment maintenance and calibration log", "Fumigation and environmental health log"]);

    form.addScaleItem()
      .setTitle("How critical are quality and compliance tools for Royan Hospital?")
      .setBounds(1, 5)
      .setLabels("Low priority", "Top priority");

    form.addParagraphTextItem()
      .setTitle("Any quality / regulatory compliance concerns? (e.g. HEFAMAA inspections, recurring incidents)");


    // 👥 HR, Administration & Staff Management
    form.addPageBreakItem()
      .setTitle("👥 HR, Administration & Staff Management")
      .setHelpText("Covers staff scheduling, HR records, payroll integration, and general hospital administration.");

    form.addCheckboxItem()
      .setTitle("Which HR and administration features would be useful for Royan Hospital?")
      .setChoiceValues(["Staff roster and duty scheduling", "Staff attendance / time tracking", "Leave management", "On-call scheduling", "Staff performance appraisal module", "Staff HR record management", "Locum / agency staff management", "Payroll data export", "Nursing competency and training record"]);

    form.addScaleItem()
      .setTitle("How critical is HR and staff management functionality for your hospital?")
      .setBounds(1, 5)
      .setLabels("Low priority", "Top priority");

    form.addParagraphTextItem()
      .setTitle("Any HR or staffing challenges to highlight?");


    // 📱 Digital & Patient Engagement
    form.addPageBreakItem()
      .setTitle("📱 Digital & Patient Engagement")
      .setHelpText("Covers online patient-facing features — self-service, telemedicine, notifications, and the SynbotHealth AI assistant.");

    form.addMultipleChoiceItem()
      .setTitle("Does Royan Hospital currently offer any digital / online patient services?")
      .setChoiceValues(["No — all interactions are in-person or by phone", "WhatsApp for enquiries only", "Website with basic information only", "Online booking and/or patient portal"]);

    form.addCheckboxItem()
      .setTitle("Which digital patient engagement features interest you?")
      .setChoiceValues(["AI chatbot (SynbotHealth) for patient enquiries", "WhatsApp appointment booking via SynbotHealth", "Online patient registration / pre-registration", "Patient portal (view results, history, prescriptions)", "SMS / WhatsApp appointment reminders", "Telemedicine / video consultation", "Patient satisfaction surveys (post-visit)", "Health tips and campaign messaging", "Digital queue number on patient's phone", "Bill payment via mobile money / online transfer"]);

    form.addScaleItem()
      .setTitle("How high a priority is digital / patient-facing technology for Royan Hospital's strategy?")
      .setBounds(1, 5)
      .setLabels("Low priority", "Top priority");

    form.addParagraphTextItem()
      .setTitle("Any specific digital features your patients or management have requested?");


    // 📊 Reporting, Analytics & Management Dashboard
    form.addPageBreakItem()
      .setTitle("📊 Reporting, Analytics & Management Dashboard")
      .setHelpText("Covers what management and department heads need to see to run the hospital effectively.");

    form.addCheckboxItem()
      .setTitle("Which reporting and analytics capabilities do you need?")
      .setChoiceValues(["Daily OPD and A&E attendance report", "Inpatient census (daily bed occupancy)", "Revenue report (daily / monthly by department)", "HMO claims ageing report", "Pharmacy stock report (consumption & forecasting)", "Laboratory turnaround time (TAT) report", "Surgical throughput report", "Top diagnoses / disease burden report", "Chronic disease patient register report", "Infection surveillance report", "Staff productivity report", "Real-time hospital operations dashboard", "NHIA / HMIS regulatory report export"]);

    form.addScaleItem()
      .setTitle("How critical is real-time reporting and analytics for hospital management?")
      .setBounds(1, 5)
      .setLabels("Low priority", "Top priority");

    form.addParagraphTextItem()
      .setTitle("What is the single most important report or metric your management looks at today?");


    // ⚙️ Infrastructure & Technical Requirements
    form.addPageBreakItem()
      .setTitle("⚙️ Infrastructure & Technical Requirements")
      .setHelpText("Covers hardware, connectivity, integration requirements, and deployment preferences.");

    form.addMultipleChoiceItem()
      .setTitle("How would you describe your hospital's internet connectivity?")
      .setChoiceValues(["Unreliable / intermittent (frequent outages)", "Moderate (mostly reliable, occasional drops)", "Reliable broadband (rarely drops)", "Dedicated fibre / enterprise-grade connection"]);

    form.addCheckboxItem()
      .setTitle("What devices are currently in use or planned for clinical staff?")
      .setChoiceValues(["Desktop computers at fixed workstations", "Laptops", "Android tablets (bedside / ward)", "iPads (iOS tablets)", "Smartphones (Android)", "Dedicated nursing station terminals", "Barcode / QR scanners at pharmacy / lab", "Patient-facing kiosk / registration screen"]);

    form.addMultipleChoiceItem()
      .setTitle("What is your preference for system deployment?")
      .setChoiceValues(["Cloud-hosted (SynbotHealth manages servers — lower upfront cost)", "On-premise server in hospital (hospital manages hardware)", "Hybrid (critical data on-premise, reporting in cloud)", "No preference / need guidance"]);

    form.addCheckboxItem()
      .setTitle("Which external systems or services would you want SynbotHealth to integrate with?")
      .setChoiceValues(["HMO / insurance portals (claim submission API)", "NHIA (National Health Insurance Authority) portal", "Paystack / Flutterwave (online payment)", "WhatsApp Business API", "SMS gateway (bulk SMS for notifications)", "LIMS (existing lab equipment data export)", "PACS / digital imaging viewer", "Accounting software (QuickBooks, Sage, etc.)", "NHIA / HMIS government reporting portal", "Biometric / fingerprint authentication"]);

    form.addParagraphTextItem()
      .setTitle("Any IT infrastructure concerns or constraints we should know about?");


    // 💾 Current HMS — DRM Hope Configuration
    form.addPageBreakItem()
      .setTitle("💾 Current HMS — DRM Hope Configuration")
      .setHelpText("DRM Hope is your current Hospital Management System. These answers determine exactly how SynbotHealth connects to it — via REST API, ODBC database bridge, or HL7 FHIR — and which data is already tracked in Hope so we know what to read versus what to build fresh.");

    form.addMultipleChoiceItem()
      .setTitle("Which edition of DRM Hope is installed at Royan Hospital?")
      .setChoiceValues(["Community Edition", "Professional Edition", "Enterprise Edition", "Not sure — I would need to check"]);

    form.addParagraphTextItem()
      .setTitle("Hope version number (e.g. 3.2.1) — check the About screen inside Hope (optional but very helpful)");

    form.addMultipleChoiceItem()
      .setTitle("What database engine does DRM Hope use on the server? (Your IT team or the Hope installer documentation will confirm this)")
      .setChoiceValues(["Microsoft SQL Server (MSSQL)", "MySQL / MariaDB", "PostgreSQL", "Not sure — we would need to check"]);

    form.addMultipleChoiceItem()
      .setTitle("Does your DRM Hope installation expose any API or integration interface?")
      .setChoiceValues(["Yes — it has a licensed REST API", "Yes — it supports HL7 FHIR (R4)", "ODBC / direct database access only (no REST API)", "Not sure — IT would need to confirm"]);

    form.addCheckboxItem()
      .setTitle("Which modules are currently active and in daily use in your DRM Hope installation? (Select all that apply)")
      .setChoiceValues(["Patient Registration / Demographics", "Outpatient / Appointment Scheduling", "Inpatient / Ward Management", "Accident & Emergency (A&E)", "Pharmacy / Dispensing", "Laboratory / LIMS", "Radiology / Imaging orders", "Billing & Finance", "HMO / Insurance Management", "Theatre / Surgical Management", "Maternity / Antenatal Care", "HR / Staff Management", "Reporting / Analytics dashboard", "None — Hope is installed but not yet in active use"]);

    form.addMultipleChoiceItem()
      .setTitle("Is the computer running DRM Hope on the same Local Area Network (LAN) as other hospital systems?")
      .setChoiceValues(["Yes — it is on the hospital LAN and reachable by other machines", "Yes — but it is behind a firewall or restricted VLAN", "No — it is a standalone machine not connected to the network", "Not sure"]);

    form.addParagraphTextItem()
      .setTitle("Any additional notes about your DRM Hope setup, IT environment, or integration constraints we should know before the site visit?");

    return form;
  }

  // =============================================================================
  // Entry point — click Run to execute
  // =============================================================================

  function createForm() {
    Logger.log("SynbotHealth — Royan Hospital System Requirements");
    var form = buildHospitalForm();
    Logger.log("\n\u2713 Form created!");
    Logger.log("  Edit URL:      " + form.getEditUrl());
    Logger.log("  Responder URL: " + form.getPublishedUrl());
    Logger.log("");
    Logger.log("Share the Responder URL with the client.");
  }

  createForm();
}
