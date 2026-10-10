/**
 * Live measurement summary for the current session, derived from engine
 * events with the same definitions the engine uses (see docs/metrics.md).
 */
import type { FrameResultMessage } from "@tari/shared-types";

type EngineEvent = FrameResultMessage["events"][number];

export interface MeasuredValue {
  value: number | null;
  samples: number;
  label: string;
  unit: string;
  method: string;
  detail?: string;
}

export interface LiveMeasurements {
  placement: MeasuredValue;
  anglePrep: MeasuredValue;
  acquisition: MeasuredValue;
  overshoot: MeasuredValue;
  undershoot: MeasuredValue;
  unstableShots: MeasuredValue;
  movingShots: MeasuredValue;
  onHeadShots: MeasuredValue;
  exposures: number;
}

const median = (v: number[]): number | null => {
  if (!v.length) return null;
  const s = [...v].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2;
};

export class SessionMetrics {
  private vert: number[] = [];
  private horiz: number[] = [];
  private acq: number[] = [];
  private flicks: string[] = [];
  private shots: { speed: number | null; moving: boolean | null; onHead: boolean | null }[] = [];
  private exposures = 0;

  reset(): void {
    this.vert = [];
    this.horiz = [];
    this.acq = [];
    this.flicks = [];
    this.shots = [];
    this.exposures = 0;
  }

  ingest(events: EngineEvent[]): boolean {
    let changed = false;
    for (const e of events) {
      switch (e.type) {
        case "target_exposed":
          this.exposures++;
          if (e.view_settled && e.confidence >= 0.4) {
            this.vert.push(e.entry_error_deg.y);
            this.horiz.push(Math.abs(e.entry_error_deg.x));
          }
          changed = true;
          break;
        case "target_acquired":
          if (e.confidence >= 0.4) this.acq.push(e.acquisition_ms);
          changed = true;
          break;
        case "flick_analyzed":
          if (e.outcome !== "unresolved") this.flicks.push(e.outcome);
          changed = true;
          break;
        case "shot_fired":
          this.shots.push({ speed: e.view_speed_dps ?? null, moving: e.movement_error ?? null, onHead: e.on_head ?? null });
          changed = true;
          break;
      }
    }
    return changed;
  }

  summary(): LiveMeasurements {
    const timed = this.shots.filter((s) => s.speed !== null);
    const mov = this.shots.filter((s) => s.moving !== null);
    const head = this.shots.filter((s) => s.onHead !== null);
    return {
      exposures: this.exposures,
      placement: {
        value: median(this.vert),
        samples: this.vert.length,
        label: "Head-level placement",
        unit: "°",
        method: "Median vertical angle from crosshair to the estimated head center at each target's first fully visible frame, while the view was held (< 15°/s). Positive = crosshair below head.",
      },
      anglePrep: {
        value: median(this.horiz),
        samples: this.horiz.length,
        label: "Angle preparation",
        unit: "°",
        method: "Median absolute horizontal angle from crosshair to head at the same exposures.",
      },
      acquisition: {
        value: median(this.acq),
        samples: this.acq.length,
        label: "Acquisition time",
        unit: "ms",
        method: "Median time from a target's first detection to the first analyzed frame with the crosshair inside the estimated head radius. Resolution: one analyzed frame.",
      },
      overshoot: {
        value: this.flicks.filter((f) => f === "overshoot").length,
        samples: this.flicks.length,
        label: "Overshoots",
        unit: "flicks",
        method: "Flicks where the crosshair passed the head center by more than the head radius along the flick direction.",
      },
      undershoot: {
        value: this.flicks.filter((f) => f === "undershoot").length,
        samples: this.flicks.length,
        label: "Undershoots",
        unit: "flicks",
        method: "Flicks whose first movement stopped more than a head radius short and needed a second movement.",
      },
      unstableShots: {
        value: timed.filter((s) => (s.speed ?? 0) > 40).length,
        samples: timed.length,
        label: "Shots during view motion",
        unit: "shots",
        method: "Shots (HUD ammo decrements) fired while measured view speed exceeded 40°/s.",
      },
      movingShots: {
        value: mov.filter((s) => s.moving).length,
        samples: mov.length,
        label: "Shots while moving",
        unit: "shots",
        method: "Shots fired while the crosshair showed movement-error spread.",
      },
      onHeadShots: {
        value: head.filter((s) => s.onHead).length,
        samples: head.length,
        label: "Crosshair on head at shot",
        unit: "shots",
        method: "Shots fired with the crosshair inside the estimated head radius of the nearest tracked target. Head position is an estimate; see confidence.",
      },
    };
  }
}
