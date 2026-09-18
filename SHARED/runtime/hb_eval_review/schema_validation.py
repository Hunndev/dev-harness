"""Validate the harness's local JSON Schema subset without optional dependencies.

Unknown validation keywords fail closed, including in unselected conditional branches.
Only the annotation keywords listed below are ignored. This is deliberately not a
general JSON Schema implementation; contracts adding other keywords must extend it.
"""

import copy
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List


_ANNOTATIONS = {"$schema", "$id", "$comment", "title", "description", "default", "examples"}
_KEYWORDS = {"type", "const", "enum", "required", "additionalProperties", "properties", "items",
             "minItems", "minLength", "minimum", "pattern", "allOf", "if", "then", "else", "not"}
_TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}
_TDD_SCHEMAS = {"tdd-test-design-result.schema.json", "tdd-sensitivity-result.schema.json"}


def _load_schema(schema_name: str) -> Dict[str, Any]:
    if not isinstance(schema_name, str) or Path(schema_name).name != schema_name:
        raise ValueError("schema must name a local contract")
    # Shared and vendored runtimes both keep contracts next to their runtime directory.
    contracts = Path(__file__).resolve().parents[2] / "contracts"
    return json.loads((contracts / schema_name).read_text(encoding="utf-8"))


def _schema_errors(schema: Any, path: str = "$") -> List[str]:
    if isinstance(schema, bool):
        return []
    if not isinstance(schema, dict):
        return ["SCHEMA_INVALID:" + path]
    errors = ["SCHEMA_UNSUPPORTED:" + path + ":" + key
              for key in schema if key not in _KEYWORDS | _ANNOTATIONS]
    declared_type = schema.get("type")
    if declared_type is not None and (not isinstance(declared_type, str) or declared_type not in _TYPES):
        errors.append("SCHEMA_INVALID:" + path + ":type")
    for keyword in ("minItems", "minLength"):
        if keyword in schema and (type(schema[keyword]) is not int or schema[keyword] < 0):
            errors.append("SCHEMA_INVALID:" + path + ":" + keyword)
    if "minimum" in schema and (type(schema["minimum"]) not in (int, float) or not math.isfinite(schema["minimum"])):
        errors.append("SCHEMA_INVALID:" + path + ":minimum")
    if "pattern" in schema:
        try:
            re.compile(schema["pattern"])
        except (TypeError, re.error):
            errors.append("SCHEMA_INVALID:" + path + ":pattern")
    if "required" in schema and (not isinstance(schema["required"], list)
                                  or not all(isinstance(key, str) for key in schema["required"])):
        errors.append("SCHEMA_INVALID:" + path + ":required")
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        errors.append("SCHEMA_INVALID:" + path + ":enum")
    if "properties" in schema:
        if not isinstance(schema["properties"], dict):
            errors.append("SCHEMA_INVALID:" + path + ":properties")
        else:
            for key, child in schema["properties"].items():
                errors.extend(_schema_errors(child, path + ".properties." + key))
    for keyword in ("items", "additionalProperties", "if", "then", "else", "not"):
        if keyword in schema:
            errors.extend(_schema_errors(schema[keyword], path + "." + keyword))
    if "allOf" in schema:
        if not isinstance(schema["allOf"], list) or not schema["allOf"]:
            errors.append("SCHEMA_INVALID:" + path + ":allOf")
        else:
            for index, child in enumerate(schema["allOf"]):
                errors.extend(_schema_errors(child, path + ".allOf[" + str(index) + "]"))
    return errors


def _equal(left: Any, right: Any) -> bool:
    """JSON equality keeps booleans distinct from numbers, including nested values."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_equal(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_equal(a, b) for a, b in zip(left, right))
    return left == right


def _matches_type(value: Any, expected: str) -> bool:
    return {"object": isinstance(value, dict), "array": isinstance(value, list),
            "string": isinstance(value, str), "integer": type(value) is int,
            "number": type(value) in (int, float), "boolean": type(value) is bool,
            "null": value is None}[expected]


def _validate(data: Any, schema: Any, path: str = "$") -> List[str]:
    if schema is True:
        return []
    if schema is False:
        return ["SCHEMA_FALSE:" + path]
    errors: List[str] = []
    if "type" in schema and not _matches_type(data, schema["type"]):
        return ["SCHEMA_TYPE:" + path]
    if "const" in schema and not _equal(data, schema["const"]):
        errors.append("SCHEMA_CONST:" + path)
    if "enum" in schema and not any(_equal(data, item) for item in schema["enum"]):
        errors.append("SCHEMA_ENUM:" + path)
    if isinstance(data, dict):
        for key in schema.get("required", []):
            if key not in data:
                errors.append("SCHEMA_REQUIRED:" + path + "." + key)
        properties = schema.get("properties", {})
        for key, value in data.items():
            if key in properties:
                errors.extend(_validate(value, properties[key], path + "." + key))
            elif "additionalProperties" in schema:
                errors.extend(_validate(value, schema["additionalProperties"], path + "." + key))
    if isinstance(data, list):
        if len(data) < schema.get("minItems", 0):
            errors.append("SCHEMA_MIN_ITEMS:" + path)
        if "items" in schema:
            for index, value in enumerate(data):
                errors.extend(_validate(value, schema["items"], path + "[" + str(index) + "]"))
    if isinstance(data, str):
        if len(data) < schema.get("minLength", 0):
            errors.append("SCHEMA_MIN_LENGTH:" + path)
        if "pattern" in schema and re.search(schema["pattern"], data) is None:
            errors.append("SCHEMA_PATTERN:" + path)
    if type(data) in (int, float) and "minimum" in schema and data < schema["minimum"]:
        errors.append("SCHEMA_MINIMUM:" + path)
    for child in schema.get("allOf", []):
        errors.extend(_validate(data, child, path))
    if "if" in schema:
        branch = "else" if _validate(data, schema["if"], path) else "then"
        if branch in schema:
            errors.extend(_validate(data, schema[branch], path))
    if "not" in schema and not _validate(data, schema["not"], path):
        errors.append("SCHEMA_NOT:" + path)
    return errors


def validate_schema(data: Any, schema_name: str) -> List[str]:
    """Return structural errors for a local contract; an empty list means valid.

    Historical TDD 1.0 evidence retains its original RED_TO_GREEN-only contract.
    Semantic TDD checks remain the responsibility of tdd_quality validators.
    """
    try:
        schema = _load_schema(schema_name)
        errors = _schema_errors(schema)
        if errors:
            return errors
        if schema_name in _TDD_SCHEMAS and isinstance(data, dict) and data.get("schema_version") == "1.0":
            schema = copy.deepcopy(schema)
            schema["properties"]["schema_version"] = {"const": "1.0"}
            schema["properties"].pop("baseline", None)
            schema["required"] = [key for key in schema["required"] if key != "baseline"]
            schema.pop("allOf", None)
            if schema_name == "tdd-test-design-result.schema.json":
                if "red_failure_kind" not in schema["required"]:
                    schema["required"].append("red_failure_kind")
            else:
                schema["properties"]["red_outcome"] = {"const": "FAIL"}
        # Reject values outside JSON, nonfinite numbers, and malformed Unicode.
        json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return list(dict.fromkeys(_validate(data, schema)))
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return ["SCHEMA_UNAVAILABLE:" + str(schema_name)]
