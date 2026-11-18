# Keyless CI/CD: GitHub Actions authenticates with Workload Identity Federation.
resource "google_iam_workload_identity_pool" "github" {
  count                     = var.enable_github_wif ? 1 : 0
  project                   = var.project_id
  workload_identity_pool_id = "${var.service_name}-gh"
  display_name              = "Deal Dragons GitHub"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  count                              = var.enable_github_wif ? 1 : 0
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  attribute_condition = "assertion.repository == \"${var.github_repository}\""
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer" {
  project      = var.project_id
  account_id   = "${var.service_name}-deployer"
  display_name = "Deal Dragons CI deployer"
}

resource "google_service_account_iam_member" "deployer_wif" {
  count              = var.enable_github_wif ? 1 : 0
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github[0].name}/attribute.repository/${var.github_repository}"
}

resource "google_project_iam_member" "deployer" {
  for_each = toset(["roles/run.admin", "roles/artifactregistry.writer", "roles/aiplatform.user", "roles/iam.serviceAccountUser"])
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.deployer.email}"
}
