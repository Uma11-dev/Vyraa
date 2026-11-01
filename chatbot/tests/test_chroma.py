import chromadb

client = chromadb.PersistentClient(
    path="chroma_db"
)

collection = client.get_collection(
    name="knowledge_chunks"
)

print("\n========== CHROMA TEST ==========")
print("Collection:", collection.name)
print("Total chunks:", collection.count())

print("\n========== LUNA'S SANCTUM SEARCH ==========")

results = collection.get(
    where={
        "filename": "Lunas_Sanctum_VYRA_Knowledge_Base_v1.pdf"
    },
    limit=5,
    include=["documents", "metadatas"]
)

documents = results.get("documents", [])
metadatas = results.get("metadatas", [])

print("Luna chunks found:", len(documents))

for i, document in enumerate(documents, start=1):
    print(f"\n--- Luna Chunk {i} ---")
    print(document[:1000])

    print("\nMetadata:")
    print(metadatas[i - 1])