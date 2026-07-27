from typing import Any

from fastapi import APIRouter, HTTPException

from app.schemas.schema_mapping_schema import (
    ApiSchemaCompareRequest,
    ApiSchemaCompareResponse,
    ApiSchemaSummary,
    ApiSchemaTransformPreviewRequest,
    ApiSchemaTransformPreviewResponse,
    InferJsonSchemaRequest,
    InferXmlSchemaRequest,
    MatrixRequest,
    MatrixResponse,
    SchemaCompareRequest,
    SchemaCompareResponse,
    SchemaInferenceResponse,
    SchemaMappingErrorResponse,
    TransformPreviewRequest,
    TransformPreviewResponse,
)
from app.services.schema_mapping.service import (
    SchemaMappingError,
    build_compatibility_matrix,
    compare_schema_pair,
    compare_database_api_schemas,
    infer_json_schema_from_sample,
    infer_xml_schema_from_sample,
    list_database_api_schemas,
    transform_database_mapping_preview,
    transform_preview,
)

router = APIRouter(prefix="/schema-mapping", tags=["schema-mapping"])


def _bad_request(exc: SchemaMappingError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/compare",
    response_model=SchemaCompareResponse,
    responses={400: {"model": SchemaMappingErrorResponse}},
)
def compare_schemas_endpoint(request: SchemaCompareRequest) -> dict[str, Any]:
    try:
        return compare_schema_pair(
            source_schema=request.source_schema,
            target_schema=request.target_schema,
            source_name=request.source_name,
            target_name=request.target_name,
        )
    except SchemaMappingError as exc:
        raise _bad_request(exc) from exc


@router.get(
    "/api-schemas",
    response_model=list[ApiSchemaSummary],
    responses={400: {"model": SchemaMappingErrorResponse}},
)
def list_api_schemas_endpoint() -> list[dict[str, Any]]:
    try:
        return list_database_api_schemas()
    except SchemaMappingError as exc:
        raise _bad_request(exc) from exc


@router.post(
    "/compare-api-schemas",
    response_model=ApiSchemaCompareResponse,
    responses={400: {"model": SchemaMappingErrorResponse}},
)
def compare_api_schemas_endpoint(request: ApiSchemaCompareRequest) -> dict[str, Any]:
    try:
        return compare_database_api_schemas(
            source_schema_id=request.source_schema_id,
            target_schema_id=request.target_schema_id,
            save_mapping=request.save_mapping,
        )
    except SchemaMappingError as exc:
        raise _bad_request(exc) from exc


@router.post(
    "/transform-api-preview",
    response_model=ApiSchemaTransformPreviewResponse,
    responses={400: {"model": SchemaMappingErrorResponse}},
)
def transform_api_preview_endpoint(request: ApiSchemaTransformPreviewRequest) -> dict[str, Any]:
    try:
        return transform_database_mapping_preview(
            mapping_id=request.mapping_id,
            data=request.data,
            output_format=request.format,
            save_run=request.save_run,
        )
    except SchemaMappingError as exc:
        raise _bad_request(exc) from exc


@router.post(
    "/matrix",
    response_model=MatrixResponse,
    responses={400: {"model": SchemaMappingErrorResponse}},
)
def matrix_endpoint(request: MatrixRequest) -> dict[str, Any]:
    try:
        return build_compatibility_matrix(
            [
                {"name": schema.name, "schema": schema.schema_definition}
                for schema in request.schemas
            ]
        )
    except SchemaMappingError as exc:
        raise _bad_request(exc) from exc


@router.post(
    "/transform-preview",
    response_model=TransformPreviewResponse,
    responses={400: {"model": SchemaMappingErrorResponse}},
)
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
        raise _bad_request(exc) from exc


@router.post(
    "/infer-json-schema",
    response_model=SchemaInferenceResponse,
    responses={400: {"model": SchemaMappingErrorResponse}},
)
def infer_json_schema_endpoint(request: InferJsonSchemaRequest) -> dict[str, Any]:
    try:
        return {"schema": infer_json_schema_from_sample(request.data)}
    except SchemaMappingError as exc:
        raise _bad_request(exc) from exc


@router.post(
    "/infer-xml-schema",
    response_model=SchemaInferenceResponse,
    responses={400: {"model": SchemaMappingErrorResponse}},
)
def infer_xml_schema_endpoint(request: InferXmlSchemaRequest) -> dict[str, Any]:
    try:
        return {"schema": infer_xml_schema_from_sample(request.xml_content)}
    except SchemaMappingError as exc:
        raise _bad_request(exc) from exc
