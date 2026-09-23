---
name: image-geneate-skill
description: 讀取 workspace 底下 `講義/` 中「最後新增」的 .md 講義，用瀏覽器連到 ChatGPT 執行「製作圖像／創作圖像」，產生 1024×1536 直式高解析度的樂高積木科技風單元海報（扁平明亮、版面精簡），再把原圖回存到 workspace 的 `海報/`。當使用者說「產生海報」「講義轉海報」「幫這一課做海報」「創作圖像」時使用。
allowed-tools: Bash(playwright-cli:*) Bash(npx:*) Bash(ls:*) Bash(mkdir:*) Bash(mv:*) Bash(node:*)
---

# 講義 → ChatGPT 創作圖像 → 海報（樂高積木科技風）

把一份單元講義（Markdown）轉成一張與系列風格一致的直式教學海報，全程在 ChatGPT 裡完成，
最後把 ChatGPT 產出的**原始高解析度檔**下載回 `海報/`。

風格固定為**樂高積木科技風**：積木搭建的技術意象、樂高原色、扁平明亮、**版面最多 5 個文字區塊**。
完整規格見 [references/poster-style.md](references/poster-style.md)，寫提示詞前先讀過。

- 所有路徑相對於**目前的 workspace**（`./講義`、`./海報`），同一份 skill 複製到別門課的
  workspace 都能用。
- 課程名取自 workspace 的上層資料夾名
  （`E:\AI工程教案計畫\SQL Server RAG與jev決策應用\workspace` → 課程名 `SQL Server RAG與jev決策應用`）。
  太長或不適合上海報時，改用講義 H1（沒有 H1 時用 front matter 的 `title:`）的課程名，並在回報時說明。
- **所有 playwright-cli 指令都必須在 workspace 根目錄執行**：`run-code` 的相對路徑是相對於
  當初執行 `open` 的工作目錄（已實測）。

---

## 前置條件

| 項目 | 檢查方式 |
|---|---|
| `playwright-cli` | `playwright-cli --version`；沒有就 `npm install -g @playwright/cli@latest` |
| 已登入的 ChatGPT | 第一次會停在登入頁，**請使用者自己在跳出的視窗登入**，之後靠 `--persistent` 記住 |
| `講義/` 底下有 .md | 沒有就直接回報，不要自己編一份講義 |

> **不要用截圖當海報。** 截圖不會是 1024×1536 原圖。要拿原檔，走步驟七的 `save-image.js`
> （頁內 fetch 原圖網址取回位元組），並以步驟八的尺寸檢查把關。

---

## 步驟一　選定講義

```bash
ls -t 講義/*.md | head -1
```

- `-t` 依修改時間排序，天然排除 `講義/*.pdf` 與 `講義/images/`。
- 使用者若有給參數（`$ARGUMENTS`，例如 `06_Embedding與SQL向量儲存.md` 或 `06`），**以參數為準**。

**選好之後一定要先回報選中哪一支，再往下做。**
「最後新增」是依 mtime，未必是編號最大的那一支。
編號與時間不一致時要明講，讓使用者有機會改用參數指定。

讀取該檔取出下列五項，對應海報的五個區塊（取材對應表見
[references/poster-style.md](references/poster-style.md)）：

| 取出 | 餵進海報 |
|---|---|
| H1 標題（或 front matter `title:`）、Section 序號（或 `session:`） | 標題磚條 |
| 該單元的學習目標 → 濃縮成一句白話 | 副標 |
| 時間配置 | 時間行（本課程固定 `120 分鐘｜觀念 20・示範 25・實作 65・驗收 10`） |
| 3～5 個關鍵技術名詞＋各一行極短白話註解 | 技術名詞磚 |
| 單元驗收成果一句 | 驗收磚條 |

另外挑出**一個核心技術物件**（資料庫、PDF 文件、向量、路由、聊天室…）當主視覺意象。
**只取這些，不要把講義其他段落塞進提示詞** —— 區塊一多，中文字就會糊掉。

## 步驟二　決定海報檔名

沿用系列既有命名：`NN 標題.png`（**半形空格分隔，非底線**）。

