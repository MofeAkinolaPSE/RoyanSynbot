"""
hope-bridge/mock_data.py
------------------------
Static sample data returned when HOPE_MOCK=1.
Replace with real ODBC calls after the first site visit confirms the
DRM Hope database schema and ODBC DSN.
"""

from datetime import date, datetime

MOCK_PATIENTS: list[dict] = [
    {
        "patient_id":   "P-0001",
        "mrn":          "RH-2024-001",
        "first_name":   "Amaka",
        "last_name":    "Okonkwo",
        "dob":          "1985-03-14",
        "gender":       "F",
        "phone":        "+2348012345678",
        "blood_group":  "O+",
        "hmo":          "Hygeia HMO",
        "updated_at":   "2025-05-10T08:23:00Z",
    },
    {
        "patient_id":   "P-0002",
        "mrn":          "RH-2024-002",
        "first_name":   "Emeka",
        "last_name":    "Nwosu",
        "dob":          "1972-07-30",
        "gender":       "M",
        "phone":        "+2348099887766",
        "blood_group":  "A+",
        "hmo":          "AXA Mansard",
        "updated_at":   "2025-05-11T11:05:00Z",
    },
]

MOCK_APPOINTMENTS: list[dict] = [
    {
        "appointment_id": "APT-0001",
        "patient_id":     "P-0001",
        "doctor":         "Dr. Chidi Eze",
        "department":     "Cardiology",
        "slot_date":      "2025-05-20",
        "slot_time":      "09:00",
        "status":         "confirmed",
    },
    {
        "appointment_id": "APT-0002",
        "patient_id":     "P-0002",
        "doctor":         "Dr. Ngozi Adaora",
        "department":     "General Surgery",
        "slot_date":      "2025-05-21",
        "slot_time":      "11:30",
        "status":         "pending",
    },
]

MOCK_ADMISSIONS: list[dict] = [
    {
        "admission_id": "ADM-0001",
        "patient_id":   "P-0001",
        "ward":         "Medical Ward A",
        "bed":          "3B",
        "admitted_at":  "2025-05-12T14:00:00Z",
        "discharged_at": None,
        "diagnosis":    "Hypertensive crisis",
        "consultant":   "Dr. Chidi Eze",
    },
]

MOCK_PHARMACY_ORDERS: list[dict] = [
    {
        "order_id":   "RX-0001",
        "patient_id": "P-0001",
        "drug":       "Amlodipine 5mg",
        "quantity":   30,
        "unit":       "tablet",
        "status":     "dispensed",
        "ordered_at": "2025-05-12T15:30:00Z",
    },
]

MOCK_LAB_ORDERS: list[dict] = [
    {
        "order_id":   "LAB-0001",
        "patient_id": "P-0001",
        "test":       "Full Blood Count (FBC)",
        "status":     "resulted",
        "ordered_at": "2025-05-12T16:00:00Z",
        "resulted_at": "2025-05-12T18:00:00Z",
        "result_summary": "WBC 6.2, HGB 12.1, PLT 210",
    },
]

MOCK_BILLING: list[dict] = [
    {
        "invoice_id":    "INV-0001",
        "patient_id":    "P-0001",
        "total_amount":  45000.00,
        "hmo_claim":     40000.00,
        "patient_due":   5000.00,
        "currency":      "NGN",
        "status":        "part_paid",
        "created_at":    "2025-05-12T20:00:00Z",
    },
]
