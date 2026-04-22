resource "google_service_account" "api" {
  account_id   = "drug-cell-viz-api"
  display_name = "drug-cell-viz API runtime"
}

# Let the service account read every secret we expose as env vars.
resource "google_secret_manager_secret_iam_member" "api_db" {
  secret_id = google_secret_manager_secret.db_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

resource "google_secret_manager_secret_iam_member" "api_redis" {
  secret_id = google_secret_manager_secret.redis_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

# Optional RabbitMQ + Logfire secrets — only referenced in env if the
# matching secret id variables are non-empty. We read them by data source
# so they can be created out-of-band.
data "google_secret_manager_secret" "rabbitmq_url" {
  count     = var.rabbitmq_url_secret_id != "" ? 1 : 0
  secret_id = var.rabbitmq_url_secret_id
}

data "google_secret_manager_secret" "logfire_token" {
  count     = var.logfire_token_secret_id != "" ? 1 : 0
  secret_id = var.logfire_token_secret_id
}

resource "google_cloud_run_v2_service" "api" {
  name     = "drug-cell-viz-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.api.email

    scaling {
      min_instance_count = var.api_min_instances
      max_instance_count = var.api_max_instances
    }

    # Cloud SQL Auth Proxy sidecar so the API can connect via unix socket
    # without exposing the DB to the public internet.
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.postgres.connection_name]
      }
    }

    containers {
      image = var.api_image

      resources {
        limits = {
          cpu    = var.api_cpu
          memory = var.api_memory
        }
      }

      ports {
        container_port = 8000
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_url.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "REDIS_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.redis_url.secret_id
            version = "latest"
          }
        }
      }

      dynamic "env" {
        for_each = var.rabbitmq_url_secret_id != "" ? [1] : []
        content {
          name = "RABBITMQ_URL"
          value_source {
            secret_key_ref {
              secret  = var.rabbitmq_url_secret_id
              version = "latest"
            }
          }
        }
      }

      dynamic "env" {
        for_each = var.logfire_token_secret_id != "" ? [1] : []
        content {
          name = "LOGFIRE_TOKEN"
          value_source {
            secret_key_ref {
              secret  = var.logfire_token_secret_id
              version = "latest"
            }
          }
        }
      }

      env {
        name  = "STORAGE_BACKEND"
        value = "gcs"
      }

      env {
        name  = "PUBLIC_BASE_URL"
        # Cloud Run injects a public URL once the service is deployed —
        # config.py resolves RENDER_EXTERNAL_URL or this value at runtime.
        value = ""
      }

      env {
        name  = "OTEL_SERVICE_NAME"
        value = "drug-cell-viz-api"
      }

      startup_probe {
        http_get {
          path = "/healthz"
        }
        timeout_seconds   = 5
        period_seconds    = 10
        failure_threshold = 6
      }

      liveness_probe {
        http_get {
          path = "/healthz"
        }
        timeout_seconds   = 5
        period_seconds    = 30
      }
    }
  }

  depends_on = [google_project_service.apis]
}

# Allow unauthenticated traffic — the API is public. For internal-only
# deploys, replace with roles/run.invoker on a specific group.
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
