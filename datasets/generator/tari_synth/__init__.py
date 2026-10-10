"""Deterministic synthetic (simulated) Training-Lab-style video with ground truth."""

from .scenarios import ExposurePlan, Scenario, angle_hold, build_scenario, flicks
from .render import Cover, FrameSpec, GroundTruth, SynthTarget, SyntheticRenderer, TargetTruth, build_packet

__all__ = [
    "ExposurePlan", "Scenario", "angle_hold", "build_scenario", "flicks","Cover", "FrameSpec", "GroundTruth", "SynthTarget", "SyntheticRenderer", "TargetTruth", "build_packet"]
