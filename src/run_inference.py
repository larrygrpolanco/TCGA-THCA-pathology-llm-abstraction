"""
Run zero-shot LLM inference on thyroid cancer pathology reports.

Reads patient IDs from data/final_split.csv, loads the corresponding parsed
report from data/reports/, calls the LLM, and appends structured JSON output
to output/predictions_{model}.csv.

Requires a .env file with API keys (see .env.example).
"""

import os
import csv
import json
import time
import argparse
import requests
from pathlib import Path
from typing import Dict, Set, Tuple
from dotenv import load_dotenv
from groq import Groq

# -----------------------------------------------------------------------------
# MODELS
# Uncomment models you want to run. Groq models are faster/cheaper.
# OpenRouter is needed for Mistral-Large.
# Check current availability at groq.com and openrouter.ai.
# -----------------------------------------------------------------------------

MODELS = {
    "llama-3.1-8b":     {"id": "llama-3.1-8b-instant",            "provider": "groq"},
    "llama-3.3-70b":    {"id": "llama-3.3-70b-versatile",          "provider": "groq"},
    "gpt-oss-20b":      {"id": "openai/gpt-oss-20b",               "provider": "groq"},
    "gpt-oss-120b":     {"id": "openai/gpt-oss-120b",              "provider": "groq"},
    "qwen3-32b":        {"id": "qwen/qwen3-32b",                   "provider": "groq"},
    "kimi-k2":          {"id": "moonshotai/kimi-k2-instruct-0905", "provider": "groq"},
    "mistral-large":    {"id": "mistralai/mistral-large-2512",     "provider": "openrouter"},
}

# -----------------------------------------------------------------------------
# PATHS
# -----------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE_DIR / "data" / "reports"
SPLIT_FILE = BASE_DIR / "data" / "final_split.csv"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# -----------------------------------------------------------------------------
# PROMPT  (also available as a standalone file: prompt.md)
# -----------------------------------------------------------------------------

SYSTEM_PROMPT = """Role: Clinical data abstractor for cancer registry coding.
Task: Extract structured variables from pathology reports following rules below.

--- EXTRACTION RULES ---

1. histologic_variant:
   - Options: "Classical" | "Follicular" | "Tall Cell"
   - RULES:
     A. Extract variant ONLY from the final diagnosis line, NOT from microscopic descriptions.
     B. "Follicular/Tall Cell features" or "architecture" → ignore (these describe cellular patterns, not the variant).
     C. If multiple variants mentioned, use the one in the PRIMARY/DOMINANT tumor only.
     D. DEFAULT: If diagnosis says "Papillary Thyroid Carcinoma" without specifying variant → "Classical".

2. tumor_site (The Bilateral Rule):
   - Options: "Right lobe" | "Left lobe" | "Isthmus" | "Bilateral"
   - Rules:
     A. Identify the location of the DOMINANT (largest) nodule.
     B. LOGIC GATE - SECONDARY TUMORS:
        - Look for other tumors in the CONTRALATERAL lobe (Left vs Right).
        - IGNORE any secondary tumor that is ≤ 1.0 cm. It does not exist for this task.
        - IGNORE any tumor in the Isthmus when calculating Bilaterality.
     C. If a tumor > 1.0 cm exists in the Right Lobe AND a tumor > 1.0 cm exists in the Left Lobe -> Output "Bilateral".
     D. "Right Lobe" + "Isthmus" = "Right Lobe".
     E. "Left Lobe" + "Isthmus" = "Left Lobe".
     F. Otherwise, output the site of the dominant nodule.

3. extrathyroidal_extension:
   - Options: "No ETE" | "Microscopic" | "Gross"
   - Rules:
     A. Check Synoptic table first and trust the *descriptive text* over the TNM stage code
        (staging criteria vary by AJCC edition).
     B. "Not identified", "Absent", "Intrathyroidal", "Confined/limited to thyroid" -> "No ETE"
     C. "Present", "Identified", "Microscopic extension", "Invades fat/soft tissue" -> "Microscopic"
     D. "Gross extension", "Macroscopic", "Invades strap muscles/trachea" -> "Gross"

4. margins:
   - Options: "R0" | "R1" | "R2"
   - Rules:
     A. "Uninvolved", "Negative", "Clear", or if no involvement is mentioned -> "R0" (even if close).
     B. "Involved", "Positive", or "Focal involvement" -> "R1".

5. tumor_size (Header Priority):
   - Type: Float (cm).
   - Rules:
     A. Extract the size of the largest MALIGNANT tumor focus.
     B. IGNORE sizes of benign nodules, cysts, adenomas, or "nodular hyperplasia,"
        even if larger than the carcinoma.
     C. Synoptic Data / Final Diagnosis takes priority.
     D. EXCEPTION: Use Gross Description ONLY if Synoptic/Diagnosis is missing tumor size.
        If both exist, Synoptic/Final Diagnosis is the final truth.
     E. Convert mm to cm.

--- OUTPUT FORMAT ---
Return a JSON object:
{
  "histologic_variant": "Classical | Follicular | Tall Cell",
  "tumor_site": "Right lobe | Left lobe | Isthmus | Bilateral",
  "extrathyroidal_extension": "No ETE | Microscopic | Gross",
  "margins": "R0 | R1 | R2",
  "tumor_size": Float
}
"""

