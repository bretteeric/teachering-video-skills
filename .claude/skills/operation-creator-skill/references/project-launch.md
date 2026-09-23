# 專案啟動

目標只有一個：**擷取到的每一張畫面，都確定來自「這個」專案**。

---

## 一、專案類型偵測（`launch.py` 內建）

| 判斷依據 | 類型 | 啟動命令 |
|---|---|---|
| `*.csproj` 且 `Sdk="Microsoft.NET.Sdk.Web"`（排除 `*.Tests`） | dotnet | `dotnet run --project X.csproj --no-launch-profile --urls http://localhost:{port}` |
| `run.py`／`app.py`／`wsgi.py`／`main.py` 內含 `Flask`／`FastAPI`／`create_app` | python | 優先用 `.venv\Scripts\python.exe`；`app.py` 走 `-m flask --app`，FastAPI 走 `uvicorn` |
| `package.json` 有 `dev` 或 `start` script | node | `npm run dev -- --port {port}`（環境變數也給 `PORT`） |

偵測不到或命令不對時，用 `--cmd` 自訂，`{port}` 會被替換：

```powershell
python launch.py start --project X --state s.json --cmd "python run.py --port {port}"
```

### .NET 的兩個細節

- **`--no-launch-profile`**：不然會套用 `launchSettings.json` 寫死的埠（常被別的站佔住）。
  代價是 launch profile 裡的環境變數也不套用，所以 `launch.py` 會自己把 `http` profile 的
  `environmentVariables` 讀回來（至少補上 `ASPNETCORE_ENVIRONMENT=Development`）。
  少了 Development，`appsettings.Development.json` 的模擬開關與開發用端點都不會生效。
- 第一次 `dotnet run` 要還原＋建置，`launch.py` 的就緒等待是 180 秒。

---

## 二、連接埠：一律挑空的

`launch.py` 從 **5310** 往上找第一個 IPv4 與 IPv6 都沒人聽的埠。

**為什麼不用專案預設埠**：實測過 `範例/15` 的 `RagDemo.exe` 正佔著 5199 時，
另一個單元的 `dotnet run --urls http://localhost:5199` 以 `address already in use` 失敗，
但輪詢 `/Health` **仍然拿到 200**——回應來自第 15 單元。截圖整批擷到錯的 app，
十張影格作廢、TTS 與 30 分鐘 4K 合成全部重跑。

被佔的埠**不要去停佔用者**，那是使用者自己開的站。

---

## 三、就緒與身分斷言

`launch.py start` 依序確認：

1. 行程沒有提早結束（結束了就印日誌尾巴）
2. `--probe` 路徑回應碼 < 500（200、302、401 都代表網站活著）
3. `--page`（預設 `/`）的 HTML **經 `html.unescape` 後**：
   - 每個 `--marker` 字串都出現
   - 每個 `--absent` 字串都不出現
   - 日誌沒有 `address already in use`

> Razor 會把 `@ViewData["Title"]` 之類輸出的中文編成 `&#x9996;&#x9801;`，所以一定要先 unescape 再比對。

### 怎麼挑 marker

| 好的 marker | 不好的 marker |
|---|---|
| 本專案選單才有的項目（「授權驗證」） | 站名（十五個單元都叫 RagDemo） |
| 本單元特有的版本字串或頁面標題 | 共用版面的頁尾文字 |

`--absent` 放**後面單元才有**的選單項目（例如做第 02 單元時放「期末驗收」）。
結束碼 3 = 身分斷言失敗，行程保留著讓你檢查；查完用 `stop` 停掉。

---

## 四、外部相依與模擬模式

本機常缺的東西與處理方式：

| 缺什麼 | 處理 |
|---|---|
| 資料庫（或版本不對，例如 SQL Server 2022 沒有 `VECTOR`） | 開專案的記憶體／模擬開關 |
| LLM、Embedding 服務 | 開模擬開關；本機有 Ollama 可用就真跑 |
| 付費外部 API | **一律模擬**，不消耗使用者額度 |

ASP.NET Core 的巢狀設定用雙底線覆寫，不用改檔：

```powershell
--env Connectivity__Simulated=true --env Embedding__Simulated=true
```

先讀 `appsettings.Development.json` 找開關名稱。**只讀開關，不把金鑰、連線字串帶進任何輸出。**
用了模擬，就在 notes.md 記下來，旁白也要講。

---

## 五、登入

需要登入的頁面，在 storyboard 頂層放 `login` 區塊（`capture.py` 與 `inventory.py --login` 共用格式）：

```json
{
  "url": "http://localhost:5310/Identity/Account/Login",
  "user_selector": "#Input_Email",
  "pass_selector": "#Input_Password",
  "submit_selector": "button[type=submit]",
  "username": "<種子帳號>",
  "password": "<種子密碼>"
}
```

- 專案若有「開網址就簽發 Cookie」的開發用登入（例如 `/DevAuth/Login`），`login` 只給 `{"url": "/DevAuth/Login"}`
  即可，不給選擇器就只會開那個網址。但錄影時更好的做法是**不放頂層 login**，改在分鏡中段用一個 screen 場景
  `goto` 那個網址——登入本身就是要講的功能（以及「正式環境必須關閉」）。
- 帳號用專案的**種子／開發帳號**（看 `IdentitySeeder`、`SeedAdmin` 設定或操作說明）。
- 種子密碼若仍是「請填入…」這類佔位值，專案不會建帳號——**問使用者**，不要自己改設定檔。
- 登入畫面本身也是功能，要示範的話另寫一個 screen 場景（密碼欄只會顯示圓點）。
- 帶密碼的 login JSON 只放 scratchpad。

---

## 六、停止

```powershell
python launch.py stop --state "$WORK/{名稱}/launch.json"
```

`taskkill /PID <pid> /T /F`：連同 `dotnet run` 再開的子行程（`RagDemo.exe`）一起停，**只停自己啟動的那一棵**。
停完會再檢查一次埠有沒有釋放。

---

## 七、疑難排解

| 症狀 | 原因與處理 |
|---|---|
| 行程立刻結束 | 看 `launch.log` 尾巴：常見是 SDK 版本不符、建置錯誤、缺連線字串 |
| 180 秒沒回應 | 探針路徑不對（改 `--probe /`），或網站聽的不是指定埠（python/node 專案沒讀 `PORT`，改用 `--cmd`） |
| 身分斷言失敗 | marker 挑錯，或真的連到別的站——後者要查誰在聽那個埠 |
| 某頁 `goto` 逾時 | 頁面持續發請求，到不了 networkidle。`capture.py`／`inventory.py` 已改成 load + 最多 8 秒 idle，不會再卡死 |
| 擷取畫面是英文或日期格式怪 | context 已設 `locale="zh-TW"`；仍不對就是專案本身的文化設定 |
