---
name: book-creator-skill
description: 把資料夾中依序編號的 Markdown 講義（如 講義/00～15_*.md）依時序與章節編排成一本教科書，同時輸出 .md 與 .pdf：滿版封面（書名、徽章、代表圖示）、書名頁、如何使用本書、含頁碼的目錄、前言、篇扉頁、章扉頁（附海報主視覺）、章內容、書末關鍵詞索引、PDF 書籤。版式沿用《AI Agent 架構師訓練手冊-30HRS》。當使用者說「講義編成一本書」「整理成教科書／手冊／電子書」「合輯成 PDF」「加封面、目錄、索引」「重新產生訓練手冊」時使用。
allowed-tools: Bash(python:*) Bash(ls:*) Bash(cp:*) Bash(mkdir:*) Bash(npm:*)
---

# 講義 → 教科書（Markdown + PDF）

把一組講義原稿編成一本書。版式、頁序與章節架構已固定在本 skill 的腳本與樣式中，
**不要重新手刻 HTML 或自己拼接 Markdown**——你的工作是：檢查原稿、規劃篇章、寫設定檔、執行、驗證。

- 編排規格（頁序、標題層級、版面、索引規則）：[references/book-structure.md](references/book-structure.md)
- 設定檔欄位：[references/config-schema.md](references/config-schema.md)
- 設定範本（即《AI Agent 架構師訓練手冊-30HRS》的實際設定）：[templates/book.json](templates/book.json)
- 所有指令都在 **workspace 根目錄**執行；下文 `$SK` 代表 `.claude/skills/book-creator-skill`。

## 前置條件

| 項目 | 檢查 | 沒有時 |
|---|---|---|
| Python 套件 | `python -c "import markdown, pymupdf, PIL, playwright"` | `pip install markdown pymupdf pillow playwright` 後 `python -m playwright install chromium` |
| mermaid、highlight.js | 設定檔 `node_modules`（預設 `工具/node_modules`）或 `$SK/node_modules` | `cd $SK && npm install mermaid @highlightjs/cdn-assets` |
| 原稿 | `ls <source_dir>/[0-9][0-9]_*.md` | 沒有原稿就回報，不要自己編內容 |

## 情境 A：重新產生《AI Agent 架構師訓練手冊-30HRS》

講義有修改、海報有更新時，直接用範本設定重跑即可：

```bash
python $SK/scripts/build_book.py --config $SK/templates/book.json
```

然後做步驟六的驗證。

## 情境 B：編一本新書

### 步驟一　盤點原稿

```bash
ls <source_dir>/[0-9][0-9]_*.md
python $SK/scripts/harvest_terms.py <source_dir> "[0-9][0-9]_*.md" 3 60
```

逐檔確認（見 book-structure.md 第 3 節）：
- 有 front matter，至少有 `title`、`subtitle`；章號用 `session:` 或 `chapter:`，否則取檔名前綴。
- **程式碼區塊外沒有 H1**，節從 `##` 開始。有 H1 的原稿先回報使用者，確認後改成 H2 或移到 front matter。
- 圖片是相對於原稿資料夾的路徑。

`harvest_terms.py` 會列出每章副標關鍵詞與跨章英文技術名詞，步驟三挑索引詞會用到。

### 步驟二　規劃書名與篇章

需要決定：書名、徽章、輸出檔名、前言是哪一章、分成哪幾篇。
- 使用者有指定的照指定。**檔名照使用者給的字面值**（例：`AI Agent 架構師訓練手冊-30HRS`）。
- 分篇依據：原稿中已有的階段劃分（例如課程總覽裡的「四個學習階段」）優先；沒有就依主題歸納 3～5 篇，
  並在回報時說明分篇理由。
- 書名或分篇無法從原稿與使用者的話推得時，才用 AskUserQuestion 問。

### 步驟三　撰寫設定檔

```bash
cp $SK/templates/book.json <放設定的位置>/book.json    # 建議 工具/<書名>.book.json
```

逐欄改寫（欄位見 config-schema.md），**範本裡的每個字串都是舊書的內容，一個都不能漏改**。重點：
- 封面書名 `title_cover_html`、統計列 `cover_stats`、`cover_kicker`、`cover_footer_left`、`title_page_rows`
  與 `title` 是**各自獨立**的欄位——只改 `title` 的話，封面仍會印出舊書名（已實測）。
