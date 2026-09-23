"""把一組依序編號的 Markdown 講義編排成一本教科書（Markdown + PDF）。

用法（在 workspace 根目錄執行）：
    python .claude/skills/book-creator-skill/scripts/build_book.py --config book.json
    python .../build_book.py --config book.json --md-only          # 只產生 Markdown
    python .../build_book.py --config book.json --out-dir 暫存/      # 輸出到別的資料夾（試做用）

編排：封面 → 書名頁 → 如何使用本書 → 目錄 → 前言 → 各篇（篇扉頁 → 章扉頁 → 章內容）→ 索引。
PDF 分兩次渲染：第一次以隱形標記取得每個標題的頁碼，第二次把頁碼填進索引；
封面／前置頁／本文分開輸出後合併，再補上目錄與索引的跳頁連結、PDF 書籤與中繼資料。
設定欄位說明見 references/config-schema.md。
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import markdown
import pymupdf as fitz
from PIL import Image
from playwright.sync_api import sync_playwright

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS = SKILL_DIR / "assets"

FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
MARK = "@@{}@@"
MD_EXT = ["extra", "admonition", "sane_lists"]
MARGIN = {"top": "16mm", "bottom": "18mm", "left": "14mm", "right": "14mm"}

C: dict = {}        # 書籍設定（book.json）
WS = Path.cwd()     # workspace 根目錄
OUT = Path.cwd()    # 輸出資料夾


# ---------------------------------------------------------------- 設定

def book_name() -> str:
    return f"{C['title']}（{C['badge']}）" if C.get("badge") else C["title"]


def parts() -> list[dict]:
    for p in C["parts"]:
        p["range"] = range(p["chapters"][0], p["chapters"][1] + 1)
    return C["parts"]


def part_of(num: int) -> dict:
    return next(p for p in parts() if num in p["range"])


def inline_md(text: str) -> str:
    """設定檔中的短字串允許 **粗體**、`程式碼`。"""
    out = markdown.markdown(text)
    return re.sub(r"^<p>(.*)</p>$", r"\1", out.strip(), flags=re.S)


def lib_paths() -> dict[str, str]:
    candidates = [WS / C.get("node_modules", "工具/node_modules"), SKILL_DIR / "node_modules"]
    for nm in candidates:
        mermaid = nm / "mermaid/dist/mermaid.min.js"
        hljs = nm / "@highlightjs/cdn-assets/highlight.min.js"
        if mermaid.exists() and hljs.exists():
            return {"mermaid": mermaid.as_uri(), "hljs": hljs.as_uri(),
                    "hljs_css": (nm / "@highlightjs/cdn-assets/styles/github.min.css").as_uri()}
    raise SystemExit("找不到 mermaid／highlight.js。請在 skill 資料夾執行：\n"
                     f"  cd \"{SKILL_DIR}\" && npm install mermaid @highlightjs/cdn-assets")


# ---------------------------------------------------------------- 讀取原稿

@dataclass
class Section:
    key: str          # 全書唯一 id，例如 ch03-s02
    title: str
    text: str         # 不含 fenced code 的內文，用於索引統計
    md_slug: str = ""


@dataclass
class Chapter:
    num: int
    meta: dict
    body: str
    source: Path
    sections: list[Section] = field(default_factory=list)

    @property
    def is_preface(self) -> bool:
        return bool(C.get("preface")) and self.num == C["preface"].get("chapter_num", 0)

    @property
    def key(self) -> str:
        return "preface" if self.is_preface else f"ch{self.num:02d}"

    @property
    def title(self) -> str:
        if self.is_preface:
            return C["preface"].get("title") or self.meta.get("title", "前言")
        return self.meta.get("title", self.source.stem)


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    m = FRONT_MATTER.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, text[m.end():]


def scan(body: str):
    """逐行回傳 (行, 是否在 fenced code 內)；規則與 Python-Markdown fenced_code 相同（行首、同長度收尾）。"""
    fence = None
    for line in body.splitlines():
        if fence is None:
            m = FENCE_RE.match(line)
            if m:
                fence = m.group(1)
                yield line, True
                continue
            yield line, False
        else:
            yield line, True
            if line.rstrip() == fence:
                fence = None


def load_chapters() -> list[Chapter]:
    chapters = []
    for path in sorted((WS / C["source_dir"]).glob(C.get("source_glob", "[0-9][0-9]_*.md"))):
        if path.stem == C["output_name"]:
            continue
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        num = meta.get("session") or meta.get("chapter") or re.match(r"\d+", path.name).group(0)
        body = re.sub(r"^\[TOC\]\s*$", "", body, flags=re.M).strip() + "\n"
        ch = Chapter(int(num), meta, body, path)
        cur = None
        for line, in_code in scan(body):
            if in_code:
                continue
            m = HEADING_RE.match(line)
            if m and len(m.group(1)) == 1:
                raise SystemExit(f"{path.name}: 程式碼區塊外出現 H1「{m.group(2)}」——章名由本工具產生，原稿請從 H2 開始。")
            if m and len(m.group(1)) == 2:
                cur = Section(f"{ch.key}-s{len(ch.sections) + 1:02d}", m.group(2), "")
                ch.sections.append(cur)
            elif cur is not None:
                cur.text += line + "\n"
        chapters.append(ch)
    chapters.sort(key=lambda c: c.num)

    nums = [c.num for c in chapters]
    if len(set(nums)) != len(nums):
        raise SystemExit(f"章號重複：{nums}")
    for c in chapters:
        if c.is_preface:
            continue
        owners = [p["name"] for p in parts() if c.num in p["range"]]
        if len(owners) != 1:
            raise SystemExit(f"第 {c.num} 章（{c.source.name}）必須恰好屬於一篇，目前：{owners or '無'}")
    return chapters


def prepare_images(out_dir: Path) -> dict[int, str]:
    """把海報縮成 JPEG 放到 <輸出>/images/book/，回傳 {章號: 相對路徑}。"""
    img_dir = out_dir / "images" / "book"
    img_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    poster_dir = WS / C.get("poster_dir", "海報")
    if not poster_dir.exists():
        return out
    for png in sorted(poster_dir.glob(C.get("poster_glob", "[0-9][0-9] *.png"))):
        m = re.match(r"\d+", png.name)
        if not m:
            continue
        num = int(m.group(0))
        target = img_dir / f"ch{num:02d}.jpg"
        if not target.exists() or target.stat().st_mtime < png.stat().st_mtime:
            im = Image.open(png).convert("RGB")
            im.thumbnail((900, 1350), Image.LANCZOS)
            im.save(target, "JPEG", quality=84, optimize=True)
        out[num] = f"images/book/{target.name}"
    return out


# ---------------------------------------------------------------- 代表圖示（SVG）

def emblem_svg() -> str:
    e = C.get("emblem", {})
    names = e.get("nodes", ["SPEC", "SKILL", "RULES", "CODE", "UI", "TEST"])
    accent = set(e.get("accent_nodes", names[:1]))
    n = len(names)

    def hexagon(r):
        return " ".join(f"{200 + r * math.cos(math.radians(-90 + 60 * i)):.1f},"
                        f"{200 + r * math.sin(math.radians(-90 + 60 * i)):.1f}" for i in range(6))

    spokes, nodes = [], []
    for i, name in enumerate(names):
        a = math.radians(-90 + 30 + 360 / n * i) if n == 6 else math.radians(-90 + 360 / n * i)
        x, y = 200 + 150 * math.cos(a), 200 + 150 * math.sin(a)
        spokes.append(f'<line x1="{200 + 70 * math.cos(a):.1f}" y1="{200 + 70 * math.sin(a):.1f}" x2="{x:.1f}" y2="{y:.1f}"/>')
        color = "#f5a623" if name in accent else "#7fe3ee"
        nodes.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="27" fill="#0b2748" stroke="{color}" stroke-width="2.4" filter="url(#glow)"/>'
            f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" font-size="11" font-weight="700" fill="#fff" '
            f'font-family="Segoe UI, sans-serif" letter-spacing=".5">{html.escape(name)}</text>')
    return f"""
