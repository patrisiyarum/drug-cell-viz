variable "project_id" {
  description = "GCP project id to deploy into."
  type        = string
}

variable "region" {
  description = "Primary region for all regional resources (Cloud Run, Cloud SQL, Memorystore, GCS)."
  type        = string
  default     = "us-central1"
}

variable "api_image" {
  description = "Fully-qualified container image for the FastAPI backend (e.g. us-central1-docker.pkg.dev/PROJECT/drug-cell-viz/api:latest)."
  type        = string
}

variable "rabbitmq_url_secret_id" {
  description = "Name of an existing Secret Manager secret holding the external RabbitMQ (CloudAMQP) AMQP URL. Created manually; referenced here."
  type        = string
  default     = "rabbitmq-url"
}

variable "logfire_token_secret_id" {
  description = "Optional Secret Manager secret holding a Logfire token for OTel ingest. Leave unset to export traces to Cloud Trace via OTLP only."
  type        = string
  default     = ""
}

variable "db_tier" {
  description = "Cloud SQL tier for Postgres. db-f1-micro is the cheapest; bump to db-custom-2-7680 (or larger) for production."
  type        = string
  default     = "db-f1-micro"
}

variable "redis_tier" {
  description = "Memorystore tier: BASIC (single node, cheap) or STANDARD_HA (replicated, HA)."
  type        = string
  default     = "BASIC"
}

variable "redis_memory_size_gb" {
  description = "Redis memory in GiB. 1 is the floor for BASIC tier."
  type        = number
  default     = 1
}

variable "blob_bucket_location" {
  description = "GCS bucket location. Prefer a multi-region like US for cheap, high-availability blob storage."
  type        = string
  default     = "US"
}

variable "api_min_instances" {
  description = "Cloud Run min instances. Set to 1 to avoid cold-start latency on the first request of the day."
  type        = number
  default     = 0
}

variable "api_max_instances" {
  description = "Cloud Run max instances — caps the concurrency when a burst of analyses hits."
  type        = number
  default     = 10
}

variable "api_cpu" {
  description = "Cloud Run CPU per instance. '2' is enough for RDKit docking stubs; bump to '4' for concurrent screening jobs."
  type        = string
  default     = "2"
}

variable "api_memory" {
  description = "Cloud Run memory per instance. RDKit + xgboost + AlphaMissense data caches need ~1 GiB baseline."
  type        = string
  default     = "2Gi"
}
