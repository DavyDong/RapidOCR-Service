import io

import pytest
import pymupdf
from fastapi.testclient import TestClient
from PIL import Image

from deployment.app import HERE, app
from deployment import documents

TEST_TOKEN = "rapidocr-auth-test-token-only"
AUTH_HEADERS = {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture(autouse=True)
def configured_token(monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN", TEST_TOKEN)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as session:
        yield session


def test_health_and_home(client):
    assert client.get("/health").json()["status"] == "ok"
    assert "RapidOCR" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200


def test_real_chinese_ocr(client):
    with (HERE / "sample.jpg").open("rb") as image:
        response = client.post("/api/ocr", headers=AUTH_HEADERS, files={"file": ("sample.jpg", image, "image/jpeg")})
    assert response.status_code == 200
    result = response.json()
    assert "正品促销" in result["text"]
    assert len(result["lines"]) >= 15
    assert all(0 <= line["confidence"] <= 1 for line in result["lines"])
    assert all(len(line["box"]) == 4 for line in result["lines"])


def test_blank_image(client):
    image = io.BytesIO()
    Image.new("RGB", (200, 200), "white").save(image, format="PNG")
    response = client.post("/api/ocr", headers=AUTH_HEADERS, files={"file": ("blank.png", image.getvalue())})
    assert response.status_code == 200
    assert response.json()["lines"] == []


@pytest.mark.parametrize("payload", [b"", b"not an image"])
def test_invalid_upload(client, payload):
    assert client.post("/api/ocr", headers=AUTH_HEADERS, files={"file": ("bad.png", payload)}).status_code == 400


def test_oversized_upload(client):
    response = client.post("/api/ocr", headers=AUTH_HEADERS, files={"file": ("huge.png", b"0" * (10 * 1024 * 1024 + 1))})
    assert response.status_code == 413


def test_busy_engine(client):
    with app.state.ocr_lock:
        response = client.post("/api/ocr", headers=AUTH_HEADERS, files={"file": ("sample.jpg", (HERE / "sample.jpg").read_bytes())})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "2"


@pytest.mark.parametrize("authorization", [None, "", "Bearer wrong-token", "Bearer", f"Basic {TEST_TOKEN}", f"Bearer {TEST_TOKEN} extra"])
def test_unauthorized_before_body_parsing(client, authorization):
    headers = {"Content-Type": "multipart/form-data; boundary=broken"}
    if authorization is not None:
        headers["Authorization"] = authorization
    response = client.post("/api/ocr", headers=headers, content=b"invalid multipart data")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert TEST_TOKEN not in response.text


def test_auth_on_trailing_slash(client):
    response = client.post("/api/ocr/", content=b"invalid", follow_redirects=False)
    assert response.status_code == 401


@pytest.mark.parametrize("configured", [None, "", "  "])
def test_unconfigured_service_fails_closed(client, monkeypatch, configured):
    if configured is None:
        monkeypatch.delenv("ACCESS_TOKEN")
    else:
        monkeypatch.setenv("ACCESS_TOKEN", configured)
    response = client.post("/api/ocr", headers=AUTH_HEADERS, content=b"invalid")
    assert response.status_code == 503
    assert client.get("/health").status_code == 200


def test_openapi_bearer_security(client):
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/api/ocr"]["post"]["security"] == [{"HTTPBearer": []}]
    assert schema["paths"]["/ocr/invoice"]["post"]["security"] == [{"HTTPBearer": []}]
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    for path in ["/", "/docs", "/openapi.json", "/static/app.js"]:
        assert TEST_TOKEN not in client.get(path).text


def test_corrupt_pdf(client):
    response = client.post("/api/ocr", headers=AUTH_HEADERS, files={"file": ("sample.pdf", b"%PDF-1.7\n", "application/pdf")})
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


def pdf_bytes(text="Invoice DEMO-001 Total EUR 100.00", pages=1, rotation=0, encrypted=False):
    with pymupdf.open() as doc:
        for _ in range(pages):
            page = doc.new_page()
            if text:
                page.insert_text((48, 80), text, fontsize=18)
            page.set_rotation(rotation)
        return doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="reader") if encrypted else doc.tobytes()


def post_pdf(client, payload, route="/api/ocr", **kwargs):
    return client.post(route, headers=AUTH_HEADERS, files={"file": ("upload.pdf", payload, "application/pdf")}, **kwargs)


def test_native_pdf_skips_ocr(client, monkeypatch):
    def should_not_run(_):
        raise AssertionError("Native PDF must not invoke OCR")
    monkeypatch.setattr(app.state, "engine", should_not_run)
    response = post_pdf(client, pdf_bytes(pages=2))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["type"] == "pdf" and result["pages"] == 2
    assert len(result["page_results"]) == 2
    assert all(page["method"] == "native" for page in result["page_results"])
    assert [line["page_number"] for line in result["lines"]] == [1, 2]
    assert all(line["confidence"] is None for line in result["lines"])
    assert "DEMO-001" in result["text"]


def test_real_native_and_scanned_pdf(client):
    response = post_pdf(client, (HERE / "sample.pdf").read_bytes())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["pages"] == 2
    assert [page["method"] for page in result["page_results"]] == ["native", "ocr"]
    assert "DEMO-2026-001" in result["page_results"][0]["text"]
    assert "极速发货" in result["page_results"][1]["text"]
    assert len(result["page_results"][1]["lines"]) >= 15
    assert all(line["page_number"] == 2 for line in result["page_results"][1]["lines"])
    for page in result["page_results"]:
        assert page["coordinate_unit"] == "points"
        for line in page["lines"]:
            assert all(0 <= x <= page["width"] and 0 <= y <= page["height"] for x, y in line["box"])


def test_mixed_page_does_not_drop_scanned_content(client):
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((48, 45), "INVOICE HEADER", fontsize=18)
        page.insert_image(pymupdf.Rect(48, 100, 547, 770), filename=str(HERE / "sample.jpg"))
        response = post_pdf(client, doc.tobytes())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["pages"] == 1
    assert result["page_results"][0]["method"] == "ocr"
    assert "正品促销" in result["text"]
    assert "INVOICE" in result["text"]


def test_blank_pdf_preserves_page(client):
    response = post_pdf(client, pdf_bytes(text=None))
    assert response.status_code == 200, response.text
    assert response.json()["pages"] == 1
    assert response.json()["page_results"][0]["lines"] == []


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_rotated_native_pdf_coordinates(client, rotation):
    result = post_pdf(client, pdf_bytes(rotation=rotation)).json()
    page = result["page_results"][0]
    assert page["method"] == "native"
    assert "DEMO-001" in page["text"]
    assert (page["width"] > page["height"]) == (rotation in {90, 270})
    assert all(0 <= x <= page["width"] and 0 <= y <= page["height"] for line in page["lines"] for x, y in line["box"])


def test_force_ocr_native_pdf(client):
    response = post_pdf(client, pdf_bytes(), data={"force_ocr": "true"})
    assert response.status_code == 200, response.text
    assert response.json()["page_results"][0]["method"] == "ocr"
    assert "100.00" in response.json()["text"]


def test_content_detection_and_invoice_alias(client):
    response = client.post("/ocr/invoice", headers=AUTH_HEADERS, files={"file": ("wrong.jpg", pdf_bytes(), "image/jpeg")})
    assert response.status_code == 200, response.text
    assert response.json()["type"] == "pdf"
    response = post_pdf(client, (HERE / "sample.jpg").read_bytes(), route="/ocr/invoice")
    assert response.status_code == 200, response.text
    assert response.json()["type"] == "image"


@pytest.mark.parametrize("route", ["/ocr/invoice", "/ocr/invoice/"])
def test_invoice_alias_is_protected_before_body_parsing(client, route):
    response = client.post(route, content=b"invalid multipart", follow_redirects=False)
    assert response.status_code == 401


def test_encrypted_pdf_and_page_limit(client):
    assert post_pdf(client, pdf_bytes(encrypted=True)).status_code == 422
    assert post_pdf(client, pdf_bytes(pages=21)).status_code == 413


def test_pdf_time_limit_releases_lock(client, monkeypatch):
    monkeypatch.setattr(documents, "MAX_PDF_SECONDS", -1)
    response = post_pdf(client, pdf_bytes())
    assert response.status_code == 422
    assert not app.state.ocr_lock.locked()


def test_inference_failure_releases_lock(client, monkeypatch):
    def broken(_):
        raise RuntimeError("engine unavailable")
    monkeypatch.setattr(app.state, "engine", broken)
    response = post_pdf(client, pdf_bytes(), data={"force_ocr": "true"})
    assert response.status_code == 500
    assert not app.state.ocr_lock.locked()
    assert "engine unavailable" not in response.text


def test_pdf_render_pixel_limit():
    with pymupdf.open() as doc:
        page = doc.new_page(width=20000, height=18000)
        with documents.render_page(page) as image:
            assert image.width * image.height <= documents.MAX_RENDER_PIXELS
            assert max(image.size) <= documents.MAX_RENDER_SIDE


@pytest.mark.parametrize("format", ["TIFF", "WEBP", "BMP"])
def test_additional_image_formats(client, format):
    data = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(data, format=format)
    response = client.post("/api/ocr", headers=AUTH_HEADERS, files={"file": ("file", data.getvalue())})
    assert response.status_code == 200
    assert response.json()["type"] == "image"


def test_multiframe_tiff_does_not_silently_drop_pages(client):
    data = io.BytesIO()
    a = Image.new("RGB", (100, 100), "white")
    b = Image.new("RGB", (100, 100), "black")
    a.save(data, format="TIFF", save_all=True, append_images=[b])
    response = client.post("/api/ocr", headers=AUTH_HEADERS, files={"file": ("file.tiff", data.getvalue())})
    assert response.status_code == 422
