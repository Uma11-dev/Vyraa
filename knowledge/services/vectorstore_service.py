from pathlib import Path
from typing import Dict, List, Optional

import chromadb
from chromadb.config import Settings
from langchain_core.documents import Document
from langchain_community.vectorstores.utils import filter_complex_metadata


class VectorStoreService:

    CHUNK_COLLECTION = "knowledge_chunks"
    DOCUMENT_COLLECTION = "knowledge_documents"

    def __init__(
        self,
        persist_directory: str | Path | None = None,
    ):

        if persist_directory is None:
            project_root = Path(__file__).resolve().parents[2]
            persist_directory = project_root / "chroma_db"

        self.persist_directory = Path(
            persist_directory
        ).resolve()

        self.persist_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        print(
            f"[CHROMA] Database: "
            f"{self.persist_directory}"
        )

        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(
                anonymized_telemetry=False
            ),
        )

        self.chunk_collection = (
            self.client.get_or_create_collection(
                self.CHUNK_COLLECTION
            )
        )

        self.document_collection = (
            self.client.get_or_create_collection(
                self.DOCUMENT_COLLECTION
            )
        )

    # =========================================================
    # CHUNKS
    # =========================================================

    def store_chunks(
        self,
        semantic_chunks: List[Document],
        chunk_embeddings: List[List[float]],
        document_id: str,
    ) -> None:

        if len(semantic_chunks) != len(chunk_embeddings):
            raise ValueError(
                "Number of chunks must match "
                "number of embeddings."
            )

        semantic_chunks = filter_complex_metadata(
            semantic_chunks
        )

        ids = []
        documents = []
        metadatas = []

        total_chunks = len(semantic_chunks)

        for index, chunk in enumerate(
            semantic_chunks
        ):

            metadata = dict(
                chunk.metadata
            )

            metadata.update({
                "document_id": document_id,
                "chunk_index": index,
                "chunk_count": total_chunks,
                "embedding_type": "chunk",
            })

            chunk_id = (
                f"{document_id}_chunk_{index}"
            )

            ids.append(chunk_id)
            documents.append(
                chunk.page_content
            )
            metadatas.append(metadata)

        if not ids:
            print(
                f"[CHROMA] No chunks to store "
                f"for {document_id}"
            )
            return

        max_batch_size = (
            self.client.get_max_batch_size()
        )

        for start in range(
            0,
            len(ids),
            max_batch_size,
        ):

            end = min(
                start + max_batch_size,
                len(ids),
            )

            self.chunk_collection.upsert(
                ids=ids[start:end],
                embeddings=chunk_embeddings[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
            )

        print(
            f"[CHROMA] Stored {len(ids)} chunks "
            f"for {document_id}"
        )

    # =========================================================
    # DOCUMENT EMBEDDING
    # =========================================================

    def store_document_embedding(
        self,
        embedding: List[float],
        document_id: str,
        title: str,
        metadata: Optional[Dict] = None,
    ) -> None:

        metadata = dict(metadata or {})

        metadata.update({
            "document_id": document_id,
            "title": title,
            "embedding_type": "document",
            "version": 1,
        })

        self.document_collection.upsert(
            ids=[document_id],
            embeddings=[embedding],
            documents=[title],
            metadatas=[metadata],
        )

        print(
            f"[CHROMA] Stored document: {title}"
        )

    # =========================================================
    # DELETE
    # =========================================================

    def delete_document_chunks(
        self,
        document_id: str,
    ) -> None:

        self.chunk_collection.delete(
            where={
                "document_id": document_id
            }
        )

        print(
            f"[CHROMA] Deleted chunks: "
            f"{document_id}"
        )

    def delete_document_embedding(
        self,
        document_id: str,
    ) -> None:

        self.document_collection.delete(
            ids=[document_id]
        )

        print(
            f"[CHROMA] Deleted document: "
            f"{document_id}"
        )

    def delete_document(
        self,
        document_id: str,
    ) -> None:

        self.delete_document_chunks(
            document_id
        )

        self.delete_document_embedding(
            document_id
        )

    # =========================================================
    # COLLECTION ACCESS
    # =========================================================

    def get_chunk_collection(self):
        return self.chunk_collection

    def get_document_collection(self):
        return self.document_collection

    # =========================================================
    # COUNTS
    # =========================================================

    def document_count(self) -> int:
        return self.document_collection.count()

    def chunk_count(self) -> int:
        return self.chunk_collection.count()