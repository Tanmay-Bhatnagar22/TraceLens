import pandas as pd
import json
import xml.etree.ElementTree as ET
from tkinter import filedialog, messagebox
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.units import inch
import os
import sys
import tempfile


class MetadataReporter:
    """Object-oriented metadata report generator with PDF/JSON/XML/CSV/Excel export."""

    def __init__(self):
        pass

    @staticmethod
    def resource_path(relative_path):
        """Get absolute path to resource, works for dev and for PyInstaller
        
        Args:
            relative_path (str): Relative path to the resource.
            
        Returns:
            str: Absolute path to the resource file.
        """
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    @staticmethod
    def get_asset_path(filename):
        """Get path to asset file
        
        Args:
            filename (str): Name of the asset file (e.g., 'Metadata.png').
            
        Returns:
            str: Absolute path to the asset file.
        """
        candidate = MetadataReporter.resource_path(os.path.join("assets", filename))
        if os.path.exists(candidate):
            return candidate
        return MetadataReporter.resource_path(filename)

    def generate_report_text(self, extracted_metadata, file_path, risk_analysis=None, batch_summary=None):
        """Build plain-text report from metadata and file info.
        
        Creates a formatted text report with file headers and metadata key-value pairs.
        
        Args:
            extracted_metadata (dict): Dictionary of extracted metadata.
            file_path (str): Path to the source file.
            
        Returns:
            str: Plain-text report content.
        """
        try:
            file_name = os.path.basename(file_path) if file_path else ""
            try:
                size_bytes = os.path.getsize(file_path) if file_path and os.path.exists(file_path) else 0
            except Exception:
                size_bytes = 0

            def _fmt_size(n):
                for unit in ["B", "KB", "MB", "GB", "TB"]:
                    if n < 1024.0 or unit == "TB":
                        return f"{n:.2f} {unit}" if unit != "B" else f"{int(n)} {unit}"
                    n /= 1024.0

            size_fmt = _fmt_size(float(size_bytes))
            _, ext = os.path.splitext(file_name)
            ftype = (ext[1:] if ext.startswith(".") else ext) or "unknown"

            extracted_at_h = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                modified_on_h = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime("%Y-%m-%d %H:%M:%S") if file_path and os.path.exists(file_path) else extracted_at_h
            except Exception:
                modified_on_h = extracted_at_h

            header_lines = [
                f"File Name: {file_name}",
                f"File Size: {size_fmt}",
                f"File Type: {ftype}",
                f"Extracted At: {extracted_at_h}",
                f"Modified On: {modified_on_h}",
            ]

            metadata_lines = []
            if isinstance(extracted_metadata, dict):
                for k, v in extracted_metadata.items():
                    try:
                        metadata_lines.append(f"{str(k)}: {json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)}")
                    except Exception:
                        metadata_lines.append(f"{str(k)}: {str(v)}")
            elif extracted_metadata:
                metadata_lines.append(str(extracted_metadata))

            extra_sections = []
            if isinstance(risk_analysis, dict):
                risk_lines = [
                    "Privacy Risk Analysis",
                    f"Risk Level: {risk_analysis.get('risk_level', 'N/A')}",
                    f"Risk Score: {risk_analysis.get('risk_score', 'N/A')}/100",
                    f"Timeline Events: {risk_analysis.get('event_count', len(risk_analysis.get('timeline', [])))}",
                ]
                reasons = risk_analysis.get("reasons", []) or []
                if reasons:
                    risk_lines.append("Risk Reasons:")
                    for reason in reasons:
                        risk_lines.append(f"- {reason}")

                timeline = risk_analysis.get("timeline", []) or []
                if timeline:
                    risk_lines.append("Forensic Timeline:")
                    for event in timeline:
                        risk_lines.append(f"- {event.get('event', 'Event')}: {event.get('timestamp', '')}")

                extra_sections.append("\n".join(risk_lines))

            if isinstance(batch_summary, dict):
                counts = batch_summary.get("risk_counts", {})
                batch_lines = [
                    "Batch Risk Summary",
                    f"Total Files: {batch_summary.get('total_files', 0)}",
                    f"LOW: {counts.get('LOW', 0)}",
                    f"MEDIUM: {counts.get('MEDIUM', 0)}",
                    f"HIGH: {counts.get('HIGH', 0)}",
                ]
                folders = batch_summary.get("folders", {})
                if folders:
                    batch_lines.append("Folder Breakdown:")
                    for folder, values in folders.items():
                        batch_lines.append(
                            f"- {folder}: total={values.get('total', 0)}, low={values.get('LOW', 0)}, medium={values.get('MEDIUM', 0)}, high={values.get('HIGH', 0)}"
                        )
                extra_sections.append("\n".join(batch_lines))

            metadata_text = "\n\n".join(["\n".join(header_lines + [""] + metadata_lines)] + extra_sections)
            return metadata_text
        except Exception:
            return "Metadata Report\n(No details available)"

    def create_pdf_report_from_text(self, metadata_text, file_path):
        """Build PDF document with title, metadata table, timestamp using ReportLab.
        
        Args:
            metadata_text (str): Plain-text report content.
            file_path (str): Output PDF file path.
            
        Returns:
            None: PDF file is created at file_path.
        """
        doc = SimpleDocTemplate(file_path, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        img_path = self.get_asset_path('Metadata.png')
        if os.path.exists(img_path):
            story.append(Image(img_path, width=120, height=60))
            story.append(Spacer(1, 12))

        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=1
        )
        story.append(Paragraph("TraceLens Report", title_style))
        story.append(Spacer(1, 20))

        date_style = ParagraphStyle(
            'DateStyle',
            parent=styles['Normal'],
            fontSize=10,
            alignment=1
        )
        story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", date_style))
        story.append(Spacer(1, 20))

        section_heading_style = ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading2'],
            fontSize=12,
            spaceAfter=8,
            spaceBefore=8,
            alignment=0
        )

        def _build_section_table(rows):
            table_data = [['Property', 'Value']] + rows
            table = Table(table_data, colWidths=[2.5 * inch, 4 * inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
            ]))
            return table

        lines = (metadata_text or '').split('\n')
        metadata_rows = []
        privacy_rows = []
        timeline_rows = []
        section = 'metadata'

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            normalized_heading = line.rstrip(':').strip().lower()

            if normalized_heading == 'privacy risk analysis':
                section = 'privacy'
                continue
            if normalized_heading == 'forensic timeline':
                section = 'timeline'
                continue

            target_rows = metadata_rows
            if section == 'privacy':
                target_rows = privacy_rows
            elif section == 'timeline':
                target_rows = timeline_rows

            if ':' in line:
                key, value = line.split(':', 1)
                target_rows.append([key.strip(), value.strip()])
            elif line.startswith('-'):
                target_rows.append(['Note', line.lstrip('-').strip()])
            else:
                target_rows.append(['Note', line])

        if not metadata_rows:
            metadata_rows.append(['Info', 'No metadata details found'])
        if not privacy_rows:
            privacy_rows.append(['Info', 'No privacy risk analysis found'])
        if not timeline_rows:
            timeline_rows.append(['Info', 'No forensic timeline events found'])

        story.append(Paragraph('Metadata Details', section_heading_style))
        story.append(_build_section_table(metadata_rows))
        story.append(Spacer(1, 14))

        story.append(Paragraph('Privacy Risk Analysis', section_heading_style))
        story.append(_build_section_table(privacy_rows))
        story.append(Spacer(1, 14))

        story.append(Paragraph('Forensic Timeline', section_heading_style))
        story.append(_build_section_table(timeline_rows))

        doc.build(story)

    def print_metadata_report(self, metadata_text):
        """Create a temporary PDF from text and send to default printer (Windows).
        
        Args:
            metadata_text (str): Plain-text report content.
            
        Returns:
            None: Shows success/error messagebox.
        """
        if not metadata_text or metadata_text.strip() == "":
            messagebox.showwarning("No Data", "There is no metadata to print.")
            return

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp_path = tmp.name
            self.create_pdf_report_from_text(metadata_text, tmp_path)

            if os.name == "nt":
                try:
                    os.startfile(tmp_path, "print")
                    messagebox.showinfo("Print", "Report sent to the default printer.")
                except Exception as e:
                    messagebox.showerror("Print Error", f"Failed to print: {str(e)}")
            else:
                messagebox.showinfo("Print", "Automatic printing is only supported on Windows.")
        except Exception as e:
            messagebox.showerror("Print Error", f"Failed to prepare print: {str(e)}")

    def save_metadata(self, metadata_text):
        """Convert metadata text to formatted PDF report with header and table layout.
        
        Args:
            metadata_text (str): Plain-text report content.
            
        Returns:
            None: Shows file dialog for user to save PDF file.
        """
        if not metadata_text or metadata_text.strip() == "":
            messagebox.showwarning("No Data", "There is no metadata to save.")
            return

        default_name = f"metadata_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=default_name,
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )

        if file_path:
            try:
                self.create_pdf_report_from_text(metadata_text, file_path)
                messagebox.showinfo("Save Successful", f"Metadata report saved as PDF: {file_path}")
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save PDF report: {str(e)}")

    def create_pdf_from_dataframe(self, df, file_path):
        """Generate PDF report from metadata DataFrame with record count and table display.
        
        Args:
            df (pd.DataFrame): DataFrame with metadata records.
            file_path (str): Output PDF file path.
            
        Returns:
            None: PDF file is created at file_path.
        """
        doc = SimpleDocTemplate(file_path, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        img_path = self.get_asset_path('Metadata.png')
        if os.path.exists(img_path):
            story.append(Image(img_path, width=120, height=60))
            story.append(Spacer(1, 12))

        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=30,
            alignment=1
        )
        story.append(Paragraph("Metadata Database Export", title_style))
        story.append(Spacer(1, 20))

        summary_text = f"Total Records: {len(df)}<br/>Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        story.append(Paragraph(summary_text, styles['Normal']))
        story.append(Spacer(1, 20))

        display_columns = ['ID', 'File Name', 'File Size', 'File Type', 'Extracted At']
        table_data = [display_columns]

        for _, row in df.iterrows():
            table_row = [
                str(row['ID']),
                str(row['File Name'])[:30] + '...' if len(str(row['File Name'])) > 30 else str(row['File Name']),
                str(row['File Size']),
                str(row['File Type']),
                str(row['Extracted At'])[:16]
            ]
            table_data.append(table_row)

        table = Table(table_data, colWidths=[0.5*inch, 2*inch, 0.8*inch, 0.7*inch, 1.2*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))

        story.append(table)
        doc.build(story)

    def export_to_pdf(self, df):
        """Convert DataFrame to formatted PDF table with summary statistics.
        
        Args:
            df (pd.DataFrame): DataFrame with metadata records.
            
        Returns:
            None: Shows file dialog for user to save PDF file.
        """
        if df.empty:
            messagebox.showwarning("No Data", "There is no metadata to export.")
            return

        default_name = f"metadata_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=default_name,
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )

        if file_path:
            try:
                self.create_pdf_from_dataframe(df, file_path)
                messagebox.showinfo("Export Successful", f"Metadata exported to {file_path}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export PDF: {str(e)}")

    def export_to_json(self, df):
        """Serialize DataFrame to JSON (orient=records) with user file dialog.
        
        Args:
            df (pd.DataFrame): DataFrame with metadata records.
            
        Returns:
            None: Shows file dialog for user to save JSON file.
        """
        if df.empty:
            messagebox.showwarning("No Data", "There is no metadata to export.")
            return

        default_name = f"metadata_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfile=default_name,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )

        if file_path:
            try:
                df.to_json(file_path, orient='records', indent=4)
                messagebox.showinfo("Export Successful", f"Metadata exported to {file_path}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export JSON: {str(e)}")

    def export_to_xml(self, df):
        """Convert DataFrame to XML with record elements and column-based subelements.
        
        Args:
            df (pd.DataFrame): DataFrame with metadata records.
            
        Returns:
            None: Shows file dialog for user to save XML file.
        """
        if df.empty:
            messagebox.showwarning("No Data", "There is no metadata to export.")
            return

        default_name = f"metadata_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xml",
            initialfile=default_name,
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")]
        )

        if file_path:
            try:
                root = ET.Element("metadata_records")

                for index, row in df.iterrows():
                    record = ET.SubElement(root, "record")
                    for col in df.columns:
                        element = ET.SubElement(record, col.lower().replace(' ', '_'))
                        element.text = str(row[col]) if pd.notna(row[col]) else ""

                tree = ET.ElementTree(root)
                tree.write(file_path, encoding='utf-8', xml_declaration=True)
                messagebox.showinfo("Export Successful", f"Metadata exported to {file_path}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export XML: {str(e)}")

    def export_to_excel(self, df):
        """Write DataFrame to Excel (.xlsx) using openpyxl engine with 'Metadata' sheet.
        
        Args:
            df (pd.DataFrame): DataFrame with metadata records.
            
        Returns:
            None: Shows file dialog for user to save Excel file.
        """
        if df.empty:
            messagebox.showwarning("No Data", "There is no metadata to export.")
            return

        default_name = f"metadata_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            initialfile=default_name,
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
        )

        if file_path:
            try:
                with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name='Metadata', index=False)
                messagebox.showinfo("Export Successful", f"Metadata exported to {file_path}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export Excel: {str(e)}")

    def export_to_csv(self, data):
        """Convert tuple data to DataFrame and save as CSV with standard headers.
        
        Args:
            data (list): List of metadata record tuples.
            
        Returns:
            None: Shows file dialog for user to save CSV file.
        """
        if not data:
            messagebox.showwarning("No Data", "There is no metadata to export.")
            return

        default_name = f"metadata_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if file_path:
            try:
                df = pd.DataFrame(
                    data,
                    columns=[
                        'ID',
                        'File Path',
                        'File Name',
                        'File Size',
                        'File Type',
                        'Extracted At',
                        'Modified On',
                        'Full Metadata',
                    ],
                )
                df.to_csv(file_path, index=False)
                messagebox.showinfo("Export Successful", f"Metadata exported to {file_path}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export CSV: {str(e)}")


