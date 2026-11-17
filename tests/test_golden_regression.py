"""Runs the golden-dataset regression suite as part of pytest (CI gate)."""

import json

import pytest

from eval.run_eval import GOLDEN, evaluate_case_offline


@pytest.mark.parametrize("case", GOLDEN, ids=[c["case_id"] for c in GOLDEN])
def test_golden_case(case):
    assert evaluate_case_offline(case) == []


def test_adk_evalset_is_valid():
    from pathlib import Path

    from google.adk.evaluation.eval_set import EvalSet

    data = json.loads((Path(__file__).resolve().parents[1] / "eval/deal_dragons.evalset.json").read_text())
    es = EvalSet.model_validate(data)
    assert len(es.eval_cases) >= 2
