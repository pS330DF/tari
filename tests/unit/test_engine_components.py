import asyncio
import re
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from tari_engine.scheduler import FrameItem, LatestFrameSlot, drop_reason
from tari_engine.store import SessionStore
from tari_engine.telemetry import Telemetry, latency_stats
from tari_perception.onnx_backend import (
    InvalidModelOutput, OnnxTargetDetector, accelerator_label, select_providers, validate_detections,
)
from tari_perception.registry import ModelEntry, load_registry
from tari_schema import (
    Evidence, FramePacketHeader, FrameRegion, PixelRect, SessionSummary, TargetExposedEvent, Point2,
)


def item(frame_id: int, acquired: float) -> FrameItem:
    header = FramePacketHeader(
        session_id="s", frame_id=frame_id, source_id="x", source_kind="screen", acquired_ts_ms=acquired,
        sent_ts_ms=acquired, source_width=4, source_height=4,
        regions=[FrameRegion(name="full", src_rect=PixelRect(x=0, y=0, w=4, h=4), width=4, height=4,
                             byte_offset=0, byte_length=64)],
    )
    return FrameItem(header, memoryview(bytes(64)), acquired, 64)


# -- scheduler -----------------------------------------------------------------

def test_latest_frame_slot_drops_oldest_when_full():
    async def go():
        slot = LatestFrameSlot(1)
        assert slot.put(item(1, 0)) is None
        dropped = slot.put(item(2, 10))
        assert dropped.header.frame_id == 1
        got = await slot.get()
        assert got.header.frame_id == 2 and slot.depth == 0
    asyncio.run(go())


def test_slot_get_waits_for_frames():
    async def go():
        slot = LatestFrameSlot(2)
        task = asyncio.create_task(slot.get())
        await asyncio.sleep(0.01)
        assert not task.done()
        slot.put(item(5, 0))
        assert (await asyncio.wait_for(task, 1)).header.frame_id == 5
    asyncio.run(go())


def test_drop_reason_stale_and_out_of_order():
    assert drop_reason(item(1, 1000), 1100, 250, None) is None
    assert drop_reason(item(1, 1000), 1300, 250, None) == "stale"
    assert drop_reason(item(1, 1000), 1010, 250, 1000) == "out_of_order"
    assert drop_reason(item(1, 1000), 1010, 250, 1200) == "out_of_order"


# -- telemetry ------------------------------------------------------------------

def test_latency_percentiles():
    s = latency_stats(list(range(1, 101)))
    assert s.count == 100 and s.p50 == pytest.approx(50.5) and s.p95 == pytest.approx(95.05) and s.max == 100
    assert latency_stats([]).p50 is None


def test_telemetry_window_and_rates():
    t = Telemetry(window_s=1.0)
    for i in range(11):
        t.mark("frames", 1000.0 + i * 100)
        t.record("lat", float(i), 1000.0 + i * 100)
    snap = t.snapshot(now=2000.0)
    assert snap.rates["frames"] == pytest.approx(10.0)
    assert snap.latencies["lat"].count == 11
    snap2 = t.snapshot(now=3500.0)
    assert snap2.latencies["lat"].count == 0


def test_resource_sampler_reports_gpu_unavailable_reason():
    from tari_engine.telemetry import ResourceSampler

    gauges, unavailable = ResourceSampler().sample()
    assert gauges["engine_rss_mb"] > 0
    assert "gpu_utilization_percent" in gauges or "gpu_utilization_percent" in unavailable


# -- store ----------------------------------------------------------------------

def summary(sid: str, value: float, samples: int = 6, t: float = 0.0) -> SessionSummary:
    return SessionSummary(session_id=sid, started_ts_ms=t, ended_ts_ms=t + 60_000, frames_processed=100,
                          frames_dropped=3, exposures=samples, acquisitions=samples,
                          metrics=[Evidence(metric="vertical_entry_abs_offset_deg", value=value, unit="deg",
                                            samples=samples, method="test")])


