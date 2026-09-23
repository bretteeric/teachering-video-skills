---
name: document-creator-skill
description: 依 workspace 根目錄的課程大綱 Markdown，按課程順序逐一編排每個單元的教學教案：切開章節分別說明、每個觀念寫清楚「是什麼／為什麼／怎麼運作／限制」、用 Mermaid 補充流程圖並逐節點說明、程式碼貼完整方法並逐段講解與附預期結果、建立對應的範例專案到 `範例/`、在模擬環境擷取操作畫面，最後以 A4 PDF 輸出到 `講義/`。當使用者說「產生教案」「做講義」「編排教學文件」「把大綱變成教案」「輸出 PDF 講義」「建立範例專案」「講義寫得更詳細」時使用。
allowed-tools: Bash(node:*) Bash(dotnet:*) Bash(ls:*) Bash(mkdir:*) Bash(mv:*) Bash(cp:*) Bash(grep:*) Bash(playwright-cli:*) Bash(curl:*) Read Write Edit Glob Grep
---

# 課程大綱 → 單元教案 → PDF 講義

把 workspace 根目錄的**課程大綱 Markdown**，依課程順序拆成一個個單元教案，每個單元產出以下四樣東西：

| 產出 | 路徑 | 說明 |
|---|---|---|
| 教案原稿 | `講義/NN_主題.md` | YAML front matter + 分章節的教案，含 Mermaid 圖、擷圖、程式碼與逐段說明 |
| 教案講義 | `講義/NN_主題.pdf` | A4 直式，交給學員的正式文件 |
| 範例專案 | `範例/NN_主題/` | 該單元可實際跑起來、`dotnet build` 通過的程式 |
| 操作擷圖 | `講義/images/NN/*.png` | 模擬環境跑出來的畫面 |

## 寫作標準：學員沒有老師在旁邊也看得懂

教案的讀者是**學員**。判斷一段有沒有寫完的標準是：學員只拿著 PDF 和範例專案，
能不能**看懂為什麼、照著做出來、自己判斷做對了沒**。三條硬規則：

1. **內容精準**：每個觀念回答「是什麼／為什麼需要／怎麼運作／限制」；類別、設定鍵、端點、數字一律寫出具體值，
   不寫「相關設定」「等等」。
2. **圖不孤立**：每張圖 = 引導句 + 圖 + `*圖 NN-k　標題*` 圖說 + 逐節點編號說明表。
3. **程式碼有講解**：每段程式 = 引導句（做什麼、在哪個檔案、被誰呼叫）+ 完整方法（第一行是檔案路徑）
   + 標號對應的「程式說明」表 + 「預期結果」。

完整規格、合格與不合格對照範例、寫完後的自我檢核清單，都在
[references/writing-guide.md](references/writing-guide.md)。**動筆前先讀一次，寫完照文末檢核跑一次。**

## 一次只做一個單元

**不要一口氣產生所有單元。** 每次呼叫只處理**一個** Section：寫稿 → 建範例 → 擷圖 → 出 PDF → 回報，
然後**停下來等使用者確認**再做下一個。理由有三：

- 範例專案要真的 `dotnet build` 過，一次做完 15 個會在第一個編譯錯誤上全盤皆輸。
- 擷圖要把網站跑起來，失敗需要人介入判斷。
- 第一個單元定調了整個系列的深淺與長度，先讓使用者驗收再量產。

使用者若明講「全部做完」，仍然**逐一循環**、每做完一個就簡短回報進度，不要平行展開。

---

## 輸出契約（不可任意更改命名）

`講義/` 與 `海報/` 這條線上還有一個 hook 和另外兩個 skill 在等，格式錯了整條就斷掉：

- 檔名一律 `NN_主題.md` / `NN_主題.pdf`，**兩位數編號 + 半形底線 + 主題**。
- `NN` 用 `01`～`15`，對齊大綱的 Section 編號。
- **底線是硬性規定**，不是偏好。[.claude/hooks/pdf-image-hook.js](../../hooks/pdf-image-hook.js)
  的 `unitKey()` 用 `^(\d{1,3})` 取編號、`findLectureMd()` 用 `startsWith(key + '_')` 找對應的 .md。
  改成空格或連字號，PDF 落地時 hook 就配不到講義。
