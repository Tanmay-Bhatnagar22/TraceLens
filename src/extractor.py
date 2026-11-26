"""Extractor module compatibility shim forwarding to src.core.extractor.extractor."""

from __future__ import annotations

from src.core.extractor.extractor import *
import src.core.extractor.extractor as _extractor_impl

_extractor = _extractor_impl._extractor
