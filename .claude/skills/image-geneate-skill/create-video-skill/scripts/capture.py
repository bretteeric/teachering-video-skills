#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""以 Playwright 擷取實際操作畫面 —— 輸出 3840x2160 PNG。

關鍵：viewport 1920x1080 + device_scale_factor=2。
直接開 3840 viewport 會讓所有元素小到看不清，且文字不是 2 倍密度渲染。

用法:
  python capture.py --storyboard storyboard.json --outdir assets/
  python capture.py --storyboard storyboard.json --outdir assets/ --scene s03
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

W, H = 3840, 2160
ACCENT = "#B04A32"          # 與字幕同色，全片視覺一致

FOCUS_JS = """(sel) => {
  const el = document.querySelector(sel);
  if (!el) return false;
  const r = el.getBoundingClientRect();
  const box = document.createElement('div');
  box.id = '__focus__';
  Object.assign(box.style, {
    position: 'fixed',
    left: (r.left - 8) + 'px', top: (r.top - 8) + 'px',
    width: (r.width + 16) + 'px', height: (r.height + 16) + 'px',
    border: '6px solid %s', borderRadius: '12px',
    boxShadow: '0 0 0 9999px rgba(0,0,0,.45)',
    pointerEvents: 'none', zIndex: '2147483647',
  });
  document.body.appendChild(box);
  return true;
}""" % ACCENT

CLEAR_JS = "() => document.getElementById('__focus__')?.remove()"


def shot(page, path: Path) -> None:
    page.wait_for_timeout(350)                       # 等 transition / Vue 掛載
    page.screenshot(path=str(path), scale="device")  # 不加會輸出 1920x1080
    print(f"    -> {path.name}")


def run_steps(page, scene: dict, outdir: Path, sid: str) -> int:
    n = 0

    def nxt() -> Path:
        nonlocal n
        p = outdir / (f"{sid}.png" if n == 0 else f"{sid}_{n:02d}.png")
        n += 1
        return p

    if scene.get("url"):
        page.goto(scene["url"], wait_until="networkidle")
        shot(page, nxt())

    for st in scene.get("steps", []):
        act = st.get("action")
        sel = st.get("selector")
        try:
            if act == "goto":
                page.goto(st["url"], wait_until="networkidle")
            elif act == "click":
                if st.get("highlight") and page.evaluate(FOCUS_JS, sel):
                    shot(page, nxt())
                    page.evaluate(CLEAR_JS)
                page.click(sel)
                page.wait_for_timeout(st.get("wait", 500))
            elif act == "type":
                page.click(sel)
                page.fill(sel, "")
                page.type(sel, st["text"], delay=60)   # 逐字，較像真人操作
            elif act == "select":
                page.select_option(sel, st["value"])
            elif act == "zoom":
                # 放大整頁：原始 JSON 回應這類純文字頁面在 1920 版面下字太小，
                # 縮到 4K 畫面裡讀不到。換頁後 zoom 會自然失效，不需還原。
                page.evaluate("(z) => { document.body.style.zoom = z; }",
                              str(st.get("value", 2)))
            elif act == "hover":
                page.hover(sel)
            elif act == "scroll":
                page.locator(sel).scroll_into_view_if_needed()
            elif act == "wait":
                page.wait_for_selector(sel) if sel else page.wait_for_timeout(st.get("ms", 800))
            elif act == "shot":
                pass
            else:
                print(f"    ! 未知動作 {act}，略過", file=sys.stderr)
                continue
        except Exception as e:
            print(f"    ! 步驟 {act} {sel} 失敗: {e}", file=sys.stderr)
            raise
        # 預設每個 step 都留一張關鍵影格；"shot": false 可略過。
        # 用途：goto 到原始 JSON 這類頁面時，zoom 之前那張字太小、畫面幾乎全空，
        # 留著會變成十幾秒的空畫面，不如只保留放大後的那張。
        if st.get("shot", True):
            shot(page, nxt())

    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--storyboard", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--scene", help="只擷取指定場景 id")
    ap.add_argument("--headed", action="store_true", help="顯示瀏覽器視窗以便除錯")
    a = ap.parse_args()

    sb = json.loads(Path(a.storyboard).read_text(encoding="utf-8"))
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    scenes = [s for s in sb["scenes"] if s.get("type") == "screen"
              and (not a.scene or s.get("id") == a.scene)]
    if not scenes:
        print("沒有 screen 類型的場景，不需擷取")
        return 0

    total = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not a.headed)
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2,                 # 1920*2 = 3840 -> 真 4K 銳利度
            locale="zh-TW",
            reduced_motion="reduce",               # 關掉動畫，截圖才穩定
            # 深色主視覺的專案在 storyboard 設 "color_scheme": "dark"，
            # 瀏覽器內建頁面（原始 JSON 檢視、錯誤頁）才不會是刺眼的白底。
            # 預設留 light，淺色版面的網站才不會被意外翻成深色。
            color_scheme=sb.get("color_scheme", "light"),
        )
        page = ctx.new_page()

        if sb.get("login"):                        # 需登入的頁面先登入，cookie 會保留
            lg = sb["login"]
            page.goto(lg["url"], wait_until="networkidle")
            page.fill(lg["user_selector"], lg["username"])
            page.fill(lg["pass_selector"], lg["password"])
            page.click(lg["submit_selector"])
            page.wait_for_load_state("networkidle")
            print("  已登入")

        for scene in scenes:
            sid = scene.get("id")
            print(f"  {sid}:")
            total += run_steps(page, scene, outdir, sid)

        browser.close()

    # 尺寸驗證
    try:
        from PIL import Image
        for f in sorted(outdir.glob("*.png")):
            w, h = Image.open(f).size
            if (w, h) != (W, H):
                print(f"  ! {f.name} 是 {w}x{h}，應為 {W}x{H}"
                      f"（檢查 device_scale_factor 與 scale='device'）", file=sys.stderr)
    except ImportError:
        pass

    print(f"\n完成 {total} 張擷取")
    return 0


if __name__ == "__main__":
    sys.exit(main())
