
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_experimental.text_splitter import SemanticChunker

from data_ingestion.loaders import load_documents
from embeddings.embeddings_model import (
    create_embeddings,
    load_embedding_model,
)
from knowledge.services.vectorstore_service import VectorStoreService


logger = logging.getLogger(__name__)


# =========================================================
# Knowledge base configuration
# =========================================================

KNOWLEDGE_DOMAINS = {
    "luna_sanctum": {
        "aliases": [
            "luna_sanctum",
            "lunas_sanctum",
        ],
        "description": "Luna's Sanctum knowledge and content",
    },
    "tarot_reference": {
        "aliases": [
            "tarot",
            "tarot_reference",
        ],
        "description": "Tarot learning and reference material",
    },
    "spiritual_reference": {
        "aliases": [
            "gita",
            "bhagavad",
            "spiritual",
        ],
        "description": "Spiritual philosophy and reference material",
    },
    "general_reference": {
        "aliases": [],
        "description": "General knowledge documents",
    },
}


SEMANTIC_BREAKPOINT_THRESHOLD_TYPE = "percentile"
SEMANTIC_BREAKPOINT_THRESHOLD_AMOUNT = 95
HASH_BLOCK_SIZE = 1024 * 1024


# =========================================================
# Knowledge Base Manager
# =========================================================

