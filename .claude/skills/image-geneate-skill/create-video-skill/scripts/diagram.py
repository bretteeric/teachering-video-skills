#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""產生場景素材：mermaid 圖解、標題卡、重點卡 —— 一律輸出 3840x2160 PNG。

用法:
  python diagram.py --storyboard storyboard.json --outdir assets/
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 3840, 2160
BG_TOP, BG_BOTTOM = (15, 23, 42), (30, 41, 59)      # #0f172a -> #1e293b
ACCENT = (176, 74, 50)                              # #B04A32 紅棕色
FG, FG_DIM = (241, 245, 249), (148, 163, 184)
SUBTITLE_SAFE = 400                                 # 底部保留給字幕

FONT_BOLD = r"C:\Windows\Fonts\msjhbd.ttc"
FONT_REG  = r"C:\Windows\Fonts\msjh.ttc"

MERMAID_THEME = (
    "%%{init: {'theme':'dark', 'themeVariables': {"
    "'primaryColor':'#1e293b','primaryTextColor':'#e2e8f0',"
    "'primaryBorderColor':'#B04A32','lineColor':'#94a3b8',"
    "'secondaryColor':'#334155','tertiaryColor':'#0f172a',"
    "'fontFamily':'Microsoft JhengHei','fontSize':'28px'}}}%%\n"
)


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype(r"C:\Windows\Fonts\NotoSansTC-VF.ttf", size)


def gradient_bg() -> Image.Image:
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(
            int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)))
    return img


def centered(d: ImageDraw.ImageDraw, text: str, f, y: int, fill) -> None:
    w = d.textlength(text, font=f)
    d.text(((W - w) / 2, y), text, font=f, fill=fill)


def make_title(scene: dict, out: Path) -> None:
    img = gradient_bg()
    d = ImageDraw.Draw(img)
    heading = scene.get("heading", scene.get("title", ""))
    sub = scene.get("subheading", "")

    f_h, f_s = font(FONT_BOLD, 200), font(FONT_REG, 110)
    y = H // 2 - (200 if sub else 120)
    centered(d, heading, f_h, y, FG)
    # 紅棕色底線，與字幕同色系，全片視覺一致
    lw = min(int(d.textlength(heading, font=f_h)), W - 400)
    d.rectangle([(W - lw) / 2, y + 270, (W + lw) / 2, y + 282], fill=ACCENT)
    if sub:
        centered(d, sub, f_s, y + 360, FG_DIM)
    img.save(out)


def make_slide(scene: dict, out: Path) -> None:
    img = gradient_bg()
    d = ImageDraw.Draw(img)
    heading = scene.get("heading", "")
    bullets = scene.get("bullets", [])[:4]          # 每頁最多 4 條

    f_h, f_b = font(FONT_BOLD, 150), font(FONT_REG, 100)
    y = 260
    if heading:
        d.text((320, y), heading, font=f_h, fill=FG)
        d.rectangle([320, y + 200, 320 + min(int(d.textlength(heading, font=f_h)), 2400),
                     y + 210], fill=ACCENT)
        y += 340

    avail = H - SUBTITLE_SAFE - y
    step = min(200, avail // max(len(bullets), 1))
    for b in bullets:
        d.ellipse([330, y + 38, 372, y + 80], fill=ACCENT)
        d.text((430, y), b, font=f_b, fill=FG)
        y += step
    img.save(out)


def make_mermaid(scene: dict, out: Path, sb_dir: Path) -> None:
    """用 mermaid-cli 算圖，再置中貼到 4K 畫布（不拉伸，避免變形）。"""
    src = scene.get("mermaid", "")
    code = (sb_dir / src).read_text(encoding="utf-8") if (sb_dir / src).exists() else src
    if not code.strip():
        raise ValueError(f"場景 {scene.get('id')} 的 mermaid 內容是空的")
    if "%%{init" not in code:
        code = MERMAID_THEME + code

    tmp = Path(tempfile.mkdtemp())
    mmd, png = tmp / "d.mmd", tmp / "d.png"
    mmd.write_text(code, encoding="utf-8", newline="\n")

    # -s 4：mermaid 的 PNG 尺寸取決於圖的內容，不是 -w/-H。
    # 節點少的圖會算得很小，先用高 scale 取得足夠像素，再放大填滿版面。
    # -b transparent：讓圖直接疊在漸層背景上，不會出現一塊突兀的深色方塊。
    r = subprocess.run(
        ["npx", "-y", "@mermaid-js/mermaid-cli", "-i", str(mmd), "-o", str(png),
         "-t", "dark", "-b", "transparent", "-w", "1600", "-H", "900", "-s", "4"],
        capture_output=True, text=True, shell=True)
    if r.returncode != 0 or not png.exists():
        raise RuntimeError(f"mermaid 算圖失敗（場景 {scene.get('id')}）\n{r.stderr[-600:]}")

    canvas = gradient_bg()
    dia = Image.open(png).convert("RGBA")
    box_w, box_h = W - 480, H - SUBTITLE_SAFE - 320

    # 等比縮放填滿可用區域（可放大）。thumbnail() 只會縮小，
    # 用它會讓簡單的圖在 4K 畫面上小得看不清楚。
    k = min(box_w / dia.width, box_h / dia.height)
    k = min(k, 3.0)                                  # 放大上限，避免糊掉
    if abs(k - 1.0) > 0.01:
        dia = dia.resize((max(int(dia.width * k), 1), max(int(dia.height * k), 1)),
                         Image.LANCZOS)
    # 垂直置中要在「標題以下」的區域內，不是整個畫面內。
    # box_h 已經扣掉了標題那 320px，位置卻用整塊高度去置中的話，
    # 圖會往上跑進標題裡——高度剛好用滿時必定相疊（實測：流程圖蓋住標題）。
    head_h = 320 if scene.get("heading") else 0
    canvas.paste(dia, ((W - dia.width) // 2,
                       head_h + (H - SUBTITLE_SAFE - head_h - dia.height) // 2), dia)

    if scene.get("heading"):
        d = ImageDraw.Draw(canvas)
        centered(d, scene["heading"], font(FONT_BOLD, 120), 160, FG)
    canvas.save(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--storyboard", required=True)
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()

    sb_path = Path(a.storyboard)
    sb = json.loads(sb_path.read_text(encoding="utf-8"))
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    made = 0
    for i, scene in enumerate(sb["scenes"]):
        sid = scene.get("id", f"s{i:02d}")
        kind = scene.get("type", "slide")
        if kind == "screen":
            continue                                 # 由 capture.py 負責
        out = outdir / f"{sid}.png"
        if kind == "title":
            make_title(scene, out)
        elif kind == "diagram":
            make_mermaid(scene, out, sb_path.parent)
        else:
            make_slide(scene, out)

        w, h = Image.open(out).size
        assert (w, h) == (W, H), f"{out} 尺寸為 {w}x{h}，應為 {W}x{H}"
        print(f"  {sid} ({kind}) -> {out.name}  {w}x{h}")
        made += 1

    print(f"\n完成 {made} 張素材")
    return 0


if __name__ == "__main__":
    sys.exit(main())
