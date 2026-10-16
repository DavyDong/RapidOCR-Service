"""Run the OCR implementation from this checkout."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from rapidocr import RapidOCR  # noqa: E402


def create_engine():
    engine = RapidOCR(
        params={
            "Global.model_root_dir": str(ROOT / "models"),
            "EngineConfig.onnxruntime.intra_op_num_threads": int(
                os.environ.get("OCR_THREADS", "2")
            ),
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        }
    )
    # Exercise detection, classification and recognition before reporting ready.
    result = engine(ROOT / "deployment" / "sample.jpg")
    if not result.txts:
        raise RuntimeError("OCR model warm-up returned no text")
    return engine


if __name__ == "__main__":
    create_engine()
    print("OCR models downloaded and verified.")
