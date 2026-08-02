from __future__ import annotations

from hashlib import sha256
from typing import Any

import pytest

from quinta_ordem import ExecutionContext

VALID_HASH = sha256(b"quinta-ordem-test-evidence").hexdigest()


@pytest.fixture
def context_factory():
    def factory(**overrides: Any) -> ExecutionContext:
        values: dict[str, Any] = {
            "execution_id": "test-execution",
            "evidence": [
                {
                    "artifact_id": "EVD-1",
                    "sha256": VALID_HASH,
                    "modified_original": False,
                    "source": "memory://tests/evidence-1",
                }
            ],
            "artifacts": [],
            "gate_results": [{"gate": "compliance", "status": "approved"}],
            "logs": [],
            "decisions": [
                {
                    "decision_id": "DEC-1",
                    "classification": "fact",
                    "support_level": "direct",
                    "evidence_refs": ["EVD-1"],
                    "promoted": False,
                }
            ],
            "metadata": {"open_points": []},
        }
        values.update(overrides)
        return ExecutionContext(**values)

    return factory
