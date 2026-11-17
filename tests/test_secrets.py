"""Secure secret management: no hardcoded credentials anywhere in the repository."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),  # Google API key
    re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),
    re.compile(r"ghp_[0-9A-Za-z]{36}"),  # GitHub PAT
    re.compile(r"(?i)(api_key|secret|password|token)\s*=\s*['\"][A-Za-z0-9/+_\-]{16,}['\"]"),
]
SKIP = {".venv", ".git", "__pycache__", ".terraform", "node_modules"}


def test_no_hardcoded_secrets():
    offenders = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP for part in path.parts) or not path.is_file():
            continue
        if path.suffix not in {".py", ".tf", ".yaml", ".yml", ".json", ".toml", ".md", ".env", ".example"}:
            continue
        if path.name == "test_secrets.py":
            continue
        text = path.read_text(errors="ignore")
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                offenders.append(f"{path.relative_to(ROOT)}: {pat.pattern}")
    assert not offenders, offenders


def test_secret_manager_is_used():
    src = (ROOT / "deal_dragons/infrastructure/secrets.py").read_text()
    assert "secretmanager.SecretManagerServiceClient" in src
