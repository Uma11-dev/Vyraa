from pathlib import Path

from data_ingestion.loaders import load_documents


PDF_PATH = Path(
    "knowledge_base/Lunas_Sanctum_VYRA_Knowledge_Base_v1.pdf"
)


print("\n========== LUNA PDF LOADER TEST ==========")

print("PDF exists:", PDF_PATH.exists())
print("PDF path:", PDF_PATH.resolve())

if not PDF_PATH.exists():
    raise FileNotFoundError(
        f"PDF not found: {PDF_PATH.resolve()}"
    )


documents = load_documents(PDF_PATH)


print("\nDocuments extracted:", len(documents))


for i, document in enumerate(documents[:5], start=1):

    print(f"\n========== DOCUMENT {i} ==========")

    print("CONTENT:")
    print(document.page_content[:1000])

    print("\nMETADATA:")
    print(document.metadata)


print("\n========== TEST COMPLETE ==========")