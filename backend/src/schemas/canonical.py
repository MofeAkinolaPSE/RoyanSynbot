"""Canonical aggregate response schemas — Chapter 3.13 & 8.7 of the blueprint.

These models represent the 7-domain clinical data model as seen through the
API layer. They are read-only aggregates; mutations go through domain-specific
business-capability endpoints.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Shared primitives
# ─────────────────────────────────────────────────────────────────────────────

class StaffRef(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    role: Optional[str] = None
    specialty: Optional[str] = None


class DepartmentRef(BaseModel):
    id: Optional[int] = None
    code: Optional[str] = None
    name: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Domain: Identity
# ─────────────────────────────────────────────────────────────────────────────

class PatientDemographics(BaseModel):
    id: int
    mrn: str
    first_name: str
    last_name: str
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    blood_group: Optional[str] = None
    genotype: Optional[str] = None
    hmo_provider: Optional[str] = None
    hmo_id: Optional[str] = None
    registered_at: Optional[str] = None


class PatientSummary(BaseModel):
    """Full patient identity + clinical snapshot."""
    patient: PatientDemographics
    total_encounters: int = 0
    last_encounter_date: Optional[str] = None
    last_encounter_type: Optional[str] = None
    last_diagnosis: Optional[str] = None
    active_medications: int = 0
    pending_lab_orders: int = 0
    outstanding_balance: float = 0.0
    hmo_coverage: Optional[str] = None
    known_allergies: List[str] = Field(default_factory=list)
    primary_doctor: Optional[StaffRef] = None


# ─────────────────────────────────────────────────────────────────────────────
# Domain: Clinical (Encounters & Timeline)
# ─────────────────────────────────────────────────────────────────────────────

class EncounterBrief(BaseModel):
    id: int
    encounter_type: Optional[str] = None
    status: Optional[str] = None
    department: Optional[str] = None
    consulting_doctor: Optional[str] = None
    chief_complaint: Optional[str] = None
    diagnosis_notes: Optional[str] = None
    triage_at: Optional[str] = None
    discharge_at: Optional[str] = None
    created_at: Optional[str] = None


class LabResultBrief(BaseModel):
    test_name: Optional[str] = None
    test_code: Optional[str] = None
    result_value: Optional[str] = None
    result_summary: Optional[str] = None
    is_critical: Optional[bool] = None
    resulted_at: Optional[str] = None
    status: Optional[str] = None


class PrescriptionBrief(BaseModel):
    drug_name: Optional[str] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = None
    status: Optional[str] = None
    prescribed_at: Optional[str] = None


class EncounterComplete(BaseModel):
    """Full encounter with all clinical domains included."""
    encounter: EncounterBrief
    patient: PatientDemographics
    lab_orders: List[Dict[str, Any]] = Field(default_factory=list)
    prescriptions: List[Dict[str, Any]] = Field(default_factory=list)
    vitals: List[Dict[str, Any]] = Field(default_factory=list)
    notes: List[Dict[str, Any]] = Field(default_factory=list)
    billing: Optional[Dict[str, Any]] = None


class EncounterTimelineItem(BaseModel):
    encounter_id: int
    encounter_type: Optional[str] = None
    status: Optional[str] = None
    department: Optional[str] = None
    consulting_doctor: Optional[str] = None
    chief_complaint: Optional[str] = None
    diagnosis_notes: Optional[str] = None
    triage_at: Optional[str] = None
    discharge_at: Optional[str] = None
    created_at: Optional[str] = None
    lab_count: int = 0
    prescription_count: int = 0
    total_billed: float = 0.0


class EncounterTimeline(BaseModel):
    patient_mrn: str
    total_encounters: int
    encounters: List[EncounterTimelineItem]


# ─────────────────────────────────────────────────────────────────────────────
# Domain: Results (Laboratory)
# ─────────────────────────────────────────────────────────────────────────────

class LabOrderDetail(BaseModel):
    id: int
    test_name: Optional[str] = None
    test_code: Optional[str] = None
    urgency: Optional[str] = None
    status: Optional[str] = None
    sample_type: Optional[str] = None
    ordered_by: Optional[str] = None
    ordered_at: Optional[str] = None
    result_value: Optional[str] = None
    result_summary: Optional[str] = None
    interpretation: Optional[str] = None
    is_critical: Optional[bool] = None
    resulted_at: Optional[str] = None
    encounter_id: Optional[int] = None


class LaboratoryHistory(BaseModel):
    patient_mrn: str
    total_orders: int
    critical_count: int = 0
    pending_count: int = 0
    orders: List[LabOrderDetail]


# ─────────────────────────────────────────────────────────────────────────────
# Domain: Medication
# ─────────────────────────────────────────────────────────────────────────────

class MedicationRecord(BaseModel):
    id: int
    drug_name: Optional[str] = None
    drug_code: Optional[str] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = None
    quantity: Optional[float] = None
    duration_days: Optional[int] = None
    status: Optional[str] = None
    prescribed_by: Optional[str] = None
    prescribed_at: Optional[str] = None
    encounter_id: Optional[int] = None


class MedicationHistory(BaseModel):
    patient_mrn: str
    total_prescriptions: int
    active_count: int = 0
    prescriptions: List[MedicationRecord]


# ─────────────────────────────────────────────────────────────────────────────
# Domain: Revenue (Billing)
# ─────────────────────────────────────────────────────────────────────────────

class BillingSummary(BaseModel):
    patient_mrn: str
    total_billed: float = 0.0
    total_paid: float = 0.0
    outstanding_balance: float = 0.0
    hmo_covered: float = 0.0
    last_payment_date: Optional[str] = None
    payment_method: Optional[str] = None
    bill_count: int = 0
    pending_claims: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Domain: Operational Queue
# ─────────────────────────────────────────────────────────────────────────────

class QueueEntry(BaseModel):
    encounter_id: int
    patient_mrn: str
    patient_name: str
    triage_level: Optional[str] = None
    department: Optional[str] = None
    status: Optional[str] = None
    wait_minutes: Optional[int] = None
    triage_at: Optional[str] = None


class DepartmentQueue(BaseModel):
    department: str
    waiting: int = 0
    in_consultation: int = 0
    avg_wait_minutes: Optional[float] = None
    entries: List[QueueEntry] = Field(default_factory=list)


class QueueOverview(BaseModel):
    total_active: int = 0
    departments: List[DepartmentQueue]
    generated_at: str


# ─────────────────────────────────────────────────────────────────────────────
# Business capability request bodies
# ─────────────────────────────────────────────────────────────────────────────

class StartConsultationRequest(BaseModel):
    doctor_name: Optional[str] = None
    department: Optional[str] = None
    notes: Optional[str] = None


class OrderLabRequest(BaseModel):
    test_name: str = Field(..., min_length=1)
    test_code: Optional[str] = None
    urgency: str = "routine"
    sample_type: Optional[str] = None
    notes: Optional[str] = None


class PrescribeRequest(BaseModel):
    drug_name: str = Field(..., min_length=1)
    drug_code: Optional[str] = None
    dosage: str = Field(..., min_length=1)
    frequency: str = Field(..., min_length=1)
    route: str = "oral"
    quantity: Optional[float] = None
    duration_days: Optional[int] = None
    notes: Optional[str] = None


class DischargeRequest(BaseModel):
    discharge_condition: str = "stable"
    discharge_diagnosis: Optional[str] = None
    discharge_summary: Optional[str] = None
    follow_up_instructions: Optional[str] = None
    follow_up_date: Optional[str] = None
    notes: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Domain: Observations (vitals + clinical findings)
# ─────────────────────────────────────────────────────────────────────────────

class ObservationRecord(BaseModel):
    id: Optional[int] = None
    observation_type: str = "vital"        # vital | finding | symptom | measurement
    name: str
    value: Optional[str] = None
    unit: Optional[str] = None
    is_abnormal: Optional[bool] = None
    reference_range: Optional[str] = None
    recorded_by: Optional[str] = None
    recorded_at: Optional[str] = None
    encounter_id: Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
# Domain: Diagnoses
# ─────────────────────────────────────────────────────────────────────────────

class DiagnosisRecord(BaseModel):
    id: Optional[int] = None
    icd_code: Optional[str] = None
    description: str
    diagnosis_type: str = "primary"        # primary | secondary | differential
    onset_date: Optional[str] = None
    resolution_date: Optional[str] = None
    is_chronic: bool = False
    recorded_by: Optional[str] = None
    recorded_at: Optional[str] = None
    encounter_id: Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
# Domain: Workflow Events (immutable audit trail)
# ─────────────────────────────────────────────────────────────────────────────

class WorkflowEventRecord(BaseModel):
    id: Optional[int] = None
    instance_id: Optional[int] = None
    from_state: str
    to_state: str
    event_name: str
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None
    correlation_id: Optional[str] = None
    event_data: Dict[str, Any] = Field(default_factory=dict)
    occurred_at: str


# ─────────────────────────────────────────────────────────────────────────────
# Composite: PatientClinicalContext — the EKE master object (Ch 9)
# Assembled by knowledge_service and returned by workspace endpoints.
# ─────────────────────────────────────────────────────────────────────────────

class PatientClinicalContext(BaseModel):
    """Complete 7-domain clinical context for a patient. Assembled by EKE."""
    # Domain: Identity
    patient: PatientDemographics
    # Domain: Clinical
    active_encounter: Optional[EncounterBrief] = None
    encounter_count: int = 0
    last_visit_date: Optional[str] = None
    # Domain: Observations
    latest_vitals: List[ObservationRecord] = Field(default_factory=list)
    # Domain: Diagnoses
    active_diagnoses: List[DiagnosisRecord] = Field(default_factory=list)
    chronic_conditions: List[DiagnosisRecord] = Field(default_factory=list)
    # Domain: Medication
    active_medications: List[MedicationRecord] = Field(default_factory=list)
    known_allergies: List[str] = Field(default_factory=list)
    # Domain: Orders / Results
    pending_lab_orders: List[LabOrderDetail] = Field(default_factory=list)
    recent_lab_results: List[LabOrderDetail] = Field(default_factory=list)
    # Domain: Revenue
    outstanding_balance: float = 0.0
    hmo_coverage: Optional[str] = None
    # Domain: Intelligence
    risk_flags: List[str] = Field(default_factory=list)
    clinical_notes_count: int = 0
    # Metadata
    context_assembled_at: Optional[str] = None
    is_stale: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Workspace view models — role-specific assembled views (Ch 9 ViewModelFactory)
# ─────────────────────────────────────────────────────────────────────────────

class DoctorWorkspace(BaseModel):
    """Complete clinical view for the doctor consultation screen."""
    patient: PatientDemographics
    encounter: EncounterBrief
    active_diagnoses: List[DiagnosisRecord] = Field(default_factory=list)
    latest_vitals: List[ObservationRecord] = Field(default_factory=list)
    active_medications: List[MedicationRecord] = Field(default_factory=list)
    known_allergies: List[str] = Field(default_factory=list)
    pending_lab_orders: List[LabOrderDetail] = Field(default_factory=list)
    recent_lab_results: List[LabOrderDetail] = Field(default_factory=list)
    chronic_conditions: List[DiagnosisRecord] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)
    workflow_state: Optional[str] = None
    assembled_at: Optional[str] = None


class NurseWorkspace(BaseModel):
    """View for nursing assessment and care delivery screen."""
    patient: PatientDemographics
    encounter: EncounterBrief
    latest_vitals: List[ObservationRecord] = Field(default_factory=list)
    active_medications: List[MedicationRecord] = Field(default_factory=list)
    known_allergies: List[str] = Field(default_factory=list)
    nursing_tasks: List[Dict[str, Any]] = Field(default_factory=list)
    workflow_state: Optional[str] = None
    triage_notes: Optional[str] = None
    assembled_at: Optional[str] = None


class BillingWorkspace(BaseModel):
    """View for billing and cashiering screen."""
    patient: PatientDemographics
    encounter: EncounterBrief
    billing_summary: BillingSummary
    bill_items: List[Dict[str, Any]] = Field(default_factory=list)
    payments: List[Dict[str, Any]] = Field(default_factory=list)
    hmo_coverage: Optional[str] = None
    insurance_claim_status: Optional[str] = None
    workflow_state: Optional[str] = None
    assembled_at: Optional[str] = None


class PatientPortalView(BaseModel):
    """Patient-facing summary for the patient portal."""
    patient: PatientDemographics
    upcoming_appointments: List[Dict[str, Any]] = Field(default_factory=list)
    recent_encounters: List[EncounterTimelineItem] = Field(default_factory=list)
    active_medications: List[MedicationRecord] = Field(default_factory=list)
    outstanding_balance: float = 0.0
    assembled_at: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Business capability request bodies (Ch 10 — canonical capability endpoints)
# ─────────────────────────────────────────────────────────────────────────────

class RegisterPatientRequest(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    blood_group: Optional[str] = None
    genotype: Optional[str] = None
    hmo_provider: Optional[str] = None
    hmo_id: Optional[str] = None
    next_of_kin_name: Optional[str] = None
    next_of_kin_phone: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class StartEncounterRequest(BaseModel):
    patient_mrn: str = Field(..., min_length=1)
    encounter_type: str = "outpatient"
    department: Optional[str] = None
    department_id: Optional[int] = None
    chief_complaint: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class CompleteConsultationRequest(BaseModel):
    diagnosis_notes: Optional[str] = None
    diagnoses: List[Dict[str, Any]] = Field(default_factory=list)
    follow_up_required: bool = False
    follow_up_date: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}


class RecordVitalsRequest(BaseModel):
    temperature: Optional[float] = None            # °C
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    pulse_rate: Optional[int] = None               # bpm
    respiratory_rate: Optional[int] = None         # breaths/min
    oxygen_saturation: Optional[float] = None      # %
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    notes: Optional[str] = None

    model_config = {"extra": "ignore"}
