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
import zlib
from pathlib import Path
from typing import Any


CURRENT_YEAR = 2026
OPENALEX_WORKS_URL = "https://api.openalex.org/works"
OPENALEX_SOURCES_URL = "https://api.openalex.org/sources"
SOURCE_QUERIES = [
    "credit risk",
    "default risk",
    "default prediction",
    "credit scoring",
    "financial distress",
    "bankruptcy",
    "business failure",
    "loan default",
    "non-performing loans",
    "creditworthiness",
]

UTD24_JOURNALS = {
    "Academy of Management Journal",
    "Academy of Management Review",
    "Accounting Review",
    "Administrative Science Quarterly",
    "Contemporary Accounting Research",
    "Information Systems Research",
    "Journal of Accounting and Economics",
    "Journal of Accounting Research",
    "Journal of Consumer Research",
    "Journal of Finance",
    "Journal of Financial Economics",
    "Journal of International Business Studies",
    "Journal of Marketing",
    "Journal of Marketing Research",
    "Management Science",
    "Manufacturing & Service Operations Management",
    "Marketing Science",
    "MIS Quarterly",
    "Operations Research",
    "Organization Science",
    "Production and Operations Management",
    "Review of Financial Studies",
    "Strategic Management Journal",
    "The Accounting Review",
}

FT50_JOURNALS = {
    "Academy of Management Annals",
    "Academy of Management Journal",
    "Academy of Management Review",
    "Accounting Review",
    "Accounting, Organizations and Society",
    "Administrative Science Quarterly",
    "American Economic Review",
    "American Sociological Review",
    "Contemporary Accounting Research",
    "Econometrica",
    "Entrepreneurship Theory and Practice",
    "Harvard Business Review",
    "Human Resource Management",
    "Information Systems Research",
    "Journal of Accounting and Economics",
    "Journal of Accounting Research",
    "Journal of Applied Psychology",
    "Journal of Business Venturing",
    "Journal of Consumer Psychology",
    "Journal of Consumer Research",
    "Journal of Finance",
    "Journal of Financial and Quantitative Analysis",
    "Journal of Financial Economics",
    "Journal of International Business Studies",
    "Journal of Management",
    "Journal of Management Information Systems",
    "Journal of Management Studies",
    "Journal of Marketing",
    "Journal of Marketing Research",
    "Journal of Operations Management",
    "Journal of Political Economy",
    "Journal of the Academy of Marketing Science",
    "Management Science",
    "Manufacturing & Service Operations Management",
    "Marketing Science",
    "MIS Quarterly",
    "MIT Sloan Management Review",
    "Operations Research",
    "Organization Science",
    "Organizational Behavior and Human Decision Processes",
    "Production and Operations Management",
    "Psychological Science",
    "Quarterly Journal of Economics",
    "Research Policy",
    "Review of Accounting Studies",
    "Review of Economic Studies",
    "Review of Finance",
    "Review of Financial Studies",
    "Strategic Entrepreneurship Journal",
    "Strategic Management Journal",
}

PRIORITY_WHITELIST_JOURNALS = {
    "Accounting Review",
    "AccountingOrganizationsandSociety",
    "AmericanEconomicReview",
    "ContemporaryAccountingResearch",
    "Econometrica",
    "EconomicJournal",
    "EuropeanEconomicReview",
    "InformationSystemsResearch",
    "JournalofAccounting&Economics",
    "JournalofAccountingResearch",
    "JournalofBanking&Finance",
    "JournalofBusiness&EconomicStatistics",
    "JournalofCorporateFinance",
    "JournalofEconometrics",
    "JournalofEconomicTheory",
    "JournalofFinance",
    "JournalofFinancialandQuantitativeAnalysis",
    "JournalofFinancialEconomics",
    "JournalofFinancialIntermediation",
    "JournalofInternationalEconomics",
    "JournalofMonetaryEconomics",
    "JournalofPoliticalEconomy",
    "JournalofPublicEconomics",
    "ManagementScience",
    "MISQuarterly",
    "OperationsResearch",
    "QuarterlyJournalofEconomics",
    "ReviewofEconomicStudies",
    "ReviewofEconomicsandStatistics",
    "ReviewofFinance",
    "ReviewofFinancialStudies",
}

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
    ("default risk", r"\bdefault[- ]risk\b|\bdefault risk\b"),
    ("non-performing loans", r"\bnon[- ]performing loans?\b|\bnonperforming loans?\b|\bnpls?\b"),
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
    "default risk",
    "non-performing loans",
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
PRIORITY_WHITELIST_NORMALIZED = {
    normalize_journal_name(name) for name in PRIORITY_WHITELIST_JOURNALS
}


