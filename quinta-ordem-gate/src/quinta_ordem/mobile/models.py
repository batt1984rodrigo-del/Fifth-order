from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from quinta_ordem.models import DecisionStatus


class MobileAuthority(str, Enum):
    COMPLEMENTARY_NON_AUTHORITATIVE = "complementary_non_authoritative"


class SourceDigestBasis(str, Enum):
    RAW_BYTES = "raw_bytes"
    CANONICAL_PAYLOAD = "canonical_payload"


@dataclass(frozen=True)
class RecordWithoutGates:
    source_partition: str
    source_record_index: int
    document_ref: str
    document_sha256: str
    source_classification: str
    raises_accusation: bool
    explanation: str


@dataclass(frozen=True)
class MobileCheckpoint:
    schema_version: str
    session_id: str
    sequence: int
    checkpoint_id: str
    authority: MobileAuthority
    observation_mode: str
    observed_at: str
    source_artifact_sha256: str
    source_partition: str
    source_record_index: int
    document_ref: str
    document_sha256: str
    source_classification: str
    source_classification_reasons: tuple[str, ...]
    source_overall_outcome: str | None
    gate_name: str
    source_status: str
    source_reason: str
    source_evidence: str | None
    companion_status: DecisionStatus
    companion_reason: str
    companion_summary: str
    human_review_required: bool
    previous_receipt_sha256: str
    receipt_sha256: str


@dataclass(frozen=True)
class MobileSession:
    schema_version: str
    canonicalization: str
    session_id: str
    authority: MobileAuthority
    companion_scope: str
    observation_mode: str
    observed_at: str
    source_producer: str
    producer_revision: str | None
    source_ref: str
    source_artifact_sha256: str
    source_payload_sha256: str
    source_digest_basis: SourceDigestBasis
    source_generated_at: str | None
    records_observed: int
    records_with_gates: int
    records_without_gates: int
    records_without_gate_details: tuple[RecordWithoutGates, ...]
    checkpoint_count: int
    genesis_sha256: str
    final_chain_sha256: str
    checkpoints: tuple[MobileCheckpoint, ...]
    notice: str


@dataclass(frozen=True)
class ChainVerification:
    valid: bool
    checkpoint_count: int
    final_chain_sha256: str
    errors: tuple[str, ...]
