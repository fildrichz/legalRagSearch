# Legal RAG — Vertex AI Gemini Showcase

A retrieval-augmented generation (RAG) app built on Google Cloud, using:

- **Vertex AI Gemini 2.0 Flash** — answer generation
- **Vertex AI text-embedding-004** — document and query embeddings
- **Vertex AI Vector Search** — managed vector index (persistent, scalable)
- **LangChain** — RAG orchestration via LCEL
- **FastAPI** — REST API + streaming chat UI
- **Cloud Run** — serverless deployment

The knowledge base is the [CUAD dataset](https://huggingface.co/datasets/cuad) — 500+ real commercial contracts, making it a realistic legal Q&A showcase.

---

## Architecture

```
User → Cloud Run (FastAPI)
           │
           ├─ Query → Vertex AI text-embedding-004 → embedding
           │                                            │
           │          Vertex AI Vector Search ←─────────┘
           │                    │ top-k contract chunks
           │                    ↓
           └─ Prompt + context → Vertex AI Gemini 2.0 Flash → streamed answer
```

---

## Prerequisites

- [gcloud CLI](https://cloud.google.com/sdk/docs/install) installed and authenticated
- Python 3.10+
- Docker
- A GCP account with billing enabled

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
pip install datasets huggingface-hub   # only needed for ingestion
```

### 2. Authenticate

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

### 3. Provision GCP infrastructure (~1 hour)

Creates the GCS bucket, Vector Search index, index endpoint, and IAM bindings.

```bash
GOOGLE_CLOUD_PROJECT=your-project python scripts/setup_gcp.py
```

Copy the printed `INDEX_ID` and `ENDPOINT_ID` into your `.env`:

```bash
cp .env.example .env
# fill in GOOGLE_CLOUD_PROJECT, GCS_BUCKET, VECTOR_SEARCH_INDEX_ID, VECTOR_SEARCH_ENDPOINT_ID
```

### 4. Ingest CUAD contracts

Downloads 40 commercial contracts, chunks, embeds, and streams them into Vector Search.

```bash
source .env   # or: set -a; source .env; set +a  (bash)
python scripts/ingest.py
```

### 5. Run locally

```bash
python main.py
# open http://localhost:8080
```

### 6. Deploy to Cloud Run

```bash
bash scripts/deploy.sh
```

---

## Project structure

```
├── main.py                  # FastAPI app entry point
├── app/
│   ├── vectorstore.py       # Vertex AI Vector Search wrapper (LangChain)
│   └── rag.py               # LCEL chain: retrieve → prompt → Gemini stream
├── scripts/
│   ├── setup_gcp.py         # One-time GCP resource provisioning
│   ├── ingest.py            # Download CUAD + embed + index into Vector Search
│   └── deploy.sh            # Build Docker image + deploy to Cloud Run
├── static/
│   └── index.html           # Streaming chat UI
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Cost notes (free trial)

| Resource | Approx. cost |
|---|---|
| Vector Search endpoint (1 replica, e2-standard-2) | ~$55/month |
| Gemini 2.0 Flash | ~$0.10 per 1M tokens |
| text-embedding-004 | ~$0.00002 per 1K chars |
| Cloud Run | Free tier covers typical demo usage |

**Undeploy the Vector Search endpoint when not in use** to stop the largest cost:

```bash
gcloud ai index-endpoints undeploy-index ENDPOINT_ID \
  --deployed-index-id=legal_rag_deployed \
  --region=us-central1
```
