"""Boundary tests for the `signed=` diagnostic in `DriverProcessError`.

`DriverProcessError` converts an unsigned 32-bit `returncode` (as some
platforms/subprocess wrappers report it) to its signed int32
interpretation for the `signed=` field in the message. The conversion
uses `returncode - 2**32 if returncode > 2**31 else returncode`, which
is off by one at the exact int32 boundary: `2**31` (0x80000000) is
itself the most negative signed int32 value (-2147483648), but
`returncode > 2**31` is False for `returncode == 2**31`, so it is left
unconverted.
"""

from __future__ import annotations

from consejo.driver_errors import DriverProcessError


def test_returncode_int32_boundary_is_converted_to_negative() -> None:
    # 2**31 == 0x80000000 is INT32_MIN as a signed 32-bit value.
    err = DriverProcessError(
        returncode=2**31,
        stderr_head="",
        stdout_head="",
        stderr_len=0,
        stdout_len=0,
    )
    assert "signed=-2147483648" in str(err)


def test_returncode_just_below_boundary_is_unconverted() -> None:
    # 2**31 - 1 == INT32_MAX: still positive as signed, no conversion.
    err = DriverProcessError(
        returncode=2**31 - 1,
        stderr_head="",
        stdout_head="",
        stderr_len=0,
        stdout_len=0,
    )
    assert "signed=2147483647" in str(err)


def test_returncode_all_ones_32bit_is_minus_one() -> None:
    # 0xFFFFFFFF is -1 as a signed 32-bit value; already correct today.
    err = DriverProcessError(
        returncode=0xFFFFFFFF,
        stderr_head="",
        stdout_head="",
        stderr_len=0,
        stdout_len=0,
    )
    assert "signed=-1" in str(err)
