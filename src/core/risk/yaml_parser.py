"""YAML loader, dumper, and validator for TraceLens risk rules.

Provides transparent integration with PyYAML when available, plus a robust
pure-Python fallback parser for zero-dependency operation.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from src.config.logging_config import get_logger

logger = get_logger("core.risk.yaml_parser")

try:
    import yaml as _pyyaml

    _HAS_PYYAML = True
except ImportError:  # pragma: no cover - fallback path
    _pyyaml = None
    _HAS_PYYAML = False


def _parse_scalar(val_str: str) -> Any:
    """Parse a single YAML scalar string to a typed Python object."""
    val = val_str.strip()
    if not val:
        return ""

    # Quoted strings
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]

    # Booleans & Null
    val_lower = val.lower()
    if val_lower in ("true", "yes", "on"):
        return True
    if val_lower in ("false", "no", "off"):
        return False
    if val_lower in ("null", "none", "~"):
        return None

    # Integers
    try:
        return int(val)
    except ValueError:
        pass

    # Floats
    try:
        return float(val)
    except ValueError:
        pass

    # Inline JSON list or dict: e.g. ["a", "b"] or {"a": 1}
    if (val.startswith("[") and val.endswith("]")) or (val.startswith("{") and val.endswith("}")):
        try:
            return json.loads(val)
        except Exception:
            # Fallback simple list split if json parse fails
            if val.startswith("[") and val.endswith("]"):
                items = [s.strip().strip("\"'") for s in val[1:-1].split(",") if s.strip()]
                return items

    return val


def _strip_yaml_comment(line: str) -> str:
    """Remove comments from a YAML line while respecting quoted strings."""
    in_single = False
    in_double = False
    for i, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:i]
    return line


def _builtin_yaml_load(yaml_str: str) -> dict[str, Any] | list[Any]:
    """Pure-Python indentation-based YAML parser supporting nested maps, lists, and scalars."""
    raw_lines = yaml_str.splitlines()
    cleaned_lines: list[tuple[int, str]] = []

    for raw in raw_lines:
        comment_stripped = _strip_yaml_comment(raw)
        if not comment_stripped.strip():
            continue
        indent = len(comment_stripped) - len(comment_stripped.lstrip())
        content = comment_stripped.strip()
        cleaned_lines.append((indent, content))

    if not cleaned_lines:
        return {}

    def parse_block(index: int, parent_indent: int) -> tuple[Any, int]:
        if index >= len(cleaned_lines):
            return {}, index

        first_indent, first_line = cleaned_lines[index]
        is_list = first_line.startswith("-")

        if is_list:
            result_list: list[Any] = []
            curr_idx = index

            while curr_idx < len(cleaned_lines):
                ind, line = cleaned_lines[curr_idx]
                if ind < first_indent:
                    break
                if ind == first_indent and line.startswith("-"):
                    item_content = line[1:].strip()
                    if not item_content:
                        # Nested mapping or list under this list item
                        child, next_idx = parse_block(curr_idx + 1, ind)
                        result_list.append(child)
                        curr_idx = next_idx
                    elif ":" in item_content and not (
                        (item_content.startswith('"') and item_content.endswith('"'))
                        or (item_content.startswith("'") and item_content.endswith("'"))
                    ):
                        # List item starting with a map key (e.g. "- id: gps")
                        k, v = item_content.split(":", 1)
                        k = k.strip().strip("\"'")
                        v = v.strip()

                        # Collect all map items indented under this list item
                        item_dict: dict[str, Any] = {}
                        if v:
                            item_dict[k] = _parse_scalar(v)
                            curr_idx += 1
                        else:
                            child, next_idx = parse_block(curr_idx + 1, ind + 2)
                            item_dict[k] = child
                            curr_idx = next_idx

                        # Check subsequent siblings at ind + 2 or greater
                        while curr_idx < len(cleaned_lines):
                            next_ind, next_line = cleaned_lines[curr_idx]
                            if next_ind <= ind:
                                break
                            if ":" in next_line and not next_line.startswith("-"):
                                sub_k, sub_v = next_line.split(":", 1)
                                sub_k = sub_k.strip().strip("\"'")
                                sub_v = sub_v.strip()
                                if sub_v:
                                    item_dict[sub_k] = _parse_scalar(sub_v)
                                    curr_idx += 1
                                else:
                                    child, sub_next_idx = parse_block(curr_idx + 1, next_ind)
                                    item_dict[sub_k] = child
                                    curr_idx = sub_next_idx
                            else:
                                break
                        result_list.append(item_dict)
                    else:
                        result_list.append(_parse_scalar(item_content))
                        curr_idx += 1
                elif ind > first_indent:
                    # Belonging to previous list element
                    curr_idx += 1
                else:
                    break
            return result_list, curr_idx

        else:
            result_dict: dict[str, Any] = {}
            curr_idx = index

            while curr_idx < len(cleaned_lines):
                ind, line = cleaned_lines[curr_idx]
                if ind < first_indent:
                    break
                if ind == first_indent:
                    if ":" in line and not line.startswith("-"):
                        k, v = line.split(":", 1)
                        k = k.strip().strip("\"'")
                        v = v.strip()
                        if v:
                            result_dict[k] = _parse_scalar(v)
                            curr_idx += 1
                        else:
                            child, next_idx = parse_block(curr_idx + 1, ind)
                            result_dict[k] = child
                            curr_idx = next_idx
                    else:
                        curr_idx += 1
                elif ind > first_indent:
                    curr_idx += 1
                else:
                    break
            return result_dict, curr_idx

    parsed_result, _ = parse_block(0, -1)
    return parsed_result if isinstance(parsed_result, (dict, list)) else {}


def _builtin_yaml_dump(data: Any, indent_level: int = 0) -> str:
    """Pure-Python YAML serialization generator."""
    lines: list[str] = []
    prefix = "  " * indent_level

    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, dict):
                lines.append(f"{prefix}{k}:")
                lines.append(_builtin_yaml_dump(v, indent_level + 1))
            elif isinstance(v, list):
                lines.append(f"{prefix}{k}:")
                lines.append(_builtin_yaml_dump(v, indent_level + 1))
            elif isinstance(v, bool):
                lines.append(f"{prefix}{k}: {'true' if v else 'false'}")
            elif v is None:
                lines.append(f"{prefix}{k}: null")
            elif isinstance(v, (int, float)):
                lines.append(f"{prefix}{k}: {v}")
            else:
                s = str(v)
                if any(c in s for c in ":#\n\"'[]{}"):
                    clean = s.replace('"', '\\"')
                    lines.append(f'{prefix}{k}: "{clean}"')
                else:
                    lines.append(f"{prefix}{k}: {s}")
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                first = True
                for k, v in item.items():
                    if first:
                        if isinstance(v, (dict, list)):
                            lines.append(f"{prefix}- {k}:")
                            lines.append(_builtin_yaml_dump(v, indent_level + 2))
                        else:
                            val_str = (
                                "null"
                                if v is None
                                else (
                                    "true"
                                    if v is True
                                    else ("false" if v is False else str(v))
                                )
                            )
                            if any(c in val_str for c in ":#\n\"'[]{}") and not (
                                val_str.startswith("[") or val_str.startswith("{")
                            ):
                                escaped_val = val_str.replace('"', '\\"')
                                val_str = f'"{escaped_val}"'
                            lines.append(f"{prefix}- {k}: {val_str}")
                        first = False
                    else:
                        sub_prefix = "  " * (indent_level + 1)
                        if isinstance(v, (dict, list)):
                            lines.append(f"{sub_prefix}{k}:")
                            lines.append(_builtin_yaml_dump(v, indent_level + 2))
                        else:
                            val_str = (
                                "null"
                                if v is None
                                else (
                                    "true"
                                    if v is True
                                    else ("false" if v is False else str(v))
                                )
                            )
                            if any(c in val_str for c in ":#\n\"'[]{}") and not (
                                val_str.startswith("[") or val_str.startswith("{")
                            ):
                                escaped_val = val_str.replace('"', '\\"')
                                val_str = f'"{escaped_val}"'
                            lines.append(f"{sub_prefix}{k}: {val_str}")
            elif isinstance(item, list):
                lines.append(f"{prefix}-")
                lines.append(_builtin_yaml_dump(item, indent_level + 1))
            else:
                lines.append(f"{prefix}- {_parse_scalar(str(item))}")

    return "\n".join(lines)


def load_yaml_string(yaml_text: str) -> dict[str, Any]:
    """Parse YAML text into a Python dictionary.

    Uses PyYAML if installed, falling back to the built-in parser.
    """
    if not yaml_text or not yaml_text.strip():
        return {}

    if _HAS_PYYAML and _pyyaml is not None:
        try:
            res = _pyyaml.safe_load(yaml_text)
            if isinstance(res, dict):
                return res
            if isinstance(res, list):
                return {"rules": res}
            return {}
        except Exception as exc:
            logger.warning("PyYAML failed to parse string (%s), trying fallback parser", exc)

    res = _builtin_yaml_load(yaml_text)
    if isinstance(res, dict):
        return res
    if isinstance(res, list):
        return {"rules": res}
    return {}


def load_yaml_file(file_path: str | Path) -> dict[str, Any]:
    """Read and parse a YAML file from disk into a Python dictionary."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"YAML rules file not found: {file_path}")

    content = path.read_text(encoding="utf-8")
    return load_yaml_string(content)


