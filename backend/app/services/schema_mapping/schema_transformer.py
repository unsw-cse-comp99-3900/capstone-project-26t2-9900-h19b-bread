from __future__ import annotations

"""
schema_transformer.py
─────────────────────
Generates and executes transformation code from a SchemaMapping.

Usage
-----
    from schema_comparator import compare_schemas
    from schema_mapper import build_mapping
    from schema_transformer import build_transformer

    result   = compare_schemas(source_schema, target_schema, "A", "B")
    mapping  = build_mapping(result)
    fn       = build_transformer(mapping)

    output   = fn(source_document)        # dict → dict
    xml_out  = transform_to_xml(fn, source_document, root_tag="record")
"""

import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, List, Optional


def build_transformer(mapping) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """
    Accept a SchemaMapping (from schema_mapper.build_mapping) and return a
    callable  fn(source: dict) -> dict  that performs the transformation.
    """
    compiled = _compile_mapping(mapping.fields)
    source_name = mapping.source
    target_name = mapping.target

    def transform(source: Dict[str, Any]) -> Dict[str, Any]:
        target: Dict[str, Any] = {}
        errors: List[str] = []

        for rule in compiled:
            try:
                rule(source, target)
            except Exception as exc:
                errors.append(str(exc))

        if errors:
            raise TransformError(
                f"Transformation from '{source_name}' to '{target_name}' "
                f"completed with {len(errors)} error(s):\n" + "\n".join(errors)
            )

        return target

    transform.__doc__ = (
        f"Transform a '{source_name}' document into a '{target_name}' document.\n\n"
        + generate_transform_code(mapping)
    )
    return transform

def transform_to_xml(
    transformer: Callable[[Dict[str, Any]], Dict[str, Any]],
    source: Dict[str, Any],
    root_tag: str = "root",
) -> str:
    """Run the transformer and serialise the result to an XML string."""
    result = transformer(source)
    root = ET.Element(root_tag)
    _dict_to_xml(result, root)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")

def _dict_to_xml(data: Any, parent: ET.Element) -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            child = ET.SubElement(parent, key)
            _dict_to_xml(value, child)
    elif isinstance(data, list):
        for item in data:
            item_el = ET.SubElement(parent, "item")
            _dict_to_xml(item, item_el)
    elif data is None:
        parent.text = ""
    else:
        parent.text = str(data)

def generate_transform_code(mapping) -> str:
    """
    Return a human-readable Python function as a string.
    Useful for inspection, debugging, or saving to disk.
    """
    lines: List[str] = [
        f'def transform_{_safe_name(mapping.source)}_to_{_safe_name(mapping.target)}(source: dict) -> dict:',
        f'    """Auto-generated transformer: {mapping.source} → {mapping.target}"""',
        '    target = {}',
        '',
    ]

    for fm in mapping.fields:
        lines += _render_field(fm)

    lines += ['    return target', '']
    return "\n".join(lines)

def _render_field(fm) -> List[str]:
    transform = fm.transform
    src = fm.source_path
    tgt = fm.target_path
    src_type = fm.source_type
    tgt_type = fm.target_type

    comment = f"    # [{transform.upper()}] {src} → {tgt}"

    if transform == "direct" or transform == "rename":
        getter = _getter(src)
        setter = _setter(tgt, getter)
        return [comment, setter, '']

    if transform == "cast":
        getter = _getter(src)
        cast_expr = _cast_expression(getter, src_type, tgt_type)
        setter = _setter(tgt, cast_expr)
        return [comment, setter, '']

    if transform == "wrap_array":
        getter = _getter(src)
        setter = _setter(tgt, f"[{getter}] if {getter} is not None else []")
        return [comment, setter, '']

    if transform == "unwrap_array":
        getter = _getter(src)
        setter = _setter(tgt, f"{getter}[0] if {getter} else None")
        return [comment, setter, '']

    if transform == "drop":
        return [comment, f"    # '{src}' has no target counterpart — omitted.", '']

    if transform == "constant":
        setter = _setter(tgt, "None  # TODO: supply a default value")
        return [comment, setter, '']

    if transform == "missing":
        return [
            comment,
            f"    # WARNING: required target field '{tgt}' has no source — "
            "you must supply this value.",
            f"    # {_setter(tgt, 'None  # TODO: provide value')}",
            '',
        ]

    getter = _getter(src) if src else "None"
    setter = _setter(tgt, getter)
    return [comment, setter, '']

def _compile_mapping(fields) -> List[Callable]:
    """Turn each FieldMapping into a callable rule(source, target)."""
    rules = []
    for fm in fields:
        rules.append(_compile_field(fm))
    return rules

