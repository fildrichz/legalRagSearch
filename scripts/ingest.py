"""
One-time ingestion script — run after scripts/setup_gcp.py has finished.

What it does:
  1. Downloads the CUAD dataset (commercial contracts) from HuggingFace
  2. Chunks each contract into overlapping text windows
  3. Embeds and streams chunks directly into Vertex AI Vector Search

Prerequisites (run once):
  pip install datasets huggingface-hub

Authentication:
  gcloud auth application-default login

Usage:
  GOOGLE_CLOUD_PROJECT=my-project \
  GCS_BUCKET=my-bucket \
  VECTOR_SEARCH_INDEX_ID=123... \
  VECTOR_SEARCH_ENDPOINT_ID=456... \
  python scripts/ingest.py
"""

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

PROJECT          = os.environ.get("GOOGLE_CLOUD_PROJECT")
LOCATION         = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
GCS_BUCKET       = os.environ.get("GCS_BUCKET")
INDEX_ID         = os.environ.get("VECTOR_SEARCH_INDEX_ID")
ENDPOINT_ID      = os.environ.get("VECTOR_SEARCH_ENDPOINT_ID")

MAX_CONTRACTS    = 40
CHUNK_SIZE       = 1200
CHUNK_OVERLAP    = 150

for var, name in [
    (PROJECT,     "GOOGLE_CLOUD_PROJECT"),
    (GCS_BUCKET,  "GCS_BUCKET"),
    (INDEX_ID,    "VECTOR_SEARCH_INDEX_ID"),
    (ENDPOINT_ID, "VECTOR_SEARCH_ENDPOINT_ID"),
]:
    if not var:
        sys.exit(f"ERROR: Set the {name} environment variable.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def chunk_text(text: str) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = end - CHUNK_OVERLAP
    return chunks


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # ---- 1. Load CUAD -------------------------------------------------------
    print("Loading CUAD dataset from HuggingFace (first run downloads ~50 MB)...")
    try:
        from datasets import load_dataset
    except ImportError:
        sys.exit("Missing: pip install datasets huggingface-hub")

    dataset = load_dataset("theatticusproject/cuad-qa", split="train")

    contracts: dict[str, str] = {}
    for item in dataset:
        title = item.get("title") or item.get("id", "unknown")
        context = item.get("context", "").strip()
        if title not in contracts and context:
            contracts[title] = context
        if len(contracts) >= MAX_CONTRACTS:
            break

    print(f"Loaded {len(contracts)} unique contracts.")

    # ---- 2. Build LangChain Documents ---------------------------------------
    from langchain_core.documents import Document

    docs: list[Document] = []
    for contract_idx, (title, text) in enumerate(contracts.items()):
        for chunk_idx, chunk in enumerate(chunk_text(text)):
            docs.append(
                Document(
                    page_content=chunk,
                    metadata={
                        "title": title,
                        "contract_idx": contract_idx,
                        "chunk_idx": chunk_idx,
                    },
                )
            )

    print(f"Created {len(docs)} chunks across {len(contracts)} contracts.")

    # ---- 3. Connect to Vertex AI Vector Search ------------------------------
    from langchain_google_vertexai import VertexAIEmbeddings
    from langchain_google_vertexai.vectorstores import VectorSearchVectorStore

    print(f"Connecting to Vector Search (project={PROJECT}, location={LOCATION})...")
    embeddings = VertexAIEmbeddings(
        model_name="text-embedding-004",
        project=PROJECT,
        location=LOCATION,
    )
    vectorstore = VectorSearchVectorStore.from_components(
        project_id=PROJECT,
        region=LOCATION,
        gcs_bucket_name=GCS_BUCKET,
        index_id=INDEX_ID,
        endpoint_id=ENDPOINT_ID,
        embedding=embeddings,
        stream_update=True,
    )

    # ---- 4. Stream documents into the index ---------------------------------
    print(f"Streaming {len(docs)} chunks into Vector Search index...")
    BATCH = 100
    for i in range(0, len(docs), BATCH):
        batch = docs[i : i + BATCH]
        vectorstore.add_documents(batch)
        print(f"  {min(i + BATCH, len(docs))}/{len(docs)} chunks ingested")

    print(f"\nDone! {len(docs)} chunks are now live in Vector Search.")
    print("\nNext step:")
    print("  bash scripts/deploy.sh")


if __name__ == "__main__":
    main()
