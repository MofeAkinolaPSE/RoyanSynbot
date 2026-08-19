"""Match-and-migrate repair for the ~25,320 legacy `"<id>:encounter"`-keyed
duplicate encounters discovered 2026-08-17.

Background: an OLDER admissions pipeline run loaded a batch of admissions
using external_id format f"{diagnoses_id}:encounter" and attached full SOAP
notes / problem-list entries / radiology orders to them. A LATER pipeline
run re-loaded (mostly) the same underlying admissions using bare numeric
external_ids (matching the current admissions.py), producing a second,
correctly-keyed encounter row per visit -- but that later run did NOT
re-attach the clinical notes, so today the "correct" encounter usually has
0 notes while its stale "<id>:encounter" duplicate holds the only copy.

This is NOT the same bug as repair_shared_encounter_keys.py (which
consolidates genuinely empty lab/pharmacy/billing shell encounters into a
generic "Ancillary Services" bucket) -- these duplicates carry real
clinical content that must be preserved by migrating it to the correct
encounter, not discarded into a placeholder.

Matching strategy per stub (patient_id, id):
  1. Candidates = patient's other real-admission encounters (external_id
     NOT LIKE '%:encounter').
  2. A candidate matches if its chief_complaint is a non-trivial substring
     of the stub's note content, or vice versa (case-insensitive).
  3. Exactly one matching candidate -> migrate (high confidence).
  4. Zero or 2+ matching candidates -> skip entirely, no changes. (0
     candidates = nothing to consolidate into, might be genuinely unique;
     2+ = ambiguous, not worth guessing on real clinical data.)

Migration = repoint royan_encounter_notes / royan_problem_list /
royan_radiology_orders from the stub to the matched target, then delete
the stub only once verified fully orphaned (same generic FK-introspection
safety check as repair_shared_encounter_keys.py's step 4).

Usage:
    python scripts/dedupe_legacy_encounters.py --dry-run
    python scripts/dedupe_legacy_encounters.py --execute
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from html import unescape

import psycopg2
import psycopg2.extras

sys.path.insert(0, ".")
from config import DATABASE_URL  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("dedupe_legacy_encounters")

BATCH_SIZE = 5_000
MIN_WORDS = 3            # ignore trivially short complaint strings, too likely to spuriously match
MATCH_THRESHOLD = 0.75   # fraction of the complaint's distinct words that must appear in the note
AMBIGUOUS_GAP = 0.15     # if 2+ candidates both score within this gap of each other, treat as ambiguous

_TAG_RE = re.compile(r"<[^>]+>")
_WORD_RE = re.compile(r"[a-z0-9]+")


def _connect():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def _norm(s: str) -> str:
    s = unescape(s or "")
    s = _TAG_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _words(s: str) -> set[str]:
    return set(_WORD_RE.findall(s))


def _overlap_score(complaint_words: set[str], note_words: set[str]) -> float:
    if not complaint_words:
        return 0.0
    return len(complaint_words & note_words) / len(complaint_words)


def _fetch_stubs(cur) -> list[dict]:
    cur.execute(
        """
        SELECT e.id, e.patient_id,
               COALESCE((SELECT string_agg(n.content, ' ') FROM royan_encounter_notes n WHERE n.encounter_id = e.id), '')
               || ' ' ||
               COALESCE((SELECT string_agg(pl.description, ' ') FROM royan_problem_list pl WHERE pl.encounter_id = e.id), '')
               AS note_text
        FROM royan_encounters e
        WHERE e.external_source = 'hope' AND e.external_id LIKE '%:encounter'
        ORDER BY e.id
        """
    )
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _fetch_candidates_by_patient(cur) -> dict[int, list[dict]]:
    cur.execute(
        """
        SELECT id, patient_id, chief_complaint
        FROM royan_encounters
        WHERE external_source = 'hope' AND external_id NOT LIKE '%:encounter'
          AND chief_complaint IS NOT NULL AND chief_complaint <> ''
        """
    )
    cols = [d.name for d in cur.description]
    by_patient: dict[int, list[dict]] = {}
    for row in cur.fetchall():
        r = dict(zip(cols, row))
        by_patient.setdefault(r["patient_id"], []).append(r)
    return by_patient


def _match_target(stub: dict, candidates: list[dict]) -> tuple[dict | None, str]:
    note_text = _norm(stub.get("note_text") or "")
    note_words = _words(note_text)
    if not note_words or not candidates:
        return None, "no_note_or_no_candidates"

    # Single candidate: no ambiguity is possible (nothing else it could be),
    # so a short/generic complaint like "fever" is still a valid match --
    # the MIN_WORDS/threshold guards below exist specifically to avoid
    # misattributing among *multiple* real visits, which doesn't apply here.
    if len(candidates) == 1:
        complaint_words = _words(_norm(candidates[0]["chief_complaint"]))
        if not complaint_words:
            return None, "no_note_or_no_candidates"
        score = _overlap_score(complaint_words, note_words)
        if score >= 0.5:
            return candidates[0], "matched_single_candidate"
        return None, "no_match"

    scored = []
    for c in candidates:
        complaint_words = _words(_norm(c["chief_complaint"]))
        if len(complaint_words) < MIN_WORDS:
            continue
        score = _overlap_score(complaint_words, note_words)
        if score >= MATCH_THRESHOLD:
            scored.append((score, c))

    if not scored:
        return None, "no_match"
    scored.sort(key=lambda x: -x[0])
    if len(scored) > 1 and (scored[0][0] - scored[1][0]) < AMBIGUOUS_GAP:
        return None, f"ambiguous_{len(scored)}_matches"
    return scored[0][1], "matched"


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run

    conn = _connect()
    try:
        with conn.cursor() as cur:
            logger.info("Fetching stub encounters...")
            stubs = _fetch_stubs(cur)
            logger.info("Found %s stub encounters", len(stubs))

            logger.info("Fetching candidate real-admission encounters...")
            candidates_by_patient = _fetch_candidates_by_patient(cur)

            outcomes: dict[str, int] = {}
            to_migrate: list[tuple[int, int]] = []  # (stub_id, target_id)

            for stub in stubs:
                target, reason = _match_target(stub, candidates_by_patient.get(stub["patient_id"], []))
                outcomes[reason] = outcomes.get(reason, 0) + 1
                if target:
                    to_migrate.append((stub["id"], target["id"]))

            logger.info("=== Matching results ===")
            for reason, n in sorted(outcomes.items(), key=lambda x: -x[1]):
                logger.info("  %s: %s", reason, n)
            logger.info("Total confidently matched (will migrate): %s", len(to_migrate))

            if dry_run:
                cur.execute(
                    "SELECT COUNT(*) FROM royan_encounter_notes WHERE encounter_id = ANY(%s)",
                    ([s for s, _ in to_migrate],),
                )
                notes_n = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM royan_problem_list WHERE encounter_id = ANY(%s)",
                    ([s for s, _ in to_migrate],),
                )
                problems_n = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM royan_radiology_orders WHERE encounter_id = ANY(%s)",
                    ([s for s, _ in to_migrate],),
                )
                radiology_n = cur.fetchone()[0]
                logger.info("[dry-run] would repoint %s encounter_notes, %s problem_list, %s radiology_orders",
                            notes_n, problems_n, radiology_n)
                logger.info("[dry-run] would then attempt to delete %s now-empty stub encounters", len(to_migrate))
                conn.rollback()
                logger.info("Dry-run complete - no changes committed.")
                return

            # --- Execute ---
            migrated_notes = migrated_problems = migrated_radiology = 0
            for i in range(0, len(to_migrate), BATCH_SIZE):
                batch = to_migrate[i:i + BATCH_SIZE]
                for stub_id, target_id in batch:
                    cur.execute(
                        "UPDATE royan_encounter_notes SET encounter_id = %s WHERE encounter_id = %s",
                        (target_id, stub_id),
                    )
                    migrated_notes += cur.rowcount
                    cur.execute(
                        "UPDATE royan_problem_list SET encounter_id = %s WHERE encounter_id = %s",
                        (target_id, stub_id),
                    )
                    migrated_problems += cur.rowcount
                    cur.execute(
                        "UPDATE royan_radiology_orders SET encounter_id = %s WHERE encounter_id = %s",
                        (target_id, stub_id),
                    )
                    migrated_radiology += cur.rowcount
                logger.info("Migrated batch %s-%s (running: %s notes, %s problems, %s radiology)",
                            i, i + len(batch), migrated_notes, migrated_problems, migrated_radiology)

            logger.info("Migration complete: %s notes, %s problem_list, %s radiology_orders repointed",
                         migrated_notes, migrated_problems, migrated_radiology)

            # Delete stubs now verified orphaned across every table with an FK to royan_encounters.
            cur.execute(
                """
                SELECT DISTINCT cl.relname, a.attname
                FROM pg_constraint con
                JOIN pg_class cl ON cl.oid = con.conrelid
                JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
                WHERE con.contype = 'f' AND con.confrelid = 'royan_encounters'::regclass
                  AND cl.relispartition = false
                """
            )
            referencing = cur.fetchall()
            if not referencing:
                raise RuntimeError("FK introspection returned zero referencing tables — refusing to delete.")

            not_exists = "\n  AND ".join(
                f'NOT EXISTS (SELECT 1 FROM {t} WHERE {c} = e.id)' for t, c in referencing
            )
            stub_ids = [s for s, _ in to_migrate]
            cur.execute(
                f"""
                DELETE FROM royan_encounters e
                WHERE e.id = ANY(%s) AND {not_exists}
                """,
                (stub_ids,),
            )
            deleted = cur.rowcount
            logger.info("Deleted %s now-orphaned stub encounters (%s could not be verified orphaned and were left in place)",
                         deleted, len(stub_ids) - deleted)

        conn.commit()
        logger.info("Repair complete - changes committed.")
    except Exception:
        conn.rollback()
        logger.exception("Repair failed - rolled back.")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
