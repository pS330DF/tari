"""End-to-end: WebSocket stream through the real engine (perception -> state -> coaching -> SQLite)."""

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from helpers import renderer
from tari_engine.app import create_app
from tari_engine.config import EngineConfig
from tari_schema import (
    CoachingSettings, ClientSourceInfo, EndSessionMessage, PingMessage, StartSessionMessage,
    UpdateSettingsMessage, decode_frame_packet, encode_frame_packet,
)
from tari_synth import angle_hold, build_packet

TOKEN = "test-token"


@pytest.fixture()
def client(tmp_path: Path):
    app = create_app(EngineConfig(token=TOKEN, data_dir=tmp_path, telemetry_interval_s=0.2))
    with TestClient(app) as c:
        yield c


def restamp(packet: bytes, acquired: float, frame_id: int | None = None, session: str = "it") -> bytes:
    header, payload = decode_frame_packet(packet)
    upd = {"acquired_ts_ms": acquired, "sent_ts_ms": time.time() * 1000, "session_id": session}
    if frame_id is not None:
        upd["frame_id"] = frame_id
    h = header.model_copy(update=upd)
    chunks = {r.name: bytes(payload[r.byte_offset:r.byte_offset + r.byte_length]) for r in header.regions}
    return encode_frame_packet(h, chunks)


def recv(ws, kinds: set[str], limit: int = 200) -> tuple[dict, list[dict]]:
    others = []
    for _ in range(limit):
        msg = ws.receive_json()
        if msg["type"] in kinds:
            return msg, others
        others.append(msg)
    raise AssertionError(f"no {kinds} within {limit} messages; got {[m['type'] for m in others]}")


def start(ws, **coaching) -> dict:
    ws.send_text(StartSessionMessage(
        session_id="it", source=ClientSourceInfo(source_id="synthetic:0", source_kind="synthetic",
                                                 label="TARI Training Lab"),
        coaching=CoachingSettings(**coaching),
    ).model_dump_json())
    msg, _ = recv(ws, {"session_started"})
    return msg


