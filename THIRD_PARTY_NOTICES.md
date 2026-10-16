# Third-party components and licensing

This notice describes the image/PDF web service added to the RapidOCR checkout.
It does not replace any upstream license or grant additional rights to third-party
code, model weights, or sample assets. Dependency versions are pinned in
[requirements.txt](requirements.txt).

## Provenance

| Component | Role in this application | License / source |
| --- | --- | --- |
| RapidOCR | OCR implementation imported from `python/rapidocr`; upstream base commit `7cfd3d9ef786a2e538ca30df700325e72e85b5f5` | [Apache-2.0](LICENSES/Apache-2.0.txt), [upstream repository](https://github.com/RapidAI/RapidOCR) |
| RapidOCRPDF | Design reference for native-text extraction versus page rendering and OCR; its Python package is not installed or vendored by this integration | [Upstream Apache-2.0 license](https://github.com/RapidAI/RapidOCRPDF/blob/main/LICENSE), [implementation](https://github.com/RapidAI/RapidOCRPDF/blob/main/rapidocr_pdf/main.py) |
| PyMuPDF / MuPDF | Actual PDF parsing, text extraction and rendering dependency | [AGPLv3 or Artifex commercial license](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright) |
| ONNX Runtime | CPU inference | [MIT](https://github.com/microsoft/onnxruntime/blob/main/LICENSE) |
| FastAPI | HTTP API and OpenAPI documentation | [MIT](https://github.com/fastapi/fastapi/blob/master/LICENSE) |
| Starlette / Uvicorn | ASGI framework and server | [Starlette BSD-3-Clause](https://github.com/Kludex/starlette/blob/main/LICENSE.md), [Uvicorn BSD-3-Clause](https://github.com/Kludex/uvicorn/blob/main/LICENSE.md) |
| Pillow | Image decoding and orientation | [Pillow license](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |

The new integration consists of `deployment/`, the local/deployment scripts,
Cloud Foundry manifests, and the root dependency lock. The main READMEs have been
extended to document this integration, with the original content retained in a
folded upstream section. The original RapidOCR documentation is also
available at the [upstream base revision](https://github.com/RapidAI/RapidOCR/tree/7cfd3d9ef786a2e538ca30df700325e72e85b5f5).
This is not an official RapidAI or SAP product release.

## License scope and source availability

The added integration code, deployment helpers, configuration and documentation
are released under **AGPL-3.0-only**, as provided in the root [LICENSE](LICENSE).
Copyright (c) 2026 DavyDong and contributors, for those additions.
The combined image/PDF service is distributed under AGPL-3.0-only.

Unmodified upstream RapidOCR source and assets retain their original terms.
The original root Apache-2.0 license, including its copyright notice, is preserved
verbatim in [LICENSES/Apache-2.0.txt](LICENSES/Apache-2.0.txt);
[python/LICENSE](python/LICENSE) is unchanged. Original third-party files are not
relicensed by the root license change. More specific component and model notices
continue to apply. RapidOCRPDF's Apache-2.0 license does not change PyMuPDF's license.

[Artifex's licensing guidance](https://artifex.com/licensing) states that a server
application using its AGPL edition must disclose the application's full source
under AGPL to users interacting with it. Publishing this integration while
retaining the community PyMuPDF dependency therefore requires an AGPL-compliant
release of the combined application, including the applicable license notices
and access to the corresponding source for the running version. Keep the
upstream Apache notices as well. A repository link to the original RapidOCR
project alone does not provide the added service's source.

Complete integration source and deployment instructions are published at
[DavyDong/RapidOCR-Service](https://github.com/DavyDong/RapidOCR-Service).
The web footer and API documentation link to this repository. Operators deploying
a modified version must provide the corresponding source for their running
version, including their modifications, to their service users as required by
the AGPL. Do not label the complete runtime as solely Apache-2.0 or promise
unrestricted closed-source use.
If the intended deployment cannot meet AGPL requirements, obtain the appropriate
Artifex commercial license or replace the PDF implementation and validate it.

Authoritative references:

- [PyMuPDF license and copyright](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)
- [Artifex licensing guidance](https://artifex.com/licensing)
- [GNU AGPLv3 full text](https://www.gnu.org/licenses/agpl-3.0.html)

## Models and samples

The bundled/default ONNX models have their own provenance and redistribution
notices in [python/MODEL_LICENSES.md](python/MODEL_LICENSES.md). Preserve those
notices when distributing model files. Models are downloaded into `models/`
during warm-up, excluded from Git, and included in the CF upload after warm-up.

`deployment/sample.jpg` is an unchanged copy of the upstream fixture
`python/tests/test_files/ch_en_num.jpg` at the base revision above. Its SHA-256 is
`b94c1bf68af9ceb3c550b86931d7b48d4181c26c9f5ace2492e64042f36a02ca`.
`deployment/sample.pdf` contains synthetic demo invoice text and that same image;
it is test data, not a real invoice. Asset attribution does not transfer ownership
of any third-party names or marks visible in the example image.

This list highlights the integration's main components. It is not an exhaustive
license inventory for all transitive dependencies or all upstream platform
subdirectories. Preserve the license files supplied with packages and review the
specific artifacts included in each release.