def parse_attachment2_foreign_journals(text: str) -> list[str]:
    return [record["journal_name"] for record in parse_attachment2_foreign_journal_records(text)]


def parse_attachment2_foreign_journal_records(text: str) -> list[dict[str, str]]:
    pattern = re.compile(
        r"\d+T\d+\d+([A-Za-z&,:]+?)(\d{4}-[0-9X]{4})(\d{4}-[0-9X]{4})"
    )
    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in pattern.finditer(text):
        name = match.group(1)
        normalized = normalize_journal_name(name)
        if normalized and normalized not in seen:
            records.append(
                {
                    "journal_name": name,
                    "issn": match.group(2),
                    "eissn": match.group(3),
                }
            )
            seen.add(normalized)
    return records


def _decode_pdf_hex(hex_text: str, cmap: dict[int, str]) -> str:
    data = bytes.fromhex(hex_text)
    result: list[str] = []
    i = 0
    while i < len(data):
        two_byte = (data[i] << 8) | data[i + 1] if i + 1 < len(data) else data[i]
        if i + 1 < len(data) and two_byte in cmap:
            result.append(cmap[two_byte])
            i += 2
        elif data[i] in cmap:
            result.append(cmap[data[i]])
            i += 1
        elif i + 1 < len(data):
            result.append(chr(two_byte) if 32 <= two_byte <= 126 else "")
            i += 2
        else:
            result.append(chr(data[i]) if 32 <= data[i] <= 126 else "")
            i += 1
    return "".join(result)


def _inflate_pdf_streams(path: Path) -> list[bytes]:
    data = path.read_bytes()
    streams: list[bytes] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        try:
            streams.append(zlib.decompress(match.group(1)))
        except zlib.error:
            continue
    return streams


def _parse_pdf_cmap(streams: list[bytes]) -> dict[int, str]:
    cmap: dict[int, str] = {}
    for stream in streams:
        if b"begincmap" not in stream:
            continue
        text = stream.decode("latin1", "ignore")
        for block in re.findall(r"beginbfchar\s*(.*?)\s*endbfchar", text, re.S):
            for src, dst in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
                try:
                    cmap[int(src, 16)] = bytes.fromhex(dst).decode("utf-16-be")
                except UnicodeDecodeError:
                    continue
        for block in re.findall(r"beginbfrange\s*(.*?)\s*endbfrange", text, re.S):
            for start, end, dst in re.findall(
                r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>",
                block,
            ):
                start_int = int(start, 16)
                end_int = int(end, 16)
                dst_int = int(dst, 16)
                for code in range(start_int, end_int + 1):
                    try:
                        cmap[code] = chr(dst_int + code - start_int)
                    except ValueError:
                        continue
    return cmap


def extract_pdf_text(path: Path) -> str:
    streams = _inflate_pdf_streams(path)
    cmap = _parse_pdf_cmap(streams)
    chunks: list[str] = []
    for stream in streams:
        if b" Tj" not in stream and b" TJ" not in stream:
            continue
        content = stream.decode("latin1", "ignore")
        for match in re.finditer(r"<([0-9A-Fa-f]+)>|\(([^()]*)\)", content):
            if match.group(1):
                chunks.append(_decode_pdf_hex(match.group(1), cmap))
            else:
                chunks.append(match.group(2) or "")
    return "".join(chunks)


def build_journal_whitelist(
    attachment_journals: list[str] | list[dict[str, str]] | None = None,
) -> dict[str, dict[str, str]]:
    whitelist: dict[str, dict[str, str]] = {}

    def add(name: str, source: str, issn: str = "", eissn: str = "") -> None:
        normalized = normalize_journal_name(name)
        if not normalized:
            return
        if normalized not in whitelist:
            whitelist[normalized] = {
                "journal_name": name,
                "normalized_name": normalized,
                "source_list": source,
                "issn": issn,
                "eissn": eissn,
                "openalex_source_id": "",
                "openalex_display_name": "",
            }
        elif source not in whitelist[normalized]["source_list"].split(";"):
            whitelist[normalized]["source_list"] += f";{source}"
        if issn and not whitelist[normalized]["issn"]:
            whitelist[normalized]["issn"] = issn
        if eissn and not whitelist[normalized]["eissn"]:
            whitelist[normalized]["eissn"] = eissn

    for item in attachment_journals or []:
        if isinstance(item, dict):
            add(item["journal_name"], "附件2", item.get("issn", ""), item.get("eissn", ""))
        else:
            add(item, "附件2")
    for name in sorted(UTD24_JOURNALS):
        add(name, "UTD24")
    for name in sorted(FT50_JOURNALS):
        add(name, "FT50")
    return whitelist


