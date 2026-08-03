import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from quinta_ordem import DecisionStatus, QuintaOrdemGate
from quinta_ordem.adapters.tcria import TCRIAExecutionContextAdapter
from quinta_ordem.reporting import write_report_bundle


def normalized_tcria_payload() -> dict[str, object]:
    return {
        "quinta_ordem_adapter_version": "1.0",
        "execution_id": "tcria-integration-001",
        "evidence": [
            {
                "artifact_id": "TCRIA-EVD-001",
                "sha256": sha256(b"normalized-tcria-evidence").hexdigest(),
                "modified_original": False,
                "source": "memory://tcria/integration/evidence-001",
            }
        ],
        "artifacts": [],
        "gate_results": [{"gate": "tcria-documentary", "status": "approved"}],
        "logs": [
            {
                "event": "normalized_handoff_created",
                "actor": "tcria",
            }
        ],
        "decisions": [
            {
                "decision_id": "TCRIA-DEC-001",
                "classification": "fact",
                "support_level": "direct",
                "evidence_refs": ["TCRIA-EVD-001"],
                "promoted": False,
            }
        ],
        "signals_for_verification": [
            {
                "signal_id": "TCRIA-SIG-001",
                "support_level": "partial",
                "evidence_refs": ["TCRIA-EVD-001"],
                "message": "Sinal preservado para validação humana antes da promoção.",
            }
        ],
        "metadata": {"open_points": []},
    }


def main() -> None:
    payload = normalized_tcria_payload()
    original_payload = deepcopy(payload)

    context = TCRIAExecutionContextAdapter().adapt(payload)
    decision = QuintaOrdemGate.default().evaluate(context)

    if payload != original_payload:
        raise RuntimeError("O adaptador alterou o payload original do TCRIA.")
    if decision.status != DecisionStatus.CONDITIONAL:
        raise RuntimeError(
            f"Esperado conditional para o sinal pendente, obtido {decision.status.value}."
        )

    bundle = write_report_bundle(decision, context, Path("output/tcria"))
    signal = next(
        item for item in context.decisions if item.get("decision_id") == "TCRIA-SIG-001"
    )

    print("flow=tcria->execution_context->quinta_ordem_gate->report_bundle")
    print(f"execution_id={context.execution_id}")
    print(f"signal_promoted={str(signal['promoted']).lower()}")
    print(f"status={decision.status.value}")
    print(f"human_review={str(decision.human_review_required).lower()}")
    print(f"context_sha256={decision.execution_context_sha256}")
    print(f"manifest={bundle.manifest}")


if __name__ == "__main__":
    main()
