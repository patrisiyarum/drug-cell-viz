terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.40"
    }
  }
  # See README — for real deploys, uncomment and point at a state bucket.
  # backend "gcs" {
  #   bucket = "drug-cell-viz-tf-state"
  #   prefix = "gcp/"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable all APIs the stack touches. safe to run repeatedly.
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "redis.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudtrace.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}
