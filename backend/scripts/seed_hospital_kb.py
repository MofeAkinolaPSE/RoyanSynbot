"""Hospital Knowledge Base Seeder — Phase 2.

Reads data/hospital_qna_pairs.csv (question, answer),
generates 384-dim embeddings via FastEmbed,
writes data/hospital_qna_pairs_with_embeddings.csv,
then seeds the qna table in the database.

Usage:
    python scripts/seed_hospital_kb.py              # embed + seed
    python scripts/seed_hospital_kb.py --embed-only  # only write the CSV with embeddings
    python scripts/seed_hospital_kb.py --seed-only   # only seed from existing embedded CSV
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys

# Ensure backend root is on path regardless of working directory
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(_BACKEND_ROOT, ".env"), override=True)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

INPUT_CSV    = os.path.join(_BACKEND_ROOT, "data", "hospital_qna_pairs.csv")
EMBEDDED_CSV = os.path.join(_BACKEND_ROOT, "data", "hospital_qna_pairs_with_embeddings.csv")
EMBEDDING_DIM = 384


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def _load_embed_model():
    try:
        from fastembed import TextEmbedding
        model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
        logger.info("FastEmbed model loaded (all-MiniLM-L6-v2, 384-dim).")
        return model
    except Exception as exc:
        logger.error("FastEmbed unavailable: %s", exc)
        return None


def generate_embeddings(input_csv: str, output_csv: str) -> int:
    """Read Q&A CSV, embed each question, write out with embeddings column."""
    model = _load_embed_model()
    if model is None:
        logger.error("Cannot generate embeddings — FastEmbed model not loaded.")
        return 0

    rows = []
    with open(input_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            q = (row.get("question") or "").strip()
            a = (row.get("answer") or "").strip()
            if q and a:
                rows.append({"question": q, "answer": a})

    if not rows:
        logger.error("No valid rows found in %s", input_csv)
        return 0

    logger.info("Generating embeddings for %d Q&A pairs...", len(rows))
    questions = [r["question"] for r in rows]

    # Batch embed all questions at once (FastEmbed is efficient in batch)
    embeddings = list(model.embed(questions))

    written = 0
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["question", "answer", "embedding"])
        writer.writeheader()
        for row, emb in zip(rows, embeddings):
            emb_list = emb.tolist()
            if len(emb_list) != EMBEDDING_DIM:
                logger.warning("Unexpected embedding dim %d for '%s', skipping.", len(emb_list), row["question"][:50])
                continue
            writer.writerow({
                "question":  row["question"],
                "answer":    row["answer"],
                "embedding": json.dumps(emb_list),
            })
            written += 1

    logger.info("Wrote %d rows with embeddings to %s", written, output_csv)
    return written


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

def seed_to_db(embedded_csv: str) -> int:
    """Seed the qna table from an embedded CSV file."""
    from src.db import db
    from src.constants import TABLE_QNA

    rows_to_insert = []
    with open(embedded_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            q   = (row.get("question") or "").strip()
            a   = (row.get("answer") or "").strip()
            emb_raw = row.get("embedding", "")
            try:
                emb = json.loads(emb_raw)
            except Exception:
                logger.warning("Could not parse embedding for '%s', skipping.", q[:50])
                continue
            if not q or not a or len(emb) != EMBEDDING_DIM:
                logger.warning("Invalid row for '%s', skipping.", q[:50])
                continue
            rows_to_insert.append({"question": q, "answer": a, "embedding": emb})

    if not rows_to_insert:
        logger.warning("No valid rows to seed.")
        return 0

    try:
        db.table(TABLE_QNA).insert(rows_to_insert).execute()
        logger.info("Seeded %d rows into %s.", len(rows_to_insert), TABLE_QNA)
        return len(rows_to_insert)
    except Exception as exc:
        logger.error("Seed failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Seed Royan Hospital knowledge base")
    parser.add_argument("--embed-only", action="store_true", help="Only generate embeddings CSV, do not seed DB")
    parser.add_argument("--seed-only",  action="store_true", help="Only seed DB from existing embedded CSV")
    args = parser.parse_args()

    if args.seed_only:
        if not os.path.exists(EMBEDDED_CSV):
            logger.error("Embedded CSV not found: %s — run without --seed-only first.", EMBEDDED_CSV)
            sys.exit(1)
        count = seed_to_db(EMBEDDED_CSV)
        print(f"Seeded {count} rows into the database.")
    elif args.embed_only:
        count = generate_embeddings(INPUT_CSV, EMBEDDED_CSV)
        print(f"Generated embeddings for {count} rows → {EMBEDDED_CSV}")
    else:
        # Full pipeline: embed then seed
        logger.info("=== Step 1: Generating embeddings ===")
        embedded = generate_embeddings(INPUT_CSV, EMBEDDED_CSV)
        if embedded == 0:
            logger.error("Embedding step failed — aborting seed.")
            sys.exit(1)
        logger.info("=== Step 2: Seeding database ===")
        seeded = seed_to_db(EMBEDDED_CSV)
        print(f"\nDone. Embedded: {embedded} rows  |  Seeded: {seeded} rows")


if __name__ == "__main__":
    main()
