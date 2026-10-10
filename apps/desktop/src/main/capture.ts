/**
 * Capture source enumeration and selection.
 *
 * On Windows, Chromium's desktop capturer can use Windows.Graphics.Capture;
 * which backend it uses depends on the Chromium build and feature flags and is
 * not verified by this project. A native WGC service (services/capture) is the
 * planned dedicated backend.
 */
import { desktopCapturer, session, type DesktopCapturerSource } from "electron";
import type { CaptureSourceInfo } from "../shared/ipc";
import { TRAINING_LAB_TITLE } from "../shared/ipc";
import { log } from "./logger";

let selectedId: string | null = null;

export async function listSources(thumbnails: boolean): Promise<CaptureSourceInfo[]> {
  const sources = await desktopCapturer.getSources({
    types: ["screen", "window"],
    thumbnailSize: thumbnails ? { width: 320, height: 180 } : { width: 0, height: 0 },
    fetchWindowIcons: thumbnails,
  });
  return sources.map(toInfo);
}

function toInfo(s: DesktopCapturerSource): CaptureSourceInfo {
  const thumb = s.thumbnail && !s.thumbnail.isEmpty() ? s.thumbnail.toDataURL() : null;
  const icon = s.appIcon && !s.appIcon.isEmpty() ? s.appIcon.toDataURL() : null;
  return {
    id: s.id,
    name: s.name,
    kind: s.id.startsWith("screen:") ? "screen" : "window",
    thumbnail: thumb,
    appIcon: icon,
    isTrainingLab: s.name.includes(TRAINING_LAB_TITLE),
    looksLikeValorant: /valorant/i.test(s.name),
  };
}

export async function selectSource(id: string): Promise<{ ok: boolean; reason?: string }> {
  const sources = await desktopCapturer.getSources({ types: ["screen", "window"], thumbnailSize: { width: 0, height: 0 } });
  if (!sources.some((s) => s.id === id)) return { ok: false, reason: "Source no longer available." };
  selectedId = id;
  return { ok: true };
}

/** Route renderer getDisplayMedia() calls to the source the user picked in TARI. */
export function installDisplayMediaHandler(): void {
  session.defaultSession.setDisplayMediaRequestHandler(
    (_request, callback) => {
      void (async () => {
        try {
          const sources = await desktopCapturer.getSources({ types: ["screen", "window"], thumbnailSize: { width: 0, height: 0 } });
          const source = sources.find((s) => s.id === selectedId);
          if (!source) {
            log("warn", "display media request without a selected source");
            callback({});
            return;
          }
          callback({ video: source });
        } catch (err) {
          log("error", "display media handler failed", { error: String(err) });
          callback({});
        }
      })();
    },
    { useSystemPicker: false },
  );
}
