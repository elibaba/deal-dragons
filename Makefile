.PHONY: install test eval eval-live lint playground serve tf-init tf-plan tf-apply deploy

install:
	python -m venv .venv && .venv/bin/pip install -e ".[dev]"

test:
	.venv/bin/python -m pytest -q

eval:            ## deterministic golden-dataset regression gate (no LLM)
	.venv/bin/python eval/run_eval.py

eval-live:       ## end-to-end LLM eval + ADK AgentEvaluator
	.venv/bin/python eval/run_eval.py --live

eval-agents-cli:
	agents-cli eval deal_dragons --eval-dataset-path eval/deal_dragons.evalset.json --config-path eval/test_config.json

lint:
	.venv/bin/ruff check deal_dragons tests eval

playground:      ## ADK dev UI with persistent local sessions
	.venv/bin/adk web . --session_service_uri "sqlite+aiosqlite:///./.deal_dragons_sessions.db"

serve:
	.venv/bin/python server.py

tf-init:
	terraform -chdir=terraform init

tf-plan:
	terraform -chdir=terraform plan -var-file=terraform.tfvars

tf-apply:
	terraform -chdir=terraform apply -var-file=terraform.tfvars

deploy:          ## build + deploy via agents-cli (alternative to the GitHub Actions pipeline)
	agents-cli deploy --target cloud_run
