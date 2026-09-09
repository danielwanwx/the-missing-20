"""Exercise the installed SDK's actual structured-output schema conversion."""

import pytest
from jsonschema import Draft7Validator
from strands.tools import convert_pydantic_to_tool_spec

from the_missing_20.agents.role_delegation import SourceObservation, SpecialistFinding


@pytest.mark.parametrize("value", [80, 8.0, "LOT-B", False, None])
def test_wire_schema_accepts_every_supported_source_scalar(value):
    schema = convert_pydantic_to_tool_spec(SpecialistFinding)["inputSchema"]["json"]
    observation = schema["properties"]["observations"]["items"]
    candidate = {"source": "read_erp_evidence", "pointer": "/quantity", "value": value}
    Draft7Validator(observation).validate(candidate)


@pytest.mark.parametrize("value", [{"quantity": 80}, [80]])
def test_wire_schema_does_not_admit_a_whole_record_as_a_scalar(value):
    schema = convert_pydantic_to_tool_spec(SpecialistFinding)["inputSchema"]["json"]
    observation = schema["properties"]["observations"]["items"]
    candidate = {"source": "read_erp_evidence", "pointer": "/quantity", "value": value}
    assert not Draft7Validator(observation).is_valid(candidate)


def test_source_aliases_are_rejected_at_the_provider_schema_boundary():
    schema = convert_pydantic_to_tool_spec(SpecialistFinding)["inputSchema"]["json"]
    observation = schema["properties"]["observations"]["items"]
    assert not Draft7Validator(observation).is_valid(
        {"source": "ERP", "pointer": "/quantity", "value": 8}
    )
    with pytest.raises(ValueError):
        SourceObservation(source="ERP", pointer="/quantity", value=8)
