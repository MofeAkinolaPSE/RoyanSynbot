"""
Ingest raw scraped Royan Hospital web pages into knowledge_chunks table.

Input  : backend/data/royalhospital.com.csv  (URL, Content)
Output : Rows inserted into knowledge_chunks via the ingestion pipeline.

Run from backend/ directory:
    python scripts/ingest_royanhospital_web.py
"""
from __future__ import annotations

import csv
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_HERE    = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
sys.path.insert(0, _BACKEND)

INPUT_CSV = os.path.join(_BACKEND, "data", "royalhospital.com.csv")

# Map URL path segments to Royan Hospital departments for metadata tagging
_URL_TO_DEPT: dict[str, str] = {
    "cardiology":                     "Cardiology",
    "gastroenterology":               "Gastroenterology",
    "urology":                        "Urology",
    "family-medicine":                "Family Medicine",
    "orthopaedic":                    "Orthopaedic",
    "general-surgery":                "General Surgery",
    "pharmacy":                       "Pharmacy",
    "pediatrics":                     "Pediatrics",
    "obstretrics-and-gynaecology":    "Obstetrics & Gynaecology",
    "covid-19-info":                  "Administration",
    "health-wellness":                "Health & Wellness",
    "about-us-2":                     "Administration",
    "contact":                        "Administration",
}


def _url_to_department(url: str) -> str:
    for segment, dept in _URL_TO_DEPT.items():
        if segment in url:
            return dept
    return "General"


def _chunk_text(text: str, size: int = 800, overlap: int = 150) -> list[str]:
    """Split text into overlapping chunks."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end].strip())
        start += size - overlap
    return [c for c in chunks if len(c) > 50]


def main() -> None:
    if not os.path.exists(INPUT_CSV):
        logger.error(f"Input CSV not found: {INPUT_CSV}")
        sys.exit(1)

    # Load embedding model
    try:
        from fastembed import TextEmbedding
        model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
        logger.info("FastEmbed model loaded")
    except ImportError:
        logger.error("fastembed not installed. Run: pip install fastembed")
        sys.exit(1)

    from src.db import db

    rows: list[dict] = []
    with open(INPUT_CSV, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            url     = (raw.get("URL") or "").strip()
            content = (raw.get("Content") or "").strip()
            if not url or not content:
                continue
            rows.append({"url": url, "content": content})

    logger.info(f"Loaded {len(rows)} pages from {INPUT_CSV}")

    inserted = 0
    for page in rows:
        url        = page["url"]
        department = _url_to_department(url)
        chunks     = _chunk_text(page["content"])

        for chunk in chunks:
            try:
                embedding = list(model.embed([chunk]))[0].tolist()
            except Exception as exc:
                logger.warning(f"Embedding failed for chunk in {url}: {exc}")
                continue

            record = {
                "source":      url,
                "source_type": "web_page",
                "department":  department,
                "content":     chunk,
                "embedding":   embedding,
                "metadata":    {"url": url, "origin": "royanhospital.com"},
            }
            try:
                db.table("knowledge_chunks").insert(record).execute()
                inserted += 1
            except Exception as exc:
                logger.warning(f"Insert failed for {url}: {exc}")

        logger.info(f"  Processed {url} → {len(chunks)} chunks")

    logger.info(f"Done — inserted {inserted} knowledge chunks")


if __name__ == "__main__":
    main()