- `NN`：md 檔名前綴，`06_Embedding與SQL向量儲存.md` → `06`
- `標題`：主標是**再創作**的短句（`06_Embedding與SQL向量儲存.md` → `06 把文字變成向量.png`），不是照抄檔名。
  優先序：使用者指定 > ChatGPT 建議的主標 > md 的 H1（沒有 H1 時用 front matter 的 `title:`）。命名慣例見
  [references/poster-style.md](references/poster-style.md)。

```bash
mkdir -p 海報
```

`海報/NN *.png` 已存在時**不要覆蓋**：先問使用者要重畫（存成 `NN 標題 v2.png`）還是跳過。

## 步驟三　開啟瀏覽器（必須 `--headed`）

```bash
playwright-cli -s=chatgpt open https://chatgpt.com --persistent --headed --browser=chrome
playwright-cli -s=chatgpt snapshot
```

- **`--headed` 不可省略。** 實測（2026-09）：headless 會被 Cloudflare 卡在標題「請稍候...」的
  驗證頁，reload 也過不去；加上 `--headed` 後才順利進站。
- `--persistent`：保留登入狀態，之後每次跑不必重登。
- `--browser=chrome`：用真實 Chrome 通道；沒裝 Chrome 才改 `--browser=msedge`。
- snapshot 後**先判斷畫面狀態**：
  - 出現「登入 / 免費註冊」或人機驗證 → 停下來，請使用者在已開啟的視窗登入，再重新 snapshot。
    （登出狀態的畫面文字長這樣：`登入即可取得以儲存的聊天為基礎的回答，還可以創作圖像並上傳檔案。`）
  - 已在對話畫面 → 繼續。

## 步驟四　選定對話位置（預設：不進專案）

**預設直接在新對話發訊息，不必進任何 ChatGPT 專案。** 樂高風是扁平的固定配色與固定版面，
一致性靠步驟五的提示詞就夠，不像水墨風得靠同專案的歷史對話帶風格。

只有在**使用者明確指名某個 ChatGPT 專案**時（`$ARGUMENTS` 或對話中指定）才走這一段：
從 snapshot 的側欄找到名稱相符的連結並點擊，**不要硬寫死 URL**（專案 id 因帳號而異）。

```bash
playwright-cli -s=chatgpt snapshot            # 每次點擊前重新取 snapshot
playwright-cli -s=chatgpt click "<該連結的 ref>"
```

側欄沒展開時先點「開啟側邊欄」，必要時展開「專案 / Projects」。
在**專案頁面本身**的輸入框發訊息，新對話才會歸屬在該專案底下。
側欄常點不動，鍵盤的解法見文末「驗證狀態」。

## 步驟五　附上講義並執行「製作圖像」

**先附檔，再選圖像工具，最後送出提示詞。**

輸入框左側的 `+` 按鈕，其可及名稱是 **「新增檔案和更多內容」**（已實測 zh-TW 介面）。
點開後的選單項目為：`新增相片`、`網路搜尋`、**`製作圖像`**、`深度研究`、**`新增檔案`**。

```bash
playwright-cli -s=chatgpt snapshot
playwright-cli -s=chatgpt click "<「新增檔案和更多內容」的 ref>"
playwright-cli -s=chatgpt snapshot
playwright-cli -s=chatgpt click "<「新增檔案」的 ref>"
playwright-cli -s=chatgpt upload "./講義/<選中的檔名>.md"
```

「新增檔案」有可能再展一層子選單（`從電腦上傳` / `Google 雲端硬碟`）——若 snapshot 出現子選單，
先點「從電腦上傳」再 `upload`。同理，登入後「製作圖像」可能被收在「更多」底下。

> 一律用附檔，不要把一萬多字的中文講義 `type` 進輸入框——Windows shell 的編碼與引號很容易把
> 內容打斷。若檔案選擇器沒被攔截，改用 `playwright-cli -s=chatgpt drop "<輸入框 ref>" --path="./講義/<檔名>.md"`。

接著重新開一次 `+` 選單，點 **`製作圖像`**。
不同版本字樣可能不同，逐一比對這組候選：

```
製作圖像 / 創作圖像 / 建立圖片 / 產生圖片 / 圖片 / Create image / Create an image
```

都找不到時，改用純文字提示詞（開頭寫「請創作圖像：」）送出也能觸發圖像生成；
此時下面那段固定的前置提示詞一樣要放在最前面。

送出以下提示詞。**第一行的前置提示詞是固定的，每次都必須原樣帶上**，其餘 `<...>`
由步驟一、二填入：

