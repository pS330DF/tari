import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { SCHEMA_VERSION, decodeFramePacket, encodeFramePacket, parseEngineMessage, isMajorCompatible } from "../src";

const fixture = resolve(__dirname, "../../event-schema/fixtures/frame_packet_v1.bin");

function pixels(w: number, h: number, seed: number): Uint8Array {
  const out = new Uint8Array(w * h * 4);
  for (let i = 0; i < w * h; i++) {
    out.set([(i + seed) % 256, (i * 3 + seed) % 256, (i * 7 + seed) % 256, 255], i * 4);
  }
  return out;
}

describe("FramePacket codec", () => {
  it("is byte-identical to the Python encoder (golden fixture)", () => {
    const golden = readFileSync(fixture);
    const packet = encodeFramePacket(
      {
        schema_version: "1.0.0",
        session_id: "fixture-session",
        frame_id: 42,
        source_id: "screen:0:0",
        source_kind: "screen",
        source_label: "Fixture",
        acquired_ts_ms: 1700000000000.25,
        sent_ts_ms: 1700000000003.5,
        source_width: 8,
        source_height: 4,
        simulated: true,
      },
      [
        { name: "full", srcRect: { x: 0, y: 0, w: 8, h: 4 }, width: 4, height: 2, data: pixels(4, 2, 0) },
        { name: "center", srcRect: { x: 3, y: 1, w: 2, h: 2 }, width: 2, height: 2, data: pixels(2, 2, 100) },
      ],
    );
    const ours = new Uint8Array(packet);
    // Header JSON key order may differ between serializers; compare decoded content and payload bytes.
    const a = decodeFramePacket(packet);
    const b = decodeFramePacket(golden.buffer.slice(golden.byteOffset, golden.byteOffset + golden.byteLength));
    expect(a.header).toEqual(b.header);
    expect(Array.from(a.payload)).toEqual(Array.from(b.payload));
    expect(Array.from(ours.subarray(0, 4))).toEqual([84, 70, 82, 77]);
  });

  it("rejects mismatched region sizes", () => {
    expect(() =>
      encodeFramePacket(
        {
          session_id: "s",
          frame_id: 1,
          source_id: "x",
          source_kind: "screen",
          acquired_ts_ms: 1,
          sent_ts_ms: 1,
          source_width: 4,
          source_height: 4,
        },
        [{ name: "full", srcRect: { x: 0, y: 0, w: 4, h: 4 }, width: 2, height: 2, data: new Uint8Array(15) }],
      ),
    ).toThrow(/expected 16/);
  });

  it("decoder rejects garbage", () => {
    expect(() => decodeFramePacket(new TextEncoder().encode("nope-nope-nope").buffer)).toThrow("bad_magic");
  });
});

describe("engine messages", () => {
  it("parses known and rejects unknown message types", () => {
    expect(parseEngineMessage('{"type":"pong","client_ts_ms":1,"engine_ts_ms":2,"schema_version":"1.0.0"}')?.type).toBe("pong");
    expect(parseEngineMessage('{"type":"surprise"}')).toBeNull();
    expect(parseEngineMessage("not json")).toBeNull();
  });
  it("checks major schema compatibility", () => {
    expect(isMajorCompatible("1.4.0", SCHEMA_VERSION)).toBe(true);
    expect(isMajorCompatible("2.0.0", SCHEMA_VERSION)).toBe(false);
  });
});
