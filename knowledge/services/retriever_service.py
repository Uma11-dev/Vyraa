from knowledge.services.vectorstore_service import VectorStoreService
from embeddings.embeddings_model import load_embedding_model


class RetrieverService:
    """
    Retrieves relevant knowledge from VYRA's ChromaDB database.

    Retrieval architecture:
    1. Generate an embedding for the user's query.
    2. Perform semantic search across the knowledge base.
    3. Optionally apply an explicit knowledge-domain filter.
    4. Return relevant chunks with metadata, distances and IDs.

    Domain routing is not performed automatically.
    Semantic relevance takes priority.
    """

    def __init__(self):
        self.vector_store = VectorStoreService()
        self.embedding_model = load_embedding_model()

    # =========================================================
    # QUERY EMBEDDING
    # =========================================================

    def embed_query(self, query: str):
        """
        Generate an embedding using the same model
        used during document ingestion.
        """

        return self.embedding_model.embed_query(query)

    # =========================================================
    # RETRIEVAL
    # =========================================================

    def retrieve_documents(
        self,
        query: str,
        collection_name: str = "knowledge_chunks",
        top_k: int = 8,
        knowledge_domain: str | None = None,
    ):
        """
        Retrieve semantically relevant knowledge chunks.

        Parameters:
            query:
                User's natural language question.

            collection_name:
                ChromaDB collection to search.

            top_k:
                Maximum number of chunks to retrieve.

            knowledge_domain:
                Optional explicit domain restriction.

                If None, searches across all knowledge domains.

        Returns:
            ChromaDB query results containing:
                - documents
                - metadatas
                - distances
                - ids
        """

        query = query.strip()

        # -----------------------------------------------------
        # Validate query
        # -----------------------------------------------------

        if not query:
            return self._empty_results()

        if top_k < 1:
            raise ValueError(
                "top_k must be greater than zero."
            )

        # -----------------------------------------------------
        # Retrieve collection
        # -----------------------------------------------------

        if collection_name == self.vector_store.CHUNK_COLLECTION:
            chunk_collection = (
                self.vector_store.get_chunk_collection()
            )
        else:
            chunk_collection = (
                self.vector_store.client.get_collection(
                    name=collection_name
                )
            )

        total_chunks = chunk_collection.count()

        print()
        print("=" * 70)
        print("VYRA SEMANTIC RETRIEVER")
        print("=" * 70)

        print("Query:", query)
        print("Collection:", collection_name)
        print("Total chunks:", total_chunks)

        # -----------------------------------------------------
        # Handle empty database
        # -----------------------------------------------------

        if total_chunks == 0:
            print("[CHROMA] No chunks available.")
            return self._empty_results()

        # -----------------------------------------------------
        # Generate query embedding
        # -----------------------------------------------------

        query_embedding = self.embed_query(query)

        # -----------------------------------------------------
        # Optional metadata filtering
        # -----------------------------------------------------

        query_parameters = {
            "query_embeddings": [query_embedding],
            "n_results": min(top_k, total_chunks),
            "include": [
                "documents",
                "metadatas",
                "distances",
            ],
        }

        if knowledge_domain is not None:
            query_parameters["where"] = {
                "knowledge_domain": knowledge_domain
            }

            print(
                "Domain filter:",
                knowledge_domain,
            )

        else:
            print(
                "Domain filter: NONE (Global Search)"
            )

        # -----------------------------------------------------
        # Semantic search
        # -----------------------------------------------------

        results = chunk_collection.query(
            **query_parameters
        )

        # -----------------------------------------------------
        # Extract results
        # -----------------------------------------------------

        retrieved_documents = results.get(
            "documents",
            [[]],
        )[0]

        retrieved_metadatas = results.get(
            "metadatas",
            [[]],
        )[0]

        retrieved_distances = results.get(
            "distances",
            [[]],
        )[0]

        retrieved_ids = results.get(
            "ids",
            [[]],
        )[0]

        # -----------------------------------------------------
        # Debug output
        # -----------------------------------------------------

        print()
        print("-" * 70)

        print(
            "Retrieved chunks:",
            len(retrieved_documents),
        )

        for index, document in enumerate(
            retrieved_documents,
            start=1,
        ):

            metadata = retrieved_metadatas[index - 1]

            distance = retrieved_distances[index - 1]

            chunk_id = retrieved_ids[index - 1]

            print()
            print("-" * 70)

            print(f"Rank: {index}")
            print(f"Chunk ID: {chunk_id}")
            print(f"Distance: {distance}")

            print(
                f"File: {metadata.get('filename')}"
            )

            print(
                f"Domain: {metadata.get('knowledge_domain')}"
            )

            print(
                f"Chunk Index: {metadata.get('chunk_index')}"
            )

            print(
                f"Document ID: {metadata.get('document_id')}"
            )

            print()
            print("Content:")
            print(document[:600])

        print()
        print("=" * 70)
        print("RETRIEVAL COMPLETED")
        print("=" * 70)

        return results

    # =========================================================
    # EMPTY RESULTS
    # =========================================================

    @staticmethod
    def _empty_results():
        """
        Return a consistent empty ChromaDB-style response.
        """

        return {
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
            "ids": [[]],
        }