from fastapi import APIRouter
from app.schemas.validation_schema import ValidationRequest, ValidationResponse
from app.services.validation_service import validate_specification

router = APIRouter(prefix="/validation", tags=["validation"])


@router.post("/spec", response_model=ValidationResponse)
def validate_spec_endpoint(request: ValidationRequest) -> ValidationResponse:
    return validate_specification(request)