def _compile_field(fm) -> Callable:
    transform = fm.transform
    src = fm.source_path
    tgt = fm.target_path
    src_type = fm.source_type
    tgt_type = fm.target_type

    if transform in ("direct", "rename"):
        def rule(source, target, _src=src, _tgt=tgt):
            value = _get_nested(source, _src)
            _set_nested(target, _tgt, value)
        return rule

    if transform == "cast":
        caster = _make_caster(src_type, tgt_type)
        def rule(source, target, _src=src, _tgt=tgt, _cast=caster):
            value = _get_nested(source, _src)
            _set_nested(target, _tgt, _cast(value))
        return rule

    if transform == "wrap_array":
        def rule(source, target, _src=src, _tgt=tgt):
            value = _get_nested(source, _src)
            _set_nested(target, _tgt, [value] if value is not None else [])
        return rule

    if transform == "unwrap_array":
        def rule(source, target, _src=src, _tgt=tgt):
            value = _get_nested(source, _src)
            _set_nested(target, _tgt, value[0] if value else None)
        return rule

    if transform in ("drop", "missing", "constant"):
        def rule(source, target):
            pass  # no-op at runtime; caller must inject constants separately
        return rule

    # Fallback: treat as direct
    def rule(source, target, _src=src, _tgt=tgt):
        _set_nested(target, _tgt, _get_nested(source, _src))
    return rule

def _get_nested(doc: Dict[str, Any], path: str) -> Any:
    """
    Retrieve a value from a nested dict using a dot-separated path.
    Array items are accessed with [] notation: "data.items[].name"
    is not supported at this level — arrays are treated as whole values.
    """
    if path in ("$", "", None):
        return doc

    parts = _split_path(path)
    node = doc
    for idx, part in enumerate(parts):
        if node is None:
            return None
        if isinstance(node, list):
            # If mid-path and hit a list, map the remainder over items.
            remainder = ".".join(parts[idx:])
            return [_get_nested(item, remainder) for item in node]
        node = node.get(part) if isinstance(node, dict) else None
    return node

def _set_nested(doc: Dict[str, Any], path: str, value: Any) -> None:
    """
    Write a value into a nested dict, creating intermediate dicts as needed.
    """
    if path in ("$", "", None):
        return

    parts = _split_path(path)
    node = doc
    for part in parts[:-1]:
        if part not in node or not isinstance(node[part], dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value


def _split_path(path: str) -> List[str]:
    """Split a dot-separated path, stripping leading $ and [] array markers."""
    cleaned = path.lstrip("$.")
    parts = [p.replace("[]", "") for p in cleaned.split(".")]
    return [p for p in parts if p]

def _make_caster(src_type: Optional[str], tgt_type: Optional[str]) -> Callable:
    """Return a callable that converts a value from src_type to tgt_type."""
    key = (src_type, tgt_type)
    casters = {
        ("integer",  "string"):  str,
        ("number",   "string"):  str,
        ("boolean",  "string"):  lambda v: str(v).lower(),
        ("string",   "integer"): int,
        ("string",   "number"):  float,
        ("string",   "boolean"): lambda v: v.lower() in ("true", "1", "yes"),
        ("integer",  "boolean"): bool,
        ("boolean",  "integer"): int,
        ("number",   "integer"): int,
        ("integer",  "number"):  float,
        ("null",     None):      lambda v: None,
    }
    return casters.get(key, lambda v: v)

def _cast_expression(getter: str, src_type: Optional[str], tgt_type: Optional[str]) -> str:
    """Return a Python expression string that applies the right cast."""
    exprs = {
        ("integer",  "string"):  f"str({getter})",
        ("number",   "string"):  f"str({getter})",
        ("boolean",  "string"):  f"str({getter}).lower()",
        ("string",   "integer"): f"int({getter})",
        ("string",   "number"):  f"float({getter})",
        ("string",   "boolean"): f"({getter}).lower() in ('true', '1', 'yes')",
        ("integer",  "boolean"): f"bool({getter})",
        ("boolean",  "integer"): f"int({getter})",
        ("number",   "integer"): f"int({getter})",
        ("integer",  "number"):  f"float({getter})",
    }
    return exprs.get((src_type, tgt_type), getter)

def _getter(path: str) -> str:
    """Render a safe chained .get() expression for the source path."""
    if not path or path == "$":
        return "source"
    parts = _split_path(path)
    expr = "source"
    for part in parts:
        expr = f"{expr}.get({part!r})"
    return expr

def _setter(path: str, value_expr: str) -> str:
    if not path or path == "$":
        return f"    target = {value_expr}"
    parts = _split_path(path)
    if len(parts) == 1:
        return f"    target[{parts[0]!r}] = {value_expr}"

    lines = []
    for i in range(len(parts) - 1):
        chain = "target" + "".join(f"[{p!r}]" for p in parts[:i+1])
        lines.append(f"    {chain} = {chain} if isinstance({chain}, dict) else {{}}")
        lines.append(f"    {chain}.setdefault({parts[i+1]!r}, {{}})")

    assignment = "target" + "".join(f"[{p!r}]" for p in parts)
    lines.append(f"    {assignment} = {value_expr}")
    return "\n".join(lines)

def _safe_name(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

class TransformError(Exception):
    pass
