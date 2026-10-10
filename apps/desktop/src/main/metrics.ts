/** Process resource usage for the telemetry panel. GPU utilization is not exposed by Electron. */
import { app } from "electron";
import type { SystemMetrics } from "../shared/ipc";

export function systemMetrics(): SystemMetrics {
  const processes = app.getAppMetrics().map((m) => ({
    type: m.type,
    cpuPercent: Math.round(m.cpu.percentCPUUsage * 10) / 10,
    memoryMB: Math.round((m.memory.workingSetSize / 1024) * 10) / 10,
  }));
  const status = app.getGPUFeatureStatus();
  const accel = status.gpu_compositing?.startsWith("enabled") ? "hardware compositing on" : `compositing: ${status.gpu_compositing}`;
  return {
    ts: Date.now(),
    processes,
    totalCpuPercent: Math.round(processes.reduce((s, p) => s + p.cpuPercent, 0) * 10) / 10,
    totalMemoryMB: Math.round(processes.reduce((s, p) => s + p.memoryMB, 0)),
    gpu: { status: "utilization unavailable", detail: `${accel}; Electron does not report GPU utilization` },
  };
}
