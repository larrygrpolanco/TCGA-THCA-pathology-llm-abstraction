"""
Evaluate LLM predictions against gold standard labels.

Reads output/predictions_{model}.csv files (produced by run_inference.py),
merges with data/gold_standard.csv, computes weighted F1 per variable,
and prints a summary table.

Usage:
    python src/evaluate.py
    python src/evaluate.py --output results/my_metrics.csv
"""

import json
import argparse
import pandas as pd
from pathlib import Path
from sklearn.metrics import precision_recall_fscore_support, accuracy_score

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalization import (
    normalize_histologic_variant,
    normalize_ete,
    normalize_margins,
    normalize_site,
    normalize_numeric_float,
)

BASE_DIR = Path(__file__).resolve().parent.parent
GOLD_CSV = BASE_DIR / "data" / "gold_standard.csv"
OUTPUT_DIR = BASE_DIR / "output"

FIELDS = {
    "histologic_variant":    normalize_histologic_variant,
    "extrathyroidal_extension": normalize_ete,
    "margins":               normalize_margins,
    "tumor_site":            normalize_site,
    "tumor_size":            normalize_numeric_float,
}


def load_predictions(pred_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(pred_csv)
    df = df[df["status"] == "success"].copy()
    parsed = df["parsed_json"].apply(lambda x: json.loads(x) if x and x != "JSON_ERROR" else {})
    df2 = pd.json_normalize(parsed)
    return pd.concat([df[["patient_id"]].reset_index(drop=True), df2.reset_index(drop=True)], axis=1)


def evaluate_model(pred_csv: Path, gold_df: pd.DataFrame) -> list:
    model_name = pred_csv.stem.replace("predictions_", "")
    pred_df = load_predictions(pred_csv)
    merged = pred_df.merge(gold_df, on="patient_id", suffixes=("_llm", "_gold"))
    rows = []
    for field, norm_fn in FIELDS.items():
        col_llm = f"{field}_llm" if f"{field}_llm" in merged.columns else field
        y_pred = merged[col_llm].apply(lambda x: norm_fn(x) if pd.notnull(x) else None).fillna("missing").astype(str)
        y_true = merged[f"{field}_gold"].apply(lambda x: norm_fn(x) if pd.notnull(x) else None).fillna("missing").astype(str)
        acc = accuracy_score(y_true, y_pred)
        _, _, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="weighted", zero_division=0)
        rows.append({"model": model_name, "variable": field, "accuracy": round(acc, 4), "weighted_f1": round(f1, 4)})
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=None, help="Optional CSV path to save results")
    args = parser.parse_args()

    gold_df = pd.read_csv(GOLD_CSV)
    pred_files = sorted(OUTPUT_DIR.glob("predictions_*.csv"))

    if not pred_files:
        print("No prediction files found in output/. Run src/run_inference.py first.")
        return

    all_rows = []
    for pred_csv in pred_files:
        rows = evaluate_model(pred_csv, gold_df)
        all_rows.extend(rows)

    results = pd.DataFrame(all_rows)

    # Print pivot table
    pivot = results.pivot_table(index="model", columns="variable", values="weighted_f1")
    pivot["average"] = pivot.mean(axis=1).round(4)
    print("\nWeighted F1 by model and variable:")
    print(pivot.to_string())

    if args.output:
        results.to_csv(args.output, index=False)
        print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()
