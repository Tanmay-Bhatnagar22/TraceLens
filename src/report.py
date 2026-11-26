"""Report module compatibility shim forwarding to src.core.reports.report."""

from __future__ import annotations

from src.core.reports.report import *
import src.core.reports.report as _report_impl

_reporter = _report_impl._reporter
reporter = _report_impl.reporter
