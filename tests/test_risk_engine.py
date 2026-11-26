"""Comprehensive tests for the YAML-based Risk Engine and Forensic Scanner."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import pytest
from src.core.risk import (
    PrivacyForensicAnalyzer,
    RiskEngine,
    RiskRuleDefinition,
    RuleCondition,
    RuleSet,
    ThresholdConfig,
    YamlRiskEngine,
    analyze_batch,
    analyze_metadata,
    dump_yaml,
    load_yaml_file,
    load_yaml_string,
    validate_rules_schema,
)
from src.core.risk.yaml_parser import _builtin_yaml_dump, _builtin_yaml_load
from src.core.services.risk_service import RiskAnalysisService


def test_risk_engine_default_initialization():
    """Verify default RiskEngine loads default rules.yaml successfully."""
    engine = RiskEngine()
    assert len(engine.rules) >= 5
    assert any(r.id == "gps_coordinates" for r in engine.rules)
    assert any(r.id == "author_identity" for r in engine.rules)
    assert any(r.id == "device_information" for r in engine.rules)
    assert any(r.id == "editing_traces" for r in engine.rules)
    assert any(r.id == "hidden_blocks" for r in engine.rules)


def test_analyze_file_high_risk():
    """Test evaluating metadata with multiple high-risk indicators."""
    engine = RiskEngine()
    metadata = {
        "GPS Latitude": "28.6139",
        "GPS Longitude": "77.2090",
        "Author": "John Doe",
        "Camera Model": "Sony A7IV",
        "Software": "Adobe Photoshop 2024",
        "XMP": "Embedded Block",
    }
    result = engine.analyze_file(metadata, "C:/photos/test.jpg")

    assert result["risk_score"] >= 65
    assert result["risk_level"] == "HIGH"
    assert "gps_coordinates" in result["matched_rules"]
    assert "author_identity" in result["matched_rules"]
    assert len(result["reasons"]) >= 4
    assert len(result["sensitive_keys"]) > 0
    assert len(result["remediation_suggestions"]) > 0


def test_analyze_file_low_risk():
    """Test evaluating metadata with benign/no sensitive indicators."""
    engine = RiskEngine()
    metadata = {
        "File Size": "1024 B",
        "Encoding": "utf-8",
        "Line Count": 42,
    }
    result = engine.analyze_file(metadata, "C:/docs/readme.txt")

    assert result["risk_score"] == 0
    assert result["risk_level"] == "LOW"
    assert len(result["matched_rules"]) == 0
    assert "No high-sensitivity" in result["reasons"][0]


def test_custom_yaml_rules_loading():
    """Test loading and evaluating custom YAML rules from string."""
    custom_yaml = """
version: "1.0"
name: "Custom Corporate Privacy Rules"
thresholds:
  low:
    min: 0
    max: 20
    label: "SAFE"
  medium:
    min: 21
    max: 50
    label: "WARNING"
  high:
    min: 51
    max: 100
    label: "DANGER"
rules:
  - id: "confidential_marker"
    name: "Confidentiality Marker"
    score: 60
    severity: "HIGH"
    reason: "Document is marked confidential."
    remediation: "Redact confidentiality labels before public disclosure."
    conditions:
      any:
        - match_type: "value_contains"
          tokens: ["confidential", "secret", "restricted", "internal only"]
