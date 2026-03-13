# TraceLens: Intelligent Metadata Analysis & Privacy Inspection Toolkit

![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)
![Tests](https://img.shields.io/badge/tests-pytest-informational.svg)
![GUI](https://img.shields.io/badge/GUI-Tkinter-ff69b4.svg)
![Database](https://img.shields.io/badge/database-SQLite-003b57.svg)

TraceLens is a desktop application built with Python and Tkinter for extracting, editing, analyzing, and exporting file metadata. It includes a local SQLite history, report generation, and a privacy/forensic risk analysis workflow.

## Table of Contents

- [Key Features](#key-features)
- [Feature Breakdown](#feature-breakdown)
- [Supported File Handling](#supported-file-handling)
- [Project Structure](#project-structure)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Run the Application](#run-the-application)
- [How to Use](#how-to-use)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Database Schema](#database-schema)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Known Limitations](#known-limitations)
- [Contributing](#contributing)
- [License](#license)

## Key Features

- Metadata extraction from PDF, text-like files, and additional formats through Hachoir parsers.
- Metadata editing UI with field-level control and support for writing metadata back to files.
- SQLite-backed history with search, filtering, sorting, delete, and export operations.
- Report generation in PDF/text style and data export formats (JSON, XML, CSV, Excel, PDF).
- Privacy/forensic risk analyzer with rule-based scoring, reasons, and timeline visualization.
- Batch processing for multiple files with aggregate risk summary.
- Statistics dashboard with charts, filters, and metadata trend insights.

## Feature Breakdown

### 1) Metadata Extraction

- Choose a file from the Extractor tab and run extraction.
- Format-aware extraction strategy:
  - PDF files via `PyPDF2`.
  - Text-like files via UTF-8 read plus line count and size metadata.
  - Other supported media/document types via `hachoir` parser metadata.
- Results are displayed in the UI and persisted to the database.

### 2) Metadata Editing and Write-Back

- Editable metadata fields are shown in the Editor tab.
- Non-editable core fields are preserved (`File Name`, `File Size`, `File Type`, `Extracted At`, `Modified On`).
- Write-back support:
  - PDF metadata writing.
  - Image metadata writing (PNG text chunks, JPEG/TIFF EXIF with `piexif`).
  - Audio metadata writing (`mutagen`).
  - Text/structured text metadata header insertion.
  - DOCX core properties (`python-docx`).
  - Generic fallback writes to a companion `.meta.json` file.

### 3) History Management

- Stores every extracted/edited record in SQLite.
- Filter history by search term, file type, date range, and sort option.
- Supports refreshing, deleting selected records, deleting all records, and opening a record back into the main view.
- Exports filtered history via CSV, Excel, JSON, XML, or PDF.

### 4) Risk Analyzer

- Rule-based privacy and forensic analysis (`LOW`, `MEDIUM`, `HIGH`) based on metadata signals such as:
  - GPS/location markers
  - identity clues
  - device identifiers
  - editing software traces
  - embedded metadata block indicators
- Provides:
  - risk score
  - explanation/reasons
  - timeline extraction
  - anomaly detection insights
- Batch mode includes risk count summary per level and folder-level grouping.

### 5) Reports and Exports

- Generates a report text representation from extracted metadata and optional risk summary.
- Creates formatted PDF reports using ReportLab.
- Supports export dialogs for JSON, XML, CSV, Excel, and PDF.
- Preview tab supports save, print, and zoom operations.

### 6) Dashboard and Analytics

- Statistics dashboard with charts and summary cards.
- Filter by date range, file type, and search text.
- Includes trend visualization, size distribution, top files, and metadata completeness indicators.

## Supported File Handling

### Extraction

- PDF: `.pdf`
- Text-like: `.py`, `.txt`, `.cpp`, `.c`, `.java`, `.js`, `.json`, `.csv`, `.md`, `.html`, `.css`
- Additional formats based on available Hachoir parser support.

### Metadata Write-Back

- PDF: `.pdf`
- Image: `.jpg`, `.jpeg`, `.png`, `.tiff`, `.tif`, `.bmp`, `.gif`
- Audio: `.mp3`, `.wav`, `.flac`, `.m4a`, `.ogg`
- Text-like output embedding: `.txt`, `.json`, `.xml`, `.csv`, `.md`, `.log`, `.yaml`, `.yml`
- Office: `.docx` (explicit support), other office extensions may require additional libraries/implementation paths.
- Fallback for unsupported types: companion `.meta.json` file.

## Project Structure

```text
TraceLens/
├── src/
│   ├── main.py
│   ├── gui.py
│   ├── extractor.py
│   ├── editor.py
│   ├── db.py
│   ├── report.py
│   └── risk_analyzer.py
├── tests/
│   ├── test_main.py
│   ├── test_gui.py
│   ├── test_extractor.py
│   ├── test_editor.py
│   ├── test_db.py
│   ├── test_report.py
│   └── test_risk_analyzer.py
├── requirements.txt
├── LICENSE
└── README.md
```

## Architecture
```
                 ┌────────────────────────┐
                 │        USER GUI        │
                 │   (Tkinter Interface)  │
                 └──────────┬─────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐   ┌──────────────┐   ┌──────────────┐
│ File Loader   │   │ History UI   │   │ Dashboard UI │
│ (Select File) │   │ (Search DB)  │   │(Charts/Stats)|
└───────┬───────┘   └──────┬───────┘   └──────┬───────┘
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────────────────────────────────────────────┐
│                CORE PROCESSING LAYER                 │
└──────────────────────────────────────────────────────┘
        │                   │                   │
        ▼                   ▼                   ▼

┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ extractor.py  │   │ risk_analyzer │   │   db.py       │
│ Metadata Read │   │ Risk Scoring  │   │ SQLite Storage│
└───────┬───────┘   └──────┬────────┘   └──────┬────────┘
        │                  │                   │
        ▼                  ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  editor.py    │   │ report.py     │   │ analytics UI  │
│ Write-Back    │   │ Export System │   │ Charts/Stats  │
└───────────────┘   └───────────────┘   └───────────────┘
```

### src/main.py
- Entry point that launches `run_gui()`.

### src/gui.py
- Main application class: `MetadataAnalyzerApp`.
- Main tabs:
  - Extractor
  - Editor
  - History
  - Risk analyzer
  - Preview
- Also includes menu actions, batch process UI, and analytics dashboard.

### src/extractor.py
- `MetadataExtractor` handles extraction, validation, and optional persistence.
- Exposes both class-based API and module-level wrappers.

### src/editor.py
- `MetadataEditor` handles parse, validate, save, and write-back logic.
- Uses backup/rollback behavior during write operations where applicable.

### src/db.py
- `MetadataDatabase` encapsulates SQLite operations and export adapters.
- Central store file: `file_metadata.db`.

### src/report.py
- `MetadataReporter` provides report text generation and export functions.
- Includes PDF creation and print/save dialog integrations.

### src/risk_analyzer.py
- `PrivacyForensicAnalyzer` provides per-file and batch risk analysis.
- Generates risk score, reasons, timeline, and anomaly flags.

```
USER selects file
        │
        ▼
GUI → extractor.py
        │
        ▼
Metadata extracted
        │
        ├──► Saved to db.py
        │
        ├──► Sent to risk_analyzer.py
        │         │
        │         ▼
        │     Risk score + timeline
        │
        ├──► Displayed in GUI
        │
        ├──► Optional editing → editor.py
        │         │
        │         ▼
        │     Metadata written back
        │
        └──► Export request → report.py
                  │
                  ▼
           PDF / CSV / JSON / Excel
```

## Requirements

- Python 3.10 or later
  - This project uses modern type syntax such as `dict[str, Any]` and `X | None`.
- Tkinter available in your Python installation
- Recommended: virtual environment

All runtime dependencies are listed in `requirements.txt`.

## Installation

Clone the repository:

```bash
git clone https://github.com/Tanmay-Bhatnagar22/TraceLens.git
cd TraceLens
```

Create virtual environment:

```bash
python -m venv .venv
```

Activate virtual environment:

- Windows PowerShell

```bash
.venv\Scripts\Activate.ps1
```

- macOS/Linux

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run the Application

From the repository root:

```bash
python src/main.py
```

## How to Use

1. Open **Extractor** tab and choose a file.
2. Click **Extract** to collect metadata and persist history.
3. Open **Editor** to modify editable fields.
4. Save changes and optionally write metadata back to the source file.
5. Open **Risk analyzer** to inspect risk level, reasons, and timeline.
6. Generate reports and export from **Preview** or **History**.
7. Use **Statistics Dashboard** (Tools menu) for broader analytics.

## Keyboard Shortcuts

- `Ctrl+N` New project
- `Ctrl+O` Open file
- `Ctrl+E` Export results
- `Ctrl+C` Copy results
- `F5` Refresh data
- `Ctrl++` Zoom in
- `Ctrl+-` Zoom out
- `Ctrl+0` Reset zoom
- `F11` Full screen
- `F1` Documentation
- `Ctrl+?` or `Ctrl+/` Shortcuts dialog

## Database Schema

Table: `metadata`

- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `file_path` TEXT NOT NULL
- `file_name` TEXT NOT NULL
- `file_size_formatted` TEXT
- `file_type` TEXT
- `extracted_at` TEXT NOT NULL
- `modified_on` TEXT
- `full_metadata` TEXT NOT NULL (JSON payload)

Database file: `file_metadata.db` (created automatically).

## Testing

Run full test suite:

```bash
pytest tests/
```

Run per-module tests:

```bash
pytest tests/test_extractor.py
pytest tests/test_editor.py
pytest tests/test_db.py
pytest tests/test_report.py
pytest tests/test_gui.py
pytest tests/test_risk_analyzer.py
pytest tests/test_main.py
```

## Troubleshooting

### Tkinter import issues

- Ensure your Python distribution includes Tkinter.

### Optional metadata write-back fails

- Install optional libraries from `requirements.txt` (`piexif`, `mutagen`, `python-docx`, `openpyxl`).

### Report/print dialogs in headless test environments

- Mock UI dialogs, as done in the test suite.

### Icon not loading on startup

- Ensure `Metadata.png` is available at runtime in the expected location.

## Known Limitations

- Database backup menu currently references `metadata.db` while primary storage uses `file_metadata.db`.
- Office metadata write-back is primarily implemented for DOCX.
- Export and print actions rely on GUI dialogs.

## Contributing

Contributions are welcome.

- Keep changes focused and consistent with existing code style.
- Add or update tests in `tests/` for behavior changes.
- Update this README when functionality changes.

## License

This project is licensed under the MIT License. See `LICENSE` for details.