<svg class="emblem" viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{html.escape(C['title'])} 代表圖示">
  <defs>
    <radialGradient id="core" cx="50%" cy="45%" r="60%"><stop offset="0" stop-color="#1f8fd6"/><stop offset="1" stop-color="#0b2748"/></radialGradient>
    <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <circle cx="200" cy="200" r="186" fill="none" stroke="#7fe3ee" stroke-opacity=".25" stroke-width="1"/>
  <circle cx="200" cy="200" r="150" fill="none" stroke="#7fe3ee" stroke-opacity=".55" stroke-width="1.4" stroke-dasharray="4 7"/>
  <circle cx="200" cy="200" r="112" fill="none" stroke="#7fe3ee" stroke-opacity=".18" stroke-width="10"/>
  <g stroke="#7fe3ee" stroke-width="1.6" stroke-opacity=".75">{''.join(spokes)}</g>
  <polygon points="{hexagon(66)}" fill="url(#core)" stroke="#7fe3ee" stroke-width="3" filter="url(#glow)"/>
  <polygon points="{hexagon(54)}" fill="none" stroke="#7fe3ee" stroke-opacity=".45" stroke-width="1"/>
  <text x="200" y="198" text-anchor="middle" font-size="44" font-weight="800" fill="#fff"
        font-family="Segoe UI, Noto Sans TC, sans-serif" letter-spacing="2">{html.escape(e.get('core_top', 'AI'))}</text>
  <text x="200" y="228" text-anchor="middle" font-size="16" font-weight="700" fill="#7fe3ee"
        font-family="Segoe UI, Noto Sans TC, sans-serif" letter-spacing="5">{html.escape(e.get('core_bottom', 'AGENT'))}</text>
  {''.join(nodes)}