def is_whitelisted_journal(
    journal_name: str | None, whitelist: dict[str, dict[str, str]] | None
) -> bool:
    if not whitelist:
        return False
    return normalize_journal_name(journal_name) in whitelist


def whitelist_sources_for_journal(
    journal_name: str | None, whitelist: dict[str, dict[str, str]] | None
) -> str:
    if not whitelist:
        return ""
    entry = whitelist.get(normalize_journal_name(journal_name))
    return entry["source_list"] if entry else ""


def load_whitelist_from_attachment(attachment_path: Path) -> dict[str, dict[str, str]]:
    text = extract_pdf_text(attachment_path)
    attachment_records = parse_attachment2_foreign_journal_records(text)
    return build_journal_whitelist(attachment_records)


def write_whitelist_csv(path: Path, whitelist: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "journal_name",
                "normalized_name",
                "source_list",
                "issn",
                "eissn",
                "openalex_source_id",
                "openalex_display_name",
            ],
        )
        writer.writeheader()
        for row in sorted(whitelist.values(), key=lambda item: item["normalized_name"]):
            writer.writerow(row)


def read_whitelist_csv(path: Path) -> dict[str, dict[str, str]]:
    whitelist: dict[str, dict[str, str]] = {}
    if not path.exists():
        return whitelist
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            normalized = row.get("normalized_name") or normalize_journal_name(row.get("journal_name"))
            if not normalized:
                continue
            whitelist[normalized] = {
                "journal_name": row.get("journal_name", ""),
                "normalized_name": normalized,
                "source_list": row.get("source_list", ""),
                "issn": row.get("issn", ""),
                "eissn": row.get("eissn", ""),
                "openalex_source_id": row.get("openalex_source_id", ""),
                "openalex_display_name": row.get("openalex_display_name", ""),
            }
    return whitelist


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


def score_work(
    work: dict[str, Any], whitelist: dict[str, dict[str, str]] | None = None
) -> dict[str, Any]:
    matched = matched_keyword_labels(work)
    score = 0

    for label in matched:
        score += 2

    normalized_journal = normalize_journal_name(work.get("journal"))
    whitelist_source = whitelist_sources_for_journal(work.get("journal"), whitelist)
    if whitelist_source:
        score += 6
        source_match = "白名单期刊"
    elif normalized_journal in NORMALIZED_TARGET_JOURNALS:
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
    enriched["whitelist_source"] = whitelist_source
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


def openalex_json_get(
    base_url: str, params: dict[str, str | int], timeout: int = 40
) -> dict[str, Any]:
    query = dict(params)
    api_key = os.environ.get("OPENALEX_API_KEY")
    mailto = os.environ.get("OPENALEX_MAILTO")
    if api_key:
        query["api_key"] = api_key
    if mailto:
        query["mailto"] = mailto

    url = f"{base_url}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": "course-paper-search/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def openalex_get(params: dict[str, str | int], timeout: int = 40) -> dict[str, Any]:
    return openalex_json_get(OPENALEX_WORKS_URL, params, timeout)


def openalex_sources_get(params: dict[str, str | int], timeout: int = 40) -> dict[str, Any]:
    return openalex_json_get(OPENALEX_SOURCES_URL, params, timeout)


def short_openalex_id(openalex_id: str) -> str:
    return openalex_id.rstrip("/").split("/")[-1]


def resolve_openalex_source(entry: dict[str, str]) -> dict[str, str] | None:
    for issn_key in ("issn", "eissn"):
        issn = entry.get(issn_key)
        if not issn:
            continue
        data = openalex_sources_get(
            {
                "filter": f"issn:{issn}",
                "per-page": 1,
                "select": "id,display_name,issn_l,issn,type",
            }
        )
        if data.get("results"):
            source = data["results"][0]
            return {
                "id": source.get("id", ""),
                "display_name": source.get("display_name", ""),
            }

    data = openalex_sources_get(
        {
            "search": entry["journal_name"],
            "per-page": 5,
            "select": "id,display_name,issn_l,issn,type",
        }
    )
    normalized = entry["normalized_name"]
    for source in data.get("results") or []:
        if normalize_journal_name(source.get("display_name")) == normalized:
            return {
                "id": source.get("id", ""),
                "display_name": source.get("display_name", ""),
            }
    return None


