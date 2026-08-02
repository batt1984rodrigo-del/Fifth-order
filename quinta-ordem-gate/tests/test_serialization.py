from __future__ import annotations

import json

import pytest

from quinta_ordem import DecisionStatus, QuintaOrdemGate
from quinta_ordem.serialization import SerializationError, dumps_json, to_jsonable


def test_enums_and_dataclasses_use_json_primitives(context_factory):
    decision = QuintaOrdemGate.default().evaluate(context_factory())

    payload = json.loads(dumps_json(decision))

    assert payload["status"] == DecisionStatus.APPROVED.value
    assert payload["breakdown"]["integrity"] == 1.0
    assert payload["schema_version"] == "1.0"


@pytest.mark.parametrize("value", [{"bad": {1, 2}}, {"bad": float("nan")}, {"bad": object()}])
def test_unknown_or_non_deterministic_values_are_rejected(value):
    with pytest.raises(SerializationError):
        to_jsonable(value)


def test_cycles_are_rejected():
    value: list[object] = []
    value.append(value)

    with pytest.raises(SerializationError, match="Cyclic"):
        to_jsonable(value)


def test_isolated_unicode_surrogate_is_rejected():
    with pytest.raises(SerializationError, match="UTF-8"):
        to_jsonable("\ud800")


def test_json_dump_is_deterministic():
    value = {"z": [2, 1], "a": {"b": True}}

    assert dumps_json(value) == dumps_json(value)
    assert dumps_json(value).index('"a"') < dumps_json(value).index('"z"')


def test_unserializable_context_is_auditable_block(context_factory):
    context = context_factory(metadata={"open_points": [], "bad": {"set-value"}})

    result = QuintaOrdemGate.default().evaluate(context)

    assert result.status == DecisionStatus.BLOCKED
    assert result.confidence == 0.0
    assert any(finding.code == "UNSERIALIZABLE_CONTEXT" for finding in result.findings)
