#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""交付前自動驗收。能用程式驗的全部在這裡驗；聽感仍要人判斷。

檢查項：
  video      3840x2160 / h264 / yuv420p / aac 48kHz，音畫長度差 ≤ 0.5 秒
  pop        首尾樣本為 0、首尾 0.25 秒近乎靜音、全片峰值 ≤ -1.0 dBFS
  subtitle   ASS 樣式（180px、#B04A32、JhengHei、粗體），字幕與旁白逐字一致，單行 ≤ 18 字
  zh-TW      無簡體字殘留
  secrets    旁白、字幕、擷取網址不含金鑰、密碼、設定檔頁面
  pacing     每個 screen 場景 < 15 秒（screen 不運鏡，太長就是靜止畫面）
  coverage   features.json 每一項都有 screen 場景示範，或列在 exclusions 並附理由
  clean      工作目錄沒有 Chromium 留下的 debug.log

用法:
  python qa.py --video "教學影片/X.mp4" --storyboard sb.json --audio audio/ \
               --features inventory/features.json --workspace .
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from array import array
import sys
from pathlib import Path

# 只收簡體專有字。「限」「計」「里」（公里）「准」（批准）繁體也在用，
# 放進來會誤報，誘使人把正確的字改掉。
SIMPLIFIED = re.compile("[这个说话学习实现验证网络数据设备权统么为对开关样点问题华应产业务"
                        "们时间发现区图进无该让还从动态库档标输页码认运维]")
SECRET = re.compile(r"apikey_|api[_-]?key\s*[:=]|password\s*=|pwd\s*=|user id=sa|\bsk-[A-Za-z0-9]{8,}"
                    r"|bearer\s+[A-Za-z0-9._-]{20,}", re.I)
# 只查擷取網址：旁白講「金鑰放在 appsettings.Development.json」是正常教學內容，不是外洩
CONFIG_URL = re.compile(r"appsettings|connectionstring|\.env\b|web\.config", re.I)
PUNCT = re.compile(r"[，。、；：？！,.!?\s]")

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def probe(path: Path, stream: str, entries: str) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", stream,
                        "-show_entries", entries, "-of", "default=nw=1", str(path)],
                       capture_output=True, text=True)
    return dict(l.split("=", 1) for l in r.stdout.splitlines() if "=" in l)


def duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def qa_video(mp4: Path) -> None:
    v = probe(mp4, "v:0", "stream=width,height,codec_name,pix_fmt")
    check("video 4K", v.get("width") == "3840" and v.get("height") == "2160",
          f"{v.get('width')}x{v.get('height')}")
    check("video h264/yuv420p", v.get("codec_name") == "h264" and v.get("pix_fmt") == "yuv420p",
          f"{v.get('codec_name')} {v.get('pix_fmt')}")
    a = probe(mp4, "a:0", "stream=codec_name,sample_rate")
    check("audio aac 48k", a.get("codec_name") == "aac" and a.get("sample_rate") == "48000",
          f"{a.get('codec_name')} {a.get('sample_rate')}")

    vd = float(probe(mp4, "v:0", "stream=duration").get("duration", 0) or 0)
    ad = float(probe(mp4, "a:0", "stream=duration").get("duration", 0) or 0)
    check("音畫長度", abs(vd - ad) <= 0.5, f"畫面 {vd:.2f}s / 聲音 {ad:.2f}s")

    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp4), "-f", "s16le", "-ac", "1",
                          "-ar", "48000", "-"], capture_output=True).stdout
    # array 而非 struct.unpack：15 分鐘影片約 4300 萬樣本，tuple 會吃掉 1.5 GB 記憶體
    d = array("h", raw[:len(raw)//2*2])
    w = 12000                                        # 0.25 秒；片頭靜音設計值 0.3 秒
    head, tail = max(map(abs, d[:w])), max(map(abs, d[-w:]))
    peak = max(map(abs, d)) or 1
    db = 20 * math.log10(peak / 32768)
    # AAC 編碼會留極小的量化雜訊，首尾 ≤ 64（約 -54 dBFS）視為靜音
    check("首尾無爆音", head <= 64 and tail <= 64 and abs(d[0]) <= 64 and abs(d[-1]) <= 64,
          f"head {head} / tail {tail} / first {d[0]} / last {d[-1]}")
    check("峰值 ≤ -1.0 dBFS", db <= -1.0, f"{db:.2f} dBFS")


def qa_subtitle(audio: Path) -> None:
    ass = (audio / "subtitle.ass").read_bytes()
    check("ASS 無 BOM", not ass.startswith(b"\xef\xbb\xbf"))
    txt = ass.decode("utf-8")
    style = re.search(r"^Style: TW,([^,]+),(\d+),(&H\w+),.*?,(-?\d),", txt, re.M)
    check("字幕樣式", bool(style) and style.group(1) == "Microsoft JhengHei"
          and style.group(2) == "180" and style.group(3).upper() == "&H00324AB0"
          and style.group(4) == "-1",
          style.group(0)[:70] if style else "找不到 Style: TW")
    check("PlayRes 3840x2160", "PlayResX: 3840" in txt and "PlayResY: 2160" in txt)

    cues = [l.split(",", 9)[9] for l in txt.splitlines() if l.startswith("Dialogue:")]
    narr = (audio / "narration.txt").read_text(encoding="utf-8")
    same = PUNCT.sub("", "".join(cues)) == PUNCT.sub("", narr)
    check("字幕與旁白逐字一致", same, f"{len(cues)} 個 cue")
    long = [c for c in cues if len(c) > 18]
    check("單行 ≤ 18 字", not long, "；".join(long[:3]))
    bad = [l for l in narr.splitlines() if SIMPLIFIED.search(l)]
    check("無簡體字", not bad, "；".join(f"{l[:20]}…[{''.join(SIMPLIFIED.findall(l))}]"
                                      for l in bad[:3]))


def qa_storyboard(sb: dict, audio: Path, features: dict | None) -> None:
    text = json.dumps(sb, ensure_ascii=False)
    urls = re.findall(r'"url":\s*"([^"]+)"', text)
    leaks = [m.group(0) for m in SECRET.finditer(
        "\n".join(" ".join(s.get("narration", [])) for s in sb["scenes"]) + "\n" + "\n".join(urls))]
    leaks += [m.group(0) for m in CONFIG_URL.finditer("\n".join(urls))]
    check("無金鑰／密碼／設定檔頁", not leaks, "、".join(sorted(set(leaks))[:5]))

    tl = json.loads((audio / "timeline.json").read_text(encoding="utf-8"))
    dur = {s["id"]: s["duration"] for s in tl["scenes"]}
    slow = [f"{s['id']} {dur[s['id']]:.1f}s" for s in sb["scenes"]
            if s.get("type") == "screen" and dur.get(s["id"], 0) >= 15]
    check("screen 場景 < 15 秒", not slow, "、".join(slow))
    static_long = [f"{s['id']} {dur[s['id']]:.1f}s" for s in sb["scenes"]
                   if s.get("type") != "screen" and dur.get(s["id"], 0) >= 40]
    check("圖解／重點卡 < 40 秒", not static_long, "、".join(static_long))

    if features is None:
        check("功能覆蓋", False, "沒有提供 --features，無法驗證「操作所有功能」")
        return
    shown = {s.get("feature") for s in sb["scenes"] if s.get("type") == "screen"}
    shown |= {f for s in sb["scenes"] for f in s.get("features", [])}
    excluded = {e["feature"]: e.get("reason", "") for e in sb.get("exclusions", [])}
    no_reason = [k for k, v in excluded.items() if not v.strip()]
    missing = [f"{f['id']} {f['name']}" for f in features["features"]
               if f["id"] not in shown and f["id"] not in excluded]
    total = len(features["features"])
    check("功能覆蓋", not missing and not no_reason,
          f"示範 {len(shown & {f['id'] for f in features['features']})}/{total}，"
          f"排除 {len(excluded)}"
          + (f"；未涵蓋：{'、'.join(missing[:8])}" if missing else "")
          + (f"；排除未附理由：{'、'.join(no_reason)}" if no_reason else ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--storyboard", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--features")
    ap.add_argument("--workspace", default=".")
    a = ap.parse_args()

    mp4, audio = Path(a.video), Path(a.audio)
    sb = json.loads(Path(a.storyboard).read_text(encoding="utf-8"))
    feats = json.loads(Path(a.features).read_text(encoding="utf-8")) if a.features else None

    check("輸出位置", mp4.exists() and mp4.parent.name == "教學影片", str(mp4))
    if mp4.exists():
        qa_video(mp4)
        srt = mp4.with_suffix(".srt")
        check("附 SRT（無 BOM）", srt.exists() and not srt.read_bytes().startswith(b"\xef\xbb\xbf"))
    qa_subtitle(audio)
    qa_storyboard(sb, audio, feats)

    ws = Path(a.workspace)
    logs = [str(p) for p in (ws / "debug.log", Path.cwd() / "debug.log") if p.exists()]
    check("無 debug.log 殘留", not logs, "、".join(sorted(set(logs))))

    width = max(len(n) for n, _, _ in results)
    fails = 0
    for name, ok, detail in results:
        fails += not ok
        print(f"  {'✓' if ok else '✗'} {name.ljust(width)}  {detail}")
    print(f"\n{'全部通過' if not fails else f'{fails} 項未通過'}（聽感、畫面正確性仍需人工確認）")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