def test_auth_is_required(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/v1/stream?token=wrong") as ws:
            ws.receive_json()
    assert client.get("/v1/sessions").status_code == 401
    assert client.get("/v1/sessions", headers={"x-tari-token": "nope"}).status_code == 401
    assert client.get("/health").json()["status"] == "ok"


def test_full_session_over_websocket(client):
    scen = angle_hold(n=5, entry=(1.0, 1.5), seed=4)
    r = renderer()
    packets = [build_packet(r.render(spec)[0], i, spec.t_ms) for i, spec in enumerate(scen.specs)]
    t0 = scen.specs[0].t_ms
    with client.websocket_connect(f"/v1/stream?token={TOKEN}") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        caps = hello["capabilities"]
        assert caps["coaching_domains_live"] == ["aim"]
        assert caps["riot_integration"] == "disabled_pending_authorization"
        assert "CPUExecutionProvider" in caps["onnx_providers_available"]

        # Frames before a session are rejected explicitly.
        ws.send_bytes(restamp(packets[0], time.time() * 1000))
        drop, _ = recv(ws, {"frame_dropped"})
        assert drop["reason"] == "no_session"

        started = start(ws)
        assert started["persistence"] == "sqlite"

        base = time.time() * 1000
        results, recs, overlays, events = [], [], [], []
        for i, (pkt, spec) in enumerate(zip(packets, scen.specs)):
            ws.send_bytes(restamp(pkt, base + (spec.t_ms - t0), frame_id=i))
            msg, _ = recv(ws, {"frame_result", "frame_dropped"})
            if msg["type"] == "frame_result":
                results.append(msg)
                recs += msg["recommendations"]
                overlays += msg["overlays"]
                events += msg["events"]
        assert len(results) >= len(packets) - 2
        kinds = [e["type"] for e in events]
        assert kinds.count("target_exposed") == 5 and kinds.count("shot_fired") == 5
        assert any(r["rule_id"] == "aim.placement.low" for r in recs)
        for res in results:
            p = res["perception"]
            assert p["engine_received_ts_ms"] <= p["processing_started_ts_ms"] <= p["processed_ts_ms"]
            for o in res["overlays"]:
                assert o["source_frame_id"] == p["frame_id"] and o["source_ts_ms"] == p["acquired_ts_ms"]
            assert res["timings_ms"]["engine_total_ms"] >= 0
        assert results[-1]["state"]["coaching_mode"] == "live_training"
        assert results[-1]["state"]["agent"]["status"] == "unknown"  # not implemented -> unknown, not guessed

        # Settings update takes effect between frames.
        ws.send_text(UpdateSettingsMessage(coaching=CoachingSettings(language="ko")).model_dump_json())
        ws.send_text(PingMessage(client_ts_ms=1.0).model_dump_json())
        pong, _ = recv(ws, {"pong"})
        assert pong["client_ts_ms"] == 1.0

        # A stale frame (acquired long ago) is dropped, not processed.
        ws.send_bytes(restamp(packets[0], time.time() * 1000 - 5000, frame_id=10_000))
        drop, _ = recv(ws, {"frame_dropped"})
        assert drop["reason"] in ("stale", "out_of_order")

        # Invalid bytes are rejected with a reason.
        ws.send_bytes(b"garbage-bytes-that-are-not-a-frame")
        drop, _ = recv(ws, {"frame_dropped"})
        assert drop["reason"] == "invalid" and "bad_magic" in drop["detail"]

        telemetry, _ = recv(ws, {"telemetry"})
        snap = telemetry["snapshot"]
        assert snap["latencies"]["perception_ms"]["count"] > 0
        assert snap["latencies"]["engine_total_ms"]["p95"] is not None

        ws.send_text(EndSessionMessage(reason="user_stopped").model_dump_json())
        ended, _ = recv(ws, {"session_ended"})
        summary = ended["summary"]
        assert summary["exposures"] == 5 and summary["frames_processed"] >= len(packets) - 2
        metrics = {m["metric"]: m for m in summary["metrics"]}
        assert metrics["vertical_entry_offset_deg"]["value"] == pytest.approx(1.5, abs=0.3)
        assert "crosshair" in metrics["vertical_entry_offset_deg"]["method"]

    app_store = client.app.state.ctx.store
    app_store.flush()
    sessions = client.get("/v1/sessions", headers={"x-tari-token": TOKEN}).json()
    assert sessions[0]["session_id"] == "it" and sessions[0]["exposures"] == 5 and sessions[0]["simulated"] is True
    detail = client.get("/v1/sessions/it", headers={"x-tari-token": TOKEN}).json()
    assert detail["event_counts"]["target_exposed"] == 5 and detail["recommendations"]
    assert detail["end_reason"] == "user_stopped"
    prof = client.get("/v1/profile?include_simulated=true", headers={"x-tari-token": TOKEN}).json()
    assert prof["sessions_total"] == 1
    assert client.get("/v1/profile", headers={"x-tari-token": TOKEN}).json()["sessions_total"] == 0


def test_burst_frames_are_superseded_not_queued(client):
    r = renderer()
    scen = angle_hold(n=1, entry=(1.0, 1.0))
    pkt = build_packet(r.render(scen.specs[0])[0], 0, 0.0)
    with client.websocket_connect(f"/v1/stream?token={TOKEN}") as ws:
        ws.receive_json()
        start(ws)
        now = time.time() * 1000
        for i in range(12):
            ws.send_bytes(restamp(pkt, now + i, frame_id=i))
        seen = {"frame_result": 0, "superseded": 0}
        deadline = time.time() + 10
        while sum(seen.values()) < 12 and time.time() < deadline:
            msg = ws.receive_json()
            if msg["type"] == "frame_result":
                seen["frame_result"] += 1
            elif msg["type"] == "frame_dropped":
                seen["superseded"] += msg["reason"] in ("superseded", "stale", "out_of_order")
        assert seen["frame_result"] + seen["superseded"] == 12
        assert seen["superseded"] > 0  # bounded queue: excess frames dropped, not processed late


def test_disconnect_finalizes_session(client):
    r = renderer()
    scen = angle_hold(n=1, entry=(1.0, 1.0))
    pkt = build_packet(r.render(scen.specs[0])[0], 0, 0.0)
    with client.websocket_connect(f"/v1/stream?token={TOKEN}") as ws:
        ws.receive_json()
        start(ws)
        ws.send_bytes(restamp(pkt, time.time() * 1000, frame_id=1))
        recv(ws, {"frame_result"})
    deadline = time.time() + 5
    while time.time() < deadline:
        client.app.state.ctx.store.flush()
        rows = client.get("/v1/sessions", headers={"x-tari-token": TOKEN}).json()
        if rows and rows[0]["end_reason"]:
            break
        time.sleep(0.05)
    assert rows[0]["end_reason"] == "client_disconnected" and rows[0]["frames_processed"] == 1


def test_valorant_source_is_restricted_with_notice(client):
    r = renderer()
    scen = angle_hold(n=1, entry=(1.0, 1.0))
    spec = scen.specs[3]
    spec.draw_fiducial = False
    pkt = build_packet(r.render(spec)[0], 0, 0.0)
    with client.websocket_connect(f"/v1/stream?token={TOKEN}") as ws:
        ws.receive_json()
        ws.send_text(StartSessionMessage(session_id="v", source=ClientSourceInfo(
            source_id="window:1", source_kind="window", label="VALORANT  ")).model_dump_json())
        recv(ws, {"session_started"})
        ws.send_bytes(restamp(pkt, time.time() * 1000, frame_id=1, session="v"))
        res, _ = recv(ws, {"frame_result"})
        notice, _ = recv(ws, {"notice"})
    assert res["state"]["coaching_mode"] == "restricted"
    assert res["perception"]["targets"] == [] and res["overlays"] == [] and res["recommendations"] == []
    assert "Riot authorization" in notice["message"]


def test_bad_control_message_reports_error(client):
    with client.websocket_connect(f"/v1/stream?token={TOKEN}") as ws:
        ws.receive_json()
        ws.send_text(json.dumps({"type": "start_session", "schema_version": "1.0.0"}))
        notice, _ = recv(ws, {"notice"})
        assert notice["code"] == "bad_control_message"
        ws.send_text(StartSessionMessage(schema_version="2.0.0", source=ClientSourceInfo(
            source_id="x", source_kind="screen")).model_dump_json())
        notice, _ = recv(ws, {"notice"})
        assert notice["code"] == "schema_incompatible"


def test_corrupt_database_reported_to_client(tmp_path: Path):
    (tmp_path / "tari.db").write_bytes(b"\x00garbage" * 64)
    app = create_app(EngineConfig(token=TOKEN, data_dir=tmp_path))
    with TestClient(app) as c, c.websocket_connect(f"/v1/stream?token={TOKEN}") as ws:
        ws.receive_json()
        start(ws)
        notice, _ = recv(ws, {"notice"})
        assert notice["code"] == "database_recovered" and notice["priority"] == "P0"
        assert ".corrupt-" in notice["message"]


def test_engine_runs_without_persistence(tmp_path: Path):
    app = create_app(EngineConfig(token=TOKEN, data_dir=tmp_path, persistence=False))
    with TestClient(app) as c, c.websocket_connect(f"/v1/stream?token={TOKEN}") as ws:
        ws.receive_json()
        assert start(ws)["persistence"] == "unavailable"
        assert c.get("/v1/sessions", headers={"x-tari-token": TOKEN}).status_code == 503
