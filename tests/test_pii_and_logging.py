"""PII redaction + structured JSON logging tests."""

import json
import logging

from deal_dragons.observability.logging_setup import StructuredJsonFormatter
from deal_dragons.observability.pii import redact_obj, redact_text_regex


def test_regex_redaction_covers_common_pii():
    fake_key = "AIza" + "x" * 35  # built at runtime so the repo never contains a key-shaped literal
    text = f"mail a.b@corp.example card 4111 1111 1111 1111 key {fake_key}"
    out = redact_text_regex(text)
    assert "a.b@corp.example" not in out and "4111" not in out and "AIza" not in out


def test_redact_obj_recurses():
    out = redact_obj({"args": {"contact": "x@y.io", "list": ["z@w.io"]}})
    assert out == {"args": {"contact": "[REDACTED:EMAIL_ADDRESS]", "list": ["[REDACTED:EMAIL_ADDRESS]"]}}


def test_json_formatter_emits_structured_scrubbed_record():
    rec = logging.LogRecord("deal_dragons.audit", logging.INFO, __file__, 1, "intent for bob@x.io", None, None)
    rec.tool = "fetch_deal_brief"
    rec.args_payload = {"email": "bob@x.io"}
    line = StructuredJsonFormatter().format(rec)
    data = json.loads(line)
    assert data["severity"] == "INFO"
    assert data["labels"]["tool"] == "fetch_deal_brief"
    assert "bob@x.io" not in line
