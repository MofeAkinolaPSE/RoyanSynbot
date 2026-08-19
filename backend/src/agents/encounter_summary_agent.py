"""Encounter Summary Agent — Chapter 12 / Phase 10 (Knowledge Layer).

Generates a structured SOAP (Subjective / Objective / Assessment / Plan)
summary for a completed or in-progress clinical encounter by:

  1. Fetching the full encounter aggregate from the canonical API
     (GET /api/v1/encounters/{id}/complete)
  2. Composing a structured prompt that includes vitals, labs, prescriptions,
     triage notes, and discharge information
  3. Calling the LLM to produce a concise SOAP narrative
  4. Storing the summary in royan_encounter_notes as note_type='soap_summary'
     so it becomes part of the permanent clinical record

The agent is read/write-safe: it never overwrites an existing soap_summary
for the same encounter — it creates at most one per run (idempotent via
ON CONFLICT DO NOTHING on encounter_id + note_type).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agent_registry import register_agent
from src.agents.base_agent import BaseAgent, Insight

logger = logging.getLogger(__name__)

_SOAP_INSTRUCTION = """You are a senior clinical documentation specialist for a Nigerian tertiary hospital.
Given the following structured encounter data, produce a concise SOAP note:

S (Subjective): Patient's chief complaint and symptoms as reported.
O (Objective): Vital signs, examination findings, lab results.
A (Assessment): Primary and secondary diagnoses, clinical impression.
P (Plan): Medications prescribed, investigations ordered, follow-up plan, discharge instructions if applicable.

