---
name: operation-creator-skill
description: 針對指定資料夾中的專案（.NET MVC／Razor Pages、Flask、Node 網站），自動啟動專案、盤點所有功能、逐一實際操作並擷取 4K 畫面，搭配 mermaid 圖解與台灣腔沉穩男聲旁白、180px 紅棕色黑體繁中字幕，為每個專案錄製一支功能操作教學影片，輸出 教學影片/{專案資料夾名稱}.mp4。當使用者說「幫這個專案錄操作影片」「把範例專案做成教學影片」「啟動專案並操作所有功能錄影」「逐一製作專案操作說明影片」「專案功能導覽影片」時使用。
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, PowerShell, mcp__playwright__browser_navigate, mcp__playwright__browser_snapshot, mcp__playwright__browser_take_screenshot, mcp__playwright__browser_click, mcp__playwright__browser_type, mcp__playwright__browser_resize, mcp__playwright__browser_evaluate, mcp__playwright__browser_wait_for
---

# 專案功能操作教學影片

輸入是一個**資料夾**，輸出是每個專案一支 4K 操作教學影片。
重點在「**真的把專案跑起來、把每個功能操作一遍、講清楚它為什麼這樣設計**」。

## 與 create-video-skill 的分工（相依）

語音、字幕、圖解、擷取、合成這半段**直接使用** `create-video-skill` 的腳本與規範，不另外複製一份：

```
.claude/skills/create-video-skill/scripts/narrate.py    旁白 TTS、時間軸、ASS/SRT 字幕
.claude/skills/create-video-skill/scripts/diagram.py    mermaid 圖解、標題卡、重點卡
.claude/skills/create-video-skill/scripts/capture.py    Playwright 4K 操作擷取
.claude/skills/create-video-skill/scripts/compose.py    4K MP4 合成、字幕燒錄
```

本 skill 補上前半段——**專案 → 功能清單 → 分鏡**——以及交付前的自動驗收：

```
scripts/launch.py      列出專案、挑空的連接埠啟動、斷言頁面身分、只停自己的行程
scripts/inventory.py   靜態掃原始碼 + 實際爬網站 → features.json 功能清單
scripts/qa.py          規格、爆音、字幕一致、簡體字、金鑰外洩、場景節奏、功能覆蓋率
```

旁白寫法、語音參數、字幕規格的細節以 create-video-skill 的 `references/` 為準
（`narration-style.md`、`tts-audio.md`、`subtitle-ass.md`、`scene-capture.md`、`video-compose.md`）。
本 skill 的 `references/` 只寫**操作錄影特有**的部分。

---

## 固定規格（使用者需求，不可更動）

| 項目 | 規格 |
|---|---|
| 影片 | 3840×2160 MP4、H.264 yuv420p、30fps、AAC 48kHz |
| 旁白 | `zh-TW-YunJheNeural`（edge-tts 唯一台灣男聲）、rate `-10%`、pitch `-4Hz`，沉穩平順如說書 |
| 爆音 | 每句淡入 40ms／淡出 60ms、片頭 0.3 秒與片尾 0.6 秒靜音，首尾樣本為 0 |
| 口吻 | 自然口語、不念稿，技術點講「是什麼 → 為什麼 → 會踩什麼坑」 |
| 字幕 | 繁體中文、**180px**、紅棕色 `#B04A32`（ASS `&H00324AB0`）、Microsoft JhengHei 粗體、單行 ≤ 18 字、與旁白逐字一致 |
| 圖解 | 看不見的東西（架構、請求流程、授權判斷、資料模型、狀態）用 mermaid |
| 輸出 | `教學影片/{專案資料夾名稱}.mp4` ＋ 同名 `.srt`，每個專案一支 |

---

## 流程

每一步都有可驗證的產出，前一步沒過不進下一步。工作檔全部放 scratchpad 的 `$WORK/{專案名}/`。

```
0 列專案 → 1 讀懂專案 → 2 啟動 → 3 盤點功能 → 4 功能操作規劃 → 5 分鏡與旁白
→ 6 旁白合成 → 7 圖解與擷取 → 8 合成 → 9 驗收與清理
```

### 0. 列出專案、決定檔名

```powershell
python .claude/skills/operation-creator-skill/scripts/launch.py list --root "<指定資料夾>" --videos "教學影片"
```

