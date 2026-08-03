from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, ClassVar

from quinta_ordem.models import DecisionStatus
from quinta_ordem.serialization import SerializationError, dumps_json, to_jsonable

from .models import (
    ChainVerification,
    MobileAuthority,
    MobileCheckpoint,
    MobileSession,
    RecordWithoutGates,
    SourceDigestBasis,
)

SCHEMA_VERSION = "1.0"
CANONICALIZATION = "quinta_ordem_json_v1"
COMPANION_SCOPE = "custody_and_explanation_only"
OBSERVATION_MODE = "post_bundle_reconstruction"
SOURCE_PRODUCER = "TCRIA"
MOBILE_NOTICE = (
    "Registro analítico derivado, complementar e não autorizativo. O Fifth Order "
    "não altera os dados, os gates nem o desfecho oficial do TCRIA."
)


class TCRIAMobileGateError(ValueError):
    """Raised when an official TCRIA bundle cannot be observed without inference."""


class FifthOrderMobileGate:
    """External companion that reconstructs checkpoints from a completed TCRIA bundle.

    This class never imports or invokes TCRIA code. It observes only the official JSON
    contract and produces its own custody receipts and deterministic explanations.
    """

    canonical_gate_order: ClassVar[tuple[str, ...]] = (
        "prescriptiveGate",
        "complianceGate",
        "traceabilityCheck",
        "maturityGate",
        "ledgerRuntimeCheck",
    )

    def observe_bundle(
        self,
        bundle: Mapping[str, Any],
        *,
        session_id: str | None = None,
        observed_at: str | None = None,
        source_ref: str = "memory://tcria/official-audit",
        source_artifact_sha256: str | None = None,
        source_digest_basis: SourceDigestBasis = SourceDigestBasis.CANONICAL_PAYLOAD,
        producer_revision: str | None = None,
    ) -> MobileSession:
        if not isinstance(bundle, Mapping):
            raise TCRIAMobileGateError("bundle must be a mapping.")

        snapshot = _strict_snapshot(bundle)
        payload_sha256 = _digest(snapshot)
        artifact_sha256 = source_artifact_sha256 or payload_sha256
        _require_sha256(artifact_sha256, "source_artifact_sha256")
        if not isinstance(source_digest_basis, SourceDigestBasis):
            raise TCRIAMobileGateError("source_digest_basis must be a SourceDigestBasis value.")
        if source_digest_basis == SourceDigestBasis.RAW_BYTES and source_artifact_sha256 is None:
            raise TCRIAMobileGateError(
                "source_artifact_sha256 is required when source_digest_basis is raw_bytes."
            )
        if (
            source_digest_basis == SourceDigestBasis.CANONICAL_PAYLOAD
            and artifact_sha256 != payload_sha256
        ):
            raise TCRIAMobileGateError(
                "source_artifact_sha256 must match the canonical payload digest when "
                "source_digest_basis is canonical_payload."
            )

        resolved_observed_at = observed_at or datetime.now(UTC).isoformat(timespec="seconds")
        _require_aware_iso8601(resolved_observed_at, "observed_at")
        resolved_source_ref = _require_text(source_ref, "source_ref")
        resolved_revision = _optional_text(producer_revision, "producer_revision")
        resolved_session_id = session_id or _default_session_id(
            artifact_sha256,
            resolved_observed_at,
        )
        _require_text(resolved_session_id, "session_id")

        source_generated_at = _optional_text(snapshot.get("generated_at"), "generated_at")
        record_views, without_gate_details = self._parse_records(snapshot)
        records_observed = len(record_views)
        records_with_gates = sum(bool(view["gates"]) for view in record_views)
        checkpoint_count = sum(len(view["gates"]) for view in record_views)

        genesis_payload = _genesis_payload(
            schema_version=SCHEMA_VERSION,
            canonicalization=CANONICALIZATION,
            session_id=resolved_session_id,
            authority=MobileAuthority.COMPLEMENTARY_NON_AUTHORITATIVE,
            companion_scope=COMPANION_SCOPE,
            observation_mode=OBSERVATION_MODE,
            observed_at=resolved_observed_at,
            source_producer=SOURCE_PRODUCER,
            producer_revision=resolved_revision,
            source_ref=resolved_source_ref,
            source_artifact_sha256=artifact_sha256,
            source_payload_sha256=payload_sha256,
            source_digest_basis=source_digest_basis,
            source_generated_at=source_generated_at,
            records_observed=records_observed,
            records_with_gates=records_with_gates,
            records_without_gates=len(without_gate_details),
            records_without_gate_details=tuple(without_gate_details),
            checkpoint_count=checkpoint_count,
            notice=MOBILE_NOTICE,
        )
        genesis_sha256 = _digest(genesis_payload)

        checkpoints: list[MobileCheckpoint] = []
        previous_receipt = genesis_sha256
        sequence = 1
        for view in record_views:
            prior_companion_blocked = False
            for gate_name, gate in view["gates"]:
                status, reason = _companion_assessment(
                    gate_name=gate_name,
                    source_status=gate["status"],
                    raises_accusation=view["raises_accusation"],
                    known_gate=gate_name in self.canonical_gate_order,
                    prior_companion_blocked=prior_companion_blocked,
                )
                summary = _companion_summary(
                    gate_name=gate_name,
                    source_status=gate["status"],
                    source_reason=gate["reason"],
                    companion_status=status,
                )
                checkpoint_id = _checkpoint_id(
                    resolved_session_id,
                    sequence,
                    view["source_partition"],
                    view["source_record_index"],
                    view["document_sha256"],
                    gate_name,
                )
                checkpoint = MobileCheckpoint(
                    schema_version=SCHEMA_VERSION,
                    session_id=resolved_session_id,
                    sequence=sequence,
                    checkpoint_id=checkpoint_id,
                    authority=MobileAuthority.COMPLEMENTARY_NON_AUTHORITATIVE,
                    observation_mode=OBSERVATION_MODE,
                    observed_at=resolved_observed_at,
                    source_artifact_sha256=artifact_sha256,
                    source_partition=view["source_partition"],
                    source_record_index=view["source_record_index"],
                    document_ref=view["document_ref"],
                    document_sha256=view["document_sha256"],
                    source_classification=view["source_classification"],
                    source_classification_reasons=view["source_classification_reasons"],
                    source_overall_outcome=view["source_overall_outcome"],
                    gate_name=gate_name,
                    source_status=gate["status"],
                    source_reason=gate["reason"],
                    source_evidence=gate["evidence"],
                    companion_status=status,
                    companion_reason=reason,
                    companion_summary=summary,
                    human_review_required=status != DecisionStatus.APPROVED,
                    previous_receipt_sha256=previous_receipt,
                    receipt_sha256="",
                )
                receipt = _checkpoint_digest(checkpoint)
                checkpoint = replace(checkpoint, receipt_sha256=receipt)
                checkpoints.append(checkpoint)
                previous_receipt = receipt
                prior_companion_blocked = status == DecisionStatus.BLOCKED
                sequence += 1

        session = MobileSession(
            schema_version=SCHEMA_VERSION,
            canonicalization=CANONICALIZATION,
            session_id=resolved_session_id,
            authority=MobileAuthority.COMPLEMENTARY_NON_AUTHORITATIVE,
            companion_scope=COMPANION_SCOPE,
            observation_mode=OBSERVATION_MODE,
            observed_at=resolved_observed_at,
            source_producer=SOURCE_PRODUCER,
            producer_revision=resolved_revision,
            source_ref=resolved_source_ref,
            source_artifact_sha256=artifact_sha256,
            source_payload_sha256=payload_sha256,
            source_digest_basis=source_digest_basis,
            source_generated_at=source_generated_at,
            records_observed=records_observed,
            records_with_gates=records_with_gates,
            records_without_gates=len(without_gate_details),
            records_without_gate_details=tuple(without_gate_details),
            checkpoint_count=len(checkpoints),
            genesis_sha256=genesis_sha256,
            final_chain_sha256=previous_receipt,
            checkpoints=tuple(checkpoints),
            notice=MOBILE_NOTICE,
        )
        verification = verify_mobile_chain(session)
        if not verification.valid:  # pragma: no cover - construction invariant
            raise TCRIAMobileGateError(
                "Internal mobile-chain construction failure: " + "; ".join(verification.errors)
            )
        return session

    def observe_bundle_file(
        self,
        path: str | Path,
        *,
        session_id: str | None = None,
        observed_at: str | None = None,
        producer_revision: str | None = None,
    ) -> MobileSession:
        source_path = Path(path).expanduser().resolve(strict=True)
        if not source_path.is_file():
            raise TCRIAMobileGateError(f"TCRIA bundle is not a regular file: {source_path}")

        try:
            raw_bytes = source_path.read_bytes()
            text = raw_bytes.decode("utf-8")
            payload = json.loads(
                text,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_json_constant,
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TCRIAMobileGateError(f"Invalid TCRIA JSON bundle: {source_path}") from exc
        if not isinstance(payload, Mapping):
            raise TCRIAMobileGateError("The TCRIA JSON root must be an object.")

        return self.observe_bundle(
            payload,
            session_id=session_id,
            observed_at=observed_at,
            source_ref=source_path.as_uri(),
            source_artifact_sha256=sha256(raw_bytes).hexdigest(),
            source_digest_basis=SourceDigestBasis.RAW_BYTES,
            producer_revision=producer_revision,
        )

    def _parse_records(
        self,
        bundle: Mapping[str, Any],
    ) -> tuple[list[dict[str, Any]], list[RecordWithoutGates]]:
        accusation_set = _mapping_list(bundle, "accusation_set", required=True)
        non_accusation_set = _mapping_list(bundle, "non_accusation_set", required=True)
        declared_accusation_count = _non_negative_int(
            bundle.get("accusation_set_count"),
            "accusation_set_count",
        )
        if declared_accusation_count != len(accusation_set):
            raise TCRIAMobileGateError(
                "accusation_set_count does not match the published accusation_set."
            )
        declared_total = _non_negative_int(bundle.get("total_files_scanned"), "total_files_scanned")
        if declared_total != len(accusation_set) + len(non_accusation_set):
            raise TCRIAMobileGateError(
                "total_files_scanned does not match the published record collections."
            )
        views: list[dict[str, Any]] = []
        without_gate_details: list[RecordWithoutGates] = []

        for partition, records in (
            ("accusation_set", accusation_set),
            ("non_accusation_set", non_accusation_set),
        ):
            for record_index, record in enumerate(records):
                path = f"{partition}[{record_index}]"
                view = _record_view(record, path, partition, record_index)
                expected_raises_accusation = partition == "accusation_set"
                if view["raises_accusation"] is not expected_raises_accusation:
                    raise TCRIAMobileGateError(
                        f"{path}.raises_accusation conflicts with its published collection."
                    )
                raw_gates = record.get("gates")
                if raw_gates is None:
                    if view["raises_accusation"]:
                        raise TCRIAMobileGateError(
                            f"{path}.gates is missing for a record with raises_accusation=true."
                        )
                    view["gates"] = ()
                    without_gate_details.append(
                        RecordWithoutGates(
                            source_partition=partition,
                            source_record_index=record_index,
                            document_ref=view["document_ref"],
                            document_sha256=view["document_sha256"],
                            source_classification=view["source_classification"],
                            raises_accusation=False,
                            explanation=(
                                "O TCRIA não publicou gates para este documento; o Fifth Order "
                                "não inferiu checkpoints ausentes."
                            ),
                        )
                    )
                elif not isinstance(raw_gates, Mapping):
                    raise TCRIAMobileGateError(f"{path}.gates must be an object or null.")
                else:
                    view["gates"] = _ordered_gates(raw_gates, path, self.canonical_gate_order)
                    if view["raises_accusation"]:
                        published_gate_names = {name for name, _ in view["gates"]}
                        missing_gates = [
                            name
                            for name in self.canonical_gate_order
                            if name not in published_gate_names
                        ]
                        if missing_gates:
                            raise TCRIAMobileGateError(
                                f"{path}.gates is missing required TCRIA gates: "
                                + ", ".join(missing_gates)
                                + "."
                            )
                    if not view["gates"]:
                        if view["raises_accusation"]:
                            raise TCRIAMobileGateError(
                                f"{path}.gates is empty for a record with raises_accusation=true."
                            )
                        without_gate_details.append(
                            RecordWithoutGates(
                                source_partition=partition,
                                source_record_index=record_index,
                                document_ref=view["document_ref"],
                                document_sha256=view["document_sha256"],
                                source_classification=view["source_classification"],
                                raises_accusation=False,
                                explanation=(
                                    "O TCRIA publicou um mapa de gates vazio; o Fifth Order não "
                                    "inferiu resultados ausentes."
                                ),
                            )
                        )
                views.append(view)

        return views, without_gate_details


def verify_mobile_chain(session: MobileSession) -> ChainVerification:
    errors: list[str] = []
    if not isinstance(session, MobileSession):
        return ChainVerification(False, 0, "", ("session must be a MobileSession.",))

    expected_genesis = _digest(
        _genesis_payload(
            schema_version=session.schema_version,
            canonicalization=session.canonicalization,
            session_id=session.session_id,
            authority=session.authority,
            companion_scope=session.companion_scope,
            observation_mode=session.observation_mode,
            observed_at=session.observed_at,
            source_producer=session.source_producer,
            producer_revision=session.producer_revision,
            source_ref=session.source_ref,
            source_artifact_sha256=session.source_artifact_sha256,
            source_payload_sha256=session.source_payload_sha256,
            source_digest_basis=session.source_digest_basis,
            source_generated_at=session.source_generated_at,
            records_observed=session.records_observed,
            records_with_gates=session.records_with_gates,
            records_without_gates=session.records_without_gates,
            records_without_gate_details=session.records_without_gate_details,
            checkpoint_count=session.checkpoint_count,
            notice=session.notice,
        )
    )
    if session.genesis_sha256 != expected_genesis:
        errors.append("genesis_sha256 does not match the session envelope.")
    if session.records_without_gates != len(session.records_without_gate_details):
        errors.append("records_without_gates does not match its detail list.")
    if session.records_observed != session.records_with_gates + session.records_without_gates:
        errors.append("record counters are inconsistent.")
    if session.checkpoint_count != len(session.checkpoints):
        errors.append("checkpoint_count does not match checkpoints.")

    previous_receipt = expected_genesis
    checkpoint_ids: set[str] = set()
    for expected_sequence, checkpoint in enumerate(session.checkpoints, start=1):
        if checkpoint.sequence != expected_sequence:
            errors.append(f"checkpoint {expected_sequence} has an invalid sequence.")
        if checkpoint.session_id != session.session_id:
            errors.append(f"checkpoint {expected_sequence} belongs to another session.")
        if checkpoint.authority != session.authority:
            errors.append(f"checkpoint {expected_sequence} has a different authority.")
        if checkpoint.observation_mode != session.observation_mode:
            errors.append(f"checkpoint {expected_sequence} has a different observation mode.")
        if checkpoint.observed_at != session.observed_at:
            errors.append(f"checkpoint {expected_sequence} has a different observed_at.")
        if checkpoint.source_artifact_sha256 != session.source_artifact_sha256:
            errors.append(f"checkpoint {expected_sequence} points to another source artifact.")
        if checkpoint.previous_receipt_sha256 != previous_receipt:
            errors.append(f"checkpoint {expected_sequence} has a broken previous-receipt link.")
        expected_id = _checkpoint_id(
            checkpoint.session_id,
            checkpoint.sequence,
            checkpoint.source_partition,
            checkpoint.source_record_index,
            checkpoint.document_sha256,
            checkpoint.gate_name,
        )
        if checkpoint.checkpoint_id != expected_id:
            errors.append(f"checkpoint {expected_sequence} has an invalid checkpoint_id.")
        if checkpoint.checkpoint_id in checkpoint_ids:
            errors.append(f"checkpoint {expected_sequence} duplicates a checkpoint_id.")
        checkpoint_ids.add(checkpoint.checkpoint_id)
        expected_receipt = _checkpoint_digest(checkpoint)
        if checkpoint.receipt_sha256 != expected_receipt:
            errors.append(f"checkpoint {expected_sequence} receipt does not match its content.")
        previous_receipt = expected_receipt

    if session.final_chain_sha256 != previous_receipt:
        errors.append("final_chain_sha256 does not match the last receipt.")
    return ChainVerification(
        valid=not errors,
        checkpoint_count=len(session.checkpoints),
        final_chain_sha256=previous_receipt,
        errors=tuple(errors),
    )


def _record_view(
    record: Mapping[str, Any],
    path: str,
    partition: str,
    record_index: int,
) -> dict[str, Any]:
    document = record.get("document", {})
    if document is None:
        document = {}
    if not isinstance(document, Mapping):
        raise TCRIAMobileGateError(f"{path}.document must be an object when declared.")

    top_sha = record.get("sha256")
    nested_sha = document.get("sha256")
    if top_sha is not None and nested_sha is not None and top_sha != nested_sha:
        raise TCRIAMobileGateError(f"{path} has conflicting document SHA-256 values.")
    document_sha256 = top_sha if top_sha is not None else nested_sha
    _require_sha256(document_sha256, f"{path}.sha256")

    document_ref = _first_text(
        document.get("relative_path"),
        record.get("file_name"),
        f"field {path}.document_ref",
    )
    classification = _require_text(record.get("classification"), f"{path}.classification")
    classification_reasons = _text_list(
        record.get("classification_reasons"),
        f"{path}.classification_reasons",
    )
    raises_accusation = record.get("raises_accusation")
    if not isinstance(raises_accusation, bool):
        raise TCRIAMobileGateError(f"{path}.raises_accusation must be a boolean.")
    overall_outcome = _optional_text(record.get("overall_outcome"), f"{path}.overall_outcome")

    return {
        "source_partition": partition,
        "source_record_index": record_index,
        "document_ref": document_ref,
        "document_sha256": document_sha256,
        "source_classification": classification,
        "source_classification_reasons": classification_reasons,
        "raises_accusation": raises_accusation,
        "source_overall_outcome": overall_outcome,
        "gates": (),
    }


def _ordered_gates(
    raw_gates: Mapping[str, Any],
    record_path: str,
    canonical_order: tuple[str, ...],
) -> tuple[tuple[str, dict[str, str | None]], ...]:
    names: list[str] = []
    for gate_name in raw_gates:
        if not isinstance(gate_name, str) or not gate_name.strip():
            raise TCRIAMobileGateError(f"{record_path}.gates contains an invalid gate name.")
        names.append(gate_name)
    known = [name for name in canonical_order if name in raw_gates]
    unknown = sorted(name for name in names if name not in canonical_order)

    ordered: list[tuple[str, dict[str, str | None]]] = []
    for gate_name in (*known, *unknown):
        gate = raw_gates[gate_name]
        gate_path = f"{record_path}.gates.{gate_name}"
        if not isinstance(gate, Mapping):
            raise TCRIAMobileGateError(f"{gate_path} must be an object.")
        status = _require_text(gate.get("status"), f"{gate_path}.status")
        reason = _require_text(gate.get("reason"), f"{gate_path}.reason")
        evidence = _optional_text(gate.get("evidence"), f"{gate_path}.evidence", allow_empty=True)
        ordered.append((gate_name, {"status": status, "reason": reason, "evidence": evidence}))
    return tuple(ordered)


def _companion_assessment(
    *,
    gate_name: str,
    source_status: str,
    raises_accusation: bool,
    known_gate: bool,
    prior_companion_blocked: bool,
) -> tuple[DecisionStatus, str]:
    if source_status == "BLOCKED":
        return (
            DecisionStatus.BLOCKED,
            "O bloqueio oficial foi preservado integralmente e não pode ser promovido.",
        )
    if prior_companion_blocked:
        return (
            DecisionStatus.BLOCKED,
            (
                "Um checkpoint anterior deste documento foi bloqueado; o Fifth Order preservou "
                "o bloqueio sem promover os checkpoints posteriores."
            ),
        )
    if source_status not in {"PASS", "WARN", "NOT_EVALUATED", "NOT_APPLICABLE"}:
        return (
            DecisionStatus.BLOCKED,
            "O status oficial está fora do contrato conhecido; o Fifth Order falhou de modo fechado.",
        )
    if not known_gate:
        return (
            DecisionStatus.CONDITIONAL,
            f"O gate {gate_name} não pertence ao contrato TCRIA conhecido e exige revisão humana.",
        )
    if not raises_accusation:
        return (
            DecisionStatus.CONDITIONAL,
            "O TCRIA publicou um gate para documento não acusatório; a inconsistência exige revisão.",
        )
    if source_status == "PASS":
        return (
            DecisionStatus.APPROVED,
            "O registro possui identidade documental e justificativa oficial preservadas.",
        )
    if source_status == "WARN":
        return (
            DecisionStatus.CONDITIONAL,
            "O alerta oficial foi preservado e permanece sujeito à revisão humana.",
        )
    if source_status == "NOT_EVALUATED":
        return (
            DecisionStatus.CONDITIONAL,
            "Requisito não avaliado não foi tratado como requisito satisfeito.",
        )
    return (
        DecisionStatus.CONDITIONAL,
        "A não aplicabilidade oficial foi preservada como limitação explícita.",
    )


def _companion_summary(
    *,
    gate_name: str,
    source_status: str,
    source_reason: str,
    companion_status: DecisionStatus,
) -> str:
    return (
        f"{gate_name}: o TCRIA registrou {source_status}. "
        f"Justificativa oficial: {source_reason} "
        f"O Fifth Order registrou {companion_status.value} apenas quanto à custódia e à "
        "explicação, sem alterar o desfecho oficial."
    )


def _genesis_payload(**values: Any) -> dict[str, Any]:
    return {"receipt_type": "mobile_session_genesis", **values}


def _checkpoint_digest(checkpoint: MobileCheckpoint) -> str:
    payload = to_jsonable(checkpoint)
    if not isinstance(payload, dict):  # pragma: no cover - dataclass invariant
        raise TCRIAMobileGateError("checkpoint did not serialize to an object.")
    payload.pop("receipt_sha256", None)
    return _digest(payload)


def _digest(value: Any) -> str:
    return sha256(dumps_json(value).encode("utf-8")).hexdigest()


def _strict_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        snapshot = to_jsonable(value)
    except SerializationError as exc:
        raise TCRIAMobileGateError("TCRIA bundle is not strictly serializable.") from exc
    if not isinstance(snapshot, dict):  # pragma: no cover - Mapping converts to an object
        raise TCRIAMobileGateError("TCRIA bundle snapshot must be an object.")
    return snapshot


def _checkpoint_id(
    session_id: str,
    sequence: int,
    partition: str,
    record_index: int,
    document_sha256: str,
    gate_name: str,
) -> str:
    identity = "\x00".join(
        (session_id, str(sequence), partition, str(record_index), document_sha256, gate_name)
    )
    return "tcria-cp-" + sha256(identity.encode("utf-8")).hexdigest()[:24]


def _default_session_id(source_sha256: str, observed_at: str) -> str:
    identity = f"{source_sha256}\x00{observed_at}"
    return "fifth-order-tcria-" + sha256(identity.encode("utf-8")).hexdigest()[:20]


def _mapping_list(
    bundle: Mapping[str, Any],
    key: str,
    *,
    required: bool,
) -> list[Mapping[str, Any]]:
    if required and key not in bundle:
        raise TCRIAMobileGateError(f"{key} is required.")
    value = bundle.get(key, [])
    if not isinstance(value, list):
        raise TCRIAMobileGateError(f"{key} must be a list.")
    records: list[Mapping[str, Any]] = []
    for index, record in enumerate(value):
        if not isinstance(record, Mapping):
            raise TCRIAMobileGateError(f"{key}[{index}] must be an object.")
        records.append(record)
    return records


def _non_negative_int(value: Any, path: str) -> int:
    if type(value) is not int or value < 0:
        raise TCRIAMobileGateError(f"{path} must be a non-negative integer.")
    return value


def _text_list(value: Any, path: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TCRIAMobileGateError(f"{path} must be a list.")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_require_text(item, f"{path}[{index}]"))
    return tuple(result)


def _require_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TCRIAMobileGateError(f"{path} must be a non-empty string.")
    return value


def _optional_text(value: Any, path: str, *, allow_empty: bool = False) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        qualifier = "a string" if allow_empty else "a non-empty string"
        raise TCRIAMobileGateError(f"{path} must be {qualifier} or null.")
    return value


def _first_text(first: Any, second: Any, path: str) -> str:
    for value in (first, second):
        if isinstance(value, str) and value.strip():
            return value
    raise TCRIAMobileGateError(f"{path} is required.")


def _require_sha256(value: Any, path: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise TCRIAMobileGateError(f"{path} must be a 64-character SHA-256 hex digest.")
    try:
        bytes.fromhex(value)
    except ValueError as exc:
        raise TCRIAMobileGateError(f"{path} must be a SHA-256 hex digest.") from exc


def _require_aware_iso8601(value: str, path: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise TCRIAMobileGateError(f"{path} must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TCRIAMobileGateError(f"{path} must include a timezone offset.")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TCRIAMobileGateError(f"Duplicate JSON key: {key!r}.")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise TCRIAMobileGateError(f"Non-finite JSON number is not allowed: {value}.")
