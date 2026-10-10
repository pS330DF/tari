"""Scripted, deterministic aim scenarios (simulated) with known ground truth.

An *exposure* is a target peeking out from behind cover while the player holds
an angle, followed by a reaction, a flick (clean / overshoot / undershoot) and
a shot. Entry offsets use the engine convention: x>0 head right of crosshair,
y>0 head above crosshair (i.e. crosshair placed low).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .render import Cover, FrameSpec, SynthTarget


def min_jerk(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 10 * t**3 - 15 * t**4 + 6 * t**5


@dataclass
class ExposurePlan:
    tid: int
    entry: tuple[float, float]
    dist_m: float = 15.0
    reaction_ms: float = 220.0
    flick_ms: float = 180.0
    outcome: str = "clean"  # clean | overshoot | undershoot | miss
    overshoot_deg: float = 1.6
    undershoot_frac: float = 0.65
    shot_delay_ms: float = 70.0
    moving_at_shot: bool = False
    emerge_ms: float = 150.0


@dataclass
class Scenario:
    name: str
    fps: float
    specs: list[FrameSpec]
    plans: list[ExposurePlan]
    windows: list[tuple[float, float]] = field(default_factory=list)  # per-exposure (start, end) ms


def _view_path(plan: ExposurePlan, hold: tuple[float, float], t_rel: float, t_react: float) -> tuple[float, float, bool]:
    """View (yaw, pitch) at time t_rel after the target starts emerging. Returns (yaw, pitch, moving_flag)."""
    tx, ty = hold[0] + plan.entry[0], hold[1] + plan.entry[1]
    dx, dy = tx - hold[0], ty - hold[1]
    mag = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / mag, dy / mag
    t = t_rel - t_react
    if t <= 0 or plan.outcome == "miss":
        return hold[0], hold[1], False
    if plan.outcome == "overshoot":
        ox, oy = tx + ux * plan.overshoot_deg, ty + uy * plan.overshoot_deg
        if t < plan.flick_ms:
            s = min_jerk(t / plan.flick_ms)
            return hold[0] + (ox - hold[0]) * s, hold[1] + (oy - hold[1]) * s, True
        t2 = t - plan.flick_ms - 60.0
        if t2 <= 0:
            return ox, oy, False
        s = min_jerk(t2 / 140.0)
        return ox + (tx - ox) * s, oy + (ty - oy) * s, t2 < 140.0
    if plan.outcome == "undershoot":
        mx, my = hold[0] + dx * plan.undershoot_frac, hold[1] + dy * plan.undershoot_frac
        if t < plan.flick_ms:
            s = min_jerk(t / plan.flick_ms)
            return hold[0] + (mx - hold[0]) * s, hold[1] + (my - hold[1]) * s, True
        t2 = t - plan.flick_ms - 90.0
        if t2 <= 0:
            return mx, my, False
        s = min_jerk(t2 / 150.0)
        return mx + (tx - mx) * s, my + (ty - my) * s, t2 < 150.0
    s = min_jerk(t / plan.flick_ms)
    return hold[0] + dx * s, hold[1] + dy * s, t < plan.flick_ms


def _settle_time(plan: ExposurePlan, t_react: float) -> float:
    if plan.outcome == "overshoot":
        return t_react + plan.flick_ms + 60.0 + 140.0
    if plan.outcome == "undershoot":
        return t_react + plan.flick_ms + 90.0 + 150.0
    return t_react + plan.flick_ms


def build_scenario(name: str, plans: list[ExposurePlan], fps: float = 30.0, start_ms: float = 10_000.0,
                   hold: tuple[float, float] = (0.0, 0.0), gap_ms: float = 600.0, lead_ms: float = 500.0,
                   drill: int = 1, **spec_kwargs) -> Scenario:
    specs: list[FrameSpec] = []
    windows: list[tuple[float, float]] = []
    dt = 1000.0 / fps
    t = start_ms
    ammo = 25
    timer = 90

    def push(**kw):
        nonlocal t
        specs.append(FrameSpec(t_ms=round(t, 3), ammo=ammo, timer=timer, drill=drill, **spec_kwargs, **kw))
        t += dt

    while t < start_ms + lead_ms:
        push(view_yaw=hold[0], view_pitch=hold[1])
    for plan in plans:
        tx, ty = hold[0] + plan.entry[0], hold[1] + plan.entry[1]
        edge = tx + 1.4  # cover's left edge, target emerges leftwards from behind it
        cover = Cover(edge, ty - 20.0, edge + 25.0, ty + 3.0)
        t_react = plan.emerge_ms + plan.reaction_ms
        t_settle = _settle_time(plan, t_react)
        t_shot = t_settle + plan.shot_delay_ms if plan.outcome != "miss" else None
        t_end = (t_shot + 80.0) if t_shot is not None else plan.emerge_ms + 900.0
        t0 = t
        windows.append((t0, t0 + t_end))
        fired = False
        while t < t0 + t_end:
            rel = t - t0
            ex = edge + 2.2 - (edge + 2.2 - tx) * min_jerk(rel / plan.emerge_ms)
            vy, vp, moving_view = _view_path(plan, hold, rel, t_react)
            shots = 0
            if t_shot is not None and not fired and rel >= t_shot:
                ammo -= 1
                fired = True
                shots = 1
            moving = plan.moving_at_shot and t_shot is not None and abs(rel - t_shot) <= 120.0
            push(view_yaw=vy, view_pitch=vp, targets=[SynthTarget(plan.tid, ex, ty, plan.dist_m)], covers=[cover],
                 crosshair_gap=11.0 if moving else 4.0, moving=moving, shots=shots,
                 meta={"tid": plan.tid, "rel_ms": rel, "view_moving": moving_view})
            if ammo <= 5:
                ammo = 25
        # Return to the hold position with no targets visible.
        last_vy, last_vp = specs[-1].view_yaw, specs[-1].view_pitch
        tr0 = t
        while t < tr0 + gap_ms:
            s = min_jerk((t - tr0) / (gap_ms * 0.6))
            push(view_yaw=last_vy + (hold[0] - last_vy) * s, view_pitch=last_vp + (hold[1] - last_vp) * s)
        timer = max(0, timer - 2)
    return Scenario(name, fps, specs, plans, windows)


def angle_hold(n: int = 6, entry: tuple[float, float] = (1.0, 1.4), jitter: float = 0.25, seed: int = 1,
               outcome: str = "clean", fps: float = 30.0, **kw) -> Scenario:
    rng = np.random.default_rng(seed)
    plans = []
    for i in range(n):
        ex = entry[0] + float(rng.uniform(-jitter, jitter))
        ey = entry[1] + float(rng.uniform(-jitter, jitter))
        plans.append(ExposurePlan(tid=i + 1, entry=(ex, ey), dist_m=float(rng.uniform(10, 20)), outcome=outcome,
                                  reaction_ms=float(rng.uniform(190, 260)), **kw))
    return build_scenario(f"angle_hold_{outcome}", plans, fps=fps)


def flicks(n: int = 6, outcome: str = "overshoot", seed: int = 2, fps: float = 30.0) -> Scenario:
    rng = np.random.default_rng(seed)
    plans = []
    for i in range(n):
        ang = float(rng.uniform(-0.6, 0.6))
        mag = float(rng.uniform(6.0, 10.0))
        plans.append(ExposurePlan(tid=i + 1, entry=(mag * np.cos(ang) * (1 if i % 2 else -1), mag * np.sin(ang) * 0.4),
                                  dist_m=float(rng.uniform(10, 18)), outcome=outcome, flick_ms=200.0))
    return build_scenario(f"flicks_{outcome}", plans, fps=fps, drill=2)
