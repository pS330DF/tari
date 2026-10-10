"""Benchmark: the engine's WebSocket stream under realistic and overload send rates.

Starts the real engine (uvicorn, loopback) in-process, streams synthetic frames
at a fixed rate with a configurable number of frames in flight, and measures
round-trip latency (p50/p95/p99), throughput, and how many frames the bounded
scheduler drops instead of queueing. Results: tests/performance/results/stream.json
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import uvicorn
import websockets

from tari_engine.app import create_app
from tari_engine.config import EngineConfig
from tari_schema import ClientSourceInfo, StartSessionMessage, decode_frame_packet, encode_frame_packet
from tari_synth import SyntheticRenderer, angle_hold, build_packet

OUT = Path(__file__).resolve().parent / "results" / "stream.json"
TOKEN = "bench"


def start_engine(data_dir: Path) -> tuple[uvicorn.Server, int]:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    app = create_app(EngineConfig(token=TOKEN, data_dir=data_dir, persistence=True))
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, ws_max_size=64 * 1024 * 1024, ws_per_message_deflate=False))
    threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True).start()
    while not server.started:
        time.sleep(0.02)
    return server, port


def restamp(packet: bytes, frame_id: int, ts: float) -> bytes:
    header, payload = decode_frame_packet(packet)
    h = header.model_copy(update={"frame_id": frame_id, "acquired_ts_ms": ts, "sent_ts_ms": ts, "session_id": "bench"})
    return encode_frame_packet(h, {r.name: bytes(payload[r.byte_offset:r.byte_offset + r.byte_length]) for r in header.regions})


async def stream(port: int, packets: list[bytes], fps: float, max_in_flight: int, seconds: float) -> dict:
    uri = f"ws://127.0.0.1:{port}/v1/stream?token={TOKEN}"
    async with websockets.connect(uri, max_size=None, compression=None) as ws:
        await ws.recv()  # hello
        await ws.send(StartSessionMessage(session_id="bench", source=ClientSourceInfo(
            source_id="synthetic:0", source_kind="synthetic", label="TARI Training Lab")).model_dump_json())
        while json.loads(await ws.recv())["type"] != "session_started":
            pass
        sent: dict[int, float] = {}
        rtt: list[float] = []
        counts = {"sent": 0, "results": 0, "dropped": 0, "skipped_client": 0}
        done = asyncio.Event()

        async def reader():
            while not done.is_set():
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=0.5))
                except asyncio.TimeoutError:
                    continue
                if msg["type"] == "frame_result":
                    fid = msg["perception"]["frame_id"]
                    if fid in sent:
                        rtt.append((time.perf_counter() - sent.pop(fid)) * 1000)
                    counts["results"] += 1
                elif msg["type"] == "frame_dropped":
                    sent.pop(msg.get("frame_id"), None)
                    counts["dropped"] += 1

        task = asyncio.create_task(reader())
        interval = 1.0 / fps
        t_end = time.perf_counter() + seconds
        i = 0
        next_t = time.perf_counter()
        while time.perf_counter() < t_end:
            now = time.perf_counter()
            if now < next_t:
                await asyncio.sleep(next_t - now)
            next_t += interval
            if len(sent) >= max_in_flight:
                counts["skipped_client"] += 1
                continue
            pkt = restamp(packets[i % len(packets)], i, time.time() * 1000)
            sent[i] = time.perf_counter()
            await ws.send(pkt)
            counts["sent"] += 1
            i += 1
        await asyncio.sleep(0.5)
        done.set()
        await task
        a = np.asarray(rtt) if rtt else np.asarray([np.nan])
        return {
            "target_fps": fps, "max_in_flight": max_in_flight, "seconds": seconds, **counts,
            "analyzed_fps": round(counts["results"] / seconds, 1),
            "rtt_ms": {"p50": round(float(np.nanpercentile(a, 50)), 2), "p95": round(float(np.nanpercentile(a, 95)), 2),
                       "p99": round(float(np.nanpercentile(a, 99)), 2), "max": round(float(np.nanmax(a)), 2)},
        }


def main() -> None:
    r = SyntheticRenderer(1920, 1080)
    scen = angle_hold(n=8, entry=(1.0, 1.2), seed=5)
    packets = [build_packet(r.render(s)[0], i, 0.0) for i, s in enumerate(scen.specs[:120])]
    with TemporaryDirectory() as tmp:
        server, port = start_engine(Path(tmp))
        runs = []
        # Realistic: 30 fps, 1 in flight (the desktop default). Overload: up to 400 fps / 64 in flight,
        # far beyond what the engine can analyze, to show frames are dropped instead of queued.
        for fps, inflight in ((30, 1), (60, 1), (60, 2), (120, 8), (400, 64)):
            runs.append(asyncio.run(stream(port, packets, fps, inflight, 6.0)))
        server.should_exit = True
    result = {"note": "Loopback WebSocket, 1920x1080 synthetic frames (540p + 384 crop packets, ~2.6 MB each).", "runs": runs}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    for run in runs:
        print(f"send {run['target_fps']:>3} fps, in-flight {run['max_in_flight']}: analyzed {run['analyzed_fps']:5.1f} fps, "
              f"rtt p50 {run['rtt_ms']['p50']:6.2f} p95 {run['rtt_ms']['p95']:6.2f} p99 {run['rtt_ms']['p99']:6.2f} ms, "
              f"engine dropped {run['dropped']}, client skipped {run['skipped_client']}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
