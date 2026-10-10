import { mkdtempSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { SettingsStore } from "../src/main/settings-store";
import { DEFAULT_SETTINGS, mergeSettings, settingsSchema } from "../src/shared/settings";

describe("settings schema", () => {
  it("has complete, valid defaults", () => {
    expect(settingsSchema.parse({})).toEqual(DEFAULT_SETTINGS);
    expect(DEFAULT_SETTINGS.perception.hfov_deg).toBe(103);
    expect(DEFAULT_SETTINGS.privacy.microphoneEnabled).toBe(false);
  });

  it("merges nested patches and keeps other values", () => {
    const next = mergeSettings(DEFAULT_SETTINGS, { coaching: { language: "ko" }, capture: { targetFps: 60 } });
    expect(next.coaching.language).toBe("ko");
    expect(next.coaching.strictness).toBe("balanced");
    expect(next.capture.targetFps).toBe(60);
  });

  it("rejects out-of-range or malformed values", () => {
    expect(() => mergeSettings(DEFAULT_SETTINGS, { perception: { hfov_deg: 200 } })).toThrow();
    expect(() => mergeSettings(DEFAULT_SETTINGS, { perception: { crosshair_color: "cyan" } })).toThrow();
    expect(() => mergeSettings(DEFAULT_SETTINGS, { coaching: { focus: ["aim", "cheating" as never] } })).toThrow();
  });
});

describe("SettingsStore", () => {
  it("persists updates atomically and reloads them", async () => {
    const dir = mkdtempSync(join(tmpdir(), "tari-settings-"));
    const a = new SettingsStore(dir);
    await a.load();
    await a.update({ voice: { enabled: false } });
    const b = new SettingsStore(dir);
    expect((await b.load()).voice.enabled).toBe(false);
  });

  it("backs up a corrupt file and falls back to defaults", async () => {
    const dir = mkdtempSync(join(tmpdir(), "tari-settings-"));
    writeFileSync(join(dir, "settings.json"), "{ this is not json");
    const s = new SettingsStore(dir);
    expect(await s.load()).toEqual(DEFAULT_SETTINGS);
    expect(s.recovered).toMatch(/settings\.corrupt-\d+\.json$/);
    expect(readdirSync(dir).some((f) => f.startsWith("settings.corrupt-"))).toBe(true);
  });
});
