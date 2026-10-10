/**
 * FramePacket binary codec (mirror of tari_schema.frame).
 *
 *   offset 0   4 bytes  magic "TFRM"
 *   offset 4   u16 LE   packet layout version
 *   offset 6   u32 LE   header length N
 *   offset 10  N bytes  UTF-8 JSON header (FramePacketHeader)
 *   offset 10+N         payload: concatenated region buffers
 */
import type { FramePacketHeader, FrameRegion } from "./generated";
import { SCHEMA_VERSION } from "./generated";

export const FRAME_MAGIC = "TFRM";
export const FRAME_PACKET_VERSION = 1;
export const FRAME_PREFIX_BYTES = 10;

export interface RegionPayload {
  name: string;
  srcRect: { x: number; y: number; w: number; h: number };
  width: number;
  height: number;
  /** RGBA8 pixels, length = width * height * 4 */
  data: Uint8Array | Uint8ClampedArray;
}

export type FrameHeaderInput = Omit<FramePacketHeader, "regions" | "schema_version" | "type" | "source_label" | "simulated"> & {
  schema_version?: string;
  source_label?: string;
  simulated?: boolean;
};

const encoder = new TextEncoder();
const decoder = new TextDecoder();

export function encodeFramePacket(input: FrameHeaderInput, regions: RegionPayload[]): ArrayBuffer {
  let offset = 0;
  if (regions.length === 0) throw new Error("a frame packet needs at least one region");
  const metas = regions.map((r): FrameRegion => {
    const expected = r.width * r.height * 4;
    if (r.data.byteLength !== expected) {
      throw new Error(`region ${r.name}: ${r.data.byteLength} bytes, expected ${expected}`);
    }
    const meta: FrameRegion = {
      name: r.name,
      src_rect: { x: r.srcRect.x, y: r.srcRect.y, w: r.srcRect.w, h: r.srcRect.h },
      width: r.width,
      height: r.height,
      format: "rgba8",
      byte_offset: offset,
      byte_length: expected,
    };
    offset += expected;
    return meta;
  });
  const header: FramePacketHeader = {
    ...input,
    source_label: input.source_label ?? "",
    simulated: input.simulated ?? false,
    schema_version: input.schema_version ?? SCHEMA_VERSION,
    type: "frame",
    regions: metas as FramePacketHeader["regions"],
  };
  const headerBytes = encoder.encode(JSON.stringify(header));
  const total = FRAME_PREFIX_BYTES + headerBytes.byteLength + offset;
  const buf = new ArrayBuffer(total);
  const view = new DataView(buf);
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < 4; i++) bytes[i] = FRAME_MAGIC.charCodeAt(i);
  view.setUint16(4, FRAME_PACKET_VERSION, true);
  view.setUint32(6, headerBytes.byteLength, true);
  bytes.set(headerBytes, FRAME_PREFIX_BYTES);
  let at = FRAME_PREFIX_BYTES + headerBytes.byteLength;
  for (const r of regions) {
    bytes.set(r.data instanceof Uint8Array ? r.data : new Uint8Array(r.data.buffer, r.data.byteOffset, r.data.byteLength), at);
    at += r.data.byteLength;
  }
  return buf;
}

export function decodeFramePacket(buf: ArrayBuffer): { header: FramePacketHeader; payload: Uint8Array } {
  if (buf.byteLength < FRAME_PREFIX_BYTES) throw new Error("truncated");
  const bytes = new Uint8Array(buf);
  const magic = String.fromCharCode(bytes[0]!, bytes[1]!, bytes[2]!, bytes[3]!);
  if (magic !== FRAME_MAGIC) throw new Error("bad_magic");
  const view = new DataView(buf);
  const version = view.getUint16(4, true);
  if (version !== FRAME_PACKET_VERSION) throw new Error("unsupported_version");
  const len = view.getUint32(6, true);
  if (FRAME_PREFIX_BYTES + len > buf.byteLength) throw new Error("truncated");
  const header = JSON.parse(decoder.decode(bytes.subarray(FRAME_PREFIX_BYTES, FRAME_PREFIX_BYTES + len))) as FramePacketHeader;
  return { header, payload: bytes.subarray(FRAME_PREFIX_BYTES + len) };
}
