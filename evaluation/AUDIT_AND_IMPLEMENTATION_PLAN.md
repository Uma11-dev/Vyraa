# VYRA RAG Evaluation — Audit and Implementation Plan

## Scope

Improve the existing evaluation harness without changing VYRA's user-facing
application or creating a separate dashboard/application.

## Audit observations

- The evaluation runner already calls the production retrieval function
  (`retriever.retrieve_context`) and can run without Claude generation.
- The retrieval path embeds the query, queries ChromaDB, and combines ranked
  candidates using weighted Reciprocal Rank Fusion (RRF).
- The RRF output preserves `chunk_id`, `document_id`, `retrieval_rank`, and
  `retrieval_score` in LangChain document metadata.
- The lower-level retriever returns ChromaDB IDs, metadata and distances, but
  the current RRF adapter does not preserve the original vector distance in
  the final metadata.
- The runner's existing expected-source metric is filename-based. It is a
  diagnostic and must not be represented as Precision@K or Recall@K.
- The v0.2 golden dataset contains 22 cases; all are marked
  `draft_needs_human_review`. No case currently supplies verified relevant
  chunk/document IDs.
- The existing answer-quality module provides useful heuristic checks, but
  lexical overlap and literal phrase checks are not proof of faithfulness.
- The runner currently measures end-to-end elapsed time only. It does not
  separately expose embedding, vector-search, RRF, context-building and LLM
  generation timings.
- The Claude wrapper currently returns only response text, discarding the
  provider usage metadata needed for token accounting.
- The evaluation README previously described v0.1 as the default although
  the runner defaults to v0.2; documentation has been aligned to v0.2.
- The runner's old warning that arbitrary collection names may be ignored was
  incorrect: `RetrieverService.retrieve_documents` supports collection names.

## Implemented in this milestone

1. Added `evaluation/metrics/retrieval_metrics.py` with deterministic:
   - Precision@K
   - Recall@K
   - reciprocal rank (per-query MRR contribution)
   - nDCG@K for graded labels
   - macro aggregation and metric coverage
2. Integrated per-query metrics and aggregate summaries into the existing
   evaluation runner.
3. Added optional `relevant_chunk_ids`, `relevant_document_ids`, and
   `relevance_grades` support. Existing cases remain valid and unlabelled
   metrics correctly remain null.
4. Added eight unit tests for metric correctness, empty labels, duplicate IDs,
   invalid K, and aggregation coverage.
5. Updated evaluation documentation and removed the incorrect collection-name
   warning.

## Validation performed

- Python compilation passed for the modified runner and retrieval metrics.
- Eight retrieval-metric unit tests passed.
- No live ChromaDB or Claude benchmark was run in this environment. Therefore
  this milestone makes no claim about VYRA's current retrieval quality,
  generation quality, latency, or token efficiency.

## Next implementation phases

### Phase 2 — Relevance labels and retrieval evidence

- Run the existing retrieval-only benchmark against the user's actual local
  ChromaDB collection.
- Export the retrieved chunk IDs, text excerpts, metadata, and ranks.
- Human-review relevance labels for the existing 22 cases before expanding
  the dataset.
- Add chunk-level relevance judgements and optional graded relevance.
- Preserve source filename hit-rate as a separate legacy diagnostic.

### Phase 3 — Stage-level performance instrumentation

- Time query embedding, each ChromaDB query, RRF merge/ranking, context
  formatting, Claude generation, and end-to-end response.
- Report sample count, mean, median/P50, P95, min and max.
- Record warm-up policy, concurrency, environment and collection size.

### Phase 4 — Token and cost accounting

- Preserve Anthropic response usage metadata without breaking the existing
  string-returning generation API (for example, add an opt-in detailed result
  or a separate instrumented wrapper).
- Record input/output and cache token counts when returned by the API.
- Calculate costs from a dated, versioned pricing configuration rather than
  hardcoding an assumed price.
- Never infer exact token counts from character length when provider usage is
  available.

### Phase 5 — Generation evaluation and reliability

- Retain current deterministic diagnostics.
- Add explicit human scoring for faithfulness, relevance, correctness and
  completeness on a representative sample.
- Add automated evaluator scores as supplementary signals, clearly labelling
  judge model/version and evaluation prompt.
- Test abstention, unsupported questions, contradictory sources, long context,
  malformed input, timeouts and provider failures.

### Phase 6 — Controlled optimization and publication

- Change one variable per experiment: chunking, top-K, retrieval strategy,
  embeddings, reranking or prompt.
- Keep the dataset, corpus snapshot and evaluation settings fixed between
  compared runs.
- Record Git commit, dataset version, model IDs, collection name, chunking
  configuration, top-K, timestamps and environment metadata.
- Publish only reproducible measured results and disclose sample size and
  limitations.

## Security and publication gate

Before any public GitHub push, inspect the repository for OAuth client/token
files, `.env` files, API keys, logs, databases, private user data, and source
PDFs or other materials without redistribution permission. Rotate/revoke any
credential that may have been exposed. Do not include secrets or private
corpus files in benchmark artifacts.
