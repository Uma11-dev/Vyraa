# VYRA RAG Golden Dataset — v0.2.0

## Purpose
A source-grounded benchmark for evaluating VYRA's retrieval and answer generation. This dataset is a draft benchmark fixture, not an evaluation result. All cases remain marked `draft_needs_human_review` until their questions, expected answers, source locations, and scoring criteria have been checked against the actual source PDFs.

## Files
- `vyra_rag_golden_v0.2.jsonl`: machine-readable cases, answer criteria, and scoring fields.
- `vyra_rag_golden_v0.2.csv`: spreadsheet-friendly version for manual review and annotation.
- `vyra_rag_golden_v0.1.jsonl` and `vyra_rag_golden_v0.1.csv`: preserved historical dataset containing the earlier three-source benchmark. Do not use v0.1 as the current evaluation dataset.

## Current sources
1. `Lunas_Sanctum_VYRA_Knowledge_Base_v1.pdf` — Luna's Sanctum philosophy, practice frameworks, service details, routing logic, and assistant boundaries.
2. `History_and_Origins_of_Tarot.pdf` — historical claims about playing cards, tarot's development, and occult use. Where the source presents contested or speculative claims, answers should retain appropriate attribution and uncertainty.

## Coverage
- 12 Luna's Sanctum / VYRA cases (`LS-001`–`LS-012`)
- 10 Tarot history cases (`TAR-001`–`TAR-010`)
- 22 cases total
- Includes factual questions, multi-point completeness, service routing, source attribution, uncertainty, unsupported questions, and assistant-boundary cases.

## Proposed evaluation dimensions
- **Retrieval relevance:** whether retrieved chunks support the query.
- **Document retrieval:** whether expected source documents or chunks appear near the top. Human relevance judgments should be added before reporting ranking metrics such as NDCG.
- **Groundedness:** whether the response is supported by the retrieved context.
- **Answer relevance:** whether the response addresses the question.
- **Completeness:** whether the response includes the essential expected points.

These are proposed project dimensions. This README does not claim that the rubric exactly matches any hosted evaluator's rubric or that this dataset executes external evaluators.

## Manual scoring
Use a 1–5 scale:
1. Poor / incorrect / unsupported
2. Weak / major omissions
3. Acceptable with material gaps
4. Good with minor gaps
5. Excellent / fully supported and complete

Record the evaluator name and version, model, prompt version, embedding model, chunking settings, retrieval `k`, dataset version, latency, and cost in each evaluation report where available.

## Evaluation protocol
1. Review every expected answer, source location, required phrase, and prohibited claim against the two current PDFs.
2. Confirm the actual source filename and chunk-ID metadata produced by VYRA's ingestion pipeline. `expected_source_ids` are human-readable benchmark identifiers and may not be ChromaDB record IDs.
3. Run retrieval for every query and record the top-k chunk IDs, scores or distances, source metadata, and retrieved text.
4. Generate answers using the configured prompt and model, recording the output.
5. Evaluate the actual retrieved context and generated answer, not the answer in isolation.
6. Manually review failures and sample successful cases. Automated and LLM-based scores are estimates, not proof of correctness.
7. Preserve earlier dataset versions and reports when tuning prompts, chunking, embeddings, or retrieval parameters.
8. Do not describe v0.2 as a validated golden benchmark until human review is complete.

## Repository and source permissions
Before publishing source PDFs or substantial excerpts, verify that distribution is permitted. Keep copyrighted source documents out of public repositories unless you have the necessary rights.

## Next step
Validate the v0.2 files, review the retained cases against the two source PDFs, and run a small retrieval-only smoke test before executing the full evaluation. Do not report benchmark scores until the run has completed.