</svg>"""


# ---------------------------------------------------------------- 索引

def build_index(chapters: list[Chapter]) -> list:
    sections = [s for ch in chapters for s in ch.sections]
    order = {k: i for i, k in enumerate(k for ch in chapters for k in [ch.key] + [s.key for s in ch.sections])}
    entries = []
    for name, pattern in C.get("index_terms", []):
        rx = re.compile(pattern)
        counts = [(s.key, len(rx.findall(s.title)) * 5 + len(rx.findall(s.text))) for s in sections]
        counts = [c for c in counts if c[1] > 0]
        if not counts:
            print(f"[索引] 全書找不到詞彙，已略過：{name}", file=sys.stderr)
            continue
        # 詞彙出現在章名／副標 → 該章扉頁優先列入
        homes = [(ch.key, 99) for ch in chapters
                 if not ch.is_preface and rx.search(ch.title + " " + ch.meta.get("subtitle", ""))][:3]
        home_chaps = {k for k, _ in homes}
        rest = [c for c in counts if c[0].split("-s")[0] not in home_chaps]
        strong = [c for c in rest if c[1] >= 3] or rest
        top = homes + sorted(strong, key=lambda c: -c[1])[:max(6 - len(homes), 3)]
        entries.append((name, sorted(top, key=lambda c: order[c[0]])))
    latin = sorted([e for e in entries if e[0][0].isascii()], key=lambda e: e[0].lower())
    cjk = sorted([e for e in entries if not e[0][0].isascii()], key=lambda e: e[0].encode("big5", "replace"))
    groups: dict[str, list] = {}
    for e in latin:
        groups.setdefault(e[0][0].upper(), []).append(e)
    result = list(groups.items())
    if cjk:
        result.append(("中文詞彙", cjk))
    return result


def ref_label(key: str) -> str:
    if key.startswith("preface"):
        return f"前言–{int(key.split('-s')[1])}"
    if "-s" not in key:
        return f"第 {int(key[2:])} 章"
    chap, sec = key.split("-s")
    return f"{int(chap[2:])}–{int(sec)}"


# ---------------------------------------------------------------- Markdown 版

def gh_slug(text: str, seen: dict[str, int]) -> str:
    """GitHub／VS Code 預覽的錨點規則（重複時加 -1、-2）。"""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>|\{:[^}]*\}", "", text)
    slug = re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")
    n = seen.get(slug, 0)
    seen[slug] = n + 1
    return slug if n == 0 else f"{slug}-{n}"


def build_markdown(chapters: list[Chapter], posters: dict[int, str], index: list) -> str:
    seen: dict[str, int] = {}
    heads: dict[str, str] = {}

    def h(level: int, text: str, key: str | None = None) -> str:
        slug = gh_slug(text, seen)
        if key:
            heads[key] = slug
        return f"{'#' * level} {text}"

    hw = C.get("howto", {})
    front = [f"![{C['title']} 封面](images/book/cover.png)", "", h(1, book_name()), "",
             f"**{C.get('subtitle', '')}**", ""]
    if C.get("tagline"):
        front += [f"> {C['tagline']}", ""]
    front += ["| 項目 | 內容 |", "|---|---|", f"| 書名 | {book_name()} |"]
    front += [f"| {k} | {v} |" for k, v in C.get("title_page_rows", [])]
    front += ["", h(2, "如何使用本書"), ""]
    if hw.get("intro"):
        front += [hw["intro"], ""]
    if hw.get("structure"):
        front += [hw.get("structure_intro", ""), ""]
        front += [f"{i}. **{a}**：{b}" for i, (a, b) in enumerate(hw["structure"], 1)]
        front.append("")
    front += ["| 篇 | 主題 | 章 |", "|---|---|---|"]
    front += [f"| {p['name']} | {p['title']} | 第 {p['range'][0]}～{p['range'][-1]} 章"
              f"{'（' + p['span'] + '）' if p.get('span') else ''} |" for p in parts()]
    front.append("")
    if hw.get("admonitions"):
        front += ["書中提示框：" + "、".join(f"**{t}**（{d.rstrip('。')}）" for _, t, d in hw["admonitions"]) + "。", ""]
    front += ["書末附**索引**，可依關鍵詞查到相關章節。", ""]

    body: list[str] = []
    for ch in chapters:
        sub = ch.meta.get("subtitle", "")
        if ch.is_preface:
            body += [h(1, f"前言　{ch.title}", ch.key), ""]
            if ch.num in posters:
                body += [f"![前言主視覺]({posters[ch.num]})", ""]
            if sub:
                body += [f"> {sub}", ""]
        else:
            part = part_of(ch.num)
            if ch.num == part["range"][0]:
                body += [h(1, f"{part['name']}　{part['title']}", "part-" + part["name"]), "", part.get("desc", ""), "",
                         "| 章 | 主題 | 重點 |", "|---:|---|---|"]
                body += [f"| {c.num} | {c.title} | {c.meta.get('subtitle', '')} |"
                         for c in chapters if not c.is_preface and c.num in part["range"]]
                body.append("")
            body += [h(1, f"第 {ch.num} 章　{ch.title}", ch.key), ""]
            if ch.num in posters:
                body += [f"![第 {ch.num} 章主視覺]({posters[ch.num]})", ""]
            meta_bits = [f"{label}：`{ch.meta[k]}`" if len(spec) > 2 else f"{label}：{ch.meta[k]}"
                         for spec in C.get("opener_meta", []) for label, k in [spec[:2]] if ch.meta.get(k)]
            if sub:
                body.append(f"> **{sub}**" + ("  " if meta_bits else ""))
            if meta_bits:
                body.append("> " + "　｜　".join(meta_bits))
            body.append("")
        sec_iter = iter(ch.sections)
        for line, in_code in scan(ch.body):
            if not in_code:
                m = HEADING_RE.match(line)
                if m:
                    if len(m.group(1)) == 2:
                        sec = next(sec_iter)
                        sec.md_slug = gh_slug(m.group(2), seen)
                        heads[sec.key] = sec.md_slug
                    else:
                        gh_slug(m.group(2), seen)
            body.append(line)
        body.append("")

    idx = [h(1, "索引", "index"), "", "依英文字母與中文詞彙排列；每個條目列出該詞彙討論最集中的章節（章號–節）。", ""]
    for group, entries in index:
        idx += [f"**{group}**", ""]
        idx += [f"- **{name}** — " + "、".join(f"[{ref_label(k)}](#{heads[k]})" for k, _ in refs) for name, refs in entries]
        idx.append("")

    toc = ["", h(2, "目錄"), ""]
    for ch in chapters:
        if ch.is_preface:
            toc.append(f"- [前言　{ch.title}](#{heads[ch.key]})")
            toc += [f"    - [{s.title}](#{s.md_slug})" for s in ch.sections]
    for p in parts():
        toc.append(f"- **[{p['name']}　{p['title']}](#{heads['part-' + p['name']]})**")
        for ch in chapters:
            if not ch.is_preface and ch.num in p["range"]:
                toc.append(f"  - [第 {ch.num} 章　{ch.title}](#{heads[ch.key]})")
                toc += [f"    - [{s.title}](#{s.md_slug})" for s in ch.sections]
    toc += [f"- [索引](#{heads['index']})", ""]

    header = (f"<!-- 本檔由 book-creator-skill 依 {C['source_dir']}/ 原稿自動編排產生，請勿直接修改；"
              f"修改原稿後重新執行即可。 -->\n\n")
    return header + "\n".join(front + toc + body + idx) + "\n"


# ---------------------------------------------------------------- HTML 版

def md_to_html(text: str) -> str:
    out = markdown.markdown(text, extensions=MD_EXT)
    out = re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>',
                 lambda m: f'<pre class="mermaid">{m.group(1)}</pre>', out, flags=re.S)
    out = re.sub(r"<li>\[ \]\s*", '<li class="task">☐ ', out)
    return re.sub(r"<li>\[[xX]\]\s*", '<li class="task">☑ ', out)


def mark(key: str, pos: str = "") -> str:
    return f'<span class="pm {pos}">{MARK.format(key)}</span>'


def chapter_html(ch: Chapter, posters: dict[int, str]) -> str:
    content = md_to_html(ch.body)
    h2s = re.findall(r"<h2( [^>]*)?>", content)
    if len(h2s) != len(ch.sections):
        raise SystemExit(f"{ch.source.name}: H2 數量不符（HTML {len(h2s)}、解析 {len(ch.sections)}）")
    it = iter(ch.sections)
    content = re.sub(r"<h2( [^>]*)?>", lambda m: (lambda s: f'<h2 id="{s.key}">{mark(s.key)}')(next(it)), content)

    img = (f'<img class="op-poster" src="{(OUT / posters[ch.num]).as_uri()}" alt="{html.escape(ch.title)} 主視覺">'
           if ch.num in posters else '<div class="op-noposter"></div>')
    sub = html.escape(ch.meta.get("subtitle", ""))
    if ch.is_preface:
        opener = f"""
