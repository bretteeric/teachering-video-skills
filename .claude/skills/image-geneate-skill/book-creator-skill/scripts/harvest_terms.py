"""從原稿蒐集索引候選詞（排除 fenced code），分三區列出：
  1. 章節副標關鍵詞——front matter `subtitle` 以「、」「×」「，」切開；是索引的骨幹
  2. 英文技術名詞——大寫開頭或全大寫縮寫（Flask、Repository、RBAC…），依跨章數排序
  3. **粗體**詞——作者特別強調的概念

用法：
    python harvest_terms.py 講義 "[0-9][0-9]_*.md" [最少章數=2] [每區筆數=80]

挑好的詞寫進 book.json 的 index_terms（每筆 [顯示名稱, 正規式]）。
挑選原則見 references/book-structure.md 的「索引」一節。
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
src, pattern = Path(sys.argv[1]), sys.argv[2]
min_ch = int(sys.argv[3]) if len(sys.argv) > 3 else 2
limit = int(sys.argv[4]) if len(sys.argv) > 4 else 80

EN_TERM = re.compile(r"\b(?:[A-Z][A-Za-z0-9]*[a-z0-9][A-Za-z0-9]*|[A-Z]{2,6}\d?)(?:\.md)?\b")
STOP = {"The", "This", "If", "And", "Or", "To", "In", "On", "For", "With", "No", "Yes", "OK", "Session", "PS",
        "A", "B", "C", "D", "E", "F", "True", "False", "None", "Step", "Figure"}

subtitle_terms, en_total, en_where = [], Counter(), defaultdict(set)
bold_total, bold_where = Counter(), defaultdict(set)

for path in sorted(src.glob(pattern)):
    raw = path.read_text(encoding="utf-8")
    fm = re.match(r"\A---\s*\n(.*?)\n---", raw, re.S)
    if fm:
        m = re.search(r"^subtitle:\s*(.+)$", fm.group(1), re.M)
        if m:
            parts = [t.strip() for t in re.split(r"[、，,×]| 與 |與", m.group(1)) if t.strip()]
            subtitle_terms.append((path.name[:2], parts))
    fence, lines = None, []
    for line in raw.splitlines():
        m = re.match(r"^(`{3,}|~{3,})", line)
        if fence is None and m:
            fence = m.group(1)
        elif fence is not None and line.rstrip() == fence:
            fence = None
        elif fence is None:
            lines.append(line)
    text = re.sub(r"`[^`\n]*`", " ", "\n".join(lines))        # 行內程式碼多為識別字，不列入
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)|\]\([^)]*\)", " ", text)  # 圖片與連結網址
    ch = path.name[:2]
    for t in EN_TERM.findall(text):
        if t not in STOP and not re.fullmatch(r"[A-Z]\d", t):   # T1、S3 之類的編號
            en_total[t] += 1
            en_where[t].add(ch)
    for t in re.findall(r"\*\*([^*\n]{2,20})\*\*", text):
        t = t.strip("：:，,。 ")
        if t and not (re.search(r"[/\\|=<>(){}]|\s\d+$|^\d", t) or re.fullmatch(r"[一-鿿]{1,2}", t)):
            bold_total[t] += 1
            bold_where[t].add(ch)

print("== 1. 章節副標關鍵詞")
for ch, terms in subtitle_terms:
    print(f"  {ch}  " + "｜".join(terms))

for label, total, where in (("2. 英文技術名詞", en_total, en_where), ("3. 粗體詞", bold_total, bold_where)):
    rows = [(t, n, len(where[t])) for t, n in total.items() if len(where[t]) >= min_ch]
    print(f"\n== {label}：{len(rows)} 個（至少 {min_ch} 章，列前 {limit}）")
    for t, n, c in sorted(rows, key=lambda r: (-r[2], -r[1]))[:limit]:
        print(f"{c:>3} 章  {n:>4} 次  {t}")
