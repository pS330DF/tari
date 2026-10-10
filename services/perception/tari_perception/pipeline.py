"""Perception pipeline: runs each analyzer with error isolation and timing.

A failing module reports ``failed`` with the error; its outputs stay empty.
The gate callback lets the session restrict analysis (e.g. unverified source)
after the environment check, so unapproved sources are not analyzed further.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

from tari_schema import (
    EnvironmentObservation, ModuleStatus, PerceptionResult, PerceptionSettings, TargetDetection,
)

from .color import HsvRange
from .crosshair import CrosshairAnalyzer
from .egomotion import EgoMotionEstimator
from .fiducial import FiducialDetector
from .frames import FrameView
from .geometry import Projection
from .hud import SevenSegmentHudParser
from .kb import load_environment_profile
from .targets import ColorTargetDetector

log = logging.getLogger("tari.perception")


class TargetBackend(Protocol):
    name: str
    backend: str

    def detect(self, frame: FrameView, occluders: list[tuple[float, float, float, float]] | None = None,
               overlaps: Callable[[float, float, float], bool] | None = None) -> list[TargetDetection]: ...


GateFn = Callable[[EnvironmentObservation], bool]


def target_ranges(profile: dict[str, Any], color: str) -> list[HsvRange]:
    return [tuple(r) for r in profile["targets"]["hsv_ranges_opencv"][color]]  # type: ignore[misc]


class PerceptionPipeline:
    def __init__(self, settings: PerceptionSettings | None = None, profile: dict[str, Any] | None = None,
                 target_backend: TargetBackend | None = None):
        self.profile = profile or load_environment_profile()
        self.settings = settings or PerceptionSettings()
        self.environment = FiducialDetector(self.profile)
        self.hud = SevenSegmentHudParser(self.profile)
        self.crosshair = CrosshairAnalyzer(self.settings.crosshair_color)
        self.color_targets = ColorTargetDetector(target_ranges(self.profile, self.settings.target_color))
        self.targets: TargetBackend = target_backend or self.color_targets
        self.ego = EgoMotionEstimator()

    def configure(self, settings: PerceptionSettings) -> None:
        self.settings = settings
        self.crosshair.configure(settings.crosshair_color)
        self.color_targets.configure(target_ranges(self.profile, settings.target_color))

    def reset_temporal(self) -> None:
        self.ego.reset()
        self.environment.reset()

    def module_inventory(self) -> list[ModuleStatus]:
        return [
            ModuleStatus(name="environment", state="ok", backend="aruco"),
            ModuleStatus(name="hud", state="ok" if self.settings.hud_profile != "none" else "unavailable",
                         backend=f"seven_segment:{self.hud.profile_id}"),
            ModuleStatus(name="crosshair", state="ok", backend="color_arms"),
            ModuleStatus(name="targets", state="ok", backend=self.targets.backend),
            ModuleStatus(name="ego_motion", state="ok", backend="phase_correlation"),
            ModuleStatus(name="agent", state="unavailable", detail="agent/ability recognizer not implemented"),
            ModuleStatus(name="minimap", state="unavailable", detail="map/minimap analyzer not implemented"),
        ]

    def process(self, frame: FrameView, received_ts_ms: float, gate: GateFn | None = None) -> PerceptionResult:
        started = time.time() * 1000.0
        modules: list[ModuleStatus] = []
        projection = Projection(frame.width, frame.height, self.settings.hfov_deg)

        env = self._run(modules, "environment", "aruco", lambda: self.environment.detect(frame))
        allowed = gate(env) if (gate is not None and env is not None) else gate is None
        crosshair = hud = ego = None
        targets: list[TargetDetection] = []
        if allowed:
            if self.settings.hud_profile == "none":
                modules.append(ModuleStatus(name="hud", state="skipped", detail="HUD profile disabled"))
            elif env is None or env.kind != "training_lab":
                modules.append(ModuleStatus(name="hud", state="unavailable", detail="no HUD anchor (fiducial) in frame"))
            else:
                hud = self._run(modules, "hud", f"seven_segment:{self.hud.profile_id}", lambda: self.hud.parse(frame, env))
                if hud is not None and modules[-1].state == "ok" and any(r.value is None for r in hud.readouts):
                    modules[-1] = modules[-1].model_copy(update={"state": "degraded", "detail": "unreadable readout"})
            crosshair = self._run(modules, "crosshair", "color_arms", lambda: self.crosshair.analyze(frame))
            if crosshair is not None and crosshair.method == "assumed_center":
                modules[-1] = modules[-1].model_copy(update={"state": "degraded", "detail": "crosshair not found; center assumed"})
            zone = self.crosshair.occluder_zone() if crosshair is not None and crosshair.method == "detected" else None
            found = self._run(modules, "targets", self.targets.backend,
                              lambda: self.targets.detect(frame, [zone] if zone else None,
                                                          self.crosshair.overlaps if zone else None))
            targets = found or []
            # Mask screen-fixed overlays (HUD, crosshair) and moving targets: in low-texture
            # scenes a strafing target would otherwise dominate the global motion estimate.
            masked = [z for z in (zone, self.environment.hud_zone(env, frame.width, frame.height) if env else None) if z]
            for t in targets:
                pad_x, pad_y = 0.25 * t.bbox.w, 0.1 * t.bbox.h
                masked.append(((t.bbox.x - pad_x) * frame.width, (t.bbox.y - pad_y) * frame.height,
                               (t.bbox.x + t.bbox.w + pad_x) * frame.width, (t.bbox.y + t.bbox.h + pad_y) * frame.height))
            ego = self._run(modules, "ego_motion", "phase_correlation",
                            lambda: self.ego.estimate(frame, projection, masked))
        else:
            reason = "analysis restricted: source not verified as Training Lab"
            for name in ("hud", "crosshair", "targets", "ego_motion"):
                modules.append(ModuleStatus(name=name, state="skipped", detail=reason))
            self.ego.reset()

        return PerceptionResult(
            session_id=frame.header.session_id,
            frame_id=frame.header.frame_id,
            acquired_ts_ms=frame.header.acquired_ts_ms,
            engine_received_ts_ms=received_ts_ms,
            processing_started_ts_ms=started,
            processed_ts_ms=time.time() * 1000.0,
            source_width=frame.width,
            source_height=frame.height,
            simulated=frame.header.simulated,
            crosshair=crosshair,
            targets=targets,
            ego_motion=ego,
            hud=hud,
            environment=env,
            modules=modules,
        )

    @staticmethod
    def _run(modules: list[ModuleStatus], name: str, backend: str, fn: Callable[[], Any]) -> Any:
        t0 = time.perf_counter()
        try:
            value = fn()
        except Exception as exc:  # noqa: BLE001 - isolate module failures
            log.warning("perception module failed", extra={"perception_module": name, "error": repr(exc)})
            modules.append(ModuleStatus(name=name, state="failed", backend=backend,
                                        duration_ms=round((time.perf_counter() - t0) * 1000, 3), detail=repr(exc)[:300]))
            return None
        modules.append(ModuleStatus(name=name, state="ok", backend=backend,
                                    duration_ms=round((time.perf_counter() - t0) * 1000, 3)))
        return value
