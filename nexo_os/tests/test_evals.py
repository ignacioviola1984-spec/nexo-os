"""Phase 8: the eval harness is green on the seeded dataset, and its suites actually
catch a regression (the gate bites)."""

from __future__ import annotations

import copy

import pytest

from nexo_os.data.factory import get_repository
from nexo_os.data.ground_truth import ground_truth_path, load_ground_truth
from nexo_os.evals import runner

pytestmark = pytest.mark.skipif(
    not ground_truth_path().exists(), reason="run `python -m nexo_os seed` first"
)


def test_eval_main_is_green() -> None:
    assert runner.main() == 0


def test_numbers_suite_catches_drift() -> None:
    repo = get_repository()
    gt = copy.deepcopy(load_ground_truth())
    gt["cartera"]["prima_total_ars"] = "0.00"  # introduce a regression
    fails = runner.suite_numbers(repo, gt)
    assert any("prima_total" in f for f in fails)


def test_detection_suite_catches_missing(monkeypatch) -> None:
    repo = get_repository()
    gt = copy.deepcopy(load_ground_truth())
    gt["morosidad"]["cuota_ids"] = gt["morosidad"]["cuota_ids"][:-1]  # drop one expected id
    fails = runner.suite_detection(repo, gt)
    assert any("cobranza" in f for f in fails)
