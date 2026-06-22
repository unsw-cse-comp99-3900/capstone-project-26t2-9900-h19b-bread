from fastapi import FastAPI

app = FastAPI(title="E-Invoicing API Publisher Backend")

@app.get("/")
def root():
    return {"message": "Backend is running"}