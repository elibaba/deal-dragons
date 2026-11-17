# Least-privilege runtime identity for the agent (no keys are ever created).
resource "google_service_account" "agent_runtime" {
  project      = var.project_id
  account_id   = "${var.service_name}-runtime"
  display_name = "Deal Dragons agent runtime"
}

locals {
  runtime_roles = [
    "roles/aiplatform.user",              # Gemini, Agent Engine Sessions & Memory Bank
    "roles/secretmanager.secretAccessor", # runtime secret access
    "roles/cloudtrace.agent",             # OpenTelemetry spans -> Cloud Trace
    "roles/logging.logWriter",            # structured JSON logs
    "roles/monitoring.metricWriter",
    "roles/dlp.user",                     # PII redaction via Sensitive Data Protection
    "roles/modelarmor.user",              # prompt/response screening
    "roles/telemetry.tracesWriter",
  ]
}

resource "google_project_iam_member" "agent_runtime" {
  for_each = toset(local.runtime_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.agent_runtime.email}"
}

resource "google_cloud_run_v2_service_iam_member" "invokers" {
  for_each = toset(var.invoker_members)
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.agent.name
  role     = "roles/run.invoker"
  member   = each.value
}
