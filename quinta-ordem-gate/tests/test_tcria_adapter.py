from __future__ import annotations

import os
import subprocess
import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from quinta_ordem import DecisionStatus, QuintaOrdemGate
from quinta_ordem.adapters.tcria import TCRIAAdapterError, TCRIAExecutionContextAdapter


def _payload():
    return {
        "quinta_ordem_adapter_version": "1.0",
        "execution_id": "tcria-case-001",
        "evidence": [
            {
                "artifact_id": "DOC-1",
                "sha256": sha256(b"document").hexdigest(),
                "modified_original": False,
                "source": "memory://tcria/document-1",
            }
        ],
        "artifacts": [],
        "gate_results": [{"gate": "documentary", "status": "approved"}],
        "logs": [],
        "decisions": [
            {
                "decision_id": "DEC-1",
                "classification": "fact",
                "support_level": "direct",
                "evidence_refs": ["DOC-1"],
                "promoted": False,
            }
        ],
        "metadata": {"open_points": []},
    }


def test_adapter_is_pure_and_detaches_all_mutables():
    payload = _payload()
    before = deepcopy(payload)

    context = TCRIAExecutionContextAdapter().adapt(payload)
    context.evidence[0]["artifact_id"] = "CHANGED-IN-COPY"
    context.metadata["open_points"].append({"id": "P-1"})

    assert payload == before
    assert payload["evidence"][0]["artifact_id"] == "DOC-1"
    assert payload["metadata"]["open_points"] == []


def test_adapter_preserves_previous_block():
    payload = _payload()
    payload["gate_results"] = [{"gate": "documentary", "status": "BLOCKED"}]

    context = TCRIAExecutionContextAdapter().adapt(payload)
    result = QuintaOrdemGate.default().evaluate(context)

    assert result.status == DecisionStatus.BLOCKED
    assert any(finding.code == "PREVIOUS_GATE_BLOCKED" for finding in result.findings)


def test_signals_remain_unpromoted_and_require_human_review():
    payload = _payload()
    payload["decisions"] = []
    payload["signals_for_verification"] = [
        {
            "signal_id": "SIG-1",
            "support_level": "partial",
            "evidence_refs": ["DOC-1"],
            "message": "Sinal para verificação humana.",
        }
    ]

    context = TCRIAExecutionContextAdapter().adapt(payload)
    result = QuintaOrdemGate.default().evaluate(context)

    assert context.decisions[0]["classification"] == "signal"
    assert context.decisions[0]["promoted"] is False
    assert result.status == DecisionStatus.CONDITIONAL
    assert result.human_review_required is True
    assert any(finding.code == "UNRESOLVED_POINT" for finding in result.findings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quinta_ordem_adapter_version", "2.0"),
        ("gate_results", [{"gate": "documentary", "status": "mystery"}]),
    ],
)
def test_unknown_version_or_status_is_rejected(field, value):
    payload = _payload()
    payload[field] = value

    with pytest.raises(TCRIAAdapterError):
        TCRIAExecutionContextAdapter().adapt(payload)


def test_missing_adapter_version_is_rejected():
    payload = _payload()
    del payload["quinta_ordem_adapter_version"]

    with pytest.raises(TCRIAAdapterError, match="version is required"):
        TCRIAExecutionContextAdapter().adapt(payload)


@pytest.mark.parametrize(
    "field", ["evidence", "artifacts", "gate_results", "logs", "decisions", "metadata"]
)
def test_required_normalized_fields_are_not_inferred(field):
    payload = _payload()
    del payload[field]

    with pytest.raises(TCRIAAdapterError, match="required"):
        TCRIAExecutionContextAdapter().adapt(payload)


def test_adapter_schema_version_cannot_be_reconfigured():
    with pytest.raises(TypeError):
        TCRIAExecutionContextAdapter(adapter_schema_version="2.0")


def test_missing_original_state_is_not_inferred():
    payload = _payload()
    del payload["evidence"][0]["modified_original"]

    context = TCRIAExecutionContextAdapter().adapt(payload)
    result = QuintaOrdemGate.default().evaluate(context)

    assert "modified_original" not in context.evidence[0]
    assert result.status == DecisionStatus.RETURNED
    assert any(finding.code == "ORIGINAL_STATE_UNDECLARED" for finding in result.findings)


@pytest.mark.parametrize("open_points", [{"id": "P-1"}, "P-1", None])
def test_root_open_points_must_be_a_list(open_points):
    payload = _payload()
    payload["metadata"] = {}
    payload["open_points"] = open_points

    with pytest.raises(TCRIAAdapterError, match="open_points must be a list"):
        TCRIAExecutionContextAdapter().adapt(payload)


def test_core_import_does_not_load_tcria_adapter():
    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project_root / "src")
    command = (
        "import sys; import quinta_ordem; assert 'quinta_ordem.adapters.tcria' not in sys.modules"
    )

    completed = subprocess.run(
        [sys.executable, "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