def test_store_roundtrip_and_profile_trend(tmp_path: Path):
    store = SessionStore(tmp_path / "t.db")
    values = [1.6, 1.5, 1.4, 0.9, 0.7, 0.6]
    for i, v in enumerate(values):
        sid = f"s{i}"
        store.start_session(sid, "local", i * 100_000.0, "window", "TARI Training Lab", False)
        store.add_events([TargetExposedEvent(event_id=f"e{i}", session_id=sid, frame_id=1, ts_ms=1.0, confidence=0.8,
                                             track_id=1, head=Point2(x=0.5, y=0.5), entry_error_deg=Point2(x=0, y=v),
                                             head_radius_deg=0.3, view_speed_dps=1.0, view_settled=True)])
        store.end_session(summary(sid, v, t=i * 100_000.0), "user_stopped", "training_lab", False)
    store.flush()
    sessions = store.list_sessions()
    assert len(sessions) == 6 and sessions[0]["session_id"] == "s5" and sessions[0]["exposures"] == 1
    prof = store.profile()
    skill = next(s for s in prof.skills if s.skill == "vertical_entry_abs_offset_deg")
    assert [p.value for p in skill.points] == values
    assert skill.trend == "improving" and "0.73" in skill.trend_detail and "1.50" in skill.trend_detail
    assert prof.validated_sessions == 6
    store.close()


def test_profile_never_invents_trends(tmp_path: Path):
    store = SessionStore(tmp_path / "t.db")
    store.start_session("a", "local", 0.0, "window", "lab", False)
    store.end_session(summary("a", 1.2), "user_stopped", "training_lab", False)
    store.start_session("b", "local", 1.0, "window", "lab", False)
    store.end_session(summary("b", 0.4, samples=2), "user_stopped", "training_lab", False)  # too few samples
    store.flush()
    prof = store.profile()
    skill = next(s for s in prof.skills if s.skill == "vertical_entry_abs_offset_deg")
    assert len(skill.points) == 1 and skill.trend == "insufficient_data"
    acq = next(s for s in prof.skills if s.skill == "acquisition_time_ms")
    assert acq.points == [] and acq.trend == "insufficient_data"
    store.close()


def test_simulated_sessions_excluded_from_profile_by_default(tmp_path: Path):
    store = SessionStore(tmp_path / "t.db")
    store.start_session("sim", "local", 0.0, "synthetic", "synthetic", True)
    store.end_session(summary("sim", 1.0), "done", "training_lab", True)
    store.flush()
    assert store.profile().sessions_total == 0
    assert store.profile(include_simulated=True).sessions_total == 1
    store.close()


def test_corrupt_database_is_quarantined_not_deleted(tmp_path: Path):
    db = tmp_path / "tari.db"
    db.write_bytes(b"this is not a sqlite database" * 100)
    store = SessionStore(db)
    assert store.recovery is not None
    quarantined = Path(store.recovery["quarantined_to"])
    assert quarantined.exists() and quarantined.read_bytes().startswith(b"this is not")
    store.start_session("s", "local", 0.0, "window", "lab", False)
    store.flush()
    assert store.list_sessions()[0]["session_id"] == "s"
    store.close()


# -- model registry / ONNX adapter ---------------------------------------------------

def write_registry(d: Path, models: list[dict], version: int = 1) -> None:
    (d / "registry.json").write_text(json.dumps({"registry_version": version, "models": models}))


def entry(**over) -> dict:
    base = {"name": "det", "version": "1.0.0", "task": "target_detection", "file": "det.onnx", "sha256": "0" * 64,
            "input": {"width": 64, "height": 64}, "output_format": "xyxy_score_class_v1", "min_engine": "0.1.0"}
    base.update(over)
    return base


def test_registry_rejects_missing_mismatched_and_incompatible_models(tmp_path: Path):
    (tmp_path / "det.onnx").write_bytes(b"model-bytes")
    good_sha = hashlib.sha256(b"model-bytes").hexdigest()
    write_registry(tmp_path, [
        entry(sha256=good_sha),
        entry(name="tampered"),
        entry(name="gone", file="missing.onnx", sha256=good_sha),
        entry(name="future", min_engine="9.0.0", sha256=good_sha),
        entry(name="newfmt", output_format="xyxy_score_class_v2", sha256=good_sha),
        {"name": "broken"},
    ])
    entries, problems = load_registry(tmp_path)
    status = {e.name: e.status for e in entries}
    assert problems == []
    assert status == {"det": "ready", "tampered": "checksum_mismatch", "gone": "missing_file",
                      "future": "incompatible_version", "newfmt": "unsupported_format", "broken": "invalid_manifest"}


def test_registry_version_change_is_refused(tmp_path: Path):
    write_registry(tmp_path, [entry()], version=2)
    entries, problems = load_registry(tmp_path)
    assert entries == [] and "unsupported" in problems[0]


