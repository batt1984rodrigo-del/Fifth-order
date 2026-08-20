from quinta_ordem.verifiers.utils import evidence_ref_for_item, evidence_ref_from_raw


def test_evidence_reference_identifier_is_trimmed():
    reference = evidence_ref_from_raw(" EVD-1 ")

    assert reference is not None
    assert reference.artifact_id == "EVD-1"


def test_mapping_reference_identifier_is_trimmed():
    reference = evidence_ref_from_raw({"artifact_id": " EVD-1 "})

    assert reference is not None
    assert reference.artifact_id == "EVD-1"


def test_evidence_item_identifier_is_trimmed():
    reference = evidence_ref_for_item({"artifact_id": " EVD-1 "})

    assert reference is not None
    assert reference.artifact_id == "EVD-1"
