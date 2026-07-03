"""
llm_extract.py
--------------
Step 2 of the VistA Pipeline.

For each civilian-relevant module from 01_raw_modules.json, calls the
DeepSeek API (already configured in .env) to produce structured JSON:

    {
      "module":       str,
      "domain":       str,
      "description":  str,          # 2-3 sentence plain-English summary
      "features":     [             # concrete capabilities
        {
          "name":        str,
          "description": str,
          "clinical_impact": "High|Medium|Low"
        }, ...
      ],
      "typical_users": [str],       # e.g. ["Doctor", "Nurse", "Pharmacist"]
      "dependencies":  [str],       # other VistA modules it relies on
      "relevance_score": int,       # 1-5  (5 = very relevant for Nigerian hospital)
      "relevance_notes": str,
    }

Results are saved to 02_structured_modules.json.
Failed/skipped modules are logged to 02_errors.jsonl.

Usage:
    python -m scripts.vista_pipeline.llm_extract [--max N] [--resume]

Options:
    --max N      Process at most N modules (useful for testing)
    --resume     Skip modules already present in 02_structured_modules.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT  = Path(__file__).resolve().parents[3]
OUTPUT_DIR = REPO_ROOT / "backend" / "docs" / "vista_res" / "pipeline_output"
RAW_FILE   = OUTPUT_DIR / "01_raw_modules.json"
OUT_FILE   = OUTPUT_DIR / "02_structured_modules.json"
ERR_FILE   = OUTPUT_DIR / "02_errors.jsonl"

ENV_FILE   = REPO_ROOT / "backend" / ".env"
load_dotenv(ENV_FILE)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL   = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
API_URL          = "https://api.deepseek.com/chat/completions"

# Safety: refuse to run if no key
if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY.startswith("optional"):
    raise EnvironmentError(
        "DEEPSEEK_API_KEY is not set in backend/.env — cannot run LLM extraction."
    )

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a hospital IT consultant helping a Nigerian private hospital
evaluate which modules from the US Veterans Affairs VistA system are relevant to their
operations. You extract structured, accurate information about each software module.

Respond ONLY with valid JSON. No markdown fences, no prose outside the JSON object."""

def build_user_prompt(module_name: str, raw_text: str, domain: str) -> str:
    # Truncate very long modules to avoid token overruns (keep first 1500 chars)
    body = raw_text[:1500].strip() if len(raw_text) > 1500 else raw_text.strip()
    return f"""Module name: {module_name}
Domain: {domain}
---
{body}
---

Extract and return ONLY the following JSON object (fill every field):

{{
  "module": "<exact module name>",
  "domain": "<domain>",
  "description": "<2-3 sentence plain-English summary of what this module does>",
  "features": [
    {{
      "name": "<feature name>",
      "description": "<one sentence>",
      "clinical_impact": "High|Medium|Low"
    }}
  ],
  "typical_users": ["<role1>", "<role2>"],
  "dependencies": ["<other VistA module name if any>"],
  "relevance_score": <integer 1-5, where 5=essential for a Nigerian hospital, 1=VA-specific/irrelevant>,
  "relevance_notes": "<one sentence explaining the score>"
}}

Rules:
- features list: include 3-8 items; skip obvious/generic items like 'login'
- typical_users: use plain role names (Doctor, Nurse, Pharmacist, Receptionist, etc.)
- relevance_score 5: daily-use clinical workflow (ADT, Pharmacy, Lab, Radiology, Billing)
- relevance_score 4: important but optional (Quality, Mental Health, Scheduling)
- relevance_score 3: useful supporting module
- relevance_score 2: mostly infrastructure/technical, end-users don't touch it
- relevance_score 1: VA-specific, legal/compliance feature not applicable outside US VA
"""


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------
def call_deepseek(prompt: str, retries: int = 3) -> dict:
    """Call DeepSeek and return parsed JSON dict from the response."""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens":  1024,
    }

    for attempt in range(1, retries + 1):
        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(API_URL, headers=headers, json=payload)
                resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            # Strip accidental markdown fences
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
        except (httpx.HTTPStatusError, httpx.ReadTimeout) as exc:
            log.warning("Attempt %d failed: %s", attempt, exc)
            if attempt < retries:
                time.sleep(2 ** attempt)
        except json.JSONDecodeError as exc:
            log.warning("JSON parse error on attempt %d: %s", attempt, exc)
            if attempt < retries:
                time.sleep(1)
    raise RuntimeError(f"All {retries} attempts failed")


# ---------------------------------------------------------------------------
# Main extraction loop
# ---------------------------------------------------------------------------
def run_extraction(max_modules: int | None = None, resume: bool = False) -> list[dict]:
    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"Raw modules file not found: {RAW_FILE}\n"
            "Run extract.py first."
        )

    with RAW_FILE.open(encoding="utf-8") as f:
        raw_modules: list[dict] = json.load(f)

    # Only process civilian-relevant modules
    target = [m for m in raw_modules if not m["va_specific"]]
    log.info("Civilian-relevant modules to process: %d", len(target))

    # Resume logic — load already-processed names
    already_done: set[str] = set()
    existing_results: list[dict] = []
    if resume and OUT_FILE.exists():
        with OUT_FILE.open(encoding="utf-8") as f:
            existing_results = json.load(f)
        already_done = {r["module"] for r in existing_results}
        log.info("Resuming — %d already processed", len(already_done))

    if max_modules:
        target = target[:max_modules]

    results = list(existing_results)
    errors: list[dict] = []

    for i, mod in enumerate(target, 1):
        name = mod["name"]
        if name in already_done:
            log.debug("Skipping (already done): %s", name)
            continue

        log.info("[%d/%d] Processing: %s", i, len(target), name)
        prompt = build_user_prompt(name, mod["raw_text"], mod["domain"])

        try:
            structured = call_deepseek(prompt)
            # Ensure domain and module name are consistent
            structured.setdefault("module", name)
            structured.setdefault("domain", mod["domain"])
            results.append(structured)
        except Exception as exc:
            log.error("FAILED %s: %s", name, exc)
            errors.append({"module": name, "error": str(exc)})
            with ERR_FILE.open("a", encoding="utf-8") as ef:
                ef.write(json.dumps({"module": name, "error": str(exc)}) + "\n")

        # Persist after each module so progress isn't lost on interruption
        _save_results(results)

        # Polite rate-limiting (DeepSeek free tier: ~3 req/s)
        time.sleep(0.4)

    log.info("Extraction complete. Success: %d  Errors: %d", len(results), len(errors))
    return results


def _save_results(results: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="VistA LLM feature extraction")
    parser.add_argument("--max",    type=int, default=None, help="Max modules to process (for testing)")
    parser.add_argument("--resume", action="store_true",    help="Skip already-processed modules")
    args = parser.parse_args()

    results = run_extraction(max_modules=args.max, resume=args.resume)
    print(f"\n✓  Structured modules saved → {OUT_FILE}")
    print(f"   Total processed: {len(results)}")