- 資料夾裡**兩個以上**子資料夾是專案 → 每個一支影片，檔名＝**該子資料夾名稱**。
- 否則整個資料夾就是一個專案 → 檔名＝**指定資料夾名稱**（不是 csproj 名稱；十五個單元的 csproj 全叫 `RagDemo`）。
- 使用者**明確指定檔名**時以指定為準（`教學影片/{指定名稱}.mp4`），不必再用資料夾名。
- `video_exists: true` 的專案，**先問使用者**要覆蓋、略過，還是另存 `{名稱}_操作示範.mp4`。
  不可默默覆蓋既有影片——那可能是另一套流程做好、已經驗收過的成品。

多個專案時**一次做一個**，做完（含停掉伺服器）才換下一個。

### 1. 讀懂專案（不可略過）

先讀、後動手。依序看：

1. 專案說明：`README.md`、`操作說明.md`、`驗收報告.md`、`測試報告.md`、`執行專案.ps1`
2. 進入點與組態：`Program.cs`／`run.py`、`appsettings.Development.json`——**只為了找模擬模式開關與種子帳號**，內容絕不上畫面、不進旁白
3. 功能實作：Controller／Service／View，搞清楚每個功能背後**真正做了什麼**

產出 `$WORK/{名稱}/notes.md`：專案目的、技術堆疊、功能清單初稿、每個功能的技術重點與坑、需要的模擬開關。
對不上或看不懂的地方**問使用者**，不要編。影片會把錯誤放大。

### 2. 啟動專案

```powershell
python .claude/skills/operation-creator-skill/scripts/launch.py start `
  --project "<專案資料夾>" --state "$WORK/{名稱}/launch.json" `
  --marker "<本專案才有的字串>" --absent "<別的專案才有的字串>" --probe /api/public/ping
```

- 一律用 `launch.py` 挑**沒人用的埠**（5310 起），不沿用專案預設埠——別的站可能正佔著。
- `--marker`／`--absent` 是**身分斷言**：從選單或首頁挑一個本專案獨有的字串。斷言失敗（結束碼 3）就停下查原因，不可擷取。
- 需要外部服務（資料庫、LLM、付費 API）而本機沒有時，用 `--env Key__Sub=true` 開模擬模式，並在旁白**明講**這是模擬。
- 細節與疑難排解見 [references/project-launch.md](references/project-launch.md)。

### 3. 盤點所有功能

```powershell
python .claude/skills/operation-creator-skill/scripts/inventory.py `
  --project "<專案資料夾>" --url <launch.json 的 url> --out "$WORK/{名稱}/inventory" [--login login.json]
