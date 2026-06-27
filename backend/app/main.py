from fastapi import FastAPI
from app.routers import validation, auth, submissions

app = FastAPI(title="E-Invoicing API Publisher Backend")

app.include_router(validation.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(submissions.router, prefix="/api/v1")

@app.get("/")
def root():
    return {"message": "Backend is running"}