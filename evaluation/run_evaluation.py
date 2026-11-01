
"""
VYRA RAG evaluation runner.

Run from the VYRA project root with its virtual environment active.

Quick retrieval-only smoke test:
    python evaluation/run_evaluation.py --collection-name knowledge_chunks --retrieval-only --limit 3

Test retrieval + Claude generation:
    python evaluation/run_evaluation.py --collection-name knowledge_chunks --limit 3

Full evaluation:
    python evaluation/run_evaluation.py --collection-name knowledge_chunks

Reports are written to evaluation/reports/.

Safety:
- Does not call ask_vyra() or Django chat/booking endpoints.
- Does not intentionally write chat history, memories, profiles, bookings,
  or notifications.
- Claude generation mode may incur API charges.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------
# Paths and configuration
# ---------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVALUATION_DIR = PROJECT_ROOT / "evaluation"

DEFAULT_DATASET = (
    EVALUATION_DIR / "datasets" / "vyra_rag_golden_v0.2.jsonl"
)
DEFAULT_OUTPUT_DIR = EVALUATION_DIR / "reports"
DEFAULT_COLLECTION = "knowledge_chunks"


# Load answer_quality.py directly from its file path.
# This avoids the "No module named 'evaluation'" import error.
QUALITY_MODULE_PATH = EVALUATION_DIR / "answer_quality.py"

if not QUALITY_MODULE_PATH.is_file():
    raise FileNotFoundError(
        f"Answer-quality module not found: {QUALITY_MODULE_PATH}\n"
        "Make sure evaluation/answer_quality.py exists."
    )

_quality_spec = importlib.util.spec_from_file_location(
    "vyra_answer_quality",
    QUALITY_MODULE_PATH,
)

if _quality_spec is None or _quality_spec.loader is None:
    raise ImportError(
        f"Could not load answer-quality module: {QUALITY_MODULE_PATH}"
    )

_quality_module = importlib.util.module_from_spec(_quality_spec)
_quality_spec.loader.exec_module(_quality_module)

score_answer_quality = _quality_module.score_answer_quality

# Load deterministic retrieval metrics from the evaluation package directory.
_METRICS_PATH = EVALUATION_DIR / "metrics" / "retrieval_metrics.py"
_metrics_spec = importlib.util.spec_from_file_location(
    "vyra_retrieval_metrics", _METRICS_PATH
)
if _metrics_spec is None or _metrics_spec.loader is None:
    raise ImportError(f"Could not load retrieval metrics: {_METRICS_PATH}")
_metrics_module = importlib.util.module_from_spec(_metrics_spec)
_metrics_spec.loader.exec_module(_metrics_module)
evaluate_retrieval_case = _metrics_module.evaluate_retrieval_case
aggregate_metric_rows = _metrics_module.aggregate_metric_rows


# Add aliases only when the two filenames refer to the same document.
SOURCE_ALIASES = {
    "lunas_sanctum_vyra_knowledge_base.pdf": {
        "lunas_sanctum_vyra_knowledge_base_v1.pdf",
    },
    "lunas_sanctum_vyra_knowledge_base_copy.pdf": {
        "lunas_sanctum_vyra_knowledge_base_v1.pdf",
    },
    "history_and_origins_of_tarot(2).pdf": {
        "history_and_origins_of_tarot.pdf",
    },
}


# ---------------------------------------------------------------------
# General utilities
# ---------------------------------------------------------------------

def normalize(value: Any) -> str:
    """Normalize whitespace and case for literal comparisons."""
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def normalized_filename(value: Any) -> str:
    """Return a normalized basename for a path-like metadata value."""
    text = str(value or "").strip().replace("\\", "/")
    return Path(text).name.casefold()


def get_metadata(document: Any) -> dict[str, Any]:
    """Safely obtain metadata from a retrieved document."""
    metadata = getattr(document, "metadata", {}) or {}
    return metadata if isinstance(metadata, dict) else {}


def get_filename(document: Any) -> str:
    """Read the source filename from retrieved-document metadata."""
    metadata = get_metadata(document)

    return normalized_filename(
        metadata.get("filename")
        or metadata.get("source")
        or metadata.get("file_name")
        or ""
    )


def get_retrieved_domains(documents: list[Any]) -> list[str]:
    """Return unique knowledge domains found in retrieved metadata."""
    domains: list[str] = []

    for document in documents:
        domain = str(
            get_metadata(document).get("knowledge_domain") or ""
        ).strip()

        if domain and domain not in domains:
            domains.append(domain)

    return domains


def make_context(documents: list[Any]) -> str:
    """Format retrieved chunks for VYRA's existing Claude response function."""
    parts: list[str] = []

    for index, document in enumerate(documents, start=1):
        metadata = get_metadata(document)
        content = getattr(document, "page_content", "")

        parts.append(
            "==========================\n"
            f"Document {index}\n"
            f"Metadata: {json.dumps(metadata, ensure_ascii=False, default=str)}\n"
            "==========================\n\n"
            f"{content}"
        )

    return "\n\n".join(parts)


