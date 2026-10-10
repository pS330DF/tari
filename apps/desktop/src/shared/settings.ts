/** Persisted desktop settings (validated on every load and write). */
import { z } from "zod";

export const DOMAINS = ["aim", "utility", "positioning", "tactical", "agent", "team", "communication"] as const;

export const coachingSchema = z.object({
  language: z.enum(["en", "ko"]).default("en"),
  intensity: z.enum(["low", "balanced", "high"]).default("balanced"),
  voice_frequency: z.enum(["off", "minimal", "normal", "frequent"]).default("normal"),
  strictness: z.enum(["lenient", "balanced", "strict"]).default("balanced"),
  overlay_density: z.enum(["minimal", "standard", "detailed"]).default("standard"),
  skill_level: z.enum(["new", "intermediate", "advanced"]).default("intermediate"),
  focus: z.array(z.enum(DOMAINS)).default(["aim"]),
  training_goals: z.array(z.string().max(80)).max(8).default([]),
  min_confidence: z.number().min(0.2).max(0.95).default(0.5),
});

export const perceptionSchema = z.object({
  crosshair_color: z.string().regex(/^#[0-9a-fA-F]{6}$/).default("#00f0ff"),
  target_color: z.enum(["red", "yellow", "purple"]).default("red"),
  hfov_deg: z.number().min(60).max(140).default(103),
  hud_profile: z.enum(["training_lab_v1", "none"]).default("training_lab_v1"),
});

export const captureSchema = z.object({
  targetFps: z.number().int().min(5).max(60).default(30),
  maxInFlight: z.number().int().min(1).max(3).default(1),
  analysisHeight: z.number().int().min(360).max(1080).default(540),
  centerSize: z.number().int().min(128).max(768).default(384),
  viewerMode: z.enum(["synced", "live"]).default("synced"),
});

export const voiceSchema = z.object({
  enabled: z.boolean().default(true),
  voiceURI: z.string().nullable().default(null),
  rate: z.number().min(0.6).max(1.6).default(1.05),
  volume: z.number().min(0).max(1).default(0.9),
});

export const privacySchema = z.object({
  microphoneEnabled: z.boolean().default(false),
  cloudExplanations: z.boolean().default(false),
});

export const settingsSchema = z.object({
  version: z.literal(1).default(1),
  coaching: coachingSchema.default({}),
  perception: perceptionSchema.default({}),
  capture: captureSchema.default({}),
  voice: voiceSchema.default({}),
  privacy: privacySchema.default({}),
});

export type AppSettings = z.infer<typeof settingsSchema>;
export type CoachingSettingsInput = z.infer<typeof coachingSchema>;

export const DEFAULT_SETTINGS: AppSettings = settingsSchema.parse({});

type DeepPartial<T> = { [K in keyof T]?: T[K] extends object ? (T[K] extends unknown[] ? T[K] : DeepPartial<T[K]>) : T[K] };
export type SettingsPatch = DeepPartial<AppSettings>;

export function mergeSettings(base: AppSettings, patch: SettingsPatch): AppSettings {
  const merged = {
    ...base,
    coaching: { ...base.coaching, ...(patch.coaching ?? {}) },
    perception: { ...base.perception, ...(patch.perception ?? {}) },
    capture: { ...base.capture, ...(patch.capture ?? {}) },
    voice: { ...base.voice, ...(patch.voice ?? {}) },
    privacy: { ...base.privacy, ...(patch.privacy ?? {}) },
  };
  return settingsSchema.parse(merged);
}
