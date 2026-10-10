"""Locate versioned knowledge-base files (environment profiles, agent data)."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()


def _search_dirs() -> list[Path]:
    dirs: list[Path] = []
    env = os.environ.get("TARI_KB_DIR")
    if env:
        dirs.append(Path(env))
    # repo layout: services/perception/tari_perception -> packages/knowledge-base
    for parent in _HERE.parents:
        candidate = parent / "packages" / "knowledge-base"
        if candidate.is_dir():
            dirs.append(candidate)
            break
    return dirs


@lru_cache(maxsize=8)
def load_environment_profile(name: str = "training-lab-v1") -> dict[str, Any]:
    for base in _search_dirs():
        path = base / "environments" / f"{name}.json"
        if path.is_file():
            return json.loads(path.read_text())
    raise FileNotFoundError(f"environment profile '{name}' not found (set TARI_KB_DIR)")
