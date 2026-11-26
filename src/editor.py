"""Editor module compatibility shim forwarding to src.core.editor.editor."""

from __future__ import annotations

from src.core.editor.editor import *
import src.core.editor.editor as _editor_impl

_editor = _editor_impl._editor