# ---------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------

def expected_filenames(case: dict[str, Any]) -> list[str]:
    """Extract expected source filenames from one dataset case."""
    names: list[str] = []

    source_document = case.get("source_document")
    if source_document:
        names.append(normalized_filename(source_document))

    for source_id in case.get("expected_source_ids") or []:
        source_name = str(source_id).split("#", 1)[0]
        name = normalized_filename(source_name)

        if name:
            names.append(name)

    return list(dict.fromkeys(name for name in names if name))


def load_dataset(path: Path) -> list[dict[str, Any]]:
    """Load and validate the JSONL golden evaluation dataset."""
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {path}\n"
            "Expected evaluation/datasets/vyra_rag_golden_v0.2.jsonl "
            "or pass --dataset /path/to/file.jsonl."
        )

    cases: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_number}: {exc}"
                ) from exc

            if not isinstance(item, dict):
                raise ValueError(
                    f"Line {line_number} must contain a JSON object."
                )

            if not item.get("case_id") or not item.get("query"):
                raise ValueError(
                    f"Line {line_number} must contain case_id and query."
                )

            cases.append(item)

    if not cases:
        raise ValueError(f"No evaluation cases found in {path}")

    return cases


# ---------------------------------------------------------------------
# Source and domain diagnostics
# ---------------------------------------------------------------------

def filenames_match(expected_name: str, retrieved_name: str) -> bool:
    """Compare exact filenames and explicitly configured aliases."""
    if not expected_name or not retrieved_name:
        return False

    if expected_name == retrieved_name:
        return True

    if retrieved_name in SOURCE_ALIASES.get(expected_name, set()):
        return True

    if expected_name in SOURCE_ALIASES.get(retrieved_name, set()):
        return True

    # Avoid substring matching because it can create false positives.
    return False


def detect_expected_domain(case: dict[str, Any]) -> str | None:
    """
    Infer a diagnostic domain from the case category and expected source.
    This is a heuristic, not a human-validated label.
    """
    category = normalize(case.get("category", ""))
    source = " ".join(expected_filenames(case))
    combined = f"{category} {source}"

    if any(term in combined for term in (
        "luna", "sanctum", "knowledge_base", "knowledge base", "ls-"
    )):
        return "luna_sanctum"

    if "tarot" in combined or category == "tarot history":
        return "tarot_reference"

    if any(term in combined for term in (
        "bhagavad", "gita", "spiritual", "scripture"
    )):
        return "spiritual_reference"

    return None


# ---------------------------------------------------------------------
# Per-case evaluation
# ---------------------------------------------------------------------