```text
製作海報時，採用高解析度，並以樂高積木科技風繪製：扁平向量、塑膠亮面、樂高原色、明亮乾淨。

請依附件講義《<md 檔名>》創作一張教學海報圖像。

規格：直式 1024×1536、高解析度、繁體中文、文字清晰不可變形或亂碼、不可出現簡體字；
英文技術名詞維持原文拼寫正確。
系列：<課程名> 單元海報第 <NN> 張。風格完全以下列規格為準，不需參考任何先前對話。
風格：白底或極淺藍白漸層，底層可鋪很淡的樂高圓凸點陣列；扁平向量、塑膠亮面、圓角、柔和單向投影。
配色用樂高原色，以藍為主色、黃為強調色，紅與綠僅點綴。
不要水墨、不要紙質肌理、不要書法或印章、不要金屬反射、不要寫實攝影。
版面（由上而下，整張最多這 5 個文字區塊，字要大、留白要多）：
1. 頂部一條藍色長條積木：Section <NN>｜<主題>（白色粗體大字）
2. 其下一行深灰副標：<一句白話主旨>；再一行小字：<時間行>
3. 中段主視覺（約佔版面 40%）：用樂高積木搭建的 <核心技術物件>，旁邊站一個樂高小人講師
   （戴眼鏡、拿平板）；區塊之間用樂高顆粒串成的線條或箭頭表示流程方向
4. 3～5 塊 2x2 彩色積木，每塊寫一個技術名詞，下方一行不超過 12 字的白話註解：<技術名詞清單>
5. 底部一條黃色長條積木，深色粗體字寫驗收成果：<單元驗收成果>

除上述 5 區塊外不要再加任何文字或裝飾方框。
請直接輸出成品，不要先問我問題。
```

`<時間行>` 本課程固定填 `120 分鐘｜觀念 20・示範 25・實作 65・驗收 10`。
完整風格拆解與取材對應表見 [references/poster-style.md](references/poster-style.md)。

> **「簡易」是硬要求，不是形容詞。** 圖像模型畫小字中文很容易糊掉或跑出簡體字，
> 區塊少、字大是最有效的防呆。使用者要求補內容時，優先換掉現有區塊的文字，
> 而不是新增第 6 個區塊。

## 步驟六　等待生成

不要用 snapshot 輪詢，改成一次性等待（圖像生成常需 1～4 分鐘）：

```bash
playwright-cli -s=chatgpt run-code "async page => await page.waitForSelector('[data-testid=\"image-download-button\"], button[aria-label*=\"下載\"], button[aria-label*=\"Download\"]', { timeout: 240000 })"
```

逾時就 snapshot，看是被擋（額度、政策拒絕、驗證）還是還在畫，據實回報使用者。

## 步驟七　下載原圖並回存

```bash
node .claude/skills/image-geneate-skill/scripts/save-image.js
mv "海報/__latest-poster.png" "海報/<NN 標題>.png"
```

`save-image.js` 會去呼叫 `download-image.js`（在瀏覽器裡取得原圖位元組、回傳 base64），
再由 Node 解碼寫成固定檔名 `海報/__latest-poster.png`，最後由這裡改名。
它自己會驗 PNG 檔頭與位元組數，對不上就直接報錯，不會留下壞檔。

> **不要再用 `<a download>` 或 blob 觸發下載。** 實測（2026-09-09）那會讓**整個瀏覽器結束**
> （Session closed），接著 `download.saveAs()` 必定拿到
> "Target page, context or browser has been closed"。
> 而且這個版本的介面裡，圖片訊息**根本沒有下載鈕**（只有 編輯圖片／共享此圖像／更多動作），
> `button[aria-label*="下載"]` 只會誤中側欄常駐的「**下載應用程式**」。
> 完整實測紀錄寫在 [scripts/download-image.js](scripts/download-image.js) 檔頭。

> **為什麼是固定檔名再 mv：** run-code 的沙箱沒有 `process`，也沒有 `require`／`Buffer`／`fs`
> （已實測），檔名沒辦法用環境變數傳進去。`save-image.js` 是一般 Node 腳本，cwd 就是 workspace，
> 因此相對路徑 `海報/` 在任何一門課的 workspace 都通用。

## 步驟八　驗證與收尾

