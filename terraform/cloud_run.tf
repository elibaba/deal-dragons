resource "google_artifact_registry_repository" "agents" {
  project       = var.project_id
  location      = var.region
  repository_id = var.service_name
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

resource "google_cloud_run_v2_service" "agent" {
  project             = var.project_id
  name                = var.service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.agent_runtime.email
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
    containers {
      image = var.image
      resources {
        limits = { cpu = "2", memory = "2Gi" }
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION" # Gemini 3.x is served from the global endpoint
        value = "global"
      }
      env {
        name  = "GOOGLE_CLOUD_REGION" # Agent Engine + Model Armor region
        value = var.region
      }
      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "true"
      }
      env {
        name  = "AGENT_ENGINE_ID"
        value = local.agent_engine_id
      }
      env {
        name  = "FAST_MODEL"
        value = var.fast_model
      }
      env {
        name  = "PRO_MODEL"
        value = var.pro_model
      }
      env {
        name  = "ENABLE_CLOUD_TRACE"
        value = "true"
      }
      env {
        name  = "ENABLE_CLOUD_DLP"
        value = "true"
      }
      env {
        name  = "MODEL_ARMOR_TEMPLATE"
        value = var.enable_model_armor ? google_model_armor_template.deal_dragons[0].id : ""
      }
      # Secret injected by Cloud Run from Secret Manager - never baked into the image.
      env {
        name = "CRM_API_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.crm_token.secret_id
            version = "latest"
          }
        }
      }
    }
  }
  depends_on = [google_secret_manager_secret_iam_member.runtime_access, google_project_iam_member.agent_runtime]
}
