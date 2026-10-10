/** The shared visual contract with the perception engine (single source of truth). */
import raw from "../../../packages/knowledge-base/environments/training-lab-v1.json";

export interface Readout {
  x: number;
  y: number;
  digits: number;
  digit_w: number;
  digit_h: number;
  pitch: number;
  label: string;
}

export interface LabProfile {
  id: string;
  fiducial: { bits: number[][]; cells: number; size_css_px: number; size_viewport_fraction: number; margin_css_px: number; marker_id: number };
  hud: {
    fiducial_frame: [number, number, number, number];
    quiet_zone: [number, number, number, number];
    panel: [number, number, number, number];
    colors: Record<"frame" | "quiet" | "panel" | "lit" | "unlit" | "label", string>;
    readouts: Record<"drill" | "ammo" | "timer", Readout>;
    segments: Record<string, [number, number, number, number]>;
    digit_patterns: Record<string, string>;
  };
  drills: Record<string, string>;
  crosshair: { color: string; outline: string; arm_length_css_px: number; thickness_css_px: number; gap_css_px: number; movement_error_max_css_px: number };
  targets: { colors: Record<"red" | "yellow" | "purple", string>; head_radius_m: number; head_center_height_m: number };
  camera: { hfov_deg: number; eye_height_m: number };
}

export const profile = raw as unknown as LabProfile;
export type TargetColor = keyof LabProfile["targets"]["colors"];

export const DRILL_CODES: Record<string, number> = Object.fromEntries(
  Object.entries(profile.drills).map(([code, name]) => [name, Number(code)]),
);
