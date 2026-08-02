from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from quinta_ordem import ExecutionContext, Finding, QuintaOrdemGate, Severity, Verifier, reporting
from quinta_ordem.reporting import (
    UnsafeOutputPathError,
    write_point_reports,
    write_report_bundle,
)


def test_bundle_contains_all_reports_and_valid_manifest(tmp_path, context_factory):
    context = context_factory(metadata={"open_points": [{"id": "P-1", "status": "open"}]})
    decision = QuintaOrdemGate.default().evaluate(context)

    bundle = write_report_bundle(decision, context, tmp_path / "derived")

    assert bundle.root.is_dir()
    assert bundle.json_report.is_file()
    assert bundle.markdown_report.is_file()
    assert bundle.manifest.is_file()
    assert len(bundle.point_reports) == len(decision.findings) == 1

    payload = json.loads(bundle.json_report.read_text(encoding="utf-8"))
    assert payload["status"] == "conditional"
    assert payload["findings"][0]["severity"] == "warning"
    assert payload["execution_context_sha256"] == decision.execution_context_sha256

    markdown = bundle.markdown_report.read_text(encoding="utf-8")
    assert r"UNRESOLVED\_POINT" in markdown
    assert r"P\-1" in markdown
    assert decision.execution_context_sha256 in markdown
    assert decision.execution_context_sha256 in bundle.point_reports[0].read_text(encoding="utf-8")

    manifest = json.loads(bundle.manifest.read_text(encoding="utf-8"))
    assert len(manifest["files"]) == 2 + len(decision.findings)
    assert manifest["execution_context_sha256"] == decision.execution_context_sha256
    assert bundle.manifest.name not in {entry["path"] for entry in manifest["files"]}
    for entry in manifest["files"]:
        report_path = bundle.root / entry["path"]
        data = report_path.read_bytes()
        assert entry["size_bytes"] == len(data)
        assert entry["sha256"] == sha256(data).hexdigest()


def test_bundle_is_idempotent_only_when_bytes_are_identical(tmp_path, context_factory):
    context = context_factory()
    decision = QuintaOrdemGate.default().evaluate(context)
    output_root = tmp_path / "derived"

    first = write_report_bundle(decision, context, output_root)
    second = write_report_bundle(decision, context, output_root)

    assert first == second

    first.markdown_report.write_text("tampered", encoding="utf-8")
    with pytest.raises(FileExistsError, match="Different report bundle"):
        write_report_bundle(decision, context, output_root)


def test_bundle_is_bound_to_the_exact_evaluated_context(tmp_path, context_factory):
    first_context = context_factory()
    first_decision = QuintaOrdemGate.default().evaluate(first_context)
    evidence = deepcopy(first_context.evidence)
    evidence[0]["sha256"] = sha256(b"different-evidence").hexdigest()
    second_context = context_factory(evidence=evidence)
    second_decision = QuintaOrdemGate.default().evaluate(second_context)
    output_root = tmp_path / "derived"

    write_report_bundle(first_decision, first_context, output_root)

    with pytest.raises(ValueError, match="was not produced"):
        write_report_bundle(first_decision, second_context, output_root)
    with pytest.raises(FileExistsError, match="Different report bundle"):
        write_report_bundle(second_decision, second_context, output_root)


def test_decision_and_context_ids_must_match(tmp_path, context_factory):
    context = context_factory()
    decision = replace(
        QuintaOrdemGate.default().evaluate(context),
        execution_id="another-execution",
    )

    with pytest.raises(ValueError, match="execution_id must match"):
        write_report_bundle(decision, context, tmp_path / "derived")


def test_execution_and_point_ids_cannot_escape_output(tmp_path, context_factory):
    context = context_factory(
        execution_id="../../evidence/original",
        metadata={"open_points": [{"id": "../../point", "status": "open"}]},
    )
    decision = QuintaOrdemGate.default().evaluate(context)
    output_root = (tmp_path / "derived").resolve()

    bundle = write_report_bundle(decision, context, output_root)

    assert bundle.root.is_relative_to(output_root)
    assert all(path.is_relative_to(bundle.root) for path in bundle.point_reports)
    assert not (tmp_path / "evidence").exists()


