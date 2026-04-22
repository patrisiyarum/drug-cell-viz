output "api_url" {
  description = "Public URL of the deployed Cloud Run API service."
  value       = google_cloud_run_v2_service.api.uri
}

output "blobs_bucket" {
  description = "GCS bucket for AlphaFold PDBs, docked poses, PDF exports."
  value       = google_storage_bucket.blobs.name
}

output "db_instance_connection_name" {
  description = "Cloud SQL connection name (PROJECT:REGION:INSTANCE) for the Auth Proxy sidecar."
  value       = google_sql_database_instance.postgres.connection_name
}

output "redis_host" {
  description = "Memorystore private endpoint."
  value       = google_redis_instance.cache.host
}
