-- 122_rbac_views.sql
-- Role-specific views enforcing column-level visibility for RBAC.
-- These are the first layer of access control; PostgreSQL GRANT statements
-- on these views (not base tables) restrict what each role can query.
--
-- Roles defined:
--   royan_nurse       — clinical workflow; no billing/HMO/financial data
--   royan_radiographer — radiology worklist; no billing or pharmacy
--   royan_auditor     — compliance view; no patient PII (name/phone/email)
--   royan_admin       — full access via GRANTs on base tables (no view restriction)

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- NURSE VIEWS
-- Can see: patient demographics (no HMO/insurance), encounters, lab orders,
--          prescriptions. Cannot see: billing, payments, HMO coverage.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW public.v_nurse_patients AS
SELECT
    p.id,
    p.mrn,
    p.first_name,
    p.last_name,
    p.date_of_birth,
    p.gender,
    p.blood_group,
    p.genotype,
    p.allergies,
    p.phone,
    p.next_of_kin_name,
    p.next_of_kin_phone,
    p.is_active,
    p.registered_at
FROM public.royan_patients p
WHERE p.is_active = true;

COMMENT ON VIEW public.v_nurse_patients IS
    'Patient demographics for nursing staff. Excludes HMO/insurance and financial columns.';

CREATE OR REPLACE VIEW public.v_nurse_encounters AS
SELECT
    e.id,
    e.patient_id,
    e.encounter_type,
    e.status,
    e.department,
    e.ward_id,
    e.bed_id,
    e.triage_level,
    e.triage_notes,
    e.chief_complaint,
    e.triage_at,
    e.triage_by,
    e.consulting_doctor,
    e.diagnosis_notes,
    e.consultation_at,
    e.discharge_summary,
    e.discharge_at,
    e.registered_by,
    e.created_at
FROM public.royan_encounters e;

COMMENT ON VIEW public.v_nurse_encounters IS
    'Encounter/queue view for nursing staff. No billing or financial data.';

CREATE OR REPLACE VIEW public.v_nurse_lab_orders AS
SELECT
    lo.id,
    lo.patient_id,
    lo.encounter_id,
    lo.test_name,
    lo.test_code,
    lo.urgency,
    lo.status,
    lo.sample_type,
    lo.ordered_by,
    lo.ordered_at,
    lo.notes,
    lo.updated_at
FROM public.royan_lab_orders lo;

CREATE OR REPLACE VIEW public.v_nurse_prescriptions AS
SELECT
    rx.id,
    rx.patient_id,
    rx.encounter_id,
    rx.drug_name,
    rx.dosage,
    rx.frequency,
    rx.duration,
    rx.route,
    rx.quantity,
    rx.unit,
    rx.special_instructions,
    rx.prescribed_by,
    rx.prescribed_at,
    rx.status
FROM public.royan_prescriptions rx;

-- ─────────────────────────────────────────────────────────────────────────────
-- RADIOGRAPHER VIEWS
-- Can see: imaging/radiology worklist from operations_events.
-- No billing, pharmacy, or full patient PII.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW public.v_radiographer_worklist AS
SELECT
    oe.id                               AS event_id,
    oe.event_date,
    oe.title                            AS study_description,
    oe.status,
    oe.performed_by                     AS radiographer,
    oe.metadata->>'study_type'          AS study_type,
    oe.metadata->>'body_region'         AS body_region,
    oe.metadata->>'ordering_doctor'     AS ordering_doctor,
    oe.metadata->>'report_text'         AS report_text,
    oe.metadata->>'performed_at'        AS performed_at,
    oe.metadata->>'reported_at'         AS reported_at,
    oe.department,
    oe.created_at
FROM public.royan_operations_events oe
WHERE oe.event_type = 'radiology';

COMMENT ON VIEW public.v_radiographer_worklist IS
    'Radiology worklist scoped to imaging events. No billing or full patient PII.';

CREATE OR REPLACE VIEW public.v_radiographer_patients AS
SELECT
    p.id,
    p.mrn,
    p.first_name,
    p.last_name,
    p.date_of_birth,
    p.gender,
    p.blood_group
FROM public.royan_patients p;

-- ─────────────────────────────────────────────────────────────────────────────
-- AUDITOR VIEWS
-- Can see: full audit log and operations events.
-- Patient PII (name, phone, email, address) is excluded — auditors track
-- system actions, not clinical data.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW public.v_auditor_audit_log AS
SELECT
    al.id,
    al.event_type,
    al.event_class,
    al.action,
    al.outcome,
    al.reason_code,
    al.actor_id,
    al.actor_role,
    al.subject_type,
    al.subject_id,
    al.trace_id,
    al.approval_reason,
    al.attestation_text,
    al.details,
    al.created_at
FROM public.royan_audit_logs al;

COMMENT ON VIEW public.v_auditor_audit_log IS
    'Full audit log for compliance auditors. No patient PII columns.';

CREATE OR REPLACE VIEW public.v_auditor_operations AS
SELECT
    oe.id,
    oe.event_type,
    oe.event_date,
    oe.title,
    oe.status,
    oe.severity,
    oe.department,
    oe.performed_by,
    oe.source_table,
    oe.run_id,
    oe.external_source,
    oe.external_id,
    oe.created_at
FROM public.royan_operations_events oe;

COMMENT ON VIEW public.v_auditor_operations IS
    'Operational events for compliance review. Metadata column excluded to keep view clean.';

-- Analytics views available to auditors
CREATE OR REPLACE VIEW public.v_auditor_queue_stats AS
SELECT * FROM public.mv_daily_queue_stats;

-- ─────────────────────────────────────────────────────────────────────────────
-- NOTE ON GRANTS
-- Apply these after creating application roles in PostgreSQL:
--
--   CREATE ROLE royan_nurse     NOLOGIN;
--   CREATE ROLE royan_radiographer NOLOGIN;
--   CREATE ROLE royan_auditor   NOLOGIN;
--
--   GRANT SELECT ON public.v_nurse_patients       TO royan_nurse;
--   GRANT SELECT ON public.v_nurse_encounters     TO royan_nurse;
--   GRANT SELECT ON public.v_nurse_lab_orders     TO royan_nurse;
--   GRANT SELECT ON public.v_nurse_prescriptions  TO royan_nurse;
--
--   GRANT SELECT ON public.v_radiographer_worklist  TO royan_radiographer;
--   GRANT SELECT ON public.v_radiographer_patients  TO royan_radiographer;
--
--   GRANT SELECT ON public.v_auditor_audit_log    TO royan_auditor;
--   GRANT SELECT ON public.v_auditor_operations   TO royan_auditor;
--   GRANT SELECT ON public.v_auditor_queue_stats  TO royan_auditor;
-- ─────────────────────────────────────────────────────────────────────────────

COMMIT;
