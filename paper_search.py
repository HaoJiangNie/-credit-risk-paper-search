#!/usr/bin/env python3
"""Search and screen English papers for the credit-risk assignment.

The script uses OpenAlex because it exposes enough metadata for bulk screening:
article type, year, venue, DOI, abstract, citation count, and open-access links.
It does not bypass publisher paywalls.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


CURRENT_YEAR = 2026
OPENALEX_WORKS_URL = "https://api.openalex.org/works"

QUERIES = [
    "credit risk default prediction imbalanced data",
    "corporate default prediction high-dimensional feature selection",
    "financial distress prediction machine learning imbalanced",
    "bankruptcy forecasting class imbalance credit risk",
    "credit risk monitoring default prediction machine learning",
    "high dimensional data credit scoring default prediction",
    "interpretable machine learning credit risk prediction",
    "business failure prediction machine learning",
    "creditworthiness prediction machine learning",
    "SME credit risk prediction machine learning",
    "loan default prediction machine learning",
    "corporate bankruptcy prediction feature selection",
    "financial distress prediction XGBoost",
    "P2P lending default prediction imbalanced",
]

TARGET_JOURNALS = {
    # Finance, accounting, and economics journals shown in / consistent with Attachment 2.
    "Journal of Banking & Finance",
    "Journal of Corporate Finance",
    "Journal of Financial Economics",
    "Journal of Financial Intermediation",
    "Journal of Financial and Quantitative Analysis",
    "Journal of Finance",
    "Review of Financial Studies",
    "Review of Finance",
    "Journal of Econometrics",
    "Journal of Business & Economic Statistics",
    "Journal of the American Statistical Association",
    "Econometrica",
    "Management Science",
    "Operations Research",
    "Information Systems Research",
    "MIS Quarterly",
    # Common credit-risk outlets likely useful for manual Attachment 2 verification.
    "International Review of Financial Analysis",
    "European Journal of Operational Research",
    "Decision Support Systems",
    "Expert Systems with Applications",
    "Omega",
    "Applied Soft Computing",
    "Knowledge-Based Systems",
    "Finance Research Letters",
    "Research in International Business and Finance",
}

NORMALIZED_TARGET_JOURNALS = {
    # Keep normalized names precomputed for fast scoring.
    # Values are not used; a set gives simpler membership checks.
    # Built at import time for tests and script use.
}

KEYWORD_PATTERNS = [
    ("credit risk", r"\bcredit risk\b"),
    ("default prediction", r"\b(default|defaults|defaulting)\b.*\b(prediction|forecasting|model|models)\b"),
    ("bankruptcy forecasting", r"\b(bankruptcy|insolvency)\b.*\b(prediction|forecasting|model|models)\b"),
    ("financial distress", r"\bfinancial distress\b"),
    ("credit scoring", r"\bcredit scoring\b"),
    ("credit monitoring", r"\bcredit monitoring\b|\bmonitoring\b.*\bcredit\b"),
    ("loan default", r"\bloan default\b|\blending default\b|\bp2p lending\b"),
    ("creditworthiness", r"\bcreditworthiness\b|\bcredit worthiness\b"),
    ("business failure", r"\bbusiness failure\b|\bfirm failure\b|\bcompany failure\b"),
    ("high-dimensional", r"\bhigh[- ]dimensional\b|\bfeature selection\b|\bvariable selection\b"),
    ("imbalanced", r"\bimbalanced\b|\bclass imbalance\b|\bunbalanced sample\b|\bminority class\b"),
    ("machine learning", r"\bmachine learning\b|\bdeep learning\b|\brandom forest\b|\bxgboost\b|\bneural network"),
    ("interpretability", r"\binterpretable\b|\binterpretability\b|\bexplainable\b|\bshap\b"),
]

PRIMARY_TOPIC_LABELS = {
    "credit risk",
    "default prediction",
    "bankruptcy forecasting",
    "financial distress",
    "credit scoring",
    "credit monitoring",
    "loan default",
    "creditworthiness",
    "business failure",
}

EXCLUSION_PATTERNS = [
    r"\bliterature review\b",
    r"\bsystematic review\b",
    r"\bscoping review\b",
    r"\bbibliometric\b",
    r"\bsurvey\b",
    r"\breview of\b",
    r"\brecent developments\b",
    r"\bfuture directions\b",
]


def normalize_journal_name(name: str | None) -> str:
    text = (name or "").strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


NORMALIZED_TARGET_JOURNALS = {normalize_journal_name(name) for name in TARGET_JOURNALS}


def abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    positions: dict[int, str] = {}
    for word, offsets in index.items():
        for offset in offsets:
            positions[offset] = word
    return " ".join(positions[i] for i in sorted(positions))


def matched_keyword_labels(work: dict[str, Any]) -> list[str]:
    text = f"{work.get('title', '')} {work.get('abstract', '')}".lower()
    labels = []
    for label, pattern in KEYWORD_PATTERNS:
        if re.search(pattern, text):
            labels.append(label)
    return labels


def is_topic_relevant(work: dict[str, Any]) -> bool:
    labels = set(matched_keyword_labels(work))
    return bool(labels & PRIMARY_TOPIC_LABELS)


def is_excluded_publication(work: dict[str, Any]) -> bool:
    text = f"{work.get('title', '')} {work.get('abstract', '')}".lower()
    return any(re.search(pattern, text) for pattern in EXCLUSION_PATTERNS)


def extract_source(location: dict[str, Any] | None) -> str:
    if not location:
        return ""
    source = location.get("source") or {}
    return source.get("display_name") or ""


def first_pdf_url(work: dict[str, Any]) -> str:
    for key in ("best_oa_location", "primary_location"):
        location = work.get(key) or {}
        if location.get("pdf_url"):
            return location["pdf_url"]

    for location in work.get("locations") or []:
        if location.get("pdf_url"):
            return location["pdf_url"]

    open_access = work.get("open_access") or {}
    return open_access.get("oa_url") or ""


def authors_to_text(authorships: list[dict[str, Any]] | None, limit: int = 8) -> str:
    names = []
    for authorship in authorships or []:
        author = authorship.get("author") or {}
        name = author.get("display_name")
        if name:
            names.append(name)
    if len(names) > limit:
        return ", ".join(names[:limit]) + " et al."
    return ", ".join(names)


def parse_openalex_work(raw: dict[str, Any]) -> dict[str, Any]:
    primary_location = raw.get("primary_location") or {}
    best_oa_location = raw.get("best_oa_location") or {}
    journal = extract_source(primary_location) or extract_source(best_oa_location)
    open_access = raw.get("open_access") or {}
    biblio = raw.get("biblio") or {}

    doi = raw.get("doi") or ""
    if doi.startswith("https://doi.org/"):
        doi = doi.removeprefix("https://doi.org/")

    return {
        "openalex_id": raw.get("id") or "",
        "title": raw.get("display_name") or "",
        "authors": authors_to_text(raw.get("authorships")),
        "publication_year": raw.get("publication_year") or "",
        "publication_date": raw.get("publication_date") or "",
        "journal": journal,
        "doi": doi,
        "volume": biblio.get("volume") or "",
        "issue": biblio.get("issue") or "",
        "first_page": biblio.get("first_page") or "",
        "last_page": biblio.get("last_page") or "",
        "cited_by_count": raw.get("cited_by_count") or 0,
        "is_oa": open_access.get("is_oa", False),
        "oa_status": open_access.get("oa_status") or "",
        "pdf_url": first_pdf_url(raw),
        "landing_page_url": (
            primary_location.get("landing_page_url")
            or best_oa_location.get("landing_page_url")
            or open_access.get("oa_url")
            or ""
        ),
        "abstract": abstract_from_inverted_index(raw.get("abstract_inverted_index")),
    }


def score_work(work: dict[str, Any]) -> dict[str, Any]:
    matched = matched_keyword_labels(work)
    score = 0

    for label in matched:
        score += 2

    normalized_journal = normalize_journal_name(work.get("journal"))
    if normalized_journal in NORMALIZED_TARGET_JOURNALS:
        score += 4
        source_match = "附件2/重点外文期刊"
    else:
        source_match = "待人工核验期刊来源"

    try:
        year = int(work.get("publication_year") or 0)
    except (TypeError, ValueError):
        year = 0
    if 2020 <= year <= CURRENT_YEAR:
        score += 1

    if work.get("doi"):
        score += 1
    if work.get("pdf_url"):
        score += 1
    score += min(int(work.get("cited_by_count") or 0) // 25, 3)

    enriched = dict(work)
    enriched["score"] = score
    enriched["source_match"] = source_match
    enriched["matched_keywords"] = "; ".join(matched)
    return enriched


def slugify_filename(title: str, doi: str = "") -> str:
    base = re.sub(r"[\\/:*?\"<>|]+", "_", title).strip(" ._")
    base = re.sub(r"\s+", "_", base)
    base = re.sub(r"_+", "_", base)
    base = base[:90] or "paper"
    suffix = re.sub(r"[\\/:*?\"<>|\s]+", "_", doi).strip(" ._")
    suffix = re.sub(r"_+", "_", suffix)
    if suffix:
        base = f"{base}_{suffix[:40]}"
    return f"{base}.pdf"


def openalex_get(params: dict[str, str | int], timeout: int = 40) -> dict[str, Any]:
    query = dict(params)
    api_key = os.environ.get("OPENALEX_API_KEY")
    mailto = os.environ.get("OPENALEX_MAILTO")
    if api_key:
        query["api_key"] = api_key
    if mailto:
        query["mailto"] = mailto

    url = f"{OPENALEX_WORKS_URL}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": "course-paper-search/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def search_openalex(limit_per_query: int, sleep_seconds: float) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    fields = ",".join(
        [
            "id",
            "doi",
            "display_name",
            "publication_year",
            "publication_date",
            "type",
            "cited_by_count",
            "primary_location",
            "best_oa_location",
            "locations",
            "open_access",
            "abstract_inverted_index",
            "authorships",
            "biblio",
        ]
    )
    filters = "from_publication_date:2020-01-01,to_publication_date:2026-12-31,type:article"

    for query in QUERIES:
        data = openalex_get(
            {
                "search": query,
                "filter": filters,
                "per-page": limit_per_query,
                "sort": "cited_by_count:desc",
                "select": fields,
            }
        )
        for raw in data.get("results") or []:
            work = parse_openalex_work(raw)
            if not is_topic_relevant(work) or is_excluded_publication(work):
                continue
            key = (work.get("doi") or work.get("openalex_id") or work.get("title")).lower()
            if not key:
                continue
            scored = score_work(work)
            if key not in rows or scored["score"] > rows[key]["score"]:
                rows[key] = scored
        time.sleep(sleep_seconds)

    return sorted(rows.values(), key=lambda item: (item["score"], item["cited_by_count"]), reverse=True)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "rank",
        "score",
        "source_match",
        "matched_keywords",
        "title",
        "authors",
        "publication_year",
        "journal",
        "doi",
        "volume",
        "issue",
        "first_page",
        "last_page",
        "cited_by_count",
        "is_oa",
        "oa_status",
        "pdf_url",
        "landing_page_url",
        "local_pdf",
        "openalex_id",
        "abstract",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for rank, row in enumerate(rows, start=1):
            output = dict(row)
            output["rank"] = rank
            writer.writerow(output)


def download_pdf(url: str, output_path: Path, timeout: int = 60) -> bool:
    if not url or output_path.exists():
        return bool(url and output_path.exists())
    request = urllib.request.Request(url, headers={"User-Agent": "course-paper-search/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("content-type", "").lower()
            data = response.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return False

    if b"%PDF" not in data[:1024] and "pdf" not in content_type:
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data)
    return True


def maybe_download_pdfs(rows: list[dict[str, Any]], output_dir: Path) -> None:
    for row in rows:
        pdf_url = row.get("pdf_url") or ""
        if not pdf_url:
            row["local_pdf"] = ""
            continue
        filename = slugify_filename(row.get("title") or "", row.get("doi") or "")
        path = output_dir / filename
        if download_pdf(pdf_url, path):
            row["local_pdf"] = str(path)
        else:
            row["local_pdf"] = ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit-per-query", type=int, default=50)
    parser.add_argument("--top-n", type=int, default=35)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--download-pdfs", action="store_true")
    parser.add_argument("--out-dir", default="results")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    candidate_path = out_dir / "候选外文文献.csv"
    selected_path = out_dir / "外文35篇初筛.csv"
    manual_path = out_dir / "需要手动下载_外文.csv"
    pdf_dir = Path("参考文献") / "外文开放获取"

    try:
        candidates = search_openalex(args.limit_per_query, args.sleep)
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403, 429}:
            print(
                "OpenAlex request was rejected. Set OPENALEX_API_KEY to a free API key "
                "from https://openalex.org/settings/api and rerun.",
                flush=True,
            )
        raise

    selected = candidates[: args.top_n]
    if args.download_pdfs:
        maybe_download_pdfs(selected, pdf_dir)
    else:
        for row in selected:
            row["local_pdf"] = ""
    for row in candidates:
        row.setdefault("local_pdf", "")

    manual = [row for row in selected if not row.get("local_pdf")]

    write_csv(candidate_path, candidates)
    write_csv(selected_path, selected)
    write_csv(manual_path, manual)

    print(f"Wrote {len(candidates)} candidates to {candidate_path}")
    print(f"Wrote top {len(selected)} records to {selected_path}")
    print(f"Wrote {len(manual)} manual-download records to {manual_path}")
    if args.download_pdfs:
        downloaded = sum(1 for row in selected if row.get("local_pdf"))
        print(f"Downloaded {downloaded} open-access PDFs to {pdf_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
