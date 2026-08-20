from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator, Mapping
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from quinta_ordem import DecisionStatus
from quinta_ordem.mobile import (
    FifthOrderMobileGate,
    MobileAuthority,
    SourceDigestBasis,
    TCRIAMobileGateError,
    verify_mobile_chain,
)
from quinta_ordem.mobile.reporting import (
    MobileUnsafeOutputPathError,
    write_mobile_report_bundle,
)
from quinta_ordem.serialization import dumps_json

OBSERVED_AT = "2026-08-03T10:30:00-03:00"


def _record(
    *,
    content: bytes = b"official document",
    raises_accusation: bool = True,
    gates: dict[str, object] | None | object = ...,
) -> dict[str, object]:
    document_sha = sha256(content).hexdigest()
    if gates is ...:
        gates = {
            "ledgerRuntimeCheck": {
                "status": "NOT_APPLICABLE",
                "reason": "Static files do not expose runtime ledger state.",
                "evidence": None,
            },
            "traceabilityCheck": {
                "status": "WARN",
                "reason": "Only one traceability signal was found.",
                "evidence": "dates=1",
            },
            "prescriptiveGate": {
                "status": "PASS",
                "reason": "No prescriptive patterns detected.",
                "evidence": None,
            },
            "maturityGate": {
                "status": "NOT_EVALUATED",
                "reason": "Maturity score is unavailable in static content.",
                "evidence": None,
            },
            "complianceGate": {
                "status": "BLOCKED",
                "reason": "DecisionRecord is incomplete.",
                "evidence": None,
            },
        }
    return {
        "file_name": "documento.txt",
        "sha256": document_sha,
        "document": {
            "relative_path": "case/documento.txt",
            "sha256": document_sha,
            "text": "SECRET ORIGINAL TEXT MUST NOT BE COPIED",
        },
        "classification": "ACCUSATORY_CANDIDATE" if raises_accusation else "SUPPORTING_EVIDENCE",
        "raises_accusation": raises_accusation,
        "classification_reasons": ["Official deterministic classification reason."],
        "gates": gates,
        "overall_outcome": "BLOCKED (complianceGate)" if raises_accusation else None,
    }


def _bundle() -> dict[str, object]:
    return {
        "generated_at": "2026-08-03T10:29:58",
        "audit_basis": "TCRIA modular engine audit",
        "total_files_scanned": 2,
        "accusation_set_count": 1,
        "accusation_set": [_record()],
        "non_accusation_set": [_record(content=b"support", raises_accusation=False, gates=None)],
    }


def _observe(bundle=None, **kwargs):
    return FifthOrderMobileGate().observe_bundle(
        bundle or _bundle(),
        session_id=kwargs.pop("session_id", "mobile-test-session"),
        observed_at=kwargs.pop("observed_at", OBSERVED_AT),
        **kwargs,
    )


def test_official_bundle_generates_five_ordered_checkpoints_without_mutating_input():
    source = _bundle()
    before = deepcopy(source)

    session = _observe(source, producer_revision="dfed1af")

    assert source == before
    assert session.authority == MobileAuthority.COMPLEMENTARY_NON_AUTHORITATIVE
    assert session.observation_mode == "post_bundle_reconstruction"
    assert session.companion_scope == "custody_and_explanation_only"
    assert session.records_observed == 2
    assert session.records_with_gates == 1
    assert session.records_without_gates == 1
    assert session.checkpoint_count == 5
    assert [checkpoint.gate_name for checkpoint in session.checkpoints] == [
        "prescriptiveGate",
        "complianceGate",
        "traceabilityCheck",
        "maturityGate",
        "ledgerRuntimeCheck",
    ]
    assert session.checkpoints[0].source_status == "PASS"
    assert session.checkpoints[0].source_reason == "No prescriptive patterns detected."
    assert session.checkpoints[0].source_evidence is None
    assert "SECRET ORIGINAL TEXT" not in dumps_json(session)
    assert verify_mobile_chain(session).valid is True


