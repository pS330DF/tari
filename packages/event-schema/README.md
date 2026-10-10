# Event schema (v1)

`python/tari_schema/` holds the Pydantic models — the source of truth for every
message and record. `pnpm gen:schema` exports `schemas/v1/tari.schema.json` and
regenerates `packages/shared-types/src/generated.ts`. `fixtures/frame_packet_v1.bin`
is a golden FramePacket decoded by the Python, TypeScript and Rust tests
(`pnpm gen:fixtures`). See `docs/protocol.md`.
