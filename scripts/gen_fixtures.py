"""Write the golden FramePacket fixture shared by Python and TypeScript tests."""

from pathlib import Path

from tari_schema import FramePacketHeader, FrameRegion, PixelRect, encode_frame_packet

OUT = Path(__file__).resolve().parents[1] / "packages" / "event-schema" / "fixtures" / "frame_packet_v1.bin"


def pixels(w: int, h: int, seed: int) -> bytes:
    out = bytearray()
    for i in range(w * h):
        out += bytes([(i + seed) % 256, (i * 3 + seed) % 256, (i * 7 + seed) % 256, 255])
    return bytes(out)


def main() -> None:
    full, center = pixels(4, 2, 0), pixels(2, 2, 100)
    header = FramePacketHeader(
        schema_version="1.0.0", session_id="fixture-session", frame_id=42, source_id="screen:0:0",
        source_kind="screen", source_label="Fixture", acquired_ts_ms=1700000000000.25, sent_ts_ms=1700000000003.5,
        source_width=8, source_height=4, simulated=True,
        regions=[
            FrameRegion(name="full", src_rect=PixelRect(x=0, y=0, w=8, h=4), width=4, height=2, byte_offset=0,
                        byte_length=len(full)),
            FrameRegion(name="center", src_rect=PixelRect(x=3, y=1, w=2, h=2), width=2, height=2, byte_offset=0,
                        byte_length=len(center)),
        ],
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(encode_frame_packet(header, {"full": full, "center": center}))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
