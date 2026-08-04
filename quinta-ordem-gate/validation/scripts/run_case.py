from __future__ import annotations

import argparse
import json
from pathlib import Path

from quinta_ordem import ExecutionContext, QuintaOrdemGate
from quinta_ordem.reporting import write_report_bundle


def load_context(path: Path) -> ExecutionContext:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ExecutionContext(**payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a validation case through the frozen Quinta Ordem Gate core.")
    parser.add_argument("execution_context", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    context = load_context(args.execution_context)
    decision = QuintaOrdemGate.default().evaluate(context)
    bundle = write_report_bundle(decision, context, args.out)

    print(json.dumps(
        {
            "execution_id": decision.execution_id,
            "status": decision.status.value,
            "confidence": decision.confidence,
            "human_review_required": decision.human_review_required,
            "execution_context_sha256": decision.execution_context_sha256,
            "manifest": str(bundle.manifest),
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
