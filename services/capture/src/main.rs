//! `tari-capture`: native capture service for TARI.
//!
//! ```text
//! tari-capture list
//! tari-capture stream --engine <ws-url> (--window <hwnd> | --monitor <index>) [--fps 30] [--seconds N]
//! tari-capture synthetic --engine <ws-url> [--frames 90]
//! ```
//! `list` and `stream` use Windows.Graphics.Capture and only exist on Windows.
//! `synthetic` streams generated frames on any OS to validate the wire protocol.

use std::collections::HashMap;
use std::time::Instant;

use serde_json::json;
use tari_capture::client::{EngineClient, FrameOutcome};
use tari_capture::{analysis_size, center_rect, crop_bgra_to_rgba, downscale_bgra_to_rgba, encode_frame_packet, epoch_ms, Bgra, PixelRect, RegionData};

fn args() -> (String, HashMap<String, String>) {
    let mut it = std::env::args().skip(1);
    let cmd = it.next().unwrap_or_default();
    let mut map = HashMap::new();
    let rest: Vec<String> = it.collect();
    let mut i = 0;
    while i < rest.len() {
        if let Some(k) = rest[i].strip_prefix("--") {
            let v = rest.get(i + 1).filter(|v| !v.starts_with("--")).cloned().unwrap_or_else(|| "true".into());
            if v != "true" {
                i += 1;
            }
            map.insert(k.to_string(), v);
        }
        i += 1;
    }
    (cmd, map)
}

fn usage() -> ! {
    eprintln!("usage:\n  tari-capture list\n  tari-capture stream --engine <ws-url> (--window <hwnd> | --monitor <index>) [--fps 30] [--seconds N]\n  tari-capture synthetic --engine <ws-url> [--frames 90]");
    std::process::exit(2)
}

/// Build the desktop-equivalent packet (540p analysis frame + 384 px center crop) from a BGRA frame.
pub fn packet_from_bgra(frame: &Bgra<'_>, session: &str, frame_id: u64, source_id: &str, kind: &str, label: &str, acquired: f64) -> Vec<u8> {
    let (aw, ah) = analysis_size(frame.width, frame.height, 540, 1280);
    let full = downscale_bgra_to_rgba(frame, aw, ah);
    let c = center_rect(frame.width, frame.height, 384);
    let center = crop_bgra_to_rgba(frame, c);
    encode_frame_packet(
        session, frame_id, source_id, kind, label, acquired, epoch_ms(), (frame.width, frame.height), kind == "synthetic",
        &[
            RegionData { name: "full", src_rect: PixelRect { x: 0, y: 0, w: frame.width, h: frame.height }, width: aw, height: ah, rgba: &full },
            RegionData { name: "center", src_rect: PixelRect { x: c.x, y: c.y, w: c.w, h: c.h }, width: c.w, height: c.h, rgba: &center },
        ],
    )
    .expect("regions are sized by construction")
}

fn synthetic(opts: &HashMap<String, String>) -> Result<(), tari_capture::client::BoxError> {
    let url = opts.get("engine").cloned().unwrap_or_else(|| usage());
    let frames: u64 = opts.get("frames").and_then(|v| v.parse().ok()).unwrap_or(90);
    let (w, h) = (1920u32, 1080u32);
    let mut client = EngineClient::connect(&url)?;
    let session = client.start_session("synthetic:rust", "synthetic", "tari-capture synthetic")?;
    let mut buf = vec![0u8; (w * h * 4) as usize];
    let (mut results, mut dropped, mut rtts) = (0u64, 0u64, Vec::new());
    let mut modes = std::collections::BTreeSet::new();
    for i in 0..frames {
        // Moving gradient: deterministic content with texture for the engine's motion estimator.
        for y in 0..h {
            for x in 0..w {
                let o = ((y * w + x) * 4) as usize;
                let v = (((x + i as u32 * 7) ^ y) & 0xff) as u8;
                buf[o] = v / 2 + 40;
                buf[o + 1] = v / 2 + 40;
                buf[o + 2] = v / 2 + 40;
                buf[o + 3] = 255;
            }
        }
        let frame = Bgra { data: &buf, width: w, height: h, stride: (w * 4) as usize };
        let t0 = Instant::now();
        client.send_frame(packet_from_bgra(&frame, &session, i + 1, "synthetic:rust", "synthetic", "tari-capture synthetic", epoch_ms()))?;
        match client.wait_outcome(i + 1)? {
            FrameOutcome::Result { coaching_mode, .. } => {
                results += 1;
                modes.insert(coaching_mode);
                rtts.push(t0.elapsed().as_secs_f64() * 1000.0);
            }
            FrameOutcome::Dropped { .. } => dropped += 1,
        }
    }
    let summary = client.end_session()?;
    rtts.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let pct = |q: f64| rtts.get(((rtts.len() as f64 - 1.0) * q).round() as usize).copied();
    println!("{}", json!({
        "ok": true, "session_id": session, "frames": frames, "results": results, "dropped": dropped,
        "coaching_modes": modes, "rtt_ms": { "p50": pct(0.5), "p95": pct(0.95) },
        "engine_frames_processed": summary["frames_processed"],
    }));
    Ok(())
}

#[cfg(windows)]
fn platform(cmd: &str, opts: &HashMap<String, String>) -> Result<(), tari_capture::client::BoxError> {
    use tari_capture::wgc;
    match cmd {
        "list" => {
            println!("{}", serde_json::to_string_pretty(&wgc::list_targets()?)?);
            Ok(())
        }
        "stream" => {
            let url = opts.get("engine").cloned().unwrap_or_else(|| usage());
            let target = if let Some(h) = opts.get("window") {
                wgc::Target::Window(h.parse()?)
            } else if let Some(m) = opts.get("monitor") {
                wgc::Target::Monitor(m.parse()?)
            } else {
                usage()
            };
            let fps: f64 = opts.get("fps").and_then(|v| v.parse().ok()).unwrap_or(30.0);
            let seconds: Option<f64> = opts.get("seconds").and_then(|v| v.parse().ok());
            let stats = wgc::stream(&url, target, fps, seconds, packet_from_bgra)?;
            println!("{}", serde_json::to_string(&stats)?);
            Ok(())
        }
        _ => usage(),
    }
}

#[cfg(not(windows))]
fn platform(cmd: &str, _opts: &HashMap<String, String>) -> Result<(), tari_capture::client::BoxError> {
    match cmd {
        "list" | "stream" => Err("Windows.Graphics.Capture is only available on Windows 10 1903+ / Windows 11".into()),
        _ => usage(),
    }
}

fn main() {
    let (cmd, opts) = args();
    let result = match cmd.as_str() {
        "synthetic" => synthetic(&opts),
        "" | "help" | "--help" => usage(),
        other => platform(other, &opts),
    };
    if let Err(e) = result {
        eprintln!("{}", json!({ "ok": false, "error": e.to_string() }));
        std::process::exit(1);
    }
}
