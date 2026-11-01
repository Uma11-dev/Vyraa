from typing import List

import numpy as np


class DocumentEmbeddingService:

    @staticmethod
    def generate(
        chunk_embeddings: List[List[float]],
        strategy: str = "mean",
    ) -> List[float]:

        if not chunk_embeddings:
            raise ValueError(
                "Cannot generate document embedding from empty chunks."
            )

        if strategy == "mean":
            return DocumentEmbeddingService.mean_pool(
                chunk_embeddings
            )

        raise ValueError(
            f"Unknown embedding strategy: {strategy}"
        )

    @staticmethod
    def mean_pool(
        chunk_embeddings: List[List[float]],
    ) -> List[float]:

        if not chunk_embeddings:
            raise ValueError(
                "Cannot generate document embedding from empty chunks."
            )

        embeddings_array = np.array(
            chunk_embeddings,
            dtype=np.float32,
        )

        document_embedding = np.mean(
            embeddings_array,
            axis=0,
        )

        return document_embedding.tolist()