from __future__ import annotations

import argparse
from pathlib import Path

from quinta_ordem.serialization import dumps_json

from .reporting import write_mobile_report_bundle
from .tcria import FifthOrderMobileGate, verify_mobile_chain


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reconstrói checkpoints externos do Fifth Order a partir de um JSON oficial do TCRIA."
        )
    )
    parser.add_argument("bundle", type=Path, help="JSON oficial concluído do TCRIA")
    parser.add_argument("--output", type=Path, required=True, help="raiz externa para os outputs")
    parser.add_argument("--session-id")
    parser.add_argument("--observed-at", help="timestamp ISO-8601 com fuso")
    parser.add_argument("--producer-revision", help="commit do TCRIA, somente quando conhecido")
    args = parser.parse_args()

    session = FifthOrderMobileGate().observe_bundle_file(
        args.bundle,
        session_id=args.session_id,
        observed_at=args.observed_at,
        producer_revision=args.producer_revision,
    )
    verification = verify_mobile_chain(session)
    if not verification.valid:  # pragma: no cover - observer verifies before returning
        parser.error("cadeia móvel inválida: " + "; ".join(verification.errors))
    reports = write_mobile_report_bundle(session, args.output)
    print(
        dumps_json(
            {
                "session_id": session.session_id,
                "checkpoint_count": session.checkpoint_count,
                "source_artifact_sha256": session.source_artifact_sha256,
                "final_chain_sha256": session.final_chain_sha256,
                "report_root": str(reports.root),
                "manifest": str(reports.manifest),
            }
        ),
        end="",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
