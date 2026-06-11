# Credit Risk Paper Search

This repository contains a small Python workflow for finding and screening
English journal articles for a course assignment on credit risk, default
prediction, imbalanced samples, and high-dimensional feature selection.

The script queries OpenAlex, scores candidate papers by topic relevance and
journal priority, excludes review-style publications, and writes CSV files for
manual verification and download.

## Files

- `paper_search.py` - OpenAlex search, screening, scoring, CSV export, and
  optional open-access PDF download.
- `test_paper_search.py` - Unit tests for abstract reconstruction, journal
  normalization, topic relevance, exclusion rules, scoring, and filename safety.

Generated files such as `results/*.csv`, downloaded PDFs, course attachments,
and local caches are intentionally ignored by git.

## Requirements

- Python 3.12 or compatible Python 3.x
- No third-party Python packages are required.
- Network access to `api.openalex.org`

OpenAlex may require a free API key. If needed, create one at:

```text
https://openalex.org/settings/api
```

Then run:

```bash
export OPENALEX_API_KEY="your_api_key"
```

Optionally set a contact email for polite API usage:

```bash
export OPENALEX_MAILTO="your_email@example.com"
```

## Usage

Run the tests:

```bash
python3 -m unittest test_paper_search.py
```

Generate candidate CSV files:

```bash
python3 paper_search.py --limit-per-query 100 --top-n 35
```

This writes:

- `results/候选外文文献.csv`
- `results/外文35篇初筛.csv`
- `results/需要手动下载_外文.csv`

To also try downloading open-access PDFs:

```bash
python3 paper_search.py --limit-per-query 100 --top-n 35 --download-pdfs
```

PDF downloads are limited to openly available URLs returned by OpenAlex. The
script does not bypass publisher paywalls or institutional login requirements.

## Screening Logic

The workflow prioritizes papers that match the assignment topic through terms
such as:

- credit risk
- default prediction
- bankruptcy forecasting
- financial distress
- credit scoring
- class imbalance
- high-dimensional data
- feature selection
- explainable or interpretable machine learning

It excludes likely review-style publications, including titles or abstracts
containing terms such as `literature review`, `systematic review`,
`bibliometric`, or `survey`.

The output is an automated first pass. The final paper list should still be
checked manually against the course-approved journal list, UTD24, or FT50.
