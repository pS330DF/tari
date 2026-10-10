import { SCHEMA_VERSION } from "@tari/shared-types";
import { epochMs } from "@tari/telemetry";
import { RotateCw, Volume2 } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import type { AppInfo } from "../../../shared/ipc";
import type { AppSettings, SettingsPatch } from "../../../shared/settings";
import { Button } from "../components/ui/button";
import { Segmented } from "../components/ui/segmented";
import { Select } from "../components/ui/select";
import { Slider } from "../components/ui/slider";
import { Switch } from "../components/ui/switch";
import { cn } from "../lib/utils";
import { runtime } from "../runtime";
import { useApp } from "../store/app-store";

const update = (patch: SettingsPatch) => void window.tari.invoke("settings:set", patch);

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section className="border-t border-line py-5 first:border-t-0">
      <h2 className="text-[13.5px] font-semibold">{title}</h2>
      {description && <p className="mt-0.5 max-w-2xl text-[12.5px] leading-relaxed text-fg-muted">{description}</p>}
      <div className="mt-3 space-y-3.5">{children}</div>
    </section>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-6">
      <div className="min-w-0">
        <div className="text-[13px] text-fg">{label}</div>
        {hint && <div className="text-[12px] leading-snug text-fg-subtle">{hint}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

const CROSSHAIR_PRESETS = ["#00f0ff", "#00ff6a", "#ffff00", "#ffffff", "#ff00ff"];

export function SettingsView() {
  const settings = useApp((s) => s.settings);
  const engine = useApp((s) => s.engine);
  const caps = useApp((s) => s.capabilities);
  const companionVisible = useApp((s) => s.companionVisible);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [minConf, setMinConf] = useState<number | null>(null);

  useEffect(() => {
    const load = () => setVoices(window.speechSynthesis.getVoices());
    load();
    window.speechSynthesis.addEventListener("voiceschanged", load);
    void window.tari.invoke("app:info", undefined).then(setInfo);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", load);
  }, []);

  if (!settings) return null;
  const s: AppSettings = settings;
  const lang = s.coaching.language === "ko" ? "ko" : "en";
  const langVoices = voices.filter((v) => v.lang.toLowerCase().startsWith(lang));
  const live = new Set(caps?.coaching_domains_live ?? ["aim"]);

  function testVoice() {
    runtime.voice.enqueue({
      schema_version: SCHEMA_VERSION, voice_id: crypto.randomUUID(), session_id: "settings", created_ts_ms: epochMs(),
      priority: "P1", domain: "system", language: s.coaching.language, dedupe_key: `test.${Date.now()}`, interrupt: true, ttl_ms: 4000, rec_id: null,
      text: s.coaching.language === "ko" ? "조준점을 머리 높이로 올리세요." : "Raise your placement to head height.",
    });
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-6 py-6">
        <h1 className="text-[16px] font-semibold">Settings</h1>

        <Section title="Coaching" description="How TARI speaks to you and how strict its feedback is. Changes apply to the running session immediately.">
          <Row label="Language" hint="Feedback text and voice">
            <Segmented value={s.coaching.language} onChange={(v) => update({ coaching: { language: v } })} options={[{ value: "en", label: "English" }, { value: "ko", label: "한국어" }]} />
          </Row>
          <Row label="Coaching intensity" hint="How often feedback may appear (duplicate cooldown and spacing)">
            <Segmented value={s.coaching.intensity} onChange={(v) => update({ coaching: { intensity: v } })} options={[{ value: "low", label: "Low" }, { value: "balanced", label: "Balanced" }, { value: "high", label: "High" }]} />
          </Row>
          <Row label="Feedback strictness" hint="Thresholds for placement, acquisition and stability rules">
            <Segmented value={s.coaching.strictness} onChange={(v) => update({ coaching: { strictness: v } })} options={[{ value: "lenient", label: "Lenient" }, { value: "balanced", label: "Balanced" }, { value: "strict", label: "Strict" }]} />
          </Row>
          <Row label="Skill level" hint="Adjusts the acquisition-time target">
            <Segmented value={s.coaching.skill_level} onChange={(v) => update({ coaching: { skill_level: v } })} options={[{ value: "new", label: "New" }, { value: "intermediate", label: "Intermediate" }, { value: "advanced", label: "Advanced" }]} />
          </Row>
          <Row label="Overlay density" hint="Spatial markers drawn on analyzed frames">
            <Segmented value={s.coaching.overlay_density} onChange={(v) => update({ coaching: { overlay_density: v } })} options={[{ value: "minimal", label: "Minimal" }, { value: "standard", label: "Standard" }, { value: "detailed", label: "Detailed" }]} />
          </Row>
          <Row label="Coaching focus" hint={`Live now: ${[...live].join(", ")}. Planned: ${(caps?.coaching_domains_planned ?? []).join(", ") || "—"}.`}>
            <div className="flex gap-1.5">
              {[...live].map((d) => {
                const on = s.coaching.focus.includes(d as never);
                return (
                  <button
                    key={d}
                    onClick={() => update({ coaching: { focus: on ? s.coaching.focus.filter((f) => f !== d) : [...s.coaching.focus, d as never] } })}
                    className={cn("h-7 rounded-md border px-2.5 text-[12.5px] capitalize", on ? "border-accent/50 bg-accent/10 text-accent-strong" : "border-line-strong text-fg-muted")}
                  >
                    {d}
                  </button>
                );
              })}
            </div>
          </Row>
          <Row label="Minimum confidence" hint="Feedback below this certainty score is withheld">
            <div className="flex w-56 items-center gap-3">
              <Slider value={minConf ?? s.coaching.min_confidence} min={0.3} max={0.9} step={0.05} onValueChange={setMinConf} onValueCommit={(v) => { setMinConf(null); update({ coaching: { min_confidence: v } }); }} />
              <span className="tabular w-9 text-right text-[12.5px]">{(minConf ?? s.coaching.min_confidence).toFixed(2)}</span>
            </div>
          </Row>
        </Section>

        <Section title="Voice" description="Spoken feedback uses your system's local voices. P0 system notices interrupt; training feedback interrupts explanations; repeats are suppressed.">
          <Row label="Spoken feedback">
            <Switch checked={s.voice.enabled} onCheckedChange={(v) => update({ voice: { enabled: v } })} />
          </Row>
          <Row label="Voice frequency" hint="Minimal: essential training feedback only. Frequent: includes general advice.">
            <Segmented value={s.coaching.voice_frequency} onChange={(v) => update({ coaching: { voice_frequency: v } })} options={[{ value: "off", label: "Off" }, { value: "minimal", label: "Minimal" }, { value: "normal", label: "Normal" }, { value: "frequent", label: "Frequent" }]} />
          </Row>
          <Row label="Voice" hint={langVoices.length ? `${langVoices.length} ${lang === "ko" ? "Korean" : "English"} voices installed` : `No ${lang === "ko" ? "Korean" : "English"} system voice found`}>
            <Select
              width="w-64"
              value={s.voice.voiceURI ?? ""}
              placeholder="System default"
              onValueChange={(v) => update({ voice: { voiceURI: v } })}
              options={langVoices.map((v) => ({ value: v.voiceURI, label: v.name, hint: v.lang }))}
            />
          </Row>
          <Row label="Rate">
            <div className="flex w-56 items-center gap-3">
              <Slider value={s.voice.rate} min={0.7} max={1.5} step={0.05} onValueCommit={(v) => update({ voice: { rate: v } })} />
              <span className="tabular w-9 text-right text-[12.5px]">{s.voice.rate.toFixed(2)}</span>
            </div>
          </Row>
          <Row label="Volume">
            <div className="flex w-56 items-center gap-3">
              <Slider value={s.voice.volume} min={0} max={1} step={0.05} onValueCommit={(v) => update({ voice: { volume: v } })} />
              <span className="tabular w-9 text-right text-[12.5px]">{Math.round(s.voice.volume * 100)}</span>
            </div>
          </Row>
          <Row label="Test voice">
            <Button variant="secondary" size="sm" onClick={testVoice} disabled={!s.voice.enabled}>
              <Volume2 /> Speak a sample
            </Button>
          </Row>
        </Section>

        <Section title="Detection" description="Tell TARI what your crosshair and enemy highlight look like. Wrong values pause measurements rather than guessing.">
          <Row label="Crosshair color">
            <div className="flex items-center gap-1.5">
              {CROSSHAIR_PRESETS.map((c) => (
                <button key={c} onClick={() => update({ perception: { crosshair_color: c } })} aria-label={`Crosshair ${c}`}
                  className={cn("size-6 rounded border", s.perception.crosshair_color.toLowerCase() === c ? "border-fg" : "border-line-strong")} style={{ background: c }} />
              ))}
              <input type="color" value={s.perception.crosshair_color} onChange={(e) => update({ perception: { crosshair_color: e.target.value } })}
                className="ml-1 h-6 w-8 cursor-pointer rounded border border-line-strong bg-transparent" aria-label="Custom crosshair color" />
            </div>
          </Row>
          <Row label="Enemy highlight color" hint="Matches VALORANT's accessibility options">
            <Segmented value={s.perception.target_color} onChange={(v) => update({ perception: { target_color: v } })} options={[{ value: "red", label: "Red" }, { value: "yellow", label: "Yellow" }, { value: "purple", label: "Purple" }]} />
          </Row>
          <Row label="Horizontal field of view" hint="Used to convert screen offsets to angles (VALORANT and the Lab use 103°)">
            <div className="flex w-56 items-center gap-3">
              <Slider value={s.perception.hfov_deg} min={70} max={120} step={1} onValueCommit={(v) => update({ perception: { hfov_deg: v } })} />
              <span className="tabular w-9 text-right text-[12.5px]">{s.perception.hfov_deg}°</span>
            </div>
          </Row>
        </Section>

        <Section title="Capture & analysis" description="Frames beyond the analysis rate, or that arrive while the engine is busy, are skipped instead of queued, keeping feedback current.">
          <Row label="Analysis rate">
            <Segmented value={String(s.capture.targetFps)} onChange={(v) => update({ capture: { targetFps: Number(v) } })} options={["15", "20", "30", "45", "60"].map((v) => ({ value: v, label: `${v} fps` }))} />
          </Row>
          <Row label="Analysis resolution" hint="Height of the downscaled frame; the crosshair area is always analyzed at full resolution">
            <Segmented value={String(s.capture.analysisHeight)} onChange={(v) => update({ capture: { analysisHeight: Number(v) } })} options={["360", "540", "720"].map((v) => ({ value: v, label: `${v}p` }))} />
          </Row>
          <Row label="Frames in flight" hint="1 gives the lowest latency; 2 can raise throughput on slower machines">
            <Segmented value={String(s.capture.maxInFlight)} onChange={(v) => update({ capture: { maxInFlight: Number(v) } })} options={[{ value: "1", label: "1" }, { value: "2", label: "2" }]} />
          </Row>
        </Section>

        <Section title="Companion window" description="A small always-on-top panel showing TARI's status and latest feedback while you play.">
          <Row label="Show compact companion">
            <Switch checked={companionVisible} onCheckedChange={(v) => void window.tari.invoke("companion:set-visible", { visible: v })} />
          </Row>
        </Section>

        <Section title="Engine">
          <Row label="Status" hint={engine.lastError ?? (engine.python ? `Python: ${engine.python}` : undefined)}>
            <span className="text-[12.5px] text-fg-muted">{engine.state}{engine.port ? ` · 127.0.0.1:${engine.port}` : ""}</span>
          </Row>
          <Row label="Restart engine" hint="Ends the current session; capture keeps running and a new session starts automatically">
            <Button variant="secondary" size="sm" onClick={() => void window.tari.invoke("engine:restart", undefined)}>
              <RotateCw /> Restart
            </Button>
          </Row>
        </Section>

        <Section title="Privacy">
          <p className="text-[12.5px] leading-relaxed text-fg-muted">
            Captured frames are analyzed on this computer by the local engine and are never uploaded. Session history is stored in a
            local SQLite database{info ? ` under ${info.dataDir}` : ""}. The microphone is not used in this build, and TARI does not
            read game memory, inject into games, or generate input.
          </p>
        </Section>

        {info && (
          <p className="pt-2 pb-8 text-[11.5px] text-fg-subtle">
            TARI {info.version} · Electron {info.electron} · Chromium {info.chrome} · {info.platform} · schema {SCHEMA_VERSION}
          </p>
        )}
      </div>
    </div>
  );
}
