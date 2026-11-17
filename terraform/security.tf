# Model Armor template: prompt-injection/jailbreak, malicious URI and RAI screening.
resource "google_model_armor_template" "deal_dragons" {
  count       = var.enable_model_armor ? 1 : 0
  project     = var.project_id
  location    = var.region
  template_id = "${var.service_name}-guard"

  filter_config {
    pi_and_jailbreak_filter_settings {
      filter_enforcement = "ENABLED"
      confidence_level   = "MEDIUM_AND_ABOVE"
    }
    malicious_uri_filter_settings {
      filter_enforcement = "ENABLED"
    }
    rai_settings {
      rai_filters {
        filter_type      = "DANGEROUS"
        confidence_level = "MEDIUM_AND_ABOVE"
      }
      rai_filters {
        filter_type      = "HARASSMENT"
        confidence_level = "MEDIUM_AND_ABOVE"
      }
    }
    sdp_settings {
      basic_config {
        filter_enforcement = "ENABLED"
      }
    }
  }
  depends_on = [google_project_service.apis]
}
