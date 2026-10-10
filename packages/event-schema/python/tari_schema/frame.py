"""FramePacket: the binary unit sent from a capture adapter to the engine.

Wire layout (little-endian):

    offset 0   4 bytes   magic  b"TFRM"
    offset 4   u16       packet layout version (FRAME_PACKET_VERSION)
    offset 6   u32       header length N (bytes)
    offset 10  N bytes   UTF-8 JSON header (FramePacketHeader)
    offset 10+N          payload: concatenated region pixel buffers

Each region carries its own byte offset/length relative to the payload start.
"""

from __future__ import annotations

import json
import struct
from typing import Literal

from pydantic import Field, ValidationError

from .common import PixelRect, TariModel, VersionedModel

FRAME_MAGIC = b"TFRM"
FRAME_PACKET_VERSION = 1
FRAME_PREFIX = struct.Struct("<4sHI")
MAX_HEADER_BYTES = 64 * 1024
BYTES_PER_PIXEL = {"rgba8": 4}

PixelFormat = Literal["rgba8"]
SourceKind = Literal["screen", "window", "video_file", "native_wgc", "synthetic"]


class FrameRegion(TariModel):
    """A pixel buffer cut from the source frame, possibly rescaled.

    ``src_rect`` is in source-frame pixels; ``width``/``height`` are the payload
    dimensions. ``full`` regions are downscaled whole frames; ``center`` regions
    are unscaled crops around the frame center used for crosshair precision.
    """

    name: str = Field(min_length=1, max_length=32)
    src_rect: PixelRect
    width: int = Field(gt=0, le=8192)
    height: int = Field(gt=0, le=8192)
    format: PixelFormat = "rgba8"
    byte_offset: int = Field(ge=0)
    byte_length: int = Field(gt=0)


class FramePacketHeader(VersionedModel):
    type: Literal["frame"] = "frame"
    session_id: str = Field(min_length=1, max_length=64)
    frame_id: int = Field(ge=0)
    source_id: str = Field(max_length=256)
    source_kind: SourceKind
    source_label: str = Field(default="", max_length=256)
    acquired_ts_ms: float = Field(description="Wall-clock time the capture adapter received the frame")
    sent_ts_ms: float
    source_width: int = Field(gt=0, le=16384)
    source_height: int = Field(gt=0, le=16384)
    regions: list[FrameRegion] = Field(min_length=1, max_length=8)
    simulated: bool = Field(default=False, description="True only for synthetic/test frames")


class FramePacketError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def encode_frame_packet(header: FramePacketHeader, payloads: dict[str, bytes]) -> bytes:
    """Serialize a packet. Region offsets/lengths in ``header`` are recomputed."""
    regions: list[FrameRegion] = []
    offset = 0
    chunks: list[bytes] = []
    for region in header.regions:
        data = payloads[region.name]
        regions.append(region.model_copy(update={"byte_offset": offset, "byte_length": len(data)}))
        chunks.append(bytes(data))
        offset += len(data)
    final = header.model_copy(update={"regions": regions})
    header_bytes = final.model_dump_json().encode("utf-8")
    if len(header_bytes) > MAX_HEADER_BYTES:
        raise FramePacketError("header_too_large", f"{len(header_bytes)} bytes")
    return FRAME_PREFIX.pack(FRAME_MAGIC, FRAME_PACKET_VERSION, len(header_bytes)) + header_bytes + b"".join(chunks)


def decode_frame_packet(buf: bytes | bytearray | memoryview) -> tuple[FramePacketHeader, memoryview]:
    """Parse and validate a packet. Returns the header and a zero-copy payload view."""
    view = memoryview(buf)
    if len(view) < FRAME_PREFIX.size:
        raise FramePacketError("truncated", "packet shorter than prefix")
    magic, version, header_len = FRAME_PREFIX.unpack_from(view, 0)
    if magic != FRAME_MAGIC:
        raise FramePacketError("bad_magic", repr(bytes(magic)))
    if version != FRAME_PACKET_VERSION:
        raise FramePacketError("unsupported_version", f"packet version {version}")
    if header_len <= 0 or header_len > MAX_HEADER_BYTES:
        raise FramePacketError("bad_header_length", str(header_len))
    start = FRAME_PREFIX.size
    end = start + header_len
    if end > len(view):
        raise FramePacketError("truncated", "header exceeds packet")
    try:
        raw = json.loads(bytes(view[start:end]).decode("utf-8"))
        header = FramePacketHeader.model_validate(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FramePacketError("bad_header_json", str(exc)) from exc
    except ValidationError as exc:
        raise FramePacketError("bad_header_schema", exc.errors(include_url=False).__repr__()[:500]) from exc
    payload = view[end:]
    seen: set[str] = set()
    for region in header.regions:
        if region.name in seen:
            raise FramePacketError("duplicate_region", region.name)
        seen.add(region.name)
        expected = region.width * region.height * BYTES_PER_PIXEL[region.format]
        if region.byte_length != expected:
            raise FramePacketError(
                "region_size_mismatch",
                f"{region.name}: {region.byte_length} bytes, expected {expected} for {region.width}x{region.height}",
            )
        if region.byte_offset + region.byte_length > len(payload):
            raise FramePacketError("region_out_of_bounds", region.name)
        r = region.src_rect
        if r.x + r.w > header.source_width or r.y + r.h > header.source_height:
            raise FramePacketError("region_outside_source", region.name)
    return header, payload
