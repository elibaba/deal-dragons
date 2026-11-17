# Secret *containers* only. Values are added out-of-band, never committed:
#   printf '%s' "$TOKEN" | gcloud secrets versions add deal-dragons-crm-token --data-file=-
resource "google_secret_manager_secret" "crm_token" {
  project   = var.project_id
  secret_id = "deal-dragons-crm-token"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret" "gemini_api_key" {
  project   = var.project_id
  secret_id = "deal-dragons-gemini-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_iam_member" "runtime_access" {
  for_each  = {
    crm    = google_secret_manager_secret.crm_token.id
    gemini = google_secret_manager_secret.gemini_api_key.id
  }
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_runtime.email}"
}