```

產出 `features.json`（每項功能有 `id`）、`features.md`、`thumbs/*.png`。
**打開 thumbs 逐張看過**，再對照 notes.md 補齊：來源為 `code` 的項目是爬蟲沒走到的（POST 動作、需要參數的頁），逐一判斷要示範或排除。

### 4. 功能操作規劃

為每一項功能寫一列操作規劃：**怎麼進入 → 輸入什麼示範資料 → 按什麼 → 預期看到什麼 → 技術重點 → 需不需要圖解**。
先用 `mcp__playwright__*` 工具或 `capture.py --headed` 實際走一遍，確認按鈕、選擇器、結果都存在，
**確認可行後**才寫進分鏡。會改變資料的流程（上傳、改版、驗收）要**整條彩排一次**並把每頁結果存檔，
旁白裡的數字只能來自彩排紀錄；彩排完用 `stop`／`start` 重啟，讓正式擷取從乾淨狀態開始。規則見 [references/feature-walkthrough.md](references/feature-walkthrough.md)。

### 5. 分鏡與旁白

寫 `$WORK/{名稱}/storyboard.json`（格式同 create-video-skill，另加 `feature`／`exclusions` 欄位）。骨架：

```
開場 title → 架構 diagram → [每個功能：概念 diagram（需要時）→ 操作 screen × N → 坑 slide（需要時）] → 總結 slide
```

- **一個 screen 場景 = 一個標示框 = 1～2 句旁白（< 15 秒）**。screen 不運鏡，長了就是靜止畫面。
- 每個 screen 場景填 `"feature": "fXX"`；不示範的功能寫進 `exclusions` 並附理由（例如「登出：會結束工作階段，於結尾口頭說明」）。
- URL 用 `launch.json` 裡的實際網址寫成絕對路徑。
- 旁白依 create-video-skill 的 `references/narration-style.md`，外加 feature-walkthrough.md 的「操作旁白」規則。

### 6. 旁白合成

```powershell
python .claude/skills/create-video-skill/scripts/narrate.py --storyboard "$WORK/{名稱}/storyboard.json" --outdir "$WORK/{名稱}/audio"
```

跑完先看 `timeline.json`：screen 場景 ≥ 15 秒就拆場景後**重跑 narrate**（場景邊界會變）。
遇到 edge-tts 503 已有自動重試；仍失敗就等幾分鐘整支重跑，不要改旁白。

### 7. 圖解與操作擷取

```powershell
python .claude/skills/create-video-skill/scripts/diagram.py --storyboard "$WORK/{名稱}/storyboard.json" --outdir "$WORK/{名稱}/assets"
python .claude/skills/create-video-skill/scripts/capture.py --storyboard "$WORK/{名稱}/storyboard.json" --outdir "$WORK/{名稱}/assets"
```

擷取前再確認一次伺服器還活著、身分斷言仍成立。擷取後**用 Read 抽看影格**：
標示框有沒有框對、結果有沒有出現、畫面有沒有金鑰或個資。

> **為什麼是「關鍵影格」不是螢幕錄影**：Playwright 的 `record_video` 輸出 VP8 webm，4K 下文字糊、掉幀，
> 而且無法讓畫面停留時間配合旁白。改成每個操作步驟擷取 3840×2160 無損影格、依旁白長度排時間、
> 以淡入淡出銜接——畫質銳利且音畫精準對位，這就是本 skill 的「錄影」。

### 8. 合成

```powershell
python .claude/skills/create-video-skill/scripts/compose.py --storyboard "$WORK/{名稱}/storyboard.json" `
  --audio "$WORK/{名稱}/audio" --assets "$WORK/{名稱}/assets" --out "教學影片/{名稱}.mp4"
```

4K x264 合成一支約 20～40 分鐘，用 `run_in_background`。想先看效果可加 `--nvenc` 出草稿，定稿一定用 x264。

### 9. 驗收與清理

```powershell
python .claude/skills/operation-creator-skill/scripts/qa.py --video "教學影片/{名稱}.mp4" `
  --storyboard "$WORK/{名稱}/storyboard.json" --audio "$WORK/{名稱}/audio" `
  --features "$WORK/{名稱}/inventory/features.json" --workspace .
python .claude/skills/operation-creator-skill/scripts/launch.py stop --state "$WORK/{名稱}/launch.json"
Remove-Item .\debug.log -Force -ErrorAction SilentlyContinue      # Chromium 會留在工作目錄
```

`qa.py` 全過之後，再做程式驗不到的：抽 5 張影格目視（開頭、中段、結尾）、確認每個操作結果畫面正確。
回報時列出：影片長度、場景數、檔案大小、**功能覆蓋（示範 N／總數，排除項與理由）**、模擬模式使用情況，
以及錄製過程中**發現的專案問題**（功能壞掉、與文件不符）——這些是很有價值的副產品，不要藏起來。

---

## 硬性規則

- **不可虛構功能或結果。** 畫面上沒出現的東西不能講成有；操作失敗就修流程或排除，不能用旁白帶過。
- **不可停掉別人的行程。** 只用 `launch.py stop` 停自己啟動的 pid。埠被佔就換埠。
- **金鑰與個資不上畫面、不進旁白。** 不擷取設定檔、環境檢查頁若會顯示連線字串就先確認遮罩；登入密碼只在密碼欄（顯示為圓點）輸入，不唸出來。
- **模擬就要說是模擬。** 用了模擬模式的畫面，旁白要講清楚「這是模擬值，不代表真的連上」。
- **CJK 路徑走 PowerShell 或 Python**，不用 Git Bash 操作 `教學影片`／`範例` 等中文路徑。
- **檔案一律 UTF-8 無 BOM**；中間檔只放 scratchpad，專案目錄只多出 `教學影片/{名稱}.mp4` 與 `.srt`。

## 參照文件

| 文件 | 內容 |
|---|---|
| [專案啟動](references/project-launch.md) | 專案類型偵測、連接埠、身分斷言、模擬模式、登入、停止與疑難排解 |
| [功能操作與分鏡](references/feature-walkthrough.md) | 功能覆蓋原則、操作規劃表、場景模式、mermaid 選圖、操作旁白、分鏡範例 |
| [分鏡範例](references/storyboard-example.json) | 實測可跑的完整 storyboard：title／diagram／screen（`focus`）／slide、`feature`、`exclusions` |
| create-video-skill `references/` | 旁白風格、TTS 與去爆音、ASS 字幕、擷取、合成、驗收清單 |
