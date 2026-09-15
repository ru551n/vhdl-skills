"""Package smoke tests."""

import vhdl_tools.wave


def test_version() -> None:
    assert vhdl_tools.wave.__version__ == "0.1.0"