def enrich_whitelist_with_openalex_sources(
    whitelist: dict[str, dict[str, str]], sleep_seconds: float
) -> None:
    for entry in whitelist.values():
        if entry.get("openalex_source_id"):
            continue
        source = resolve_openalex_source(entry)
        if source:
            entry["openalex_source_id"] = source["id"]
            entry["openalex_display_name"] = source["display_name"]
        time.sleep(sleep_seconds)


def search_openalex(
    limit_per_query: int,
    sleep_seconds: float,
    whitelist: dict[str, dict[str, str]] | None = None,
    strict_whitelist: bool = False,
) -> list[dict[str, Any]]:
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
            if strict_whitelist and not is_whitelisted_journal(work.get("journal"), whitelist):
                continue
            key = (work.get("doi") or work.get("openalex_id") or work.get("title")).lower()
            if not key:
                continue
            scored = score_work(work, whitelist)
            if key not in rows or scored["score"] > rows[key]["score"]:
                rows[key] = scored
        time.sleep(sleep_seconds)

    return sorted(rows.values(), key=lambda item: (item["score"], item["cited_by_count"]), reverse=True)


def search_openalex_by_whitelist_sources(
    whitelist: dict[str, dict[str, str]],
    per_source: int,
    sleep_seconds: float,
    priority_only: bool = False,
) -> list[dict[str, Any]]:
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

    for entry in sorted(whitelist.values(), key=lambda item: item["normalized_name"]):
        if priority_only and entry["normalized_name"] not in PRIORITY_WHITELIST_NORMALIZED:
            continue
        source_id = entry.get("openalex_source_id")
        if not source_id:
            continue
        source_short_id = short_openalex_id(source_id)
        filters = (
            f"primary_location.source.id:{source_short_id},"
            "from_publication_date:2020-01-01,"
            "to_publication_date:2026-12-31,"
            "type:article"
        )
        for query in SOURCE_QUERIES:
            try:
                data = openalex_get(
                    {
                        "search": query,
                        "filter": filters,
                        "per-page": per_source,
                        "sort": "cited_by_count:desc",
                        "select": fields,
                    }
                )
            except (urllib.error.URLError, TimeoutError, OSError):
                time.sleep(sleep_seconds)
                continue
            for raw in data.get("results") or []:
                work = parse_openalex_work(raw)
                if not is_topic_relevant(work) or is_excluded_publication(work):
                    continue
                if not is_whitelisted_journal(work.get("journal"), whitelist):
                    continue
                key = (work.get("doi") or work.get("openalex_id") or work.get("title")).lower()
                if not key:
                    continue
                scored = score_work(work, whitelist)
                if key not in rows or scored["score"] > rows[key]["score"]:
                    rows[key] = scored
            time.sleep(sleep_seconds)

    return sorted(rows.values(), key=lambda item: (item["score"], item["cited_by_count"]), reverse=True)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = [
        "rank",
        "score",
        "source_match",
        "whitelist_source",
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
    parser.add_argument("--per-source", type=int, default=30)
    parser.add_argument("--top-n", type=int, default=35)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--download-pdfs", action="store_true")
    parser.add_argument("--strict-whitelist", action="store_true")
    parser.add_argument("--priority-whitelist", action="store_true")
    parser.add_argument("--write-whitelist", action="store_true")
    parser.add_argument("--attachment2", default="附件2【期刊列表】.pdf")
    parser.add_argument("--out-dir", default="results")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    candidate_path = out_dir / "候选外文文献.csv"
    selected_path = out_dir / "外文35篇初筛.csv"
    manual_path = out_dir / "需要手动下载_外文.csv"
    whitelist_path = out_dir / "journal_whitelist.csv"
    pdf_dir = Path("参考文献") / "外文开放获取"

    whitelist = read_whitelist_csv(whitelist_path) or load_whitelist_from_attachment(Path(args.attachment2))
    if args.write_whitelist or args.strict_whitelist:
        enrich_whitelist_with_openalex_sources(whitelist, args.sleep)
        write_whitelist_csv(whitelist_path, whitelist)

    try:
        if args.strict_whitelist:
            candidates = search_openalex_by_whitelist_sources(
                whitelist,
                per_source=args.per_source,
                sleep_seconds=args.sleep,
                priority_only=args.priority_whitelist,
            )
        else:
            candidates = search_openalex(
                args.limit_per_query,
                args.sleep,
                whitelist=whitelist,
                strict_whitelist=False,
            )
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
    if args.write_whitelist or args.strict_whitelist:
        print(f"Wrote {len(whitelist)} whitelist journals to {whitelist_path}")
    if args.download_pdfs:
        downloaded = sum(1 for row in selected if row.get("local_pdf"))
        print(f"Downloaded {downloaded} open-access PDFs to {pdf_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
