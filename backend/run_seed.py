import os
import sys

# Ensure backend directory is in path
sys.path.append(os.path.dirname(__file__))

from src.seed_qna import seed

_DATA = os.path.join(os.path.dirname(__file__), "data")

# CSVs to seed (in order). Each entry: (csv_path, description)
_SEED_FILES = [
    (
        os.path.join(_DATA, "hospital_qna_pairs_with_embeddings.csv"),
        "Base hospital Q&A pairs",
    ),
    (
        os.path.join(_DATA, "royanhospital.com_qna_with_embeddings.csv"),
        "Royan Hospital website Q&A pairs",
    ),
]

if __name__ == "__main__":
    total = 0
    for csv_path, description in _SEED_FILES:
        if not os.path.exists(csv_path):
            print(f"[SKIP] {description} — file not found: {csv_path}")
            continue
        print(f"[SEED] {description} — {csv_path}")
        try:
            count = seed(csv_path)
            print(f"  Inserted {count} rows.")
            total += count
        except Exception as e:
            print(f"  Failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
    print(f"\nTotal rows seeded: {total}")
