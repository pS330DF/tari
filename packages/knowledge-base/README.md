# Knowledge base

Versioned data shared across components.

- `environments/training-lab-v1.json` — the Training Lab's visual contract: ArUco
  fiducial bits, HUD layout (drill/ammo/timer seven-segment readouts in marker
  units), palette, crosshair geometry, target colors, camera FOV, drill codes.
  The Lab renders from it and the perception engine parses frames with it.
  Regenerate with `pnpm gen:lab-profile`.

Agent, ability and map data for VALORANT coaching are not included yet.
