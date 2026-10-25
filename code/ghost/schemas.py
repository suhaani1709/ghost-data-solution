"""Explicit JSON schemas for every structured model answer, and a small validator (stdlib only).

The agents never trust a model answer's shape: each item is checked with `errors()` before use.
An answer that fails its schema is treated as "no answer" (the deterministic rules or the
development transcript decide) and is counted, so a malformed reply can never silently change
the output. Supported keywords: type, enum, required, properties, items, pattern, minimum.
"""
from __future__ import annotations

import re
from typing import Any

from . import parse_common as pc

_TYPES = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool}

INTENT_LABELS = ("DELETE", "NON_DELETE", "UNSURE")
INTENT_ITEM = {
    "type": "object", "required": ["id", "label"],
    "properties": {"id": {"type": "integer", "minimum": 1},
                   "label": {"type": "string", "enum": list(INTENT_LABELS)},
                   "reason": {"type": "string"}},
}

VISION_STATES = ("PRESENT", "IDENTIFIABLE", "ANONYMIZED", "REDACTED", "ABSENT", "ACTIVE", "DISABLED",
                 "BLOCKED", "REFERENCED")
VISION_ROW = {
    "type": "object", "required": ["resource_id", "role", "state"],
    "properties": {"row": {"type": "string"}, "system_id": {"type": "string"},
                   "resource_id": {"type": "string", "pattern": pc.RESOURCE_ID.pattern},
                   "role": {"type": "string", "pattern": r"OWN|REF:.*"},
                   "user_id": {"type": "string"}, "email": {"type": "string"}, "phone": {"type": "string"},
                   "state": {"type": "string", "enum": list(VISION_STATES)},
                   "category": {"type": "string"}},
}
VISION_ANSWER = {
    "type": "object", "required": ["rows"],
    "properties": {"rows": {"type": "array", "items": VISION_ROW},
                   "unreadable": {"type": "array", "items": {"type": "string"}}},
}

INVESTIGATOR_TOOLS = ("record_history", "search_identifier", "read_evidence", "account_candidates", "policy",
                      "submit")
INVESTIGATOR_ACTION = {
    "type": "object", "required": ["action", "args"],
    "properties": {"thought": {"type": "string"},
                   "action": {"type": "string", "enum": list(INVESTIGATOR_TOOLS)},
                   "args": {"type": "object"}},
}


def errors(value: Any, schema: dict, path: str = "$") -> list[str]:
    """Every violation of `schema` in `value`, as 'path: message' strings ([] = valid)."""
    out: list[str] = []
    expected = schema.get("type")
    if expected:
        py = _TYPES[expected]
        if not isinstance(value, py) or (expected == "integer" and isinstance(value, bool)):
            return [f"{path}: expected {expected}"]
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{path}: {value!r} not in {schema['enum']}")
    if "pattern" in schema and isinstance(value, str) and not re.fullmatch(schema["pattern"], value):
        out.append(f"{path}: {value!r} does not match {schema['pattern']}")
    if "minimum" in schema and isinstance(value, int) and value < schema["minimum"]:
        out.append(f"{path}: {value} < {schema['minimum']}")
    if isinstance(value, dict):
        for key in schema.get("required", ()):
            if key not in value:
                out.append(f"{path}.{key}: required")
        for key, sub in schema.get("properties", {}).items():
            if key in value and value[key] is not None:
                out += errors(value[key], sub, f"{path}.{key}")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            out += errors(item, schema["items"], f"{path}[{i}]")
    return out