<section class="opener" id="{ch.key}">{mark(ch.key, "br")}
  <div class="op-kicker">{html.escape(C['preface'].get('kicker', 'PREFACE'))}</div>
  <h1 class="op-title">前言　{html.escape(ch.title)}</h1>
  <div class="op-sub">{sub}</div>
  {img}
</section>"""
    else:
        part = part_of(ch.num)
        cells = "".join(
            f"<th>{html.escape(spec[0])}</th><td>"
            + (f"<code>{html.escape(ch.meta[spec[1]])}</code>" if len(spec) > 2 else html.escape(ch.meta[spec[1]]))
            + "</td>" for spec in C.get("opener_meta", []) if ch.meta.get(spec[1]))
        meta = f'<table class="op-meta"><tr>{cells}</tr></table>' if cells else ""
        opener = f"""
<section class="opener" id="{ch.key}">{mark(ch.key, "br")}
  <div class="op-kicker">CHAPTER {ch.num:02d}<span>{html.escape(part['name'])}・{html.escape(part['title'])}</span></div>
  <h1 class="op-title"><small>第 {ch.num} 章</small>{html.escape(ch.title)}</h1>
  <div class="op-sub">{sub}</div>
  {img}
  {meta}
</section>"""
    return opener + f'\n<div class="chapter">{content}</div>'


def part_html(part: dict, chapters: list[Chapter], no: int) -> str:
    rows = "".join(f'<li><b>第 {c.num} 章</b><span>{html.escape(c.title)}</span>'
                   f'<em>{html.escape(c.meta.get("subtitle", ""))}</em></li>'
                   for c in chapters if not c.is_preface and c.num in part["range"])
    key = "part-" + part["name"]
    return f"""
