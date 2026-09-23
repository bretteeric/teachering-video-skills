"""把書籍 PDF 的指定頁轉成 PNG 供目視檢查（檔名只用 ASCII，方便 Read 工具開啟）。

用法：
    python preview.py 書.pdf 輸出資料夾                 # 自動挑：封面、書名頁、目錄首頁、前言、第一個篇扉頁、
                                                        #         第一個章扉頁、一頁含 H2 的內文、索引首頁
    python preview.py 書.pdf 輸出資料夾 1,4,35,577       # 指定頁碼（PDF 實體頁，1 起算）
"""
import sys
from pathlib import Path

import pymupdf as fitz

pdf, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
doc = fitz.open(pdf)
if len(sys.argv) > 3:
    pages = [int(x) for x in sys.argv[3].split(",")]
else:
    toc = doc.get_toc()
    pick = {1, 2}
    for lvl, title, page in toc:
        if title == "目錄" or title.startswith("前言") or title == "索引":
            pick.add(page)
    first_part = next((p for l, t, p in toc if l == 1 and "篇" in t), None)
    first_ch = next((p for l, t, p in toc if l == 2 and t.startswith("第")), None)
    for p in (first_part, first_ch, first_ch + 1 if first_ch else None):
        if p:
            pick.add(p)
    pages = sorted(pick)
print(f"{pdf.name}: {doc.page_count} 頁，輸出 {pages}")
for n in pages:
    if 1 <= n <= doc.page_count:
        target = out / f"p{n:03d}.png"
        doc[n - 1].get_pixmap(dpi=70).save(target)
        print(target)