def evaluate_case(
    case: dict[str, Any],
    documents: list[Any],
    answer: str | None,
    retrieval_domain: str | None,
) -> dict[str, Any]:
    """Calculate retrieval, routing, phrase, and answer-quality metrics."""
    expected = expected_filenames(case)
    retrieved = [get_filename(doc) for doc in documents]

    expected_source_hit = any(
        filenames_match(expected_name, retrieved_name)
        for expected_name in expected
        for retrieved_name in retrieved
    )

    expected_domain = detect_expected_domain(case)
    retrieved_domains = get_retrieved_domains(documents)

    if expected_domain is None:
        domain_hit = None
    else:
        domain_hit = (
            retrieval_domain == expected_domain
            or expected_domain in retrieved_domains
        )

    answer_norm = normalize(answer)
    include_terms = case.get("must_include") or []
    avoid_terms = case.get("must_avoid") or []

    include_hits = [
        term for term in include_terms
        if normalize(term) and normalize(term) in answer_norm
    ]

    avoid_hits = [
        term for term in avoid_terms
        if normalize(term) and normalize(term) in answer_norm
    ]

    metadata_rows = []

    for document in documents:
        metadata = get_metadata(document)

        metadata_rows.append({
            "filename": get_filename(document),
            "chunk_id": metadata.get("chunk_id"),
            "document_id": metadata.get("document_id"),
            "knowledge_domain": metadata.get("knowledge_domain"),
            "chunk_index": metadata.get("chunk_index"),
            "distance": metadata.get("distance"),
            "retrieval_rank": metadata.get("retrieval_rank"),
        })

    retrieved_context = make_context(documents)

    # Answer-quality diagnostics are meaningful only when an answer exists.
    quality = score_answer_quality(
        case=case,
        answer=answer or "",
        retrieved_context=retrieved_context,
    )

    retrieved_chunk_ids = [
        str(get_metadata(doc).get("chunk_id") or "") for doc in documents
    ]
    retrieved_document_ids = [
        str(get_metadata(doc).get("document_id") or "") for doc in documents
    ]
    relevant_chunk_ids = case.get("relevant_chunk_ids") or []
    relevant_document_ids = case.get("relevant_document_ids") or []
    relevance_grades = case.get("relevance_grades") or {}

    if relevant_chunk_ids:
        retrieval_metric_ids = retrieved_chunk_ids
        retrieval_relevant_ids = relevant_chunk_ids
        relevance_target = "chunk"
    elif relevant_document_ids:
        retrieval_metric_ids = retrieved_document_ids
        retrieval_relevant_ids = relevant_document_ids
        relevance_target = "document"
    else:
        retrieval_metric_ids = retrieved_chunk_ids
        retrieval_relevant_ids = []
        relevance_target = "unlabelled"

    retrieval_metrics = evaluate_retrieval_case(
        retrieved_ids=retrieval_metric_ids,
        relevant_ids=retrieval_relevant_ids,
        relevance_grades=relevance_grades,
    )

    result = {
        "case_id": case.get("case_id", ""),
        "category": case.get("category", ""),
        "query": case.get("query", ""),
        "expected_behavior": case.get("expected_behavior", ""),
        "expected_domain_heuristic": expected_domain,
        "retrieval_domain": retrieval_domain,
        "retrieved_domains": retrieved_domains,
        "domain_routing_hit_heuristic": domain_hit,
        "expected_source_filenames": expected,
        "retrieved_source_filenames": retrieved,
        "retrieved_metadata": metadata_rows,
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "retrieved_document_ids": retrieved_document_ids,
        "relevance_target": relevance_target,
        "relevance_label_count": retrieval_metrics["relevance_label_count"],
        "retrieval_metrics": retrieval_metrics,
        "retrieval_count": len(documents),
        "expected_source_hit": expected_source_hit,
        "must_include_total": len(include_terms),
        "must_include_literal_hits": len(include_hits),
        "must_include_missing": [
            term for term in include_terms if term not in include_hits
        ],
        "must_avoid_total": len(avoid_terms),
        "must_avoid_literal_hits": len(avoid_hits),
        "must_avoid_found": avoid_hits,
        "ground_truth": case.get("ground_truth", ""),
        "answer": answer or "",
        "latency_seconds": None,
        "error": "",
        "review_status": case.get("review_status", "unspecified"),
    }

    # Keep the answer-quality fields alongside existing metrics.
    result.update(quality)

    return result


# ---------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------