- `parts[].chapters` 覆蓋前言以外的每一章，且不重疊。
- `emblem.nodes` 挑全書最核心的 6 個概念（大寫英文、各 ≤ 6 字母）。
- `index_terms` 60～100 筆：以步驟一的副標關鍵詞與跨章技術名詞為主，英文加 `\\b` 字界，同義詞用 `|` 合併。
- `howto.structure` 描述原稿每章的共同段落；原稿沒有固定結構就刪掉這個欄位。

### 步驟四　先產生 Markdown 試跑

```bash
python $SK/scripts/build_book.py --config <book.json> --md-only
```

- `[索引] 全書找不到詞彙` → 修正該詞的正規式或刪除。
- `必須恰好屬於一篇`、`章號重複`、`程式碼區塊外出現 H1` → 修設定或回報原稿問題。

### 步驟五　產生 PDF

```bash
python $SK/scripts/build_book.py --config <book.json>
```

約 500 頁、100 張 mermaid 圖的書需要 2～3 分鐘（本文渲染兩次）。放背景執行即可。

### 步驟六　驗證（每次都要做）

```bash
python $SK/scripts/preview.py "<輸出>.pdf" <scratchpad>/preview
```

自動挑出封面、書名頁、目錄首頁、前言、第一個篇扉頁、第一個章扉頁、一頁內文、索引首頁轉成 PNG，
**逐張用 Read 看過**，確認：
- [ ] 封面書名沒有斷在奇怪位置、各篇名稱卡片沒有擠壓
- [ ] 目錄頁碼＝對應頁的頁尾數字（抽查前言、第一篇、第 1 章）
- [ ] 章扉頁海報完整、章資訊表有值
- [ ] H2 深藍色條上沒有殘留白點（頁碼標記已清除）
- [ ] 索引有頁碼、沒有 `000`
- [ ] 建置輸出沒有 mermaid／圖片錯誤（有錯腳本會直接中止）

需要更精細的檢查時：
```bash
python -c "import pymupdf as f; d=f.open('<輸出>.pdf'); print(d.page_count, len(d.get_toc()), sum(len(p.get_links()) for p in d))"
```
書籤數應≈篇＋章＋節數；連結數應≈目錄列數＋索引頁碼數。

### 步驟七　回報

列出：兩個輸出檔的路徑、頁數與檔案大小、篇章結構（幾篇幾章、如何分篇）、索引詞數、
缺海報的章、設定檔位置，以及重建指令 `python $SK/scripts/build_book.py --config <book.json>`。

## 陷阱（都已實際踩過）

| 狀況 | 原因與處理 |
|---|---|
| `找不到頁碼標記` | 標記被 Chromium 裁掉：標記必須在頁面內容區內（`book.css` 的 `.pm` 放在元素角落），不可移到頁邊距 |
| 目錄／索引點了沒反應 | 合併 PDF（`insert_pdf`）會丟掉 Chromium 產生的內部連結；腳本已在合併後用 `insert_link` 重建，別改回 `<a href>` |
| `正被其他程式開啟` | PDF 開在檢視器中；新版已存為 `.tmp.pdf`，請使用者關掉檢視器後重跑 |
| 巢狀程式碼區塊中的 `## 1. 專案目標` 被當成節 | 原稿用 ```` 四個反引號 ```` 或 `~~~` 包三個反引號；腳本的 `scan()` 依 Python-Markdown 規則判斷，勿改成簡單的開關計數 |
| 終端機中文變亂碼 | 只是主控台編碼，檔案本身正確；腳本已 `reconfigure(encoding="utf-8")` |
| `--out-dir` 到別處後 Markdown 圖片破圖 | 原稿圖片是相對路徑；正式輸出請與原稿同資料夾，`--out-dir` 只用於試做 |
| 成品 `.md` 被當成最新講義 | 成品放在 `講義/` 後會是最新的 .md，`image-geneate-skill`「挑最後新增的講義」會選到它——提醒使用者用參數指定講義 |

## 不要做的事

- 不要直接修改成品 `.md`（檔頭已註明自動產生）；要改內容就改原稿後重跑。
- 不要改動原稿內容來「配合」排版；原稿有問題就回報。
- 不要把海報原圖（每張約 2MB）直接塞進 PDF；腳本會自動縮圖到 `images/book/`。
