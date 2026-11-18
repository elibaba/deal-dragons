variable "project_id" {
  description = "GCP project that hosts Deal Dragons."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run, Vertex AI Agent Engine, Model Armor and Artifact Registry."
  type        = string
  default     = "us-central1"
}

variable "service_name" {
  description = "Cloud Run service name."
  type        = string
  default     = "deal-dragons"
}

variable "image" {
  description = "Container image for the agent (set by CI after the build step)."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "fast_model" {
  description = "Gemini Flash model id for high-volume specialist agents."
  type        = string
  default     = "gemini-3.5-flash"
}

variable "pro_model" {
  description = "Gemini Pro model id for the Board Chair."
  type        = string
  default     = "gemini-3.1-pro-preview"
}

variable "github_repository" {
  description = "owner/repo allowed to deploy through Workload Identity Federation."
  type        = string
  default     = "elibaba/deal-dragons"
}

variable "invoker_members" {
  description = "IAM members allowed to invoke the (private) Cloud Run service, e.g. [\"user:you@example.com\"]."
  type        = list(string)
  default     = []
}

variable "enable_github_wif" {
  description = "Create a GitHub Actions Workload Identity Federation provider (keyless CD). Some orgs restrict external OIDC issuers via constraints/iam.workloadIdentityPoolProviders."
  type        = bool
  default     = true
}

variable "enable_model_armor" {
  description = "Provision a Model Armor template and wire it into the agent."
  type        = bool
  default     = true
}
