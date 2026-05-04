# Thyroid Cancer Pathology Abstraction | Replication Package

This repository accompanies the poster:

> **Evaluating Open-Source Large Language Models for Automated Abstraction of Thyroid Cancer Pathology Data**
> Larry Grullon-Polanco, Colleen Veloski, Elio Monsour, Prerna Dogra, Valentina Tarasova, Lina Pedraza-Sanchez | Moffitt Cancer Center Symposium

## What this is

Seven open-weight LLMs were evaluated on zero-shot structured data extraction from
200 TCGA-THCA (The Cancer Genome Atlas Thyroid Carcinoma) pathology reports.
The task: extract five registry-style variables and compare against TCGA clinical labels.

**The central artifact is `prompt.md`** an abstraction prompt that encodes
extraction rules, section priorities, and tie-breaking logic for each variable. Performance
was driven more by prompt quality than model size. Pre-computed results are in `results/`.

## Results (weighted F1, held-out test set, N=200)

| Model               | Histology | ETE   | Margins | Site  | Size  | Average  |
|---------------------|-----------|-------|---------|-------|-------|----------|
| Llama 3.1 8B        | 0.95      | 0.91  | 0.94    | 0.90  | 0.93  | 0.926    |
| GPT OSS 20B         | 0.93      | 0.97  | 1.00    | 0.86  | 0.93  | 0.938    |
| Qwen3 32B           | 0.95      | 0.98  | 0.99    | 0.89  | 0.93  | 0.948    |
| Llama 3.3 70B       | 0.96      | 0.96  | 0.97    | 0.91  | 0.93  | 0.946    |
| GPT OSS 120B        | 0.94      | 0.96  | 0.99    | 0.86  | 0.93  | 0.936    |
| Mistral-Large (675B)| 0.96      | 0.98  | 0.97    | 0.87  | 0.92  | 0.940    |
| Kimi-K2 (1T)        | 0.96      | 0.98  | 0.99    | 0.91  | 0.94  | **0.956**|

## Repository structure

```
Poster Repo/
├── prompt.md                   # The abstraction prompt (primary artifact)
├── requirements.txt
├── .env.example                # API key template
├── data/
│   ├── reports/                # 200 TCGA-THCA parsed pathology reports (markdown)
│   ├── gold_standard.csv       # Reference labels for 200 test cases
│   └── final_split.csv         # Patient IDs in the test set
├── src/
│   ├── run_inference.py        # Run zero-shot inference for any model
│   ├── evaluate.py             # Compute weighted F1 against gold standard
│   └── normalization.py        # Value normalization functions
└── results/
    └── summary_metrics.csv     # Pre-computed results from the study
```

## To reproduce

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set up API keys

```bash
cp .env.example .env
# Edit .env and add your keys
```

Free Groq accounts can run all models except Mistral-Large (which uses OpenRouter).
Model availability may change — check [groq.com](https://groq.com) and [openrouter.ai](https://openrouter.ai)
for current model IDs. All models were run at `temperature=0.0`.

### 3. Run inference

```bash
# Run all models
python src/run_inference.py

# Run specific models
python src/run_inference.py --models llama-3.1-8b llama-3.3-70b
```

Outputs are saved to `output/predictions_{model}.csv`. Runs are idempotent,
already-completed cases are skipped if you re-run.

### 4. Evaluate

```bash
python src/evaluate.py
```

This prints a weighted F1 table to stdout. To save results:

```bash
python src/evaluate.py --output results/my_run.csv
```

## Data

Pathology reports in `data/reports/` are parsed markdown text extracted from TCGA-THCA PDFs.
The original PDFs and clinical XMLs are available from the NCI GDC portal
(requires free registration): [https://portal.gdc.cancer.gov/](https://portal.gdc.cancer.gov/).
Search for project TCGA-THCA.

Gold standard labels in `data/gold_standard.csv` were derived from the corresponding
TCGA clinical XML files.

## Notes on reproducibility

- Model outputs may differ slightly from the study due to API updates or model version changes.
  The study used fixed model versions as listed in the poster.
- The prompt in `prompt.md` and `src/run_inference.py` is identical to the one used in the study.
- Results without re-running inference are available in `results/summary_metrics.csv`.
