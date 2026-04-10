#!/usr/bin/env bash
# Tear down all running resources (Cloud Run + Vector Search).
# Artifact Registry images are kept so redeploy is fast.
# Run from the project root: bash scripts/teardown.sh

set -euo pipefail

# Load .env from project root if present
ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
  set -a && source "$ENV_FILE" && set +a
fi

PROJECT="${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
ENDPOINT_ID="${VECTOR_SEARCH_ENDPOINT_ID:?Set VECTOR_SEARCH_ENDPOINT_ID}"

SERVICE="legal-rag"
DEPLOYED_INDEX_ID="legal_rag_deployed"

# ── 1. Delete Cloud Run service ──────────────────────────────────────────────
echo "==> Deleting Cloud Run service..."
if gcloud run services describe "${SERVICE}" \
     --region="${LOCATION}" --project="${PROJECT}" &>/dev/null; then
  gcloud run services delete "${SERVICE}" \
    --region="${LOCATION}" \
    --project="${PROJECT}" \
    --quiet
  echo "    Service deleted."
else
  echo "    Service not found, skipping."
fi

# ── 2. Undeploy index from endpoint ─────────────────────────────────────────
echo "==> Undeploying Vector Search index..."
ALREADY_DEPLOYED=$(gcloud ai index-endpoints describe "${ENDPOINT_ID}" \
  --region="${LOCATION}" \
  --project="${PROJECT}" \
  --format="value(deployedIndexes.id)" 2>/dev/null || true)

if echo "${ALREADY_DEPLOYED}" | grep -q "${DEPLOYED_INDEX_ID}"; then
  gcloud ai index-endpoints undeploy-index "${ENDPOINT_ID}" \
    --deployed-index-id="${DEPLOYED_INDEX_ID}" \
    --region="${LOCATION}" \
    --project="${PROJECT}" \
    --quiet
  echo "    Index undeployed."
else
  echo "    Index not deployed, skipping."
fi

echo ""
echo "==> Done. Artifact Registry images retained for fast redeploy."
echo "    To bring everything back up: bash scripts/deploy.sh"
