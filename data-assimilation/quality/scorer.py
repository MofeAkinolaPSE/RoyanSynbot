"""Batch quality scorer — Chapter 5.7 of the blueprint.

Runs all seven dimension checkers against a batch of records and produces
a BatchQualityReport with per-entity statistics, overall score, and a
list of records that fail hard rules (to be sent to the DLQ).

Usage:
    from quality.scorer import score_batch

    report, dlq_records = score_batch("patients", rows, domain_config)
    print(report.summary())
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from quality.dimensions import (
    DOMAIN_CONFIGS,
    DimensionResult,
    RecordQualityReport,
    UniquenessChecker,
    check_accuracy,
    check_completeness,
    check_consistency,
    check_integrity,
    check_timeliness,
    check_validity,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Batch report
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BatchQualityReport:
    entity: str
    total_records:  int = 0
    passed_records: int = 0
    hard_fails:     int = 0
    dim_scores:     Dict[str, float] = field(default_factory=dict)  # dimension → mean score
    warnings:       List[str] = field(default_factory=list)

    @property
    def overall_score(self) -> float:
        if not self.dim_scores:
            return 0.0
        return round(sum(self.dim_scores.values()) / len(self.dim_scores), 3)

    @property
    def pass_rate(self) -> float:
        if self.total_records == 0:
            return 1.0
        return round(self.passed_records / self.total_records, 3)

    def summary(self) -> str:
        lines = [
            f"=== Quality Report: {self.entity.upper()} ===",
            f"  Total   : {self.total_records}",
            f"  Passed  : {self.passed_records}  ({self.pass_rate * 100:.1f}%)",
            f"  DLQ     : {self.hard_fails}",
            f"  Overall : {self.overall_score * 100:.1f}%",
            "",
            "  Dimension scores:",
        ]
        for dim, score in sorted(self.dim_scores.items()):
            bar = "█" * int(score * 20)
            lines.append(f"    {dim:<15} {score * 100:5.1f}%  {bar}")
        if self.warnings:
            lines.append("")
            lines.append("  Warnings:")
            for w in self.warnings[:10]:
                lines.append(f"    ⚠  {w}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Core scorer
# ─────────────────────────────────────────────────────────────────────────────

def score_record(
    record: Dict[str, Any],
    config: Dict,
    uniqueness_checker: UniquenessChecker,
) -> RecordQualityReport:
    """Run all seven dimensions on one record."""
    entity = config.get("entity", "unknown")
    record_key = str(
        record.get("external_id")
        or record.get("mrn")
        or record.get("id")
        or "?"
    )
    report = RecordQualityReport(entity=entity, record_key=record_key)

    checks: List[DimensionResult] = [
        check_completeness(record, config),
        check_validity(record, config),
        check_accuracy(record, config),
        check_consistency(record, config),
        check_timeliness(record, config),
        uniqueness_checker.check(record),
        check_integrity(record, config),
    ]

    for result in checks:
        report.scores[result.dimension] = result.score
        if result.violations:
            report.violations[result.dimension] = result.violations

    return report


def score_batch(
    entity: str,
    records: List[Dict[str, Any]],
    config: Optional[Dict] = None,
) -> Tuple[BatchQualityReport, List[Dict[str, Any]]]:
    """Score an entire batch. Returns (BatchQualityReport, dlq_records).

    dlq_records contains the original records that are hard failures and
    should be routed to the bronze_dlq table rather than the operational DB.
    """
    if config is None:
        config = DOMAIN_CONFIGS.get(entity, {})
    config = {**config, "entity": entity}

    unique_field = config.get("unique_key", "external_id")
    uniqueness_checker = UniquenessChecker(unique_field)

    batch_report = BatchQualityReport(entity=entity, total_records=len(records))
    dim_accumulators: Dict[str, List[float]] = {}
    dlq_records: List[Dict] = []

    for record in records:
        rec_report = score_record(record, config, uniqueness_checker)

        if rec_report.is_hard_fail:
            batch_report.hard_fails += 1
            dlq_records.append({
                "entity":       entity,
                "record_key":   rec_report.record_key,
                "violations":   rec_report.violations,
                "overall_score": rec_report.overall_score,
                "raw_record":   record,
            })
        else:
            batch_report.passed_records += 1

        for dim, score in rec_report.scores.items():
            dim_accumulators.setdefault(dim, []).append(score)

        # Bubble up violations as warnings (first 50 only to avoid log spam)
        if len(batch_report.warnings) < 50:
            for dim, viols in rec_report.violations.items():
                for v in viols:
                    batch_report.warnings.append(
                        f"[{rec_report.record_key}] {dim}: {v}"
                    )

    for dim, scores in dim_accumulators.items():
        batch_report.dim_scores[dim] = round(sum(scores) / len(scores), 3)

    if logger.isEnabledFor(logging.INFO):
        logger.info(batch_report.summary())

    return batch_report, dlq_records
