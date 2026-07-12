"""Tests for `gateway.logging_config`.

Two independent concerns, tested independently:
- `_JSONFormatter`'s output shape — unit-tested directly against a crafted
  `LogRecord`, with no logging pipeline involved, so pytest's own log
  capturing (which attaches its own handlers to the root logger — see
  `reset_logging_state` below) cannot interfere.
- `setup_logging()`'s wiring/idempotency — tested through the root
  logger, resetting the module's own `_configured` flag (not
  `root.handlers`, which pytest's log-capture plugin populates on every
  test regardless of what this module does).
"""

from __future__ import annotations

import json
import logging
import sys

import gateway.logging_config as logging_config
import pytest
from gateway.logging_config import _JSONFormatter, setup_logging


def _make_record(
    level: int = logging.INFO, msg: str = "hello", args: tuple = (), exc_info=None
) -> logging.LogRecord:
    return logging.LogRecord(
        name="test.logger",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=exc_info,
    )


# -- _JSONFormatter -------------------------------------------------------


def test_json_formatter_produces_the_documented_shape() -> None:
    record = _make_record(msg="hello %s", args=("world",))
    line = json.loads(_JSONFormatter().format(record))

    assert line["level"] == "INFO"
    assert line["logger"] == "test.logger"
    assert line["msg"] == "hello world"
    assert "ts" in line
    assert "exc" not in line


def test_json_formatter_includes_exc_field_for_exception_records() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = _make_record(
            level=logging.ERROR, msg="failed", exc_info=sys.exc_info()
        )

    line = json.loads(_JSONFormatter().format(record))
    assert "ValueError: boom" in line["exc"]


# -- setup_logging ----------------------------------------------------------


@pytest.fixture
def reset_logging_state():
    """Resets `setup_logging`'s own idempotency flag (not `root.handlers`,
    which pytest's log-capture plugin repopulates every test regardless
    of anything this module does) and removes any handler this test's
    `setup_logging()` call adds, so it doesn't leak into later tests."""
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    level_before = root.level
    original_configured = logging_config._configured
    logging_config._configured = False

    yield

    logging_config._configured = original_configured
    for handler in list(root.handlers):
        if handler not in handlers_before:
            root.removeHandler(handler)
    root.setLevel(level_before)


def _json_handlers() -> list[logging.Handler]:
    return [
        h
        for h in logging.getLogger().handlers
        if isinstance(h.formatter, _JSONFormatter)
    ]


def test_setup_logging_attaches_a_json_formatted_stream_handler(
    reset_logging_state,
) -> None:
    before = len(_json_handlers())

    setup_logging(level="INFO", file_path="")

    handlers = _json_handlers()
    assert len(handlers) == before + 1
    assert isinstance(handlers[-1], logging.StreamHandler)
    assert logging.getLogger().level == logging.INFO


def test_setup_logging_is_idempotent(reset_logging_state) -> None:
    setup_logging(level="INFO", file_path="")
    count_after_first_call = len(_json_handlers())

    setup_logging(level="DEBUG", file_path="")  # must be a no-op

    assert len(_json_handlers()) == count_after_first_call
    assert logging.getLogger().level == logging.INFO  # unchanged by the second call


def test_setup_logging_writes_json_to_a_file_when_given_a_path(
    reset_logging_state, tmp_path
) -> None:
    log_file = tmp_path / "gateway.log"
    setup_logging(level="INFO", file_path=str(log_file))
    logging.getLogger("test.logger").info("to file")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert log_file.exists()
    line = json.loads(log_file.read_text().strip().splitlines()[-1])
    assert line["msg"] == "to file"
