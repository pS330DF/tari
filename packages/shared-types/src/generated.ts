/* eslint-disable */
/**
 * Generated from packages/event-schema/schemas/v1/tari.schema.json (schema 1.0.0).
 * Do not edit by hand: run `pnpm gen:schema`.
 */

/**
 * TARI event schema 1.0.0. Generated from tari_schema; do not edit.
 */
export interface TariSchemaV1 {
  ClientMetricsMessage?: ClientMetricsMessage;
  CoachingRecommendation?: CoachingRecommendation;
  CoachingSettings?: CoachingSettings;
  EndSessionMessage?: EndSessionMessage;
  EnvironmentChangedEvent?: EnvironmentChangedEvent;
  FlickAnalyzedEvent?: FlickAnalyzedEvent;
  FrameDroppedMessage?: FrameDroppedMessage;
  FramePacketHeader?: FramePacketHeader;
  FrameRegion?: FrameRegion;
  FrameResultMessage?: FrameResultMessage;
  GameState?: GameState;
  HelloMessage?: HelloMessage;
  NoticeMessage?: NoticeMessage;
  OverlayInstruction?: OverlayInstruction;
  PerceptionNoticeEvent?: PerceptionNoticeEvent;
  PerceptionResult?: PerceptionResult;
  PerceptionSettings?: PerceptionSettings;
  PerformanceMetric?: PerformanceMetric;
  PerformanceSnapshot?: PerformanceSnapshot;
  PingMessage?: PingMessage;
  PlayerProfile?: PlayerProfile;
  PongMessage?: PongMessage;
  SessionEndedMessage?: SessionEndedMessage;
  SessionStartedMessage?: SessionStartedMessage;
  ShotFiredEvent?: ShotFiredEvent;
  SourceReconfiguredEvent?: SourceReconfiguredEvent;
  StartSessionMessage?: StartSessionMessage;
  TargetAcquiredEvent?: TargetAcquiredEvent;
  TargetExposedEvent?: TargetExposedEvent;
  TargetLostEvent?: TargetLostEvent;
  TelemetryMessage?: TelemetryMessage;
  UpdateSettingsMessage?: UpdateSettingsMessage;
  VoiceInstruction?: VoiceInstruction;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "ClientMetricsMessage".
 */
export interface ClientMetricsMessage {
  schema_version: string;
  snapshot: PerformanceSnapshot;
  type: "client_metrics";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "PerformanceSnapshot".
 */
export interface PerformanceSnapshot {
  counters: Counters;
  gauges: Gauges;
  latencies: Latencies;
  rates: Rates;
  schema_version: string;
  source: "engine" | "desktop";
  ts_ms: number;
  unavailable: Unavailable;
  window_s: number;
}
export interface Counters {
  [k: string]: number;
}
export interface Gauges {
  [k: string]: number | null;
}
export interface Latencies {
  [k: string]: LatencyStats;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "LatencyStats".
 */
export interface LatencyStats {
  count: number;
  max: number | null;
  mean: number | null;
  p50: number | null;
  p95: number | null;
  p99: number | null;
}
export interface Rates {
  [k: string]: number;
}
/**
 * metric -> reason it cannot be measured
 */
export interface Unavailable {
  [k: string]: string;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "CoachingRecommendation".
 */
export interface CoachingRecommendation {
  confidence: number;
  context: Context;
  created_ts_ms: number;
  dedupe_key: string;
  domain: "aim" | "utility" | "positioning" | "tactical" | "agent" | "team" | "communication" | "system";
  evidence: Evidence[];
  expiration: Expiration;
  language: "en" | "ko";
  observation: string;
  priority: "P0" | "P1" | "P2" | "P3";
  reasoning: string;
  rec_id: string;
  rule_id: string;
  schema_version: string;
  session_id: string;
  short_text: string;
  source_frame_id: number;
  source_ts_ms: number;
  suggestion: string;
  tone: "corrective" | "reinforcing" | "informational";
}
export interface Context {
  [k: string]: string;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "Evidence".
 */
export interface Evidence {
  detail: string | null;
  /**
   * How the value was calculated, in plain language
   */
  method: string;
  metric: string;
  samples: number;
  unit: string;
  value: number;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "Expiration".
 */
export interface Expiration {
  expires_ts_ms: number;
  ttl_ms: number;
  /**
   * Event type that supersedes this recommendation
   */
  until_event: string | null;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "CoachingSettings".
 */
export interface CoachingSettings {
  focus: ("aim" | "utility" | "positioning" | "tactical" | "agent" | "team" | "communication" | "system")[];
  intensity: "low" | "balanced" | "high";
  language: "en" | "ko";
  min_confidence: number;
  overlay_density: "minimal" | "standard" | "detailed";
  skill_level: "new" | "intermediate" | "advanced";
  strictness: "lenient" | "balanced" | "strict";
  training_goals: string[];
  voice_frequency: "off" | "minimal" | "normal" | "frequent";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "EndSessionMessage".
 */
export interface EndSessionMessage {
  reason: string;
  schema_version: string;
  type: "end_session";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "EnvironmentChangedEvent".
 */
export interface EnvironmentChangedEvent {
  coaching_mode: string;
  confidence: number;
  current: string;
  event_id: string;
  frame_id: number;
  previous: string;
  schema_version: string;
  session_id: string;
  ts_ms: number;
  type: "environment_changed";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "FlickAnalyzedEvent".
 */
export interface FlickAnalyzedEvent {
  confidence: number;
  event_id: string;
  frame_id: number;
  /**
   * Frames where view motion was unmeasurable and was inferred from the error change
   */
  inferred_view_frames: number;
  initial_error_deg: number;
  outcome: "clean" | "overshoot" | "undershoot" | "unresolved";
  overshoot_deg: number | null;
  /**
   * Error remaining when the first movement stopped
   */
  residual_deg: number | null;
  schema_version: string;
  session_id: string;
  submovements: number;
  track_id: number;
  ts_ms: number;
  type: "flick_analyzed";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "FrameDroppedMessage".
 */
export interface FrameDroppedMessage {
  age_ms: number | null;
  detail: string | null;
  frame_id: number | null;
  reason: "stale" | "superseded" | "invalid" | "out_of_order" | "no_session";
  schema_version: string;
  type: "frame_dropped";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "FramePacketHeader".
 */
export interface FramePacketHeader {
  /**
   * Wall-clock time the capture adapter received the frame
   */
  acquired_ts_ms: number;
  frame_id: number;
  /**
   * @minItems 1
   * @maxItems 8
   */
  regions: [FrameRegion, ...FrameRegion[]];
  schema_version: string;
  sent_ts_ms: number;
  session_id: string;
  /**
   * True only for synthetic/test frames
   */
  simulated: boolean;
  source_height: number;
  source_id: string;
  source_kind: "screen" | "window" | "video_file" | "native_wgc" | "synthetic";
  source_label: string;
  source_width: number;
  type: "frame";
}
/**
 * A pixel buffer cut from the source frame, possibly rescaled.
 *
 * ``src_rect`` is in source-frame pixels; ``width``/``height`` are the payload
 * dimensions. ``full`` regions are downscaled whole frames; ``center`` regions
 * are unscaled crops around the frame center used for crosshair precision.
 *
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "FrameRegion".
 */
export interface FrameRegion {
  byte_length: number;
  byte_offset: number;
  format: "rgba8";
  height: number;
  name: string;
  src_rect: PixelRect;
  width: number;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "PixelRect".
 */
export interface PixelRect {
  h: number;
  w: number;
  x: number;
  y: number;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "FrameResultMessage".
 */
export interface FrameResultMessage {
  events: (
    | TargetExposedEvent
    | TargetAcquiredEvent
    | TargetLostEvent
    | FlickAnalyzedEvent
    | ShotFiredEvent
    | EnvironmentChangedEvent
    | SourceReconfiguredEvent
    | PerceptionNoticeEvent
  )[];
  overlays: OverlayInstruction[];
  perception: PerceptionResult;
  recommendations: CoachingRecommendation[];
  schema_version: string;
  state: GameState;
  timings_ms: TimingsMs;
  type: "frame_result";
  voice: VoiceInstruction[];
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "TargetExposedEvent".
 */
export interface TargetExposedEvent {
  confidence: number;
  entry_error_deg: Point2;
  event_id: string;
  frame_id: number;
  head: Point2;
  head_radius_deg: number;
  schema_version: string;
  session_id: string;
  track_id: number;
  ts_ms: number;
  type: "target_exposed";
  /**
   * View speed below settle threshold at exposure (pre-aim held)
   */
  view_settled: boolean | null;
  view_speed_dps: number | null;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "Point2".
 */
export interface Point2 {
  x: number;
  y: number;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "TargetAcquiredEvent".
 */
export interface TargetAcquiredEvent {
  acquisition_ms: number;
  confidence: number;
  entry_error_deg: Point2;
  event_id: string;
  frame_id: number;
  /**
   * Timing uncertainty: interval between analyzed frames
   */
  resolution_ms: number;
  schema_version: string;
  session_id: string;
  track_id: number;
  ts_ms: number;
  type: "target_acquired";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "TargetLostEvent".
 */
export interface TargetLostEvent {
  acquired: boolean;
  confidence: number;
  event_id: string;
  frame_id: number;
  schema_version: string;
  session_id: string;
  track_id: number;
  ts_ms: number;
  type: "target_lost";
  visible_ms: number;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "ShotFiredEvent".
 */
export interface ShotFiredEvent {
  confidence: number;
  error_deg: Point2 | null;
  event_id: string;
  frame_id: number;
  movement_error: boolean | null;
  on_head: boolean | null;
  schema_version: string;
  session_id: string;
  shots: number;
  track_id: number | null;
  ts_ms: number;
  type: "shot_fired";
  view_speed_dps: number | null;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "SourceReconfiguredEvent".
 */
export interface SourceReconfiguredEvent {
  confidence: number;
  event_id: string;
  frame_id: number;
  gap_ms: number | null;
  height: number;
  reason: "session_start" | "resolution_changed" | "capture_gap";
  schema_version: string;
  session_id: string;
  ts_ms: number;
  type: "source_reconfigured";
  width: number;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "PerceptionNoticeEvent".
 */
export interface PerceptionNoticeEvent {
  confidence: number;
  event_id: string;
  frame_id: number;
  message: string;
  module: string;
  schema_version: string;
  session_id: string;
  state: string;
  ts_ms: number;
  type: "perception_notice";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "OverlayInstruction".
 */
export interface OverlayInstruction {
  created_ts_ms: number;
  gated_by: "training_lab" | "authorized";
  instruction_id: string;
  layer: "spatial" | "panel";
  primitives: OverlayPrimitive[];
  schema_version: string;
  session_id: string;
  source_frame_id: number;
  /**
   * Acquisition time of the frame these primitives describe
   */
  source_ts_ms: number;
  /**
   * Renderer must hide primitives once frame age exceeds this in live mode
   */
  ttl_ms: number;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "OverlayPrimitive".
 */
export interface OverlayPrimitive {
  emphasis: number;
  kind: "box" | "circle" | "line" | "arrow" | "polyline" | "hline" | "text" | "cross";
  points: Point2[];
  /**
   * Normalized by source width
   */
  radius: number | null;
  style:
    | "target"
    | "head"
    | "crosshair"
    | "crosshair_estimated"
    | "error"
    | "correction"
    | "trajectory"
    | "guide"
    | "label"
    | "warning"
    | "good";
  text: string | null;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "PerceptionResult".
 */
export interface PerceptionResult {
  acquired_ts_ms: number;
  crosshair: CrosshairObservation | null;
  ego_motion: EgoMotion | null;
  engine_received_ts_ms: number;
  environment: EnvironmentObservation | null;
  frame_id: number;
  hud: HudReading | null;
  modules: ModuleStatus[];
  processed_ts_ms: number;
  processing_started_ts_ms: number;
  schema_version: string;
  session_id: string;
  simulated: boolean;
  source_height: number;
  source_width: number;
  targets: TargetDetection[];
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "CrosshairObservation".
 */
export interface CrosshairObservation {
  /**
   * Center-to-inner-arm distance, source px
   */
  arm_gap_px: number | null;
  arms_found: number;
  confidence: number;
  method: "detected" | "assumed_center";
  position: Point2;
}
/**
 * Global image motion between the previous and current analyzed frames.
 *
 * Rotation and player translation are not separated: this is *view* motion.
 *
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "EgoMotion".
 */
export interface EgoMotion {
  confidence: number;
  interval_ms: number;
  measurable: boolean;
  response: number;
  shift_px: Point2;
  view_rate_dps: Point2;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "EnvironmentObservation".
 */
export interface EnvironmentObservation {
  confidence: number;
  corners: Point2[];
  kind: "training_lab" | "unknown";
  map_id: string | null;
  marker_id: number | null;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "HudReading".
 */
export interface HudReading {
  profile: string;
  readouts: HudReadout[];
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "HudReadout".
 */
export interface HudReadout {
  confidence: number;
  name: string;
  raw: string | null;
  value: number | null;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "ModuleStatus".
 */
export interface ModuleStatus {
  backend: string | null;
  detail: string | null;
  duration_ms: number | null;
  name: string;
  state: "ok" | "degraded" | "failed" | "skipped" | "unavailable";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "TargetDetection".
 */
export interface TargetDetection {
  /**
   * Approximate silhouette area in source px
   */
  area_px: number;
  backend: string;
  bbox: Rect;
  confidence: number;
  /**
   * Head partly covered by the crosshair (position less certain)
   */
  crosshair_overlap: boolean;
  head: Point2;
  head_method: "head_profile" | "top_ratio" | "blob_top" | "refined_crop";
  /**
   * Head radius normalized by source width
   */
  head_radius: number;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "Rect".
 */
export interface Rect {
  h: number;
  w: number;
  x: number;
  y: number;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "GameState".
 */
export interface GameState {
  abilities: TextListField;
  agent: TextField;
  ammo: IntField;
  coaching_mode: "live_training" | "live_authorized" | "restricted";
  coaching_mode_reason: string;
  crosshair: PointField;
  drill: TextField;
  environment: TextField;
  frame_id: number;
  map: TextField;
  movement_error: BoolField;
  observation_confidence: number;
  recent_events: EventSummary[];
  round_phase: TextField;
  schema_version: string;
  session_id: string;
  targets: TrackState[];
  teammates: TextListField;
  timer_s: IntField;
  /**
   * Acquisition time of the frame this state reflects
   */
  ts_ms: number;
  view_motion: MotionField;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "TextListField".
 */
export interface TextListField {
  confidence: number;
  method: string | null;
  /**
   * Why the field is unknown/stale, if it is
   */
  reason: string | null;
  source: string | null;
  status: "observed" | "estimated" | "unknown" | "stale";
  updated_ts_ms: number | null;
  value: string[] | null;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "TextField".
 */
export interface TextField {
  confidence: number;
  method: string | null;
  /**
   * Why the field is unknown/stale, if it is
   */
  reason: string | null;
  source: string | null;
  status: "observed" | "estimated" | "unknown" | "stale";
  updated_ts_ms: number | null;
  value: string | null;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "IntField".
 */
export interface IntField {
  confidence: number;
  method: string | null;
  /**
   * Why the field is unknown/stale, if it is
   */
  reason: string | null;
  source: string | null;
  status: "observed" | "estimated" | "unknown" | "stale";
  updated_ts_ms: number | null;
  value: number | null;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "PointField".
 */
export interface PointField {
  confidence: number;
  method: string | null;
  /**
   * Why the field is unknown/stale, if it is
   */
  reason: string | null;
  source: string | null;
  status: "observed" | "estimated" | "unknown" | "stale";
  updated_ts_ms: number | null;
  value: Point2 | null;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "BoolField".
 */
export interface BoolField {
  confidence: number;
  method: string | null;
  /**
   * Why the field is unknown/stale, if it is
   */
  reason: string | null;
  source: string | null;
  status: "observed" | "estimated" | "unknown" | "stale";
  updated_ts_ms: number | null;
  value: boolean | null;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "EventSummary".
 */
export interface EventSummary {
  event_id: string;
  ts_ms: number;
  type: string;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "TrackState".
 */
export interface TrackState {
  acquired: boolean;
  acquisition_ms: number | null;
  bbox: Rect;
  confidence: number;
  /**
   * Head minus crosshair in degrees: x>0 head right of crosshair, y>0 head above
   */
  error_deg: Point2 | null;
  first_seen_ts_ms: number;
  head: Point2;
  head_radius: number;
  head_radius_deg: number | null;
  last_seen_ts_ms: number;
  status: "visible" | "coasting";
  track_id: number;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "MotionField".
 */
export interface MotionField {
  confidence: number;
  method: string | null;
  /**
   * Why the field is unknown/stale, if it is
   */
  reason: string | null;
  source: string | null;
  status: "observed" | "estimated" | "unknown" | "stale";
  updated_ts_ms: number | null;
  value: EgoMotion | null;
}
export interface TimingsMs {
  [k: string]: number;
}
/**
 * A request to speak. P0 system/safety, P1 essential training, P2 tactical, P3 general.
 *
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "VoiceInstruction".
 */
export interface VoiceInstruction {
  created_ts_ms: number;
  dedupe_key: string;
  domain: "aim" | "utility" | "positioning" | "tactical" | "agent" | "team" | "communication" | "system";
  interrupt: boolean;
  language: "en" | "ko";
  priority: "P0" | "P1" | "P2" | "P3";
  rec_id: string | null;
  schema_version: string;
  session_id: string;
  text: string;
  /**
   * Discard if not started within this many ms of creation
   */
  ttl_ms: number;
  voice_id: string;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "HelloMessage".
 */
export interface HelloMessage {
  capabilities: EngineCapabilities;
  engine_version: string;
  schema_version: string;
  type: "hello";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "EngineCapabilities".
 */
export interface EngineCapabilities {
  /**
   * Execution provider used for neural models, or 'none' if no model loaded
   */
  accelerator: string;
  coaching_domains_live: (
    "aim" | "utility" | "positioning" | "tactical" | "agent" | "team" | "communication" | "system"
  )[];
  coaching_domains_planned: (
    "aim" | "utility" | "positioning" | "tactical" | "agent" | "team" | "communication" | "system"
  )[];
  hud_profiles: string[];
  onnx_providers_available: string[];
  perception_modules: ModuleStatus[];
  riot_integration: "disabled_pending_authorization";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "NoticeMessage".
 */
export interface NoticeMessage {
  code: string;
  level: "info" | "warning" | "error";
  message: string;
  priority: "P0" | "P1" | "P2" | "P3";
  schema_version: string;
  type: "notice";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "PerceptionSettings".
 */
export interface PerceptionSettings {
  crosshair_color: string;
  hfov_deg: number;
  hud_profile: "training_lab_v1" | "none";
  target_color: "red" | "yellow" | "purple";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "PerformanceMetric".
 */
export interface PerformanceMetric {
  available: boolean;
  name: string;
  note: string | null;
  schema_version: string;
  source: "engine" | "desktop";
  ts_ms: number;
  unit: string;
  value: number | null;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "PingMessage".
 */
export interface PingMessage {
  client_ts_ms: number;
  schema_version: string;
  type: "ping";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "PlayerProfile".
 */
export interface PlayerProfile {
  environments: Environments;
  generated_ts_ms: number;
  next_focus: string | null;
  next_focus_reason: string | null;
  player_id: string;
  recurring_issues: RecurringIssue[];
  schema_version: string;
  sessions_total: number;
  skills: SkillProgress[];
  total_exposures: number;
  /**
   * Sessions with enough measured samples to count toward trends
   */
  validated_sessions: number;
}
export interface Environments {
  [k: string]: number;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "RecurringIssue".
 */
export interface RecurringIssue {
  last_ts_ms: number;
  occurrences: number;
  rule_id: string;
  sessions: number;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "SkillProgress".
 */
export interface SkillProgress {
  better: "lower" | "higher";
  label: string;
  method: string;
  points: SkillDataPoint[];
  skill: string;
  trend: "improving" | "declining" | "stable" | "insufficient_data";
  trend_detail: string | null;
  unit: string;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "SkillDataPoint".
 */
export interface SkillDataPoint {
  samples: number;
  session_id: string;
  ts_ms: number;
  value: number;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "PongMessage".
 */
export interface PongMessage {
  client_ts_ms: number;
  engine_ts_ms: number;
  schema_version: string;
  type: "pong";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "SessionEndedMessage".
 */
export interface SessionEndedMessage {
  reason: string;
  schema_version: string;
  session_id: string;
  summary: SessionSummary;
  type: "session_ended";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "SessionSummary".
 */
export interface SessionSummary {
  acquisitions: number;
  ended_ts_ms: number;
  exposures: number;
  frames_dropped: number;
  frames_processed: number;
  metrics: Evidence[];
  session_id: string;
  started_ts_ms: number;
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "SessionStartedMessage".
 */
export interface SessionStartedMessage {
  persistence: "sqlite" | "unavailable";
  schema_version: string;
  session_id: string;
  started_ts_ms: number;
  type: "session_started";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "StartSessionMessage".
 */
export interface StartSessionMessage {
  coaching: CoachingSettings;
  perception: PerceptionSettings;
  player_id: string;
  schema_version: string;
  session_id: string | null;
  source: ClientSourceInfo;
  type: "start_session";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "ClientSourceInfo".
 */
export interface ClientSourceInfo {
  label: string;
  source_id: string;
  source_kind: "screen" | "window" | "video_file" | "native_wgc" | "synthetic";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "TelemetryMessage".
 */
export interface TelemetryMessage {
  schema_version: string;
  snapshot: PerformanceSnapshot;
  type: "telemetry";
}
/**
 * This interface was referenced by `TariSchemaV1`'s JSON-Schema
 * via the `definition` "UpdateSettingsMessage".
 */
export interface UpdateSettingsMessage {
  coaching: CoachingSettings | null;
  perception: PerceptionSettings | null;
  schema_version: string;
  type: "update_settings";
}

export const SCHEMA_VERSION = "1.0.0";
