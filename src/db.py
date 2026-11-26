"""Database module compatibility shim forwarding to src.core.database.db."""

from __future__ import annotations

from src.core.database.db import *
import src.core.database.db as _db_impl

# Re-export module-level attributes
db_manager = _db_impl.db_manager
