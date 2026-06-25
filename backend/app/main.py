from fastapi import FastAPI
from app.routers import validation

app = FastAPI(title="E-Invoicing API Publisher Backend")

app.include_router(validation.router, prefix="/api/v1")


@app.get("/")
def root():
    return {"message": "Backend is running"}