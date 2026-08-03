import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from quinta_ordem import DecisionStatus, ExecutionContext, QuintaOrdemGate
from quinta_ordem.reporting import write_report_bundle


def base_context(execution_id: str) -> ExecutionContext:
    return ExecutionContext(
        execution_id=execution_id,
        evidence=[
            {
                "artifact_id": "EVD-001",
                "sha256": sha256(b"quinta-ordem-scenario-evidence").hexdigest(),
                "modified_original": False,
                "source": f"memory://scenarios/{execution_id}/evidence-001",
            }
        ],
        artifacts=[],
        gate_results=[{"gate": "tcria", "status": "approved"}],
        logs=[],
        decisions=[
            {
                "decision_id": "DEC-001",
                "classification": "fact",
                "support_level": "direct",
                "evidence_refs": ["EVD-001"],
                "promoted": False,
            }
        ],
        metadata={"open_points": []},
    )


def build_scenarios() -> list[tuple[str, DecisionStatus, ExecutionContext]]:
    approved = base_context("scenario-approved")

    conditional_values = deepcopy(approved.__dict__)
    conditional_values["execution_id"] = "scenario-conditional"
    conditional_values["metadata"] = {
        "open_points": [
            {
                "id": "POINT-HUMAN-REVIEW",
                "status": "open",
                "return_to": "human_review",
                "evidence_refs": ["EVD-001"],
            }
        ]
    }
    conditional = ExecutionContext(**conditional_values)

    returned_values = deepcopy(approved.__dict__)
    returned_values["execution_id"] = "scenario-returned"
    returned_values["gate_results"] = [
        {"gate": "tcria", "status": "returned_for_correction"}
    ]
    returned = ExecutionContext(**returned_values)

    blocked_values = deepcopy(approved.__dict__)
    blocked_values["execution_id"] = "scenario-blocked"
    blocked_values["evidence"][0]["modified_original"] = True
    blocked = ExecutionContext(**blocked_values)

    return [
        ("resultado íntegro e resolvido", DecisionStatus.APPROVED, approved),
        ("ponto aberto para revisão humana", DecisionStatus.CONDITIONAL, conditional),
        ("gate anterior devolveu para correção", DecisionStatus.RETURNED, returned),
        ("original marcado como modificado", DecisionStatus.BLOCKED, blocked),
    ]


def main() -> None:
    gate = QuintaOrdemGate.default()
    output_root = Path("output/scenarios")

    for description, expected_status, context in build_scenarios():
        decision = gate.evaluate(context)
        if decision.status != expected_status:
            raise RuntimeError(
                f"{context.execution_id}: esperado {expected_status.value}, "
                f"obtido {decision.status.value}."
            )
        bundle = write_report_bundle(decision, context, output_root)
        finding_codes = ",".join(finding.code for finding in decision.findings) or "none"
        print(
            f"scenario={context.execution_id} "
            f"status={decision.status.value} "
            f"human_review={str(decision.human_review_required).lower()} "
            f"findings={finding_codes} "
            f"description={description}"
        )
        print(f"manifest={bundle.manifest}")


if __name__ == "__main__":
    main()
