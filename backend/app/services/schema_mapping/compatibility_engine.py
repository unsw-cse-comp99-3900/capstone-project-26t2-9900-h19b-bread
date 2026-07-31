from __future__ import annotations

import difflib
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

DIRECT = "directly_compatible"
MAPPING = "compatible_with_mapping"
INCOMPATIBLE = "incompatible"

PRIMITIVE_TYPES = {"string", "integer", "number", "boolean", "null", "unknown"}

@dataclass
class SchemaEntry:
    path: str
    leaf: str
    leaf_norm: str
    node: Dict[str, Any]
    node_type: str
    is_required: bool

def normalize_name(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]", "", value.lower())
    if len(cleaned) > 3 and cleaned.endswith("s"):
        cleaned = cleaned[:-1]
    return cleaned

def tokenize_name(value: str) -> Set[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    tokens = re.split(r"[^A-Za-z0-9]+|\s+", spaced)
    normalized = set()
    for token in tokens:
        token = normalize_name(token)
        if token:
            normalized.add(token)
    if not normalized:
        joined = normalize_name(value)
        if joined:
            normalized.add(joined)
    return normalized

def normalize_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    if schema is None:
        return {"type": "unknown"}

    if not isinstance(schema, dict):
        return {"type": infer_primitive_type(schema)}

    if "root" in schema and "schema" in schema and "type" not in schema:
        root_node = normalize_schema(schema["schema"])
        root_copy = deepcopy(root_node)
        root_copy["xml_root"] = schema["root"]
        return root_copy

    if "oneOf" in schema:
        return {"oneOf": [normalize_schema(option) for option in schema["oneOf"]]}
    if "anyOf" in schema:
        return {"anyOf": [normalize_schema(option) for option in schema["anyOf"]]}

    if "properties" in schema or "attributes" in schema or schema.get("type") == "object":
        properties: Dict[str, Dict[str, Any]] = {}
        for name, child in schema.get("attributes", {}).items():
            if isinstance(child, dict):
                properties[f"@{name}"] = normalize_schema(child)
            else:
                properties[f"@{name}"] = {"type": child if isinstance(child, str) else "string"}

        for name, child in schema.get("properties", {}).items():
            properties[name] = normalize_schema(child)

        raw_required = schema.get("required")
        if raw_required is None:
            required = sorted(properties.keys())
        else:
            required = list(raw_required)
            for key in properties:
                if key.startswith("@") and key not in required:
                    required.append(key)

        normalized = {
            "type": "object",
            "properties": properties,
            "required": sorted(set(required)),
        }
        if "enum" in schema:
            normalized["enum"] = list(schema["enum"])
        if "description" in schema:
            normalized["description"] = schema["description"]
        if "xml_root" in schema:
            normalized["xml_root"] = schema["xml_root"]
        return normalized

    if "items" in schema or schema.get("type") == "array":
        normalized = {
            "type": "array",
            "items": normalize_schema(schema.get("items", {})),
        }
        if "enum" in schema:
            normalized["enum"] = list(schema["enum"])
        return normalized

    normalized = {"type": schema.get("type", "unknown")}
    if "enum" in schema:
        normalized["enum"] = list(schema["enum"])
    if "description" in schema:
        normalized["description"] = schema["description"]
    return normalized

def infer_primitive_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if value is None:
        return "null"
    return "unknown"

def compare_schemas(source_schema: Dict[str, Any], target_schema: Dict[str, Any], source_name: str = "Source", target_name: str = "Target") -> Dict[str, Any]:
    normalized_source = normalize_schema(source_schema)
    normalized_target = normalize_schema(target_schema)

    if "oneOf" in normalized_source:
        source_variants = normalized_source["oneOf"]
    elif "anyOf" in normalized_source:
        source_variants = normalized_source["anyOf"]
    else:
        source_variants = [normalized_source]

    if "oneOf" in normalized_target:
        target_variants = normalized_target["oneOf"]
    elif "anyOf" in normalized_target:
        target_variants = normalized_target["anyOf"]
    else:
        target_variants = [normalized_target]

    best_result = None
    best_score: Tuple[int, int, int] | None = None

    for s_idx, source_variant in enumerate(source_variants):
        for t_idx, target_variant in enumerate(target_variants):
            result = _compare_single_variant(source_variant, target_variant, source_name, target_name)
            score = _score_result(result)
            if best_score is None or score < best_score:
                best_score = score
                best_result = result
                best_result["chosen_variant"] = {
                    "source_variant_index": s_idx,
                    "target_variant_index": t_idx,
                }

    assert best_result is not None
    return best_result

def _compare_single_variant(source: Dict[str, Any], target: Dict[str, Any], source_name: str, target_name: str) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    source_index = build_index(source)
    used_paths: Set[str] = set()

    _compare_nodes(
        source_node=source,
        target_node=target,
        source_path="$",
        target_path="$",
        source_index=source_index,
        issues=issues,
        used_paths=used_paths,
    )

    compatibility = classify_issues(issues)
    summary = summarize_issues(issues, compatibility)
    return {
        "source": source_name,
        "target": target_name,
        "compatibility": compatibility,
        "summary": summary,
        "issues": issues,
        "normalized_source": source,
        "normalized_target": target,
    }

def _score_result(result: Dict[str, Any]) -> Tuple[int, int, int]:
    order = {
        DIRECT: 0,
        MAPPING: 1,
        INCOMPATIBLE: 2,
    }
    blocking = sum(1 for issue in result["issues"] if issue["kind"] == "blocking")
    mapping = sum(1 for issue in result["issues"] if issue["kind"] == "mapping")
    return (order[result["compatibility"]], blocking, mapping)

def build_index(
    node: Dict[str, Any],
    path: str = "$",
    *,
    is_required: bool = True,
) -> List[SchemaEntry]:
    entries: List[SchemaEntry] = []
    node_type = node.get("type", "unknown")
    leaf = path.split(".")[-1].replace("[]", "").replace("$", "root")
    entries.append(
        SchemaEntry(
            path=path,
            leaf=leaf,
            leaf_norm=normalize_name(leaf),
            node=node,
            node_type=node_type,
            is_required=is_required,
        )
    )

    if node_type == "object":
        required_keys = set(node.get("required", []))
        for key, child in node.get("properties", {}).items():
            child_path = f"{path}.{key}" if path != "$" else key
            entries.extend(
                build_index(
                    child,
                    child_path,
                    is_required=is_required and key in required_keys,
                )
            )
    elif node_type == "array":
        child_path = f"{path}[]" if path != "$" else "[]"
        entries.extend(
            build_index(
                node.get("items", {"type": "unknown"}),
                child_path,
                is_required=is_required,
            )
        )

    return entries

def _compare_nodes(
    source_node: Dict[str, Any],
    target_node: Dict[str, Any],
    source_path: str,
    target_path: str,
    source_index: List[SchemaEntry],
    issues: List[Dict[str, Any]],
    used_paths: Set[str],
) -> None:
    source_type = source_node.get("type", "unknown")
    target_type = target_node.get("type", "unknown")

    enum_issue = compare_enum(source_node, target_node, source_path, target_path)
    if enum_issue:
        issues.append(enum_issue)
        if enum_issue["kind"] == "blocking":
            return

    if target_type == "object":
        if source_type == "array":
            issues.append(make_issue(
                code="array_to_object_mapping",
                kind="mapping",
                severity="warning",
                source_path=source_path,
                target_path=target_path,
                message="Target expects an object but source provides an array. A wrap/unwrap mapping is needed.",
                suggestion="Map one array item into the required object shape or aggregate before forwarding.",
            ))
            _compare_nodes(
                source_node=source_node.get("items", {"type": "unknown"}),
                target_node=target_node,
                source_path=f"{source_path}[]",
                target_path=target_path,
                source_index=source_index,
                issues=issues,
                used_paths=used_paths,
            )
            return
        if source_type != "object":
            issues.append(make_issue(
                code="structural_mismatch",
                kind="blocking",
                severity="error",
                source_path=source_path,
                target_path=target_path,
                message=f"Target expects an object but source provides {source_type}.",
                suggestion="Provide an object-producing source or define a structural mapping layer.",
            ))
            return

        source_props = source_node.get("properties", {})
        source_required = set(source_node.get("required", []))
        target_props = target_node.get("properties", {})
        target_required = set(target_node.get("required", []))
        matched_exact: Set[str] = set()

        for target_key, target_child in target_props.items():
            child_target_path = f"{target_path}.{target_key}" if target_path != "$" else target_key

            if target_key in source_props:
                matched_exact.add(target_key)
                child_source_path = f"{source_path}.{target_key}" if source_path != "$" else target_key
                used_paths.add(child_source_path)
                if target_key in target_required and target_key not in source_required:
                    issues.append(_required_optional_issue(child_source_path, child_target_path))
                _compare_nodes(
                    source_node=source_props[target_key],
                    target_node=target_child,
                    source_path=child_source_path,
                    target_path=child_target_path,
                    source_index=source_index,
                    issues=issues,
                    used_paths=used_paths,
                )
                continue

            candidate = find_mapping_candidate(
                target_key=target_key,
                target_node=target_child,
                source_index=source_index,
                used_paths=used_paths,
            )

            if candidate is not None:
                used_paths.add(candidate.path)
                issues.append(make_issue(
                    code="field_mapping_required",
                    kind="mapping",
                    severity="warning",
                    source_path=candidate.path,
                    target_path=child_target_path,
                    message=f"No exact field named '{target_key}' was found at this level, but '{candidate.path}' looks like a compatible source field.",
                    suggestion=f"Map '{candidate.path}' to '{child_target_path}'.",
                ))
                if target_key in target_required and not candidate.is_required:
                    issues.append(_required_optional_issue(candidate.path, child_target_path))
                _compare_nodes(
                    source_node=candidate.node,
                    target_node=target_child,
                    source_path=candidate.path,
                    target_path=child_target_path,
                    source_index=source_index,
                    issues=issues,
                    used_paths=used_paths,
                )
            elif target_key in target_required:
                issues.append(make_issue(
                    code="missing_required_field",
                    kind="blocking",
                    severity="error",
                    source_path=source_path,
                    target_path=child_target_path,
                    message=f"Required target field '{child_target_path}' does not exist in the source schema.",
                    suggestion="Add this field upstream or provide a mapping/default value before calling the target API.",
                ))
            else:
                issues.append(make_issue(
                    code="missing_optional_field",
                    kind="info",
                    severity="information",
                    source_path=source_path,
                    target_path=child_target_path,
                    message=f"Optional target field '{child_target_path}' is not provided by the source schema.",
                    suggestion="No action is required unless the target API needs a default value in practice.",
                ))

        for source_key in source_props:
            if source_key not in matched_exact:
                child_source_path = f"{source_path}.{source_key}" if source_path != "$" else source_key
                if child_source_path not in used_paths:
                    issues.append(make_issue(
                        code="extra_source_field",
                        kind="info",
                        severity="information",
                        source_path=child_source_path,
                        target_path=target_path,
                        message=f"Source field '{child_source_path}' has no direct target counterpart.",
                        suggestion="This is usually safe if the target ignores unknown fields. Otherwise drop it during mapping.",
                    ))
        return

    if target_type == "array":
        if source_type == "array":
            _compare_nodes(
                source_node=source_node.get("items", {"type": "unknown"}),
                target_node=target_node.get("items", {"type": "unknown"}),
                source_path=f"{source_path}[]",
                target_path=f"{target_path}[]",
                source_index=source_index,
                issues=issues,
                used_paths=used_paths,
            )
            return

        relation = primitive_relation(source_node, target_node.get("items", {"type": "unknown"}))
        if relation in {"direct", "mapping"}:
            issues.append(make_issue(
                code="singleton_array_mapping",
                kind="mapping",
                severity="warning",
                source_path=source_path,
                target_path=target_path,
                message="Target expects an array but source provides a single value/object. A wrap-to-array mapping is needed.",
                suggestion="Wrap the source value into a one-element array before forwarding.",
            ))
            return

        issues.append(make_issue(
            code="array_type_mismatch",
            kind="blocking",
            severity="error",
            source_path=source_path,
            target_path=target_path,
            message=f"Target expects an array but source provides {source_type} and the item types are not compatible.",
            suggestion="Choose a different source or build a mediator that produces the required array structure.",
        ))
        return

    relation = primitive_relation(source_node, target_node)
    if relation == "direct":
        return
    if relation == "mapping":
        issues.append(make_issue(
            code="type_conversion_required",
            kind="mapping",
            severity="warning",
            source_path=source_path,
            target_path=target_path,
            message=f"Source type '{source_type}' can reach target type '{target_type}', but conversion is required.",
            suggestion=f"Cast or transform '{source_path}' into '{target_type}' before sending it to '{target_path}'.",
        ))
        return

    issues.append(make_issue(
        code="type_mismatch",
        kind="blocking",
        severity="error",
        source_path=source_path,
        target_path=target_path,
        message=f"Source type '{source_type}' is not compatible with target type '{target_type}'.",
        suggestion="Use a different API pair or insert a mapping/translation step that changes the data structure.",
    ))

def compare_enum(source_node: Dict[str, Any], target_node: Dict[str, Any], source_path: str, target_path: str) -> Optional[Dict[str, Any]]:
    source_enum = set(source_node.get("enum", []))
    target_enum = set(target_node.get("enum", []))
    if not target_enum:
        return None

    if source_enum:
        overlap = source_enum & target_enum
        if not overlap:
            return make_issue(
                code="enum_mismatch",
                kind="blocking",
                severity="error",
                source_path=source_path,
                target_path=target_path,
                message=f"Source enum values {sorted(source_enum)} do not overlap with target enum values {sorted(target_enum)}.",
                suggestion="Use a compatible API, or translate values into the target enum set.",
            )
        if not source_enum.issubset(target_enum):
            return make_issue(
                code="enum_mapping_required",
                kind="mapping",
                severity="warning",
                source_path=source_path,
                target_path=target_path,
                message="Source enum contains values outside the target enum. Value translation may be required.",
                suggestion="Constrain or map source enum values before sending them to the target.",
            )
    return None

def primitive_relation(source_node: Dict[str, Any], target_node: Dict[str, Any]) -> str:
    source_type = source_node.get("type", "unknown")
    target_type = target_node.get("type", "unknown")

    if source_type == target_type:
        return "direct"
    if source_type == "integer" and target_type == "number":
        return "direct"
    if source_type == "null" and target_type not in {"null", "unknown"}:
        return "mapping"

    castable_pairs = {
        ("number", "integer"),
        ("string", "integer"),
        ("string", "number"),
        ("string", "boolean"),
        ("integer", "string"),
        ("number", "string"),
        ("boolean", "string"),
        ("integer", "boolean"),
        ("boolean", "integer"),
    }
    if (source_type, target_type) in castable_pairs:
        return "mapping"
    return "incompatible"

def find_mapping_candidate(target_key: str, target_node: Dict[str, Any], source_index: List[SchemaEntry], used_paths: Set[str]) -> Optional[SchemaEntry]:
    target_norm = normalize_name(target_key)
    target_tokens = tokenize_name(target_key)
    compatible: List[Tuple[int, int, SchemaEntry]] = []

    for entry in source_index:
        if entry.path in used_paths or entry.path == "$":
            continue
        similarity = difflib.SequenceMatcher(None, target_norm, entry.leaf_norm).ratio()
        relation = primitive_relation(entry.node, target_node)
        same_leaf = target_norm == entry.leaf_norm and target_norm != ""
        source_tokens = tokenize_name(entry.leaf)
        token_overlap = bool(target_tokens & source_tokens)
        subset_match = bool(target_tokens) and (target_tokens.issubset(source_tokens) or source_tokens.issubset(target_tokens))

        if same_leaf and relation == "direct":
            compatible.append((0, len(entry.path), entry))
        elif same_leaf and relation == "mapping":
            compatible.append((1, len(entry.path), entry))
        elif subset_match and relation == "direct":
            compatible.append((2, len(entry.path), entry))
        elif subset_match and relation == "mapping":
            compatible.append((3, len(entry.path), entry))
        elif token_overlap and similarity >= 0.55 and relation in {"direct", "mapping"}:
            compatible.append((4, len(entry.path), entry))
        elif similarity >= 0.88 and relation in {"direct", "mapping"}:
            compatible.append((5, len(entry.path), entry))

    if not compatible:
        return None

    compatible.sort(key=lambda item: item[:2])
    return compatible[0][2]

def make_issue(code: str, kind: str, severity: str, source_path: str, target_path: str, message: str, suggestion: str) -> Dict[str, Any]:
    return {
        "code": code,
        "kind": kind,
        "severity": severity,
        "source_path": source_path,
        "target_path": target_path,
        "message": message,
        "suggestion": suggestion,
    }

def classify_issues(issues: List[Dict[str, Any]]) -> str:
    if any(issue["kind"] == "blocking" for issue in issues):
        return INCOMPATIBLE
    if any(issue["kind"] == "mapping" for issue in issues):
        return MAPPING
    return DIRECT

def summarize_issues(issues: List[Dict[str, Any]], compatibility: str) -> Dict[str, Any]:
    return {
        "compatibility_label": {
            DIRECT: "Directly compatible",
            MAPPING: "Compatible with mapping",
            INCOMPATIBLE: "Incompatible",
        }[compatibility],
        "blocking_issues": sum(1 for issue in issues if issue["kind"] == "blocking"),
        "mapping_issues": sum(1 for issue in issues if issue["kind"] == "mapping"),
        "informational_issues": sum(1 for issue in issues if issue["kind"] == "info"),
        "issue_count": len(issues),
    }


def _required_optional_issue(source_path: str, target_path: str) -> Dict[str, Any]:
    return make_issue(
        code="required_optional_conflict",
        kind="mapping",
        severity="warning",
        source_path=source_path,
        target_path=target_path,
        message=(
            f"Target field '{target_path}' is required, but source field "
            f"'{source_path}' is optional."
        ),
        suggestion=(
            "Provide a complete mapping with a reliable fallback and validate the "
            "result against the target schema."
        ),
    )
