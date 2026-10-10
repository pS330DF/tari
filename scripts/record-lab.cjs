/**
 * Record the real Training Lab (Chromium + WebGL) offscreen, in lockstep, with
 * exact per-frame ground truth. Needs no screen-capture permission because it
 * captures the Lab's own web contents.
 *
 *   electron scripts/record-lab.cjs --preset angle_hold_low --frames 450 --out /tmp/lab
 *
 * Output: frame_00000.png ... + gt.jsonl (+ meta.json)
 */
const { app, BrowserWindow } = require("electron");
const fs = require("node:fs");
const path = require("node:path");

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

const preset = arg("preset", "angle_hold_low");
const frames = Number(arg("frames", "450"));
const width = Number(arg("width", "1280"));
const height = Number(arg("height", "720"));
const seed = arg("seed", "7");
const out = path.resolve(arg("out", path.join(process.cwd(), "lab-recording")));
const labIndex = path.resolve(__dirname, "..", "apps", "training-lab", "dist", "index.html");

app.commandLine.appendSwitch("force-device-scale-factor", "1");

app.whenReady().then(async () => {
  try {
    if (!fs.existsSync(labIndex)) throw new Error(`Lab not built: ${labIndex} (run pnpm build:lab)`);
    fs.mkdirSync(out, { recursive: true });
    const win = new BrowserWindow({
      show: false,
      width,
      height,
      useContentSize: true,
      frame: false,
      webPreferences: { offscreen: true, backgroundThrottling: false },
    });
    win.webContents.setFrameRate(60);
    await win.loadFile(labIndex, { query: { autotest: preset, seed } });
    await win.webContents.executeJavaScript("new Promise(r => { const t = () => window.__tariLab ? r() : setTimeout(t, 20); t(); })");
    const gt = fs.createWriteStream(path.join(out, "gt.jsonl"));
    const t0 = Date.now();
    let n = 0;
    for (; n < frames; n++) {
      const truth = await win.webContents.executeJavaScript("window.__tariLab.advance()");
      const image = await win.webContents.capturePage();
      const size = image.getSize();
      fs.writeFileSync(path.join(out, `frame_${String(n).padStart(5, "0")}.png`), image.toPNG());
      gt.write(JSON.stringify({ ...truth, image_size: size }) + "\n");
      if (await win.webContents.executeJavaScript("window.__tariLab.done")) break;
    }
    gt.end();
    const config = await win.webContents.executeJavaScript("window.__tariLab.config");
    fs.writeFileSync(path.join(out, "meta.json"), JSON.stringify({ preset, seed, frames: n, width, height, config, recorded_s: (Date.now() - t0) / 1000 }, null, 2));
    console.log(JSON.stringify({ ok: true, out, frames: n, seconds: (Date.now() - t0) / 1000 }));
  } catch (err) {
    console.error(JSON.stringify({ ok: false, error: String(err && err.stack || err) }));
    process.exitCode = 1;
  } finally {
    app.quit();
  }
});
