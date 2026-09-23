#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""合成最終 4K MP4：素材 PNG + narration.wav + subtitle.ass。

場景長度一律取自 timeline.json（旁白實測長度），畫面配合語音，不是反過來。

用法:
  python compose.py --storyboard storyboard.json --audio audio/ --assets assets/ \
                    --out "教學影片/檔名.mp4"
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

W, H, FPS = 3840, 2160, 30
BG = "0x0f172a"
XFADE_SCENE = 0.5          # 場景之間
XFADE_STEP  = 0.3          # 同場景的操作步驟之間
KENBURNS_MIN = 6.0         # 超過此長度的靜態畫面才加運鏡


def run(cmd: list[str], desc: str = "") -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg 失敗 {desc}\n{r.stderr[-1500:]}")


def probe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def scene_images(assets: Path, sid: str) -> list[Path]:
    """s03.png, s03_01.png, s03_02.png ... 依序回傳。"""
    base = assets / f"{sid}.png"
    return ([base] if base.exists() else []) + sorted(assets.glob(f"{sid}_*.png"))


def make_clip(img: Path, dur: float, out: Path, kenburns: bool) -> None:
    """單張圖 -> 指定長度的影片片段。等比縮放後補邊，絕不變形。"""
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={BG}")
    if kenburns and dur >= KENBURNS_MIN:
        frames = max(int(dur * FPS), 1)
        vf += (f",zoompan=z='min(zoom+0.00015,1.08)':d={frames}"
               f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}")
    else:
        vf += f",fps={FPS}"
    vf += ",format=yuv420p,setsar=1"

    run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(img),
         "-t", f"{dur:.3f}", "-vf", vf,
         "-c:v", "libx264", "-preset", "medium", "-crf", "16", str(out)],
        f"(clip {img.name})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--storyboard", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--nvenc", action="store_true", help="用 NVENC 快速產草稿")
    a = ap.parse_args()

    sb = json.loads(Path(a.storyboard).read_text(encoding="utf-8"))
    audio = Path(a.audio)
    assets = Path(a.assets)
    timeline = json.loads((audio / "timeline.json").read_text(encoding="utf-8"))
    durations = {s["id"]: s["duration"] for s in timeline["scenes"]}

    work = Path(a.workdir) if a.workdir else audio.parent / "clips"
    work.mkdir(parents=True, exist_ok=True)

    # ---- 時間補償
    # xfade 把兩段接成 len(a)+len(b)-d，每接一次就吃掉 d 秒畫面，但音訊沒變短。
    # 不補回來的話，每過一個轉場音畫就飄移一次。
    # 片頭/片尾靜音也要有對應畫面，否則結尾旁白會被 -shortest 截掉。
    lead = timeline.get("lead", 0.0)
    tail = max(timeline["total"] - timeline["scenes"][-1]["end"], 0.0)

    todo = [(s, durations[s["id"]]) for s in sb["scenes"]
            if s.get("id") in durations and scene_images(assets, s["id"])]
    if not todo:
        print("錯誤：沒有任何可用場景（檢查素材檔名是否為 <場景id>.png）", file=sys.stderr)
        return 1
    n = len(todo)

    # ---- 攤平成單一片段序列，並記下每個接縫的轉場長度
    clips: list[Path] = []
    trans: list[float] = []            # len(clips) - 1 個

    for idx, (scene, target) in enumerate(todo):
        sid = scene["id"]
        imgs = scene_images(assets, sid)
        m = len(imgs)

        # 本場景所有片段的長度總和：旁白長度 + 被轉場吃掉的部分 + 片頭/片尾靜音
        budget = target + (m - 1) * XFADE_STEP
        if idx == 0:
            budget += lead             # 片頭靜音期間停在第一個畫面
        if idx == n - 1:
            budget += tail             # 片尾靜音期間停在最後一個畫面
        else:
            budget += XFADE_SCENE      # 補回場景轉場會吃掉的長度
        each = budget / m

        for j, im in enumerate(imgs):
            clip = work / f"{sid}_{j:02d}.mp4"
            # 操作畫面不運鏡，觀眾要看清楚 UI；多影格也不運鏡，避免與轉場打架
            make_clip(im, each, clip,
                      kenburns=(m == 1 and scene.get("type") != "screen"))
            if clips:
                trans.append(XFADE_STEP if j > 0 else XFADE_SCENE)
            clips.append(clip)

        print(f"  {sid}: {m} 張 x {each:.2f}s (旁白 {target:.2f}s)")

    # ---- 單一 xfade 鏈：全片只編碼一次，避免逐次接合造成的多代畫質損失
    inputs: list[str] = []
    for c in clips:
        inputs += ["-i", str(c)]

    durs = [probe_duration(c) for c in clips]
    steps, acc, label = [], durs[0], "0:v"
    for i in range(1, len(clips)):
        d = trans[i - 1]
        off = max(acc - d, 0.05)
        steps.append(f"[{label}][{i}:v]xfade=transition=fade:"
                     f"duration={d}:offset={off:.3f}[v{i}]")
        acc = acc + durs[i] - d
        label = f"v{i}"

    a_dur = probe_duration(audio / "narration.wav")
    print(f"  畫面 {acc:.2f}s / 旁白 {a_dur:.2f}s / 差 {abs(acc - a_dur):.2f}s")
    if abs(acc - a_dur) > 0.5:
        print(f"  ! 音畫長度相差 {abs(acc - a_dur):.2f}s，"
              f"結尾旁白可能被截斷（檢查 xfade 補償）", file=sys.stderr)

    # 字幕最後才燒，且必須在縮放之後 —— 否則 180px 會被一起縮放
    ass = (audio / "subtitle.ass").resolve()
    ass_arg = ass.as_posix().replace(":", r"\:")     # 濾鏡參數要跳脫磁碟機冒號
    steps.append(f"[{label}]ass='{ass_arg}'[vout]")
    filter_complex = ";".join(steps)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    vcodec = (["-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "20", "-b:v", "0"]
              if a.nvenc else
              ["-c:v", "libx264", "-preset", "slow", "-crf", "18",
               "-x264-params", "keyint=60:min-keyint=30"])

    run(["ffmpeg", "-y", "-v", "error",
         *inputs, "-i", str(audio / "narration.wav"),
         "-filter_complex", filter_complex,
         "-map", "[vout]", "-map", f"{len(clips)}:a:0",
         *vcodec,
         "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "5.1",
         "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-movflags", "+faststart", "-shortest", str(out)],
        "(final)")

    # ---- 附上 SRT
    srt_src = audio / "subtitle.srt"
    if srt_src.exists():
        (out.parent / f"{out.stem}.srt").write_text(
            srt_src.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")

    # ---- 驗證
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,codec_name,pix_fmt",
         "-of", "default=nw=1", str(out)], capture_output=True, text=True)
    info = dict(l.split("=", 1) for l in r.stdout.strip().splitlines() if "=" in l)
    ok = info.get("width") == "3840" and info.get("height") == "2160"
    size_mb = out.stat().st_size / 1024 / 1024

    print(f"\n{'完成' if ok else '尺寸不符 !!'}  {out}")
    print(f"  {info.get('width')}x{info.get('height')} {info.get('codec_name')} "
          f"{info.get('pix_fmt')} / {probe_duration(out):.1f}s / {size_mb:.1f} MB")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
