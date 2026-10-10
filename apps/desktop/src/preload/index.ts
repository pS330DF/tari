/** Preload: exposes a narrow, typed API. Channel names are allow-listed. */
import { contextBridge, ipcRenderer, type IpcRendererEvent } from "electron";
import type { IpcContract, IpcEvents, IpcSends } from "../shared/ipc";

const INVOKE = new Set<keyof IpcContract>([
  "settings:get", "settings:set", "capture:list-sources", "capture:select", "engine:status", "engine:restart",
  "lab:open", "companion:set-visible", "system:metrics", "app:info", "e2e:config", "e2e:report", "e2e:screenshot",
]);
const EVENTS = new Set<keyof IpcEvents>(["engine:status-changed", "settings:changed", "notice", "companion:update", "companion:visibility"]);
const SENDS = new Set<keyof IpcSends>(["companion:publish"]);

const api = {
  invoke<C extends keyof IpcContract>(channel: C, req: IpcContract[C]["req"]): Promise<IpcContract[C]["res"]> {
    if (!INVOKE.has(channel)) return Promise.reject(new Error(`channel not allowed: ${channel}`));
    return ipcRenderer.invoke(channel, req);
  },
  on<E extends keyof IpcEvents>(event: E, cb: (payload: IpcEvents[E]) => void): () => void {
    if (!EVENTS.has(event)) throw new Error(`event not allowed: ${event}`);
    const handler = (_e: IpcRendererEvent, payload: IpcEvents[E]) => cb(payload);
    ipcRenderer.on(event, handler);
    return () => ipcRenderer.removeListener(event, handler);
  },
  send<S extends keyof IpcSends>(channel: S, payload: IpcSends[S]): void {
    if (!SENDS.has(channel)) throw new Error(`send not allowed: ${channel}`);
    ipcRenderer.send(channel, payload);
  },
  platform: process.platform,
};

export type TariApi = typeof api;
contextBridge.exposeInMainWorld("tari", api);