Rules:
- Be factual — only include information present in the data.
- Use standard clinical terminology.
- Flag missing data as "Not documented".
- Do not invent or infer diagnoses not in the data.
- Maximum 400 words.
- Format as a numbered SOAP list, not flowing prose."""


@register_agent
class EncounterSummaryAgent(BaseAgent):
    """Generates an LLM-powered SOAP summary for a clinical encounter."""

    name = "encounter_summary_agent"
    required_role = "clinical"

    # ------------------------------------------------------------------
    # collect_data — pull full encounter composite from canonical API
    # ------------------------------------------------------------------
    def collect_data(self) -> Dict[str, Any]:
        encounter_id = self.context.get("encounter_id")
        if not encounter_id:
            logger.error("EncounterSummaryAgent: no encounter_id in context")
            return {}

        data: Dict[str, Any] = {}
        try:
            from src.db import db
            import psycopg2.extras

            conn = db.pool.getconn()
            try:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

                # Encounter + patient demographics
                cur.execute(
                    """
                    SELECT
                        e.id, e.encounter_type, e.status, e.department,
                        e.consulting_doctor, e.chief_complaint,
                        e.triage_at, e.discharge_at, e.created_at,
                        p.mrn, p.first_name, p.last_name, p.date_of_birth,
                        p.gender, p.blood_group, p.genotype
                    FROM public.royan_encounters e
                    JOIN public.royan_patients p ON p.id = e.patient_id
                    WHERE e.id = %s
                    """,
                    (encounter_id,),
                )
                row = cur.fetchone()
                data["encounter"] = dict(row) if row else {}

                # Vitals
                cur.execute(
                    "SELECT vital_type, value, unit, recorded_at "
                    "FROM public.royan_vitals WHERE encounter_id = %s "
                    "ORDER BY recorded_at",
                    (encounter_id,),
                )
                data["vitals"] = [dict(r) for r in cur.fetchall()]

                # Lab orders + results
                cur.execute(
                    """
                    SELECT lo.test_name, lo.test_code, lo.urgency, lo.status,
                           lr.result_value, lr.unit, lr.reference_range,
                           lr.is_abnormal, lr.verified_at
                    FROM public.royan_lab_orders lo
                    LEFT JOIN public.royan_lab_results lr ON lr.order_id = lo.id
                    WHERE lo.encounter_id = %s
                    ORDER BY lo.ordered_at
                    """,
                    (encounter_id,),
                )
                data["labs"] = [dict(r) for r in cur.fetchall()]

                # Prescriptions
                cur.execute(
                    "SELECT drug_name, dosage, frequency, route, status "
                    "FROM public.royan_prescriptions "
                    "WHERE encounter_id = %s ORDER BY prescribed_at",
                    (encounter_id,),
                )
                data["prescriptions"] = [dict(r) for r in cur.fetchall()]

                # Clinical diagnoses
                cur.execute(
                    "SELECT icd_code, diagnosis_notes, diagnosis_type "
                    "FROM public.royan_clinical_diagnoses "
                    "WHERE encounter_id = %s",
                    (encounter_id,),
                )
                data["diagnoses"] = [dict(r) for r in cur.fetchall()]

                # Discharge summary if available
                cur.execute(
                    "SELECT discharge_condition, discharge_summary, "
                    "follow_up_date, follow_up_instructions "
                    "FROM public.royan_discharge_records "
                    "WHERE encounter_id = %s LIMIT 1",
                    (encounter_id,),
                )
                dr = cur.fetchone()
                data["discharge"] = dict(dr) if dr else {}

                # Triage
                cur.execute(
                    "SELECT triage_level, triage_notes, bp_systolic, "
                    "bp_diastolic, temperature, spo2, weight, height "
                    "FROM public.royan_triage "
                    "WHERE encounter_id = %s LIMIT 1",
                    (encounter_id,),
                )
                tr = cur.fetchone()
                data["triage"] = dict(tr) if tr else {}

                cur.close()
            finally:
                db.pool.putconn(conn)

        except Exception as exc:
            logger.error("EncounterSummaryAgent.collect_data failed: %s", exc)

        return data

    # ------------------------------------------------------------------
    # analyze — compose the structured prompt context
    # ------------------------------------------------------------------
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        enc = data.get("encounter") or {}
        if not enc:
            return {"context_text": "", "encounter_id": self.context.get("encounter_id")}

        lines: List[str] = []
        p_name = f"{enc.get('first_name', '')} {enc.get('last_name', '')}".strip()
        lines.append(f"PATIENT: {p_name} | MRN: {enc.get('mrn')} | "
                     f"DOB: {enc.get('date_of_birth')} | Gender: {enc.get('gender')}")
        lines.append(f"BLOOD GROUP: {enc.get('blood_group') or 'Not recorded'} | "
                     f"GENOTYPE: {enc.get('genotype') or 'Not recorded'}")
        lines.append(f"ENCOUNTER TYPE: {enc.get('encounter_type')} | "
                     f"DEPARTMENT: {enc.get('department')} | "
                     f"DOCTOR: {enc.get('consulting_doctor') or 'Not assigned'}")
        lines.append(f"CHIEF COMPLAINT: {enc.get('chief_complaint') or 'Not documented'}")
        lines.append(f"STATUS: {enc.get('status')}")
        lines.append("")

        triage = data.get("triage") or {}
        if triage:
            lines.append("TRIAGE:")
            bp = f"{triage.get('bp_systolic','?')}/{triage.get('bp_diastolic','?')} mmHg"
            lines.append(f"  BP: {bp}  |  Temp: {triage.get('temperature','?')}°C  |  "
                         f"SpO2: {triage.get('spo2','?')}%  |  "
                         f"Wt: {triage.get('weight','?')}kg  |  Ht: {triage.get('height','?')}cm")
            lines.append(f"  Triage Level: {triage.get('triage_level','?')}")
            if triage.get("triage_notes"):
                lines.append(f"  Notes: {triage['triage_notes']}")
            lines.append("")

        vitals = data.get("vitals") or []
        if vitals:
            lines.append("VITALS:")
            for v in vitals:
                lines.append(f"  {v.get('vital_type')}: {v.get('value')} {v.get('unit') or ''} "
                             f"@ {str(v.get('recorded_at',''))[:16]}")
            lines.append("")

        labs = data.get("labs") or []
        if labs:
            lines.append("LABORATORY:")
            for lab in labs:
                result = lab.get("result_value") or "Pending"
                abnormal = " [ABNORMAL]" if lab.get("is_abnormal") else ""
                lines.append(f"  {lab.get('test_name')} ({lab.get('test_code')}): "
                             f"{result} {lab.get('unit') or ''}{abnormal}")
            lines.append("")

        diagnoses = data.get("diagnoses") or []
        if diagnoses:
            lines.append("DIAGNOSES:")
            for d in diagnoses:
                lines.append(f"  [{d.get('diagnosis_type','').upper()}] "
                             f"{d.get('icd_code','')}: {d.get('diagnosis_notes','')}")
            lines.append("")

        rxs = data.get("prescriptions") or []
        if rxs:
            lines.append("MEDICATIONS PRESCRIBED:")
            for rx in rxs:
                lines.append(f"  {rx.get('drug_name')} {rx.get('dosage')} "
                             f"— {rx.get('frequency')} — {rx.get('route')} ({rx.get('status')})")
            lines.append("")

        discharge = data.get("discharge") or {}
        if discharge:
            lines.append("DISCHARGE:")
            lines.append(f"  Condition: {discharge.get('discharge_condition','?')}")
            if discharge.get("discharge_summary"):
                lines.append(f"  Summary: {discharge['discharge_summary']}")
            if discharge.get("follow_up_date"):
                lines.append(f"  Follow-up: {discharge['follow_up_date']} — "
                             f"{discharge.get('follow_up_instructions','')}")

        return {
            "context_text": "\n".join(lines),
            "encounter_id": enc.get("id") or self.context.get("encounter_id"),
        }

    # ------------------------------------------------------------------
    # generate_insights — call LLM, produce SOAP, return Insight
    # ------------------------------------------------------------------
    def generate_insights(self, analysis: Dict[str, Any]) -> Insight:
        insight = Insight()
        ctx_text = analysis.get("context_text", "")
        encounter_id = analysis.get("encounter_id")

        if not ctx_text:
            insight.findings.append("No encounter data found — cannot generate SOAP summary.")
            insight.confidence_score = 0.0
            return insight

        try:
            from src.llm_client import LLMClient
            llm = LLMClient()
            soap_text = llm.generate_response(
                context=ctx_text,
                question="Generate a SOAP note for this encounter.",
                instruction=_SOAP_INSTRUCTION,
            )
        except Exception as exc:
            logger.error("EncounterSummaryAgent LLM call failed: %s", exc)
            soap_text = ""

        if not soap_text:
            insight.findings.append("LLM unavailable — SOAP summary could not be generated.")
            insight.confidence_score = 0.0
            return insight

        insight.findings.append(f"SOAP summary generated for encounter {encounter_id}.")
        insight.metrics = {
            "encounter_id": encounter_id,
            "soap_word_count": len(soap_text.split()),
            "generated_at": datetime.utcnow().isoformat(),
        }
        insight.supporting_refs = [{"soap_text": soap_text}]
        insight.confidence_score = 0.85

        # Persist to clinical notes
        self._persist_soap(encounter_id, soap_text)
        return insight

    # ------------------------------------------------------------------
    # write_cache
    # ------------------------------------------------------------------
    def write_cache(self, insight: Insight) -> None:
        cache = self.context.get("cache")
        if cache:
            encounter_id = insight.metrics.get("encounter_id")
            cache.set(f"{self.name}:{encounter_id}", insight,
                      ttl=int(self.context.get("cache_ttl_seconds", 300)))

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "encounter_id": "int",
            "soap_word_count": "int",
            "generated_at": "str",
            "findings": "list[str]",
            "soap_text": "str (inside supporting_refs[0])",
        }

    # ------------------------------------------------------------------
    # Internal helper — idempotent persist
    # ------------------------------------------------------------------
    def _persist_soap(self, encounter_id: Optional[int], soap_text: str) -> None:
        if not encounter_id:
            return
        try:
            from src.db import db
            conn = db.pool.getconn()
            try:
                cur = conn.cursor()
                # No unique constraint on (encounter_id, note_type) exists —
                # deliberately not one, since multiple real human `progress`
                # notes per encounter are legitimate. Idempotency for this
                # agent-generated summary is done with a pre-check instead.
                cur.execute(
                    """
                    SELECT 1 FROM public.royan_encounter_notes
                    WHERE encounter_id = %s AND note_type = 'soap_summary'
                    LIMIT 1
                    """,
                    (encounter_id,),
                )
                if cur.fetchone() is None:
                    cur.execute(
                        "SELECT patient_id FROM public.royan_encounters WHERE id = %s",
                        (encounter_id,),
                    )
                    row = cur.fetchone()
                    patient_id = row[0] if row else None
                    if patient_id is not None:
                        cur.execute(
                            """
                            INSERT INTO public.royan_encounter_notes
                                (encounter_id, patient_id, note_type, content, author_id)
                            VALUES (%s, %s, 'soap_summary', %s, %s)
                            """,
                            (
                                encounter_id,
                                patient_id,
                                soap_text,
                                self.context.get("actor_id", "system"),
                            ),
                        )
                conn.commit()
                cur.close()
            except Exception as exc:
                conn.rollback()
                logger.warning("EncounterSummaryAgent._persist_soap: %s", exc)
            finally:
                db.pool.putconn(conn)
        except Exception as exc:
            logger.error("EncounterSummaryAgent._persist_soap outer: %s", exc)
