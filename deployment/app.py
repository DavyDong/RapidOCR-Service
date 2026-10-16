import logging
import os
import secrets
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Security, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.security.utils import get_authorization_scheme_param
from fastapi.staticfiles import StaticFiles

from deployment.documents import DocumentResult, extract_document
from deployment.engine import create_engine

HERE = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 64 * 1024
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    app.state.engine = create_engine()
    app.state.ocr_lock = threading.Lock()
    yield
    app.state.engine = None


app = FastAPI(
    title="RapidOCR Image + PDF API",
    version="1.1.0",
    description="Image and PDF text extraction. [Source code](https://github.com/DavyDong/RapidOCR-Service).",
    license_info={"name": "AGPL-3.0-only", "url": "https://github.com/DavyDong/RapidOCR-Service/blob/main/LICENSE"},
    lifespan=lifespan,
)
bearer = HTTPBearer(
    auto_error=False,
    description="Enter the ACCESS_TOKEN configured for this application (without the Bearer prefix).",
)


def validate_access_token(scheme: str, token: str):
    expected = os.environ.get("ACCESS_TOKEN", "")
    if not expected.strip():
        raise HTTPException(503, "识别服务未配置访问令牌")
    if scheme.lower() != "bearer" or not token or not secrets.compare_digest(
        token.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(
            401, "访问令牌缺失或无效", headers={"WWW-Authenticate": "Bearer"}
        )


def require_access_token(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer),
):
    validate_access_token(
        credentials.scheme if credentials else "",
        credentials.credentials if credentials else "",
    )


@app.middleware("http")
async def protect_api_and_limit_request_size(request: Request, call_next):
    # Authenticate before FastAPI parses or spools the uploaded multipart body.
    if request.url.path.startswith(("/api/", "/ocr/")):
        try:
            validate_access_token(
                *get_authorization_scheme_param(request.headers.get("authorization"))
            )
        except HTTPException as error:
            return JSONResponse(
                {"detail": error.detail}, status_code=error.status_code, headers=error.headers
            )
    if request.method == "POST":
        length = request.headers.get("content-length")
        if length is None:
            return JSONResponse({"detail": "Content-Length is required"}, status_code=411)
        try:
            size = int(length)
        except ValueError:
            return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
        if size < 0 or size > MAX_REQUEST_BYTES:
            return JSONResponse({"detail": "文件不能超过 10 MB"}, status_code=413)
    return await call_next(request)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(HERE / "static" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "engine": "RapidOCR", "model": "PP-OCRv6", "backend": "onnxruntime", "supports": ["image", "pdf"]}


@app.get("/sample.jpg", include_in_schema=False)
def sample():
    return FileResponse(HERE / "sample.jpg", media_type="image/jpeg")


@app.get("/sample.pdf", include_in_schema=False)
def sample_pdf():
    return FileResponse(HERE / "sample.pdf", media_type="application/pdf")


@app.post("/api/ocr", dependencies=[Depends(require_access_token)], response_model=DocumentResult)
@app.post("/ocr/invoice", dependencies=[Depends(require_access_token)], response_model=DocumentResult)
def recognize(request: Request, file: UploadFile, force_ocr: bool = Form(False)):
    """Extract image/PDF text, automatically selecting native text or OCR per PDF page.

    Limit: 10 MB per file, 20 PDF pages. Page numbers start at 1. PDF boxes use
    points (1/72 inch), image boxes use pixels. Native text has null confidence.
    force_ocr=true also renders native PDF pages. Both paths require Bearer auth.
    """
    try:
        data = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "文件不能超过 10 MB")
        if not data:
            raise HTTPException(400, "请选择图片或 PDF 文件")
        lock = request.app.state.ocr_lock
        if not lock.acquire(blocking=False):
            raise HTTPException(429, "正在处理其他文件，请稍后重试", headers={"Retry-After": "2"})
        try:
            return extract_document(data, request.app.state.engine, force_ocr)
        except HTTPException:
            raise
        except Exception:
            logger.exception("Document extraction failed")
            raise HTTPException(500, "文件识别失败，请检查文件后重试")
        finally:
            lock.release()
    finally:
        file.file.close()


app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
