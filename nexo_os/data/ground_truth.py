"""Loader for the synthetic dataset's planted ground truth (counts, IDs, expected
figures). Used by the Phase 2 verification test and the Phase 8 eval harness.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from nexo_os.config import get_settings


def ground_truth_path() -> Path:
    return get_settings().synthetic_db_path.parent / "ground_truth.json"


@lru_cache(maxsize=1)
def load_ground_truth() -> dict:
    path = ground_truth_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Ground truth not found at {path}. Run `python -m nexo_os seed` first."
        )
    return json.loads(path.read_text(encoding="utf-8"))