- **.md 開頭是 YAML front matter（`session`、`title`、`subtitle`、`duration`、`outcome`、`example`），內文不寫 `#` H1**。
  [book-creator-skill](../book-creator-skill/SKILL.md) 編書時靠 front matter 取章號與標題，並要求內文沒有 H1；
  `md-to-pdf.js` 出單元 PDF 時會把 front matter 自動換成 H1 標題與資訊列。
- PDF 一放進 `講義/`，hook 會自動喚醒
  [image-geneate-skill](../image-geneate-skill/SKILL.md) 去產生該單元的樂高風海報。
  **這是預期行為**，不是意外；調整期間先產到 scratchpad（見步驟六），定稿後才產進 `講義/`。
- 擷圖放 `講義/images/NN/`，不要放 `講義/` 直屬目錄（image-geneate-skill 的步驟一靠這點排除雜檔）。

---

## 前置條件

| 項目 | 檢查方式 | 沒有的話 |
|---|---|---|
| Node.js | `node --version` | 整條管線都動不了，停下來回報 |
| Chrome | `ls "/c/Program Files/Google/Chrome/Application/chrome.exe"` | 出 PDF 與擷圖都要用，停下來回報 |
| `@playwright/cli`（全域） | `playwright-cli --version` | `npm install -g @playwright/cli@latest` |
| .NET SDK | `dotnet --version` | 範例專案是本 skill 的交付項目之一，停下來回報 |
| 課程大綱 .md | `ls *.md` | **不要自己編一份大綱**，直接回報請使用者提供 |

`scripts/vendor/` 底下已經 vendor 好 `marked.min.js` 與 `mermaid.min.js`，**全程離線**，不打 CDN。
萬一檔案遺失，重抓：

```bash
curl -sSL -o .claude/skills/document-creator-skill/scripts/vendor/marked.min.js  https://cdn.jsdelivr.net/npm/marked@14/marked.min.js
curl -sSL -o .claude/skills/document-creator-skill/scripts/vendor/mermaid.min.js https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js
```

---

## 步驟一　讀課程大綱，決定這次要做哪一個單元

```bash
ls -1 *.md
mkdir -p 講義 範例
```

workspace 根目錄的 .md 就是課程大綱（本課程是
`SQL_Server_2025_RAG_ASPNET_Core_MVC_30小時課程教案.md`）。從裡面讀出：

- **單元大綱表**：Section 編號、時數、主題、教學與實作內容、單元驗收成果 ← 教案的骨架全在這張表
- **每節時間配置**：本課程固定 `觀念說明 20｜教師示範 25｜學員實作 65｜單元驗收 10`，合計 120 分鐘
- **課程目標、技術選型、先備能力**：寫「學習目標」與「先備知識」時要對齊

把「教學與實作內容」那一格**拆成逐項清單**抄在手邊，後面每一項都要對應到一個 `###` 小節。

決定單元的優先序：

1. 使用者給的參數（`$ARGUMENTS`，例如 `03` 或 `03_三知識庫資料模型`）
2. 沒給參數 → `ls 講義/*.md` 看已經做到哪一號，接續**下一號**
3. 都還沒有 → 從 `01` 開始

**選好之後先回報「這次做 Section NN：主題」再動手。**
`講義/NN_*.md` 已存在時不要直接覆蓋，先問使用者是要改寫還是跳過。

## 步驟二　先建範例專案（程式碼的唯一來源）

**先寫程式、`dotnet build` 過，再寫教案。** 教案裡的每一段程式碼都要從這裡複製過去，
不要憑印象在教案裡重打 —— 那樣寫出來的程式碼常常和範例對不上，學員照抄就編譯失敗。

