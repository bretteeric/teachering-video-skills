# 場景擷取

所有素材最終都是 **3840×2160 PNG**，由 `compose.py` 加上運鏡後串成影片。

---

## 一、4K 銳利度的關鍵：deviceScaleFactor

```python
context = browser.new_context(
    viewport={"width": 1920, "height": 1080},
    device_scale_factor=2,          # ← 輸出 3840×2160
)
```

**不要**直接開 `viewport={"width": 3840, "height": 2160}`。兩者差別：

| 作法 | 版面 | 文字品質 | 結果 |
|---|---|---|---|
| viewport 1920 + `dsf=2` | 正常桌機版面 | 2 倍密度渲染 | ✅ 銳利，元素大小合理 |
| viewport 3840 + `dsf=1` | 超寬版面 | 1 倍渲染 | ✗ 所有元素小到看不清 |

網頁的 CSS 像素仍是 1920 寬（版面正常），但每個 CSS 像素用 2×2 實體像素渲染，文字邊緣是真的 4K 銳利度，不是放大。

## 二、不要用 Playwright 錄影

`record_video` 輸出 VP8 webm：文字邊緣模糊、4K 下嚴重掉幀、無法控制時間軸對齊旁白。

**改用「關鍵畫面截圖 + ffmpeg 合成運鏡」**：畫質是無損 PNG，且每個畫面停留多久完全由旁白長度決定 —— 這正是「配合語音」的要求。

需要展示連續動作（打字、Modal 開闔）時，就多截幾張關鍵影格，靠轉場銜接。

---

## 三、擷取流程

```python
page.goto(url, wait_until="networkidle")
page.wait_for_timeout(400)              # 等 CSS transition / Vue 掛載完成
page.screenshot(path=out, scale="device")   # scale="device" 才會輸出 3840×2160
```

`scale="device"` 不可省略。預設 `scale="css"` 會輸出 1920×1080。

### 步驟動作表

| action | 參數 | 用途 |
|---|---|---|
| `goto` | `url` | 換頁 |
| `click` | `selector`, `highlight` | 點擊；`highlight` 會先標示再點 |
| `focus` | `selector` | 只標示不點擊（指出結果列、說明區塊），截一張帶框影格後移除框 |
| `type` | `selector`, `text` | 逐字輸入（`delay=60` 較像真人） |
| `select` | `selector`, `value` | 下拉選單選值 |
| `upload` | `selector`, `path` | 把檔案交給 `<input type=file>`（檔案對話框是作業系統視窗，無法擷取） |
| `zoom` | `value` | 整頁放大（原始 JSON 等純文字頁面用） |
| `hover` | `selector` | 移入 |
| `wait` | `ms` 或 `selector` | 等待 |
| `scroll` | `selector` | 捲動至元素 |
| `shot` | `name` | 當下截圖 |

**每個 step 執行後都截一張圖**，作為該步驟的關鍵影格。
不需要那一張時，在該 step 加 `"shot": false` 略過——例如 `goto` 到原始 JSON 頁面後
還要再 `zoom`，放大前那張字太小、畫面幾乎全空，留著會變成十幾秒的空畫面。

### 焦點標示

點擊前先把目標框起來，觀眾才知道要看哪：

```python
page.evaluate("""(sel) => {
  const el = document.querySelector(sel);
  if (!el) return;
  const r = el.getBoundingClientRect();
  const box = document.createElement('div');
  box.id = '__focus__';
  Object.assign(box.style, {
    position: 'fixed',
    left: (r.left - 8) + 'px', top: (r.top - 8) + 'px',
    width: (r.width + 16) + 'px', height: (r.height + 16) + 'px',
    border: '6px solid #B04A32',      // 與字幕同色，視覺一致
    borderRadius: '12px',
    boxShadow: '0 0 0 9999px rgba(0,0,0,.45)',   // 其餘變暗
    pointerEvents: 'none', zIndex: 2147483647,
  });
  document.body.appendChild(box);
}""", selector)
```

截完圖後移除：`page.evaluate("document.getElementById('__focus__')?.remove()")`

> 標示框用 `#B04A32`，與字幕同色，整支影片的視覺語言一致。

---

## 四、Flask 專案的前置條件

`screen` 類型場景需要伺服器已在運行：

```powershell
.\.venv\Scripts\Activate.ps1
$env:FLASK_ENV = "development"
Start-Process python -ArgumentList "run.py"
# 確認可連線後再開始擷取
```

需要登入的頁面，第一個 step 先做登入，Playwright 的 context 會保留 session cookie。

**注意**：示範資料請用 seed 資料，不要出現真實個資。

---

## 五、mermaid 圖解

用於講「看不見的東西」——架構、資料流、狀態機、時序。截圖講不清楚的都該配圖。

### 產生方式（優先序）

**1. mermaid-cli（實測可用，v11.17.0）**

```powershell
npx -y @mermaid-js/mermaid-cli `
  -i diagram.mmd -o diagram.png `
  -t dark -b "#0f172a" -w 3200 -H 1800 -s 2
```

`-s 2` 是 scale factor，配合 `-w/-H` 得到 4K 級解析度。輸出若非 3840×2160，由 `compose.py` 置中貼到 4K 畫布上（不要拉伸變形）。

**2. Playwright + 本機 mermaid.min.js（離線後備）**

本專案有「禁用 CDN」的離線鐵則。若擷取環境不能連網，先把 mermaid 落地：

```powershell
npm install mermaid --no-save
Copy-Item node_modules/mermaid/dist/mermaid.min.js app/static/js/
```

再用一個本機 HTML 承載，以 `device_scale_factor=2` 截圖 `.mermaid` 元素。

### 圖表風格

配合本專案的深色玻璃霧狀主視覺：

```
%%{init: {'theme':'dark', 'themeVariables': {
  'primaryColor':'#1e293b', 'primaryTextColor':'#e2e8f0',
  'primaryBorderColor':'#B04A32', 'lineColor':'#94a3b8',
  'fontFamily':'Microsoft JhengHei', 'fontSize':'28px'
}}}%%
flowchart LR
  A[感測器] --> B[閘道器]
  B --> C[(資料庫)]
```

- **`fontFamily` 必須指定中文字型**，否則節點內中文變方框。
- 字級用 **28px 以上**（縮到 4K 畫面裡才讀得到）。
- 節點文字**精簡**，長說明交給旁白，不要塞進圖裡。
- 單張圖 **≤ 12 個節點**。更複雜就拆成多個場景，配合旁白逐步揭露。

---

## 六、標題卡與重點卡

`title` / `slide` 類型不需瀏覽器，直接用 Pillow 或 ffmpeg 生成，風格對齊專案的深色漸層 + 玻璃霧狀：

- 背景：`#0f172a` → `#1e293b` 深色漸層
- 標題：微軟正黑體 Bold 200px，`#f1f5f9`
- 副標：微軟正黑體 120px，`#94a3b8`
- 重點卡：每頁 **≤ 4 條**，每條 ≤ 20 字

留意底部 **400px** 要留給字幕，不要放內容。
