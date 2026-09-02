"""Report service orchestrating document generation, PDF creation, and multi-format exports."""

from __future__ import annotations

import os
from typing import Any

import pandas as pd

from src.config.logging_config import get_logger
from src.core.reports import report as report_module
from src.models.reports import ReportConfig, ReportResult

logger = get_logger("core.services.report")


class ReportService:
    """Application service for generating formatted reports and exporting data."""

    def __init__(
        self,
        reporter: report_module.MetadataReporter | None = None,
    ) -> None:
        self.reporter = reporter or report_module.reporter


    def generate_text_report(
        self,
        extracted_metadata: dict[str, Any],
        file_path: str,
        risk_analysis: dict[str, Any] | None = None,
        batch_summary: dict[str, Any] | None = None,
    ) -> str:
        """Generate a structured plain-text report from metadata, risk analysis, and batch details."""
        return self.reporter.generate_report_text(
            extracted_metadata=extracted_metadata,
            file_path=file_path,
            risk_analysis=risk_analysis,
            batch_summary=batch_summary,
        )

    def generate_pdf_report(
        self,
        extracted_metadata: dict[str, Any],
        file_path: str,
        output_path: str,
        risk_analysis: dict[str, Any] | None = None,
        batch_summary: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """Generate a professionally-formatted PDF report.

        Args:
            extracted_metadata: Dictionary of extracted metadata.
            file_path: Source file path.
            output_path: Target destination for the generated PDF.
            risk_analysis: Optional privacy and forensic risk assessment.
            batch_summary: Optional batch execution summary.

        Returns:
            tuple: (success, message_or_error)
        """
        try:
            report_text = self.generate_text_report(
                extracted_metadata=extracted_metadata,
                file_path=file_path,
                risk_analysis=risk_analysis,
                batch_summary=batch_summary,
            )
            self.reporter.create_pdf_report_from_text(report_text, output_path)
            return True, f"PDF report saved to {output_path}"
        except Exception as e:
            logger.error("Failed to generate PDF report: %s", e)
            return False, f"Failed to generate PDF report: {e}"

    def export_metadata(
        self,
        extracted_metadata: dict[str, Any],
        file_path: str,
        format_type: str,
        output_path: str | None = None,
    ) -> tuple[bool, str]:
        """Export extracted metadata to a specific file format (JSON, XML, CSV, TXT, PDF).

        Args:
            extracted_metadata: Metadata dictionary to export.
            file_path: Original file path.
            format_type: One of 'json', 'xml', 'csv', 'txt', 'pdf'.
            output_path: Optional explicit output destination.

        Returns:
            tuple: (success, message_or_path)
        """
        fmt = format_type.lower().strip()
        if not output_path:
            base, _ = os.path.splitext(file_path if file_path else "metadata_export")
            ext_map = {"json": ".json", "xml": ".xml", "csv": ".csv", "txt": ".txt", "pdf": ".pdf"}
            output_path = f"{base}_report{ext_map.get(fmt, '.txt')}"

        try:
            if fmt == "json":
                return self.reporter.export_to_json(extracted_metadata, output_path)
            elif fmt == "xml":
                return self.reporter.export_to_xml(extracted_metadata, output_path)
            elif fmt == "csv":
                return self.reporter.export_to_csv(extracted_metadata, output_path)
            elif fmt == "pdf":
                return self.generate_pdf_report(extracted_metadata, file_path, output_path)
            elif fmt in ("txt", "text"):
                text_content = self.generate_text_report(extracted_metadata, file_path)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(text_content)
                return True, f"Text report saved to {output_path}"
            else:
                return False, f"Unsupported export format: {format_type}"
        except Exception as e:
            return False, f"Export failed: {e}"

    def export_records_dataframe(
        self,
        df: pd.DataFrame,
        format_type: str,
        output_path: str,
    ) -> tuple[bool, str]:
        """Export a pandas DataFrame of history records to CSV, Excel, JSON, XML, or PDF."""
        fmt = format_type.lower().strip()
        try:
            if fmt == "json":
                df.to_json(output_path, orient="records", indent=2)
                return True, f"Exported {len(df)} records to {output_path}"
            elif fmt == "csv":
                df.to_csv(output_path, index=False)
                return True, f"Exported {len(df)} records to {output_path}"
            elif fmt in ("excel", "xlsx"):
                with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
                    df.to_excel(writer, sheet_name="Metadata", index=False)
                return True, f"Exported {len(df)} records to {output_path}"
            elif fmt == "xml":
                import xml.etree.ElementTree as ET

                root = ET.Element("metadata_records")
                for _, row in df.iterrows():
                    record = ET.SubElement(root, "record")
                    for column in df.columns:
                        element = ET.SubElement(record, column.lower().replace(" ", "_"))
                        value = row[column]
                        element.text = "" if pd.isna(value) else str(value)
                ET.ElementTree(root).write(output_path, encoding="utf-8", xml_declaration=True)
                return True, f"Exported {len(df)} records to {output_path}"
            elif fmt == "pdf":
                if hasattr(self.reporter, "create_pdf_from_dataframe"):
                    self.reporter.create_pdf_from_dataframe(df, output_path)
                    return True, f"Exported {len(df)} records to {output_path}"
                else:
                    return False, "PDF export not supported on reporter."
            else:
                return False, f"Unsupported export format: {format_type}"
        except Exception as e:
            return False, f"Export failed: {e}"

    def create_report(
        self,
        config: ReportConfig,
        metadata: dict[str, Any],
        risk_analysis: dict[str, Any] | None = None,
    ) -> ReportResult:
        """Generate a report according to a ReportConfig model."""
        target_path = config.output_path
        if not target_path:
            base, _ = os.path.splitext(config.file_path if config.file_path else "report")
            target_path = f"{base}.{config.format.lower()}"

        success, msg = self.export_metadata(
            extracted_metadata=metadata,
            file_path=config.file_path,
            format_type=config.format,
            output_path=target_path,
        )

        size_bytes = 0
        if success and os.path.exists(target_path):
            try:
                size_bytes = os.path.getsize(target_path)
            except Exception:
                size_bytes = 0

        return ReportResult(
            success=success,
            output_path=target_path if success else "",
            format=config.format,
            message=msg,
            size_bytes=size_bytes,
        )