```bash
mkdir -p "範例/NN_主題"
cp -r "範例/<前一單元>/RagDemo" "範例/NN_主題/RagDemo"      # 從前一單元長出來
dotnet new mvc    -n RagDemo -o "範例/NN_主題/RagDemo"      # 或：第一個單元從範本開始
dotnet build "範例/NN_主題/RagDemo"
```

（本機已測：.NET SDK 10.0.401，`mvc` / `webapi` / `classlib` / `sln` / `xunit` 範本都在。）

原則：

- **範例要跟著單元長大**，不是每單元從零開始。後面的單元用 `cp -r` 複製前一個單元的成果再往上加，
  讓學員看得到系統怎麼一層層疊起來。教案要寫明「這個單元新增／修改了哪些檔案」。
- **一定要 `dotnet build` 過**才算數。build 不過就修到過，不要把壞的範例寫進教案。
- 程式碼本身也要有註解：類別與公開方法寫 `///` 摘要，非直覺的判斷寫行內註解。
  教案裡的「程式說明」是**逐段講解**，程式碼註解是**就地提示**，兩者都要有，不能互相取代。
- 需要連線字串、API Key 的地方一律留 `appsettings.Development.json` 的佔位值，
  **不要寫進任何真實金鑰**，教案裡改成「請填入自己的 ○○」。
- 資料庫腳本放 `範例/NN_主題/sql/*.sql`，教案用相對路徑引用；腳本開頭註明在哪個資料庫執行、可否重複執行。
- 教案裡引用範例時寫相對路徑（`範例/03_三知識庫資料模型/RagDemo/Program.cs`），不要貼絕對路徑。

## 步驟三　撰寫教案原稿

依 [references/lesson-plan-template.md](references/lesson-plan-template.md) 的骨架寫
`講義/NN_主題.md`，每一段寫到 [references/writing-guide.md](references/writing-guide.md) 的標準。
骨架的章節順序與時間盒**直接來自大綱的時間配置，不要自行發明**。

各章節要寫到的程度：

| 章節 | 必須包含 |
|---|---|
| 學習目標 | 3～5 條，動詞開頭、可當場驗證（「用 `VECTOR_DISTANCE` 查出最接近的 5 個片段」，不是「了解向量檢索」） |
| 先備知識 | 前一單元的**具體產出**（哪個專案、哪張表有資料），不是泛泛的「會 C#」 |
| 觀念說明 | 「為什麼需要」→「怎麼運作」（含圖與逐節點說明）→「限制與注意事項」→「名詞對照」 |
| 教師示範 | 示範步驟（寫到可照做）+ 擷圖與畫面重點 + 程式碼走讀與執行結果 |
| 學員實作 | 每步驟固定六段：**目的 → 指令 → 程式碼 → 程式說明 → 預期結果 → 常見改錯**；最後一個檢查點清單 |
| 常見錯誤 | 錯誤訊息**原文**、原因、具體修法（改哪個檔、哪個設定） |
| 單元驗收 | 大綱原句 + 正向驗證步驟 + 一個反向驗證（故意做錯，系統要明確失敗） |

寫作要求：

- **每個 `##` 章節在 PDF 裡會自動分頁**，所以章節要切得有意義，一個章節講一件事；章節內用 `###` 分小節。
- 面向的是**學員**：用第二人稱、寫得出手就能照做的步驟，不要寫「我們可以考慮…」這種規劃語氣。
- 技術名詞第一次出現時給一句白話解釋，並列入「名詞對照」，之後直接用。
- **因果寫完整**：「因為 A，所以 B；不這樣做會 C」。只寫結論的規則學員記不住，也不會變通。
- 程式碼區塊標語言（```csharp、```sql、```bash、```json、```text），PDF 會套等寬字型。
- **「教學與實作內容」欄的每一項都要落到某個 `###` 小節**，不要漏掉大綱答應過學員的東西。
- 「單元驗收」章節直接引用大綱「單元驗收成果」那一格的原句，不要改寫成別的標準。

### 程式碼的貼法

- **貼最小完整單位**：整個方法（簽章到結尾大括號），類別很短就貼整個類別。
  **不要用 `/* ... */` 省略會影響理解的邏輯**；只有 using、建構子注入這類樣板可以省，並寫明完整檔案在哪。
