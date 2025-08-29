resource "google_cloud_run_v2_service" "query_engine_fn" {
  count    = var.deploy_graphrag ? 1 : 0
  name     = "query-engine-fn"
  location = var.gcp_region
  project  = var.project_id
  deletion_protection = false

  template {
    service_account = var.query_engine_sa_email
    containers {
      image = "${var.location}-docker.pkg.dev/${var.project_id}/${var.repository_id}/graphrag-fn-query-engine:${var.image_tag}"
      ports {
        container_port = 8080
      }
      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "MEMGRAPH_HOST"
        value = var.memgraph_host
      }
      env {
        name  = "MEMGRAPH_PORT"
        value = var.memgraph_port
      }
      env {
        name  = "MEMGRAPH_USER"
        value = var.memgraph_user
      }
      env {
        name  = "MEMGRAPH_PASSWORD"
        value = var.memgraph_password
      }
      env {
        name  = "LOCATION"
        value = var.gcp_region
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
}