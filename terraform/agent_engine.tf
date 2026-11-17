# Vertex AI Agent Engine instance used as the managed backend for
# persistent Sessions (VertexAiSessionService) and long-term Memory Bank
# (VertexAiMemoryBankService). No code is deployed to it - the agent runs on
# Cloud Run and only uses the engine's Sessions + Memory Bank APIs.
resource "google_vertex_ai_reasoning_engine" "memory" {
  project      = var.project_id
  region       = var.region
  display_name = "${var.service_name}-sessions-and-memory"
  description  = "Deal Dragons persistent sessions + Memory Bank"
  depends_on   = [google_project_service.apis]
}

locals {
  agent_engine_id = element(split("/", google_vertex_ai_reasoning_engine.memory.id), length(split("/", google_vertex_ai_reasoning_engine.memory.id)) - 1)
}