def test_output_inside_evidence_root_is_rejected_without_touching_original(
    tmp_path,
    context_factory,
):
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    original = evidence_root / "original.pdf"
    original.write_bytes(b"original bytes")
    original_hash = sha256(original.read_bytes()).hexdigest()
    original_stat = original.stat()
    evidence = [
        {
            "artifact_id": "EVD-1",
            "sha256": original_hash,
            "modified_original": False,
            "source_path": str(original),
        }
    ]
    context = context_factory(evidence=evidence)
    decision = QuintaOrdemGate.default().evaluate(context)

    with pytest.raises(UnsafeOutputPathError):
        write_report_bundle(decision, context, evidence_root / "reports")

    assert original.read_bytes() == b"original bytes"
    assert original.stat().st_mtime_ns == original_stat.st_mtime_ns
    assert not (evidence_root / "reports").exists()


def test_missing_evidence_origin_prevents_all_reporting(tmp_path, context_factory):
    evidence = deepcopy(context_factory().evidence)
    evidence[0].pop("source")
    context = context_factory(evidence=evidence)
    decision = QuintaOrdemGate.default().evaluate(context)

    assert decision.status.value == "returned_for_correction"
    with pytest.raises(UnsafeOutputPathError, match="declare its origin"):
        write_report_bundle(decision, context, tmp_path / "evidence" / "reports")
    assert not (tmp_path / "evidence").exists()


def test_future_protected_root_inside_final_bundle_is_rejected(tmp_path, context_factory):
    output_root = tmp_path / "derived"
    bundle_name = reporting._safe_component("test-execution")
    protected_root = output_root / bundle_name / "points"
    context = context_factory(metadata={"open_points": [], "evidence_roots": [str(protected_root)]})
    decision = QuintaOrdemGate.default().evaluate(context)

    with pytest.raises(UnsafeOutputPathError, match="overlaps protected"):
        write_report_bundle(decision, context, output_root)

    assert output_root.is_dir()
    assert list(output_root.iterdir()) == []


def test_symlink_into_evidence_root_is_rejected(tmp_path, context_factory):
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    original = evidence_root / "original.txt"
    original.write_bytes(b"original")
    context = context_factory(
        evidence=[
            {
                "artifact_id": "EVD-1",
                "sha256": sha256(b"original").hexdigest(),
                "modified_original": False,
                "source_path": str(original),
            }
        ]
    )
    link = tmp_path / "evidence-link"
    link.symlink_to(evidence_root, target_is_directory=True)

    with pytest.raises(UnsafeOutputPathError):
        write_report_bundle(
            QuintaOrdemGate.default().evaluate(context),
            context,
            link / "reports",
        )


@pytest.mark.parametrize("roots", ["/tmp/evidence", ["relative/evidence"]])
def test_malformed_evidence_roots_fail_closed(tmp_path, context_factory, roots):
    context = context_factory(metadata={"open_points": [], "evidence_roots": roots})
    decision = QuintaOrdemGate.default().evaluate(context)

    assert decision.status.value == "blocked"
    assert any(finding.code.startswith("INVALID_EVIDENCE_ROOT") for finding in decision.findings)
    with pytest.raises(UnsafeOutputPathError):
        write_report_bundle(decision, context, tmp_path / "derived")
    assert not (tmp_path / "derived").exists()


def test_relative_source_path_fails_closed(tmp_path, context_factory):
    evidence = deepcopy(context_factory().evidence)
    evidence[0]["source"] = "evidence/original.txt"
    context = context_factory(evidence=evidence)
    decision = QuintaOrdemGate.default().evaluate(context)

    assert decision.status.value == "blocked"
    assert any(finding.code == "INVALID_EVIDENCE_SOURCE" for finding in decision.findings)
    with pytest.raises(UnsafeOutputPathError):
        write_report_bundle(decision, context, tmp_path / "evidence" / "reports")
    assert not (tmp_path / "evidence").exists()


