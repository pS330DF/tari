import type { IpcContract, IpcEvents, IpcSends } from "../shared/ipc";

export interface TariApi {
  invoke<C extends keyof IpcContract>(channel: C, req: IpcContract[C]["req"]): Promise<IpcContract[C]["res"]>;
  on<E extends keyof IpcEvents>(event: E, cb: (payload: IpcEvents[E]) => void): () => void;
  send<S extends keyof IpcSends>(channel: S, payload: IpcSends[S]): void;
  platform: string;
}

declare global {
  interface Window {
    tari: TariApi;
  }
}
