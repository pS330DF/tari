import { describe, expect, it } from "vitest";
import { crosshairArms, drawCluster, markerOrigin, markerSize, type Ctx2D } from "../src/hud";
import { profile } from "../src/profile";
import { seeded } from "../src/autotest";

interface Rect { x: number; y: number; w: number; h: number; color: string }

function recorder(): { ctx: Ctx2D; rects: Rect[] } {
  const rects: Rect[] = [];
  const ctx = {
    fillStyle: "#000000",
    font: "",
    textAlign: "left",
    textBaseline: "top",
    fillRect(x: number, y: number, w: number, h: number) {
      rects.push({ x, y, w, h, color: String(this.fillStyle) });
    },
    fillText() {},
    clearRect() {},
    setTransform() {},
  } as Ctx2D;
  return { ctx, rects };
}

describe("HUD cluster follows the shared profile", () => {
  it("anchors the marker bottom-left and scales with the viewport", () => {
    expect(markerSize(720)).toBe(72);
    expect(markerSize(1440)).toBeCloseTo(108);
    const o = markerOrigin(1080);
    const f = profile.hud.fiducial_frame;
    expect(o.x).toBeCloseTo(profile.fiducial.margin_css_px - f[0] * o.M);
    expect(o.y + (f[1] + f[3]) * o.M).toBeCloseTo(1080 - profile.fiducial.margin_css_px);
  });

  it("draws the ArUco bits exactly", () => {
    const { ctx, rects } = recorder();
    drawCluster(ctx, 1080, { drill: 1, ammo: 25, timer: 60, crosshairColor: "#00f0ff", movementError: 0, showCluster: true });
    const { x, y, M } = markerOrigin(1080);
    const cell = M / profile.fiducial.cells;
    profile.fiducial.bits.forEach((row, j) =>
      row.forEach((bit, i) => {
        const r = rects.find((q) => q.x === Math.round(x + i * cell) && q.y === Math.round(y + j * cell) && (q.color === "#ffffff" || q.color === "#000000"));
        expect(r?.color).toBe(bit ? "#ffffff" : "#000000");
      }),
    );
  });

  it("lights exactly the pattern segments for each digit", () => {
    const { ctx, rects } = recorder();
    drawCluster(ctx, 1080, { drill: 2, ammo: 7, timer: 589, crosshairColor: "#00f0ff", movementError: 0, showCluster: true });
    const lit = rects.filter((r) => r.color === profile.hud.colors.lit).length;
    const expected = ["2", "0", "7", "5", "8", "9"].reduce((n, d) => n + profile.hud.digit_patterns[d]!.length, 0);
    expect(lit).toBe(expected);
    const segments = Object.keys(profile.hud.segments).length;
    expect(rects.filter((r) => r.color === profile.hud.colors.unlit).length).toBe(6 * segments - expected);
  });

  it("blank readouts draw unlit segments only (perception reads them as unreadable)", () => {
    const { ctx, rects } = recorder();
    drawCluster(ctx, 1080, { drill: null, ammo: null, timer: null, crosshairColor: "#00f0ff", movementError: 0, showCluster: true });
    expect(rects.filter((r) => r.color === profile.hud.colors.lit).length).toBe(0);
  });
});

describe("crosshair", () => {
  it("matches the synthetic renderer geometry and widens with movement error", () => {
    const arms = crosshairArms(640, 360, 0);
    expect(arms[0]).toEqual([640 - 4 - 7, 359, 7, 2]);
    expect(arms[1]).toEqual([644, 359, 7, 2]);
    const moving = crosshairArms(640, 360, 1);
    expect(moving[1]![0]).toBe(640 + 4 + profile.crosshair.movement_error_max_css_px);
    expect(crosshairArms(640, 360, 5)).toEqual(moving); // clamped
  });
});

describe("autotest RNG", () => {
  it("is deterministic per seed", () => {
    const a = seeded(7);
    const b = seeded(7);
    const c = seeded(8);
    const sa = [a(), a(), a()];
    expect([b(), b(), b()]).toEqual(sa);
    expect(c()).not.toBe(sa[0]);
    expect(sa.every((v) => v >= 0 && v < 1)).toBe(true);
  });
});
