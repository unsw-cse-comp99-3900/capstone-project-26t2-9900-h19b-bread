from typing import Any

from fastapi import APIRouter, HTTPException

from app.schemas.schema_mapping_schema import (
    InferJsonSchemaRequest,
    InferXmlSchemaRequest,
    MatrixRequest,
    SchemaCompareRequest,
    TransformPreviewRequest,
)
from app.services.schema_mapping.service import (
    SchemaMappingError,
    build_compatibility_matrix,
    compare_schema_pair,
    infer_json_schema_from_sample,
    infer_xml_schema_from_sample,
    transform_preview,
)

router = APIRouter(prefix="/schema-mapping", tags=["schema-mapping"])


@router.post("/compare")
def compare_schemas_endpoint(request: SchemaCompareRequest) -> dict[str, Any]:
    return compare_schema_pair(
        source_schema=request.source_schema,
        target_schema=request.target_schema,
        source_name=request.source_name,
        target_name=request.target_name,
    )


@router.post("/matrix")
def matrix_endpoint(request: MatrixRequest) -> dict[str, Any]:
    try:
        return build_compatibility_matrix(
            [schema.model_dump(by_alias=True) for schema in request.schemas]
        )
    except SchemaMappingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/transform-preview")
def transform_preview_endpoint(request: TransformPreviewRequest) -> dict[str, Any]:
    try:
        return transform_preview(
            source_schema=request.source_schema,
            target_schema=request.target_schema,
            data=request.data,
            output_format=request.format,
            source_name=request.source_name,
            target_name=request.target_name,
        )
    except SchemaMappingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/infer-json-schema")
def infer_json_schema_endpoint(request: InferJsonSchemaRequest) -> dict[str, Any]:
    return {"schema": infer_json_schema_from_sample(request.data)}


@router.post("/infer-xml-schema")
def infer_xml_schema_endpoint(request: InferXmlSchemaRequest) -> dict[str, Any]:
    try:
        return {"schema": infer_xml_schema_from_sample(request.xml_content)}
    except SchemaMappingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
