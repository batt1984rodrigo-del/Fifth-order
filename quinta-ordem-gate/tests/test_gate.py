from __future__ import annotations

from copy import deepcopy

import pytest

from quinta_ordem import (
    DecisionStatus,
    ExecutionContext,
    Finding,
    QuintaOrdemGate,
    Severity,
    Verifier,
    VerifierRegistry,
)
from quinta_ordem.confidence import DIMENSIONS


def test_clean_context_is_approved(context_factory):
    result = QuintaOrdemGate.default().evaluate(context_factory())

    assert result.status == DecisionStatus.APPROVED
    assert result.confidence == 1.0
    assert result.findings == []
    assert tuple(result.evaluated_verifiers) == DIMENSIONS


def test_empty_context_is_not_approved():
    context = ExecutionContext(
        execution_id="empty",
        evidence=[],
        artifacts=[],
        gate_results=[],
        logs=[],
        decisions=[],
        metadata={},
    )

    result = QuintaOrdemGate.default().evaluate(context)

    assert result.status == DecisionStatus.RETURNED
    assert result.confidence < 1.0
    assert {finding.code for finding in result.findings} >= {
        "NO_EVIDENCE",
        "NO_DECISIONS",
        "OPEN_POINTS_UNDECLARED",
    }


@pytest.mark.parametrize("sha256", [None, "abc", "z" * 64])
def test_missing_or_invalid_hash_blocks(context_factory, sha256):
    context = context_factory(
        evidence=[
            {
                "artifact_id": "EVD-1",
                "sha256": sha256,
                "modified_original": False,
            }
        ]
    )

    result = QuintaOrdemGate.default().evaluate(context)

    assert result.status == DecisionStatus.BLOCKED
    assert any(finding.code in {"MISSING_HASH", "INVALID_HASH"} for finding in result.findings)


def test_undeclared_original_state_returns_for_correction(context_factory):
    context = context_factory(evidence=[{"artifact_id": "EVD-1", "sha256": "a" * 64}])

    result = QuintaOrdemGate.default().evaluate(context)

    assert result.status == DecisionStatus.RETURNED
    assert any(finding.code == "ORIGINAL_STATE_UNDECLARED" for finding in result.findings)


def test_modified_original_blocks(context_factory):
    evidence = deepcopy(context_factory().evidence)
    evidence[0]["modified_original"] = True

    result = QuintaOrdemGate.default().evaluate(context_factory(evidence=evidence))

    assert result.status == DecisionStatus.BLOCKED
    assert any(finding.code == "ORIGINAL_MODIFIED" for finding in result.findings)


def test_previous_block_from_any_gate_is_monotonic(context_factory):
    context = context_factory(gate_results=[{"gate": "custom-safety", "status": "blocked"}])

    result = QuintaOrdemGate.default().evaluate(context)

    assert result.status == DecisionStatus.BLOCKED
    assert any(finding.code == "PREVIOUS_GATE_BLOCKED" for finding in result.findings)


@pytest.mark.parametrize(
    "statuses",
    [
        ["blocked", "approved"],
        ["approved", "blocked"],
    ],
)
def test_duplicate_gate_results_cannot_erase_block(context_factory, statuses):
    context = context_factory(
        gate_results=[{"gate": "prior", "status": status} for status in statuses]
    )

    result = QuintaOrdemGate.default().evaluate(context)

    assert result.status == DecisionStatus.BLOCKED
    assert {finding.code for finding in result.findings} >= {
        "PREVIOUS_GATE_BLOCKED",
        "CONFLICTING_GATE_RESULTS",
    }


def test_decision_without_evidence_is_returned(context_factory):
    decisions = deepcopy(context_factory().decisions)
    decisions[0]["evidence_refs"] = []
    decisions[0]["classification"] = "hypothesis"
    decisions[0]["support_level"] = "partial"

    result = QuintaOrdemGate.default().evaluate(context_factory(decisions=decisions))

    assert result.status == DecisionStatus.RETURNED
    assert any(finding.code == "DECISION_WITHOUT_EVIDENCE" for finding in result.findings)


