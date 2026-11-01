from langchain_huggingface import HuggingFaceEmbeddings

from embeddings.document_embedding import DocumentEmbeddingService


def load_embedding_model():
    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )


def create_embeddings(semantic_chunks):

    if not semantic_chunks:
        raise ValueError(
            "Cannot create embeddings from empty chunks."
        )

    embedding_model = load_embedding_model()

    texts = [
        chunk.page_content
        for chunk in semantic_chunks
    ]

    chunk_embeddings = embedding_model.embed_documents(
        texts
    )

    document_embedding = DocumentEmbeddingService.generate(
        chunk_embeddings,
        strategy="mean",
    )

    return (
        chunk_embeddings,
        document_embedding,
    )