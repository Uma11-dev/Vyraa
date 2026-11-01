from pathlib import Path
import unicodedata

from langchain_unstructured import UnstructuredLoader


def load_documents(pdf_path: str | Path):
    pdf_path = Path(pdf_path)

    loader = UnstructuredLoader(str(pdf_path))
    documents = loader.load()

    for document in documents:
        document.page_content = unicodedata.normalize(
            "NFC",
            document.page_content,
        )

    return documents