def dump_yaml(data: dict[str, Any], file_path: str | Path | None = None) -> str:
    """Serialize dictionary data to YAML string, optionally saving to a file."""
    if _HAS_PYYAML and _pyyaml is not None:
        try:
            rendered = _pyyaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        except Exception as exc:
            logger.warning("PyYAML dump failed (%s), using fallback dumper", exc)
            rendered = _builtin_yaml_dump(data)
    else:
        rendered = _builtin_yaml_dump(data)

    if file_path is not None:
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(rendered, encoding="utf-8")

    return rendered


def validate_rules_schema(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate loaded dictionary structure against the TraceLens rule schema.

    Returns:
        tuple of (is_valid: bool, error_messages: list[str])
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return False, ["Root YAML document must be a dictionary/mapping."]

    # Validate rules list
    rules = data.get("rules")
    if rules is not None and not isinstance(rules, list):
        errors.append("'rules' field must be a list of rule definitions.")
    elif isinstance(rules, list):
        for idx, r in enumerate(rules):
            if not isinstance(r, dict):
                errors.append(f"Rule at index {idx} must be a dictionary.")
                continue
            if not r.get("id") and not r.get("name"):
                errors.append(f"Rule at index {idx} must specify an 'id' or 'name'.")
            if "score" in r and not isinstance(r["score"], (int, float)):
                errors.append(f"Rule '{r.get('id', idx)}' score must be a number.")

    # Validate thresholds
    thresholds = data.get("thresholds")
    if thresholds is not None and not isinstance(thresholds, dict):
        errors.append("'thresholds' field must be a dictionary.")

    # Validate scoring
    scoring = data.get("scoring")
    if scoring is not None and not isinstance(scoring, dict):
        errors.append("'scoring' field must be a dictionary.")

    # Validate anomalies
    anomalies = data.get("anomalies")
    if anomalies is not None and not isinstance(anomalies, list):
        errors.append("'anomalies' field must be a list of anomaly definitions.")

    return len(errors) == 0, errors
