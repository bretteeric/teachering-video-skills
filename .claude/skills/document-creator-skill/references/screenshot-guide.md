# 模擬環境與操作畫面擷取

教案裡的圖是**教學用圖**，目的是讓學員知道「畫面長什麼樣、要點哪裡」。
不是系統驗收證據，所以**不需要真的接上 SQL Server 與 Ollama**。

## 哪些單元需要擷圖

| 需要 | 不需要 |
|---|---|
| 有畫面可操作：登入、管理後臺、上傳頁、進度頁、聊天室 | 純資料庫設計、索引維護、Embedding 運算 |
| 要指出「按鈕在哪」「欄位填什麼」 | 講概念、講架構、講流程 |

**不要為了湊圖去拍一張沒有資訊量的空白頁面。**

但**每個單元至少要有一張擷圖**放在「教師示範」：偏概念與資料層的單元（本課程的 01、03、06、08、09），
讓範例網站提供一個**看得到結果的頁面**再拍 —— 連線檢查頁、片段預覽、向量維度、索引狀態、版本清單。
第一輪 15 個單元就是這樣做的，每個 `講義/images/NN/` 都有 1～2 張。
概念本身的流程與架構，仍用 Mermaid 圖說明。

## 擷圖在教案裡的寫法

擷圖和 Mermaid 圖一樣不能孤立出現，要有四個部分（詳見 [writing-guide.md](writing-guide.md)）：

```markdown
教師按下「重新整理」後，連線檢查頁會逐項顯示三個外部服務的狀態。       ← 引導句

![連線檢查頁（示意畫面，模擬資料）](images/01/01-連線檢查.png)          ← 圖

*圖 01-3　連線檢查頁*                                                  ← 圖說（緊接在圖下一段）

畫面重點：                                                              ← 逐位置說明

1. **①SQL Server 列**：顯示 `已連線（17.0）`，版本號由 `SELECT SERVERPROPERTY('ProductMajorVersion')` 取得。
2. **②Ollama 列**：紅色 `逾時` 表示 `Ollama:BaseUrl` 連不到，先檢查 `ollama serve` 有沒有在跑。
```

- 替代文字（`![...]` 方括號內）寫畫面名稱並註明「示意畫面（模擬資料）」。
- 圖說 `*圖 NN-k　標題*` 和 Mermaid 圖共用同一組流水號。
- 「畫面重點」的 ①② 要能在畫面上找到對應位置（左上、右側欄、表格第 2 欄），
  並說明**數值從哪裡來**或**點下去會發生什麼**。

## 模擬環境的做法

後端服務（SQL Server 2025、Ollama 雲端、TypeSafe API）在寫教案的當下通常沒有，
所以讓畫面「長得出來」就好：

1. **假資料 stub**：在範例專案裡放一個回傳固定假資料的 service，
   用 `appsettings.Development.json` 的開關切換。

   ```csharp
   // 範例/NN_主題/RagDemo/Services/StubRetrievalService.cs
   public sealed class StubRetrievalService : IRetrievalService
   {
       public Task<IReadOnlyList<Chunk>> SearchAsync(string q, CancellationToken ct) =>
           Task.FromResult<IReadOnlyList<Chunk>>(new[]
           {
               new Chunk("長照3.0 服務對象與申請流程", "長照手冊.pdf", 12, 0.87),
               new Chunk("居家服務補助額度說明",       "長照手冊.pdf", 15, 0.81),
           });
   }
   ```

2. **靜態 HTML 原型**：連範例專案都還沒建（例如單元 01 在講環境建置），
   就寫一份靜態 HTML 放 scratchpad，用 `file://` 擷圖。畫面示意用，一樣有效。

3. **圖說一定要註明**：`![上傳頁（示意畫面，模擬資料）](images/04/02-上傳頁.png)`
   不要讓學員以為那是真的跑通後端的結果。

**不要**把任何真實金鑰、真實個資、真實病歷截進圖裡。
大綱 8.3 已經寫明：課堂使用公開衛教文件，不以真實個人病歷示範。

## 擷圖步驟

```bash
# 1. 把範例跑起來，指定埠號比較好收尾
dotnet run --project "範例/04_PDF上傳與背景工作/RagDemo" --urls http://localhost:5199 &

# 2. 確認真的起來了（沒回 200 就先別擷，會拍到錯誤頁）
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5199

# 3. 擷圖，一次給多個「路徑=檔名」
#    MSYS_NO_PATHCONV=1 在 Git Bash 裡不可省略，理由見下方。
MSYS_NO_PATHCONV=1 node .claude/skills/document-creator-skill/scripts/capture-screens.js \
  --base=http://localhost:5199 --out=講義/images/04 \
  "/=01-首頁" "/Admin/Upload=02-上傳頁" "/Admin/Jobs=03-處理進度"

# 4. 收掉背景程序
```

## Git Bash 的路徑改寫陷阱（已實測）

Git Bash（MSYS）會把 `/` 開頭的參數當成 Unix 路徑，自動改寫成 Windows 絕對路徑：

```
"/=01-首頁"  →  "C:/Program Files/Git/=01-首頁"
```

結果網址變成 `http://localhost:5199/C:/Program Files/Git/`，goto 失敗但訊息看不出原因。

**解法**：指令前面加 `MSYS_NO_PATHCONV=1`，或改用 PowerShell 執行（PowerShell 沒有這個問題）。
`capture-screens.js` 已內建偵測，撞到會直接報錯並印出修法，不會默默擷出一堆壞圖。

`capture-screens.js` 會擋掉 HTTP 400/500 的頁面（不把錯誤頁存成教學圖），
並在結束時回報成功張數；有任何一張失敗會以 exit 1 結束。

常用選項：

| 選項 | 用途 |
|---|---|
| `--full` | 整頁擷取。頁面很長時用，否則預設的可視範圍比較適合教案 |
| `--width=1280 --height=800` | 預設值。要拍窄版／手機版再改 |
| `--scale=2` | 預設 2 倍解析度，縮進 PDF 才不會糊。檔案太大可降成 1.5 |
| `--wait=1500` | 前端 JS 畫得慢（Vue、串流訊息）時加長 |
| `--headed` | 擷圖結果不對時，開視窗看它到底停在哪一頁 |

## 檔名與路徑

- 一律存 `講義/images/NN/`，**不要**放 `講義/` 直屬目錄
  —— image-geneate-skill 的步驟一靠這點排除雜檔。
- 檔名用 `序號-畫面名.png`（`01-首頁.png`、`02-上傳頁.png`），序號即教案裡出現的順序。
- 教案裡的路徑是**相對於 `講義/`**：`![圖說](images/04/02-上傳頁.png)`。
  寫成 `講義/images/...` 會在 PDF 裡變成空白框。

## 出了問題

| 症狀 | 處理 |
|---|---|
| 擷到空白頁 | 網站還沒起來。先 `curl` 確認回 200 再擷 |
| 擷到錯誤頁 | 路徑打錯。腳本會擋掉 4xx/5xx 並報 HTTP 碼，照著修路徑 |
| 圖在 PDF 裡是空白框 | md 裡的路徑寫錯，要相對於 `講義/` |
| 圖太糊 | `--scale=2` 以上；或改 `--full` 讓版面不要被壓縮 |
| 埠號被佔用 | 換一個 `--urls http://localhost:5200`，收工前記得關掉背景程序 |
| 前端還在載入就被拍 | 加大 `--wait`，或確認頁面有沒有無窮輪詢讓 networkidle 永遠不成立 |
