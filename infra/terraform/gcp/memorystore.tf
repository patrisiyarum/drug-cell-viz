resource "google_redis_instance" "cache" {
  name           = "drug-cell-viz-redis"
  tier           = var.redis_tier
  memory_size_gb = var.redis_memory_size_gb
  region         = var.region
  redis_version  = "REDIS_7_2"

  # Memorystore only speaks redis; the API auto-detects the scheme.
  # ARQ workers read the same URL via settings.redis_url.

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret" "redis_url" {
  secret_id = "redis-url"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "redis_url" {
  secret = google_secret_manager_secret.redis_url.id
  secret_data = format(
    "redis://%s:%d/0",
    google_redis_instance.cache.host,
    google_redis_instance.cache.port,
  )
}
