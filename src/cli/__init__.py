"""TraceLens CLI package."""

from __future__ import annotations

import sys
from importlib import import_module

_module = import_module(".cli", __name__)
sys.modules[__name__] = _module