- 超過約 40 行就拆成兩個區塊，各自說明，不要一整頁程式碼沒有任何講解。
- 第一行是檔案路徑註解（`// 範例/NN_主題/RagDemo/Services/Xxx.cs`、SQL 用 `--`）。
- 關鍵行加行尾標號 `// ①`，下方「程式說明」表用同一組標號，欄位是「做了什麼／為什麼這樣寫」。
- 每段之後寫「預期結果」：執行後的輸出（```text 區塊）、畫面、或資料庫查得到的列。
- 設定檔（JSON）每個鍵都要說明用途、合法值、改錯的後果，用表格列出。

## 步驟四　用 Mermaid 補充圖形

凡是講「流程」「架構」「狀態變化」「資料關係」「誰呼叫誰」的段落，補一張 Mermaid 圖。
文字一句話就講得清楚的不要硬畫。

**每張圖都要有四個部分，圖不能孤立出現：**

````markdown
下圖說明一份文件從上傳到寫進資料庫，中間經過哪幾次格式轉換。
看的時候注意：**每個箭頭都是一次轉換**，錯誤最常發生在轉換點上。        ← ① 引導句

```mermaid                                                                  ← ② 圖
flowchart LR
    A["① 文字片段"] --> B["② float[768]"]
    B --> C["③ JSON 字串"]
    C --> D["④ VECTOR(768)"]
```

*圖 06-1　文件片段向量化的資料格式轉換*                                    ← ③ 圖說

| 編號 | 做了什麼 | 對應程式碼 |                                             ← ④ 逐節點說明
|---|---|---|
| ① → ② | 呼叫 `/api/embed`，驗證長度必須是 768 | `OllamaEmbeddingService` |
| ② → ③ | 用 `InvariantCulture` 序列化，避免小數點變逗號 | `SqlEmbeddingRepository.ToJsonArray` |
| ③ → ④ | SQL Server 轉成二進位向量 | `CAST(@embedding AS VECTOR(768))` |
````

- 節點文字加 `①②③` 編號，說明表用同一組編號，學員能在圖和文字之間來回對照。
- 有分支的流程，**每一條分支**（包含失敗路徑）都要說明觸發條件與結果。
- `sequenceDiagram` 逐則訊息說明送出什麼、拿回什麼。
- 圖號 `圖 NN-k` 全單元連續（Mermaid 與擷圖共用），內文引用時寫圖號。

選圖型與大小限制（實測，細節見 writing-guide）：

| 要表達 | 用什麼 | 上限 |
|---|---|---|
| 先後順序、資料流 | `flowchart LR` | 4～6 個節點（高約 100 px，最清楚） |
| 有判斷分支 | `flowchart TD` + `{"條件？"}` | 8 個節點內 |
| 請求與回應 | `sequenceDiagram` | 3～4 個參與者、8 則訊息 |
| 狀態變化 | `stateDiagram-v2` | 5～6 個狀態 |
| 資料表關係 | `erDiagram`（3 張表內）；更多改 `flowchart LR` | 5 個實體實測 685 px |

**一張圖講一件事**；要講的太多就拆兩張圖各配說明，不要塞成高過一頁（約 979 px）的大圖。

語法規定：

- **中文節點文字一律用雙引號包起來**（`A["使用者提問"]`）。不包的話，中文標點會讓 Mermaid 解析失敗，
  而且 `md-to-pdf.js` 只會警告不會中斷，你會拿到一份缺圖的 PDF。
- 節點內換行用 `<br/>`。
- 圖的配色由 `md-to-pdf.js` 統一注入（藍白系，配合講義主色），**不要在 md 裡寫 `%%{init}%%` 覆蓋**。
- 不要畫跨 subgraph 的連線：會讓 `direction` 失效、整張攤成超寬兩列（見〈驗證狀態〉）。

## 步驟五　在模擬環境擷取操作畫面

**每個單元至少一張擷圖**，放在「教師示範」。有 UI 的單元拍操作畫面；
純資料庫、純概念的單元（本課程的 03、06、09 等）也要讓範例網站提供一個**看得到結果的頁面**
（片段預覽、向量維度、索引狀態、連線檢查），拍那一頁 —— 15 個單元都是這樣做的。
**不要**為了湊圖去拍一張沒有資訊量的空白頁或預設首頁。

擷圖用 [scripts/capture-screens.js](scripts/capture-screens.js)，它會開無頭 Chrome、
等頁面穩定、存成指定檔名，細節見 [references/screenshot-guide.md](references/screenshot-guide.md)：

```bash
# 1. 先把範例跑起來（背景執行，記下埠號）
dotnet run --project "範例/NN_主題/RagDemo" --urls http://localhost:5199 &

