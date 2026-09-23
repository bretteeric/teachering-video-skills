# book.json 欄位說明

完整範例：[../templates/book.json](../templates/book.json)（《AI Agent 架構師訓練手冊-30HRS》實際設定）。
所有路徑都相對於 `--workspace`（預設為執行指令時的目錄，也就是 workspace 根目錄）。
可用 Markdown 行內語法（`**粗體**`、`` `程式碼` ``）的欄位另外標註。

## 來源與輸出

| 欄位 | 必填 | 說明 | 範例 |
|---|:-:|---|---|
| `source_dir` | ✅ | 原稿資料夾 | `講義` |
| `source_glob` | | 原稿檔名樣式；成品同名檔會自動排除 | `[0-9][0-9]_*.md` |
| `poster_dir` | | 章主視覺資料夾；不存在就不放海報 | `海報` |
| `poster_glob` | | 海報檔名樣式，檔名開頭的數字＝章號 | `[0-9][0-9] *.png` |
| `output_dir` | | 輸出資料夾，**建議與 `source_dir` 相同**（Markdown 版的圖片路徑才有效） | `講義` |
| `output_name` | ✅ | 輸出檔名（不含副檔名），會產生 `.md` 與 `.pdf` | `AI Agent 架構師訓練手冊-30HRS` |
| `node_modules` | | 含 `mermaid`、`@highlightjs/cdn-assets` 的資料夾；找不到會改找 skill 內的 `node_modules` | `工具/node_modules` |

## 書籍資訊

| 欄位 | 必填 | 說明 |
|---|:-:|---|
| `title` | ✅ | 書名（不含徽章），用在書名頁、頁尾、PDF 中繼資料 |
| `title_cover_html` | | 封面書名的 HTML，可用 `<br>` 控制斷行；省略時用 `title` |
| `badge` | | 橘框徽章，例如 `30HRS`；頁尾與書名顯示為「書名（徽章）」 |
| `subtitle` | | 副標，封面與書名頁顯示 |
| `tagline` | | 封面標語一句 |
| `edition` | | 版次，例如 `第 1 版　2026 年 9 月` |
| `cover_kicker` | | 封面左上英文書系字樣 |
| `cover_stats` | | 封面統計列 HTML，`<span>` 包住的字會放大、變橘色 |
| `cover_footer_left` | | 封面底部左側字樣 |
| `author`、`keywords` | | PDF 中繼資料 |

## 代表圖示 `emblem`

| 欄位 | 說明 |
|---|---|
| `core_top`、`core_bottom` | 六角形核心的兩行字（例 `AI`／`AGENT`） |
| `nodes` | 外圈節點名稱，建議 6 個、每個 ≤ 6 個大寫字母 |
| `accent_nodes` | 以橘色強調的節點（最多 2 個） |

## 前置頁

| 欄位 | 說明 |
|---|---|
| `title_page_rows` | 書名頁資料表：`[["欄名", "內容"], …]`；內容可用行內 Markdown |
| `howto.intro` | 「如何使用本書」第一段；可用行內 Markdown |
| `howto.structure_intro`、`howto.structure` | 每章固定結構：`[["段落名稱", "說明"], …]` |
| `howto.admonitions` | 提示框圖例：`[["tip｜warning｜info｜danger", "標題", "說明"], …]` |

## 前言 `preface`（可省略）

| 欄位 | 說明 |
|---|---|
| `chapter_num` | 哪一個章號當前言（通常是 `0`） |
| `title` | 前言標題，省略時用原稿 front matter 的 `title` |
| `kicker` | 前言扉頁左上英文字樣，預設 `PREFACE` |

省略 `preface` 時，所有原稿都必須屬於某一篇。

## 章扉頁資訊 `opener_meta`

`[["顯示名稱", "front matter 欄位"], ["顯示名稱", "欄位", "code"]]`——第三個元素為 `"code"` 時以等寬字顯示。
原稿沒有該欄位時自動略過。

## 篇 `parts`（必填）

```json
{"name": "第一篇", "title": "架構思維與 AI 協作", "span": "S01～S05", "chapters": [1, 5],
 "desc": "篇導讀，一段 60～100 字。"}
```

- `chapters` 是**含頭尾**的章號範圍；每一章（前言以外）必須恰好屬於一篇，否則建置時報錯。
- `span` 為顯示用的範圍字樣，可省略。
- 分篇依據優先序：原稿中已有的學習階段（例如課程總覽的「四個學習階段」圖）→ 使用者指定 → 依主題自行歸納（3～5 篇為宜）。

## 索引 `index_terms`

`[["顯示名稱", "Python 正規式"], …]`，挑選原則見 [book-structure.md](book-structure.md) 第 6 節。
JSON 中反斜線要寫兩次：`"\\bService\\b"`、`"CLAUDE\\.md"`。