def test_structurally_invalid_evidence_fails_reporting_cleanly(tmp_path, context_factory):
    context = context_factory(evidence=None)
    decision = QuintaOrdemGate.default().evaluate(context)

    assert decision.status.value == "blocked"
    with pytest.raises(UnsafeOutputPathError, match="evidence must be a list"):
        write_report_bundle(decision, context, tmp_path / "derived")
    assert not (tmp_path / "derived").exists()


def test_points_subdirectory_symlink_is_rejected(tmp_path, context_factory):
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    original = evidence_root / "original.txt"
    original.write_text("original", encoding="utf-8")
    output_dir = tmp_path / "derived"
    output_dir.mkdir()
    (output_dir / "points").symlink_to(evidence_root, target_is_directory=True)
    context = context_factory(metadata={"open_points": [{"id": "P-1", "status": "open"}]})
    decision = QuintaOrdemGate.default().evaluate(context)

    with pytest.raises(UnsafeOutputPathError, match="cannot be a symlink"):
        write_point_reports(decision, output_dir, context=context)

    assert original.read_text(encoding="utf-8") == "original"
    assert list(evidence_root.iterdir()) == [original]


def test_existing_bundle_with_internal_symlink_is_not_reused(tmp_path, context_factory):
    context = context_factory()
    decision = QuintaOrdemGate.default().evaluate(context)
    output_root = tmp_path / "derived"
    bundle = write_report_bundle(decision, context, output_root)
    original_bytes = bundle.json_report.read_bytes()
    external = tmp_path / "external.json"
    external.write_bytes(original_bytes)
    bundle.json_report.unlink()
    bundle.json_report.symlink_to(external)

    with pytest.raises(FileExistsError, match="Different report bundle"):
        write_report_bundle(decision, context, output_root)


def test_reporting_does_not_mutate_context_or_decision(tmp_path, context_factory):
    context = context_factory(metadata={"open_points": [{"id": "P-1", "status": "open"}]})
    decision = QuintaOrdemGate.default().evaluate(context)
    context_before = deepcopy(context)
    decision_before = deepcopy(decision)

    write_report_bundle(decision, context, tmp_path / "derived")

    assert context == context_before
    assert decision == decision_before


def test_intermediate_failure_publishes_no_partial_bundle(
    tmp_path,
    context_factory,
    monkeypatch,
):
    context = context_factory()
    decision = QuintaOrdemGate.default().evaluate(context)
    before = deepcopy(context)
    calls = 0
    original_writer = reporting._atomic_write_text

    def fail_on_second_write(path, content):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected write failure")
        original_writer(path, content)

    monkeypatch.setattr(reporting, "_atomic_write_text", fail_on_second_write)
    output_root = tmp_path / "derived"

    with pytest.raises(OSError, match="injected"):
        write_report_bundle(decision, context, output_root)

    assert context == before
    assert output_root.is_dir()
    assert list(output_root.iterdir()) == []


class MarkdownInjectionVerifier(Verifier):
    name = "markdown-injection-test"

    def verify(self, context: ExecutionContext) -> list[Finding]:
        return [
            Finding(
                verifier=self.name,
                code="MD_INJECTION",
                severity=Severity.WARNING,
                message="# heading [click](https://example.com) <script>alert(1)</script>",
                point_id="[point](https://example.com)",
            )
        ]


def test_untrusted_markdown_is_escaped(tmp_path, context_factory):
    context = context_factory()
    gate = QuintaOrdemGate([*QuintaOrdemGate.default().verifiers, MarkdownInjectionVerifier()])
    decision = gate.evaluate(context)

    bundle = write_report_bundle(decision, context, tmp_path / "derived")
    markdown = bundle.markdown_report.read_text(encoding="utf-8")

    assert "<script>" not in markdown
    assert "[click](https://example.com)" not in markdown
    assert "\\# heading" in markdown
    assert "&lt;script" in markdown


def test_demo_generates_complete_bundle(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    demo = project_root / "examples" / "demo.py"

    completed = subprocess.run(
        [sys.executable, str(demo)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "status=conditional" in completed.stdout
    assert list((tmp_path / "output" / "demo").rglob("*_quinta_ordem.json"))
    assert list((tmp_path / "output" / "demo").rglob("*_quinta_ordem.md"))
    assert list((tmp_path / "output" / "demo").rglob("*_manifest.json"))