<section class="part-page" id="{key}">{mark(key, "br")}
  <div class="pp-no">PART {no}</div>
  <div class="pp-name">{html.escape(part['name'])}</div>
  <h1 class="pp-title">{html.escape(part['title'])}</h1>
  <div class="pp-span">{html.escape(part.get('span', ''))}</div>
  <p class="pp-desc">{html.escape(part.get('desc', ''))}</p>
  <ol class="pp-list">{rows}</ol>
</section>"""


def index_html(index: list, pages: dict[str, int]) -> str:
    blocks = []
    for group, entries in index:
        items = []
        for name, refs in entries:
            nums, done = [], set()
            for k, _ in refs:
                p = pages.get(k, 0)
                if p not in done:
                    done.add(p)
                    nums.append(str(p or "000"))
            items.append(f'<li><span class="ix-term">{html.escape(name)}</span><span class="ix-pages">{", ".join(nums)}</span></li>')
        blocks.append(f'<div class="ix-group"><div class="ix-head">{html.escape(group)}</div><ul>{"".join(items)}</ul></div>')
    return f"""
<section class="index-page" id="index">{mark('index', 'tr')}
  <h1 class="ix-title">索引</h1>
  <p class="ix-note">依英文字母與中文詞彙排列；頁碼為該詞彙討論最集中的章節起始頁，可直接點選跳頁。</p>
  <div class="ix-cols">{''.join(blocks)}</div>
</section>"""


def cover_html() -> str:
    chips = "".join(f"<span><b>{html.escape(p['name'])}</b>{html.escape(p['title'])}</span>" for p in parts())
    badge = f'<span class="bc-badge">{html.escape(C["badge"])}</span>' if C.get("badge") else "<span></span>"
    return f"""
<section class="book-cover">
  <div class="bc-top"><span>{html.escape(C.get('cover_kicker', ''))}</span>{badge}</div>
  <div class="bc-emblem">{emblem_svg()}</div>
  <h1 class="bc-title">{C.get('title_cover_html') or html.escape(C['title'])}</h1>
  <div class="bc-hours">{C.get('cover_stats', '')}</div>
  <div class="bc-sub">{html.escape(C.get('subtitle', ''))}</div>
  <div class="bc-tag">{html.escape(C.get('tagline', ''))}</div>
  <div class="bc-parts">{chips}</div>
  <div class="bc-foot"><span>{html.escape(C.get('cover_footer_left', ''))}</span><span>{html.escape(C.get('edition', ''))}</span></div>
