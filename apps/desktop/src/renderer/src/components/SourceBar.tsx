import { FlaskConical, Film, Play, RefreshCw, ShieldAlert, Square } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { CaptureSourceInfo } from "../../../shared/ipc";
import { runtime } from "../runtime";
import { useApp } from "../store/app-store";
import { Button } from "./ui/button";
import { Select } from "./ui/select";
import { Tip } from "./ui/tooltip";

function sourceListError(raw: string): string {
  if (/Failed to get sources/i.test(raw) && window.tari.platform === "darwin") {
    return "macOS has not granted screen recording to TARI (or to Electron during development). Enable it in System Settings → Privacy & Security → Screen & System Audio Recording, then restart TARI. Video files can still be analyzed.";
  }
  return `Capture sources are unavailable: ${raw.replace(/^Error: Error invoking remote method '[^']+': /, "")}`;
}

export function SourceBar() {
  const capture = useApp((s) => s.capture);
  const engine = useApp((s) => s.engine);
  const ws = useApp((s) => s.ws);
  const session = useApp((s) => s.session);
  const pushNotice = useApp((s) => s.pushNotice);
  const [sources, setSources] = useState<CaptureSourceInfo[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const list = await window.tari.invoke("capture:list-sources", { thumbnails: false });
      const sorted = [...list].sort((a, b) => Number(b.isTrainingLab) - Number(a.isTrainingLab) || a.kind.localeCompare(b.kind) || a.name.localeCompare(b.name));
      setSources(sorted);
      setListError(null);
      setSelected((cur) => (cur && sorted.some((s) => s.id === cur) ? cur : sorted.find((s) => s.isTrainingLab)?.id ?? cur));
    } catch (err) {
      setListError(sourceListError(String(err)));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const running = capture.state === "running" || capture.state === "starting";
  const source = sources.find((s) => s.id === selected);

  async function openLab() {
    const res = await window.tari.invoke("lab:open", undefined);
    if (!res.ok) pushNotice({ level: "error", message: res.reason ?? "Could not open the Training Lab." });
    else setTimeout(() => void refresh(), 900);
  }

  async function start() {
    if (!source) return;
    await runtime.startDesktop(source);
  }

  const engineReady = engine.state === "ready";
  const sessionText = session.id ? "Session live" : running && ws !== "open" ? "Waiting for engine" : running ? "Starting session" : null;

  return (
    <div className="flex h-12 shrink-0 items-center gap-2 border-b border-line px-4">
      <span className="eyebrow mr-1">Source</span>
      {running && capture.source ? (
        <div className="flex h-8 w-80 items-center gap-2 rounded-md border border-line bg-panel px-2.5 text-[13px]">
          {capture.source.kind === "file" ? <Film className="size-3.5 text-fg-muted" /> : <span className="size-1.5 rounded-full bg-accent" />}
          <span className="truncate">{capture.source.label}</span>
        </div>
      ) : listError ? (
        <Tip content={listError}>
          <div className="flex h-8 w-80 items-center gap-2 rounded-md border border-warn/30 bg-warn/5 px-2.5 text-[12.5px] text-warn">
            <ShieldAlert className="size-3.5 shrink-0" />
            <span className="truncate">Screen capture not permitted</span>
          </div>
        </Tip>
      ) : (
        <Select
          width="w-80"
          value={selected}
          onValueChange={setSelected}
          placeholder={loading ? "Loading sources…" : "Choose a window or screen"}
          options={sources.map((s) => ({
            value: s.id,
            label: s.name || (s.kind === "screen" ? "Screen" : "Untitled window"),
            hint: s.isTrainingLab ? "Training Lab · live coaching" : s.looksLikeValorant ? "VALORANT · live coaching disabled (needs Riot authorization)" : s.kind,
          }))}
        />
      )}
      <Tip content="Refresh sources">
        <Button variant="ghost" size="icon" onClick={() => void refresh()} disabled={loading || running} aria-label="Refresh sources">
          <RefreshCw className={loading ? "animate-spin" : ""} />
        </Button>
      </Tip>
      <div className="mx-1 h-5 w-px bg-line" />
      <Button variant="ghost" onClick={() => void openLab()}>
        <FlaskConical /> Open Training Lab
      </Button>
      <Tip content="Analyze a recorded video file (e.g. a Training Lab recording) through the same pipeline">
        <Button variant="ghost" onClick={() => fileInput.current?.click()} disabled={running}>
          <Film /> Video file
        </Button>
      </Tip>
      <input
        ref={fileInput}
        type="file"
        accept="video/*"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (f) void runtime.startFile(f);
        }}
      />
      <div className="ml-auto flex items-center gap-3">
        {sessionText && <span className="text-[12px] text-fg-muted">{sessionText}</span>}
        {capture.error && <span className="max-w-96 truncate text-[12px] text-danger" title={capture.error}>{capture.error}</span>}
        {running ? (
          <Button variant="danger" onClick={() => runtime.stop()}>
            <Square className="fill-current" /> Stop
          </Button>
        ) : (
          <Tip content={!engineReady ? "The engine is not running; capture works but no coaching will be produced." : "Start a coaching session on the selected source"}>
            <Button variant="primary" onClick={() => void start()} disabled={!source || Boolean(listError)}>
              <Play className="fill-current" /> Start session
            </Button>
          </Tip>
        )}
      </div>
    </div>
  );
}
