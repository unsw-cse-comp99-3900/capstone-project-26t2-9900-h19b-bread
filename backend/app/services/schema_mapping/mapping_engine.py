from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FieldMapping:
    source_path: Optional[str]
    target_path: str
    transform: str          # Can be (rename, cast, wrap_array, unwrap_array, constant, drop, missing)
    source_type: Optional[str]
    target_type: Optional[str]
    confidence: str         # Can be (high, medium, low)
    note: str

@dataclass
class SchemaMapping:
    source: str
    target: str
    status: str             # Can be (full, partial, incompatible)
    fields: List[FieldMapping] = field(default_factory=list)
    issues: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "status": self.status,
            "fields": [
                {
                    "source_path": fm.source_path,
                    "target_path": fm.target_path,
                    "transform": fm.transform,
                    "source_type": fm.source_type,
                    "target_type": fm.target_type,
                    "confidence": fm.confidence,
                    "note": fm.note,
                }
                for fm in self.fields
            ],
            "issues": self.issues,
        }

def _infer_transform(code: str, source_node: Optional[Dict], target_node: Optional[Dict]) -> str:
    """Infer the transform type from the issue code and node types."""
    if code == "field_mapping_required":
        source_type = (source_node or {}).get("type")
        target_type = (target_node or {}).get("type")
        if source_type == target_type:
            return "rename"
        return "cast"
    if code == "type_conversion_required":
        return "cast"
    if code == "singleton_array_mapping":
        return "wrap_array"
    if code == "array_to_object_mapping":
        return "unwrap_array"
    if code == "missing_required_field":
        return "missing"
    if code == "missing_optional_field":
        return "constant"
    if code == "extra_source_field":
        return "drop"
    return "rename"


def _infer_confidence(code: str) -> str:
    high = {"field_mapping_required"}
    medium = {"type_conversion_required", "singleton_array_mapping", "array_to_object_mapping"}
    low = {"enum_mapping_required", "missing_optional_field"}
    if code in high:
        return "high"
    if code in medium:
        return "medium"
    return "low"

def _get_node_at_path(schema: Dict[str, Any], path: str) -> Optional[Dict[str, Any]]:
    """
    Walk a normalised schema to retrieve the node at a dot-separated path.
    Handles array notation (path[]) by descending into 'items'.
    """
    if path in ("$", ""):
        return schema

    parts = path.lstrip("$.").split(".")
    node = schema

    for part in parts:
        if part.endswith("[]"):
            key = part[:-2]
            if key:
                node = node.get("properties", {}).get(key, {})
            node = node.get("items", {})
        else:
            node = node.get("properties", {}).get(part, {})

        if not node:
            return None

    return node

def build_mapping(comparison_result: Dict[str, Any]) -> SchemaMapping:
    """
    Consume the output of compare_schemas() and produce a SchemaMapping.

    Only issues with kind 'mapping', 'blocking', or 'info' that carry
    path information are turned into FieldMapping entries. Direct matches
    (no issue raised) are recovered by diffing the normalised schemas.
    """
    source_name = comparison_result["source"]
    target_name = comparison_result["target"]
    compatibility = comparison_result["compatibility"]
    issues = comparison_result["issues"]
    norm_source = comparison_result["normalized_source"]
    norm_target = comparison_result["normalized_target"]

    status_map = {
        "directly_compatible": "full",
        "compatible_with_mapping": "partial",
        "incompatible": "incompatible",
    }
    status = status_map.get(compatibility, "incompatible")

    mapping = SchemaMapping(source=source_name, target=target_name, status=status)
    handled_targets = set()

    for issue in issues:
        code = issue["code"]
        source_path = issue.get("source_path")
        target_path = issue.get("target_path")

        source_node = _get_node_at_path(norm_source, source_path) if source_path else None
        target_node = _get_node_at_path(norm_target, target_path) if target_path else None

        transform = _infer_transform(code, source_node, target_node)
        confidence = _infer_confidence(code)

        mapping.fields.append(FieldMapping(
            source_path=source_path if source_path != target_path else source_path,
            target_path=target_path,
            transform=transform,
            source_type=(source_node or {}).get("type"),
            target_type=(target_node or {}).get("type"),
            confidence=confidence,
            note=issue["message"],
        ))

        if target_path and code != "extra_source_field":
            handled_targets.add(target_path)

        if issue["kind"] == "blocking":
            mapping.issues.append(issue)

    _add_direct_matches(norm_source, norm_target, mapping, handled_targets)
    _sort_fields(mapping)

    return mapping


def _add_direct_matches(
    source: Dict[str, Any],
    target: Dict[str, Any],
    mapping: SchemaMapping,
    handled_targets: set,
    source_path: str = "$",
    target_path: str = "$",
) -> None:
    """Recursively walk the target schema and record silent direct matches."""
    if target.get("type") != "object":
        return

    source_props = source.get("properties", {})
    target_props = target.get("properties", {})

    for key, target_child in target_props.items():
        child_target = f"{target_path}.{key}" if target_path != "$" else key
        child_source = f"{source_path}.{key}" if source_path != "$" else key

        if child_target in handled_targets:
            continue

        if key in source_props:
            source_child = source_props[key]
            if target_child.get("type") == "object" and source_child.get("type") == "object":
                _add_direct_matches(source_child, target_child, mapping, handled_targets, child_source, child_target)
                continue

            mapping.fields.append(FieldMapping(
                source_path=child_source,
                target_path=child_target,
                transform="direct",
                source_type=source_child.get("type"),
                target_type=target_child.get("type"),
                confidence="high",
                note="Exact field and type match.",
            ))
            handled_targets.add(child_target)

def _sort_fields(mapping: SchemaMapping) -> None:
    order = {"direct": 0, "rename": 1, "cast": 2, "wrap_array": 3,
              "unwrap_array": 3, "constant": 4, "drop": 5, "missing": 6}
    mapping.fields.sort(key=lambda f: order.get(f.transform, 99))
