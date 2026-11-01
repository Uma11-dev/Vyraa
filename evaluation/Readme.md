# VYRA Evaluation Runner

This runner evaluates VYRA's existing retrieval and response-generation
pipeline. It does not create a separate RAG implementation.

## Prerequisites

- Run from the VYRA project root.
- Activate the existing Python virtual environment.
- Ensure the project's existing dependencies are installed.
- Configure the existing environment variables in the project's private .env.
- Know the exact ChromaDB collection name.

## Dataset

The default dataset location is:

evaluation/datasets/vyra_rag_golden_v0.2.jsonl

The CSV file is provided for spreadsheet review. The runner reads JSONL.

## First run: retrieval only

Run a small test without Claude API calls:

python evaluation/run_evaluation.py \
  --collection-name YOUR_ACTUAL_COLLECTION_NAME \
  --retrieval-only \
  --limit 3

Replace YOUR_ACTUAL_COLLECTION_NAME with the actual collection name.

## Second run: retrieval and answer generation

After retrieval-only testing works:

python evaluation/run_evaluation.py \
  --collection-name YOUR_ACTUAL_COLLECTION_NAME \
  --limit 3

This calls the existing Claude response function and may incur API costs.

## Full evaluation

python evaluation/run_evaluation.py \
  --collection-name YOUR_ACTUAL_COLLECTION_NAME

## Reports

Reports are written to evaluation/reports/:

- vyra_eval_TIMESTAMP.json
- vyra_eval_TIMESTAMP.csv
- vyra_eval_TIMESTAMP_summary.json

## Safety

The runner deliberately avoids ask_vyra() and the chat/booking API.
It does not intentionally create bookings, persist chat messages,
extract memories, update profiles, or process notifications.

## Metric limitations

Expected-source hits are filename-based heuristics, not chunk-level
relevance judgements. must_include and must_avoid checks use literal
phrase matching, so they do not prove semantic correctness.

The supplied golden dataset is a draft and should be reviewed by a
human before treating results as a validated benchmark.

## Deterministic retrieval metrics

The runner now calculates Precision@K, Recall@K, MRR, and nDCG@K when a
case includes human-reviewed relevance labels. Supported optional JSONL
fields are:

- `relevant_chunk_ids`: chunk IDs that are relevant to this query.
- `relevant_document_ids`: document IDs that are relevant when chunk-level
  labels are not yet available.
- `relevance_grades`: object mapping retrieved chunk/document IDs to graded
  relevance values (0 = irrelevant; larger positive integers = more relevant).

Do not infer relevance labels from `source_document` or filename matches.
A source filename hit is a useful diagnostic, but it is not a chunk-level
relevance judgement. Until labels are added, ranking metrics are deliberately
reported as null and metric coverage is shown in the summary.

Run the deterministic unit tests from the VYRA project root:

```bash
python -m unittest evaluation.tests.test_retrieval_metrics -v
```

## Relevance annotation workflow

1. Run retrieval-only evaluation and preserve the returned chunk IDs.
2. Inspect the query and candidate chunk text against the source material.
3. Add only genuinely relevant chunk IDs to `relevant_chunk_ids`.
4. Optionally assign graded relevance in `relevance_grades` (0–3), using a
   consistent rubric across the dataset.
5. Set `review_status` to `human_reviewed` only after a reviewer has checked
   the question, expected answer, source and relevance labels.
6. Version the dataset when labels or expected answers change; do not rewrite
   historical run reports.
