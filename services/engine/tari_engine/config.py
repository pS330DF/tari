from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def default_data_dir() -> Path:
    env = os.environ.get("TARI_DATA_DIR")
    if env:
        return Path(env)
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "TARI"
    return Path.home() / ".tari"


@dataclass
class EngineConfig:
    token: str
    host: str = "127.0.0.1"
    port: int = 0
    data_dir: Path = field(default_factory=default_data_dir)
    max_frame_age_ms: float = 250.0
    slot_capacity: int = 1
    telemetry_interval_s: float = 1.0
    persist_snapshot_every_s: float = 5.0
    persistence: bool = True
    allowed_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173", "null", "file://")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "tari.db"
