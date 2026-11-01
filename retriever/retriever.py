import re

from knowledge.services.retriever_service import RetrieverService
from langchain_core.documents import Document

retriever_service = RetrieverService()


def _expand_search_queries(question: str) -> list[str]:
    """Generate alternate queries for explicit Bhagavad-gita references."""
    question = question.strip()
    queries = [question]

    match = re.search(
        r"(?:bhagavad[- ]?gita|gita)\s+(\d{1,2})[.:](\d{1,3})",
        question,
        re.IGNORECASE,
    )

    if match:
        chapter, verse = match.groups()
        queries.extend([
            f"Bhagavad-gita {chapter}.{verse} purport example",
            f"Bhagavad-gita chapter {chapter} verse {verse} "
            "example described in the purport",
            f"Bhagavad-gita chapter {chapter} verse {verse} "
            "prescribed duties and setting an example for others",
        ])

    return list(dict.fromkeys(q for q in queries if q))


def retrieve_context(
    question: str,
    collection_name: str,
    top_k: int = 8,
):
    """Retrieve and combine evidence using Reciprocal Rank Fusion."""
    queries = _expand_search_queries(question)
    verse_reference = len(queries) > 1

    # Store each unique chunk and accumulate rank-based scores.
    candidates = {}

    for query_index, search_query in enumerate(queries):
        results = retriever_service.retrieve_documents(
            query=search_query,
            collection_name=collection_name,
            top_k=max(top_k, 12),
            knowledge_domain="spiritual_reference" if verse_reference else None,
        )

        docs = (results.get("documents") or [[]])[0] or []
        metas = (results.get("metadatas") or [[]])[0] or []
        ids = (results.get("ids") or [[]])[0] or []

        # Prefer the original question, but give verse-aware queries
        # extra influence when an explicit verse reference is present.
        weight = 1.0 if query_index == 0 else 1.5

        for rank, content in enumerate(docs, start=1):
            metadata = metas[rank - 1] if rank - 1 < len(metas) else {}
            metadata = metadata or {}
            chunk_id = ids[rank - 1] if rank - 1 < len(ids) else None

            key = chunk_id or (
                metadata.get("filename"),
                metadata.get("page_number"),
                metadata.get("chunk_index"),
                content[:100],
            )

            if key not in candidates:
                candidates[key] = {
                    "content": content,
                    "metadata": metadata,
                    "chunk_id": chunk_id,
                    "score": 0.0,
                }

            candidates[key]["score"] += weight / (60 + rank)

    ranked = sorted(
        candidates.values(),
        key=lambda item: item["score"],
        reverse=True,
    )[:top_k]

    documents = []

    for rank, item in enumerate(ranked, start=1):
        metadata = {
            **(item["metadata"] or {}),
            "chunk_id": item["chunk_id"],
            "retrieval_rank": rank,
            "retrieval_score": item["score"],
        }

        documents.append(
            Document(
                page_content=item["content"],
                metadata=metadata,
            )
        )

    print(f"\n========== RETRIEVED {len(documents)} DOCUMENTS ==========")

    for document in documents:
        print(
            f"Rank {document.metadata['retrieval_rank']} | "
            f"Chunk {document.metadata.get('chunk_id')} | "
            f"Score {document.metadata['retrieval_score']:.5f}"
        )
        print(document.page_content[:250].replace("\n", " "))
        print("-" * 60)

    return documents
