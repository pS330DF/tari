"""Per-connection stream session: receive frames, schedule, analyze, coach, reply.

Concurrency model
- receiver task: reads WebSocket messages; frames go into a 1-slot
  latest-frame-wins buffer, control messages are handled inline.
- processor task: takes the newest frame, drops it if stale/out of order,
  otherwise runs perception -> state -> coaching in a single worker thread
  (OpenCV/numpy release the GIL), preserving temporal order.
- sender task: the only task that writes to the socket.
- telemetry task: periodic performance snapshots.
Control messages (start/update/end) and frame processing share one asyncio
lock, so settings are applied between frames, never mid-frame.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from tari_coaching import LIVE_DOMAINS, PLANNED_DOMAINS, CoachingOrchestrator
from tari_perception import FrameView, PerceptionPipeline
from tari_schema import (
    ClientMessage, EngineCapabilities, FrameDroppedMessage, FramePacketError, FrameResultMessage, HelloMessage,
    NoticeMessage, PongMessage, SessionEndedMessage, SessionStartedMessage, SessionSummary, StartSessionMessage,
    TelemetryMessage, decode_frame_packet, is_compatible,
)
from tari_state import IntegrationPolicy, TemporalStateManager

from .scheduler import FrameItem, LatestFrameSlot, drop_reason, frame_age_ms
from .telemetry import Telemetry, now_ms

if TYPE_CHECKING:
    from .app import EngineContext

log = logging.getLogger("tari.session")
_client_adapter: TypeAdapter = TypeAdapter(ClientMessage)
OUTBOX_LIMIT = 256


@dataclass
class ActiveSession:
    session_id: str
    started_ts: float
    start: StartSessionMessage
    pipeline: PerceptionPipeline
    state: TemporalStateManager
    coach: CoachingOrchestrator
    frames_processed: int = 0
    frames_dropped: int = 0
    exposures: int = 0
    acquisitions: int = 0
    simulated: bool = False
    env_counts: dict[str, int] = field(default_factory=dict)
    notices_sent: set[str] = field(default_factory=set)
    last_processed_ts: float | None = None


class StreamSession:
    def __init__(self, ws: WebSocket, ctx: "EngineContext"):
        self.ws = ws
        self.ctx = ctx
        self.cfg = ctx.config
        self.slot = LatestFrameSlot(self.cfg.slot_capacity)
        self.outbox: asyncio.Queue[str] = asyncio.Queue(maxsize=OUTBOX_LIMIT)
        self.telemetry = Telemetry(window_s=10.0, source="engine", sampler=ctx.sampler)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tari-frame")
        self.active: ActiveSession | None = None
        self._lock = asyncio.Lock()
        self._last_persist = 0.0
        self._closed = False

    # -- lifecycle ---------------------------------------------------------------
    async def run(self) -> None:
        await self._send(HelloMessage(engine_version=self.ctx.version, capabilities=self.capabilities()))
        tasks = [
            asyncio.create_task(self._receiver(), name="receiver"),
            asyncio.create_task(self._processor(), name="processor"),
            asyncio.create_task(self._sender(), name="sender"),
            asyncio.create_task(self._telemetry_loop(), name="telemetry"),
        ]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                if t.exception() and not isinstance(t.exception(), WebSocketDisconnect):
                    log.error("session task failed", extra={"task": t.get_name(), "error": repr(t.exception())})
        finally:
            self._closed = True
            for t in tasks:
                t.cancel()
            for t in tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t
            if self.active is not None:
                self._finish_session("client_disconnected", send=False)
            self.executor.shutdown(wait=False, cancel_futures=True)

    def capabilities(self) -> EngineCapabilities:
        probe = PerceptionPipeline()
        return EngineCapabilities(
            perception_modules=probe.module_inventory(),
            onnx_providers_available=self.ctx.onnx_providers,
            accelerator="none (no neural model loaded; OpenCV CPU pipeline active)",
            coaching_domains_live=LIVE_DOMAINS,  # type: ignore[arg-type]
            coaching_domains_planned=PLANNED_DOMAINS,  # type: ignore[arg-type]
            hud_profiles=["training_lab_v1"],
            riot_integration="disabled_pending_authorization",
        )

    # -- outbound ------------------------------------------------------------------
    async def _send(self, msg) -> None:  # noqa: ANN001 - any engine message model
        data = msg.model_dump_json()
        try:
            self.outbox.put_nowait(data)
        except asyncio.QueueFull:
            self.telemetry.count("outbox_dropped")
            if msg.type != "frame_result":
                await self.outbox.put(data)

    async def _sender(self) -> None:
        while True:
            data = await self.outbox.get()
            await self.ws.send_text(data)

    # -- inbound ---------------------------------------------------------------------
    async def _receiver(self) -> None:
        while True:
            message = await self.ws.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))
            if message.get("bytes") is not None:
                await self._on_frame(message["bytes"])
            elif message.get("text") is not None:
                await self._on_control(message["text"])

    async def _on_frame(self, data: bytes) -> None:
        received = now_ms()
        self.telemetry.count("frames_received")
        self.telemetry.mark("frames_received", received)
        try:
            header, payload = decode_frame_packet(data)
        except FramePacketError as exc:
            self.telemetry.count("dropped_invalid")
            await self._send(FrameDroppedMessage(frame_id=None, reason="invalid", detail=f"{exc.code}: {exc.message}"[:300]))
            return
        if self.active is None:
            self.telemetry.count("dropped_no_session")
            await self._send(FrameDroppedMessage(frame_id=header.frame_id, reason="no_session",
                                                 detail="send start_session before frames"))
            return
        self.telemetry.record("transport_ms", received - header.sent_ts_ms)
        dropped = self.slot.put(FrameItem(header, payload, received, len(data)))
        if dropped is not None:
            self.telemetry.count("dropped_superseded")
            if self.active:
                self.active.frames_dropped += 1
            await self._send(FrameDroppedMessage(frame_id=dropped.header.frame_id, reason="superseded",
                                                 age_ms=round(frame_age_ms(dropped, received), 1)))

    async def _on_control(self, text: str) -> None:
        try:
            msg = _client_adapter.validate_json(text)
        except ValidationError as exc:
            await self._send(NoticeMessage(level="error", code="bad_control_message",
                                           message=str(exc.errors(include_url=False))[:300]))
            return
        if not is_compatible(msg.schema_version):
            await self._send(NoticeMessage(level="error", code="schema_incompatible", priority="P0",
                                           message=f"client schema {msg.schema_version} is not compatible"))
            return
        if msg.type == "start_session":
            async with self._lock:
                await self._start(msg)
        elif msg.type == "update_settings":
            async with self._lock:
                if self.active is not None:
                    a = self.active
                    a.start = a.start.model_copy(update={
                        "coaching": msg.coaching or a.start.coaching,
                        "perception": msg.perception or a.start.perception,
                    })
                    a.pipeline.configure(a.start.perception)
                    a.state.configure(hfov_deg=a.start.perception.hfov_deg)
                    a.coach.configure(a.start.coaching, a.start.perception.hfov_deg)
        elif msg.type == "end_session":
            async with self._lock:
                self.slot.clear()
                ended = self._finish_session(msg.reason, send=False)
            if ended:
                await self._send(ended)
        elif msg.type == "client_metrics":
            if self.ctx.store is not None:
                self.ctx.store.add_perf_snapshot(self.active.session_id if self.active else None, msg.snapshot)
        elif msg.type == "ping":
            await self._send(PongMessage(client_ts_ms=msg.client_ts_ms, engine_ts_ms=now_ms()))

    # -- session management -----------------------------------------------------------
    async def _start(self, start: StartSessionMessage) -> None:
        if self.active is not None:
            ended = self._finish_session("restarted", send=False)
            if ended:
                await self._send(ended)
        sid = start.session_id or uuid.uuid4().hex[:16]
        policy = IntegrationPolicy()
        self.active = ActiveSession(
            session_id=sid, started_ts=now_ms(), start=start,
            pipeline=PerceptionPipeline(start.perception),
            state=TemporalStateManager(sid, policy, start.source.label, start.perception.hfov_deg),
            coach=CoachingOrchestrator(sid, start.coaching, start.perception.hfov_deg),
        )
        self.slot.clear()
        persistence = "unavailable"
        if self.ctx.store is not None:
            self.ctx.store.start_session(sid, start.player_id, self.active.started_ts, start.source.source_kind,
                                         start.source.label, start.source.source_kind == "synthetic")
            persistence = "sqlite"
        await self._send(SessionStartedMessage(session_id=sid, started_ts_ms=self.active.started_ts,
                                               persistence=persistence))  # type: ignore[arg-type]
        if self.ctx.store is not None and self.ctx.store.recovery and not self.ctx.recovery_reported:
            self.ctx.recovery_reported = True
            await self._send(NoticeMessage(
                level="warning", code="database_recovered", priority="P0",
                message="The local history database was damaged and has been reset. The damaged file was kept at "
                        f"{self.ctx.store.recovery['quarantined_to']}."))

    def _finish_session(self, reason: str, send: bool) -> SessionEndedMessage | None:
        a = self.active
        if a is None:
            return None
        self.active = None
        ended = now_ms()
        summary = SessionSummary(session_id=a.session_id, started_ts_ms=a.started_ts, ended_ts_ms=ended,
                                 frames_processed=a.frames_processed, frames_dropped=a.frames_dropped,
                                 exposures=a.exposures, acquisitions=a.acquisitions, metrics=a.coach.summary())
        env = max(a.env_counts, key=a.env_counts.get) if a.env_counts else "unverified"
        if self.ctx.store is not None:
            self.ctx.store.add_perf_snapshot(a.session_id, self.telemetry.snapshot())
            self.ctx.store.end_session(summary, reason, env, a.simulated)
        log.info("session ended", extra={"session_id": a.session_id, "reason": reason,
                                         "frames": a.frames_processed, "dropped": a.frames_dropped})
        return SessionEndedMessage(session_id=a.session_id, reason=reason, summary=summary)

    # -- processing ---------------------------------------------------------------------
    async def _run_in_worker(self, fn):  # noqa: ANN001, ANN202
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, fn)

    async def _processor(self) -> None:
        while True:
            item = await self.slot.get()
            async with self._lock:
                await self._handle(item)

    async def _handle(self, item: FrameItem) -> None:
        a = self.active
        if a is None:
            return
        start = now_ms()
        reason = drop_reason(item, start, self.cfg.max_frame_age_ms, a.last_processed_ts)
        if reason is not None:
            self.telemetry.count(f"dropped_{reason}")
            a.frames_dropped += 1
            await self._send(FrameDroppedMessage(frame_id=item.header.frame_id, reason=reason,  # type: ignore[arg-type]
                                                 age_ms=round(frame_age_ms(item, start), 1)))
            return
        self.telemetry.gauge("queue_depth", float(self.slot.depth))
        self.telemetry.record("frame_age_at_start_ms", frame_age_ms(item, start))
        self.telemetry.record("queue_wait_ms", start - item.received_ts_ms)
        try:
            result = await self._run_in_worker(lambda: self._process(a, item))
        except Exception as exc:  # noqa: BLE001 - keep the stream alive, report the failure
            log.exception("frame processing failed")
            self.telemetry.count("processing_errors")
            await self._send(NoticeMessage(level="error", code="processing_failed",
                                           message=f"Frame {item.header.frame_id} failed: {exc!r}"[:300]))
            return
        a.last_processed_ts = item.header.acquired_ts_ms
        await self._send(result)
        for notice in a.state.decision.notices if a.state.decision else ():
            if notice not in a.notices_sent:
                a.notices_sent.add(notice)
                await self._send(NoticeMessage(level="warning", code="integration_restricted", message=notice,
                                               priority="P0"))

    def _process(self, a: ActiveSession, item: FrameItem) -> FrameResultMessage:
        t0 = time.perf_counter()
        frame = FrameView.from_packet(item.header, item.payload)
        ts = item.header.acquired_ts_ms
        perception = a.pipeline.process(
            frame, item.received_ts_ms,
            gate=lambda env: a.state.policy.allows_analysis(env, a.state.environment.field(ts, "aruco fiducial")),
        )
        t1 = time.perf_counter()
        state, events, decision = a.state.update(perception)
        t2 = time.perf_counter()
        trails = {tid: list(tr.history) for tid, tr in a.state.tracker.tracks.items()}
        out = a.coach.process(state, events, decision, (frame.width, frame.height), trails, now_ms())
        t3 = time.perf_counter()
        a.frames_processed += 1
        a.simulated = a.simulated or item.header.simulated
        env = state.environment.value if state.environment.status == "observed" else "unverified"
        a.env_counts[env or "unverified"] = a.env_counts.get(env or "unverified", 0) + 1
        a.exposures += sum(1 for e in events if e.type == "target_exposed")
        a.acquisitions += sum(1 for e in events if e.type == "target_acquired")
        timings = {
            "perception_ms": round((t1 - t0) * 1000, 3),
            "state_ms": round((t2 - t1) * 1000, 3),
            "coaching_ms": round((t3 - t2) * 1000, 3),
        }
        msg = FrameResultMessage(perception=perception, state=state, events=events,
                                 recommendations=out.recommendations, overlays=out.overlays, voice=out.voice)
        done = now_ms()
        timings["engine_total_ms"] = round(done - item.received_ts_ms, 3)
        timings["frame_age_at_result_ms"] = round(done - ts, 3)
        msg.timings_ms = timings
        tel = self.telemetry
        tel.record("perception_ms", timings["perception_ms"])
        tel.record("state_ms", timings["state_ms"])
        tel.record("coaching_ms", timings["coaching_ms"])
        tel.record("engine_total_ms", timings["engine_total_ms"])
        tel.record("frame_age_at_result_ms", timings["frame_age_at_result_ms"])
        tel.mark("frames_processed", done)
        tel.count("frames_processed")
        if self.ctx.store is not None:
            self.ctx.store.add_events(events)
            self.ctx.store.add_recommendations(out.recommendations)
        return msg

    async def _telemetry_loop(self) -> None:
        while True:
            await asyncio.sleep(self.cfg.telemetry_interval_s)
            snap = self.telemetry.snapshot()
            if self.ctx.store is not None:
                snap.gauges["persistence_degraded"] = 1.0 if self.ctx.store.degraded else 0.0
            await self._send(TelemetryMessage(snapshot=snap))
            if (self.ctx.store is not None and self.active is not None
                    and time.time() - self._last_persist >= self.cfg.persist_snapshot_every_s):
                self._last_persist = time.time()
                self.ctx.store.add_perf_snapshot(self.active.session_id, snap)
