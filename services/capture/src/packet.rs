//! FramePacket wire format (mirror of `tari_schema.frame` / `@tari/shared-types`).
//!
//! ```text
//! offset 0   4 bytes  magic "TFRM"
//! offset 4   u16 LE   packet layout version (1)
//! offset 6   u32 LE   header length N
//! offset 10  N bytes  UTF-8 JSON header
//! offset 10+N         payload: concatenated RGBA8 region buffers
//! ```

use serde::{Deserialize, Serialize};

pub const FRAME_MAGIC: &[u8; 4] = b"TFRM";
pub const FRAME_PACKET_VERSION: u16 = 1;
pub const SCHEMA_VERSION: &str = "1.0.0";
const PREFIX: usize = 10;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct PixelRect {
    pub x: u32,
    pub y: u32,
    pub w: u32,
    pub h: u32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FrameRegion {
    pub name: String,
    pub src_rect: PixelRect,
    pub width: u32,
    pub height: u32,
    pub format: String,
    pub byte_offset: u64,
    pub byte_length: u64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FramePacketHeader {
    pub schema_version: String,
    #[serde(rename = "type")]
    pub kind: String,
    pub session_id: String,
    pub frame_id: u64,
    pub source_id: String,
    pub source_kind: String,
    pub source_label: String,
    pub acquired_ts_ms: f64,
    pub sent_ts_ms: f64,
    pub source_width: u32,
    pub source_height: u32,
    pub regions: Vec<FrameRegion>,
    pub simulated: bool,
}

/// One region to encode: RGBA8 pixels plus where they came from in the source frame.
pub struct RegionData<'a> {
    pub name: &'a str,
    pub src_rect: PixelRect,
    pub width: u32,
    pub height: u32,
    pub rgba: &'a [u8],
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PacketError {
    RegionSize(String),
    Truncated,
    BadMagic,
    UnsupportedVersion(u16),
    BadHeader(String),
}

impl std::fmt::Display for PacketError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

impl std::error::Error for PacketError {}

#[allow(clippy::too_many_arguments)]
pub fn encode_frame_packet(
    session_id: &str,
    frame_id: u64,
    source_id: &str,
    source_kind: &str,
    source_label: &str,
    acquired_ts_ms: f64,
    sent_ts_ms: f64,
    source_size: (u32, u32),
    simulated: bool,
    regions: &[RegionData<'_>],
) -> Result<Vec<u8>, PacketError> {
    let mut offset = 0u64;
    let mut metas = Vec::with_capacity(regions.len());
    for r in regions {
        let expected = r.width as u64 * r.height as u64 * 4;
        if r.rgba.len() as u64 != expected {
            return Err(PacketError::RegionSize(format!("{}: {} bytes, expected {}", r.name, r.rgba.len(), expected)));
        }
        metas.push(FrameRegion {
            name: r.name.to_string(),
            src_rect: r.src_rect,
            width: r.width,
            height: r.height,
            format: "rgba8".to_string(),
            byte_offset: offset,
            byte_length: expected,
        });
        offset += expected;
    }
    let header = FramePacketHeader {
        schema_version: SCHEMA_VERSION.to_string(),
        kind: "frame".to_string(),
        session_id: session_id.to_string(),
        frame_id,
        source_id: source_id.to_string(),
        source_kind: source_kind.to_string(),
        source_label: source_label.to_string(),
        acquired_ts_ms,
        sent_ts_ms,
        source_width: source_size.0,
        source_height: source_size.1,
        regions: metas,
        simulated,
    };
    let json = serde_json::to_vec(&header).map_err(|e| PacketError::BadHeader(e.to_string()))?;
    let mut out = Vec::with_capacity(PREFIX + json.len() + offset as usize);
    out.extend_from_slice(FRAME_MAGIC);
    out.extend_from_slice(&FRAME_PACKET_VERSION.to_le_bytes());
    out.extend_from_slice(&(json.len() as u32).to_le_bytes());
    out.extend_from_slice(&json);
    for r in regions {
        out.extend_from_slice(r.rgba);
    }
    Ok(out)
}

pub fn decode_frame_packet(buf: &[u8]) -> Result<(FramePacketHeader, &[u8]), PacketError> {
    if buf.len() < PREFIX {
        return Err(PacketError::Truncated);
    }
    if &buf[0..4] != FRAME_MAGIC {
        return Err(PacketError::BadMagic);
    }
    let version = u16::from_le_bytes([buf[4], buf[5]]);
    if version != FRAME_PACKET_VERSION {
        return Err(PacketError::UnsupportedVersion(version));
    }
    let len = u32::from_le_bytes([buf[6], buf[7], buf[8], buf[9]]) as usize;
    if PREFIX + len > buf.len() {
        return Err(PacketError::Truncated);
    }
    let header: FramePacketHeader =
        serde_json::from_slice(&buf[PREFIX..PREFIX + len]).map_err(|e| PacketError::BadHeader(e.to_string()))?;
    Ok((header, &buf[PREFIX + len..]))
}
