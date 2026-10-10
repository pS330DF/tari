"""ONNX Runtime adapter with GPU-first execution provider selection.

GPU providers are preferred when present (CUDA, DirectML on Windows, CoreML on
macOS) with CPU as the always-available fallback. Model outputs are validated;
malformed output raises ``InvalidModelOutput`` and yields no detections.
"""

from __future__ import annotations

from typing import Any, Protocol

import cv2
import numpy as np

from tari_schema import Point2, Rect, TargetDetection

from .frames import FrameView
from .registry import ModelEntry

PREFERRED_PROVIDERS = [
    "CUDAExecutionProvider",
    "DmlExecutionProvider",
    "CoreMLExecutionProvider",
    "CPUExecutionProvider",
]
GPU_PROVIDERS = {"CUDAExecutionProvider", "DmlExecutionProvider", "CoreMLExecutionProvider"}


class InvalidModelOutput(RuntimeError):
    pass


def available_providers() -> list[str]:
    try:
        import onnxruntime as ort
    except ImportError:
        return []
    try:
        return list(ort.get_available_providers())
    except Exception:  # noqa: BLE001 - provider probing must never crash the engine
        return []


def select_providers(available: list[str], allow_gpu: bool = True) -> list[str]:
    chosen = [p for p in PREFERRED_PROVIDERS if p in available and (allow_gpu or p not in GPU_PROVIDERS)]
    if "CPUExecutionProvider" not in chosen and "CPUExecutionProvider" in available:
        chosen.append("CPUExecutionProvider")
    return chosen


def accelerator_label(providers: list[str]) -> str:
    for p in providers:
        if p in GPU_PROVIDERS:
            return p
    return providers[0] if providers else "none"


class _Session(Protocol):
    def run(self, output_names: Any, input_feed: dict[str, np.ndarray]) -> list[np.ndarray]: ...
    def get_inputs(self) -> list[Any]: ...


def validate_detections(raw: np.ndarray) -> np.ndarray:
    """Validate ``xyxy_score_class_v1`` output: float array [N, 6], normalized boxes."""
    arr = np.asarray(raw)
    if arr.ndim == 3 and arr.shape[0] == 1:
        arr = arr[0]
    if arr.ndim != 2 or arr.shape[1] != 6:
        raise InvalidModelOutput(f"expected [N,6], got shape {tuple(np.asarray(raw).shape)}")
    if not np.issubdtype(arr.dtype, np.floating):
        raise InvalidModelOutput(f"expected float output, got {arr.dtype}")
    if arr.size and not np.isfinite(arr).all():
        raise InvalidModelOutput("non-finite values in output")
    if arr.size:
        boxes, scores = arr[:, :4], arr[:, 4]
        if (boxes < -0.01).any() or (boxes > 1.01).any():
            raise InvalidModelOutput("box coordinates outside [0,1]")
        if ((boxes[:, 2] <= boxes[:, 0]) | (boxes[:, 3] <= boxes[:, 1])).any():
            raise InvalidModelOutput("degenerate boxes (x2<=x1 or y2<=y1)")
        if (scores < 0).any() or (scores > 1).any():
            raise InvalidModelOutput("scores outside [0,1]")
    return arr


class OnnxTargetDetector:
    name = "targets"

    def __init__(self, entry: ModelEntry, providers: list[str], session: _Session | None = None,
                 score_threshold: float = 0.4):
        if not entry.ready and session is None:
            raise RuntimeError(f"model {entry.name} not ready: {entry.status} ({entry.reason})")
        self.entry = entry
        self.providers = providers
        self.score_threshold = score_threshold
        if session is None:
            import onnxruntime as ort

            session = ort.InferenceSession(str(entry.file), providers=providers)
        self._session = session
        self._input_name = session.get_inputs()[0].name
        self.backend = f"onnx:{entry.name}@{entry.version}"

    def detect(self, frame: FrameView, occluders: list[tuple[float, float, float, float]] | None = None,
               overlaps=None) -> list[TargetDetection]:  # noqa: ANN001
        del occluders, overlaps  # the network sees the raw frame; occluder handling is learned
        rgb = frame.full().rgb()
        resized = cv2.resize(rgb, (self.entry.input_width, self.entry.input_height), interpolation=cv2.INTER_AREA)
        tensor = (resized.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
        outputs = self._session.run(None, {self._input_name: tensor})
        if not outputs:
            raise InvalidModelOutput("model returned no outputs")
        dets = validate_detections(outputs[0])
        out: list[TargetDetection] = []
        for x1, y1, x2, y2, score, _cls in dets:
            if score < self.score_threshold:
                continue
            w, h = float(x2 - x1), float(y2 - y1)
            out.append(TargetDetection(
                bbox=Rect(x=float(x1), y=float(y1), w=w, h=h),
                head=Point2(x=float(x1) + w / 2, y=float(y1) + 0.085 * h),
                head_radius=0.075 * h * frame.height / frame.width,
                head_method="top_ratio",
                confidence=round(float(score), 3),
                area_px=int(w * h * frame.width * frame.height * 0.45),
                backend=self.backend,
            ))
        return out
