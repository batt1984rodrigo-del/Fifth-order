from __future__ import annotations

import html
import json
import os
import re
import shutil
import tempfile
import unicodedata
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from urllib.parse import unquote, urlparse

from quinta_ordem.serialization import dumps_json, to_jsonable

from .models import MobileCheckpoint, MobileSession
from .tcria import MOBILE_NOTICE, verify_mobile_chain


class MobileUnsafeOutputPathError(ValueError):
    """Raised when derived mobile reports could overlap the observed source artifact."""


@dataclass(frozen=True)
class MobileReportBundle:
    root: Path
    json_report: Path
    markdown_report: Path
    checkpoint_ledger: Path
    manifest: Path


def write_mobile_report_bundle(
    session: MobileSession,
    output_root: str | Path,
) -> MobileReportBundle:
    """Atomically publish a verified session, checkpoint ledger and file manifest."""

    verification = verify_mobile_chain(session)
    if not verification.valid:
        raise ValueError("Invalid mobile chain: " + "; ".join(verification.errors))

    resolved_output = Path(output_root).expanduser().resolve(strict=False)
    source_path = _local_source_path(session.source_ref)
    protected_root = source_path.parent.resolve(strict=False) if source_path else None
    if protected_root and _paths_overlap(resolved_output, protected_root):
        raise MobileUnsafeOutputPathError(
            f"Mobile output overlaps the TCRIA source root: {protected_root}"
        )
    resolved_output.mkdir(parents=True, exist_ok=True)

    bundle_name = _safe_component(session.session_id)
    final_root = (resolved_output / bundle_name).resolve(strict=False)
    _assert_descendant(final_root, resolved_output)
    if protected_root and _paths_overlap(final_root, protected_root):
        raise MobileUnsafeOutputPathError(
            f"Mobile bundle overlaps the TCRIA source root: {protected_root}"
        )

    stage = Path(tempfile.mkdtemp(prefix=f".{bundle_name}-", dir=resolved_output))
    try:
        json_name = f"{bundle_name}_fifth_order_mobile.json"
        markdown_name = f"{bundle_name}_fifth_order_mobile.md"
        ledger_name = f"{bundle_name}_checkpoints.jsonl"
        manifest_name = f"{bundle_name}_manifest.json"

        json_report = stage / json_name
        markdown_report = stage / markdown_name
        checkpoint_ledger = stage / ledger_name
        manifest = stage / manifest_name

        _atomic_write_text(json_report, dumps_json(session))
        _atomic_write_text(markdown_report, _render_markdown(session))
        _atomic_write_text(checkpoint_ledger, _render_jsonl(session.checkpoints))
        _atomic_write_text(
            manifest,
            dumps_json(
                _manifest_payload(
                    session,
                    stage,
                    (json_report, markdown_report, checkpoint_ledger),
                )
            ),
        )

        if final_root.exists() or final_root.is_symlink():
            if (
                final_root.is_dir()
                and not final_root.is_symlink()
                and _trees_identical(stage, final_root)
            ):
                shutil.rmtree(stage)
                return MobileReportBundle(
                    root=final_root,
                    json_report=final_root / json_name,
                    markdown_report=final_root / markdown_name,
                    checkpoint_ledger=final_root / ledger_name,
                    manifest=final_root / manifest_name,
                )
            raise FileExistsError(f"Different mobile report bundle already exists: {final_root}")

        stage.rename(final_root)
        return MobileReportBundle(
            root=final_root,
            json_report=final_root / json_name,
            markdown_report=final_root / markdown_name,
            checkpoint_ledger=final_root / ledger_name,
            manifest=final_root / manifest_name,
        )
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def _manifest_payload(
    session: MobileSession,
    stage: Path,
    paths: tuple[Path, ...],
) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for path in sorted(paths, key=lambda item: item.name):
        resolved = path.resolve(strict=True)
        _assert_descendant(resolved, stage)
        data = resolved.read_bytes()
        files.append(
            {
                "path": resolved.relative_to(stage).as_posix(),
                "media_type": _media_type(resolved),
                "size_bytes": len(data),
                "sha256": sha256(data).hexdigest(),
            }
        )
    return {
        "schema_version": "1.0",
        "session_id": session.session_id,
        "source_artifact_sha256": session.source_artifact_sha256,
        "genesis_sha256": session.genesis_sha256,
        "final_chain_sha256": session.final_chain_sha256,
        "algorithm": "sha256",
        "notice": MOBILE_NOTICE,
        "files": files,
    }


