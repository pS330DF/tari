"""Encode a record-lab.cjs PNG sequence into the regression dataset layout (VP9 WebM + GT)."""

import shutil
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    dst.mkdir(parents=True, exist_ok=True)
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-framerate", "30",
                    "-i", str(src / "frame_%05d.png"), "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-crf", "22",
                    "-b:v", "0", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4", str(dst / "recording.webm")],
                   check=True)
    for name in ("gt.jsonl", "meta.json"):
        shutil.copy(src / name, dst / name)
    print(f"wrote {dst}")


if __name__ == "__main__":
    main()
