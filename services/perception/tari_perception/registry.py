"""Model registry: versioned, checksummed ONNX models under ``models/``.

A model is only loadable when its file exists, its SHA-256 matches the
manifest, its output format is one this engine understands, and the
registry/engine versions are compatible. Anything else is reported with a
reason and the model is not used.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REGISTRY_VERSION = 1
SUPPORTED_OUTPUT_FORMATS = {"xyxy_score_class_v1"}
ENGINE_VERSION = (0, 1, 0)


def _parse_version(v: str) -> tuple[int, int, int]:
    parts = [int(p) for p in v.split(".")[:3]]
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2]


@dataclass
class ModelEntry:
    name: str
    version: str
    task: str
    file: Path
    sha256: str
    input_width: int
    input_height: int
    output_format: str
    min_engine: str
    classes: list[str] = field(default_factory=list)
    status: str = "unknown"
    reason: str | None = None

    @property
    def ready(self) -> bool:
        return self.status == "ready"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_registry(models_dir: Path) -> tuple[list[ModelEntry], list[str]]:
    """Return (entries with status, registry-level problems)."""
    manifest = models_dir / "registry.json"
    if not manifest.is_file():
        return [], [f"no registry at {manifest}"]
    try:
        data: dict[str, Any] = json.loads(manifest.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return [], [f"unreadable registry: {exc}"]
    if data.get("registry_version") != REGISTRY_VERSION:
        return [], [f"registry_version {data.get('registry_version')!r} unsupported (expected {REGISTRY_VERSION})"]
    entries: list[ModelEntry] = []
    for raw in data.get("models", []):
        try:
            entry = ModelEntry(
                name=str(raw["name"]), version=str(raw["version"]), task=str(raw["task"]),
                file=models_dir / str(raw["file"]), sha256=str(raw["sha256"]).lower(),
                input_width=int(raw["input"]["width"]), input_height=int(raw["input"]["height"]),
                output_format=str(raw["output_format"]), min_engine=str(raw.get("min_engine", "0.0.0")),
                classes=list(raw.get("classes", [])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            entries.append(ModelEntry(str(raw.get("name", "?")), str(raw.get("version", "?")), "?", Path("?"), "",
                                      0, 0, "?", "0", status="invalid_manifest", reason=str(exc)))
            continue
        entries.append(_verify(entry))
    return entries, []


def _verify(entry: ModelEntry) -> ModelEntry:
    if _parse_version(entry.min_engine) > ENGINE_VERSION:
        entry.status, entry.reason = "incompatible_version", f"requires engine >= {entry.min_engine}"
    elif entry.output_format not in SUPPORTED_OUTPUT_FORMATS:
        entry.status, entry.reason = "unsupported_format", f"output_format {entry.output_format!r}"
    elif not entry.file.is_file():
        entry.status, entry.reason = "missing_file", str(entry.file.name)
    else:
        digest = file_sha256(entry.file)
        if digest != entry.sha256:
            entry.status, entry.reason = "checksum_mismatch", f"expected {entry.sha256[:12]}…, got {digest[:12]}…"
        else:
            entry.status = "ready"
    return entry