def test_provider_selection_prefers_gpu_and_falls_back_to_cpu():
    assert select_providers(["CPUExecutionProvider", "CUDAExecutionProvider"])[0] == "CUDAExecutionProvider"
    assert select_providers(["CPUExecutionProvider", "DmlExecutionProvider"])[0] == "DmlExecutionProvider"
    assert select_providers(["CPUExecutionProvider"]) == ["CPUExecutionProvider"]
    assert select_providers(["CUDAExecutionProvider", "CPUExecutionProvider"], allow_gpu=False) == ["CPUExecutionProvider"]
    assert accelerator_label(["CPUExecutionProvider"]) == "CPUExecutionProvider"
    assert accelerator_label([]) == "none"


@pytest.mark.parametrize("raw,msg", [
    (np.zeros((3, 5), np.float32), "expected [N,6]"),
    (np.array([[0.1, 0.1, 0.2, 0.2, float("nan"), 0]], np.float32), "non-finite"),
    (np.array([[0.1, 0.1, 1.5, 0.2, 0.9, 0]], np.float32), "outside [0,1]"),
    (np.array([[0.3, 0.1, 0.2, 0.2, 0.9, 0]], np.float32), "degenerate"),
    (np.array([[0.1, 0.1, 0.2, 0.2, 1.9, 0]], np.float32), "scores"),
    (np.zeros((2, 6), np.int32), "float"),
])
def test_invalid_model_output_rejected(raw, msg):
    with pytest.raises(InvalidModelOutput, match=re.escape(msg)):
        validate_detections(raw)


def test_onnx_detector_with_invalid_output_yields_failure_not_detections():
    from helpers import renderer
    from tari_perception import FrameView, PerceptionPipeline
    from tari_schema import decode_frame_packet
    from tari_synth import FrameSpec, SynthTarget, build_packet

    class FakeSession:
        def __init__(self, out):
            self.out = out

        def get_inputs(self):
            return [type("I", (), {"name": "images"})()]

        def run(self, names, feed):
            assert feed["images"].shape == (1, 3, 64, 64)
            return [self.out]

    e = ModelEntry("det", "1.0.0", "target_detection", Path("x"), "", 64, 64, "xyxy_score_class_v1", "0.1.0")
    rgba, _ = renderer().render(FrameSpec(t_ms=1, targets=[SynthTarget(1, 5, 0, 12)]))
    header, payload = decode_frame_packet(build_packet(rgba, 0, 1))
    fv = FrameView.from_packet(header, payload)
    good = OnnxTargetDetector(e, ["CPUExecutionProvider"], FakeSession(np.array([[0.4, 0.4, 0.5, 0.7, 0.9, 0]], np.float32)))
    dets = good.detect(fv)
    assert len(dets) == 1 and dets[0].backend == "onnx:det@1.0.0"
    pipe = PerceptionPipeline(target_backend=OnnxTargetDetector(e, ["CPUExecutionProvider"],
                                                                 FakeSession(np.full((1, 6), np.nan, np.float32))))
    res = pipe.process(fv, 1.0)
    mod = {m.name: m for m in res.modules}["targets"]
    assert mod.state == "failed" and "non-finite" in mod.detail and res.targets == []


def test_real_onnxruntime_session_loads_generated_model(tmp_path: Path):
    """End-to-end ONNX Runtime check with a tiny generated model (CPU provider)."""
    onnx = pytest.importorskip("onnx")
    from onnx import TensorProto, helper

    from tari_perception.onnx_backend import available_providers

    # Model ignores the image and emits one fixed, valid detection: [1,6]
    const = helper.make_tensor("det", TensorProto.FLOAT, [1, 6], [0.4, 0.3, 0.5, 0.6, 0.8, 0.0])
    node_c = helper.make_node("Constant", [], ["out"], value=const)
    graph = helper.make_graph([node_c], "g", [helper.make_tensor_value_info("images", TensorProto.FLOAT, [1, 3, 64, 64])],
                              [helper.make_tensor_value_info("out", TensorProto.FLOAT, [1, 6])])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    path = tmp_path / "det.onnx"
    onnx.save(model, path)
    write_registry(tmp_path, [entry(sha256=hashlib.sha256(path.read_bytes()).hexdigest())])
    entries, _ = load_registry(tmp_path)
    assert entries[0].ready
    providers = select_providers(available_providers(), allow_gpu=False)
    det = OnnxTargetDetector(entries[0], providers)
    from helpers import renderer
    from tari_perception import FrameView
    from tari_schema import decode_frame_packet
    from tari_synth import FrameSpec, build_packet

    rgba, _ = renderer().render(FrameSpec(t_ms=1))
    header, payload = decode_frame_packet(build_packet(rgba, 0, 1))
    out = det.detect(FrameView.from_packet(header, payload))
    assert len(out) == 1 and out[0].bbox.x == pytest.approx(0.4)
