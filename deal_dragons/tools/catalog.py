"""Read-only data access layer for the (mock) CRM, offering catalog, rate card and bench.

In production these would be backed by the CRM / PSA APIs (authenticated with a
token pulled from Secret Manager). For the demo they are JSON fixtures so the
system is fully reproducible and the evaluation suite is deterministic.
"""

from __future__ import annotations

import functools
import json
from typing import Any

from deal_dragons.config import DATA_DIR


@functools.cache
def _load(name: str) -> dict[str, Any]:
    with open(DATA_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


def offerings_by_id() -> dict[str, dict[str, Any]]:
    return {o["offering_id"]: o for o in _load("offerings_catalog.json")["offerings"]}


def rate_card() -> dict[str, Any]:
    return _load("rate_card.json")


def policy() -> dict[str, Any]:
    return rate_card()["policy"]


def consultants() -> list[dict[str, Any]]:
    return _load("consultant_bench.json")["consultants"]


def deals_by_id() -> dict[str, dict[str, Any]]:
    return {d["deal_id"]: d for d in _load("deal_pipeline.json")["deals"]}