</section>"""


def front_html(chapters: list[Chapter], pages: dict[str, int], marks: bool = True) -> str:
    def row(key, text, cls):
        return (f'<li class="{cls}">{mark("T" + key) if marks else ""}<span class="t">{text}</span>'
                f'<span class="dots"></span><span class="p">{pages.get(key, 0) or "000"}</span></li>')

    def plain(t):
        return html.escape(t.replace("`", ""))

    rows = []
    for ch in chapters:
        if ch.is_preface:
            rows.append(row(ch.key, f"前言　{plain(ch.title)}", "lv1"))
            rows += [row(s.key, plain(s.title), "lv2") for s in ch.sections]
    for p in parts():
        rows.append(row("part-" + p["name"], f"{html.escape(p['name'])}　{html.escape(p['title'])}", "lv0"))
        for ch in chapters:
            if not ch.is_preface and ch.num in p["range"]:
                rows.append(row(ch.key, f"第 {ch.num} 章　{plain(ch.title)}", "lv1"))
                rows += [row(s.key, plain(s.title), "lv2") for s in ch.sections]
    rows.append(row("index", "索引", "lv0"))

    hw = C.get("howto", {})
    meta_rows = "".join(f"<tr><th>{html.escape(k)}</th><td>{inline_md(v)}</td></tr>" for k, v in C.get("title_page_rows", []))
    badge = f'<div class="tp-hours">{html.escape(C["badge"])}</div>' if C.get("badge") else ""
    structure = "".join(f"<li><b>{html.escape(a)}</b>：{html.escape(b)}</li>" for a, b in hw.get("structure", []))
    part_rows = "".join(f"<tr><td>{html.escape(p['name'])}</td><td>{html.escape(p['title'])}</td>"
                        f"<td>第 {p['range'][0]}～{p['range'][-1]} 章{'（' + html.escape(p['span']) + '）' if p.get('span') else ''}</td></tr>"
                        for p in parts())
    adm = "".join(f'<div class="admonition {k}"><p class="admonition-title">{html.escape(t)}</p><p>{html.escape(d)}</p></div>'
                  for k, t, d in hw.get("admonitions", []))
    return f"""
<section class="title-page">
  <div class="tp-emblem">{emblem_svg()}</div>
  <h1>{html.escape(C['title'])}</h1>
  {badge}
  <div class="tp-sub">{html.escape(C.get('subtitle', ''))}</div>
  <table class="tp-meta">{meta_rows}</table>
</section>
<section class="howto">
  <h1 class="fm-title">如何使用本書</h1>
  {f"<p>{inline_md(hw['intro'])}</p>" if hw.get('intro') else ""}
  {f"<p>{inline_md(hw.get('structure_intro', ''))}</p><ol class='howto-list'>{structure}</ol>" if structure else ""}
  <table><tr><th>篇</th><th>主題</th><th>章</th></tr>{part_rows}</table>
  {adm}
  <p>書末附有<b>索引</b>：依關鍵詞列出討論最集中的章節頁碼。</p>
</section>
<section class="book-toc">
  <h1 class="fm-title">目錄</h1>
  <ul>{''.join(rows)}</ul>
</section>"""


def page_shell(body: str, libs: dict, base: Path, scripts: bool) -> str:
    js = f"""
<script src="{libs['hljs']}"></script>
<script src="{libs['mermaid']}"></script>
<script>
  document.querySelectorAll('pre code').forEach(el => {{
    if (!el.className.includes('language-')) el.classList.add('language-plaintext');
    hljs.highlightElement(el);
  }});
  mermaid.initialize({{ startOnLoad: false, theme: 'default', securityLevel: 'loose',
    fontFamily: '"Noto Sans TC", "Microsoft JhengHei", sans-serif', flowchart: {{ htmlLabels: true }} }});
  (async () => {{
    const errors = [];
    for (const [i, node] of Array.from(document.querySelectorAll('pre.mermaid')).entries()) {{
      const src = node.textContent;
      try {{
        await mermaid.run({{ nodes: [node] }});
        const svg = node.querySelector('svg');
        if (!svg) throw new Error('沒有產生 SVG');
        svg.style.maxHeight = '800px'; svg.style.maxWidth = '100%';
        svg.style.width = 'auto'; svg.style.height = 'auto'; svg.removeAttribute('height');
      }} catch (err) {{
        const msg = (err && (err.message || err.str)) || JSON.stringify(err);
        errors.push(`第 ${{i + 1}} 張圖（${{src.trim().split('\\n')[0]}}）：${{msg}}`);
      }}
    }}
    if (errors.length) window.__renderError = errors.join('\\n');
    window.__renderDone = true;
  }})();
</script>""" if scripts else "<script>window.__renderDone = true;</script>"
    return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<base href="{base.resolve().as_uri()}/">
<title>{html.escape(book_name())}</title>
<link rel="stylesheet" href="{libs['hljs_css']}">
<link rel="stylesheet" href="{(ASSETS / 'lesson.css').as_uri()}">
<link rel="stylesheet" href="{(ASSETS / 'book.css').as_uri()}">
</head><body>
{body}
{js}
</body></html>"""


# ---------------------------------------------------------------- 渲染與合併

def footer() -> str:
    return f"""<div style="font-size:8px;width:100%;padding:0 14mm;color:#667;display:flex;justify-content:space-between;
font-family:'Noto Sans TC','Microsoft JhengHei',sans-serif;">
<span>{html.escape(book_name())}</span><span>— <span class="pageNumber"></span> —</span></div>"""


