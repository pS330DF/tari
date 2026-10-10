# tari-capture — native Windows.Graphics.Capture service (Rust)

Captures a window or monitor with **Windows.Graphics.Capture** (D3D11 frame pool,
free-threaded), converts each frame into the same FramePacket the desktop sends
(540 px analysis frame + 384 px unscaled center crop, RGBA8), and streams it to
the engine over the loopback WebSocket with one frame in flight. Frames produced
while waiting replace each other (latest-wins), so latency stays bounded.

| Command | Platform | Purpose |
| --- | --- | --- |
| `tari-capture list` | Windows | JSON list of capturable windows (hwnd, title, size) and monitors |
| `tari-capture stream --engine <ws-url> (--window <hwnd> \| --monitor <i>) [--fps 30] [--seconds N]` | Windows | capture and stream; prints JSON stats |
| `tari-capture synthetic --engine <ws-url> [--frames 90]` | any | streams generated frames to validate the wire protocol |

`<ws-url>` is `ws://127.0.0.1:<port>/v1/stream?token=<token>` (e.g. after `pnpm engine`:
`ws://127.0.0.1:8765/v1/stream?token=dev`).

## Status

- `cargo test` (any OS): packet encoding matches the golden fixture shared with the
  Python and TypeScript codecs; downscale/crop/stride tests.
- `cargo check --target x86_64-pc-windows-msvc`: the WGC backend (`src/wgc.rs`) type-checks
  against `windows` 0.62.
- `synthetic` mode was run against the live Python engine (60/60 frames processed,
  4.8 ms p50 round trip); the engine kept coaching `restricted` because the frames
  carry no Training Lab marker.
- **Not yet run on Windows.** Expect to validate device creation, frame pool
  recreation on resize, and the yellow capture border behaviour on real hardware.
- The desktop app does not launch this service yet; it uses Electron's capturer.
  When this path is used, the viewer receives results without frame bitmaps.

## Build

```powershell
cargo build --release
.\target\release\tari-capture.exe list
```