```bash
ls -l "海報/<NN 標題>.png"
```

確認尺寸真的是 1024×1536（明顯小很多就是抓到預覽圖，回步驟七重來）：

```powershell
Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile('<絕對路徑>'); "$($img.Width)x$($img.Height)"; $img.Dispose()
```

```bash
playwright-cli -s=chatgpt close
```

回報：選了哪份講義、存到哪個路徑、實際尺寸。

---

## 疑難排解

| 症狀 | 處理 |
|---|---|
| 標題一直是「請稍候...」、內文空白 | Cloudflare 擋 headless。加 `--headed` 重開（見步驟三） |
| snapshot 的 ref（`e15`）點不到 | ref **每次 snapshot 都會變**。每次點擊前重新 snapshot，用 role/name 比對，不要沿用舊 ref |
| 卡在人機驗證 | 視窗是開著的，請使用者手動通過，不要嘗試繞過 |
| 找不到使用者指名的專案 | 確認登入帳號正確；側欄可能要先展開。找不到就退回預設：直接在新對話發訊息（步驟四） |
| 圖含亂碼或簡體字 | 先**砍區塊**：文字區塊超過 5 個就刪到 5 個以內、把註解縮到 12 字以內，再補「繁體中文、字形完整、勿出現簡體或錯字」重生 |
| 畫面太花、不夠亮麗 | 提示詞補「純白背景、扁平向量、無材質紋理、無陰影堆疊」，並確認沒有要求寫實或 3D 算圖 |
| 積木感不足（像一般插畫） | 補「明顯的樂高圓凸點 stud、可辨識的磚塊分模線、塑膠亮面高光」 |
| 存出來只有幾百 KB | 抓到預覽圖了。`download-image.js` 只收長寬都 >= 1024 的 img；真正的把關是步驟八的尺寸檢查 |
| `Session closed` / `Target page... has been closed` | 有人又用 `<a download>` 或 blob 去觸發下載了。那會關掉整個瀏覽器，改用步驟七的 `save-image.js` |
| `save-image.js` 說「輸出裡沒有 ### Result」 | 瀏覽器沒開或已被關掉。重開步驟三，直接 `open` 那則對話的網址即可，圖還在不必重畫 |
| `save-image.js` 說「位元組數對不上」 | base64 在傳輸中被截斷，重跑一次；持續發生就把圖分段取回 |
| Google 登入被擋（「這個瀏覽器可能不安全」） | 自動化 Chrome 常被 Google SSO 拒絕。改用 Email + 密碼登入；真的不行才退而 `playwright-cli -s=chatgpt attach --cdp=chrome` 接管使用者自己開的 Chrome |
| 一則回覆有多張圖 | 腳本抓**最後一張**原尺寸圖；要指定別張就改 `download-image.js` 裡的 `full[full.length - 1]` |

## 驗證狀態

**已實測（2026-09，登出狀態的 zh-TW 介面）**

- `--headed` 才能通過 Cloudflare；headless 一定卡在「請稍候...」。
- `run-code` 沙箱沒有 `process`。
- `+` 鈕名稱為「新增檔案和更多內容」；選單含「製作圖像」「新增檔案」「新增相片」「網路搜尋」「深度研究」。

**已實測（2026-09-09，已登入的 zh-TW 介面，完整跑完一張海報）**

- **側欄點不動。** 專案列是 `div[role=button]` 手風琴（`aria-expanded`），
  滑鼠點擊（含 `force`、直接算座標）都會被 hover 覆蓋層攔截，甚至誤點進隔壁專案。
  **可行的是鍵盤：`el.focus()` 再 `page.keyboard.press('Enter')`。**
  展開後其對話連結的 href 就帶專案 id，據此組出 `/g/g-p-<id>-<slug>/project`。
  範例（舊佛學系列的專案）：`/g/g-p-6a9ff54767a8819196b8325c4e1708c8-fo-xue/project`。
  直接對這個網址 `goto` 會得到空白頁＋「再試一次」，一定要從側欄按鍵盤進去（客戶端路由）。
- **`+` 選單打不開**（鍵盤、滑鼠都試過）。附檔改走隱藏的 `input[type=file]`：
  `page.locator('input[type=file]').first().setInputFiles(<絕對路徑>)`，穩定可用（頁面上有 5 個）。
  圖像生成則用步驟五的純文字備援（開頭「請創作圖像：」）觸發，成功。