def render(page, html_text: str, out: Path, work: Path, *, with_footer: bool, margin: dict) -> None:
    tmp = work / "page.html"
    tmp.write_text(html_text, encoding="utf-8")
    page.goto(tmp.as_uri(), wait_until="load")
    page.wait_for_function("window.__renderDone === true", timeout=0)
    err = page.evaluate("window.__renderError || null")
    broken = page.evaluate(
        "Array.from(document.images).filter(i => !i.complete || i.naturalWidth === 0).map(i => i.getAttribute('src'))")
    page.evaluate("document.fonts.ready")
    if err:
        raise SystemExit(f"mermaid 渲染失敗：{err}")
    if broken:
        raise SystemExit(f"圖片載入失敗：{broken}")
    page.pdf(path=str(out), format="A4", print_background=True, display_header_footer=with_footer,
             header_template="<div></div>", footer_template=footer() if with_footer else "<div></div>", margin=margin)


def find_marks(pdf: Path) -> dict[str, tuple[int, fitz.Rect]]:
    found = {}
    with fitz.open(pdf) as doc:
        for i, pg in enumerate(doc):
            for w in pg.get_text("words"):
                m = re.fullmatch(r"@@(.+?)@@", w[4])
                if m and m.group(1) not in found:
                    found[m.group(1)] = (i + 1, fitz.Rect(w[:4]))
    return found


def strip_marks(doc: fitz.Document) -> None:
    for pg in doc:
        hits = [fitz.Rect(w[:4]) for w in pg.get_text("words") if re.fullmatch(r"@@.+?@@", w[4])]
        for r in hits:
            pg.add_redact_annot(r, fill=False)
        if hits:
            pg.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)


