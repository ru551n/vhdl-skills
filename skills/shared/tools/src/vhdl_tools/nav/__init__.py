"""vhdl-tools nav: exact VHDL lookups through vhdl_ls, the VHDL language server."""

from __future__ import annotations


class NavError(Exception):
    """A lookup failed in a way the user can act on; the message says how."""
