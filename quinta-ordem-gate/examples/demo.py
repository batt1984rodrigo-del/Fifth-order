import sys
from hashlib import sha256
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from quinta_ordem import ExecutionContext, QuintaOrdemGate
from quinta_ordem.reporting import write_report_bundle

context = ExecutionContext(
    execution_id="demo-001",
    evidence=[
        {
            "artifact_id": "EVD-001",
            "sha256": sha256(b"quinta-ordem-demo-evidence").hexdigest(),
            "modified_original": False,
            "source": "memory://demo/evidence-001",
        }
    ],
    artifacts=[],
    gate_results=[{"gate": "compliance", "status": "approved"}],
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
    metadata={
        "open_points": [
            {
                "id": "POINT-001",
                "status": "open",
                "return_to": "human_review",
            }
        ]
    },
)

decision = QuintaOrdemGate.default().evaluate(context)
bundle = write_report_bundle(decision, context, Path("output/demo"))

print(f"status={decision.status.value}")
print(f"confidence={decision.confidence:.4f}")
print(f"json={bundle.json_report}")
print(f"markdown={bundle.markdown_report}")
for path in bundle.point_reports:
    print(f"finding={path}")
print(f"manifest={bundle.manifest}")