def write_outputs(
    results: list[dict[str, Any]],
    output_dir: Path,
    run_id: str,
    metadata: dict[str, Any],
) -> tuple[Path, Path, Path]:
    """Write detailed JSON, CSV, and summary JSON reports."""
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / f"vyra_eval_{run_id}.json"
    csv_path = output_dir / f"vyra_eval_{run_id}.csv"
    summary_path = output_dir / f"vyra_eval_{run_id}_summary.json"

    total = len(results)
    successful = sum(not row.get("error") for row in results)
    source_hits = sum(bool(row.get("expected_source_hit")) for row in results)

    domain_checked = [
        row for row in results
        if row.get("domain_routing_hit_heuristic") is not None
    ]
    domain_hits = sum(
        bool(row.get("domain_routing_hit_heuristic"))
        for row in domain_checked
    )

    include_total = sum(
        int(row.get("must_include_total") or 0) for row in results
    )
    include_hits = sum(
        int(row.get("must_include_literal_hits") or 0)
        for row in results
    )
    avoid_total = sum(
        int(row.get("must_avoid_total") or 0) for row in results
    )
    avoid_hits = sum(
        int(row.get("must_avoid_literal_hits") or 0)
        for row in results
    )

    quality_scored = [
        row for row in results
        if row.get("answer_present") is not None
    ]
    quality_passed = sum(
        row.get("answer_quality_status") == "checks_passed"
        for row in quality_scored
    )
    quality_needs_review = sum(
        row.get("answer_quality_status") == "needs_review"
        for row in quality_scored
    )

    overlap_values = [
        row["evidence_overlap_ratio"]
        for row in results
        if isinstance(row.get("evidence_overlap_ratio"), (int, float))
    ]
    retrieval_metric_rows = [
        row.get("retrieval_metrics", {})
        for row in results
        if isinstance(row.get("retrieval_metrics"), dict)
    ]
    retrieval_metric_summary = aggregate_metric_rows(retrieval_metric_rows)

    summary = {
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_configuration": metadata,
        "retrieval_metrics": retrieval_metric_summary,
        "retrieval_metric_warning": (
            "Ranking metrics are calculated only for cases with explicit "
            "relevant_chunk_ids or relevant_document_ids labels. Unlabelled "
            "cases are excluded; filename hits are not treated as relevance."
        ),
        "total_cases": total,
        "successful_cases": successful,
        "error_cases": total - successful,
        "expected_source_hits": source_hits,
        "expected_source_hit_rate": source_hits / total if total else 0,
        "domain_routing_cases_scored": len(domain_checked),
        "domain_routing_heuristic_hits": domain_hits,
        "domain_routing_heuristic_hit_rate": (
            domain_hits / len(domain_checked) if domain_checked else None
        ),
        "must_include_literal_hits": include_hits,
        "must_include_literal_checks": include_total,
        "must_include_literal_hit_rate": (
            include_hits / include_total if include_total else None
        ),
        "must_avoid_literal_violations": avoid_hits,
        "must_avoid_literal_checks": avoid_total,
        "must_avoid_literal_violation_rate": (
            avoid_hits / avoid_total if avoid_total else None
        ),
        "answer_quality_cases_scored": len(quality_scored),
        "answer_quality_checks_passed": quality_passed,
        "answer_quality_needs_review": quality_needs_review,
        "average_evidence_overlap_ratio": (
            sum(overlap_values) / len(overlap_values)
            if overlap_values else None
        ),
        "metric_warning": (
            "Source matching uses exact filenames and configured aliases. "
            "Domain expectations are inferred heuristically. Phrase checks "
            "are literal. Evidence overlap is lexical, not proof of "
            "groundedness. Answer-quality checks are diagnostic and do not "
            "replace human review."
        ),
        "results": results,
    }

    json_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    columns = [
        "case_id",
        "category",
        "query",
        "expected_behavior",
        "expected_domain_heuristic",
        "retrieval_domain",
        "retrieved_domains",
        "domain_routing_hit_heuristic",
        "expected_source_filenames",
        "retrieved_source_filenames",
        "retrieved_metadata",
        "retrieved_chunk_ids",
        "retrieved_document_ids",
        "relevance_target",
        "relevance_label_count",
        "retrieval_metrics",
        "retrieval_count",
        "expected_source_hit",
        "must_include_total",
        "must_include_literal_hits",
        "must_include_missing",
        "must_avoid_total",
        "must_avoid_literal_hits",
        "must_avoid_found",
        "ground_truth",
        "answer",
        "answer_present",
        "required_fact_total",
        "required_fact_hits",
        "required_fact_missing",
        "required_fact_coverage",
        "prohibited_phrase_total",
        "prohibited_phrase_found",
        "evidence_overlap_ratio",
        "evidence_overlap_warning",
        "answer_quality_status",
        "latency_seconds",
        "error",
        "review_status",
    ]

    with csv_path.open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="ignore",
        )
        writer.writeheader()

        for row in results:
            writer.writerow({
                key: (
                    json.dumps(value, ensure_ascii=False, default=str)
                    if isinstance(value, (list, dict))
                    else value
                )
                for key, value in row.items()
            })

    return json_path, csv_path, summary_path


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate VYRA retrieval and answer generation."
    )

    parser.add_argument(
        "--collection-name",
        default=DEFAULT_COLLECTION,
        help="Name of the ChromaDB collection to evaluate.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Skip Claude generation and evaluate retrieval only.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional case limit for a quick smoke test.",
    )

    args = parser.parse_args()

    if args.top_k < 1:
        parser.error("--top-k must be at least 1")

    if args.limit < 0:
        parser.error("--limit cannot be negative")

    # Django imports are initialized only after argument validation.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    try:
        import django

        django.setup()

        from retriever.retriever import retrieve_context
        from knowledge.services.retriever_service import RetrieverService

        if not args.retrieval_only:
            from llm.claude import generate_response

    except Exception as exc:
        print(
            f"Could not initialise VYRA imports: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        print(
            "Run this script from the VYRA project root with its "
            "virtual environment active.",
            file=sys.stderr,
        )
        return 2

    try:
        cases = load_dataset(args.dataset)
    except Exception as exc:
        print(f"Dataset error: {exc}", file=sys.stderr)
        return 2

    if args.limit:
        cases = cases[:args.limit]

    router = RetrieverService()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    results: list[dict[str, Any]] = []

    print(
        f"VYRA evaluation | cases={len(cases)} | top_k={args.top_k} "
        f"| Chroma collection={DEFAULT_COLLECTION}"
    )
    print(
        "Mode: retrieval only"
        if args.retrieval_only
        else "Mode: retrieval + Claude generation"
    )
    print(
        "Safety: this runner does not call ask_vyra(), chat/booking "
        "endpoints, memory/profile writes, or notification processing."
    )

    for index, case in enumerate(cases, start=1):
        started = time.perf_counter()
        query = case["query"]

        print(
            f"[{index}/{len(cases)}] "
            f"{case['case_id']} — {query[:100]}"
        )

        documents: list[Any] = []
        answer: str | None = None
        error = ""
        retrieval_domain = None

        try:
            retrieval_domain = router.detect_knowledge_domain(query)

            documents = retrieve_context(
                question=query,
                collection_name=args.collection_name,
                top_k=args.top_k,
            )

            if not args.retrieval_only:
                answer = generate_response(
                    question=query,
                    context=make_context(documents),
                    history="",
                    memory="",
                    service_recommendation=None,
                )

        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            print(f"  ERROR: {error}")

        try:
            row = evaluate_case(
                case=case,
                documents=documents,
                answer=answer,
                retrieval_domain=retrieval_domain,
            )
        except Exception as exc:
            # Keep the evaluation running if a diagnostic itself fails.
            row = {
                "case_id": case.get("case_id", ""),
                "category": case.get("category", ""),
                "query": query,
                "retrieval_count": len(documents),
                "expected_source_hit": False,
                "domain_routing_hit_heuristic": None,
                "answer": answer or "",
                "answer_quality_status": "needs_review",
                "diagnostic_error": f"{type(exc).__name__}: {exc}",
            }
            print(f"  DIAGNOSTIC ERROR: {row['diagnostic_error']}")

        row["latency_seconds"] = round(
            time.perf_counter() - started, 3
        )
        row["error"] = error
        results.append(row)

        print(
            f"  domain={retrieval_domain} "
            f"| retrieved={len(documents)} "
            f"| source_hit={row.get('expected_source_hit', False)} "
            f"| domain_hit={row.get('domain_routing_hit_heuristic')} "
            f"| quality={row.get('answer_quality_status', 'unavailable')} "
            f"| seconds={row['latency_seconds']}"
        )

    run_metadata = {
        "collection": DEFAULT_COLLECTION,
        "collection_argument": args.collection_name,
        "top_k": args.top_k,
        "retrieval_only": args.retrieval_only,
        "dataset_path": str(args.dataset),
        "case_limit": args.limit,
    }

    try:
        paths = write_outputs(
            results=results,
            output_dir=args.output_dir,
            run_id=run_id,
            metadata=run_metadata,
        )
    except Exception as exc:
        print(
            f"Could not write reports: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2

    successful = sum(not row.get("error") for row in results)
    source_hits = sum(
        bool(row.get("expected_source_hit")) for row in results
    )

    scored_domains = [
        row for row in results
        if row.get("domain_routing_hit_heuristic") is not None
    ]
    domain_hits = sum(
        bool(row.get("domain_routing_hit_heuristic"))
        for row in scored_domains
    )

    quality_scored = [
        row for row in results
        if row.get("answer_present") is not None
    ]
    quality_passed = sum(
        row.get("answer_quality_status") == "checks_passed"
        for row in quality_scored
    )
    quality_review = sum(
        row.get("answer_quality_status") == "needs_review"
        for row in quality_scored
    )

    print("\nEvaluation finished.")
    print(f"Cases completed without errors: {successful}/{len(results)}")
    print(f"Expected-source hits: {source_hits}/{len(results)}")

    if scored_domains:
        print(
            "Domain-routing heuristic hits: "
            f"{domain_hits}/{len(scored_domains)}"
        )

    if quality_scored:
        print(
            f"Answer-quality checks passed: "
            f"{quality_passed}/{len(quality_scored)}"
        )
        print(f"Answers needing review: {quality_review}")

    print("Reports:")
    for path in paths:
        print(f"  {path}")

    print(
        "\nReminder: source/domain metrics are diagnostic, phrase checks "
        "are literal, and lexical overlap does not prove groundedness. "
        "Review individual cases before drawing conclusions."
    )

    return 0 if successful == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