USER_PROMPT_TEMPLATE = "Report:\n---\n{report_text}\n---\n"

# -----------------------------------------------------------------------------
# API
# -----------------------------------------------------------------------------

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY")) if os.getenv("GROQ_API_KEY") else None
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def call_llm(provider: str, model_id: str, report_text: str) -> Tuple[str, str]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(report_text=report_text)},
    ]
    try:
        if provider == "groq":
            if not groq_client:
                return "GROQ_API_KEY not set in .env", "error"
            resp = groq_client.chat.completions.create(
                messages=messages,
                model=model_id,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            return resp.choices[0].message.content, "success"

        elif provider == "openrouter":
            if not OPENROUTER_API_KEY:
                return "OPENROUTER_API_KEY not set in .env", "error"
            r = requests.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json={"model": model_id, "messages": messages, "temperature": 0.0,
                      "response_format": {"type": "json_object"}},
                timeout=60,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"], "success"

    except Exception as e:
        return str(e), "error"

    return "Unknown provider", "error"


# -----------------------------------------------------------------------------
# INFERENCE LOOP
# -----------------------------------------------------------------------------

def get_completed(output_csv: Path) -> Set[str]:
    if not output_csv.exists():
        return set()
    with open(output_csv, encoding="utf-8") as f:
        return {r["patient_id"].strip() for r in csv.DictReader(f) if r.get("patient_id")}


def run_model(model_alias: str, model_config: Dict, patient_ids: list):
    output_csv = OUTPUT_DIR / f"predictions_{model_alias}.csv"

    if not output_csv.exists():
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["patient_id", "model", "timestamp", "status", "raw_response", "parsed_json"])

    completed = get_completed(output_csv)
    remaining = [pid for pid in patient_ids if pid not in completed]
    print(f"\n{model_alias}: {len(remaining)} cases to process ({len(completed)} already done)")

    for i, pid in enumerate(remaining):
        report_path = REPORTS_DIR / f"{pid}.md"
        if not report_path.exists():
            print(f"  [{i+1}] {pid}: report not found, skipping")
            continue

        report_text = report_path.read_text(encoding="utf-8")
        print(f"  [{i+1}/{len(remaining)}] {pid}...", end=" ", flush=True)

        raw, status = call_llm(model_config["provider"], model_config["id"], report_text)

        parsed_json = ""
        if status == "success":
            try:
                clean = raw.replace("```json", "").replace("```", "").strip()
                json.loads(clean)
                parsed_json = clean
                print("OK")
            except json.JSONDecodeError:
                parsed_json = "JSON_ERROR"
                print("JSON_FAIL")
        else:
            print(f"ERROR: {raw[:80]}")

        with open(output_csv, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                [pid, model_alias, time.strftime("%Y-%m-%d %H:%M:%S"), status, raw, parsed_json]
            )

        time.sleep(0.3)


def main():
    parser = argparse.ArgumentParser(description="Run LLM inference on TCGA-THCA pathology reports")
    parser.add_argument("--models", nargs="+", choices=list(MODELS.keys()),
                        default=list(MODELS.keys()), help="Models to run (default: all)")
    args = parser.parse_args()

    with open(SPLIT_FILE, encoding="utf-8") as f:
        patient_ids = [r["patient_id"].strip() for r in csv.DictReader(f)]

    for alias in args.models:
        run_model(alias, MODELS[alias], patient_ids)


if __name__ == "__main__":
    main()
