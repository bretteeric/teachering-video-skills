---
name: create-video-skill
description: 將提示詞或說明文件轉製為 4K 教學影片。當使用者要求「製作教學影片」、「錄製操作示範」、「把這份文件做成影片」、「產生 4K 影片與旁白字幕」，或需要台灣腔沉穩男聲旁白、繁體中文字幕、mermaid 圖解補充說明時使用。輸出為 教學影片/{檔名}.mp4。
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, PowerShell, mcp__playwright__browser_navigate, mcp__playwright__browser_snapshot, mcp__playwright__browser_take_screenshot, mcp__playwright__browser_click, mcp__playwright__browser_type, mcp__playwright__browser_resize, mcp__playwright__browser_evaluate, mcp__playwright__browser_wait_for
---

# 4K 教學影片製作規範

將一份「提示詞輸入」（說明文件、功能規格或直接的文字指示）轉製為**帶旁白與字幕的 4K 教學影片**。

本文件負責 **流程與決策**；各階段的實作細節見 `references/`，可直接執行的程式見 `scripts/`。

---

## 核心原則：旁白腳本是唯一事實來源

整條管線只有一個事實來源 —— **旁白腳本 `narration.txt`**。

```
narration.txt（一行 = 一句旁白）
        │
        ├──► TTS 合成每句 ──► 量測實際長度 ──┐
        │                                    ├──► 全域時間軸
        └──► 同一份文字切成字幕 cue ──────────┘
                                              │
                        場景長度 = 該場景旁白總長  ◄┘
```

由此得到三項保證，**不可用其他方式取代**：

1. **字幕文字 100% 正確** —— cue 文字是旁白字串的 substring，不經任何轉錄或辨識，不可能出錯。
2. **音畫零飄移** —— 時間軸來自 ffprobe 實測音檔長度，不是估算。
3. **畫面配合語音** —— 場景長度由旁白決定，不是先剪好畫面再硬塞旁白。

> **絕對禁止**用 Whisper／ASR 把成品音訊轉回字幕。那會引入辨識錯誤，違反「字幕需要完全正確」的要求。ASR 只能當**驗收比對**用（見 `references/qa-checklist.md`）。

---

## 輸入解析與命名

### 檔名規則（決定輸出路徑）

| 輸入形式 | 影片檔名 |
|---|---|
| 指定檔案，如 `docs/生命偵測系統第一階段系統文件.md` | 取**主檔名**（去副檔名）→ `生命偵測系統第一階段系統文件.mp4` |
| 純文字提示詞，未指定檔案 | 取內容第一個 H1 標題；無標題則取首句 ≤20 字 |

輸出固定為 **`教學影片/{檔名}.mp4`**（專案根目錄下）。資料夾不存在就建立：

```powershell
New-Item -ItemType Directory -Force -Path "教學影片" | Out-Null
```

工作檔一律放 scratchpad，**不要**污染專案目錄；只有最終 `.mp4`、`.srt` 進 `教學影片/`。

### 讀懂內容再動工（不可略過）

拿到輸入後，**先完整讀完**，再產出一份 `storyboard.json`。釐清這四件事：

1. **教學目標** —— 看完影片的人應該會做什麼？
2. **操作流程** —— 有哪些實際步驟？每步在哪個畫面、點哪裡、預期看到什麼？
3. **需要圖解的概念** —— 架構、資料流、狀態轉換、時序 → 這些**用 mermaid 補充說明**，光靠截圖講不清楚。
4. **技術重點** —— 為什麼這樣設計？有什麼坑？這是「詳細說明技術內容」的實質。

內容有歧義或缺漏時，**先問使用者**，不要自行編造操作步驟——影片會把錯誤放大。

---

## Storyboard 資料契約

```jsonc
{
  "title": "生命偵測系統第一階段",
  "output": "教學影片/生命偵測系統第一階段.mp4",
  "voice": { "name": "zh-TW-YunJheNeural", "rate": "-10%", "pitch": "-4Hz", "volume": "+0%" },
  "scenes": [
    {
      "id": "s01",
      "type": "title",                    // title | diagram | screen | slide
      "heading": "生命偵測系統",
      "subheading": "第一階段功能導覽",
      "narration": [
        "哈囉，這一支影片我們要來看的是生命偵測系統的第一階段。",
        "我會帶你從整體架構開始，一路走到實際的操作畫面。"
      ]
    },
    {
      "id": "s02",
      "type": "diagram",
      "mermaid": "diagrams/architecture.mmd",
      "narration": ["先看整體架構。資料從感測器進來以後，會先經過閘道器。"]
    },
    {
      "id": "s03",
      "type": "screen",
      "url": "http://localhost:5000/devices",
      "steps": [
        { "action": "goto",  "url": "http://localhost:5000/devices" },
        { "action": "click", "selector": "#btn-add", "highlight": true },
        { "action": "type",  "selector": "#serial", "text": "UWB-3000-001" }
      ],
      "narration": ["接著我們回到裝置管理頁面，這邊按下新增。"]
    }
  ]
}
```

**場景長度 = 該場景 `narration` 各句實測長度總和 + 句間停頓。** 不另外指定 duration。

`type` 的用途分工：

- `title` —— 開場／段落標題卡
- `diagram` —— mermaid 圖解，用於講**看不見的東西**（架構、流程、時序）
- `screen` —— Playwright 實際操作擷取，用於講**看得見的東西**（功能操作）
- `slide` —— 純文字重點卡，用於收斂總結