@pytest.mark.parametrize(
    ("source_status", "expected"),
    [
        ("PASS", DecisionStatus.APPROVED),
        ("WARN", DecisionStatus.CONDITIONAL),
        ("BLOCKED", DecisionStatus.BLOCKED),
        ("NOT_EVALUATED", DecisionStatus.CONDITIONAL),
        ("NOT_APPLICABLE", DecisionStatus.CONDITIONAL),
        ("pass", DecisionStatus.BLOCKED),
        ("FUTURE_STATUS", DecisionStatus.BLOCKED),
    ],
)
def test_source_status_is_preserved_and_companion_status_is_separate(
    source_status,
    expected,
):
    bundle = _bundle()
    bundle["accusation_set"][0]["gates"]["prescriptiveGate"] = {
        "status": source_status,
        "reason": "Official reason remains untouched.",
        "evidence": None,
    }

    checkpoint = _observe(bundle).checkpoints[0]

    assert checkpoint.source_status == source_status
    assert checkpoint.companion_status == expected
    assert checkpoint.human_review_required is (expected != DecisionStatus.APPROVED)


def test_unknown_gate_is_observed_after_known_gates_and_requires_review():
    bundle = _bundle()
    gates = bundle["accusation_set"][0]["gates"]
    gates["complianceGate"] = {
        "status": "PASS",
        "reason": "DecisionRecord is complete.",
        "evidence": None,
    }
    gates["futureGate"] = {
        "status": "PASS",
        "reason": "Future contract reason.",
        "evidence": None,
    }

    session = _observe(bundle)

    assert session.checkpoints[-1].gate_name == "futureGate"
    assert session.checkpoints[-1].source_status == "PASS"
    assert session.checkpoints[-1].companion_status == DecisionStatus.CONDITIONAL


def test_blocked_is_never_promoted_even_for_unknown_gate_or_non_accusatory_record():
    bundle = _bundle()
    bundle["accusation_set"] = []
    bundle["accusation_set_count"] = 0
    bundle["total_files_scanned"] = 1
    bundle["non_accusation_set"][0]["gates"] = {
        "futureGate": {
            "status": "BLOCKED",
            "reason": "Official block.",
            "evidence": None,
        }
    }

    checkpoint = _observe(bundle).checkpoints[0]

    assert checkpoint.source_status == "BLOCKED"
    assert checkpoint.companion_status == DecisionStatus.BLOCKED


def test_blocked_checkpoint_is_preserved_for_later_gates_in_same_document():
    session = _observe()
    by_name = {checkpoint.gate_name: checkpoint for checkpoint in session.checkpoints}

    assert by_name["complianceGate"].companion_status == DecisionStatus.BLOCKED
    assert by_name["traceabilityCheck"].source_status == "WARN"
    assert by_name["traceabilityCheck"].companion_status == DecisionStatus.BLOCKED
    assert by_name["maturityGate"].companion_status == DecisionStatus.BLOCKED
    assert by_name["ledgerRuntimeCheck"].companion_status == DecisionStatus.BLOCKED
    assert all(
        checkpoint.human_review_required
        for checkpoint in session.checkpoints
        if checkpoint.sequence >= by_name["complianceGate"].sequence
    )


@pytest.mark.parametrize(
    "gate_value",
    [
        {"status": "PASS", "reason": "", "evidence": None},
        {"status": "PASS", "evidence": None},
        {"status": None, "reason": "Reason", "evidence": None},
        "not-an-object",
    ],
)
def test_invalid_gate_contract_is_rejected(gate_value):
    bundle = _bundle()
    bundle["accusation_set"][0]["gates"] = {"prescriptiveGate": gate_value}

    with pytest.raises(TCRIAMobileGateError):
        _observe(bundle)


def test_accusatory_record_without_gates_is_rejected_instead_of_inferred():
    bundle = _bundle()
    bundle["accusation_set"][0]["gates"] = None

    with pytest.raises(TCRIAMobileGateError, match="raises_accusation=true"):
        _observe(bundle)


def test_conflicting_document_hashes_are_rejected():
    bundle = _bundle()
    bundle["accusation_set"][0]["document"]["sha256"] = sha256(b"other").hexdigest()

    with pytest.raises(TCRIAMobileGateError, match="conflicting"):
        _observe(bundle)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("accusation_set_count", 0, "accusation_set_count"),
        ("total_files_scanned", 99, "total_files_scanned"),
    ],
)
def test_declared_bundle_counts_must_match_published_records(field, value, message):
    bundle = _bundle()
    bundle[field] = value

    with pytest.raises(TCRIAMobileGateError, match=message):
        _observe(bundle)


