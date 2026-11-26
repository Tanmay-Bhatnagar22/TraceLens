<div align="center">

# TraceLens: Metadata Analysis & Privacy Inspection Toolkit

[![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)](https://github.com/Tanmay-Bhatnagar22/TraceLens)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](https://github.com/Tanmay-Bhatnagar22/TraceLens)
[![Tests](https://img.shields.io/badge/tests-225%20passed-brightgreen.svg)](tests/)
[![GUI](https://img.shields.io/badge/GUI-Tkinter-ff69b4.svg)](src/gui/)
[![CLI](https://img.shields.io/badge/CLI-Argparse%20%2B%20Rich-orange.svg)](src/cli/)
[![Database](https://img.shields.io/badge/database-SQLite-003b57.svg)](src/core/database/)

</div>

**TraceLens** is an open-source desktop and command-line application engineered for extracting, inspecting, editing, persisting, and reporting digital file metadata. Built with Python, Tkinter, and an Argparse/Rich CLI, TraceLens provides rule-based privacy risk scoring, chronological event timelines, selective metadata write-back, local SQLite history storage, and multi-format report exports (PDF, JSON, XML, CSV, Excel).

---

## Table of Contents

- [Overview](#overview)
- [What is New in Version 2.0](#what-is-new-in-version-20)
- [Key Features](#key-features)
- [Interface & Screenshots](#interface--screenshots)
- [System Architecture](#system-architecture)
- [Project Structure](#project-structure)
- [Supported File Formats](#supported-file-formats)
- [Technical Stack](#technical-stack)
- [Installation & Setup](#installation--setup)
- [Usage Guide](#usage-guide)
  - [Graphical User Interface (GUI)](#graphical-user-interface-gui)
  - [Command-Line Interface (CLI)](#command-line-interface-cli)
  - [Batch Processing Workflow](#batch-processing-workflow)
- [Python API & Service Layer](#python-api--service-layer)
- [Risk Scoring & Forensic Engine](#risk-scoring--forensic-engine)
- [Database Schema & Persistence](#database-schema--persistence)
- [Future Roadmap & Version 3.0 Plan: TraceAi](#future-roadmap--version-30-plan-traceai)
- [Testing & Quality Assurance](#testing--quality-assurance)
- [Troubleshooting](#troubleshooting)
- [Known Limitations](#known-limitations)
- [Contributing](#contributing)
- [License & Contact](#license--contact)

---

## Overview

Digital files often retain hidden metadata—such as GPS coordinates, camera configurations, creator names, software processing tags, and filesystem timestamps. When shared publicly without inspection, this metadata can expose private personal details, organizational infrastructure, and sensitive handling history.

TraceLens v2.0 provides an integrated metadata inspection and reporting toolkit:
- **Extract**: Parse metadata properties across documents, images, audio, video, archives, databases, structured data, and code files.
- **Analyze**: Evaluate privacy exposure indicators and chronological anomalies using a configurable, YAML-driven risk engine.
- **Edit & Sanitize**: Update supported fields in-place (PDF, PNG, DOCX, audio tags, text files), embed metadata in JPEG/TIFF UserComment tags, or create companion `.meta.json` sidecar files.
- **Persist**: Store extraction records in a local SQLite database (`file_metadata.db`) with keyword, date, and format filtering.
- **Visualize**: Review summary statistics, file types, and risk distribution graphs with embedded Matplotlib dashboards.
- **Report**: Export structured reports in PDF, JSON, XML, CSV, Excel, and plain-text formats.
- **Dual Interface**: Operate via a tabbed Tkinter desktop GUI or a headless Argparse/Rich command-line suite.

---

## What is New in Version 2.0

Version 2.0 represents a major architectural evolution of TraceLens, transforming it into a modular, service-driven metadata toolkit.

### 1. Unified Service Layer & Dependency Injection
- Introduced `ServiceContainer` as an application facade managing discrete lifecycle services: `ExtractionService`, `RiskAnalysisService`, `MetadataEditorService`, `HistoryService`, `ReportService`, and `AnalyticsService`.
- Clean separation between core domain algorithms, presentation layers (GUI/CLI), and persistence layers.

### 2. Configurable YAML-Based Risk & Forensic Rules Engine
- Replaced hardcoded heuristic checks with a decoupled rules engine (`rules.yaml`) loaded and validated through `yaml_parser.py` and `rule_models.py`.
- Granular scoring rules covering geolocation, personal identity, hardware fingerprints, software processing traces, hidden metadata containers, network paths, and digital signatures.
- Forensic anomaly detection heuristics:
  - **Timestamp Inversion Detection**: Flags chronological discrepancies where file modification precedes creation or capture.
  - **Multiple Editing Chain Detection**: Identifies distinct software signatures in metadata indicating multiple revision passes.
  - **Stacked Metadata Block Detection**: Identifies coexisting metadata container tags (such as EXIF, IPTC, XMP, MakerNotes indicators).
- Context-specific remediation recommendations for every triggered rule.

### 3. Production CLI Overhaul (Argparse + Rich)
- Modernized, lightweight command-line subsystem powered by Python's standard library `argparse` with dedicated subcommands (`extract`, `batch`, `analyze`, `sanitize`, `edit`, `report`, `export`, `search`, `history`, `analytics`, `config`, `logs`, `help`).
- Rich terminal output featuring styled status tables, summary panels, and progress displays, plus a Typer compatibility adapter for automated testing.
- Decoupled from Tkinter/GUI dependencies so the CLI runs cleanly in headless and non-graphical environments.
- Unified canonical help system (`tracelens help` and `tracelens --help`) alongside command-specific `argparse` help (`tracelens <command> --help`).

### 4. Modular Tabbed GUI Architecture
- Refactored Tkinter presentation layer into dedicated, decoupled tab components (`ExtractorTab`, `EditorTab`, `RiskTab`, `PreviewTab`, `HistoryTab`).
- Added a dedicated `BatchProcessDialog` for multi-threaded folder scans and batch risk aggregation.
- Implemented `StatisticsDashboard` featuring embedded Matplotlib visual analytics, risk distribution breakdowns, format distributions, and extraction timelines.

### 5. Centralized Logging Infrastructure
- Integrated `logging_config.py` providing log rotation, thread-safe memory buffers for runtime diagnostics, configurable log levels via environment variables, and live GUI log viewer integration.

### 6. Expanded Format Parsing & Write-Back
- Integration of Hachoir alongside specialized engines (`PyPDF2`, `piexif`, `mutagen`, `python-docx`, `openpyxl`, `pdf2image`).
- Selective write-back support with safety backups (`.bak` / `.backup`) and automatic companion `.meta.json` fallbacks for unsupported binary containers.

---

## Key Features

### Multi-Format Metadata Extraction
- Automated file format identification and parser dispatching across documents, media, archives, structured data, and code.
- Extracts document properties, EXIF tags, GPS geo-tags, audio ID3/Vorbis tags, video stream metadata, archive tables, and source code statistics.
- Graceful fallbacks for unhandled formats via universal binary stream parsing.

### Forensic Risk & Privacy Scoring
- 0 to 100 normalized risk score mapped into defined threat levels: LOW (0-29), MEDIUM (30-64), HIGH (65-100).
- Chronological timeline generation mapping creation, modification, capture, and edit events.
- Anomaly warnings and step-by-step remediation advice to sanitize files before distribution.

### Field-Level Editing & Sanitization
- Interactive editing interface with strict preservation of immutable file system properties (`File Name`, `File Size`, `File Type`, `Extracted At`, `Modified On`).
- In-place metadata write-back for PDFs (PyPDF2), PNG text chunks (Pillow), Word documents (python-docx), and audio tags (mutagen). For JPEG/TIFF, metadata is serialized into the EXIF `UserComment` tag (piexif), while text files receive comment/header blocks (Excel `.xlsx` and PowerPoint `.pptx` write-back is not supported).
- Automatic creation of safety copies (`.bak`) before performing destructive file modifications.

### SQLite History & Data Persistence
- Persistent local SQLite database (`file_metadata.db`) tracking extraction timestamps, formatted sizes, file paths, and raw JSON payloads.
- Search queries filtering by keyword (matching file name and path), date ranges, and file extensions. Risk scores are evaluated dynamically by the risk engine.
- Database maintenance utilities including SQLite `VACUUM` optimization and batch purging.

### Multi-Format Reporting & Export
- Formatted PDF reports rendered via ReportLab with headers, metadata key-value tables, risk summaries, timelines, and page numbering.
- Structured data export to JSON, XML, CSV, and Excel workbooks.
- Integrated document preview module leveraging `pdf2image` and Poppler.

### Analytical Dashboard
- Live visualization of historical metrics:
  - Risk distribution pie charts.
  - File format composition bar graphs.
  - File size distribution histograms.
  - Cumulative extraction activity timelines.

---

## Interface & Screenshots

### Graphical User Interface (GUI)

#### 1. Main Application Window
The TraceLens desktop interface features an organized multi-tab layout for seamless transitions across extraction, editing, risk auditing, reporting, and historical analysis.

![Main Application Window](Screenshots/image.png)

#### 2. Extractor Tab — Metadata Extraction & Inspection
Browse, select, and parse files across 50+ formats to view extracted metadata properties in an organized key-value grid with automatic SQLite indexing.

![Extractor Tab](Screenshots/gui_extractor_tab.png)

#### 3. Editor Tab — Field-Level Editing, Write-Back & Sanitization
Modify editable metadata fields, validate field structures, strip sensitive tags, and commit changes back to the physical file on disk (with automatic `.bak` safety backups) or the local database.

![Editor Tab](Screenshots/gui_editor_tab.png)

#### 4. Risk Analyzer Tab — Privacy Scoring & Forensic Timeline
Inspect calculated threat scores (`0–100`), risk tiers (`LOW`, `MEDIUM`, `HIGH`), triggered YAML privacy rules, chronological event timelines, and forensic anomaly warnings.

![Risk Analyzer Tab](Screenshots/gui_risk_analyzer_tab.png)

*Note: For unmodified files, the timeline reflects single-event creation records.*

#### 5. Preview & Reports Tab — Live PDF Preview & Multi-Format Export
Preview generated PDF dossiers directly inside the application with zoom controls and export reports across PDF, TXT, JSON, XML, CSV, and Excel formats.

![Preview and Reports Tab](Screenshots/gui_preview_reports_tab.png)

*Note: PDF preview rendering requires Poppler binaries installed on the host system.*

#### 6. History Tab — Database Search, Filtering & Record Management
Search, sort, filter by file type or date range, inspect historical records stored in SQLite, and bulk-export filtered datasets.

![History Tab](Screenshots/gui_history_tab.png)

#### 7. Batch Processing Dialog — Folder Scanning & Risk Aggregation
Scan entire folder hierarchies recursively with live progress tracking, per-file status reporting, and aggregated batch risk summaries.

![Batch Processing Dialog](Screenshots/gui_batch_processing.png)

#### 8. Analytics & Statistics Dashboard — Visual Forensic Intelligence
Examine aggregate metrics, risk distribution charts, file format breakdowns, file size distributions, and extraction timelines across historical scans.

![Analytics Dashboard](Screenshots/gui_analytics_dashboard_kpi.png)

![Analytics Dashboard](Screenshots/gui_analytics_dashboard_chart.png)

---

### Command-Line Interface (CLI)

#### 1. CLI Quick Start & Canonical Help Guide (`tracelens`, `tracelens help`, `tracelens --help`)
Displays the startup branding, Quick Start panel, 5-stage workflow pipeline, Command Reference table, and Common Operational Workflows.

##### Quick Start
![CLI Quick Start](Screenshots/cli_quick_start.png)

##### Help Guide
![CLI Help Guide](Screenshots/cli_help_overview.png)

#### 2. Metadata Extraction (`tracelens extract`)
Extracts metadata from a target file, persists the record to SQLite, and outputs a concise extraction summary (or full key-value table with `--details` / `-v`).

![CLI Extract](Screenshots/cli_extract.png)

#### 3. Batch Directory Processing (`tracelens batch`)
Scans a directory with per-file progress (`Processing 1/N`), isolates individual file failures, and prints a complete batch extraction and risk breakdown summary.

![CLI Batch Processing](Screenshots/cli_batch.png)

#### 4. Privacy & Forensic Risk Analysis (`tracelens analyze`)
Evaluates file metadata against the YAML rules engine, displaying the risk score (`0–100`), risk level, matched rules, chronological timeline events, and remediation suggestions.

![CLI Risk Analysis](Screenshots/cli_analyze.png)

#### 5. Metadata Sanitization & Field Editing (`tracelens sanitize`, `tracelens edit`)
Clears metadata on supported files with `.bak` backup protection (`sanitize`) or updates specific metadata fields via `--set KEY=VALUE` or `--metadata-file` (`edit`).

##### CLI Sanitize
![CLI Sanitize](Screenshots/cli_sanitize.png)

##### CLI Edit
![CLI Edit](Screenshots/cli_edit.png)

#### 6. Report Generation & Dataset Export (`tracelens report`, `tracelens export`)
Generates structured `.txt` and formatted `.pdf` reports from a database Record ID or file path (`report`), and exports filtered history records to JSON, CSV, XML, Excel, or PDF (`export`).

![CLI Report Generation](Screenshots/cli_report.png)

#### 7. Database Search, History Management & Analytics (`tracelens search`, `tracelens history`, `tracelens analytics`)
Performs fast keyword searches across stored records (`search`), manages historical records and database statistics (`history`, `history stats`), and computes aggregate risk metrics (`analytics`).
##### CLI Search and History
![CLI Search and History](Screenshots/cli_search_history.png)
##### CLI Analytics
![CLI Analytics Dashboard](Screenshots/cli_analytics.png)

#### 8. Configuration, Diagnostics & Verbose Logging (`tracelens config`, `tracelens logs`, `--verbose`)
Displays active environment/database paths, runs SQLite `VACUUM` optimization (`config optimize`), inspects or clears application logs (`logs`), and provides step-by-step `[INFO]`/`[DEBUG]` diagnostics (`-v`).

![CLI Config and Logs](Screenshots/cli_config_logs.png)

---

## System Architecture

TraceLens follows a strict layered architecture pattern, isolating presentation components from domain logic and infrastructure persistence.

```text
+-----------------------------------------------------------------------------+
|                            PRESENTATION LAYER                               |
|   +---------------------------------------+   +-------------------------+   |
|   |         Tkinter GUI Subsystem         |   |   Argparse / Rich CLI   |   |
|   |  - ExtractorTab     - EditorTab       |   |  - extract   - analyze  |   |
|   |  - RiskTab          - PreviewTab      |   |  - edit      - report   |   |
|   |  - HistoryTab       - BatchDialog     |   |  - history   - export   |   |
|   |  - StatisticsDashboard                |   |  - logs      - config   |   |
|   +---------------------------------------+   +-------------------------+   |
+--------------------------------------|--------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------+
|                          SERVICE & APPLICATION FACADE                       |
|   +---------------------------------------------------------------------+   |
|   |                          ServiceContainer                           |   |
|   |  - ExtractionService  - RiskAnalysisService  - MetadataEditorService|   |
|   |  - HistoryService     - ReportService        - AnalyticsService     |   |
|   +---------------------------------------------------------------------+   |
+--------------------------------------|--------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------+
|                          CORE BUSINESS LOGIC LAYER                          |
|   +-------------------+  +-------------------+  +------------------------+  |
|   | MetadataExtractor |  |  MetadataEditor   |  | PrivacyForensicAnalyzer|  |
|   | - Format Detect   |  | - Field Parsing   |  | - YAML Rule Engine     |  |
|   | - PyPDF2/mutagen  |  | - In-place Write  |  | - Anomaly Detector     |  |
|   | - Hachoir Parser  |  | - Backup Handling |  | - Timeline Builder     |  |
|   +-------------------+  +-------------------+  +------------------------+  |
+--------------------------------------|--------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------+
|                         DATA & PERSISTENCE LAYER                            |
|   +-------------------+  +-------------------+  +------------------------+  |
|   | MetadataDatabase  |  | MetadataReporter  |  |      File System       |  |
|   | - SQLite Storage  |  | - ReportLab (PDF) |  | - Target Files        |  |
|   | - Query Filtering |  | - JSON / XML / CSV|  | - .meta.json Fallback  |  |
|   | - History CRUD    |  | - Excel Workbook  |  | - Rotated Logs (.log)  |  |
|   +-------------------+  +-------------------+  +------------------------+  |
+-----------------------------------------------------------------------------+
```

---

## Project Structure

```text
TraceLens/
|-- src/
|   |-- __init__.py
|   |-- main.py                     # Main GUI desktop entry point
|   |-- cli/                        # Command-line interface subsystem
|   |   |-- __init__.py
|   |   |-- cli.py                  # Argparse commands, arguments, and handlers
|   |   |-- output.py               # Rich tables, panels, and spinners
|   |   `-- validation.py           # Path verification and input validation
|   |-- config/                     # Configuration and diagnostics
|   |   |-- __init__.py
|   |   `-- logging_config.py       # Rotating logger and in-memory log buffer
|   |-- core/                       # Core domain engines
|   |   |-- __init__.py
|   |   |-- database/               # SQLite database access
|   |   |   |-- __init__.py
|   |   |   `-- db.py               # Database manager and schema management
|   |   |-- editor/                 # Metadata modification and serialization
|   |   |   |-- __init__.py
|   |   |   `-- editor.py           # In-place write-back engine
|   |   |-- extractor/              # Parsing and extraction engine
|   |   |   |-- __init__.py
|   |   |   `-- extractor.py        # 50+ format parsers
|   |   |-- reports/                # Report generation
|   |   |   |-- __init__.py
|   |   |   `-- report.py           # PDF, JSON, XML, CSV, Excel generators
|   |   |-- risk/                   # Risk scoring and forensic anomaly engine
|   |   |   |-- __init__.py
|   |   |   |-- risk_analyzer.py    # Public risk interface
|   |   |   |-- risk_engine.py      # Core evaluation engine
|   |   |   |-- rule_models.py      # Dataclass models for rules
|   |   |   |-- rules.yaml          # Configurable YAML rule definitions
|   |   |   `-- yaml_parser.py      # YAML ruleset loader and validator
|   |   `-- services/               # Dependency injection and service facade
|   |       |-- __init__.py
|   |       |-- analytics_service.py # Analytics aggregation service
|   |       |-- container.py        # ServiceContainer facade
|   |       |-- editor_service.py   # Editing application service
|   |       |-- extraction_service.py # Extraction application service
|   |       |-- history_service.py  # History management service
|   |       |-- report_service.py   # Reporting application service
|   |       `-- risk_service.py     # Risk analysis service
|   |-- gui/                        # Presentation GUI layer (Tkinter)
|   |   |-- __init__.py
|   |   |-- gui.py                  # Main application window and menu logic
|   |   |-- batch_process_dialog.py # Multi-file batch scan dialog
|   |   |-- statistics_dashboard.py # Interactive analytics dashboard
|   |   `-- tabs/                   # Dedicated modular tab implementations
|   |       |-- __init__.py
|   |       |-- editor_tab.py       # Field editing and write-back tab
|   |       |-- extractor_tab.py    # Extraction tab
|   |       |-- history_tab.py      # History viewer and search tab
|   |       |-- preview_tab.py      # Document preview and export tab
|   |       `-- risk_tab.py         # Forensic risk analysis tab
|   |-- models/                     # Strongly typed data models
|   |   |-- __init__.py
|   |   |-- analytics.py            # Analytics and metrics models
|   |   |-- metadata.py             # Metadata record models
|   |   |-- reports.py              # Report configuration models
|   |   `-- risk.py                 # Risk evaluation models
|   |-- ai/                         # Foundation package for Version 3 AI integrations
|   |-- providers/                  # Third-party integrations
|   |-- rules/                      # Rule extensions
|   |-- utils/                      # Utilities and logger helpers
|   |   |-- __init__.py
|   |   `-- logger.py
|   |-- db.py                       # Root backward-compatibility shim
|   |-- editor.py                   # Root backward-compatibility shim
|   |-- extractor.py                # Root backward-compatibility shim
|   |-- report.py                   # Root backward-compatibility shim
|   `-- risk_analyzer.py            # Root backward-compatibility shim
|-- tests/                          # Comprehensive Pytest test suite
|   |-- test_batch_process_dialog.py
|   |-- test_cli.py
|   |-- test_db.py
|   |-- test_editor.py
|   |-- test_extractor.py
|   |-- test_gui.py
|   |-- test_gui_tabs.py
|   |-- test_logging.py
|   |-- test_main.py
|   |-- test_report.py
|   |-- test_risk_analyzer.py
|   |-- test_risk_engine.py
|   `-- test_statistics_dashboard.py
|-- assets/                         # Application branding and icon assets
|-- Screenshots/                    # Interface walkthrough media
|-- pyproject.toml                  # PEP 518/621 packaging metadata
|-- requirements.txt                # Project dependencies
|-- LICENSE                         # MIT license
`-- README.md                       # Comprehensive documentation
```

---

## Supported File Formats

### Extraction Support Matrix

| Category | Formats | Extracted Fields & Metadata Properties |
|---|---|---|
| **Documents** | PDF (`.pdf`), DOCX (`.docx`), XLSX (`.xlsx`), PPTX (`.pptx`), ODT (`.odt`), ODS (`.ods`), ODP (`.odp`) | Title, Author, Subject, Creator, Producer, Keywords, Page/Sheet count, Creation/Modification timestamps, Revision count, Last modified by |
| **Images** | JPEG (`.jpg`, `.jpeg`), PNG (`.png`), TIFF (`.tiff`, `.tif`), GIF (`.gif`), BMP (`.bmp`), WebP (`.webp`), SVG (`.svg`), ICO (`.ico`) | Camera make/model, Lens info, Exposure parameters, GPS coordinates, Altitude, standard EXIF tags, dimensions, mode/color depth, aspect ratio, DPI, PNG text chunks, SVG attributes |
| **Audio** | MP3 (`.mp3`), FLAC (`.flac`), M4A/AAC (`.m4a`, `.aac`), OGG (`.ogg`), WAV (`.wav`), OPUS (`.opus`), WMA (`.wma`) | Title, Artist, Album, Track number, Release year, Genre, Bitrate, Sample rate, Duration, Codec, Audio channel configuration |
| **Video** | MP4 (`.mp4`), MOV (`.mov`), AVI (`.avi`), MKV (`.mkv`), FLV (`.flv`), WebM (`.webm`), M4V (`.m4v`) | Container tags, duration, bitrate, and stream metadata via Mutagen (MP4/MOV) and Hachoir fallback |
| **Archives** | ZIP (`.zip`), TAR (`.tar`, `.tar.gz`, `.tar.bz2`, `.tar.xz`, `.tgz`) | Member file count, Directory count, Uncompressed/Compressed sizes, Compression ratio, Sample files. Note: other archive formats (`.7z`, `.rar`) use generic binary stream fallback. |
| **Databases** | SQLite (`.db`, `.sqlite`, `.sqlite3`, `.db3`) | Database page size, encoding, schema table names, view counts, and index metadata |
| **Code & Text** | TXT, PY, JS, JAVA, C, CPP, H, JSON, XML, YAML, CSV, MD, HTML, CSS, SQL, INI | Character count, Line count, Encoding, Frontmatter, Configuration parameters |
| **Binary & Misc** | EXE, DLL, ELF, ISO, MIDI, and additional binary formats via Hachoir | Header signatures, Stream architecture, MIME types, Section tables, Compiler signatures |

### Write-Back Support Matrix

| Format / Target | Modification Mechanism | Supported Operations |
|---|---|---|
| **PDF** (`.pdf`) | PyPDF2 Document Property Stream | Update Author, Title, Subject, Keywords, Creator, Producer |
| **JPEG / TIFF** (`.jpg`, `.tiff`) | `piexif` EXIF Serialization | Serializes updated metadata dictionary into the EXIF `UserComment` tag |
| **PNG** (`.png`) | Pillow PNG Text Chunk Modification | Injects/updates textual key-value metadata chunks (`tEXt`) |
| **Audio** (`.mp3`, `.flac`, `.m4a`, `.ogg`) | `mutagen` Tag Stream Modification | Sets standard tags (Title, Artist, Album) and serializes metadata into comments/tags |
| **Office Documents** (`.docx`) | `python-docx` Core Properties | Updates Core properties (Title, Author, Subject, Keywords, Comments). *Note: write-back is not supported for `.xlsx` or `.pptx`.* |
| **Text Documents** (`.txt`, `.md`, `.py`, `.yaml`, `.xml`, `.json`) | Header / Comment Injection | Adds metadata comment headers or injects a `_metadata` key (JSON) |
| **Other / Unsupported Binary** | Companion Sidecar (`.meta.json`) | Writes updated metadata to an adjacent JSON sidecar preserving original binary intact |

---

## Technical Stack

### Core Runtime
- **Python 3.10+**: Utilizing modern type union syntax (`X | Y`), strict dataclasses, and path handling.
- **Tkinter**: Native, cross-platform graphical user interface toolkit.

### Metadata Extraction & Manipulation
- **PyPDF2 (>=3.0.0)**: PDF document parsing and structural property modification.
- **Hachoir (>=3.2.0)**: Low-level binary stream parser for media and executable container inspection.
- **piexif (>=1.1.3)**: EXIF byte serialization and UserComment handling for JPEG/TIFF assets.
- **mutagen (>=1.47.0)**: Audio tag parsing and writing (MP3, FLAC, M4A, OGG).
- **python-docx (>=1.1.0)**: OpenXML Word document inspection and core property mutation.
- **openpyxl (>=3.1.0)**: OpenXML Excel workbook structure inspection and report export handling.
- **pdf2image (>=1.16.0)**: Document rendering and image conversion for report previewing.

### Analytics, Data Processing & Visuals
- **pandas (>=2.0.0)**: Tabular data structures, history filtering, and analytical export transformations.
- **Pillow (>=10.0.0)**: Image manipulation, dimension extraction, and PNG chunk handling.
- **matplotlib (>=3.7.0)**: Chart generation and visualization widgets for the statistics dashboard.

### Command-Line & Terminal UI
- **argparse**: Standard library argument parsing engine powering all CLI commands and subcommands.
- **rich (>=13.7.0)**: Terminal formatting, status spinners, progress displays, and styled tables.
- **typer (>=0.12.3) / click (>=8.1.0)**: Compatibility bridge facilitating automated test runner invocation.
- **pyyaml (>=6.0.0)**: Rule definitions loading and configuration validation.

### Reporting & Persistence
- **ReportLab (>=4.0.0)**: Programmatic PDF report rendering with custom layout tables and styles.
- **SQLite3**: ACID-compliant local database engine with zero external daemon requirements.

### Quality Assurance
- **pytest (>=8.3.0)**: Automated test execution framework (225 passing unit and integration tests).
- **pytest-cov (optional)**: Coverage reporting plugin (required when running `pytest --cov`).

---

## Installation & Setup

### Prerequisites

1. **Python 3.10 or higher**: Verify with `python --version`.
2. **Tkinter**:
   - **Windows**: Bundled automatically with official Python installers.
   - **Linux (Debian/Ubuntu)**: `sudo apt-get install python3-tk`
   - **Linux (Fedora/RHEL)**: `sudo dnf install python3-tkinter`
   - **macOS**: `brew install python-tk@3.11` (or respective Python version).
3. **Poppler (Optional, for PDF rendering in Preview Tab)**:
   - **Windows**: Download Poppler binaries and add the `bin/` directory to system `PATH`.
   - **Linux**: `sudo apt-get install poppler-utils`
   - **macOS**: `brew install poppler`

### Installation Steps

#### 1. Clone the Repository
```bash
git clone https://github.com/Tanmay-Bhatnagar22/TraceLens.git
cd TraceLens
```

#### 2. Create and Activate a Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### 3. Install Dependencies

Install all core and optional dependencies:
```bash
pip install -r requirements.txt
```

Alternatively, install in editable development mode:
```bash
pip install -e ".[dev,extras]"
```

#### 4. Verify Installation
```bash
python -c "import PyPDF2, hachoir, rich, typer, tkinter; print('TraceLens v2.0 environment initialized successfully.')"
```

---

## Usage Guide

### Graphical User Interface (GUI)

Starting in TraceLens v2.0, the desktop GUI and command-line interface are separated into independent entry points for dedicated GUI and CLI executables.

#### Option A: Windows Installer (`TraceLens-GUI-Setup.exe`)

For the standard Windows desktop experience with Start Menu and Desktop shortcuts (no Python or administrator privileges required):

1. Download `TraceLens-GUI-Setup.exe` from the release page (or build it locally into `dist/v2/installer/TraceLens-GUI-Setup.exe`).
2. Run `TraceLens-GUI-Setup.exe` and follow the setup wizard:
   - Default install directory: `%LOCALAPPDATA%\Programs\TraceLens` (per-user install, no admin rights required).
   - Optionally enable the **Create a desktop icon** task.
3. **Launch TraceLens GUI**:
   - Open **Start Menu -> TraceLens GUI**, double-click the **TraceLens GUI** Desktop shortcut, or check **Launch TraceLens GUI** on the installer completion screen.
4. **Uninstall**:
   - Use **Settings -> Apps -> Installed apps -> TraceLens GUI -> Uninstall** or **Start Menu -> TraceLens GUI -> Uninstall TraceLens GUI**.
   - Uninstallation removes the installed application binaries, shortcuts, and installer registry entries while **preserving** your user-generated history database and logs in `%LOCALAPPDATA%\TraceLens\`.
5. **Building the Installer Locally** (requires [Inno Setup 6](https://jrsoftware.org/isinfo.php)):
   ```powershell
   pyinstaller --noconfirm --clean --distpath dist/v2 --workpath build packaging/TraceLens.spec
   & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "installer\gui\TraceLens-GUI.iss"
   ```

#### Option B: Portable Standalone Executable (`TraceLens.exe`)

Windows users can run the packaged GUI directly without installing Python, a virtual environment, or project dependencies:

1. Download or extract the `TraceLens` standalone folder (e.g., from a release archive or `dist/v2/TraceLens/`).
2. Double-click `TraceLens.exe` (or run it from PowerShell/Command Prompt). It opens directly into the windowed GUI with no console window.

- **Supported Environment**: Windows 10 / Windows 11 (64-bit).
- **GUI vs. CLI Executables**:
  - **GUI**: `dist/v2/TraceLens/TraceLens.exe` (`packaging/TraceLens.spec`) — Windowed Tkinter desktop application (`src/main.py`).
  - **CLI**: `dist/v2/cli/TraceLens/TraceLens.exe` (`packaging/TraceLens-cli.spec`) — Console-mode headless CLI (`src/cli/cli.py`).
- **Writable Runtime Data Locations** (kept separate from the application bundle so the app works from any directory):
  - **SQLite History Database**: `%LOCALAPPDATA%\TraceLens\file_metadata.db` (overridable via `TRACELENS_DB_PATH`).
  - **Application Logs**: `%LOCALAPPDATA%\TraceLens\logs\tracelens.log` (overridable via `TRACELENS_LOG_FILE` or `TRACELENS_LOG_DIR`).
- **Runtime Limitations**:
  - Live PDF-to-image rendering in the **Preview Tab** (`pdf2image`) still requires Poppler binaries on the system `PATH`; without Poppler, the Preview Tab falls back to text preview while PDF export (`reportlab`) continues to work normally.
  - The *File -> Backup Database* menu action copies `"metadata.db"` from the current working directory rather than `%LOCALAPPDATA%\TraceLens\file_metadata.db`; you can back up the database directly from `%LOCALAPPDATA%\TraceLens\file_metadata.db`.
- **Building Locally from Source**:
  ```powershell
  # GUI executable
  pyinstaller --noconfirm --clean --distpath dist/v2 --workpath build packaging/TraceLens.spec

  # CLI executable
  pyinstaller --noconfirm --clean --distpath dist/v2/cli --workpath build/cli packaging/TraceLens-cli.spec
  ```

#### Option C: Launch from Source (Python)

Launch the full-featured desktop interface via `src/main.py`:
```bash
python src/main.py
```

#### GUI Workflow:
1. **Extractor Tab**: Click **Browse** to choose a target file and click **Extract Metadata**. The parsed attributes appear in the tabular viewer and are automatically indexed into the local SQLite database.
2. **Editor Tab**: Select any editable attribute (e.g., Author, Title, GPS), update its value, and click **Save Changes**. Click **Write Back to File** to persist edits directly to the target file.
3. **Risk Tab**: View the calculated threat score (0-100), risk tier (LOW, MEDIUM, HIGH), triggered security rules, chronological event timeline, and forensic anomalies.
4. **Preview Tab**: View generated reports with live document rendering. Click **Export Report** to produce PDF, TXT, JSON, XML, CSV, or Excel dossiers.
5. **History Tab**: Search previous extractions with keyword search, filter by file type or date range, sort columns, and bulk-export historical datasets.
6. **Analytics Dashboard** (*Tools -> Statistics Dashboard*): Access interactive Matplotlib visual metrics and file risk distribution graphs.
7. **Batch Processing** (*Batch Process -> Select Folder*): Scan entire folder hierarchies, aggregate risk metrics, and generate batch audit summaries.

---

### Command-Line Interface (CLI)

TraceLens provides a lightweight, headless `argparse` command-line suite (`tracelens`) with zero Tkinter/GUI startup dependencies, structured output, input validation, and standardized exit codes:

```text
tracelens [OPTIONS] COMMAND [ARGS]...
```

#### Windows CLI Installer (`TraceLens-CLI-Setup.exe`)

For system-wide terminal convenience on Windows 10/11 (64-bit) without Python or administrator privileges:

1. Download `TraceLens-CLI-Setup.exe` from the release page (or build it locally into `dist/v2/installer/TraceLens-CLI-Setup.exe`).
2. Run `TraceLens-CLI-Setup.exe` and follow the setup wizard:
   - Default install directory: `%LOCALAPPDATA%\Programs\TraceLens-CLI` (per-user install, no admin rights required).
   - Keep **Add TraceLens CLI to your user PATH** checked to run `TraceLens` from any directory.
   - Optionally enable **Create a desktop icon**.
3. **Verify Installation**: Open a **new** Command Prompt or PowerShell window (already-open terminals do not pick up `PATH` changes until restarted) and run:
   ```powershell
   TraceLens --version
   TraceLens --help
   TraceLens extract C:\path\to\file.png --details
   TraceLens analyze C:\path\to\file.png
   ```
4. **Uninstall**:
   - Use **Settings -> Apps -> Installed apps -> TraceLens CLI -> Uninstall** or **Start Menu -> TraceLens CLI -> Uninstall TraceLens CLI**.
   - Uninstallation removes installed binaries, shortcuts, and only the `PATH` entry added by the installer, while **preserving** your user data in `%LOCALAPPDATA%\TraceLens\`.
5. **Building the CLI Installer Locally** (requires [Inno Setup 6](https://jrsoftware.org/isinfo.php)):
   ```powershell
   pyinstaller --noconfirm --clean --distpath dist/v2/cli --workpath build/cli packaging/TraceLens-cli.spec
   & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "installer\cli\TraceLens-CLI.iss"
   ```

#### Standalone Windows CLI Executable (`TraceLens.exe`)

Windows users can run the packaged CLI directly from **Command Prompt** or **PowerShell** without installing Python, creating a virtual environment, or installing dependencies:

1. Download or extract the standalone CLI `TraceLens` folder (from a release archive or `dist/v2/cli/TraceLens/`). Keep `TraceLens.exe` together with its `_internal/` folder.
2. Run `TraceLens.exe` from Command Prompt or PowerShell (optionally add the folder to your `PATH`), or run it with no arguments to open the interactive `tracelens>` shell:

```powershell
# Check packaged version and access help
.\TraceLens.exe --version
.\TraceLens.exe --help
.\TraceLens.exe help
.\TraceLens.exe extract --help

# Extract, analyze, and generate reports from any working directory
.\TraceLens.exe extract C:\path\to\photo.png --details
.\TraceLens.exe batch C:\path\to\folder
.\TraceLens.exe analyze C:\path\to\document.pdf
.\TraceLens.exe sanitize C:\path\to\photo.png --backup
.\TraceLens.exe edit C:\path\to\photo.png -s "Author=Analyst"
.\TraceLens.exe report C:\path\to\document.pdf -f both
.\TraceLens.exe export json -o records.json
.\TraceLens.exe search document
.\TraceLens.exe history stats
.\TraceLens.exe analytics
.\TraceLens.exe config
.\TraceLens.exe logs -n 20
```

- **Supported Environment**: Windows 10 / Windows 11 (64-bit).
- **GUI vs. CLI Launch**: Run `dist/v2/TraceLens/TraceLens.exe` for the windowed Tkinter GUI, or `dist/v2/cli/TraceLens/TraceLens.exe` for terminal/headless CLI usage.
- **Writable Runtime Locations**:
  - **SQLite Database**: `%LOCALAPPDATA%\TraceLens\file_metadata.db` (overridable via `--db-path` or `TRACELENS_DB_PATH`).
  - **Logs**: `%LOCALAPPDATA%\TraceLens\logs\tracelens.log` (overridable via `TRACELENS_LOG_DIR` or `TRACELENS_LOG_FILE`).
  - **Reports & Exports**: Saved to your current working directory by default unless `--output-dir` (`report`) or `-o` (`export`) is specified.
- **Runtime Limitations**:
  - The `onedir` distribution requires `TraceLens.exe` and its sibling `_internal/` directory to remain in the same folder.
  - In-place metadata write-back is not supported for Excel (`.xlsx`) or PowerPoint (`.pptx`) files.
  - GUI-only PDF page image preview (`pdf2image`) is not included in the headless CLI.

#### Quick Examples & Unified Help System
```bash
tracelens help                  # Display full table-based CLI workflow & command reference
tracelens --help                # Display the same canonical CLI workflow & command reference
tracelens extract --help        # Display detailed argparse options & examples for 'extract'
tracelens help extract          # Display deep-dive topic guide for 'extract'
tracelens extract example.jpg
tracelens analyze example.jpg
tracelens search confidential
tracelens report 17
tracelens batch ./samples
tracelens --version
tracelens -v extract example.jpg
```

#### Global Options
- `-h, --help`: Display the canonical TraceLens workflow and command reference (or per-command options via `tracelens <command> --help`) and exit.
- `-V, --version`: Display the TraceLens version string (`TraceLens 2.0.0`) and exit.
- `-v, --verbose`: Enable verbose diagnostic logging (`[INFO]` / `[DEBUG]`) and include detailed tracebacks on unexpected errors.
- `-q, --quiet`: Suppress banners and non-critical messages.
- `--db-path PATH`: Use a custom SQLite database file path.

#### Verbose Mode
Passing `-v` or `--verbose` activates step-by-step diagnostic logging via Python's `logging` framework without altering the underlying operation:
```text
[INFO] Validating file: example.jpg
[INFO] File size: 18432 bytes
[INFO] Extracting metadata
[INFO] Storing metadata in database
✓ Metadata extraction completed
```

#### Exit Codes
| Exit Code | Constant | Meaning |
|---|---|---|
| `0` | `EXIT_SUCCESS` | Command completed successfully |
| `1` | `EXIT_GENERAL_ERROR` | General or unexpected runtime error |
| `2` | `EXIT_INVALID_ARGS` | Invalid command, missing argument, or invalid parameter value |
| `3` | `EXIT_FILE_ERROR` | File or directory path error (missing, wrong type, or unreadable) |
| `4` | `EXIT_DATABASE_ERROR` | Database lookup or storage failure |
| `5` | `EXIT_REPORT_ERROR` | Report generation or dataset export failure |

#### Command Reference

##### 1. Extract Metadata (`tracelens extract`)
Extract metadata from one or more files and store records in SQLite:
```bash
# Single file extraction (outputs concise summary)
tracelens extract document.pdf

# Show full metadata key-value table in addition to summary
tracelens extract document.pdf --details

# Extract without persisting to database
tracelens extract sample.jpg --no-save

# Recursive folder extraction
tracelens extract ./evidence_folder/ --recursive
```

##### 2. Batch Directory Processing (`tracelens batch`)
Process all files in a directory with per-file progress (`Processing 1/N: ...`) and risk aggregation:
```bash
# Batch extract and analyze a directory recursively
tracelens batch ./samples

# Process top-level directory only without saving to database
tracelens batch ./samples --flat --no-save
```

##### 3. Analyze Risk & Anomalies (`tracelens analyze`)
Run privacy scoring, anomaly detection, and timeline analysis:
```bash
# Analyze a single file
tracelens analyze photo.jpg

# Batch analyze folder with summary distribution
tracelens analyze ./documents/ --recursive
```

##### 4. Search Metadata Records (`tracelens search`)
Search historical records in the SQLite database by keyword query:
```bash
# Search records by keyword
tracelens search confidential

# Filter search by file type and limit results
tracelens search invoice --file-type pdf --limit 10
```

##### 5. Edit & Sanitize Metadata (`tracelens edit`, `tracelens sanitize`)
Modify or strip metadata fields and write changes back to the source file:
```bash
# Strip sensitive metadata tags (creates .bak backup by default)
tracelens sanitize photo.jpg

# Update individual keys
tracelens edit document.pdf --set Author="Jane Doe" --set Title="Sanitized Report"

# Merge metadata updates from a JSON file
tracelens edit sample.docx --metadata-file updates.json

# Modify database record only without altering physical file
tracelens edit sample.jpg --set Camera="Redacted" --no-write-file
```

##### 6. Generate Reports (`tracelens report`)
Render formatted text and PDF dossiers from a database record ID or file path:
```bash
# Generate report from historical database record ID
tracelens report 17

# Generate PDF report for a record ID into a custom directory
tracelens report 42 --format pdf --output-dir ./dossiers/

# Generate TXT and PDF reports directly from a file
tracelens report document.pdf --format both --output-dir ./reports/
```

##### 7. Browse & Manage History (`tracelens history`)
Query and maintain historical extractions stored in SQLite:
```bash
# View recent history records
tracelens history --limit 20

# Filter history records
tracelens history --query "financial" --file-type pdf --date-filter "Last 30 Days"

# Display database record count and distribution statistics
tracelens history stats

# Delete a specific record by ID
tracelens history delete 14 --yes

# Clear all historical records
tracelens history clear --yes
```

##### 8. Export Historical Datasets (`tracelens export`)
Export filtered database rows into structured formats:
```bash
# Export to JSON
tracelens export json --output history_dump.json

# Export to Excel workbook with query filter
tracelens export excel --query "confidential" --output audit.xlsx

# Export to CSV or XML
tracelens export csv --output export.csv
tracelens export xml --output export.xml
```

##### 9. Analytics, Diagnostics & Logging (`tracelens analytics`, `tracelens logs`, `tracelens config`)
Inspect aggregate metrics, runtime configurations, and log buffers:
```bash
# View analytics dashboard metrics
tracelens analytics

# View recent application logs
tracelens logs --lines 100

# Print active log file path
tracelens logs --path

# Optimize SQLite database storage
tracelens config optimize
```

---

### Batch Processing Workflow

To audit extensive directory trees containing heterogeneous file types:

1. **CLI Execution**:
   ```bash
   tracelens batch /path/to/evidence/
   tracelens analyze /path/to/evidence/ --recursive
   ```
   TraceLens reports per-file progress (`Processing 1/N: filename`), isolates individual file failures so the batch continues uninterrupted, calculates anomaly penalties across all detected items, and generates an aggregated summary breakdown (`Total`, `Successful`, `Failed`, and `LOW` / `MEDIUM` / `HIGH` risk counts).

2. **GUI Execution**:
   - Open **Batch Process** from the top menu bar.
   - Choose the root directory and select recursive traversal.
   - The engine processes files in the background, continuously updating the live progress dialog and outputting a comprehensive batch report summary.

---

## Python API & Service Layer

TraceLens can be imported directly into Python applications as a library.

### Using the Service Container Facade

```python
from src.core.services.container import get_service_container

# Initialize unified service container
container = get_service_container()

# Execute complete pipeline (Extraction + Risk Assessment + SQLite Persistence)
result = container.process_file_pipeline("evidence.pdf", persist=True, analyze_risk=True)

if result["success"]:
    extraction_data = result["extraction"]
    risk_data = result["risk"]
    
    print(f"File Name: {extraction_data.file_name}")
    print(f"Risk Score: {risk_data.risk_score}/100 ({risk_data.risk_level})")
    print("Triggered Rules:", risk_data.reasons)
    print("Timeline Events:", len(risk_data.timeline))
```

### Direct Module Usage

```python
from src.core.extractor import extractor
from src.core.risk import risk_analyzer
from src.core.reports import report
from src.core.database import db

# 1. Extract metadata
metadata = extractor.extract("sample_photo.jpg")

# 2. Evaluate risk and detect anomalies
analysis = risk_analyzer.analyze_metadata(metadata, "sample_photo.jpg")
print(f"Risk Level: {analysis['risk_level']}, Score: {analysis['risk_score']}")

# 3. Generate formatted reports
report_text = report.generate_report_text(
    extracted_metadata=metadata,
    file_path="sample_photo.jpg",
    risk_analysis=analysis,
)
report.create_pdf_report_from_text(
    metadata_text=report_text,
    file_path="audit_report.pdf",
)

# 4. Query SQLite persistence
recent_records = db.db_manager.get_recent_records(limit=10)
```

---

## Risk Scoring & Forensic Engine

The TraceLens risk engine computes an aggregate threat score on a scale from 0 to 100 based on weighted rule definitions in `src/core/risk/rules.yaml`.

### Threat Level Thresholds
- **LOW (0 - 29)**: Minimal exposure; standard operational metadata.
- **MEDIUM (30 - 64)**: Moderate exposure; contains identifiable creator tags, software versions, or internal network references.
- **HIGH (65 - 100)**: Severe privacy exposure; contains precise GPS geolocation, unique hardware identifiers, or critical timeline anomalies.

### Rule Categories

| Category ID | Weight | Target Triggers & Monitored Keys | Remediation Recommendation |
|---|---|---|---|
| `geolocation` | 30 pts | `gps`, `latitude`, `longitude`, `altitude`, geo-regex patterns | Strip GPS coordinates before public sharing to prevent physical location exposure. |
| `identity` | 18 pts | `author`, `creator`, `owner`, `user`, `last modified by`, `artist` | Remove user identity and personal account names to protect identity. |
| `hardware` | 18 pts | `device`, `camera`, `model`, `serial`, `imei`, `make`, `lens` | Clear device serial numbers and hardware identifiers. |
| `software` | 15 pts | `software`, `application`, `producer`, `editor`, `history`, `tool` | Scrub editing application versions and revision history from document headers. |
| `forensic` | 20 pts | `xmp`, `iptc`, `exif`, `makernote`, `thumbnail`, `private tag` | Sanitize embedded metadata blocks prior to distribution. |
| `privacy` | 15 pts | `http://`, `https://`, `\\unc_path\`, `ip address`, `host`, `server` | Remove sensitive intranet URLs, hostnames, and IP paths. |
| `security` | 10 pts | `signature`, `certificate`, `cert`, `signer`, `fingerprint` | Verify if digital signatures expose internal enterprise PKI architecture. |

### Forensic Anomaly Detection

TraceLens inspects chronological events and software attributes to flag potential file anomalies:

1. **Timestamp Inversion**:
   Triggers when a file modification or last-save timestamp chronologically precedes its creation or capture timestamp, highlighting timestamp discrepancies or out-of-order edits.
2. **Multiple Editing Chains**:
   Triggers when software metadata references two or more distinct editing applications or tools (`min_distinct: 2` in `rules.yaml`), indicating multiple revision cycles.
3. **Stacked Metadata Blocks**:
   Triggers when three or more distinct metadata container keywords (e.g., EXIF, IPTC, XMP, MakerNotes) are detected within extracted keys (`min_count: 3` in `rules.yaml`).

**Scoring Penalty**:
When one or more anomalies are detected, the engine applies a configurable flat anomaly penalty (`scoring.anomaly_penalty`, default: 20 points in `rules.yaml`) to the total score, capped at `max_score` (100).

---

## Database Schema & Persistence

TraceLens stores extraction history in a local SQLite database (`file_metadata.db`). The default database location is user-writable (under `AppData/Local/TraceLens` on Windows or `.local/share/TraceLens` on Linux/macOS), and can be customized via the `--db-path` CLI flag or `TRACELENS_DB_PATH` environment variable.

### Schema Definition

```sql
CREATE TABLE IF NOT EXISTS metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_size_formatted TEXT,
    file_type TEXT,
    extracted_at TEXT NOT NULL,
    modified_on TEXT,
    full_metadata TEXT NOT NULL
);
```

### Field Specifications
- `id`: Auto-incrementing primary key.
- `file_path`: Filesystem path to the analyzed asset.
- `file_name`: Basename of the file.
- `file_size_formatted`: Human-readable size string (e.g., `4.2 MB`).
- `file_type`: Normalized file extension identifier (e.g., `pdf`, `jpg`).
- `extracted_at`: ISO 8601 UTC timestamp of the extraction operation.
- `modified_on`: Filesystem last modification timestamp.
- `full_metadata`: Serialized JSON payload containing complete key-value extraction trees.

*Note: Database searches perform SQL `LIKE` filtering across `file_name` and `file_path`. Risk scores are evaluated dynamically by the risk engine and are not stored in database columns.*

---

## Future Roadmap & Version 3.0 Plan: TraceAi

> [!NOTE]
> TraceLens Version 2.0 is entirely deterministic, local, and rule-based with no external AI or cloud API dependencies. The TraceAi capabilities detailed below represent architectural plans for Version 3.0 and are not part of the current v2.0 release.

Version 3.0 is planned to introduce **TraceAi**, an optional context-driven AI forensic assistant and conversational copilot integrated into TraceLens. Planned integrations leverage the **Google Gemini API** (`google-genai` SDK), combining large-context reasoning with multimodal understanding to assist metadata investigations.

```text
+-----------------------------------------------------------------------------+
|                           TraceAi SUBSYSTEM (v3.0)                          |
|                                                                             |
|   +-------------------+  +--------------------+  +----------------------+   |
|   |   GUI Chat Tab    |  |  CLI `tracelens ai`|  |  Automated Reporter  |   |
|   +---------|---------+  +---------|----------+  +----------|-----------+   |
|             |                      |                        |               |
|             +----------------------+------------------------+               |
|                                    |                                        |
|                                    v                                        |
|                  +-----------------------------------+                      |
|                  |     TraceAi Context Synthesizer   |                      |
|                  |  - Local PII Masking Engine       |                      |
|                  |  - Metadata Tree Serializer       |                      |
|                  |  - Forensic Timeline Assembler    |                      |
|                  |  - Anomaly & Rule Grounding State |                      |
|                  +-----------------|-----------------+                      |
|                                    |                                        |
|                                    v                                        |
|                  +-----------------------------------+                      |
|                  |         Google Gemini API         |                      |
|                  |   - Gemini 2.0 Flash / Pro        |                      |
|                  |   - Multimodal Image Grounding    |                      |
|                  |   - Structured Forensic Analysis  |                      |
|                  +-----------------------------------+                      |
+-----------------------------------------------------------------------------+
```

### Key Capabilities Planned for TraceAi in Version 3.0

#### 1. Context-Driven Natural Language Forensics
- **Conversational Queries**: Ask investigative questions in plain English:
  - *"Which files in this batch contain geolocation coordinates outside the United States?"*
  - *"Explain why this PDF triggered a Timestamp Inversion anomaly."*
  - *"Compare the metadata profiles of file_A.docx and file_B.docx and identify discrepancies."*
- **Context Injection Engine**: TraceAi automatically aggregates extracted metadata fields, calculated risk scores, triggered YAML rules, and chronological timeline events into the Gemini context window.

#### 2. Multimodal Cross-Verification via Gemini Vision
- Leverage Gemini's native multimodal capabilities to cross-examine visual image content against internal EXIF metadata.
- Automatically flag semantic mismatches (e.g., EXIF GPS points to a desert while image pixels show an indoor office, or EXIF capture date is 2010 while image features modern vehicles/devices).

#### 3. Automated Forensic Dossier Synthesis & Compliance Auditing
- Generate executive-level incident summaries and compliance assessments tailored to regulatory frameworks (GDPR Article 32, HIPAA Security Rule, CCPA, FOIA declassification standards).
- Context-aware remediation: TraceAi generates executable sanitization strategies and step-by-step commands to strip sensitive tags without destroying evidentiary value.

#### 4. Natural Language Search Across Historical Archives
- Query thousands of historical SQLite metadata records using natural language semantics instead of structured SQL queries:
  - *"Find all Canon camera photos extracted last month that included serial numbers."*

#### 5. Privacy-Preserving AI Architecture
- **Local PII Redaction**: Sensitive personal identifiers (such as local usernames, private intranet IPs, and specific author names) can be locally masked or tokenized prior to dispatching queries to the Gemini API.
- **BYOK (Bring Your Own Key)**: Support for user-provided Gemini API keys stored securely using platform-native encrypted keyrings.

---

## Testing & Quality Assurance

TraceLens includes an automated test suite of **225 tests** built with **pytest**, covering unit tests, service layer pipelines, CLI commands, database transactions, format parsers, and GUI components.

### Running the Test Suite

```bash
# Execute all tests
pytest

# Run tests with verbose output
pytest -v

# Generate coverage reports (requires pytest-cov: pip install pytest-cov)
pytest --cov=src --cov-report=term-missing
pytest --cov=src --cov-report=html
```

### Running Specific Test Modules

```bash
# Test the YAML risk rules engine and anomaly detector
pytest tests/test_risk_engine.py tests/test_risk_analyzer.py -v

# Test the CLI interface and commands
pytest tests/test_cli.py -v

# Test the SQLite database manager
pytest tests/test_db.py -v

# Test format extractors and parsers
pytest tests/test_extractor.py -v

# Test metadata editor and write-back routines
pytest tests/test_editor.py -v

# Test PDF and multi-format report generation
pytest tests/test_report.py -v

# Test GUI tabs and batch process dialogs
pytest tests/test_gui.py tests/test_gui_tabs.py tests/test_batch_process_dialog.py -v
```

---

## Troubleshooting

### Installation & Environment

- **Tkinter Missing on Linux**:
  - *Symptom*: `ModuleNotFoundError: No module named 'tkinter'`
  - *Fix*: Install Tkinter via system package manager: `sudo apt-get install python3-tk` (Ubuntu/Debian) or `sudo dnf install python3-tkinter` (Fedora).

- **PDF Preview Generation Fails**:
  - *Symptom*: `PDFInfoNotInstalledError: Unable to get page count. Is poppler installed and in PATH?`
  - *Fix*: Install Poppler utilities (`sudo apt-get install poppler-utils` on Linux, `brew install poppler` on macOS, or download Windows binaries and add to system `PATH`).

- **PowerShell Execution Policy Error**:
  - *Symptom*: `.venv\Scripts\Activate.ps1 cannot be loaded because running scripts is disabled on this system.`
  - *Fix*: Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` in PowerShell.

### Runtime Operations

- **Database Locked (`sqlite3.OperationalError: database is locked`)**:
  - *Cause*: Multiple concurrent processes writing to the database file simultaneously.
  - *Fix*: Close auxiliary instances or optimize the database using `tracelens config optimize`.

- **Metadata Write-Back Fails on Protected Files**:
  - *Cause*: Target file has read-only filesystem attributes or is locked by another open application.
  - *Fix*: Ensure write permissions are granted (`chmod u+w filename` on Linux/macOS) and close any viewer locking the file.

---

## Known Limitations

1. **Encrypted Documents**: Password-protected PDFs and encrypted Office documents cannot be parsed without valid decryption credentials.
2. **Write-Back Format Support**: In-place binary write-back is implemented for PDFs (`.pdf`), PNG text chunks (`.png`), Word documents (`.docx`), audio tags (`.mp3`, `.flac`, `.m4a`, `.ogg`), and text comments. Other formats—including Excel spreadsheets (`.xlsx`), PowerPoint presentations (`.pptx`), and generic binaries—do not support in-place writing and persist metadata via companion `.meta.json` sidecar files.
3. **Image EXIF Write-Back**: Writing metadata to JPEG and TIFF files serializes the metadata payload into the standard EXIF `UserComment` tag (via `piexif`) rather than rewriting individual device, camera, or lens tags in-place.
4. **Specialized Archive Formats**: Specialized member enumeration is provided for `.zip` and `.tar` archives (`.tar.gz`, `.tar.bz2`, `.tar.xz`, `.tgz`). Other archives (`.7z`, `.rar`) fall back to universal binary stream inspection.
5. **Database Search Scope**: SQLite search queries perform SQL `LIKE` pattern matching over `file_name` and `file_path`. Full-text indexing over raw nested JSON metadata and querying directly by risk score are not implemented in the database schema (risk scores are computed dynamically).
6. **Headless Report Preview**: Document preview in the GUI relies on `pdf2image` and requires Poppler binaries installed on the host system PATH along with an active graphical display session.

---

## Contributing

Contributions to TraceLens are welcome. To contribute:

1. Fork the repository on GitHub.
2. Create a feature branch: `git checkout -b feature/new-format-parser`.
3. Ensure all tests pass: `pytest`.
4. Commit changes following conventional commit syntax: `git commit -m 'feat: add WebM video parser'`.
5. Push to your branch and open a Pull Request.

Please review [CONTRIBUTING.md](CONTRIBUTING.md) for coding standards, type annotation rules, and architectural guidelines.

---

## License & Contact

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for complete details.

### Contact & Support
- **Author**: Tanmay Bhatnagar
- **Email**: tanmaybhatnagar760@gmail.com
- **Repository**: [GitHub - TraceLens](https://github.com/Tanmay-Bhatnagar22/TraceLens)
- **Issue Tracker**: [GitHub Issues](https://github.com/Tanmay-Bhatnagar22/TraceLens/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Tanmay-Bhatnagar22/TraceLens/discussions)

---

<div align="center">
TraceLens: Metadata Analysis & Privacy Inspection Toolkit | Version 2.0.0
</div>
