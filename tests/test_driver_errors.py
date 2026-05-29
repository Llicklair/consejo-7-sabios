"""Regression tests for item 6 of the 20260527-183832 council plan.

The driver boundary must emit structured, human-readable errors with
machine-readable attributes — not opaque RuntimeError strings — so callers
can distinguish failure modes without string matching.
"""

from __future__ import annotations

from consejo.driver_errors import (
    DriverCLINotFoundError,
    DriverEmptyResultError,
    DriverError,
    DriverInvalidResponseError,
    DriverProcessError,
    DriverTimeoutError,
)


def test_all_driver_errors_subclass_driver_error() -> None:
    for cls in (
        DriverCLINotFoundError,
        DriverTimeoutError,
        DriverProcessError,
        DriverInvalidResponseError,
        DriverEmptyResultError,
    ):
        assert issubclass(cls, DriverError), (
            f"{cls.__name__} must subclass DriverError so callers can "
            f"catch the boundary uniformly."
        )


def test_timeout_error_exposes_seconds() -> None:
    err = DriverTimeoutError(timeout_s=42.5)
    assert err.timeout_s == 42.5
    assert "42.5" in str(err)


def test_process_error_exposes_diagnostics() -> None:
    err = DriverProcessError(
        returncode=137,
        stderr_head="OOM killed",
        stdout_head="partial output",
        stderr_len=10,
        stdout_len=15,
    )
    assert err.returncode == 137
    assert err.stderr_head == "OOM killed"
    assert err.stdout_head == "partial output"
    msg = str(err)
    assert "returncode=137" in msg
    assert "OOM killed" in msg
    assert "partial output" in msg


def test_invalid_response_error_distinguishes_wrapper_vs_inner() -> None:
    wrapper_err = DriverInvalidResponseError(response_head="oops", kind="wrapper")
    inner_err = DriverInvalidResponseError(response_head="oops", kind="inner")
    assert wrapper_err.kind == "wrapper"
    assert inner_err.kind == "inner"
    assert "claude CLI returned non-JSON" in str(wrapper_err)
    assert "sage returned non-JSON inner text" in str(inner_err)


def test_empty_result_error_preserves_wrapper() -> None:
    wrapper = {"type": "result", "num_turns": 5, "result": ""}
    err = DriverEmptyResultError(wrapper=wrapper)
    assert err.wrapper is wrapper
    assert "empty result" in str(err)


def test_cli_not_found_error_has_install_hint() -> None:
    err = DriverCLINotFoundError()
    msg = str(err)
    assert "claude" in msg.lower()
    assert "Install Claude Code" in msg
