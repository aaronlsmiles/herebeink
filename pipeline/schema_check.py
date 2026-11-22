"""Validate a document against the project's JSON Schemas (schema/*.schema.json).

Only the keywords those schemas use are implemented; a schema using any other keyword is refused
outright rather than half-checked, so the contract can't silently loosen. (The jsonschema package would
do the same job, as a new dependency; this file is the price of not adding one.)
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np

import splats

SCHEMAS = Path(__file__).resolve().parent / "schema"
KNOWN = {"$schema", "$id", "$ref", "$defs", "title", "description", "type", "properties", "required",
         "additionalProperties", "items", "minItems", "maxItems", "minLength", "enum", "const", "minimum",
         "maximum", "exclusiveMinimum", "pattern"}
TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def load(name: str) -> dict:
    schema = json.loads((SCHEMAS / name).read_text())
    unknown = keywords(schema) - KNOWN
    if unknown:
        raise ValueError(f"{name} uses keywords this checker does not implement: {sorted(unknown)}")
    return schema


def keywords(node, inside_properties: bool = False) -> set[str]:
    out: set[str] = set()
    if isinstance(node, dict):
        for k, v in node.items():
            if not inside_properties:
                out.add(k)
            out |= keywords(v, inside_properties=k in ("properties", "$defs") and not inside_properties)
    elif isinstance(node, list):
        for v in node:
            out |= keywords(v)
    return out


def _type_ok(value, t: str) -> bool:
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, TYPES[t])


def errors(value, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    root = root or schema
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        return errors(value, target, root, path)
    out = []
    if "const" in schema and value != schema["const"]:
        return [f"{path}: must be {schema['const']!r}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}: must be one of {schema['enum']}"]
    if "type" in schema and not _type_ok(value, schema["type"]):
        return [f"{path}: must be {schema['type']}"]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            out.append(f"{path}: below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            out.append(f"{path}: above {schema['maximum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            out.append(f"{path}: must be above {schema['exclusiveMinimum']}")
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            out.append(f"{path}: does not match {schema['pattern']}")
        if "minLength" in schema and len(value) < schema["minLength"]:
            out.append(f"{path}: shorter than {schema['minLength']}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            out.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            out.append(f"{path}: more than {schema['maxItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                out += errors(item, schema["items"], root, f"{path}[{i}]")
    if isinstance(value, dict):
        for k in schema.get("required", []):
            if k not in value:
                out.append(f"{path}: missing '{k}'")
        props = schema.get("properties", {})
        for k, v in value.items():
            if k in props:
                out += errors(v, props[k], root, f"{path}.{k}")
            elif schema.get("additionalProperties") is False:
                out.append(f"{path}: unexpected '{k}'")
    return out


def not_finite(value, path: str = "$") -> list[str]:
    """JSON Schema has no way to say "a finite number"; NaN and infinity get through json.loads."""
    if isinstance(value, float) and not math.isfinite(value):
        return [f"{path}: {value} is not a finite number"]
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in not_finite(v, f"{path}.{k}")]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in not_finite(v, f"{path}[{i}]")]
    return []


UNIT_TOL = 1e-3


def scene_semantics(scene: dict) -> list[str]:
    """What the schema's keywords cannot express: the matrices, the arithmetic of the counts, unit vectors."""
    out = []
    for key, f in (scene.get("splats") or {}).items():
        m = f.get("matrix")
        if isinstance(m, list) and len(m) == 16 and all(isinstance(x, (int, float)) for x in m):
            problem = splats.similarity_problem(np.array(m, float).reshape(4, 4).T)
            if problem:
                out.append(f"$.splats.{key}.matrix (column-major) {problem}")
    c = scene.get("counts") or {}
    if all(k in c for k in ("marble", "covered", "overlap", "imagined")):
        if c["covered"] + c["overlap"] + c["imagined"] != c["marble"]:
            out.append(f"$.counts: covered {c['covered']} + overlap {c['overlap']} + imagined {c['imagined']} "
                       f"is not marble {c['marble']}")
    for key, count in (("measured", "measured"), ("measuredPreview", "measuredPreview"), ("measuredPhone", "measuredPhone"),
                       ("overlap", "overlap"),
                       ("imagined", "imagined")):
        f = (scene.get("splats") or {}).get(key) or {}
        if "splats" in f and count in c and f["splats"] != c[count]:
            out.append(f"$.splats.{key}.splats {f['splats']} is not counts.{count} {c[count]}")
    for path, v in (("door.outward", (scene.get("door") or {}).get("outward")),
                    ("light.direction", (scene.get("light") or {}).get("direction")),
                    ("frame.up", (scene.get("frame") or {}).get("up")),
                    ("frame.longAxis", (scene.get("frame") or {}).get("longAxis")),
                    ("floor.normal", (scene.get("floor") or {}).get("normal"))):
        if isinstance(v, list) and len(v) == 3 and all(isinstance(x, (int, float)) for x in v):
            n = math.sqrt(sum(x * x for x in v))
            if abs(n - 1) > UNIT_TOL:
                out.append(f"$.{path} has length {n:.4g}, not a unit vector")
    s = scene.get("splats") or {}
    phone, full = s.get("measuredPhone"), s.get("measured") or {}
    if (phone is None) != ("measuredPhone" not in c):
        out.append("$.splats.measuredPhone and $.counts.measuredPhone must come together")
    if isinstance(phone, dict):
        # phones load it in measured's place, so it must be a part of measured, placed the same way
        if phone.get("matrix") != full.get("matrix"):
            out.append("$.splats.measuredPhone.matrix is not measured's matrix")
        if phone.get("provenance") != 0:
            out.append("$.splats.measuredPhone.provenance is not 0")
        if isinstance(phone.get("splats"), int) and isinstance(full.get("splats"), int) and phone["splats"] > full["splats"]:
            out.append(f"$.splats.measuredPhone has {phone['splats']} splats, more than measured's {full['splats']}")
    return out


def check(document: dict, schema_name: str) -> None:
    problems = not_finite(document) + errors(document, load(schema_name))
    if schema_name == "scene.schema.json" and not problems:
        problems += scene_semantics(document)
    if problems:
        raise ValueError(f"{schema_name}: " + "; ".join(problems[:10]))
