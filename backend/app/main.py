from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg.errors import IntegrityError

from app.lifecycle import (
    ApiNotFoundError,
    ApiPermissionError,
    CurrentVersionNotFoundError,
    InvalidStatusTransitionError,
)
from app.routers import auth, lifecycle, submissions, validation, version_history

app = FastAPI(title="E-Invoicing API Publisher Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(validation.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(submissions.router, prefix="/api/v1")
app.include_router(lifecycle.router, prefix="/api")
app.include_router(version_history.router, prefix="/api")


@app.exception_handler(ApiNotFoundError)
async def handle_api_not_found(request: Request, exc: ApiNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": "ApiNotFound", "message": str(exc)},
    )


@app.exception_handler(CurrentVersionNotFoundError)
async def handle_version_not_found(
    request: Request,
    exc: CurrentVersionNotFoundError,
) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": "CurrentVersionNotFound", "message": str(exc)},
    )


@app.exception_handler(ApiPermissionError)
async def handle_api_permission_error(
    request: Request,
    exc: ApiPermissionError,
) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={"error": "ApiPermissionDenied", "message": str(exc)},
    )


@app.exception_handler(InvalidStatusTransitionError)
async def handle_invalid_transition(
    request: Request,
    exc: InvalidStatusTransitionError,
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"error": "InvalidStatusTransition", "message": str(exc)},
    )


@app.exception_handler(IntegrityError)
async def handle_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
    constraint = getattr(exc.diag, "constraint_name", None)
    message = "Request violates a database constraint"
    if constraint:
        message += f" ({constraint})"
    message += "; a referenced record may not exist."
    return JSONResponse(
        status_code=400,
        content={"error": "IntegrityError", "message": message},
    )


@app.get("/")
def root():
    return {"message": "Backend is running"}
