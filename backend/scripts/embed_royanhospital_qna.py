"""
Embed royanhospital.com_qna.csv and write royanhospital.com_qna_with_embeddings.csv.

Input  : backend/data/royanhospital.com_qna.csv   (Question, Answer, Source)
Output : backend/data/royanhospital.com_qna_with_embeddings.csv
         (question, answer, source, embedding)

Run from repo root or backend/ directory:
    python scripts/embed_royanhospital_qna.py
"""
from __future__ import annotations

import csv
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Resolve paths relative to the backend/ directory
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)  # backend/
sys.path.insert(0, _BACKEND)

INPUT_CSV  = os.path.join(_BACKEND, "data", "royanhospital.com_qna.csv")
OUTPUT_CSV = os.path.join(_BACKEND, "data", "royanhospital.com_qna_with_embeddings.csv")


def _load_embedding_model():
    """Load FastEmbed model — same model used by the rest of the stack."""
    try:
        from fastembed import TextEmbedding
        model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
        logger.info("FastEmbed model loaded (sentence-transformers/all-MiniLM-L6-v2)")
        return model
    except ImportError:
        logger.error("fastembed not installed. Run: pip install fastembed")
        sys.exit(1)
    except Exception as exc:
        logger.error(f"Failed to load embedding model: {exc}")
        sys.exit(1)


def embed_text(model, text: str) -> list[float]:
    result = list(model.embed([text]))
    return result[0].tolist()


def main() -> None:
    if not os.path.exists(INPUT_CSV):
        logger.error(f"Input CSV not found: {INPUT_CSV}")
        sys.exit(1)

    model = _load_embedding_model()

    rows: list[dict] = []
    with open(INPUT_CSV, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            # Normalize header capitalisation (Question → question, etc.)
            row = {k.strip().lower(): v.strip() for k, v in raw.items()}
            q = row.get("question", "")
            a = row.get("answer", "")
            s = row.get("source", "royanhospital.com")
            if not q or not a:
                logger.warning(f"Skipping empty row: {row}")
                continue
            rows.append({"question": q, "answer": a, "source": s})

    logger.info(f"Loaded {len(rows)} Q&A pairs from {INPUT_CSV}")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["question", "answer", "source", "embedding"])
        writer.writeheader()
        for i, row in enumerate(rows):
            embedding = embed_text(model, row["question"])
            if len(embedding) != 384:
                logger.warning(f"Row {i}: unexpected embedding dim {len(embedding)}, skipping")
                continue
            writer.writerow({
                "question":  row["question"],
                "answer":    row["answer"],
                "source":    row["source"],
                "embedding": json.dumps(embedding),
            })
            if (i + 1) % 10 == 0:
                logger.info(f"  Embedded {i + 1}/{len(rows)}")

    logger.info(f"Done — wrote {len(rows)} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
