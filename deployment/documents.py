"""Bounded image/PDF extraction using the shared RapidOCR CPU engine."""

import io
import math
import time
import warnings
from typing import Literal

import pymupdf
from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel

MAX_PIXELS = 24_000_000
MAX_PDF_PAGES = 20
PDF_DPI = 200
MAX_RENDER_PIXELS = 4_000_000
MAX_RENDER_SIDE = 3000
MAX_PDF_SECONDS = 45


class TextLine(BaseModel):
    text: str
    confidence: float | None
    box: list[list[float]]
    page_number: int


class PageResult(BaseModel):
    page_number: int
    width: float
    height: float
    coordinate_unit: Literal["pixels", "points"]
    method: Literal["native", "ocr"]
    text: str
    lines: list[TextLine]
    elapsed_seconds: float


class DocumentResult(BaseModel):
    type: Literal["image", "pdf"]
    pages: int
    page_results: list[PageResult]
    text: str
    lines: list[TextLine]
    elapsed_seconds: float
    width: float | None = None
    height: float | None = None


def ocr_lines(engine, image, page_number=1):
    result = engine(image)
    if result.txts is None:
        return []
    return [
        {"text": text, "confidence": float(score), "box": box.tolist(), "page_number": page_number}
        for text, score, box in zip(result.txts, result.scores, result.boxes)
    ]


def page_result(page_number, width, height, unit, method, lines, started):
    return {
        "page_number": page_number, "width": width, "height": height,
        "coordinate_unit": unit, "method": method, "lines": lines,
        "text": "\n".join(line["text"] for line in lines),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def document_result(kind, pages, started):
    return {
        "type": kind, "pages": len(pages), "page_results": pages,
        "text": "\n\n".join(page["text"] for page in pages),
        "lines": [line for page in pages for line in page["lines"]],
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "width": pages[0]["width"] if kind == "image" else None,
        "height": pages[0]["height"] if kind == "image" else None,
    }


def decode_image(data):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP", "BMP", "TIFF"}:
                    raise HTTPException(415, "支持 PNG、JPEG、WebP、BMP、TIFF 或 PDF")
                if source.width * source.height > MAX_PIXELS:
                    raise HTTPException(413, "图片像素不能超过 2400 万")
                if getattr(source, "n_frames", 1) > 1:
                    raise HTTPException(422, "多帧图片请拆分为单张图片或转换为 PDF")
                return ImageOps.exif_transpose(source).convert("RGB")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(413, "图片像素过大")
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(400, "无法读取文件，请上传有效的图片或 PDF")


def extract_image(data, engine):
    started = time.perf_counter()
    with decode_image(data) as image:
        lines = ocr_lines(engine, image)
        page = page_result(1, image.width, image.height, "pixels", "ocr", lines, started)
    return document_result("image", [page], started)


def native_lines(page, number):
    # Exclude embedded image bytes: only metadata is needed for the OCR decision.
    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
    blocks = page.get_text("dict", flags=flags, sort=True)["blocks"]
    lines = []
    for block in blocks:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            if not text:
                continue
            rect = pymupdf.Rect(line["bbox"])
            points = [point * page.rotation_matrix for point in (rect.tl, rect.tr, rect.br, rect.bl)]
            lines.append({
                "text": text, "confidence": None, "page_number": number,
                "box": [[round(point.x, 3), round(point.y, 3)] for point in points],
            })
    return lines


def render_page(page):
    width, height = page.rect.width, page.rect.height
    if not all(math.isfinite(value) and value > 0 for value in (width, height)):
        raise HTTPException(400, "PDF 页面尺寸无效")
    scale = min(PDF_DPI / 72, math.sqrt(MAX_RENDER_PIXELS / (width * height)), MAX_RENDER_SIDE / max(width, height))
    # Account for the pixel rounding done by MuPDF before allocating the pixmap.
    while math.ceil(width * scale) * math.ceil(height * scale) > MAX_RENDER_PIXELS:
        scale *= 0.99
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False)
    return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def check_pdf_deadline(started):
    if time.perf_counter() - started > MAX_PDF_SECONDS:
        raise HTTPException(422, "PDF 处理时间过长，请拆分文件后重试")


def extract_pdf(data, engine, force_ocr=False):
    started = time.perf_counter()
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError, ValueError):
        raise HTTPException(400, "PDF 文件损坏或格式无效")
    with document:
        if document.needs_pass:
            raise HTTPException(422, "PDF 需要密码，请上传已解密的文件")
        if not document.page_count:
            raise HTTPException(400, "PDF 不包含页面")
        if document.page_count > MAX_PDF_PAGES:
            raise HTTPException(413, f"PDF 最多支持 {MAX_PDF_PAGES} 页，请拆分后上传")
        pages = []
        for index in range(document.page_count):
            check_pdf_deadline(started)
            page_started = time.perf_counter()
            page = document.load_page(index)
            lines = native_lines(page, index + 1)
            text = "\n".join(line["text"] for line in lines)
            # Even a page number or watermark can coexist with a scanned invoice.
            # Render mixed pages instead of treating any text layer as complete.
            needs_ocr = (
                force_ocr or not text or "\ufffd" in text
                or bool(page.get_image_info())
                or page.first_annot is not None or page.first_widget is not None
            )
            method = "native"
            if needs_ocr:
                with render_page(page) as image:
                    lines = ocr_lines(engine, image, index + 1)
                    sx, sy = page.rect.width / image.width, page.rect.height / image.height
                    for line in lines:
                        line["box"] = [[round(x * sx, 3), round(y * sy, 3)] for x, y in line["box"]]
                method = "ocr"
            check_pdf_deadline(started)
            pages.append(page_result(index + 1, page.rect.width, page.rect.height, "points", method, lines, page_started))
    return document_result("pdf", pages, started)


def extract_document(data, engine, force_ocr=False):
    # Sniff bytes rather than trusting the user-supplied filename or Content-Type.
    if data.lstrip().startswith(b"%PDF-"):
        return extract_pdf(data, engine, force_ocr)
    return extract_image(data, engine)
