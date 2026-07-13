"""
PDF to Text API
Extract text from uploaded PDFs or PDF URLs. PyMuPDF backend.
"""

import io, subprocess, os

from fastapi import FastAPI, Query, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import fitz  # PyMuPDF

app = FastAPI(title="PDF to Text API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "ok"}



class PDFResult(BaseModel):
    filename: str
    pages: int
    text: str
    text_length: int


def extract_text_from_bytes(data: bytes) -> tuple[int, str]:
    doc = fitz.open(stream=data, filetype="pdf")
    pages = len(doc)
    text = ""
    for page in doc:
        text += page.get_text() + "\n"
    return pages, text


@app.api_route("/health", methods=["GET", "HEAD"])
async def health(): return {"status": "ok"}


@app.get("/")
async def root(): return {"service": "PDF to Text API", "version": "1.0.0"}


@app.post("/extract", response_model=PDFResult)
async def extract(file: UploadFile = File(..., description="PDF file to extract text from")):
    data = await file.read()
    pages, text = extract_text_from_bytes(data)
    return PDFResult(filename=file.filename or "upload.pdf", pages=pages, text=text[:50000], text_length=len(text))


@app.get("/extract-url", response_model=PDFResult)
async def extract_url(url: str = Query(..., description="URL of PDF file")):
    cmd = ["curl", "-sL", "--connect-timeout", "10", "--max-time", "15", "-o", "/tmp/pdf.pdf", url]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise HTTPException(502, "Could not download PDF")

    with open("/tmp/pdf.pdf", "rb") as f:
        data = f.read()
    pages, text = extract_text_from_bytes(data)
    return PDFResult(filename=url.split("/")[-1], pages=pages, text=text[:50000], text_length=len(text))