def test_non_accusation_collection_is_required_for_complete_coverage():
    bundle = _bundle()
    del bundle["non_accusation_set"]

    with pytest.raises(TCRIAMobileGateError, match="non_accusation_set is required"):
        _observe(bundle)


@pytest.mark.parametrize(
    ("partition", "raises_accusation"),
    [("accusation_set", False), ("non_accusation_set", True)],
)
def test_record_partition_must_match_raises_accusation(partition, raises_accusation):
    bundle = _bundle()
    bundle[partition][0]["raises_accusation"] = raises_accusation

    with pytest.raises(TCRIAMobileGateError, match="conflicts with its published collection"):
        _observe(bundle)


def test_accusatory_record_must_publish_all_known_tcria_gates():
    bundle = _bundle()
    del bundle["accusation_set"][0]["gates"]["traceabilityCheck"]

    with pytest.raises(TCRIAMobileGateError, match="traceabilityCheck"):
        _observe(bundle)


def test_same_source_identity_and_time_generate_same_chain():
    first = _observe()
    second = _observe()

    assert first == second
    assert first.final_chain_sha256 == second.final_chain_sha256


class _SwitchingBundle(Mapping[str, object]):
    def __init__(self, first: dict[str, object], second: dict[str, object]) -> None:
        self._active = first
        self._second = second

    def __getitem__(self, key: str) -> object:
        return self._active[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._active)

    def __len__(self) -> int:
        return len(self._active)

    def items(self):
        first_items = self._active.items()
        self._active = self._second
        return first_items


def test_hash_and_checkpoints_are_built_from_one_strict_snapshot():
    first = _bundle()
    second = _bundle()
    second["accusation_set"][0] = _record(content=b"changed after first traversal")
    switching = _SwitchingBundle(first, second)

    session = _observe(switching)

    expected_sha = first["accusation_set"][0]["sha256"]
    assert session.checkpoints[0].document_sha256 == expected_sha
    assert session.source_payload_sha256 == sha256(dumps_json(first).encode("utf-8")).hexdigest()
    assert verify_mobile_chain(session).valid is True


def test_canonical_digest_basis_cannot_be_labeled_with_another_hash():
    with pytest.raises(TCRIAMobileGateError, match="canonical payload digest"):
        _observe(source_artifact_sha256=sha256(b"different payload").hexdigest())


@pytest.mark.parametrize("mutation", ["field", "remove", "reorder", "duplicate"])
def test_chain_verification_detects_checkpoint_tampering(mutation):
    session = _observe()
    checkpoints = list(session.checkpoints)
    if mutation == "field":
        checkpoints[0] = replace(checkpoints[0], source_reason="tampered")
    elif mutation == "remove":
        checkpoints.pop(1)
    elif mutation == "reorder":
        checkpoints[0], checkpoints[1] = checkpoints[1], checkpoints[0]
    else:
        checkpoints.insert(1, checkpoints[0])
    tampered = replace(session, checkpoints=tuple(checkpoints))

    verification = verify_mobile_chain(tampered)

    assert verification.valid is False
    assert verification.errors


def test_session_without_gates_is_anchored_by_genesis():
    bundle = _bundle()
    bundle["accusation_set"] = []
    bundle["accusation_set_count"] = 0
    bundle["total_files_scanned"] = 1

    session = _observe(bundle)

    assert session.checkpoint_count == 0
    assert session.final_chain_sha256 == session.genesis_sha256
    assert verify_mobile_chain(session).valid is True


def test_file_observation_hashes_exact_bytes_and_keeps_source_unchanged(tmp_path):
    source_dir = tmp_path / "tcria"
    source_dir.mkdir()
    compact = source_dir / "compact.json"
    pretty = source_dir / "pretty.json"
    payload = _bundle()
    compact.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    pretty.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    before_bytes = compact.read_bytes()
    before_mtime = compact.stat().st_mtime_ns

    first = FifthOrderMobileGate().observe_bundle_file(
        compact,
        session_id="compact",
        observed_at=OBSERVED_AT,
    )
    second = FifthOrderMobileGate().observe_bundle_file(
        pretty,
        session_id="pretty",
        observed_at=OBSERVED_AT,
    )

    assert first.source_digest_basis == SourceDigestBasis.RAW_BYTES
    assert first.source_artifact_sha256 == sha256(before_bytes).hexdigest()
    assert first.source_artifact_sha256 != second.source_artifact_sha256
    assert first.source_payload_sha256 == second.source_payload_sha256
    assert compact.read_bytes() == before_bytes
    assert compact.stat().st_mtime_ns == before_mtime


