from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def compare(expected_review: dict[str, Any], gate_report: dict[str, Any]) -> dict[str, Any]:
    expected_state = expected_review.get("expected_gate_state")
    produced_state = gate_report.get("status")
    findings = gate_report.get("findings", [])
    if not isinstance(findings, list):
        findings = []

    return {
        "expected_gate_state": expected_state,
        "produced_gate_state": produced_state,
        "agreement": {
            "state_agreement": expected_state == produced_state,
            "full_agreement": False,
            "state_agreement_with_foundation_divergence": False,
            "material_divergence": expected_state != produced_state,
        },
        "error_classification": {
            "false_approved": produced_state == "approved" and expected_state != "approved",
            "false_blocked": produced_state == "blocked" and expected_state != "blocked",
            "missed_relevant_points": [],
            "incorrect_findings": [],
            "findings_without_traceable_evidence": [
                item.get("code")
                for item in findings
                if isinstance(item, dict) and not item.get("evidence_refs")
            ],
            "excessive_blocking": produced_state == "blocked" and expected_state in {"approved", "conditional"},
            "improper_release": produced_state == "approved" and expected_state in {"returned_for_correction", "blocked"},
            "equivalent_execution_inconsistency": False,
        },
        "human_review": {
            "required": gate_report.get("human_review_required"),
            "quality_notes": [],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare gate output with pre-recorded human review.")
    parser.add_argument("expected_human_review", type=Path)
    parser.add_argument("gate_json_report", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    result = compare(load_json(args.expected_human_review), load_json(args.gate_json_report))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
