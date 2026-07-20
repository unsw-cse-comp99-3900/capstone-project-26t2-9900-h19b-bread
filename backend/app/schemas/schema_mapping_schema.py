from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class NamedSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1)
    schema_definition: dict[str, Any] = Field(..., alias="schema")


class SchemaCompareRequest(BaseModel):
    source_schema: dict[str, Any]
    target_schema: dict[str, Any]
    source_name: str = "Source"
    target_name: str = "Target"


class MatrixRequest(BaseModel):
    schemas: list[NamedSchema] = Field(..., min_length=1)


class TransformPreviewRequest(BaseModel):
    source_schema: dict[str, Any]
    target_schema: dict[str, Any]
    data: dict[str, Any]
    format: Literal["json", "xml"] = "json"
    source_name: str = "Source"
    target_name: str = "Target"


class InferJsonSchemaRequest(BaseModel):
    data: Any


class InferXmlSchemaRequest(BaseModel):
    xml_content: str = Field(..., min_length=1)


class SchemaMappingErrorResponse(BaseModel):
    detail: str


class SchemaInferenceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_definition: dict[str, Any] = Field(..., alias="schema")


class SchemaCompareResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str
    target: str
    compatibility: str
    summary: dict[str, Any]
    issues: list[dict[str, Any]]
    normalized_source: dict[str, Any]
    normalized_target: dict[str, Any]


class MatrixResponse(BaseModel):
    matrix: list[list[dict[str, Any]]]


class TransformPreviewResponse(BaseModel):
    result: Any
    format: Literal["json", "xml"]
    mapping_status: str
    mapping: dict[str, Any]
    comparison: dict[str, Any]
    transform_code: str
