"""
Vertex AI Gemini RAG showcase — FastAPI app.

Endpoints:
  GET  /        → chat UI (static/index.html)
  GET  /health  → liveness probe
  GET  /stats   → Vector Search backend info
  POST /chat    → streaming RAG response (SSE)
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.rag import RAGPipeline
from app.vectorstore import LegalVectorStore

load_dotenv()

PROJECT     = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION    = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
GCS_BUCKET  = os.environ["GCS_BUCKET"]
INDEX_ID    = os.environ["VECTOR_SEARCH_INDEX_ID"]
ENDPOINT_ID = os.environ["VECTOR_SEARCH_ENDPOINT_ID"]

# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

vectorstore: LegalVectorStore
pipeline: RAGPipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    global vectorstore, pipeline
    print("Connecting to Vertex AI Vector Search...")
    vectorstore = LegalVectorStore(
        project=PROJECT,
        location=LOCATION,
        gcs_bucket=GCS_BUCKET,
        index_id=INDEX_ID,
        endpoint_id=ENDPOINT_ID,
    )
    pipeline = RAGPipeline(vectorstore=vectorstore, project=PROJECT, location=LOCATION)
    print("Ready.")
    yield


app = FastAPI(title="Legal RAG Demo", lifespan=lifespan)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/stats")
async def stats():
    return {
        "backend": "Vertex AI Vector Search",
        "index_id": INDEX_ID,
        "endpoint_id": ENDPOINT_ID,
        "project": PROJECT,
        "location": LOCATION,
    }


@app.get("/", response_class=FileResponse)
async def index():
    path = Path("static/index.html")
    if not path.exists():
        raise HTTPException(status_code=404, detail="UI not found")
    return FileResponse(path)


class ChatRequest(BaseModel):
    query: str


@app.post("/chat")
async def chat(request: ChatRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty")

    return StreamingResponse(
        pipeline.stream(request.query),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), reload=True)
