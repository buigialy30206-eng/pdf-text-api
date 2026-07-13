"""
PDF to Text API
Extract text from uploaded PDFs or PDF URLs. PyMuPDF backend.
"""
import io, subprocess, os, time, threading
from fastapi import FastAPI, Query, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import fitz  # PyMuPDF

app = FastAPI(title="PDF to Text API", version="1.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Cache for URL-based extraction
_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL = 3600  # 1 hour

class PDFResult(BaseModel):
    filename: str
    pages: int
    text: str
    text_length: int
    error: str = ""

def extract_text_from_bytes(data: bytes) -> tuple[int, str]:
    doc = fitz.open(stream=data, filetype="pdf")
    pages = len(doc)
    text = ""
    for page in doc:
        text += page.get_text() + "\n"
    return pages, text

@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "ok", "cache_size": len(_cache)}

@app.get("/")
async def root():
    return {"service": "PDF to Text API", "version": "1.1.0", "related": ["URL Metadata Extractor API"]}

@app.post("/extract", response_model=PDFResult)
async def extract(file: UploadFile = File(..., description="PDF file")):
    try:
        data = await file.read()
        pages, text = extract_text_from_bytes(data)
        return PDFResult(
            filename=file.filename or "upload.pdf",
            pages=pages, text=text[:50000], text_length=len(text)
        )
    except Exception as e:
        return PDFResult(filename=file.filename or "error", pages=0, text="", text_length=0, error=str(e)[:200])

@app.get("/extract-url", response_model=PDFResult)
async def extract_url(url: str = Query(..., description="URL of PDF file")):
    # Check cache
    with _cache_lock:
        entry = _cache.get(url)
        if entry and time.time() - entry["ts"] < CACHE_TTL:
            return PDFResult(**entry["data"])

    out_path = "/tmp/pdf_extract.pdf"
    cmd = ["curl", "-sL", "--connect-timeout", "8", "--max-time", "15", "-o", out_path, url]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=20)
        if r.returncode != 0:
            raise HTTPException(502, "Could not download PDF")
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "PDF download timed out")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e)[:200])

    try:
        with open(out_path, "rb") as f:
            data = f.read()
        os.remove(out_path)
    except Exception as e:
        raise HTTPException(500, f"Could not read downloaded file: {e}")

    try:
        pages, text = extract_text_from_bytes(data)
    except Exception as e:
        return PDFResult(filename=url.split("/")[-1], pages=0, text="", text_length=0, error=f"PDF parse error: {e}")

    result = PDFResult(
        filename=url.split("/")[-1], pages=pages, text=text[:50000], text_length=len(text)
    )

    # Save cache
    with _cache_lock:
        _cache[url] = {"data": result.model_dump(), "ts": time.time()}
        if len(_cache) > 200:
            oldest = min(_cache, key=lambda k: _cache[k]["ts"])
            del _cache[oldest]

    return result
