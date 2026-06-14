"""Shared exception type.

Lives in its own module so both ``composer`` and ``schema`` can raise it without
creating an import cycle.
"""

from __future__ import annotations


class InvalidSelection(ValueError):
    """Raised when a stack selection, schema, or add-on set is invalid."""