- **圖片訊息沒有下載鈕。** 可用的只有 編輯圖片／共享此圖像／按讚此圖像／更多動作
  （更多動作＝查看來源、開啟新分支）。`button[aria-label*="下載"]` 會誤中側欄的「下載應用程式」。
- **`<a download>` 與 blob 下載都會讓瀏覽器整個結束**，`download.saveAs` 因此必定失敗。
  改用頁內 fetch → base64 → Node 寫檔（`save-image.js`），已用 md5 驗證與瀏覽器下載的檔案逐位元組相同。
- run-code 沙箱同時沒有 `require`／`Buffer`／`fs`；4.6 MB 的 base64 可以完整回傳不被截斷。
- 圖片網址格式：`https://chatgpt.com/backend-api/estuary/content?id=file_...`（same-origin，帶 cookie 可直接 fetch）。

**尚未實測（2026-09-23 改版）**

- 上面兩段瀏覽器操作的實測結論，是在舊的佛學系列海報上跑出來的；**流程沒動，仍然有效**。
- 改掉的只有風格：步驟四改為預設不進專案、步驟五換成樂高積木科技風提示詞、
  `references/poster-style.md` 全面改寫。

**已實測（2026-09-23，樂高提示詞第一張：`海報/01 先把環境接通.png`）**

- **樂高提示詞一次就過，不用重生。** 產出 1024×1536、1.8 MB；繁體中文全對，
  **沒有糊字、沒有簡體字**；英文技術名詞（RAG／Embedding／SQL Server VECTOR／TypeSafe Jev／
  `gemma4:31b-cloud`）拼寫皆正確。積木感充分（圓凸點、分模線、塑膠亮面都在），
  5 個文字區塊的版面照排。**4 塊技術名詞磚＋12 字註解是舒服的密度**，不必減到 3 塊。
- 步驟四「預設不進專案」可行：直接在新對話送出，風格完全由提示詞決定，結果一致。
- **步驟五的 `+` 選單這次仍然打不開**（`getByRole('button', {name:'新增檔案和更多內容'})`
  點下去沒有任何 menu 出現）。沿用備援即可，且備援是穩的：
  1. 附檔：`page.locator('input[type=file]').first().setInputFiles('./講義/<檔名>.md')`。
     **路徑用正斜線的相對路徑**；反斜線絕對路徑在 Git Bash → run-code 這條路上會被吃掉
     （`_` 的 ` ` 被當跳脫，實際傳出去變成 `_專題導入與環境建置.md` 而 ENOENT）。
  2. 圖像生成：純文字提示詞，固定前置詞在最前面，第二段開頭寫「請創作圖像：」，成功觸發。
- **點擊幾乎都會被攔截**（`<html> intercepts pointer events`）：`tb.click()` 與
  `button[data-testid=send-button]` 的 click 都卡在 retry 迴圈。
  **可行的是鍵盤流**：`el.focus()` → `page.keyboard.insertText(<提示詞>)` →
  `el.focus()` → `page.keyboard.press('Enter')` 送出。送出成功的判準是 URL 從
  `chatgpt.com/` 變成 `chatgpt.com/c/<id>`。
- **步驟六的等待條件要改。** `image-download-button` / `aria-label*="下載"` 這組選擇器等不到
  （這版介面圖片訊息仍然沒有下載鈕）。改等圖片本身，實測可靠：
  `page.waitForFunction(() => Array.from(document.images).some(i => i.naturalWidth >= 1024 && i.naturalHeight >= 1024), null, { timeout: 420000 })`。
  本次約 2 分鐘出圖。
- 步驟七的 `save-image.js` 一次成功，尺寸檢查 1024×1536 通過。

**已實測（2026-09-23，連續產完 15 張）**

- 15 張全部 1024×1536，樂高提示詞穩定；其中 **2 張需要重產**：
  - Section 13：模型自己把 OpenAI 商標畫到小人衣服與助理頭像上。
    提示詞補一句「**不要出現任何真實公司的商標或識別**」後重產即解決。
    **建議把這句話加進每一次的固定提示詞**。
  - Section 14：「權限繞過」的「限」被畫成異體字。放大檢查才看得出來。