# 2. 確認起來的是「這個單元」的網站，再擷圖（可一次給多個 路徑=檔名）
curl -s http://localhost:5199 | grep -o "<title>[^<]*"
MSYS_NO_PATHCONV=1 node .claude/skills/document-creator-skill/scripts/capture-screens.js \
  --base=http://localhost:5199 --out=講義/images/NN \
  "/=01-首頁" "/Admin/Upload=02-上傳頁"
```

> **`MSYS_NO_PATHCONV=1` 在 Git Bash 裡不可省略**（已實測）。少了它，Git Bash 會把 `/` 開頭的
> 參數改寫成 `C:/Program Files/Git/...`，網址整個歪掉。腳本會擋下來並提示，但別等它報錯。
> 改用 PowerShell 執行則沒有這個問題。

拿不到真實後端資料時（沒有 SQL Server、沒有 Ollama 金鑰），**用模擬環境**：在範例裡放一組
假資料或 stub service，讓畫面長得出來。這是教案用圖，重點是**版面與操作位置說得清楚**，
不是真的跑通後端。圖的替代文字要註明「示意畫面（模擬資料）」，不要讓學員誤會。

擷完記得把背景的 `dotnet run` 收掉。

圖片在教案裡的寫法（相對於 `講義/`），一樣要有圖說與畫面重點：

```markdown
![管理後臺上傳頁（示意畫面，模擬資料）](images/03/02-上傳頁.png)

*圖 03-2　管理後臺上傳頁*

畫面重點：

1. **①左上的知識庫下拉選單**：決定文件歸屬哪一個知識庫，選項來自 `KnowledgeBases` 資料表。
2. **②「上傳」按鈕**：送出後建立一筆 `IngestionJobs`，狀態為 `Pending`。
```

## 步驟六　輸出 PDF

調整期間先產到 scratchpad，**不要直接產進 `講義/`**（每產一次就觸發一次海報 hook）：

```bash
node .claude/skills/document-creator-skill/scripts/md-to-pdf.js "講義/NN_主題.md" --out=<scratchpad>
```

腳本會把 front matter 換成標題區、回報檔案大小與 Mermaid 張數，並且：

- 圖片載不到 → 印出警告與檔名清單（PDF 仍會產出，但該處是空白）
- Mermaid 語法錯 → 印出頁面 JS 錯誤
- **這兩種警告都要處理掉再交件**，不要把有警告的 PDF 當成功回報。

想先看排版再出 PDF，加 `--keep-html` 會留下中繼 HTML 可用瀏覽器打開檢查。

確認頁數與內容都沒問題後，才正式產進 `講義/`（這時觸發一次 hook、跑一次海報）：

```bash
node .claude/skills/document-creator-skill/scripts/md-to-pdf.js "講義/NN_主題.md"
```

## 步驟七　驗證與回報

先跑 writing-guide 文末的 grep 粗篩：

```bash
F="講義/NN_主題.md"
echo "Mermaid 圖：$(grep -c '^```mermaid' "$F")　擷圖：$(grep -c '^!\[' "$F")　圖說：$(grep -cE '^\*圖 [0-9]+-[0-9]+' "$F")"
echo "程式碼區塊：$(grep -cE '^```(csharp|sql|cshtml|razor|js)' "$F")　程式說明：$(grep -c '程式說明' "$F")　預期結果：$(grep -c '預期結果' "$F")"
grep -nE '/\* *\.\.\. *\*/|// *\.\.\.$|等等|之類' "$F"     # 應該沒有輸出
```

逐項確認後再回報：

1. PDF 存在且**不是 0 KB**；頁數在 **10～18 頁**
2. `md-to-pdf.js` **沒有**印出圖片或 Mermaid 警告
3. 範例專案 `dotnet build` 通過
4. 擷圖檔案都在 `講義/images/NN/`，且 PDF 裡看得到（不是破圖）
5. 「Mermaid 圖數 + 擷圖數 = 圖說數」；每張圖後有編號說明
6. 每個學員實作步驟都有「程式說明」與「預期結果」；教案程式碼抽查 2～3 段與範例檔一致
7. 大綱「教學與實作內容」的每一項都有對應的 `###` 小節

