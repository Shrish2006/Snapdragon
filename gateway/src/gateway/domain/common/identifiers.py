"""Validated identifier types.

`helmet_firmware.ino` (the integrated firmware) is currently a stub with no
device identification implemented at all — no MAC address, no serial, no
config-assigned ID. There is therefore no existing format to derive
`HelmetId` from. The pattern below is a conservative, generic charset (safe
to use as an MQTT topic segment, a URL path segment, and a dict key) chosen
so the gateway has a contract firmware can target once it adds device
identification — it is not a reverse-engineered existing format.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import StringConstraints

from gateway.domain.common.errors import InvalidHelmetIdError

_HELMET_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

HelmetId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=_HELMET_ID_PATTERN.pattern,
    ),
]
"""A validated helmet identifier for use as a Pydantic field type."""


def parse_helmet_id(value: str) -> str:
    """Validate a raw string as a helmet id outside a Pydantic parsing
    context (e.g. extracting one from an MQTT topic in the Phase 2/3
    ingestion adapter).

    Raises `InvalidHelmetIdError` — a domain-native exception — instead of
    `pydantic.ValidationError`, which non-Pydantic callers shouldn't have to
    depend on.
    """
    if not _HELMET_ID_PATTERN.match(value):
        raise InvalidHelmetIdError(value)
    return value
