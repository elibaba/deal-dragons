"""Fallback: create the Agent Engine instance (Sessions + Memory Bank) with the Vertex AI SDK.

Terraform (`terraform/agent_engine.tf`) is the primary path. Use this script if
your provider version does not yet support a code-less reasoning engine:

    python scripts/provision_agent_engine.py --project my-proj --location us-central1
"""

from __future__ import annotations

import argparse

import vertexai


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True)
    p.add_argument("--location", default="us-central1")
    args = p.parse_args()
    client = vertexai.Client(project=args.project, location=args.location)
    engine = client.agent_engines.create(
        config={
            "display_name": "deal-dragons-sessions-and-memory",
            "context_spec": {
                "memory_bank_config": {
                    "generation_config": {
                        "model": f"projects/{args.project}/locations/{args.location}/publishers/google/models/gemini-3.5-flash"
                    }
                }
            },
        }
    )
    print("AGENT_ENGINE_ID=" + engine.api_resource.name.split("/")[-1])


if __name__ == "__main__":
    main()
