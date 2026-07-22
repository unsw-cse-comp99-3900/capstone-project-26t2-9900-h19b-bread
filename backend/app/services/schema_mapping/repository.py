from __future__ import annotations

import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import date, datetime
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.core.database import get_connection
from app.services.schema_mapping.compatibility_engine import normalize_schema
from app.services.schema_mapping.mapping_engine import FieldMapping, SchemaMapping


def _json_ready(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _db_type_to_json_schema_type(value: str | None) -> str:
    type_value = (value or "string").lower()
    if type_value in {"integer", "number", "boolean", "null", "array", "object", "string"}:
        return type_value
    return "string"


def _split_field_path(path: str) -> list[str]:
    return [part for part in re.split(r"[/.]", path.strip()) if part and part != "$"]


def _set_required(node: dict[str, Any], key: str) -> None:
    required = node.setdefault("required", [])
    if key not in required:
        required.append(key)


class PostgresSchemaMappingRepository:
    def __init__(
        self,
        connection_factory: Callable[[], AbstractContextManager[Connection]] = get_connection,
    ) -> None:
        self.connection_factory = connection_factory

    def list_api_schemas(self) -> list[dict[str, Any]]:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.schema_id, s.api_id, a.api_name, s.version_id, v.version_number,
                           s.direction, s.format, s.source_key, s.source_path,
                           s.source_method, s.media_type, s.status_code,
                           s.schema_version, s.raw_schema, s.normalized_schema, s.created_at
                    FROM api_schema s
                    JOIN api_submission a ON a.api_id = s.api_id
                    JOIN api_version v ON v.version_id = s.version_id
                    ORDER BY a.api_name, s.direction, s.source_path, s.source_method,
                             s.media_type, s.status_code, s.schema_version DESC, s.schema_id
                    """
                )
                rows = cursor.fetchall()
                for row in rows:
                    row["schema_definition"] = self._schema_definition(cursor, row)
                return [_json_ready(row) for row in rows]

    def get_api_schema(self, schema_id: int) -> dict[str, Any] | None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.schema_id, s.api_id, a.api_name, s.version_id, v.version_number,
                           s.direction, s.format, s.source_key, s.source_path,
                           s.source_method, s.media_type, s.status_code,
                           s.schema_version, s.raw_schema, s.normalized_schema, s.created_at
                    FROM api_schema s
                    JOIN api_submission a ON a.api_id = s.api_id
                    JOIN api_version v ON v.version_id = s.version_id
                    WHERE s.schema_id = %s
                    """,
                    (schema_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                row["schema_definition"] = self._schema_definition(cursor, row)
                return _json_ready(row)

    def save_comparison(
        self,
        source_schema: dict[str, Any],
        target_schema: dict[str, Any],
        comparison: dict[str, Any],
    ) -> int:
        level = {
            "directly_compatible": "DIRECTLY_COMPATIBLE",
            "compatible_with_mapping": "COMPATIBLE_WITH_MAPPING",
            "incompatible": "INCOMPATIBLE",
        }[comparison["compatibility"]]

        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO compatibility_result (
                        source_api_id, target_api_id, source_schema_id, target_schema_id,
                        source_version_id, target_version_id, compatibility_level,
                        summary, full_result
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                    ON CONFLICT (source_schema_id, target_schema_id)
                    DO UPDATE SET
                        source_version_id = EXCLUDED.source_version_id,
                        target_version_id = EXCLUDED.target_version_id,
                        compatibility_level = EXCLUDED.compatibility_level,
                        summary = EXCLUDED.summary,
                        full_result = EXCLUDED.full_result,
                        created_at = CURRENT_TIMESTAMP
                    RETURNING result_id
                    """,
                    (
                        source_schema["api_id"],
                        target_schema["api_id"],
                        source_schema["schema_id"],
                        target_schema["schema_id"],
                        source_schema["version_id"],
                        target_schema["version_id"],
                        level,
                        Jsonb(comparison["summary"]),
                        Jsonb(comparison),
                    ),
                )
                result_id = cursor.fetchone()["result_id"]
                cursor.execute("DELETE FROM compatibility_issue WHERE result_id = %s", (result_id,))
                for issue in comparison["issues"]:
                    cursor.execute(
                        """
                        INSERT INTO compatibility_issue (
                            result_id, code, kind, severity, source_path,
                            target_path, message, suggestion
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            result_id,
                            issue["code"],
                            issue["kind"],
                            issue["severity"],
                            issue.get("source_path"),
                            issue.get("target_path"),
                            issue["message"],
                            issue.get("suggestion"),
                        ),
                    )
                return result_id

    def save_mapping(
        self,
        source_schema: dict[str, Any],
        target_schema: dict[str, Any],
        comparison_result_id: int,
        mapping: SchemaMapping,
    ) -> int:
        completeness = {
            "full": "FULL",
            "partial": "PARTIAL",
            "incompatible": "INCOMPATIBLE",
        }[mapping.status]
        overview = (
            f"{mapping.source} to {mapping.target}: {mapping.status} mapping "
            f"with {len(mapping.fields)} field rule(s)."
        )

        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO schema_mapping (
                        source_api_id, target_api_id, source_version_id, target_version_id,
                        source_schema_id, target_schema_id, compatibility_result_id,
                        source_schema_format, target_schema_format,
                        overview_note, lifecycle_status, completeness
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE', %s)
                    ON CONFLICT (source_schema_id, target_schema_id)
                    DO UPDATE SET
                        source_api_id = EXCLUDED.source_api_id,
                        target_api_id = EXCLUDED.target_api_id,
                        source_version_id = EXCLUDED.source_version_id,
                        target_version_id = EXCLUDED.target_version_id,
                        source_schema_id = EXCLUDED.source_schema_id,
                        target_schema_id = EXCLUDED.target_schema_id,
                        compatibility_result_id = EXCLUDED.compatibility_result_id,
                        source_schema_format = EXCLUDED.source_schema_format,
                        target_schema_format = EXCLUDED.target_schema_format,
                        overview_note = EXCLUDED.overview_note,
                        lifecycle_status = EXCLUDED.lifecycle_status,
                        completeness = EXCLUDED.completeness,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING mapping_id
                    """,
                    (
                        source_schema["api_id"],
                        target_schema["api_id"],
                        source_schema["version_id"],
                        target_schema["version_id"],
                        source_schema["schema_id"],
                        target_schema["schema_id"],
                        comparison_result_id,
                        source_schema["format"],
                        target_schema["format"],
                        overview,
                        completeness,
                    ),
                )
                mapping_id = cursor.fetchone()["mapping_id"]
                cursor.execute("DELETE FROM mapping_rule WHERE schema_mapping_id = %s", (mapping_id,))
                for field in mapping.fields:
                    cursor.execute(
                        """
                        INSERT INTO mapping_rule (
                            schema_mapping_id, source_field, target_field, transform_type,
                            source_type, target_type, confidence, note
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (schema_mapping_id, source_field, target_field)
                        DO UPDATE SET
                            transform_type = EXCLUDED.transform_type,
                            source_type = EXCLUDED.source_type,
                            target_type = EXCLUDED.target_type,
                            confidence = EXCLUDED.confidence,
                            note = EXCLUDED.note
                        """,
                        (
                            mapping_id,
                            field.source_path or "",
                            field.target_path,
                            "rename" if field.transform == "direct" else field.transform,
                            field.source_type,
                            field.target_type,
                            field.confidence,
                            field.note,
                        ),
                    )
                return mapping_id

    def get_mapping(self, mapping_id: int) -> dict[str, Any] | None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT sm.*, cr.full_result
                    FROM schema_mapping sm
                    LEFT JOIN compatibility_result cr ON cr.result_id = sm.compatibility_result_id
                    WHERE sm.mapping_id = %s
                    """,
                    (mapping_id,),
                )
                mapping_row = cursor.fetchone()
                if mapping_row is None:
                    return None

                source_schema = self.get_api_schema(mapping_row["source_schema_id"])
                target_schema = self.get_api_schema(mapping_row["target_schema_id"])
                cursor.execute(
                    """
                    SELECT source_field, target_field, transform_type, source_type,
                           target_type, confidence, note
                    FROM mapping_rule
                    WHERE schema_mapping_id = %s
                    ORDER BY rule_id
                    """,
                    (mapping_id,),
                )
                rules = cursor.fetchall()

        fields = [
            FieldMapping(
                source_path=rule["source_field"] or None,
                target_path=rule["target_field"],
                transform=rule["transform_type"],
                source_type=rule["source_type"],
                target_type=rule["target_type"],
                confidence=rule["confidence"],
                note=rule["note"] or "",
            )
            for rule in rules
        ]
        status = {
            "FULL": "full",
            "PARTIAL": "partial",
            "INCOMPATIBLE": "incompatible",
        }[mapping_row["completeness"]]
        mapping = SchemaMapping(
            source=source_schema["api_name"] if source_schema else "Source",
            target=target_schema["api_name"] if target_schema else "Target",
            status=status,
            fields=fields,
        )
        return {
            "row": _json_ready(mapping_row),
            "source_schema": source_schema,
            "target_schema": target_schema,
            "mapping": mapping,
            "comparison": mapping_row.get("full_result"),
        }

    def save_transform_run(
        self,
        mapping_row: dict[str, Any],
        input_data: dict[str, Any],
        output_data: Any,
        output_format: str,
        mapping_status: str,
        *,
        success: bool = True,
        error_message: str | None = None,
    ) -> int:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO transform_run (
                        schema_mapping_id, source_api_id, target_api_id,
                        source_schema_id, target_schema_id, source_version_id, target_version_id,
                        input_data, output_data, output_text, output_format,
                        mapping_status, warnings, success, error_message
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, '[]'::jsonb, %s, %s)
                    RETURNING transform_run_id
                    """,
                    (
                        mapping_row["mapping_id"],
                        mapping_row["source_api_id"],
                        mapping_row["target_api_id"],
                        mapping_row["source_schema_id"],
                        mapping_row["target_schema_id"],
                        mapping_row["source_version_id"],
                        mapping_row["target_version_id"],
                        Jsonb(input_data),
                        Jsonb(output_data) if output_format == "json" else None,
                        output_data if output_format == "xml" else None,
                        output_format.upper(),
                        mapping_status,
                        success,
                        error_message,
                    ),
                )
                return cursor.fetchone()["transform_run_id"]

    def _schema_definition(self, cursor, row: dict[str, Any]) -> dict[str, Any]:
        normalized = row.get("normalized_schema")
        if isinstance(normalized, dict) and (
            "type" in normalized or "properties" in normalized or "schema" in normalized
        ):
            return normalize_schema(normalized)
        if isinstance(normalized, dict) and isinstance(normalized.get("fields"), list):
            return normalize_schema(
                self._schema_from_fields(
                    [
                        {
                            "field_path": field.get("path", ""),
                            "field_name": _split_field_path(field.get("path", ""))[-1]
                            if _split_field_path(field.get("path", ""))
                            else "",
                            "field_type": field.get("type", "string"),
                            "is_required": bool(field.get("required", True)),
                        }
                        for field in normalized["fields"]
                    ]
                )
            )

        cursor.execute(
            """
            SELECT field_path, field_name, field_type, is_required
            FROM schema_field
            WHERE schema_id = %s
            ORDER BY nesting_depth, field_id
            """,
            (row["schema_id"],),
        )
        fields = cursor.fetchall()
        if fields:
            schema = self._schema_from_fields(fields)
        else:
            schema = self._schema_from_raw(row["raw_schema"])
        return normalize_schema(schema)

    def _schema_from_raw(self, raw_schema: dict[str, Any]) -> dict[str, Any]:
        if "type" in raw_schema or "properties" in raw_schema:
            return raw_schema
        if "root" in raw_schema and "schema" in raw_schema:
            return raw_schema
        fields = raw_schema.get("fields")
        root = raw_schema.get("root")
        if root and isinstance(fields, list):
            rows = [
                {
                    "field_path": f"{root}/{field}",
                    "field_name": str(field),
                    "field_type": "string",
                    "is_required": True,
                }
                for field in fields
            ]
            return self._schema_from_fields(rows)
        return {"type": "object", "properties": {}}

    def _schema_from_fields(self, fields: list[dict[str, Any]]) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        for field in fields:
            parts = _split_field_path(field["field_path"])
            if not parts:
                continue
            node = schema
            for part in parts[:-1]:
                properties = node.setdefault("properties", {})
                if part not in properties:
                    properties[part] = {"type": "object", "properties": {}, "required": []}
                if field["is_required"]:
                    _set_required(node, part)
                node = properties[part]
            leaf = parts[-1]
            node.setdefault("properties", {})[leaf] = {
                "type": _db_type_to_json_schema_type(field["field_type"])
            }
            if field["is_required"]:
                _set_required(node, leaf)
        return schema