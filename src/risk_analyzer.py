"""Risk analyzer module compatibility shim forwarding to src.core.risk.risk_analyzer."""

from __future__ import annotations

from src.core.risk.risk_analyzer import *
import src.core.risk.risk_analyzer as _risk_impl

_analyzer = _risk_impl._analyzer
analyzer = _risk_impl.analyzer