_reporter = MetadataReporter()


# Module-level wrapper functions for backward compatibility
def resource_path(relative_path):
    """Wrapper: Get absolute path to resource, works for dev and for PyInstaller"""
    return _reporter.resource_path(relative_path)


def get_asset_path(filename):
    """Wrapper: Get path to asset file"""
    return _reporter.get_asset_path(filename)


def generate_report_text(extracted_metadata, file_path, risk_analysis=None, batch_summary=None):
    """Wrapper: Build plain-text report from metadata and file info."""
    return _reporter.generate_report_text(extracted_metadata, file_path, risk_analysis=risk_analysis, batch_summary=batch_summary)


def print_metadata_report(metadata_text):
    """Wrapper: Create a temporary PDF and send to default printer."""
    return _reporter.print_metadata_report(metadata_text)


def save_metadata(metadata_text):
    """Wrapper: Convert metadata text to formatted PDF report."""
    return _reporter.save_metadata(metadata_text)


def create_pdf_report_from_text(metadata_text, file_path):
    """Wrapper: Build PDF document with title, metadata table, and timestamp."""
    return _reporter.create_pdf_report_from_text(metadata_text, file_path)


def export_to_pdf(df):
    """Wrapper: Convert DataFrame to formatted PDF table."""
    return _reporter.export_to_pdf(df)


def create_pdf_from_dataframe(df, file_path):
    """Wrapper: Generate PDF report from metadata DataFrame."""
    return _reporter.create_pdf_from_dataframe(df, file_path)


def export_to_json(df):
    """Wrapper: Serialize DataFrame to JSON."""
    return _reporter.export_to_json(df)


def export_to_xml(df):
    """Wrapper: Convert DataFrame to XML."""
    return _reporter.export_to_xml(df)


def export_to_excel(df):
    """Wrapper: Write DataFrame to Excel."""
    return _reporter.export_to_excel(df)


def export_to_csv(data):
    """Wrapper: Convert tuple data to DataFrame and save as CSV."""
    return _reporter.export_to_csv(data)
