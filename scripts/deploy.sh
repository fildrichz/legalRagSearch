#!/usr/bin/env bash
# Deploy the Legal RAG app to Cloud Run.
# Run from the project root: bash scripts/deploy.sh
#
# Requires these env vars (copy from .env or export them):
#   GOOGLE_CLOUD_PROJECT
#   GOOGLE_CLOUD_LOCATION   (default: us-central1)
#   GCS_BUCKET
#   VECTOR_SEARCH_INDEX_ID
#   VECTOR_SEARCH_ENDPOINT_ID

set -euo pipefail

# Load .env from project root if present
ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
  set -a && source "$ENV_FILE" && set +a
fi

PROJECT="${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
GCS_BUCKET="${GCS_BUCKET:?Set GCS_BUCKET}"
INDEX_ID="${VECTOR_SEARCH_INDEX_ID:?Set VECTOR_SEARCH_INDEX_ID}"
ENDPOINT_ID="${VECTOR_SEARCH_ENDPOINT_ID:?Set VECTOR_SEARCH_ENDPOINT_ID}"

SERVICE="legal-rag"
REPO="legal-rag-repo"
IMAGE="${LOCATION}-docker.pkg.dev/${PROJECT}/${REPO}/${SERVICE}:latest"
DEPLOYED_INDEX_ID="legal_rag_deployed"

# ── 1. Ensure Vector Search index is deployed ────────────────────────────────
echo "==> Checking Vector Search index deployment..."
ALREADY_DEPLOYED=$(gcloud ai index-endpoints describe "${ENDPOINT_ID}" \
  --region="${LOCATION}" \
  --project="${PROJECT}" \
  --format="value(deployedIndexes.id)" 2>/dev/null || true)

if echo "${ALREADY_DEPLOYED}" | grep -q "${DEPLOYED_INDEX_ID}"; then
  echo "    Index already deployed, skipping."
else
  echo "    Deploying index to endpoint (this takes ~20 minutes)..."
  gcloud ai index-endpoints deploy-index "${ENDPOINT_ID}" \
    --deployed-index-id="${DEPLOYED_INDEX_ID}" \
    --display-name="Legal RAG Index" \
    --index="${INDEX_ID}" \
    --machine-type=e2-standard-2 \
    --region="${LOCATION}" \
    --project="${PROJECT}"
  echo "    Index deployed."
fi

# ── 2. Build and push image ──────────────────────────────────────────────────
echo "==> Creating Artifact Registry repository (if needed)..."
gcloud artifacts repositories create "${REPO}" \
  --repository-format=docker \
  --location="${LOCATION}" \
  --project="${PROJECT}" 2>/dev/null || true

echo "==> Configuring Docker auth..."
gcloud auth configure-docker "${LOCATION}-docker.pkg.dev" --quiet

echo "==> Building and pushing image via Cloud Build..."
gcloud builds submit \
  --tag="${IMAGE}" \
  --project="${PROJECT}" \
  .

# ── 3. Deploy to Cloud Run ───────────────────────────────────────────────────
echo "==> Deploying to Cloud Run..."
gcloud run deploy "${SERVICE}" \
  --image="${IMAGE}" \
  --region="${LOCATION}" \
  --platform=managed \
  --allow-unauthenticated \
  --min-instances=1 \
  --memory=512Mi \
  --set-env-vars="\
GOOGLE_CLOUD_PROJECT=${PROJECT},\
GOOGLE_CLOUD_LOCATION=${LOCATION},\
GCS_BUCKET=${GCS_BUCKET},\
VECTOR_SEARCH_INDEX_ID=${INDEX_ID},\
VECTOR_SEARCH_ENDPOINT_ID=${ENDPOINT_ID}" \
  --project="${PROJECT}"

echo ""
echo "==> Deployed! Service URL:"
gcloud run services describe "${SERVICE}" \
  --region="${LOCATION}" \
  --project="${PROJECT}" \
  --format="value(status.url)"
