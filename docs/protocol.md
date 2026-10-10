# TARI stream protocol (schema 1.0.0)

Source of truth: `packages/event-schema/python/tari_schema/` (Pydantic).
Generated artifacts: `packages/event-schema/schemas/v1/tari.schema.json` and
`packages/shared-types/src/generated.ts` (`pnpm gen:schema`). Peers must share
the **major** schema version; the engine refuses control messages from another
major version (`notice: schema_incompatible`).

Conventions
- Timestamps: wall-clock epoch milliseconds (float), named `*_ts_ms`.
- Points and rects: normalized to the source frame (0..1, origin top-left, y down).
- Angles: degrees. Aim errors are *head minus crosshair*: `x > 0` head right of
  the crosshair, `y > 0` head above it (crosshair low).
- Every state field states its provenance: `observed | estimated | stale | unknown`,
  with `confidence`, `updated_ts_ms`, `source`, `method`, and `reason` when unknown.

## Endpoints (engine, loopback only)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/health` | none | liveness, version |
| GET | `/v1/info` | `x-tari-token` | versions, ONNX providers, persistence state, DB recovery info |
| GET | `/v1/sessions?limit=` | token | stored sessions with exposure/feedback counts |
| GET | `/v1/sessions/{id}` | token | metrics, recommendations, event counts, last perf snapshots |
| GET | `/v1/profile?include_simulated=` | token | longitudinal profile from stored measurements |
| WS | `/v1/stream?token=` | token | real-time stream (below) |

## FramePacket (binary WebSocket message)

```
offset 0   4 bytes  magic "TFRM"
offset 4   u16 LE   packet layout version (1)
offset 6   u32 LE   header length N (≤ 64 KiB)
offset 10  N bytes  UTF-8 JSON header
offset 10+N         payload: region buffers (RGBA8), concatenated
```

Header (`FramePacketHeader`): `schema_version`, `type:"frame"`, `session_id`,
`frame_id`, `source_id`, `source_kind` (`screen | window | video_file |
native_wgc | synthetic`), `source_label`, `acquired_ts_ms` (when the capture
adapter received the frame), `sent_ts_ms`, `source_width/height`,
`simulated`, and `regions[]`:

| field | meaning |
| --- | --- |
| `name` | `full` — whole frame scaled to 540 px height (≤ 1280 wide, never upscaled); `center` — unscaled crop (≤ 384 px) around the frame center with an even-aligned origin |
| `src_rect` | the region's rectangle in source pixels |
| `width/height` | payload dimensions |
| `byte_offset/byte_length` | location in the payload; length must equal `width*height*4` |

The engine validates magic, version, header JSON/schema, region sizes, bounds
and duplicates, and answers invalid packets with `frame_dropped: invalid`
and a coded reason (`bad_magic`, `truncated`, `region_size_mismatch`, …).

## Client → engine (text)

| `type` | fields | effect |
| --- | --- | --- |
| `start_session` | `session_id?`, `player_id`, `source{source_id, source_kind, label}`, `coaching` (CoachingSettings), `perception` (PerceptionSettings) | ends any active session, starts a new one, replies `session_started` |
| `update_settings` | `coaching?`, `perception?` | applied between frames |
| `end_session` | `reason` | finalizes and persists, replies `session_ended` with a summary |
| `client_metrics` | `snapshot` (PerformanceSnapshot, source `desktop`) | persisted with the session |
| `ping` | `client_ts_ms` | replies `pong` |

## Engine → client (text)

| `type` | content |
| --- | --- |
| `hello` | engine version + capabilities: perception modules and backends, ONNX providers, live vs planned coaching domains, `riot_integration: disabled_pending_authorization` |
| `session_started` | session id, start time, persistence (`sqlite`/`unavailable`) |
| `frame_result` | `perception` (PerceptionResult), `state` (GameState), `events[]`, `recommendations[]`, `overlays[]`, `voice[]`, `timings_ms` |
| `frame_dropped` | `frame_id`, `reason` (`stale | superseded | invalid | out_of_order | no_session`), `age_ms`, `detail` |
| `telemetry` | PerformanceSnapshot (1 Hz): latencies p50/p95/p99, rates, counters, gauges, and `unavailable{metric: reason}` |
| `notice` | `level`, `code`, `message`, `priority` (e.g. `integration_restricted`, `database_recovered`) |
| `session_ended` | summary: frames processed/dropped, exposures, acquisitions, metrics with methods |
| `pong` | round-trip check |

### Events (`events[]`, discriminated by `type`)

All carry `event_id`, `session_id`, `frame_id`, `ts_ms` (source acquisition
time) and `confidence`.

| type | key fields |
| --- | --- |
| `target_exposed` | `track_id`, `head`, `entry_error_deg`, `head_radius_deg`, `view_speed_dps`, `view_settled` |
| `target_acquired` | `acquisition_ms`, `resolution_ms` (analyzed-frame interval), `entry_error_deg` |
| `target_lost` | `visible_ms`, `acquired` |
| `flick_analyzed` | `outcome` (`clean | overshoot | undershoot | unresolved`), `initial_error_deg`, `overshoot_deg`, `residual_deg`, `submovements`, `inferred_view_frames` |
| `shot_fired` | `shots`, `track_id`, `error_deg`, `on_head`, `view_speed_dps`, `movement_error` |
| `environment_changed` | `previous`, `current`, `coaching_mode` |
| `source_reconfigured` | `reason` (`session_start | resolution_changed | capture_gap`), size, `gap_ms` |
| `perception_notice` | `module`, `state`, `message` |

### Recommendations

`CoachingRecommendation`: `rule_id`, `domain`, `priority` (P0–P3), `confidence`,
`tone`, `observation`, `suggestion`, `reasoning`, `short_text`,
`evidence[]{metric, value, unit, samples, method, detail}`, `context`,
`expiration{ttl_ms, expires_ts_ms, until_event}`, `language`, plus source frame id/time.

### Overlays

`OverlayInstruction`: `source_frame_id`, `source_ts_ms`, `ttl_ms` (200 ms),
`gated_by` (`training_lab`), `primitives[]` of kinds `cross | circle | box |
hline | line | arrow | polyline | text` with styles (`crosshair`,
`crosshair_estimated`, `target`, `head`, `guide`, `correction`, `trajectory`,
`label`, `good`, `warning`). Renderers must hide an instruction in live mode
once `now - source_ts_ms > ttl_ms`.

### Voice

`VoiceInstruction`: `priority`, `text`, `language`, `dedupe_key`, `interrupt`,
`ttl_ms`. Playback rules (client): P0 interrupts anything, P1 interrupts P2/P3,
same key not repeated within 8 s, not started within TTL → discarded.
