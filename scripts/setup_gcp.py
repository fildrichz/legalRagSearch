"""
One-time GCP resource provisioning script.

Creates:
  - Enables required GCP APIs
  - GCS bucket (stores embeddings / index staging)
  - Vertex AI Vector Search Index  (STREAM_UPDATE, cosine, 768-dim)
  - Vertex AI Vector Search Index Endpoint (public)
  - Deploys the index to the endpoint

WARNING: Index creation takes ~30-60 min. Endpoint deployment takes ~20 min.
         The script waits for both to complete before printing the IDs.

Prerequisites:
  pip install google-cloud-aiplatform google-cloud-storage
  gcloud auth application-default login
  gcloud config set project YOUR_PROJECT_ID

Usage:
  GOOGLE_CLOUD_PROJECT=my-project python scripts/setup_gcp.py
"""

import os
import subprocess
import sys
from pathlib import Path

# Load .env from project root (one level up from scripts/)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

PROJECT  = os.environ.get("GOOGLE_CLOUD_PROJECT")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

if not PROJECT:
    sys.exit("ERROR: Set GOOGLE_CLOUD_PROJECT environment variable.")

BUCKET_NAME       = f"{PROJECT}-legal-rag"
INDEX_DISPLAY     = "legal-rag-index"
ENDPOINT_DISPLAY  = "legal-rag-endpoint"
DEPLOYED_INDEX_ID = "legal_rag_deployed"

# text-embedding-004 output dimension
EMBEDDING_DIM = 768


# ---------------------------------------------------------------------------
# Step 1 — Enable APIs
# ---------------------------------------------------------------------------

APIS = [
    "aiplatform.googleapis.com",
    "storage.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
]

print("Enabling GCP APIs (this may take a minute)...")
subprocess.run(
    f"gcloud services enable {' '.join(APIS)} --project {PROJECT}",
    check=True,
    shell=True,
)
print("APIs enabled.\n")


# ---------------------------------------------------------------------------
# Step 2 — GCS bucket
# ---------------------------------------------------------------------------

from google.cloud import storage

storage_client = storage.Client(project=PROJECT)

bucket = storage_client.lookup_bucket(BUCKET_NAME)
if bucket is None:
    print(f"Creating GCS bucket gs://{BUCKET_NAME} in {LOCATION}...")
    bucket = storage_client.create_bucket(BUCKET_NAME, location=LOCATION)
    print(f"Bucket created: gs://{BUCKET_NAME}\n")
else:
    print(f"Bucket gs://{BUCKET_NAME} already exists — skipping.\n")


# ---------------------------------------------------------------------------
# Step 3 — Vector Search Index
# ---------------------------------------------------------------------------

from google.cloud import aiplatform

aiplatform.init(project=PROJECT, location=LOCATION)

print(f"Creating Vector Search Index '{INDEX_DISPLAY}'...")
print("  (This takes 30-60 minutes — the script will wait)\n")

index = aiplatform.MatchingEngineIndex.create_tree_ah_index(
    display_name=INDEX_DISPLAY,
    dimensions=EMBEDDING_DIM,
    approximate_neighbors_count=150,
    distance_measure_type="COSINE_DISTANCE",
    index_update_method="STREAM_UPDATE",
    leaf_node_embedding_count=500,
    leaf_nodes_to_search_percent=7,
    shard_size="SHARD_SIZE_SMALL",
)

index_id = index.name.split("/")[-1]
print(f"Index created: {index_id}\n")


# ---------------------------------------------------------------------------
# Step 4 — Index Endpoint
# ---------------------------------------------------------------------------

existing_endpoints = aiplatform.MatchingEngineIndexEndpoint.list(
    filter=f'display_name="{ENDPOINT_DISPLAY}"'
)
if existing_endpoints:
    endpoint = existing_endpoints[0]
    endpoint_id = endpoint.name.split("/")[-1]
    print(f"Reusing existing endpoint: {endpoint_id}\n")
else:
    print(f"Creating Index Endpoint '{ENDPOINT_DISPLAY}'...")
    endpoint = aiplatform.MatchingEngineIndexEndpoint.create(
        display_name=ENDPOINT_DISPLAY,
        public_endpoint_enabled=True,
    )
    endpoint_id = endpoint.name.split("/")[-1]
    print(f"Endpoint created: {endpoint_id}\n")


# ---------------------------------------------------------------------------
# Step 5 — Deploy index to endpoint
# ---------------------------------------------------------------------------

print("Deploying index to endpoint (this takes ~20 minutes)...")
endpoint.deploy_index(
    index=index,
    deployed_index_id=DEPLOYED_INDEX_ID,
    machine_type="e2-standard-2",
    min_replica_count=1,
    max_replica_count=1,
)
print("Index deployed.\n")


# ---------------------------------------------------------------------------
# Step 6 — Grant Cloud Run service account access
# ---------------------------------------------------------------------------

print("Granting Vertex AI + Storage access to the default compute service account...")

# Fetch project number via Python SDK (avoids bash subshell on Windows)
import google.auth
from google.cloud import resourcemanager_v3

rm_client = resourcemanager_v3.ProjectsClient()
project_resource = rm_client.get_project(name=f"projects/{PROJECT}")
project_number = project_resource.name.split("/")[-1]
compute_sa = f"{project_number}-compute@developer.gserviceaccount.com"

for role in ["roles/aiplatform.user", "roles/storage.objectViewer"]:
    subprocess.run(
        f'gcloud projects add-iam-policy-binding {PROJECT} '
        f'--member=serviceAccount:{compute_sa} '
        f'--role={role} --condition=None',
        check=True,
        shell=True,
    )
print("IAM bindings applied.\n")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("=" * 60)
print("Setup complete! Add these to your .env file:\n")
print(f"GOOGLE_CLOUD_PROJECT={PROJECT}")
print(f"GOOGLE_CLOUD_LOCATION={LOCATION}")
print(f"GCS_BUCKET={BUCKET_NAME}")
print(f"VECTOR_SEARCH_INDEX_ID={index_id}")
print(f"VECTOR_SEARCH_ENDPOINT_ID={endpoint_id}")
print("=" * 60)
print("\nNext steps:")
print("  1. python scripts/ingest.py   # embed + index CUAD contracts")
print("  2. bash scripts/deploy.sh     # build + deploy to Cloud Run")
