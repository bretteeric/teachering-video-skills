#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""盤點專案的所有功能 —— 「操作所有功能」要有一份清單才驗得了。

兩個來源合併：
  static  讀原始碼：.NET 的 Controller/Action、Razor Pages、_Layout 選單；Flask 的 route
  live    用瀏覽器實際爬正在執行的網站：選單連結、每頁的表單欄位與按鈕、是否被導去登入

輸出（都放 --out 資料夾）：
  features.json   功能清單，每筆有 id，storyboard 的 screen 場景用 "feature" 對回來
  features.md     給人看的摘要表
  thumbs/*.png    每頁 1920x1080 縮圖，寫分鏡前先看過畫面長什麼樣

用法:
  python inventory.py --project "範例/02_xxx" --url http://localhost:5310 --out "$WORK/inventory"
  python inventory.py ... --login login.json     # 需要登入才看得到的頁面
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

SKIP_DIRS = {"bin", "obj", "node_modules", ".git", ".vs", ".venv", "venv", "wwwroot"}
# 會改變狀態或結束工作階段的連結，爬的時候不要點
DANGER = re.compile(r"logout|signout|log-out|delete|remove|destroy|reset|drop|clear", re.I)
# 靜態資源與原始 API，不算「功能頁」
NOT_PAGE = re.compile(r"\.(css|js|png|jpe?g|gif|svg|ico|pdf|zip|woff2?|map)$|/api/|/swagger", re.I)


# ---------------------------------------------------------------- static

def _files(root: Path, pattern: str):
    for p in root.rglob(pattern):
        if not any(part in SKIP_DIRS for part in p.parts):
            yield p


def scan_dotnet(root: Path) -> dict:
    controllers, pages, nav = [], [], []
    act_re = re.compile(
        r"((?:\[[^\]]+\]\s*)*)public\s+(?:async\s+)?(?:Task<)?(?:IActionResult|ActionResult|"
        r"ViewResult|JsonResult|RedirectResult|IResult|[A-Z]\w*Result)>?\s+(\w+)\s*\(")
    for f in _files(root, "*Controller.cs"):
        src = f.read_text(encoding="utf-8", errors="ignore")
        cls = re.search(r"class\s+(\w+)Controller\b", src)
        if not cls:
            continue
        area = re.search(r'\[Area\("(\w+)"\)\]', src)
        route = re.search(r'\[Route\("([^"]+)"\)\]\s*(?:\[[^\]]+\]\s*)*public\s+(?:sealed\s+)?class', src)
        is_api = "[ApiController]" in src or "ControllerBase" in src.split("class", 1)[-1][:200]
        cls_auth = bool(re.search(r"\[Authorize[^\]]*\]\s*(?:\[[^\]]+\]\s*)*public\s+(?:sealed\s+)?class", src))
        actions = []
        for attrs, name in act_re.findall(src):
            verbs = re.findall(r"Http(Get|Post|Put|Delete|Patch)", attrs)
            actions.append({"name": name, "verbs": verbs or ["Get"],
                            "authorize": cls_auth or "[Authorize" in attrs,
                            "anonymous": "[AllowAnonymous" in attrs})
        controllers.append({"controller": cls.group(1), "area": area.group(1) if area else "",
                            "api": is_api, "route": route.group(1) if route else "",
                            "authorize": cls_auth, "file": str(f.relative_to(root)),
                            "actions": actions})
    for f in _files(root, "*.cshtml"):
        if "Pages" in f.parts:
            head = f.read_text(encoding="utf-8", errors="ignore")[:300]
            if head.lstrip().startswith("@page"):
                pages.append(str(f.relative_to(root)))
    for f in _files(root, "_Layout.cshtml"):
        src = f.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"<a\b([^>]*)>(.*?)</a>", src, re.S):
            attrs, text = m.group(1), re.sub(r"<[^>]+>|\s+", " ", m.group(2)).strip()
            if "brand" in attrs:                      # 站名 logo 連結，與「首頁」重複
                continue
            ctl = re.search(r'asp-controller="(\w+)"', attrs)
            act = re.search(r'asp-action="(\w+)"', attrs)
            area = re.search(r'asp-area="(\w*)"', attrs)
            page = re.search(r'asp-page="([^"]+)"', attrs)
            href = re.search(r'href="([^"#][^"]*)"', attrs)
            if ctl:
                a = area.group(1) if area else ""
                path = "/" + "/".join(x for x in (a, ctl.group(1),
                                                  "" if (act and act.group(1) == "Index") else
                                                  (act.group(1) if act else "")) if x)
            elif page:
                path = page.group(1)
            elif href and not href.group(1).startswith(("http", "~/", "mailto")):
                path = href.group(1)
            else:
                continue
            if text:
                nav.append({"text": text, "path": path, "file": str(f.relative_to(root))})
    return {"kind": "dotnet", "controllers": controllers, "razor_pages": pages, "nav": nav}


def scan_python(root: Path) -> dict:
    routes = []
    pat = re.compile(r"@(\w+)\.(route|get|post|put|delete|patch)\(\s*['\"]([^'\"]+)['\"]"
                     r"(?:[^)]*methods\s*=\s*\[([^\]]*)\])?[^)]*\)\s*(?:@[^\n]+\s*)*def\s+(\w+)")
    for f in _files(root, "*.py"):
        src = f.read_text(encoding="utf-8", errors="ignore")
        for obj, kind, path, methods, fn in pat.findall(src):
            verbs = ([kind.upper()] if kind != "route" else
                     re.findall(r"\w+", methods) or ["GET"])
            routes.append({"path": path, "verbs": verbs, "function": fn,
                           "blueprint": obj, "file": str(f.relative_to(root)),
                           "login_required": False})
    return {"kind": "python", "routes": routes}


# ---------------------------------------------------------------- live

PAGE_JS = r"""() => {
  const cssPath = (el) => {
    if (el.id) return '#' + CSS.escape(el.id);
    if (el.name && el.tagName !== 'BUTTON')
      return `${el.tagName.toLowerCase()}[name="${el.name}"]`;
    const parts = [];
    while (el && el.nodeType === 1 && el !== document.body) {
      if (el.id) { parts.unshift('#' + CSS.escape(el.id)); break; }
      let i = 1, s = el;
      while ((s = s.previousElementSibling)) if (s.tagName === el.tagName) i++;
      parts.unshift(`${el.tagName.toLowerCase()}:nth-of-type(${i})`);
      el = el.parentElement;
    }
    return parts.join(' > ');
  };
  const visible = (el) => { const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  const labelOf = (el) => {
    if (el.id) { const l = document.querySelector(`label[for="${el.id}"]`); if (l) return l.innerText.trim(); }
    const w = el.closest('label'); if (w) return w.innerText.trim();
    return el.getAttribute('aria-label') || el.placeholder || '';
  };
  const fields = [...document.querySelectorAll('input,select,textarea')]
    .filter(e => e.type !== 'hidden' && visible(e))
    .map(e => ({ selector: cssPath(e), tag: e.tagName.toLowerCase(), type: e.type || '',
                 name: e.name || '', label: labelOf(e).slice(0, 40),
                 options: e.tagName === 'SELECT' ? [...e.options].map(o => o.value).slice(0, 12) : undefined }));
  const buttons = [...document.querySelectorAll('button,input[type=submit],a.btn,[role=button]')]
    .filter(visible)
    .map(e => ({ selector: cssPath(e), text: (e.innerText || e.value || '').trim().slice(0, 30) }))
    .filter(b => b.text);
  const links = [...document.querySelectorAll('a[href]')]
    .map(a => ({ href: a.href, text: a.innerText.trim().slice(0, 30), nav: !!a.closest('nav,aside,header,.sidebar,.navbar') }));
  const heads = [...document.querySelectorAll('h1,h2')].map(h => h.innerText.trim()).filter(Boolean).slice(0, 6);
  return { title: document.title, heads, fields, buttons, links,
           tables: document.querySelectorAll('table').length,
           text_len: document.body.innerText.length };
}"""


def settle(page, idle_ms: int = 8000) -> None:
    """等頁面穩定，但不無限等。

    有些頁面載入後會自己持續發請求（例如授權驗證頁逐一打 401/302 探針），
    永遠到不了 networkidle；直接 goto(wait_until="networkidle") 會卡滿 30 秒後失敗。
    """
    try:
        page.wait_for_load_state("networkidle", timeout=idle_ms)
    except Exception:                                 # noqa: BLE001
        pass
    page.wait_for_timeout(300)


def crawl(base: str, out: Path, login: dict | None, max_pages: int, depth: int) -> list[dict]:
    from playwright.sync_api import sync_playwright

    thumbs = out / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    origin = urlparse(base).netloc
    seen: set[str] = set()
    queue: list[tuple[str, int]] = [(base.rstrip("/") + "/", 0)]
    pages: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080},
                                  locale="zh-TW", reduced_motion="reduce")
        page = ctx.new_page()

        if login:
            page.goto(urljoin(base, login["url"]), wait_until="load")
            if login.get("user_selector"):            # 表單登入；沒給選擇器＝開網址就簽發 Cookie（開發用登入）
                page.fill(login["user_selector"], login["username"])
                page.fill(login["pass_selector"], login["password"])
                page.click(login["submit_selector"])
            settle(page)
            print("  已登入")

        while queue and len(pages) < max_pages:
            url, d = queue.pop(0)
            key = url.split("#")[0].rstrip("/").lower()
            if key in seen:
                continue
            seen.add(key)
            try:
                resp = page.goto(url, wait_until="load", timeout=30000)
            except Exception as e:                    # noqa: BLE001 — 單頁失敗不中斷整次盤點
                pages.append({"url": url, "error": str(e)[:200]})
                continue
            settle(page)
            info = page.evaluate(PAGE_JS)
            final = page.url
            to_login = bool(re.search(r"login|signin|account/login", final, re.I)) and \
                not re.search(r"login|signin", url, re.I)
            n = len(pages)
            thumb = thumbs / f"p{n:02d}.png"
            page.screenshot(path=str(thumb))
            path = urlparse(url).path or "/"
            pages.append({"id": f"p{n:02d}", "url": url, "path": path, "final_url": final,
                          "status": resp.status if resp else None,
                          "redirected_to_login": to_login, "thumb": thumb.name,
                          **{k: info[k] for k in ("title", "heads", "fields", "buttons",
                                                  "tables", "text_len")},
                          "nav_links": [l for l in info["links"] if l["nav"]][:40]})
            print(f"  {pages[-1]['id']} {resp.status if resp else '---'} {path}"
                  f"{'  → 登入' if to_login else ''}  {info['title'][:30]}")
            if d >= depth:
                continue
            for l in info["links"]:
                h = l["href"]
                u = urlparse(h)
                if (u.netloc != origin or u.scheme not in ("http", "https")
                        or NOT_PAGE.search(u.path) or DANGER.search(h + " " + l["text"])):
                    continue
                queue.append((h.split("#")[0], d + 1))
        browser.close()
    return pages


# ---------------------------------------------------------------- 合併

def _norm(path: str) -> str:
    p = (path.split("?")[0].rstrip("/") or "/").lower().removesuffix("/index")
    return "/" if p in ("", "/home") else p        # MVC 預設路由：/Home/Index 就是 /


def _page_name(pg: dict) -> str:
    """「首頁 - RagDemo」→「首頁」。版面共用的站名後綴對功能辨識沒有幫助。"""
    t = (pg.get("title") or "").split(" - ")[0].strip()
    return t or (pg.get("heads") or [pg.get("path", "")])[0]


def merge(static: dict, pages: list[dict]) -> list[dict]:
    """一個「功能」= 一個使用者看得到、能操作的頁面。

    以選單項目為主軸（那是使用者心中的功能清單），再補上爬到但不在選單裡的頁面，
    以及原始碼裡有、但選單與爬蟲都沒走到的 Action（常是 POST 或需要參數的頁）。
    """
    feats: list[dict] = []
    by_path = {_norm(p.get("path", "")): p for p in pages if "path" in p}
    used: set[str] = set()

    for n in static.get("nav", []):
        k = _norm(n["path"])
        if k in used:
            continue
        used.add(k)
        pg = by_path.get(k)
        feats.append({"id": f"f{len(feats)+1:02d}", "name": n["text"], "path": n["path"],
                      "source": "nav+live" if pg else "nav",
                      "requires_login": bool(pg and pg.get("redirected_to_login")),
                      "page": pg.get("id") if pg else None,
                      "fields": len(pg.get("fields", [])) if pg else None,
                      "buttons": [b["text"] for b in pg.get("buttons", [])][:10] if pg else []})

    for k, pg in by_path.items():
        if k in used or pg.get("status", 200) >= 400:
            continue
        used.add(k)
        feats.append({"id": f"f{len(feats)+1:02d}", "name": _page_name(pg),
                      "path": pg["path"], "source": "live",
                      "requires_login": pg.get("redirected_to_login", False), "page": pg["id"],
                      "fields": len(pg.get("fields", [])),
                      "buttons": [b["text"] for b in pg.get("buttons", [])][:10]})

    # 原始碼有、但沒被走到的 MVC Action（排除 API 與 Error/Privacy 這類樣板頁）
    for c in static.get("controllers", []):
        if c["api"] or c["controller"] in ("Error",):
            continue
        for act in c["actions"]:
            if act["name"] in ("Error", "Privacy"):
                continue
            path = "/" + "/".join(x for x in (c["area"], c["controller"],
                                              "" if act["name"] == "Index" else act["name"]) if x)
            k = _norm(path)
            if k in used:
                continue
            used.add(k)
            feats.append({"id": f"f{len(feats)+1:02d}", "name": f"{c['controller']}.{act['name']}",
                          "path": path, "source": "code", "verbs": act["verbs"],
                          "requires_login": act["authorize"] and not act["anonymous"],
                          "page": None, "fields": None, "buttons": []})
    # Razor Pages：Areas/Identity/Pages/Account/Register.cshtml → /Identity/Account/Register
    for rp in static.get("razor_pages", []):
        parts = Path(rp).with_suffix("").parts
        i = parts.index("Pages")
        area = parts[i - 1] if i >= 2 and parts[i - 2] == "Areas" else ""
        segs = [s for s in parts[i + 1:] if s != "Index"]
        path = "/" + "/".join(x for x in (area, *segs) if x)
        k = _norm(path)
        if k in used or segs[-1:] in (["Logout"], ["Error"]):
            continue
        used.add(k)
        feats.append({"id": f"f{len(feats)+1:02d}", "name": segs[-1] if segs else area,
                      "path": path, "source": "code", "requires_login": False,
                      "page": None, "fields": None, "buttons": []})

    for r in static.get("routes", []):
        k = _norm(r["path"])
        if k in used or "<" in r["path"]:
            continue
        used.add(k)
        feats.append({"id": f"f{len(feats)+1:02d}", "name": r["function"], "path": r["path"],
                      "source": "code", "verbs": r["verbs"], "requires_login": False,
                      "page": None, "fields": None, "buttons": []})
    return feats


def write_md(out: Path, feats: list[dict], static: dict) -> None:
    rows = ["| id | 功能 | 路徑 | 來源 | 需登入 | 欄位 | 按鈕 |", "|---|---|---|---|---|---|---|"]
    for f in feats:
        rows.append(f"| {f['id']} | {f['name']} | `{f['path']}` | {f['source']} | "
                    f"{'是' if f['requires_login'] else ''} | {f['fields'] if f['fields'] is not None else ''} | "
                    f"{'、'.join(f['buttons'][:5])} |")
    api = [f"{c['controller']}（{len(c['actions'])} 個動作）"
           for c in static.get("controllers", []) if c["api"]]
    txt = "# 功能盤點\n\n" + "\n".join(rows) + "\n"
    if api:
        txt += "\n## API 控制器（不在畫面上操作，用圖解或回應畫面說明）\n\n" + \
               "\n".join(f"- {a}" for a in api) + "\n"
    txt += ("\n> 來源 `code` 的項目是原始碼裡有、但選單與爬蟲都沒走到的動作。"
            "逐一判斷：要示範就補進分鏡；不示範就寫進 storyboard 的 `exclusions` 並附理由。\n")
    (out / "features.md").write_text(txt, encoding="utf-8", newline="\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--url", help="正在執行的網站根網址；省略則只做靜態掃描")
    ap.add_argument("--out", required=True)
    ap.add_argument("--login", help="登入設定 JSON（同 storyboard 的 login 區塊）")
    ap.add_argument("--max-pages", type=int, default=60)
    ap.add_argument("--depth", type=int, default=2)
    a = ap.parse_args()

    root = Path(a.project).resolve()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    has_cs = any(_files(root, "*.csproj"))
    static = scan_dotnet(root) if has_cs else scan_python(root)
    print(f"  靜態：{static['kind']}  "
          + (f"{len(static['controllers'])} 個 Controller、{len(static['nav'])} 個選單項目"
             if has_cs else f"{len(static['routes'])} 個 route"))

    login = json.loads(Path(a.login).read_text(encoding="utf-8")) if a.login else None
    pages = crawl(a.url, out, login, a.max_pages, a.depth) if a.url else []

    feats = merge(static, pages)
    (out / "features.json").write_text(json.dumps(
        {"project": str(root), "url": a.url, "features": feats, "pages": pages,
         "static": static}, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    write_md(out, feats, static)

    print(f"\n完成：{len(feats)} 項功能、{len(pages)} 個頁面")
    print(f"  {out / 'features.json'}\n  {out / 'features.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