"""
    engine = RiskEngine()
    engine.load_rules_yaml(custom_yaml)

    assert len(engine.rules) == 1
    assert engine.rules[0].id == "confidential_marker"

    # Test match
    result = engine.analyze_file({"Classification": "Internal Only", "Author": "Alice"})
    assert result["risk_score"] == 60
    assert result["risk_level"] == "DANGER"
    assert "confidential_marker" in result["matched_rules"]

    # Test non-match
    result_clean = engine.analyze_file({"Classification": "Public", "Author": "Alice"})
    assert result_clean["risk_score"] == 0
    assert result_clean["risk_level"] == "SAFE"


def test_rule_conditions_types():
    """Test various RuleCondition evaluation logic (value_regex, key_regex, key_equals, exists, all, none)."""
    engine = RiskEngine()

    # Rule with ALL condition
    rule_all = RiskRuleDefinition(
        id="all_check",
        score=25,
        reason="Matched all keys",
        condition=RuleCondition(
            all=[
                RuleCondition(match_type="exists", keys=["project"]),
                RuleCondition(match_type="value_regex", pattern=r"^v\d+\.\d+"),
            ]
        ),
    )
    engine.add_rule(rule_all)

    # Test matches when both match
    res_pass = engine.analyze_file({"project": "TraceLens", "version": "v2.0"})
    assert "all_check" in res_pass["matched_rules"]

    # Test fails when one is missing
    res_fail = engine.analyze_file({"project": "TraceLens", "version": "alpha"})
    assert "all_check" not in res_fail["matched_rules"]

    # Rule with NONE condition
    rule_none = RiskRuleDefinition(
        id="none_check",
        score=15,
        reason="Safe from forbidden terms",
        condition=RuleCondition(
            none=[
                RuleCondition(match_type="key_contains", keys=["secret", "password"]),
            ]
        ),
    )
    engine.add_rule(rule_none)
    assert "none_check" in engine.analyze_file({"Title": "Public Doc"})["matched_rules"]
    assert "none_check" not in engine.analyze_file({"Password": "123"})["matched_rules"]


def test_dynamic_rule_management():
    """Test adding, removing, enabling, disabling, and exporting rules."""
    engine = RiskEngine()
    initial_count = len(engine.rules)

    new_rule = RiskRuleDefinition(
        id="test_rule",
        name="Test Rule",
        score=50,
        reason="Test reason",
        condition=RuleCondition(match_type="key_contains", keys=["test_key"]),
    )
    engine.add_rule(new_rule)
    assert len(engine.rules) == initial_count + 1
    assert engine.get_rule("test_rule") is not None

    # Disable rule
    assert engine.enable_rule("test_rule", False) is True
    res = engine.analyze_file({"test_key": "val"})
    assert "test_rule" not in res["matched_rules"]

    # Re-enable rule
    assert engine.enable_rule("test_rule", True) is True
    res2 = engine.analyze_file({"test_key": "val"})
    assert "test_rule" in res2["matched_rules"]

    # Remove rule
    assert engine.remove_rule("test_rule") is True
    assert len(engine.rules) == initial_count

    # Export to YAML string
    yaml_out = engine.export_rules_yaml()
    assert "version:" in yaml_out
    assert "rules:" in yaml_out


def test_timeline_and_anomaly_detection():
    """Test chronological timeline sorting and anomaly triggers."""
    engine = RiskEngine()

    # Inverted timestamp: Modified earlier than Created
    metadata = {
        "CreateDate": "2025-06-15 12:00:00",
        "ModifyDate": "2025-06-10 09:00:00",
        "Software": "Photoshop > GIMP > Illustrator",
        "XMP": "block",
        "EXIF": "block",
        "IPTC": "block",
    }
    result = engine.analyze_file(metadata, "C:/anomaly.jpg")

    assert len(result["timeline"]) == 2
    assert result["timeline"][0]["event"] == "ModifyDate"
    assert result["timeline"][1]["event"] == "CreateDate"

    # Anomalies detected
    assert len(result["anomalies"]) >= 2
    assert any("Timestamp mismatch" in a for a in result["anomalies"])
    assert any("Multiple editing chain" in a for a in result["anomalies"])
    assert any("stacked metadata blocks" in a.lower() for a in result["anomalies"])


def test_analyze_batch_aggregation():
    """Test batch analysis with folder statistics."""
    engine = RiskEngine()
    entries = [
        {"file_path": "C:/folder1/file1.jpg", "metadata": {"GPS": "10,20", "Author": "Alice"}},
        {"file_path": "C:/folder1/file2.txt", "metadata": {"Lines": 10}},
        {"file_path": "C:/folder2/file3.pdf", "metadata": {"Software": "Acrobat", "Producer": "PDFCore"}},
    ]
    summary = engine.analyze_batch(entries)

    assert summary["total_files"] == 3
    assert "C:/folder1" in summary["folders"]
    assert "C:/folder2" in summary["folders"]
    assert summary["folders"]["C:/folder1"]["total"] == 2
    assert summary["folders"]["C:/folder2"]["total"] == 1
    assert summary["highest_risk"] is not None


def test_yaml_parser_pure_python_fallback():
    """Test pure-python built-in YAML parser with complex data structures."""
    yaml_text = """
# Header comment
app_name: "TraceLens"
active: true
debug_mode: false
max_limit: 100
ratio: 3.14
items:
  - id: 1
    name: "First Item"
    tags: ["tag1", "tag2"]
  - id: 2
    name: "Second Item"
    nested:
      key_a: "val_a"
      key_b: 42
"""
    parsed = _builtin_yaml_load(yaml_text)
    assert parsed["app_name"] == "TraceLens"
    assert parsed["active"] is True
    assert parsed["debug_mode"] is False
    assert parsed["max_limit"] == 100
    assert parsed["ratio"] == 3.14
    assert len(parsed["items"]) == 2
    assert parsed["items"][0]["id"] == 1
    assert parsed["items"][1]["nested"]["key_b"] == 42

    dumped = _builtin_yaml_dump(parsed)
    assert "TraceLens" in dumped
    assert "nested:" in dumped


def test_validate_rules_schema():
    """Test rule schema validation for valid and invalid inputs."""
    valid_data = {
        "rules": [
            {"id": "r1", "name": "Rule 1", "score": 20},
            {"id": "r2", "score": 10},
        ],
        "thresholds": {"low": {"min": 0, "max": 30}},
    }
    is_valid, errors = validate_rules_schema(valid_data)
    assert is_valid is True
    assert len(errors) == 0

    invalid_data = {
        "rules": "not_a_list",
        "thresholds": "not_a_dict",
    }
    is_valid2, errors2 = validate_rules_schema(invalid_data)
    assert is_valid2 is False
    assert len(errors2) >= 2


def test_backward_compatibility_facade():
    """Test PrivacyForensicAnalyzer facade and top-level helper functions."""
    analyzer = PrivacyForensicAnalyzer()
    meta = {"Author": "Bob", "GPS Latitude": "12.34"}
    res = analyzer.analyze_file(meta, "C:/test.jpg")

    assert res["risk_level"] in ("MEDIUM", "HIGH")
    assert res["risk_score"] >= 40

    # Top-level helper functions
    res2 = analyze_metadata(meta)
    assert res2["risk_score"] == res["risk_score"]

    batch_res = analyze_batch([{"file_path": "a.jpg", "metadata": meta}])
    assert batch_res["total_files"] == 1


def test_service_integration():
    """Test RiskAnalysisService integration with YAML RiskEngine."""
    service = RiskAnalysisService()
    assert isinstance(service.engine, RiskEngine)
    assert len(service.get_active_rules()) >= 5

    meta = {"Author": "Charlie", "Device": "Pixel 8"}
    assessment = service.analyze_metadata(meta, "C:/test.png")

    assert assessment.risk_score > 0
    assert assessment.file_name == "test.png"
    assert len(assessment.sensitive_keys) >= 2

    remediations = service.get_remediation_suggestions(assessment)
    assert len(remediations) > 0