def _render_jsonl(checkpoints: tuple[MobileCheckpoint, ...]) -> str:
    lines: list[str] = []
    for checkpoint in checkpoints:
        lines.append(
            json.dumps(
                to_jsonable(checkpoint),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        )
    return "\n".join(lines) + ("\n" if lines else "")


def _render_markdown(session: MobileSession) -> str:
    lines = [
        "# Fifth Order Gate — trilha móvel do TCRIA",
        "",
        f"**Sessão:** {_md(session.session_id)}  ",
        f"**Autoridade:** `{session.authority.value}`  ",
        f"**Modo de observação:** `{session.observation_mode}`  ",
        f"**Escopo:** `{session.companion_scope}`  ",
        f"**Observado em:** `{_md(session.observed_at)}`  ",
        f"**Fonte:** {_md(session.source_ref)}  ",
        f"**SHA-256 do artefato-fonte:** `{session.source_artifact_sha256}`  ",
        f"**SHA-256 do payload canônico:** `{session.source_payload_sha256}`  ",
        f"**Genesis:** `{session.genesis_sha256}`  ",
        f"**Recibo final:** `{session.final_chain_sha256}`",
        "",
        "## Cobertura",
        "",
        f"- Registros observados: `{session.records_observed}`",
        f"- Registros com gates: `{session.records_with_gates}`",
        f"- Registros sem gates: `{session.records_without_gates}`",
        f"- Checkpoints reconstruídos: `{session.checkpoint_count}`",
    ]

    if session.records_without_gate_details:
        lines.extend(["", "### Registros sem gates", ""])
        for record in session.records_without_gate_details:
            lines.append(
                f"- `{_md(record.source_partition)}[{record.source_record_index}]` — "
                f"{_md(record.document_ref)}: {_md(record.explanation)}"
            )

    lines.extend(["", "## Checkpoints", ""])
    if not session.checkpoints:
        lines.append(
            "Nenhum gate foi publicado pelo TCRIA; a sessão permanece ancorada no genesis."
        )
    for checkpoint in session.checkpoints:
        lines.extend(
            [
                f"### {checkpoint.sequence:03d} — `{_md(checkpoint.gate_name)}`",
                "",
                f"- Documento: {_md(checkpoint.document_ref)}",
                f"- SHA-256 do documento: `{checkpoint.document_sha256}`",
                f"- Status oficial TCRIA: `{_md(checkpoint.source_status)}`",
                f"- Motivo oficial: {_md(checkpoint.source_reason)}",
                "- Lastro oficial: "
                + (
                    _md(checkpoint.source_evidence)
                    if checkpoint.source_evidence
                    else "não informado"
                ),
                f"- Status complementar Fifth Order: `{checkpoint.companion_status.value}`",
                f"- Por quê do Fifth Order: {_md(checkpoint.companion_reason)}",
                f"- Resumo: {_md(checkpoint.companion_summary)}",
                f"- Recibo anterior: `{checkpoint.previous_receipt_sha256}`",
                f"- Recibo deste checkpoint: `{checkpoint.receipt_sha256}`",
                "",
            ]
        )

    lines.extend(
        [
            "## Limite operacional",
            "",
            (
                "Os checkpoints foram reconstruídos do bundle oficial concluído. O TCRIA atual não "
                "publica eventos durante a execução interna de cada gate; portanto este relatório "
                "não afirma observação em tempo real."
            ),
            "",
            "## Observação de integridade",
            "",
            MOBILE_NOTICE,
            "",
        ]
    )
    return "\n".join(lines)


def _local_source_path(source_ref: str) -> Path | None:
    parsed = urlparse(source_ref)
    if parsed.scheme.lower() == "file" and parsed.path:
        return Path(unquote(parsed.path)).resolve(strict=False)
    if parsed.scheme:
        return None
    path = Path(source_ref)
    return path.resolve(strict=False) if path.is_absolute() else None


def _paths_overlap(first: Path, second: Path) -> bool:
    return _is_relative_to(first, second) or _is_relative_to(second, first)


def _assert_descendant(path: Path, root: Path) -> None:
    if path == root or not _is_relative_to(path, root):
        raise MobileUnsafeOutputPathError(f"Derived path escapes output root: {path}")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_component(value: str, *, max_base_length: int = 48) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", normalized).strip("-._")
    base = re.sub(r"[-_.]{2,}", "-", base)[:max_base_length].rstrip("-._")
    if not base:
        base = "mobile-session"
    digest = sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"{base}-{digest}"


def _atomic_write_text(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _media_type(path: Path) -> str:
    if path.suffix == ".json":
        return "application/json"
    if path.suffix == ".jsonl":
        return "application/x-ndjson"
    return "text/markdown"


def _md(value: object) -> str:
    flattened = " ".join(str(value).splitlines())
    escaped_html = html.escape(flattened, quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|>\-])", r"\\\1", escaped_html)


def _trees_identical(left: Path, right: Path) -> bool:
    left_files = _regular_tree_files(left)
    right_files = _regular_tree_files(right)
    if left_files is None or right_files is None or left_files != right_files:
        return False
    return all((left / path).read_bytes() == (right / path).read_bytes() for path in left_files)


def _regular_tree_files(root: Path) -> list[Path] | None:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            return None
        if path.is_file():
            resolved = path.resolve(strict=True)
            if not _is_relative_to(resolved, root):
                return None
            files.append(path.relative_to(root))
    return sorted(files)