回報內容：做了哪一個 Section、PDF 路徑與頁數、範例專案路徑與 build 結果、圖（Mermaid／擷圖）各幾張、
以及**下一個單元是哪一個**。

---

## 疑難排解

| 症狀 | 處理 |
|---|---|
| `找不到 vendor/marked.min.js` | 見「前置條件」的 curl 重抓指令 |
| PDF 裡中文變成方塊 | 系統缺「微軟正黑體」。改 `md-to-pdf.js` 的 `font-family` 加上實際有的中文字型 |
| PDF 裡 Mermaid 位置空白 | 中文節點沒用雙引號包，或語法錯。看腳本印出的 JS 錯誤，修好 md 再跑一次 |
| PDF 裡圖片是空白框 | 路徑錯。教案裡的路徑是**相對於 `講義/`**，不是相對於 workspace 根目錄 |
| PDF 開頭多出一頁怪標題 | front matter 格式錯（開頭不是 `---`、或少了結尾 `---`），marked 把它當成內文 |
| 圖說沒有置中變灰 | 圖說要**緊接在圖的下一段**，而且整段只有 `*圖 NN-k　…*`，中間不能夾其他文字 |
| 章節沒有分頁 / 分頁太碎 | 分頁是綁 `##`。層級用錯（該用 `###` 卻寫 `##`）就會一直跳頁 |
| 某一節有大片空白 | 圖或程式碼區塊太高，整塊被推到下一頁。把圖拆兩張、程式碼拆兩段各自說明 |
| `dotnet run` 佔著埠號不放 | 換一個埠（`--urls http://localhost:5200`），收工前把背景程序關掉 |
| 擷圖是空白頁 | 網站還沒起來就擷了。先 `curl -s -o /dev/null -w "%{http_code}" <url>` 確認回 200 再擷 |
| 擷到別的單元的畫面 | 5199 被其他單元的範例站佔著。擷圖前先 `curl` 看 `<title>` 或頁面關鍵字 |
| 放進 `講義/` 的 PDF 觸發了海報 hook | 這是預期行為，見「輸出契約」。調整期間用 `--out=<scratchpad>` |
| 一個單元超過 18 頁 | 先檢查是不是有大片空白（圖太高）。真的是內容多，回頭對照大綱，拿掉大綱沒要求的延伸內容；**不要刪程式說明與圖解說明** |
| 一個單元不到 10 頁 | 通常是圖與程式碼沒有講解。照 writing-guide 的自我檢核補齊 |

## 驗證狀態

**已實測（2026-09-23，本機 Windows 11）**

- PDF 管線走 **marked（瀏覽器內）→ mermaid（瀏覽器內）→ Chrome `page.pdf()`**，
  用絕對路徑 require 全域 `@playwright/cli` 內附的 `playwright-core`，
  瀏覽器用 `channel: 'chrome'` 吃系統既有的 Chrome。
  **不需要 pandoc / wkhtmltopdf / LaTeX / mmdc —— 這台機器上都沒有，也不必裝。**
