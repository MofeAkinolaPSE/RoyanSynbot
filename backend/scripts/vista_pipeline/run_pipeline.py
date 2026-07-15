"""
run_pipeline.py
---------------
Master runner for the VistA feature extraction & questionnaire pipeline.

Stages
------
  1  extract     Parse DOCX → 01_raw_modules.json
  2  llm         Call DeepSeek per module → 02_structured_modules.json
  3  questionnaire  Generate form spec + HTML + Google Forms script

Usage
-----
  # Full pipeline (all 3 stages):
  python -m scripts.vista_pipeline.run_pipeline

  # Stop after raw extraction (no API calls):
  python -m scripts.vista_pipeline.run_pipeline --stop-after extract

  # Skip LLM step (build questionnaire from raw text only):
  python -m scripts.vista_pipeline.run_pipeline --skip-llm

  # Resume a partial LLM run:
  python -m scripts.vista_pipeline.run_pipeline --resume

  # Test with only 5 modules:
  python -m scripts.vista_pipeline.run_pipeline --max 5

  # Show extracted module count only (dry run):
  python -m scripts.vista_pipeline.run_pipeline --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

log = logging.getLogger(__name__)

REPO_ROOT  = Path(__file__).resolve().parents[3]
OUTPUT_DIR = REPO_ROOT / "backend" / "docs" / "vista_res" / "pipeline_output"
MONOGRAPH  = REPO_ROOT / "backend" / "docs" / "vista_res" / "vista_monograph_0723_r.docx"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _check_monograph():
    if not MONOGRAPH.exists():
        print(f"ERROR: Monograph not found at:\n  {MONOGRAPH}")
        sys.exit(1)


def _print_banner(title: str):
    bar = "─" * 60
    print(f"\n{bar}\n  {title}\n{bar}")


# ---------------------------------------------------------------------------
# Stage runners
# ---------------------------------------------------------------------------
def stage_extract(dry_run: bool = False) -> list[dict]:
    _print_banner("Stage 1 — DOCX extraction")
    from scripts.vista_pipeline.extract import extract_modules, save_raw_modules

    modules = extract_modules(MONOGRAPH)

    domain_counts = Counter(m["domain"] for m in modules if not m["va_specific"])
    civilian      = [m for m in modules if not m["va_specific"]]

    print(f"  Total modules extracted  : {len(modules)}")
    print(f"  VA-specific (skipped)    : {len(modules) - len(civilian)}")
    print(f"  Civilian-relevant        : {len(civilian)}")
    print(f"\n  Domain breakdown:")
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        print(f"    {count:3d}  {domain}")

    if not dry_run:
        saved = save_raw_modules(modules, OUTPUT_DIR)
        print(f"\n  Saved → {saved}")
    else:
        print("\n  (dry-run: not saving)")

    return modules


def stage_llm(max_modules: int | None = None, resume: bool = False) -> list[dict]:
    _print_banner("Stage 2 — LLM feature extraction (DeepSeek)")
    from scripts.vista_pipeline.llm_extract import run_extraction

    results = run_extraction(max_modules=max_modules, resume=resume)
    print(f"\n  Structured modules saved → {OUTPUT_DIR / '02_structured_modules.json'}")
    return results


def stage_questionnaire(skip_llm: bool = False) -> None:
    _print_banner("Stage 3 — Questionnaire generation")
    from scripts.vista_pipeline.questionnaire_gen import run_questionnaire_gen

    input_file = OUTPUT_DIR / "02_structured_modules.json"

    if skip_llm:
        # Build a minimal structured file from raw data with placeholder values
        raw_file = OUTPUT_DIR / "01_raw_modules.json"
        if not raw_file.exists():
            print("ERROR: Run extract stage first.")
            sys.exit(1)
        with raw_file.open(encoding="utf-8") as f:
            raw_modules = json.load(f)
        # Build minimal structured entries (no LLM, features = empty)
        minimal = [
            {
                "module":          m["name"],
                "domain":          m["domain"],
                "description":     m["raw_text"][:200].replace("\n", " ") + "...",
                "features":        [],
                "typical_users":   [],
                "dependencies":    [],
                "relevance_score": 3 if not m["va_specific"] else 1,
                "relevance_notes": "Auto-classified — run LLM stage for detailed features.",
            }
            for m in raw_modules
        ]
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with input_file.open("w", encoding="utf-8") as f:
            json.dump(minimal, f, indent=2, ensure_ascii=False)
        print("  Note: using raw text (no LLM features) — questionnaire will list modules only.")

    run_questionnaire_gen(input_file)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="VistA → RoyanHealth feature pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--stop-after",
        choices=["extract", "llm"],
        default=None,
        help="Stop pipeline after this stage",
    )
    parser.add_argument("--skip-llm",  action="store_true", help="Skip LLM stage; build questionnaire from raw text")
    parser.add_argument("--resume",    action="store_true", help="Resume interrupted LLM extraction")
    parser.add_argument("--max",       type=int, default=None, help="Max modules for LLM stage (testing)")
    parser.add_argument("--dry-run",   action="store_true", help="Extract only; print counts without saving")
    args = parser.parse_args()

    _check_monograph()

    # ── Stage 1
    stage_extract(dry_run=args.dry_run)
    if args.dry_run:
        sys.exit(0)
    if args.stop_after == "extract":
        print("\n✓ Stopped after extraction stage.")
        sys.exit(0)

    # ── Stage 2
    if not args.skip_llm:
        stage_llm(max_modules=args.max, resume=args.resume)
        if args.stop_after == "llm":
            print("\n✓ Stopped after LLM stage.")
            sys.exit(0)

    # ── Stage 3
    stage_questionnaire(skip_llm=args.skip_llm)

    _print_banner("Pipeline complete")
    print(f"\n  All outputs in:\n  {OUTPUT_DIR}\n")


if __name__ == "__main__":
    main()