def test_unknown_reference_is_returned(context_factory):
    decisions = deepcopy(context_factory().decisions)
    decisions[0]["evidence_refs"] = ["EVD-404"]
    decisions[0]["classification"] = "hypothesis"
    decisions[0]["support_level"] = "partial"

    result = QuintaOrdemGate.default().evaluate(context_factory(decisions=decisions))

    assert result.status == DecisionStatus.RETURNED
    assert any(finding.code == "UNKNOWN_EVIDENCE_REFERENCE" for finding in result.findings)


def test_fact_without_sufficient_support_blocks(context_factory):
    decisions = deepcopy(context_factory().decisions)
    decisions[0]["support_level"] = "partial"

    result = QuintaOrdemGate.default().evaluate(context_factory(decisions=decisions))

    assert result.status == DecisionStatus.BLOCKED
    assert any(finding.code == "FACT_WITH_INSUFFICIENT_SUPPORT" for finding in result.findings)


def test_corroboration_requires_two_distinct_evidences(context_factory):
    decisions = deepcopy(context_factory().decisions)
    decisions[0]["support_level"] = "corroborated"

    result = QuintaOrdemGate.default().evaluate(context_factory(decisions=decisions))

    assert result.status == DecisionStatus.BLOCKED
    assert any(finding.code == "CORROBORATION_NOT_DEMONSTRATED" for finding in result.findings)


def test_corroboration_rejects_duplicate_content_under_different_ids(context_factory):
    first = deepcopy(context_factory().evidence[0])
    second = deepcopy(first)
    second["artifact_id"] = "EVD-2"
    second["source"] = "memory://tests/evidence-2"
    decisions = deepcopy(context_factory().decisions)
    decisions[0]["support_level"] = "corroborated"
    decisions[0]["evidence_refs"] = ["EVD-1", "EVD-2"]

    result = QuintaOrdemGate.default().evaluate(
        context_factory(evidence=[first, second], decisions=decisions)
    )

    assert result.status == DecisionStatus.BLOCKED
    assert any(finding.code == "CORROBORATION_NOT_DEMONSTRATED" for finding in result.findings)


def test_missing_evidence_source_is_not_approved(context_factory):
    evidence = deepcopy(context_factory().evidence)
    evidence[0].pop("source")

    result = QuintaOrdemGate.default().evaluate(context_factory(evidence=evidence))

    assert result.status == DecisionStatus.RETURNED
    assert any(finding.code == "MISSING_EVIDENCE_SOURCE" for finding in result.findings)


def test_open_point_is_conditional(context_factory):
    context = context_factory(metadata={"open_points": [{"id": "P-1", "status": "open"}]})

    result = QuintaOrdemGate.default().evaluate(context)

    assert result.status == DecisionStatus.CONDITIONAL
    assert result.human_review_required is True
    assert any(finding.code == "UNRESOLVED_POINT" for finding in result.findings)


def test_accepted_uncertainty_requires_justification(context_factory):
    context = context_factory(
        metadata={"open_points": [{"id": "P-1", "status": "accepted_uncertainty"}]}
    )

    result = QuintaOrdemGate.default().evaluate(context)

    assert result.status == DecisionStatus.CONDITIONAL
    assert any(finding.code == "UNJUSTIFIED_ACCEPTED_UNCERTAINTY" for finding in result.findings)


def test_accepted_uncertainty_with_owner_and_reason_is_approved(context_factory):
    context = context_factory(
        metadata={
            "open_points": [
                {
                    "id": "P-1",
                    "status": "accepted_uncertainty",
                    "accepted_by": "human-reviewer",
                    "reason": "Limite documental registrado.",
                }
            ]
        }
    )

    result = QuintaOrdemGate.default().evaluate(context)

    assert result.status == DecisionStatus.APPROVED


def test_structurally_invalid_context_fails_closed_without_crashing(context_factory):
    context = context_factory(evidence="not-a-list")

    result = QuintaOrdemGate.default().evaluate(context)

    assert result.status == DecisionStatus.BLOCKED
    assert result.confidence == 0.0
    assert any(finding.code == "INVALID_COLLECTION_TYPE" for finding in result.findings)


class ExplodingDeepcopyDict(dict):
    def __deepcopy__(self, memo):
        raise RuntimeError("snapshot failure")


