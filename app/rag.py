"""
RAG pipeline using LangChain Expression Language (LCEL).

Flow:
  1. Retrieve top-k docs with scores from ChromaDB
  2. Stream sources event to client
  3. Run LCEL chain (prompt | ChatVertexAI | StrOutputParser) with async streaming
"""

import json
from typing import AsyncGenerator

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_vertexai import ChatVertexAI

from app.vectorstore import LegalVectorStore

GEMINI_MODEL = "gemini-2.0-flash-001"
TOP_K = 5

SYSTEM_PROMPT = (
    "You are a knowledgeable legal assistant. Answer the user's question using ONLY "
    "the contract excerpts provided. If the excerpts lack sufficient information, say so. "
    "Be concise, accurate, and cite the contract title when relevant."
)

_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("human", "Contract excerpts:\n\n{context}\n\nQuestion: {question}"),
    ]
)


class RAGPipeline:
    def __init__(self, vectorstore: LegalVectorStore, project: str, location: str):
        self._vs = vectorstore

        llm = ChatVertexAI(
            model=GEMINI_MODEL,
            project=project,
            location=location,
            temperature=0.1,
            max_tokens=1024,
        )

        # LCEL chain — retrieval is done separately so we can emit sources first
        self._chain = _prompt | llm | StrOutputParser()

    async def stream(self, query: str) -> AsyncGenerator[str, None]:
        """
        Yields SSE events:
          data: {"type": "sources", "sources": [...]}
          data: {"type": "token",   "text": "..."}
          data: {"type": "done"}
        """
        # 1. Retrieve
        results = await self._vs.search_with_scores(query, k=TOP_K)

        sources = [
            {
                "title": doc.metadata.get("title", "Unknown"),
                "excerpt": doc.page_content[:300],
                "score": round(float(score), 3),
            }
            for doc, score in results
        ]
        yield _sse("sources", {"sources": sources})

        # 2. Build context string
        if results:
            context = "\n\n---\n\n".join(
                f"[{doc.metadata.get('title', 'Unknown')}]\n{doc.page_content}"
                for doc, _ in results
            )
        else:
            context = "No relevant excerpts found in the knowledge base."

        # 3. Stream via LCEL chain
        async for chunk in self._chain.astream({"context": context, "question": query}):
            if chunk:
                yield _sse("token", {"text": chunk})

        yield _sse("done", {})


def _sse(event_type: str, data: dict) -> str:
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"
