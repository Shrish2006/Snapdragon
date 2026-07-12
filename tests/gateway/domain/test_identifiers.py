"""Tests for `gateway.domain.common.identifiers`."""

import pytest
from pydantic import BaseModel, ValidationError

from gateway.domain.common.errors import InvalidHelmetIdError
from gateway.domain.common.identifiers import HelmetId, parse_helmet_id


class _Holder(BaseModel):
    helmet_id: HelmetId


@pytest.mark.parametrize("value", ["HLM-0007", "a", "A" * 64, "helmet_1"])
def test_helmet_id_accepts_valid_values(value: str) -> None:
    assert _Holder(helmet_id=value).helmet_id == value


@pytest.mark.parametrize(
    "value", ["", "A" * 65, "has space", "bad/slash", "-leading-dash"]
)
def test_helmet_id_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValidationError):
        _Holder(helmet_id=value)


def test_parse_helmet_id_returns_value_when_valid() -> None:
    assert parse_helmet_id("HLM-0007") == "HLM-0007"


def test_parse_helmet_id_raises_domain_error_when_invalid() -> None:
    with pytest.raises(InvalidHelmetIdError):
        parse_helmet_id("bad/slash")