def test_snapshot_failure_has_zero_unevaluated_confidence(context_factory):
    metadata = ExplodingDeepcopyDict(open_points=[])

    result = QuintaOrdemGate.default().evaluate(context_factory(metadata=metadata))

    assert result.status == DecisionStatus.BLOCKED
    assert result.confidence == 0.0
    assert set(result.breakdown.as_dict().values()) == {0.0}
    assert any(finding.code == "CONTEXT_SNAPSHOT_FAILED" for finding in result.findings)


def test_duplicate_evidence_ids_block(context_factory):
    evidence = [*deepcopy(context_factory().evidence), *deepcopy(context_factory().evidence)]

    result = QuintaOrdemGate.default().evaluate(context_factory(evidence=evidence))

    assert result.status == DecisionStatus.BLOCKED
    assert any(finding.code == "DUPLICATE_EVIDENCE_ID" for finding in result.findings)


def test_original_and_derived_artifact_ids_cannot_collide(context_factory):
    context = context_factory(artifacts=[{"artifact_id": "EVD-1", "sha256": "b" * 64}])

    result = QuintaOrdemGate.default().evaluate(context)

    assert result.status == DecisionStatus.BLOCKED
    assert any(finding.code == "COLLIDING_ARTIFACT_ID" for finding in result.findings)


def test_invalid_open_point_references_fail_closed(context_factory):
    context = context_factory(
        metadata={"open_points": [{"id": "P-1", "status": "open", "evidence_refs": "EVD-1"}]}
    )

    result = QuintaOrdemGate.default().evaluate(context)

    assert result.status == DecisionStatus.BLOCKED
    assert any(finding.code == "INVALID_OPEN_POINT_REFS_TYPE" for finding in result.findings)


class MutatingVerifier(Verifier):
    name = "mutating-test"

    def verify(self, context: ExecutionContext) -> list[Finding]:
        context.evidence[0]["sha256"] = "0" * 64
        context.decisions.clear()
        return []


class FailingVerifier(Verifier):
    name = "failing-test"

    def verify(self, context: ExecutionContext) -> list[Finding]:
        raise RuntimeError("sensitive internal error")


class MalformedFindingVerifier(Verifier):
    name = "malformed-test"

    def verify(self, context: ExecutionContext) -> list[Finding]:
        return [
            Finding(
                verifier=self.name,
                code="MALFORMED",
                severity="critical",  # type: ignore[arg-type]
                message="Invalid runtime enum.",
                point_id="malformed",
            )
        ]


class UnserializableFindingVerifier(Verifier):
    name = "unserializable-test"

    def verify(self, context: ExecutionContext) -> list[Finding]:
        return [
            Finding(
                verifier=self.name,
                code="UNSERIALIZABLE",
                severity=Severity.WARNING,
                message="Invalid details.",
                point_id="unserializable",
                details={"unsupported": {1}},
            )
        ]


class FakeLogicalConsistencyVerifier(Verifier):
    name = "logical_consistency"

    def verify(self, context: ExecutionContext) -> list[Finding]:
        return []


def test_verifier_cannot_mutate_caller_or_other_checks(context_factory):
    context = context_factory()
    before = deepcopy(context)
    gate = QuintaOrdemGate([*QuintaOrdemGate.default().verifiers, MutatingVerifier()])

    result = gate.evaluate(context)

    assert context == before
    assert result.status == DecisionStatus.APPROVED
    assert result.confidence == 1.0


def test_verifier_exception_becomes_auditable_block(context_factory):
    gate = QuintaOrdemGate([*QuintaOrdemGate.default().verifiers, FailingVerifier()])

    result = gate.evaluate(context_factory())

    assert result.status == DecisionStatus.BLOCKED
    failure = next(
        finding for finding in result.findings if finding.code == "VERIFIER_EXECUTION_FAILED"
    )
    assert failure.details == {"exception_type": "RuntimeError"}
    assert "sensitive internal error" not in failure.message


def test_malformed_verifier_output_becomes_auditable_block(context_factory):
    gate = QuintaOrdemGate([*QuintaOrdemGate.default().verifiers, MalformedFindingVerifier()])

    result = gate.evaluate(context_factory())

    assert result.status == DecisionStatus.BLOCKED
    assert any(finding.code == "VERIFIER_EXECUTION_FAILED" for finding in result.findings)


