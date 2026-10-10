import { Activity, BarChart3, History, Settings as SettingsIcon, X } from "lucide-react";
import { useEffect } from "react";
import { StatusDot } from "./components/ui/badge";
import { TooltipProvider } from "./components/ui/tooltip";
import { TariMark } from "./components/TariMark";
import { cn } from "./lib/utils";
import { useApp, type View } from "./store/app-store";
import { LiveView } from "./views/LiveView";
import { ProfileView } from "./views/ProfileView";
import { SessionsView } from "./views/SessionsView";
import { SettingsView } from "./views/SettingsView";

const NAV: { id: View; label: string; icon: typeof Activity }[] = [
  { id: "live", label: "Live", icon: Activity },
  { id: "sessions", label: "Sessions", icon: History },
  { id: "profile", label: "Progress", icon: BarChart3 },
  { id: "settings", label: "Settings", icon: SettingsIcon },
];

export function App() {
  const view = useApp((s) => s.view);
  const set = useApp((s) => s.set);
  const engine = useApp((s) => s.engine);
  const notices = useApp((s) => s.notices);
  const dismiss = useApp((s) => s.dismissNotice);
  const mac = window.tari.platform === "darwin";

  useEffect(() => {
    const t = setInterval(() => {
      const old = useApp.getState().notices.filter((n) => n.level === "info" && Date.now() - n.ts > 8000);
      old.forEach((n) => dismiss(n.id));
    }, 2000);
    return () => clearInterval(t);
  }, [dismiss]);

  const engineTone = engine.state === "ready" ? "ok" : engine.state === "unavailable" ? "danger" : engine.state === "stopped" ? "idle" : "busy";
  const engineText = { ready: "Engine ready", starting: "Engine starting", restarting: "Engine restarting", unavailable: "Engine unavailable", stopped: "Engine stopped" }[engine.state];

  return (
    <TooltipProvider>
      <div className="flex h-full flex-col">
        <header className={cn("drag flex h-10 shrink-0 items-center border-b border-line bg-bg", mac ? "pl-[78px]" : "pl-3", mac ? "pr-3" : "pr-[150px]")}>
          <div className="flex items-center gap-2 pr-5">
            <TariMark size={17} active={engine.state === "ready"} />
            <span className="text-[13px] font-semibold tracking-[0.18em] text-fg">TARI</span>
          </div>
          <nav className="no-drag flex items-center gap-0.5">
            {NAV.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => set({ view: id })}
                className={cn(
                  "flex h-7 items-center gap-1.5 rounded-md px-2.5 text-[12.5px] font-medium transition-colors",
                  view === id ? "bg-raised text-fg" : "text-fg-muted hover:text-fg",
                )}
              >
                <Icon className="size-3.5" />
                {label}
              </button>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2 text-[12px] text-fg-muted">
            <StatusDot tone={engineTone} />
            <span>{engineText}</span>
            {engine.version && <span className="text-fg-subtle tabular">v{engine.version}</span>}
          </div>
        </header>
        <main className="relative min-h-0 flex-1">
          {view === "live" && <LiveView />}
          {view === "sessions" && <SessionsView />}
          {view === "profile" && <ProfileView />}
          {view === "settings" && <SettingsView />}
          <div className="pointer-events-none absolute right-4 bottom-4 z-40 flex w-[380px] flex-col gap-2">
            {notices.map((n) => (
              <div
                key={n.id}
                className={cn(
                  "fade-in pointer-events-auto flex items-start gap-2 rounded-md border bg-[#101418] px-3 py-2.5 text-[12.5px] shadow-xl shadow-black/40",
                  n.level === "error" ? "border-danger/40" : n.level === "warning" ? "border-warn/35" : "border-line-strong",
                )}
              >
                <span className={cn("mt-1 size-1.5 shrink-0 rounded-full", n.level === "error" ? "bg-danger" : n.level === "warning" ? "bg-warn" : "bg-cyan")} />
                <p className="flex-1 leading-relaxed text-fg">{n.message}</p>
                <button className="text-fg-subtle hover:text-fg" onClick={() => dismiss(n.id)} aria-label="Dismiss">
                  <X className="size-3.5" />
                </button>
              </div>
            ))}
          </div>
        </main>
      </div>
    </TooltipProvider>
  );
}