def build_pdf(chapters: list[Chapter], posters: dict[int, str], index: list, out_dir: Path) -> Path:
    libs = lib_paths()
    src_dir = WS / C["source_dir"]   # 原稿內的相對圖片路徑以此為基準
    body_parts, no = [], 0
    for ch in chapters:
        if not ch.is_preface and ch.num == part_of(ch.num)["range"][0]:
            no += 1
            body_parts.append(part_html(part_of(ch.num), chapters, no))
        body_parts.append(chapter_html(ch, posters))
    main_body = "\n".join(body_parts)
    all_keys = (["index"] + [c.key for c in chapters] + ["part-" + p["name"] for p in parts()]
                + [s.key for c in chapters for s in c.sections])

    work = Path(tempfile.mkdtemp(prefix="book_"))
    cover_pdf, front_pdf, body_pdf = work / "cover.pdf", work / "front.pdf", work / "body.pdf"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_default_timeout(0)

        cover = page_shell(cover_html(), libs, src_dir, scripts=False)
        render(page, cover, cover_pdf, work, with_footer=False, margin={k: "0" for k in MARGIN})
        shot = browser.new_page(viewport={"width": 794, "height": 1123}, device_scale_factor=2)
        (work / "cover.html").write_text(cover, encoding="utf-8")
        shot.goto((work / "cover.html").as_uri())
        shot.screenshot(path=str(out_dir / "images" / "book" / "cover.png"))
        shot.close()

        print("[渲染] 本文第 1 次（取得頁碼；含 mermaid，可能需要數分鐘）…")
        render(page, page_shell(main_body + index_html(index, {}), libs, src_dir, True), body_pdf, work,
               with_footer=True, margin=MARGIN)
        marks = find_marks(body_pdf)
        missing = [k for k in all_keys if k not in marks]
        if missing:
            raise SystemExit(f"找不到頁碼標記：{missing[:10]}（共 {len(missing)} 個）")
        pages = {k: marks[k][0] for k in all_keys}

        print("[渲染] 本文第 2 次（填入索引頁碼）…")
        render(page, page_shell(main_body + index_html(index, pages), libs, src_dir, True), body_pdf, work,
               with_footer=True, margin=MARGIN)
        check = find_marks(body_pdf)
        moved = [k for k in all_keys if check[k][0] != pages[k]]
        if moved:
            raise SystemExit(f"第二次渲染頁碼位移：{moved[:10]}")

        # 前置頁：先帶標記渲染取得目錄每列位置，再無標記重繪（標記為絕對定位，版面相同）
        render(page, page_shell(front_html(chapters, pages), libs, src_dir, False), front_pdf, work,
               with_footer=False, margin=MARGIN)
        front_marks = find_marks(front_pdf)
        render(page, page_shell(front_html(chapters, pages, marks=False), libs, src_dir, False), front_pdf, work,
               with_footer=False, margin=MARGIN)
        browser.close()

    book = fitz.open(cover_pdf)
    book.insert_pdf(fitz.open(front_pdf))
    offset = book.page_count
    book.insert_pdf(fitz.open(body_pdf))

    # 目錄連結（每列整行可點）
    for key, (pno, rect) in front_marks.items():
        target = key[1:]
        if key.startswith("T") and target in pages:
            pg = book[pno]
            pg.insert_link({"kind": fitz.LINK_GOTO, "page": offset + pages[target] - 1,
                            "from": fitz.Rect(40, rect.y0 - 2, pg.rect.width - 40, rect.y1 + 2), "to": fitz.Point(0, 0)})
    strip_marks(book)
    # 索引頁碼連結
    for pno in range(offset + pages["index"] - 1, book.page_count):
        pg = book[pno]
        for w in pg.get_text("words"):
            num = w[4].rstrip(",")
            if num.isdigit() and w[0] > 60 and w[3] < pg.rect.height - 50 and 0 < int(num) <= book.page_count - offset:
                pg.insert_link({"kind": fitz.LINK_GOTO, "page": offset + int(num) - 1,
                                "from": fitz.Rect(w[:4]), "to": fitz.Point(0, 0)})

    # 書籤：篇／前言／索引 → 章 → 節
    bm = [[1, "封面", 1], [1, "書名頁", 2], [1, "目錄", 1 + min(pno for k, (pno, _) in front_marks.items() if k.startswith("T"))]]
    for ch in chapters:
        if ch.is_preface:
            bm.append([1, f"前言　{ch.title}", offset + pages[ch.key]])
            bm += [[2, s.title.replace("`", ""), offset + pages[s.key]] for s in ch.sections]
    for p in parts():
        bm.append([1, f"{p['name']}　{p['title']}", offset + pages["part-" + p["name"]]])
        for ch in chapters:
            if not ch.is_preface and ch.num in p["range"]:
                bm.append([2, f"第 {ch.num} 章　{ch.title}", offset + pages[ch.key]])
                bm += [[3, s.title.replace("`", ""), offset + pages[s.key]] for s in ch.sections]
    bm.append([1, "索引", offset + pages["index"]])
    book.set_toc(bm)
    book.set_metadata({"title": book_name(), "subject": C.get("subtitle", ""), "keywords": C.get("keywords", ""),
                       "author": C.get("author", ""), "creator": "book-creator-skill"})

    out = out_dir / f"{C['output_name']}.pdf"
    tmp_out = out.with_suffix(".tmp.pdf")
    total = book.page_count
    book.save(tmp_out, garbage=3, deflate=True)
    book.close()
    try:
        tmp_out.replace(out)
    except PermissionError:
        raise SystemExit(f"{out.name} 正被其他程式開啟，新版已存成 {tmp_out.name}；請關閉檢視器後再執行一次。")
    print(f"[完成] {out.name}  {total} 頁  {out.stat().st_size / 1024 / 1024:.1f} MB"
          f"（封面 1 + 前置 {offset - 1} + 本文 {total - offset}）")
    return out


# ---------------------------------------------------------------- main

def main() -> None:
    global C, WS, OUT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, required=True, help="書籍設定 JSON（見 templates/book.json）")
    ap.add_argument("--workspace", type=Path, default=Path.cwd(), help="設定檔中相對路徑的基準（預設為目前目錄）")
    ap.add_argument("--out-dir", type=Path, help="覆寫設定中的 output_dir")
    ap.add_argument("--md-only", action="store_true", help="只產生 Markdown，不渲染 PDF")
    args = ap.parse_args()

    WS = args.workspace.resolve()
    C = json.loads(args.config.read_text(encoding="utf-8"))
    out_dir = (args.out_dir or WS / C.get("output_dir", C["source_dir"])).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    OUT = out_dir

    chapters = load_chapters()
    if not chapters:
        raise SystemExit(f"{C['source_dir']}/ 找不到符合 {C.get('source_glob')} 的原稿")
    posters = prepare_images(out_dir)
    if out_dir != (WS / C["source_dir"]).resolve():
        print(f"[提醒] 輸出資料夾與原稿不同，Markdown 版中原稿的相對圖片路徑（如 images/NN/…）會失效；PDF 版不受影響。")
    index = build_index(chapters)

    md_out = out_dir / f"{C['output_name']}.md"
    md_out.write_text(build_markdown(chapters, posters, index), encoding="utf-8")
    print(f"[完成] {md_out.name}  {md_out.stat().st_size / 1024:.0f} KB  "
          f"（{sum(not c.is_preface for c in chapters)} 章、{len(parts())} 篇、索引 {sum(len(e) for _, e in index)} 詞）")
    if not args.md_only:
        build_pdf(chapters, posters, index, out_dir)


if __name__ == "__main__":
    main()