@pytest.mark.parametrize(
    "raw_bytes",
    [
        b'{"accusation_set": [], "accusation_set": []}',
        b'{"accusation_set": [], "value": NaN}',
        b'{"accusation_set": [',
        b"\xff\xfe\x00",
    ],
)
def test_malformed_or_ambiguous_json_is_rejected(tmp_path, raw_bytes):
    path = tmp_path / "audit.json"
    path.write_bytes(raw_bytes)

    with pytest.raises(TCRIAMobileGateError):
        FifthOrderMobileGate().observe_bundle_file(path, observed_at=OBSERVED_AT)


def test_mobile_reporting_writes_verified_atomic_bundle_and_manifest(tmp_path):
    source_dir = tmp_path / "tcria"
    source_dir.mkdir()
    source = source_dir / "audit.json"
    source.write_text(json.dumps(_bundle(), ensure_ascii=False), encoding="utf-8")
    session = FifthOrderMobileGate().observe_bundle_file(
        source,
        session_id="report-session",
        observed_at=OBSERVED_AT,
    )
    output_root = tmp_path / "fifth-order-output"

    first = write_mobile_report_bundle(session, output_root)
    second = write_mobile_report_bundle(session, output_root)

    assert first == second
    assert first.json_report.is_file()
    assert first.markdown_report.is_file()
    assert first.checkpoint_ledger.is_file()
    assert first.manifest.is_file()
    all_derived = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            first.json_report,
            first.markdown_report,
            first.checkpoint_ledger,
            first.manifest,
        )
    )
    assert "SECRET ORIGINAL TEXT" not in all_derived
    assert "post_bundle_reconstruction" in all_derived
    assert "complementary_non_authoritative" in all_derived

    manifest = json.loads(first.manifest.read_text(encoding="utf-8"))
    assert len(manifest["files"]) == 3
    assert manifest["final_chain_sha256"] == session.final_chain_sha256
    for entry in manifest["files"]:
        artifact = first.root / entry["path"]
        assert entry["sha256"] == sha256(artifact.read_bytes()).hexdigest()


def test_reporting_rejects_invalid_chain_before_creating_output(tmp_path):
    session = _observe()
    tampered = replace(
        session,
        checkpoints=(replace(session.checkpoints[0], source_reason="tampered"),)
        + session.checkpoints[1:],
    )
    output = tmp_path / "derived"

    with pytest.raises(ValueError, match="Invalid mobile chain"):
        write_mobile_report_bundle(tampered, output)

    assert not output.exists()


def test_reporting_rejects_output_inside_source_root_and_symlink(tmp_path):
    source_root = tmp_path / "tcria"
    source_root.mkdir()
    source = source_root / "audit.json"
    source.write_text(json.dumps(_bundle()), encoding="utf-8")
    session = FifthOrderMobileGate().observe_bundle_file(
        source,
        session_id="unsafe-output",
        observed_at=OBSERVED_AT,
    )

    with pytest.raises(MobileUnsafeOutputPathError):
        write_mobile_report_bundle(session, source_root / "derived")

    link = tmp_path / "tcria-link"
    link.symlink_to(source_root, target_is_directory=True)
    with pytest.raises(MobileUnsafeOutputPathError):
        write_mobile_report_bundle(session, link / "derived")

    assert not (source_root / "derived").exists()


def test_cli_produces_external_bundle_without_importing_tcria(tmp_path):
    source_root = tmp_path / "tcria"
    source_root.mkdir()
    source = source_root / "audit.json"
    source.write_text(json.dumps(_bundle()), encoding="utf-8")
    output = tmp_path / "mobile-output"
    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project_root / "src")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "quinta_ordem.mobile",
            str(source),
            "--output",
            str(output),
            "--session-id",
            "cli-session",
            "--observed-at",
            OBSERVED_AT,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=project_root,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["checkpoint_count"] == 5
    assert Path(result["manifest"]).is_file()
    assert "tcria" not in sys.modules