- 冒煙測試（繁中內文＋Mermaid flowchart＋表格＋程式碼區塊＋PNG 擷圖）一次通過：
  產出 6 頁 122 KB 的 A4 PDF，內嵌 4 組字型子集；繁體中文、Mermaid 中文節點皆正常，無方塊字。
- `dotnet --version` = 10.0.401；`mvc` / `webapi` / `classlib` / `sln` / `xunit` 範本齊全，
  與大綱指定的 .NET 10 LTS 相符。
- `capture-screens.js` 已對**真的跑起來的 ASP.NET Core MVC 網站**擷圖成功：
  `dotnet new mvc` → `dotnet build`（0 錯誤）→ `dotnet run --urls http://localhost:5199`，
  擷下首頁與隱私權頁各一張（1280×800、2 倍解析度、約 55 KB）。
  不存在的路徑會被擋下並以 exit 1 結束，不會把 404 頁存成教學圖。
- **Git Bash 會改寫 `/` 開頭的參數**：`"/=01-首頁"` 會變成 `"C:/Program Files/Git/=01-首頁"`，
  網址跟著壞掉且錯得很安靜。解法是前面加 `MSYS_NO_PATHCONV=1`（或改用 PowerShell）。
  腳本已內建偵測，撞到會直接報錯並給出修法。
- **「PDF 落進 `講義/` → hook 喚醒 image-geneate-skill」整條接力已跑通**，
  在 Section 01 產出 `海報/01 先把環境接通.png`（1024×1536）。每重產一次 PDF 就觸發一次 hook。
- **全 15 個單元已實際產出一輪（2026-09-23，舊版寫作規則）**：15 份講義 PDF 11～12 頁、
  15 張海報、15 個範例專案 `dotnet build` 全部 0 錯誤、Section 14／15 的 xUnit 測試 20 項全過、
  每個單元至少 1 張擷圖（共 17 張）。
  那一輪為了壓在 12 頁內，程式碼只貼片段、圖後沒有說明，**使用者驗收後要求改成現在的寫作標準**；
  頁數區間因此放寬到 10～18 頁。新標準尚未用完整單元重跑驗證。

- **排版量測（A4 內文區約 979 px 一頁）**：
  - 分頁綁 `##`，章節再短也各自佔滿一頁：骨架 8 個 `##` 本身就是 8 頁下限。
  - 舊版的 `body > h2:first-of-type` 永遠配不到（h2 在 `#content` 裡），第一個 `##` 會跳頁、
    讓標題區獨佔一頁；已改成 `#content > h2:first-of-type`。
  - 頁數異常時用 `--keep-html` 留下中繼檔，在瀏覽器量每個 `##` 的內容高度，
    找出是哪一節被大圖或長程式碼推出大片空白，**拆圖、拆程式碼區塊，而不是刪說明**。

- **Mermaid 圖的高度會直接決定頁數，畫之前先想版型**（實測踩過）：
  - `.mermaid` 帶 `break-inside: avoid`，**圖只要高過一頁（≈979 px）就排不進去**，
    會整張推到新頁並留下大片空白。第一版 `flowchart TD` 兩個 subgraph 疊起來 1030 px，
    害 PDF 從 9.6 頁的內容量膨脹成 17 頁。
  - `flowchart LR` 搭 subgraph 內 `direction TB` **不保證有效**：只要有跨 subgraph 的連線
    （`A5 -.-> B3`），mermaid 會忽略 `direction`，把圖攤成超寬兩列，
    縮到版面寬度後字小到看不清楚。拿掉連線又會變成上下堆疊、而且**順序可能顛倒**。
  - **`erDiagram` 也會爆**：5 個實體的 ER 圖量到 685 px。
    要表達「文件→版本→片段→向量」這種鏈狀關係，改用 4 個節點的 `flowchart LR` 就夠，高度只剩約 100 px。
  - **可靠作法：一條流程一個 `flowchart LR`，控制在 4～6 個節點**，
    寬度約 680 px 剛好等於版面寬，幾乎不縮放、字最清楚。要表達兩張圖的關係就用一句文字說明。
