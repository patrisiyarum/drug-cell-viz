# GCP infra (Terraform)

Infrastructure-as-code for a production deploy of drug-cell-viz on Google
Cloud. Provisioned services:

| Service              | GCP primitive                   | Purpose                              |
|----------------------|---------------------------------|--------------------------------------|
| API                  | Cloud Run (containerised FastAPI) | Stateless HTTP + SSE ingress         |
| Postgres             | Cloud SQL (PostgreSQL 16)        | Analysis audit rows                  |
| Redis                | Memorystore for Redis            | ARQ task queue, app cache            |
| RabbitMQ             | External (CloudAMQP)             | Event bus for `analysis.completed`   |
| Blob storage         | Cloud Storage bucket             | AlphaFold PDBs, docked poses, PDFs   |
| Secrets              | Secret Manager                   | DB passwords, API tokens, Modal auth |
| Observability        | Cloud Logging + OTLP → Logfire   | Traces via OTEL instrumentation      |

The Render blueprint (`render.yaml` at the repo root) stays as the zero-cost
deployment path for demos and the free-tier public instance. This Terraform
module is the production path — paid, regional, reproducible, versioned.

## Layout

```
gcp/
├── main.tf              # provider + top-level module wiring
├── variables.tf         # project, region, image refs, env toggles
├── outputs.tf           # service URLs, connection strings (secret refs)
├── cloud_run_api.tf     # Cloud Run service for the FastAPI backend
├── cloud_sql.tf         # Postgres instance + database + user
├── memorystore.tf       # Redis instance (ARQ broker + app cache)
├── storage.tf           # GCS bucket for /blobs + IAM
├── secrets.tf           # Secret Manager entries consumed by Cloud Run env
└── terraform.tfvars.example   # Copy → terraform.tfvars + fill in
```

## Usage

```bash
cd infra/terraform/gcp
cp terraform.tfvars.example terraform.tfvars
# edit project_id, region, image refs
terraform init
terraform plan
terraform apply
```

## State

State is intentionally NOT committed. For a real deploy, back state with a
GCS bucket:

```hcl
terraform {
  backend "gcs" {
    bucket = "YOUR-tf-state-bucket"
    prefix = "drug-cell-viz"
  }
}
```

## Cost floor

A minimal regional deploy runs ~\$60/month: Cloud SQL db-f1-micro (~\$10),
Memorystore basic 1GB (~\$35), Cloud Run at free tier, GCS well below a
dollar, Secret Manager negligible. Scale Postgres + Memorystore tiers up
as traffic warrants.
