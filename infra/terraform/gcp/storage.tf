resource "google_storage_bucket" "blobs" {
  name                        = "${var.project_id}-drug-cell-viz-blobs"
  location                    = var.blob_bucket_location
  force_destroy               = false
  uniform_bucket_level_access = true
  storage_class               = "STANDARD"

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }
  # AlphaFold PDBs + docked-pose caches are idempotent — safe to recompute
  # from source — so older blobs are fine in nearline storage.
}

# Cloud Run service account needs read/write access to the blobs bucket.
resource "google_storage_bucket_iam_member" "api_rw" {
  bucket = google_storage_bucket.blobs.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api.email}"
}
