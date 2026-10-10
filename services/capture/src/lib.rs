//! TARI native capture service library.
//!
//! Platform-independent parts (packet encoding, pixel conversion, engine
//! client) live here and are unit-tested on every OS. The Windows Graphics
//! Capture backend is in `wgc` (Windows only).

pub mod client;
pub mod image;
pub mod packet;
#[cfg(windows)]
pub mod wgc;

pub use image::{analysis_size, center_rect, crop_bgra_to_rgba, downscale_bgra_to_rgba, Bgra, Rect};
pub use packet::{decode_frame_packet, encode_frame_packet, FramePacketHeader, FrameRegion, PixelRect, RegionData};

/// Wall-clock epoch milliseconds (same clock the engine uses for frame age).
pub fn epoch_ms() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs_f64() * 1000.0)
        .unwrap_or(0.0)
}