class KnowledgeBaseManager:
    """
    Manages PDF ingestion into VYRA's Chroma knowledge base.

    Responsibilities:
        - Detect new and modified PDFs
        - Prevent duplicate ingestion
        - Extract PDF content
        - Create retrieval chunks
        - Generate embeddings
        - Store chunks and document embeddings
        - Maintain ingestion registry
        - Remove deleted documents
        - Attach knowledge metadata
    """

    def __init__(
        self,
        knowledge_base_dir: str | Path = "knowledge_base",
        registry_path: str | Path = (
            "knowledge_base/.ingestion_registry.json"
        ),
        semantic_breakpoint_threshold_type: str = (
            SEMANTIC_BREAKPOINT_THRESHOLD_TYPE
        ),
        semantic_breakpoint_threshold_amount: float = (
            SEMANTIC_BREAKPOINT_THRESHOLD_AMOUNT
        ),
    ) -> None:

        if semantic_breakpoint_threshold_type not in {
            "percentile",
            "standard_deviation",
            "interquartile",
            "gradient",
        }:
            raise ValueError(
                "Unsupported semantic breakpoint threshold type: "
                f"{semantic_breakpoint_threshold_type}"
            )

        if not 0 <= semantic_breakpoint_threshold_amount <= 100:
            raise ValueError(
                "semantic_breakpoint_threshold_amount must be between 0 and 100"
            )

        self.semantic_breakpoint_threshold_type = (
            semantic_breakpoint_threshold_type
        )
        self.semantic_breakpoint_threshold_amount = (
            semantic_breakpoint_threshold_amount
        )

        self.knowledge_base_dir = Path(
            knowledge_base_dir
        ).resolve()

        self.registry_path = Path(
            registry_path
        ).resolve()

        self.knowledge_base_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._registry = self._load_registry()

        self.vector_store = VectorStoreService()

    # =====================================================
    # Registry
    # =====================================================

    @staticmethod
    def _empty_registry() -> dict[str, Any]:
        return {
            "documents": {},
            "hashes": {},
        }

    def _load_registry(self) -> dict[str, Any]:
        """
        Load and validate the ingestion registry.

        Supports the previous registry format where
        document records were stored at the root level.
        """

        if not self.registry_path.exists():
            return self._empty_registry()

        try:
            registry = json.loads(
                self.registry_path.read_text(
                    encoding="utf-8"
                )
            )

            if not isinstance(registry, dict):
                raise ValueError(
                    "Registry root must be a dictionary"
                )

            # Backwards compatibility with the old format.
            if "documents" not in registry:
                registry = {
                    "documents": registry,
                    "hashes": {},
                }

            documents = registry.get("documents", {})
            hashes = registry.get("hashes", {})

            if not isinstance(documents, dict):
                raise ValueError(
                    "Registry documents must be a dictionary"
                )

            if not isinstance(hashes, dict):
                raise ValueError(
                    "Registry hashes must be a dictionary"
                )

            return {
                "documents": documents,
                "hashes": hashes,
            }

        except (
            json.JSONDecodeError,
            OSError,
            ValueError,
        ) as exc:

            logger.exception(
                "Could not load ingestion registry: %s",
                exc,
            )

            # Preserve the existing file for investigation.
            # Do not overwrite it automatically.
            raise RuntimeError(
                "Ingestion registry is invalid. "
                "Inspect or restore the registry before "
                "continuing."
            ) from exc

    def _save_registry(self) -> None:
        """
        Persist registry using a temporary file and
        atomic replacement.
        """

        self.registry_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.registry_path.parent,
                suffix=".tmp",
                delete=False,
            ) as temporary_file:

                temporary_path = Path(
                    temporary_file.name
                )

                json.dump(
                    self._registry,
                    temporary_file,
                    indent=2,
                    ensure_ascii=False,
                )

                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            temporary_path.replace(
                self.registry_path
            )

        finally:
            if (
                temporary_path is not None
                and temporary_path.exists()
            ):
                temporary_path.unlink()

    # =====================================================
    # File identity
    # =====================================================

    @staticmethod
    def _file_hash(path: Path) -> str:
        """
        Calculate the SHA-256 hash of a file.
        """

        digest = hashlib.sha256()

        with path.open("rb") as file:

            for block in iter(
                lambda: file.read(HASH_BLOCK_SIZE),
                b"",
            ):
                digest.update(block)

        return digest.hexdigest()

    @staticmethod
    def _document_id(path: Path) -> str:
        """
        Generate a stable document ID from its absolute path.
        """

        normalized_path = str(
            path.resolve()
        )

        return hashlib.sha256(
            normalized_path.encode("utf-8")
        ).hexdigest()[:32]

    # =====================================================
    # Knowledge classification
    # =====================================================

    @staticmethod
    def _knowledge_domain(path: Path) -> str:
        """
        Classify a document using the domain configuration.

        Unknown documents are assigned to general_reference.
        """

        filename = path.stem.lower()

        for domain, configuration in KNOWLEDGE_DOMAINS.items():

            if domain == "general_reference":
                continue

            for alias in configuration["aliases"]:

                if alias.lower() in filename:
                    return domain

        return "general_reference"

    @classmethod
    def _knowledge_metadata(
        cls,
        path: Path,
        document_id: str,
    ) -> dict[str, str]:
        """
        Generate standardised document metadata.
        """

        return {
            "document_id": document_id,
            "knowledge_source": "knowledge_base",
            "knowledge_domain": cls._knowledge_domain(path),
            "filename": path.name,
            "source": str(path.resolve()),
            "filetype": "application/pdf",
        }

    # =====================================================
    # Duplicate detection
    # =====================================================

    def _find_duplicate_by_hash(
        self,
        file_hash: str,
        current_path: Path,
    ) -> dict[str, Any] | None:
        """
        Find another registered document with identical content.
        """

        duplicate = self._registry["hashes"].get(
            file_hash
        )

        if not duplicate:
            return None

        duplicate_path = duplicate.get("path")

        if duplicate_path:

            try:
                existing_path = Path(
                    duplicate_path
                ).resolve()

                if existing_path == current_path.resolve():
                    return None

            except (OSError, TypeError, ValueError):
                logger.warning(
                    "Could not resolve duplicate path: %s",
                    duplicate_path,
                )

        return duplicate

    # =====================================================
    # Retrieval chunking
    # =====================================================

    def _create_retrieval_chunks(
        self,
        documents: list[Document],
        path: Path,
        document_id: str,
    ) -> list[Document]:
        """
        Group extracted content by page and create
        semantically coherent retrieval chunks.
        """

        pages: dict[int, list[str]] = {}

        # Group extracted elements by page.
        for document in documents:

            text = "\n".join(
                line.strip()
                for line in document.page_content.splitlines()
                if line.strip()
            ).strip()

            if not text:
                continue

            page_number = int(
                document.metadata.get(
                    "page_number",
                    0,
                ) or 0
            )

            pages.setdefault(
                page_number,
                [],
            ).append(text)

        base_metadata = self._knowledge_metadata(
            path,
            document_id,
        )

        page_documents: list[Document] = []

        # Create one document per page.
        for page_number, parts in sorted(pages.items()):

            page_text = "\n\n".join(parts)

            metadata = {
                **base_metadata,
                "page_number": page_number,
            }

            page_documents.append(
                Document(
                    page_content=page_text,
                    metadata=metadata,
                )
            )

        if not page_documents:
            return []

        # SemanticChunker uses embeddings to identify semantic
        # breakpoints between neighboring sentence groups.
        embedding_model = load_embedding_model()

        splitter = SemanticChunker(
            embeddings=embedding_model,
            breakpoint_threshold_type=(
                self.semantic_breakpoint_threshold_type
            ),
            breakpoint_threshold_amount=(
                self.semantic_breakpoint_threshold_amount
            ),
        )

        logger.info(
            "CHUNKING METHOD IN USE: %s | Threshold: %s (%s)",
            splitter.__class__.__name__,
            self.semantic_breakpoint_threshold_amount,
            self.semantic_breakpoint_threshold_type,
        )

        chunks = splitter.split_documents(page_documents)

        logger.info(
            "CHUNKING COMPLETED | Method: %s | Chunks: %s",
            splitter.__class__.__name__,
            len(chunks),
        )

        if chunks:
            logger.info(
                "FIRST CHUNK PREVIEW: %s",
                chunks[0].page_content[:200],
            )

        total_chunks = len(chunks)

        # Attach chunk-level metadata.
        for index, chunk in enumerate(chunks):

            chunk.metadata.update({
                "chunk_index": index,
                "chunk_count": total_chunks,
            })

        return chunks

    # =====================================================
    # PDF ingestion
    # =====================================================

    def ingest_pdf(
        self,
        path: str | Path,
        force: bool = False,
    ) -> bool:
        """
        Ingest a single PDF.

        Returns:
            True: document was ingested.
            False: document was skipped.
        """

        path = Path(path).resolve()

        if path.suffix.lower() != ".pdf":
            logger.warning(
                "Unsupported file type: %s",
                path,
            )
            return False

        if not path.is_file():
            logger.warning(
                "PDF does not exist: %s",
                path,
            )
            return False

        file_key = str(path)

        current_hash = self._file_hash(path)

        documents_registry = self._registry["documents"]
        hashes_registry = self._registry["hashes"]

        previous = documents_registry.get(file_key)

        # -------------------------------------------------
        # Case 1: unchanged document
        # -------------------------------------------------

        if (
            not force
            and previous
            and previous.get("file_hash") == current_hash
        ):

            logger.info(
                "Skipping unchanged PDF: %s",
                path.name,
            )

            return False

        # -------------------------------------------------
        # Case 2: duplicate document
        # -------------------------------------------------

        if not force:

            duplicate = self._find_duplicate_by_hash(
                current_hash,
                path,
            )

            if duplicate:

                logger.info(
                    "Duplicate PDF detected: %s. "
                    "Existing path: %s",
                    path.name,
                    duplicate.get("path", "unknown"),
                )

                return False

        # -------------------------------------------------
        # Document identity and metadata
        # -------------------------------------------------

        document_id = (
            previous.get("document_id")
            if previous
            else self._document_id(path)
        )

        metadata = self._knowledge_metadata(
            path,
            document_id,
        )

        knowledge_domain = metadata["knowledge_domain"]

        logger.info(
            "Starting ingestion: %s | Domain: %s",
            path.name,
            knowledge_domain,
        )

        try:

            # -------------------------------------------------
            # Extract PDF
            # -------------------------------------------------

            logger.info(
                "Extracting PDF: %s",
                path.name,
            )

            raw_documents = load_documents(path)

            logger.info(
                "PDF EXTRACTION COMPLETED | Extracted documents: %s",
                len(raw_documents),
            )

            if not raw_documents:
                raise ValueError(
                    "PDF extraction returned no documents"
                )

            # -------------------------------------------------
            # Create retrieval chunks
            # -------------------------------------------------

            chunks = self._create_retrieval_chunks(
                raw_documents,
                path,
                document_id,
            )

            if not chunks:
                raise ValueError(
                    "No usable retrieval chunks were produced"
                )

            logger.info(
                "Created %s retrieval chunks",
                len(chunks),
            )

            # -------------------------------------------------
            # Generate embeddings
            # -------------------------------------------------

            (
                chunk_embeddings,
                document_embedding,
            ) = create_embeddings(chunks)

            if len(chunk_embeddings) != len(chunks):
                raise ValueError(
                    "Embedding count does not match chunk count"
                )

            # -------------------------------------------------
            # Replace previous document
            # -------------------------------------------------

            # IMPORTANT:
            # The existing vector-store interface does not
            # expose a documented atomic replacement operation.
            # We retain the existing deletion behaviour here.
            # A staging/versioned replacement is a future
            # reliability improvement.

            if previous:

                logger.info(
                    "Removing previous document version: %s",
                    path.name,
                )

                self.vector_store.delete_document(
                    document_id
                )

            # -------------------------------------------------
            # Store chunk embeddings
            # -------------------------------------------------

            self.vector_store.store_chunks(
                semantic_chunks=chunks,
                chunk_embeddings=chunk_embeddings,
                document_id=document_id,
            )

            # -------------------------------------------------
            # Store document-level embedding
            # -------------------------------------------------

            document_metadata = {
                **metadata,
                "file_hash": current_hash,
            }

            self.vector_store.store_document_embedding(
                embedding=document_embedding,
                document_id=document_id,
                title=path.name,
                metadata=document_metadata,
            )

            # -------------------------------------------------
            # Update registry
            # -------------------------------------------------

            record = {
                "document_id": document_id,
                "file_hash": current_hash,
                "filename": path.name,
                "path": file_key,
                "knowledge_source": metadata["knowledge_source"],
                "knowledge_domain": knowledge_domain,
                "chunk_count": len(chunks),
                "status": "ingested",
                "processed_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            }

            documents_registry[file_key] = record

            # Remove previous hash entry after successful storage.
            if previous:

                old_hash = previous.get("file_hash")

                if old_hash and old_hash != current_hash:
                    hashes_registry.pop(
                        old_hash,
                        None,
                    )

            hashes_registry[current_hash] = {
                "document_id": document_id,
                "filename": path.name,
                "path": file_key,
                "knowledge_domain": knowledge_domain,
            }

            self._save_registry()

            logger.info(
                "Ingestion complete: %s | Chunks: %s",
                path.name,
                len(chunks),
            )

            return True

        except Exception:

            logger.exception(
                "Ingestion failed for PDF: %s",
                path.name,
            )

            raise

    # =====================================================
    # Initial scan
    # =====================================================

    def scan(self) -> None:
        """
        Scan the knowledge base directory for PDFs.
        """

        pdfs = sorted(
            self.knowledge_base_dir.glob("*.pdf")
        )

        if not pdfs:

            logger.info(
                "No PDFs found in %s",
                self.knowledge_base_dir,
            )

            return

        logger.info(
            "Scanning %s PDF(s)",
            len(pdfs),
        )

        for pdf in pdfs:

            try:
                self.ingest_pdf(pdf)

            except Exception:
                logger.exception(
                    "Failed to ingest PDF: %s",
                    pdf.name,
                )

    # =====================================================
    # File stability
    # =====================================================

    def wait_until_stable(
        self,
        path: str | Path,
        checks: int = 2,
        interval_seconds: float = 1.5,
    ) -> None:
        """
        Wait until file size and modification time remain
        unchanged for the requested number of checks.
        """

        if checks < 1:
            raise ValueError(
                "checks must be at least 1"
            )

        if interval_seconds < 0:
            raise ValueError(
                "interval_seconds cannot be negative"
            )

        path = Path(path)

        last_signature = None
        stable_count = 0

        while stable_count < checks:

            if not path.exists():
                return

            stat = path.stat()

            signature = (
                stat.st_size,
                stat.st_mtime_ns,
            )

            if signature == last_signature:
                stable_count += 1

            else:
                stable_count = 0
                last_signature = signature

            if stable_count < checks:
                time.sleep(interval_seconds)

    # =====================================================
    # Deletion
    # =====================================================

    def delete_pdf(
        self,
        path: str | Path,
    ) -> bool:
        """
        Remove a deleted PDF from Chroma and the registry.
        """

        path = Path(path).resolve()

        file_key = str(path)

        previous = self._registry["documents"].get(
            file_key
        )

        if not previous:

            logger.warning(
                "Deleted PDF was not registered: %s",
                path.name,
            )

            return False

        document_id = previous.get("document_id")
        file_hash = previous.get("file_hash")

        # Remove document vectors first.
        if document_id:

            self.vector_store.delete_document(
                document_id
            )

        # Remove document registry entry.
        self._registry["documents"].pop(
            file_key,
            None,
        )

        # Remove hash registry entry.
        if file_hash:

            self._registry["hashes"].pop(
                file_hash,
                None,
            )

        self._save_registry()

        logger.info(
            "Deleted PDF from knowledge base: %s",
            path.name,
        )

        return True