---

## 製作流程（六階段）

每階段都有可驗證的產出，**前一階段沒過不要進下一階段**。

### 階段 1 — 解析與分鏡

讀完輸入 → 寫 `storyboard.json` + `narration.txt`。
**產出檢查**：每個 scene 都有 narration；每句 ≤ 45 字（過長難斷句、聽起來像念稿）。

### 階段 2 — 旁白腳本

依 `references/narration-style.md` 撰寫。這是影片品質的關鍵，**不是把文件唸一遍**。
**產出檢查**：隨機抽三句朗讀，是否像「人在講話」而非「念稿」。

### 階段 3 — 語音與時間軸

```powershell
python .claude/skills/create-video-skill/scripts/narrate.py `
  --storyboard "$WORK/storyboard.json" --outdir "$WORK/audio"
```
產出 `narration.wav`（48kHz 單聲道）、`timeline.json`、`subtitle.ass`、`subtitle.srt`。
**產出檢查**：首尾樣本為 0（無爆音）、峰值 ≤ -1.0 dBFS。

### 階段 4 — 素材擷取

```powershell
python .claude/skills/create-video-skill/scripts/diagram.py --storyboard ... --outdir "$WORK/assets"
python .claude/skills/create-video-skill/scripts/capture.py --storyboard ... --outdir "$WORK/assets"
```
產出每個場景的 3840×2160 PNG。
**產出檢查**：每張都是 3840×2160，文字銳利不糊。

### 階段 5 — 合成

```powershell
python .claude/skills/create-video-skill/scripts/compose.py `
  --storyboard ... --audio "$WORK/audio" --assets "$WORK/assets" --out "教學影片/{檔名}.mp4"
```

### 階段 6 — 驗收

跑完 `references/qa-checklist.md` 的每一項才算完成。

---

## 硬性規則（本機環境實測，違反會失敗）

### 路徑與編碼

- **CJK 路徑一律走 Python 或 PowerShell，絕不用 Git Bash。** 本機 Git Bash 會把 `教學影片` 之類的中文路徑變成亂碼（實測 `ls` 直接找不到檔案）。Python 的 `os`/`pathlib` 與 PowerShell 都正常。
- 所有寫檔用 **UTF-8 無 BOM**。ASS／SRT 帶 BOM 會讓 libass 第一句解析異常。

### 語音

- 台灣男聲**只有 `zh-TW-YunJheNeural` 一個**（實測 `edge-tts --list-voices`）。其餘 zh-TW 皆為女聲，zh-CN 系列是大陸腔，不符需求。
- **edge-tts 7.x 不支援 SSML。** 原始碼對輸入做 `escape()`，`<break>`／`<prosody>` 會被當成字面文字唸出來。沉穩與停頓只能靠 `rate`／`pitch` 加**腳本寫法**達成。
- **每段結尾固定附帶約 0.95 秒靜音**（實測與句長無關），必須裁掉再補上設計的停頓，否則句間變成 1.25 秒死氣。
- `WordBoundary` 事件要明確指定 `boundary="WordBoundary"`，**預設是 `SentenceBoundary`**，不指定會拿到 0 筆。

### 字幕

- ASS 顏色是 **`&HAABBGGRR`（BGR 反序）**，不是 RGB。`#B04A32` → `&H00324AB0`。寫錯會變成藍綠色。
- `PlayResX/PlayResY` 必須設 **3840/2160**，否則 `Fontsize: 180` 不等於 180 實際像素。
- 180px 下每行**最多 18 個全形字**（實測 JhengHei Bold 全形進距正好 180px，18 字 = 3240px，左右各留 160px 邊界）。超過會換行吃掉畫面。
- **cue 時間直接用 `WordBoundary` 原始 offset，不要等比縮放。** 拿「音檔長度 ÷ 最後一詞結束」當比例，會被那 0.95 秒尾端靜音灌水成 1.12～1.21 倍，讓每句最後一個 cue 晚將近一秒。
- **算字數要排除標點**：`WordBoundary` 的 `text` 不含標點與空白，用 `len(cue)` 對位會逐個標點累積偏移。

### 影像

- 4K 截圖用 **viewport 1920×1080 + `device_scale_factor=2`**，不要直接開 3840 viewport。前者文字以 2 倍密度渲染後輸出 3840×2160，銳利；後者所有元素會小到看不清。
- **不要**用 Playwright 的錄影功能：輸出 VP8 webm，文字邊緣糊，且 4K 下掉幀。改用「關鍵畫面截圖 + ffmpeg 合成運鏡」。

---

## 參照文件

| 文件 | 內容 |
|---|---|
| [旁白撰寫規範](references/narration-style.md) | 台灣口語、沉穩說書感、避免念稿的具體寫法 |
| [語音與音訊處理](references/tts-audio.md) | edge-tts 參數、去爆音鏈、響度正規化 |
| [ASS 字幕規範](references/subtitle-ass.md) | 180px 紅棕色黑體、BGR 陷阱、繁中斷句 |
| [場景擷取](references/scene-capture.md) | Playwright 4K 擷取、mermaid 圖解產生 |
| [影片合成](references/video-compose.md) | ffmpeg 4K 編碼、運鏡、轉場、字幕燒錄 |
| [驗收檢查表](references/qa-checklist.md) | 交付前必跑的檢查項 |
