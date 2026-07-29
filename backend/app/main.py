# FastAPI entry point

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import workspaces, documents


app = FastAPI(title="DocuSense API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workspaces.router)
app.include_router(documents.router)


@app.get("/healthz")
async def health():
    return {"status": "ok"}