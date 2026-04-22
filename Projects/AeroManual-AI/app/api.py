import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from app.config import UPLOAD_DIR
from app.document_loader import load_and_split
from app.vector_store import add_documents
from app.rag_chain import ask

from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="AeroManual AI")
Instrumentator().instrument(app).expose(app)


class QueryRequest(BaseModel):
    question: str


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    dest = UPLOAD_DIR / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        chunks = load_and_split(str(dest))
        count = add_documents(chunks)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process file: {e}")

    return {"filename": file.filename, "chunks_indexed": count}


@app.post("/query")
async def query_documents(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    return ask(req.question)


@app.get("/health")
async def health():
    return {"status": "ok"}
