# FastAPI entry point

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import workspaces, documents, chat, eval as eval_router, compare, conversations


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
app.include_router(chat.router)
app.include_router(eval_router.router)
app.include_router(compare.router)
app.include_router(conversations.router)


@app.get("/healthz")
async def health():
    return {"status": "ok"}