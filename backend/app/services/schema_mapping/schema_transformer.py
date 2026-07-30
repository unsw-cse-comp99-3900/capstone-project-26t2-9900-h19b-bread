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

import re
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
    return serialize_to_xml(transformer(source), root_tag=root_tag)


def serialize_to_xml(data: Dict[str, Any], root_tag: str | None = None) -> str:
    """Serialise a transformed dictionary with a stable, non-duplicated root."""
    preferred_root = root_tag if _is_xml_name(root_tag) else None
    payload: Any = data
    if len(data) == 1:
        sole_key, sole_value = next(iter(data.items()))
        if _is_xml_name(sole_key) and (preferred_root is None or preferred_root == sole_key):
            preferred_root = sole_key
            payload = sole_value

    root = ET.Element(preferred_root or "root")
    _dict_to_xml(payload, root)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")


def _is_xml_name(value: str | None) -> bool:
    return bool(value and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", value))

def _dict_to_xml(data: Any, parent: ET.Element) -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            if not _is_xml_name(str(key)):
                raise TransformError(f"'{key}' is not a valid XML element name.")
            child = ET.SubElement(parent, str(key))
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
            _set_nested(target, _tgt, _cast_nested(value, _cast))
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
    """Read dot or slash paths, mapping explicit ``[]`` segments by index."""
    if path in ("$", "", None):
        return doc
    return _get_path_value(doc, _path_tokens(path), 0)

def _set_nested(doc: Dict[str, Any], path: str, value: Any) -> None:
    """Write dot or slash paths, merging explicit ``[]`` items by index."""
    if path in ("$", "", None):
        return
    tokens = _path_tokens(path)
    if tokens:
        _set_path_value(doc, tokens, 0, value)


def _get_path_value(node: Any, tokens: list[tuple[str, bool]], index: int) -> Any:
    if index == len(tokens):
        return node
    if not isinstance(node, dict):
        return None
    name, is_array = tokens[index]
    child = node.get(name)
    if not is_array:
        return _get_path_value(child, tokens, index + 1)
    if not isinstance(child, list):
        return None
    if index == len(tokens) - 1:
        return child
    return [_get_path_value(item, tokens, index + 1) for item in child]


def _set_path_value(
    node: Dict[str, Any],
    tokens: list[tuple[str, bool]],
    index: int,
    value: Any,
) -> None:
    name, is_array = tokens[index]
    is_last = index == len(tokens) - 1
    if not is_array:
        if is_last:
            node[name] = value
            return
        child = node.get(name)
        if not isinstance(child, dict):
            child = {}
            node[name] = child
        _set_path_value(child, tokens, index + 1, value)
        return

    values = value if isinstance(value, list) else ([] if value is None else [value])
    if is_last:
        node[name] = values
        return
    children = node.get(name)
    if not isinstance(children, list):
        children = []
        node[name] = children
    while len(children) < len(values):
        children.append({})
    for item_index, item_value in enumerate(values):
        if not isinstance(children[item_index], dict):
            children[item_index] = {}
        _set_path_value(children[item_index], tokens, index + 1, item_value)


def _path_tokens(path: str) -> list[tuple[str, bool]]:
    cleaned = path.lstrip("$./")
    tokens = []
    for raw_part in re.split(r"[/.]", cleaned):
        if not raw_part:
            continue
        is_array = raw_part.endswith("[]")
        name = raw_part[:-2] if is_array else raw_part
        if name:
            tokens.append((name, is_array))
    return tokens


def _cast_nested(value: Any, caster: Callable) -> Any:
    if isinstance(value, list):
        return [_cast_nested(item, caster) for item in value]
    return None if value is None else caster(value)


def _split_path(path: str) -> List[str]:
    """Split persisted slash or dot paths, stripping root and array markers."""
    cleaned = path.lstrip("$.")
    parts = [part.replace("[]", "") for part in re.split(r"[/.]", cleaned)]
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

    lines = ["    node = target"]
    for part in parts[:-1]:
        lines.append(f"    if not isinstance(node.get({part!r}), dict):")
        lines.append(f"        node[{part!r}] = {{}}")
        lines.append(f"    node = node[{part!r}]")

    lines.append(f"    node[{parts[-1]!r}] = {value_expr}")
    return "\n".join(lines)

def _safe_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

class TransformError(Exception):
    pass
