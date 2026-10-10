import { CompanionPanel } from "../components/CompanionPanel";
import { SourceBar } from "../components/SourceBar";
import { TelemetryStrip } from "../components/TelemetryStrip";
import { TrainingViewer } from "../components/TrainingViewer";

export function LiveView() {
  return (
    <div className="flex h-full">
      <div className="flex min-w-0 flex-1 flex-col">
        <SourceBar />
        <TrainingViewer />
        <TelemetryStrip />
      </div>
      <CompanionPanel />
    </div>
  );
}