def test_unserializable_verifier_finding_becomes_auditable_block(context_factory):
    gate = QuintaOrdemGate([*QuintaOrdemGate.default().verifiers, UnserializableFindingVerifier()])

    result = gate.evaluate(context_factory())

    assert result.status == DecisionStatus.BLOCKED
    assert any(finding.code == "VERIFIER_EXECUTION_FAILED" for finding in result.findings)


def test_malformed_original_hash_blocks(context_factory):
    evidence = deepcopy(context_factory().evidence)
    evidence[0]["original_sha256"] = "not-a-sha256"

    result = QuintaOrdemGate.default().evaluate(context_factory(evidence=evidence))

    assert result.status == DecisionStatus.BLOCKED
    assert any(finding.code == "INVALID_ORIGINAL_HASH" for finding in result.findings)


def test_unsupported_hypothesis_requires_human_review(context_factory):
    decisions = deepcopy(context_factory().decisions)
    decisions[0].update(
        classification="hypothesis",
        support_level="unsupported",
        promoted=False,
    )

    result = QuintaOrdemGate.default().evaluate(context_factory(decisions=decisions))

    assert result.status == DecisionStatus.CONDITIONAL
    assert any(finding.code == "UNSUPPORTED_ITEM_REQUIRES_REVIEW" for finding in result.findings)


@pytest.mark.parametrize("promoted", ["true", 1, []])
def test_promotion_state_must_be_boolean(context_factory, promoted):
    decisions = deepcopy(context_factory().decisions)
    decisions[0]["promoted"] = promoted

    result = QuintaOrdemGate.default().evaluate(context_factory(decisions=decisions))

    assert result.status == DecisionStatus.BLOCKED
    assert any(finding.code == "INVALID_PROMOTION_STATE" for finding in result.findings)


def test_missing_required_verifier_blocks(context_factory):
    gate = QuintaOrdemGate([])

    result = gate.evaluate(context_factory())

    assert result.status == DecisionStatus.BLOCKED
    assert len([f for f in result.findings if f.code == "REQUIRED_VERIFIER_MISSING"]) == 5


def test_core_verifier_cannot_be_replaced_or_bypassed(context_factory):
    gate = QuintaOrdemGate.default()
    with pytest.raises(ValueError, match="Core verifier cannot be replaced"):
        gate.register_verifier(FakeLogicalConsistencyVerifier(), replace=True)

    gate.registry.register(FakeLogicalConsistencyVerifier(), replace=True)
    context = context_factory(gate_results=[{"gate": "prior", "status": "blocked"}])
    result = gate.evaluate(context)

    assert result.status == DecisionStatus.BLOCKED
    assert {finding.code for finding in result.findings} >= {
        "PREVIOUS_GATE_BLOCKED",
        "CORE_VERIFIER_REPLACED",
    }
    assert result.breakdown.logical_consistency == 0.0
    assert result.confidence < 1.0


def test_registry_is_ordered_and_rejects_duplicate_names():
    registry = VerifierRegistry([MutatingVerifier(), FailingVerifier()])

    assert registry.names() == ("mutating-test", "failing-test")
    with pytest.raises(ValueError, match="already registered"):
        registry.register(MutatingVerifier())


def test_invalid_thresholds_are_rejected():
    with pytest.raises(ValueError, match="Thresholds"):
        QuintaOrdemGate([], approval_threshold=0.5, return_threshold=0.8)


def test_custom_finding_is_individually_preserved(context_factory):
    class InformationalVerifier(Verifier):
        name = "informational-test"

        def verify(self, context: ExecutionContext) -> list[Finding]:
            return [
                Finding(
                    verifier=self.name,
                    code="CUSTOM_INFO",
                    severity=Severity.INFO,
                    message="Registro explicativo.",
                    point_id="custom-point",
                )
            ]

    gate = QuintaOrdemGate([*QuintaOrdemGate.default().verifiers, InformationalVerifier()])

    result = gate.evaluate(context_factory())

    assert result.status == DecisionStatus.CONDITIONAL
    assert [finding.code for finding in result.findings] == ["CUSTOM_INFO"]
