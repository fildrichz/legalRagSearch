#!/usr/bin/env bash
# Deploy only the Vector Search index — use this for local development.
# Run from the project root: bash scripts/deploy_index.sh

set -euo pipefail

# Load .env from project root if present
ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
  set -a && source "$ENV_FILE" && set +a
fi

PROJECT="${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
INDEX_ID="${VECTOR_SEARCH_INDEX_ID:?Set VECTOR_SEARCH_INDEX_ID}"
ENDPOINT_ID="${VECTOR_SEARCH_ENDPOINT_ID:?Set VECTOR_SEARCH_ENDPOINT_ID}"

DEPLOYED_INDEX_ID="legal_rag_deployed"

echo "==> Checking Vector Search index deployment..."
ALREADY_DEPLOYED=$(gcloud ai index-endpoints describe "${ENDPOINT_ID}" \
  --region="${LOCATION}" \
  --project="${PROJECT}" \
  --format="value(deployedIndexes.id)" 2>/dev/null || true)

if echo "${ALREADY_DEPLOYED}" | grep -q "${DEPLOYED_INDEX_ID}"; then
  echo "    Index already deployed, nothing to do."
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

echo ""
echo "==> Ready. Run the app locally with: python main.py"
