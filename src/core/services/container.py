"""Unified service container and application facade for TraceLens."""

from __future__ import annotations

from typing import Any

from src.config.logging_config import get_logger
from src.core.database import db as db_module
from src.core.editor import editor as editor_module
from src.core.extractor import extractor as extractor_module
from src.core.reports import report as report_module
from src.core.risk import risk_analyzer as risk_module

from src.core.services.analytics_service import AnalyticsService
from src.core.services.editor_service import MetadataEditorService
from src.core.services.extraction_service import ExtractionService
from src.core.services.history_service import HistoryService
from src.core.services.report_service import ReportService
from src.core.services.risk_service import RiskAnalysisService

logger = get_logger("core.services.container")


class ServiceContainer:
    """Dependency injection container and facade for all TraceLens services."""

    def __init__(
        self,
        db_path: str | None = None,
        database: db_module.MetadataDatabase | None = None,
        extractor: extractor_module.MetadataExtractor | None = None,
        analyzer: risk_module.PrivacyForensicAnalyzer | None = None,
        editor: editor_module.MetadataEditor | None = None,
        reporter: report_module.MetadataReporter | None = None,
    ) -> None:
        logger.debug("Initializing ServiceContainer (custom db_path=%s)", db_path)

        # Core domain / infrastructure components
        if database is not None:
            self.database = database
        elif db_path is not None:
            self.database = db_module.MetadataDatabase(db_path=db_path)
        else:
            self.database = db_module.db_manager

        self.extractor = extractor or extractor_module.MetadataExtractor(db_client=self.database)
        self.analyzer = analyzer or risk_module.analyzer
        self.editor_core = editor or editor_module.MetadataEditor(db_client=self.database)
        self.reporter_core = reporter or report_module.reporter

        # Application services
        self.extraction = ExtractionService(extractor=self.extractor, database=self.database)
        self.risk = RiskAnalysisService(analyzer=self.analyzer)
        self.editor = MetadataEditorService(editor=self.editor_core, database=self.database)
        self.history = HistoryService(database=self.database)
        self.report = ReportService(reporter=self.reporter_core)
        self.analytics = AnalyticsService(database=self.database, analyzer=self.analyzer)

    # ------------------------------------------------------------------
    # High-level Facade Workflows
    # ------------------------------------------------------------------
    def process_file_pipeline(
        self,
        file_path: str,
        persist: bool = True,
        analyze_risk: bool = True,
    ) -> dict[str, Any]:
        """Execute complete extraction + risk assessment pipeline for a single file."""
        extraction_res = self.extraction.extract_file(file_path, persist=persist)

        risk_assessment = None
        if analyze_risk and extraction_res.success:
            risk_assessment = self.risk.analyze_metadata(
                metadata=extraction_res.metadata,
                file_path=file_path,
                fallback_timestamps={
                    "Extracted At": extraction_res.extracted_at,
                    "Modified On": extraction_res.modified_on,
                },
            )

        return {
            "extraction": extraction_res,
            "risk": risk_assessment,
            "success": extraction_res.success,
        }

    def sanitize_file(self, file_path: str, backup: bool = True) -> tuple[bool, str]:
        """Strip sensitive metadata tags from a physical file."""
        return self.editor.strip_sensitive_metadata(file_path=file_path, backup=backup)


# Default shared service container
_default_container: ServiceContainer | None = None


def get_service_container(db_path: str | None = None) -> ServiceContainer:
    """Retrieve the global service container singleton or initialize one with custom parameters."""
    global _default_container
    if db_path is not None:
        return ServiceContainer(db_path=db_path)
    if _default_container is None:
        _default_container = ServiceContainer()
    return _default_container


def set_service_container(container: ServiceContainer | None) -> None:
    """Set or override the global service container singleton."""
    global _default_container
    _default_container = container


def reset_service_container() -> None:
    """Reset the global service container singleton to None."""
    global _default_container
    _default_container = None
