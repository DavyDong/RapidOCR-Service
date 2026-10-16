"""Check a running deployment with authenticated image and PDF requests."""

import argparse
import json
import os
from pathlib import Path

import requests

parser = argparse.ArgumentParser()
parser.add_argument("url", nargs="?", default="http://127.0.0.1:8765")
args = parser.parse_args()
base = args.url.rstrip("/")
sample = Path(__file__).resolve().parents[1] / "deployment" / "sample.jpg"
sample_pdf = sample.with_suffix(".pdf")
token = os.environ.get("ACCESS_TOKEN", "")
if not token.strip():
    raise SystemExit("Set ACCESS_TOKEN in the environment before running this check.")
headers = {"Authorization": f"Bearer {token}"}

health = requests.get(f"{base}/health", timeout=30)
health.raise_for_status()
assert health.json()["status"] == "ok"
assert health.json()["supports"] == ["image", "pdf"]
unauthorized = requests.post(f"{base}/api/ocr", data=b"invalid body", timeout=30)
assert unauthorized.status_code == 401, "Requests without a token must be rejected"
wrong_token = requests.post(
    f"{base}/api/ocr", headers={"Authorization": f"Bearer {token}-invalid"},
    data=b"invalid body", timeout=30,
)
assert wrong_token.status_code == 401, "Requests with an invalid token must be rejected"
alias_unauthorized = requests.post(f"{base}/ocr/invoice", data=b"invalid body", timeout=30)
assert alias_unauthorized.status_code == 401
with sample.open("rb") as image:
    response = requests.post(
        f"{base}/api/ocr", headers=headers, files={"file": ("sample.jpg", image, "image/jpeg")}, timeout=120
    )
response.raise_for_status()
result = response.json()
assert "正品促销" in result["text"], result
assert len(result["lines"]) >= 15, result
invalid = requests.post(
    f"{base}/api/ocr", headers=headers, files={"file": ("invalid.jpg", b"invalid")}, timeout=30
)
assert invalid.status_code == 400, invalid.text
corrupt_pdf = requests.post(
    f"{base}/api/ocr", headers=headers,
    files={"file": ("sample.pdf", b"%PDF-1.7\n", "application/pdf")}, timeout=30,
)
assert corrupt_pdf.status_code == 400, corrupt_pdf.text
with sample_pdf.open("rb") as pdf_file:
    pdf = requests.post(
        f"{base}/ocr/invoice", headers=headers,
        files={"file": ("sample.pdf", pdf_file, "application/pdf")}, timeout=120,
    )
pdf.raise_for_status()
pdf_result = pdf.json()
assert pdf_result["type"] == "pdf" and pdf_result["pages"] == 2
assert [page["method"] for page in pdf_result["page_results"]] == ["native", "ocr"]
assert "DEMO-2026-001" in pdf_result["page_results"][0]["text"]
assert "极速发货" in pdf_result["page_results"][1]["text"]
assert len(pdf_result["page_results"][1]["lines"]) >= 15
for path in ["/", "/static/app.js", "/openapi.json"]:
    assert token not in requests.get(f"{base}{path}", timeout=30).text, "A public response exposed the token"
print(json.dumps({
    "url": base,
    "health": health.json(),
    "line_count": len(result["lines"]),
    "elapsed_seconds": result["elapsed_seconds"],
    "first_line": result["lines"][0]["text"],
    "invalid_image_status": invalid.status_code,
    "missing_token_status": unauthorized.status_code,
    "invalid_token_status": wrong_token.status_code,
    "pdf_status": pdf.status_code,
    "pdf_pages": pdf_result["pages"],
    "pdf_page_methods": [page["method"] for page in pdf_result["page_results"]],
    "pdf_line_counts": [len(page["lines"]) for page in pdf_result["page_results"]],
    "pdf_elapsed_seconds": pdf_result["elapsed_seconds"],
    "corrupt_pdf_status": corrupt_pdf.status_code,
    "invoice_alias_missing_token_status": alias_unauthorized.status_code,
}, ensure_ascii=True, indent=2))
