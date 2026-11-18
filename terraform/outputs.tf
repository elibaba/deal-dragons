output "service_url" {
  value = google_cloud_run_v2_service.agent.uri
}

output "agent_engine_id" {
  value = local.agent_engine_id
}

output "runtime_service_account" {
  value = google_service_account.agent_runtime.email
}

output "artifact_registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.agents.repository_id}"
}

output "workload_identity_provider" {
  value = var.enable_github_wif ? google_iam_workload_identity_pool_provider.github[0].name : ""
}

output "deployer_service_account" {
  value = google_service_account.deployer.email
}
