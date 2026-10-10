/** Validated, atomically written JSON settings in the user data directory. */
import { existsSync } from "node:fs";
import { readFile, rename, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { DEFAULT_SETTINGS, mergeSettings, settingsSchema, type AppSettings, type SettingsPatch } from "../shared/settings";
import { log } from "./logger";

export class SettingsStore {
  private current: AppSettings = DEFAULT_SETTINGS;
  private readonly file: string;
  recovered: string | null = null;

  constructor(dir: string) {
    this.file = join(dir, "settings.json");
  }

  async load(): Promise<AppSettings> {
    if (!existsSync(this.file)) {
      this.current = DEFAULT_SETTINGS;
      return this.current;
    }
    try {
      const raw = JSON.parse(await readFile(this.file, "utf8"));
      this.current = settingsSchema.parse(raw);
    } catch (err) {
      const backup = this.file.replace(/\.json$/, `.corrupt-${Date.now()}.json`);
      await rename(this.file, backup).catch(() => undefined);
      this.recovered = backup;
      this.current = DEFAULT_SETTINGS;
      log("warn", "settings file invalid; defaults restored", { backup, error: String(err) });
      await this.persist();
    }
    return this.current;
  }

  get(): AppSettings {
    return this.current;
  }

  async update(patch: SettingsPatch): Promise<AppSettings> {
    this.current = mergeSettings(this.current, patch);
    await this.persist();
    return this.current;
  }

  private async persist(): Promise<void> {
    const tmp = `${this.file}.tmp`;
    await writeFile(tmp, JSON.stringify(this.current, null, 2), "utf8");
    await rename(tmp, this.file);
  }
}
