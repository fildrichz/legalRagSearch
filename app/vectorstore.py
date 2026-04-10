"""
Vector store backed by Vertex AI Vector Search, orchestrated via LangChain.
Embeddings use Vertex AI text-embedding-004 through VertexAIEmbeddings.

The index and endpoint must already exist — run scripts/setup_gcp.py first.
"""

import asyncio

from langchain_google_vertexai import VertexAIEmbeddings
from langchain_google_vertexai.vectorstores import VectorSearchVectorStore


class LegalVectorStore:
    def __init__(
        self,
        project: str,
        location: str,
        gcs_bucket: str,
        index_id: str,
        endpoint_id: str,
    ):
        embeddings = VertexAIEmbeddings(
            model_name="text-embedding-004",
            project=project,
            location=location,
        )
        self._store = VectorSearchVectorStore.from_components(
            project_id=project,
            region=location,
            gcs_bucket_name=gcs_bucket,
            index_id=index_id,
            endpoint_id=endpoint_id,
            embedding=embeddings,
            stream_update=True,
        )

    async def search_with_scores(self, query: str, k: int = 5) -> list[tuple]:
        """Return list of (Document, score) sorted by relevance."""
        # Run sync SDK call in a thread to avoid blocking the event loop
        return await asyncio.to_thread(
            self._store.similarity_search_with_score, query, k
        )