- **一定要放大檢查文字**。整張縮圖看起來都對，但把文字區塊裁切放大到 4～5 倍，
  才分辨得出異體字與錯字（用 PIL crop + LANCZOS 放大即可）。
- **要求重產時，`save-image.js` 會抓到舊圖**。它取的是「最後一張夠大的圖」，
  但新圖還沒算完時，頁面上仍只有舊圖。正確作法是先等到**出現第二個不同的 file id**：
  `page.waitForFunction(() => new Set(Array.from(document.images).filter(i=>i.naturalWidth>=1024).map(i=>i.src.match(/id=([^&]+)/)?.[1])).size >= 2)`
- 送出提示詞後偶爾 Enter 不生效（URL 仍停在 `chatgpt.com/`）。
  送完後檢查 URL 有沒有變成 `/c/<id>`，沒有就 focus 後再按一次 Enter。

**已實測（2026-09-23，三張「整份 PDF」海報：教科書、簡報、英文檔名那份）**

- **來源不是單元講義時，步驟一的五項取材要換掉。** 整份教科書／簡報沒有「單元學習目標」與
  「時間配置」，硬套會編出假資訊。改法：頂部磚條寫「課程總覽／簡報總覽／技術總覽｜<主題>」，
  時間行改寫課程層級的真實數字（本課程 `30 小時｜四篇 15 章｜每章 120 分鐘`、
  `30 小時｜15 個 Section｜每章 120 分鐘`），並在回報時說明這個偏離。
- **每一張都要開新對話。** 送提示詞前先 `page.goto("https://chatgpt.com/")` 並確認 URL 是裸的
  `chatgpt.com/`（含 `/c/` 就是還在舊對話）。兩個理由：`save-image.js` 取「最後一張夠大的圖」，
  同一對話裡的前一張會被誤抓；上一張的附件仍在脈絡裡，會污染這一張的內容。
  開新對話比「等第二個 file id」那招穩，而且省掉那一步。
- **`講義/` 裡那三份大 PDF 沒有文字層**（14.9 MB / 15 頁、12.0 MB / 10 頁，`pypdf` 的
  `extract_text()` 每頁都是空字串）。所以：
  1. **提示詞必須自己完整**，不能指望 ChatGPT 讀得到附件內容。附件照附（hook 要求），但規格以提示詞為準。
  2. 自己要讀內容就用 `pypdf` 的 `page.images` 把每頁內嵌圖倒出來（本例 1376×768／頁），
     再拼成 4 欄的 contact sheet 一次看完，比逐頁讀省很多 token。
- **附大檔要輪詢等它落定。** 15 MB PDF 的 `setInputFiles` 之後，要等 form 的 chip 文字出現
  `PDF` 且 `form [role=progressbar], form progress` 歸零才能按 Enter，否則會帶著半截附件送出。
  實測約 3 秒落定，但仍應輪詢而不是固定 sleep。
- **附件本身就是樂高風 deck 時**（`SQL Server 2025  Building...` 那份 10 頁全是樂高插畫），
  提示詞要加「不要複製附件裡任何一頁的版面，只依下列 5 區塊規格排版」，否則會照抄原頁。
- 「不要出現任何真實公司的商標或識別」這句已確認**每次都要帶**：那份 deck 第 9 頁本身就有
  可見的 ChatGPT 標籤，不加這句會被沿用。
- **hook 的海報比對規則**（`.claude/hooks/pdf-image-hook.js`）：檔名沒有數字前綴時，`unitKey()`
  回傳整個主檔名，`hasPoster()` 用 `^<主檔名>(\D|$)` 比對。所以這類海報要命名成
  `<PDF 主檔名> <主標>.png`（主檔名後面接一個半形空格），才不會每次開 session 都被重複提醒。
  檔名含連續兩個空格（`2025  Building`）要原樣保留，用 `Move-Item -LiteralPath` 不會被壓縮。
- 三張的文字一次就對，都不用重產：1024×1536、1.79～1.83 MB，繁體全對、無簡體、無異體字，
  `SQL Server VECTOR`／`Embedding`／`TypeSafe Jev`／`DiskANN`／`RRF`／`ChunkHash` 拼寫皆正確。
  唯一瑕疵是簡報那張的 `ChunkHash` 字距被拆成 `Chunk Hash`（拼字正確，僅字距），不值得重產。
