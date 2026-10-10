import json
import struct
from pathlib import Path

import pytest

from tari_schema import (
    FRAME_MAGIC, FramePacketError, FramePacketHeader, FrameRegion, PixelRect, decode_frame_packet, encode_frame_packet,
)

FIXTURE = Path(__file__).resolve().parents[2] / "packages" / "event-schema" / "fixtures" / "frame_packet_v1.bin"


def make_header(**over):
    base = dict(
        session_id="s1", frame_id=7, source_id="window:42", source_kind="window", source_label="Lab",
        acquired_ts_ms=1000.5, sent_ts_ms=1002.25, source_width=8, source_height=4,
        regions=[FrameRegion(name="full", src_rect=PixelRect(x=0, y=0, w=8, h=4), width=4, height=2,
                             byte_offset=0, byte_length=32)],
    )
    base.update(over)
    return FramePacketHeader(**base)


def test_roundtrip_preserves_header_and_payload():
    pkt = encode_frame_packet(make_header(), {"full": bytes(range(32))})
    header, payload = decode_frame_packet(pkt)
    assert header.frame_id == 7 and header.source_width == 8
    assert bytes(payload[:32]) == bytes(range(32))
    assert header.regions[0].byte_length == 32


@pytest.mark.parametrize("mutate,code", [
    (lambda b: b"XXXX" + b[4:], "bad_magic"),
    (lambda b: b[:4] + struct.pack("<H", 9) + b[6:], "unsupported_version"),
    (lambda b: b[:6], "truncated"),
    (lambda b: b[:-5], "region_out_of_bounds"),
])
def test_corrupted_packets_are_rejected(mutate, code):
    pkt = encode_frame_packet(make_header(), {"full": bytes(32)})
    with pytest.raises(FramePacketError) as exc:
        decode_frame_packet(mutate(pkt))
    assert exc.value.code == code


def test_region_size_mismatch_rejected():
    header = make_header()
    raw = header.model_dump()
    raw["regions"][0]["byte_length"] = 30
    hb = json.dumps(raw).encode()
    pkt = FRAME_MAGIC + struct.pack("<HI", 1, len(hb)) + hb + bytes(30)
    with pytest.raises(FramePacketError) as exc:
        decode_frame_packet(pkt)
    assert exc.value.code == "region_size_mismatch"


def test_region_outside_source_rejected():
    header = make_header(regions=[FrameRegion(name="full", src_rect=PixelRect(x=4, y=0, w=8, h=4), width=4,
                                              height=2, byte_offset=0, byte_length=32)])
    with pytest.raises(FramePacketError) as exc:
        decode_frame_packet(encode_frame_packet(header, {"full": bytes(32)}))
    assert exc.value.code == "region_outside_source"


def test_bad_header_json_and_schema():
    pkt = FRAME_MAGIC + struct.pack("<HI", 1, 5) + b"{oops"
    with pytest.raises(FramePacketError) as exc:
        decode_frame_packet(pkt)
    assert exc.value.code == "bad_header_json"
    hb = b'{"type":"frame"}'
    with pytest.raises(FramePacketError) as exc:
        decode_frame_packet(FRAME_MAGIC + struct.pack("<HI", 1, len(hb)) + hb)
    assert exc.value.code == "bad_header_schema"


def test_golden_fixture_decodes():
    """The TypeScript encoder test writes/validates the same fixture (cross-language contract)."""
    assert FIXTURE.exists(), "run `pnpm gen:fixtures`"
    header, payload = decode_frame_packet(FIXTURE.read_bytes())
    assert header.session_id == "fixture-session"
    assert header.frame_id == 42
    assert [r.name for r in header.regions] == ["full", "center"]
    full = header.regions[0]
    assert bytes(payload[full.byte_offset:full.byte_offset + 8]) == bytes([0, 0, 0, 255, 1, 3, 7, 255])
