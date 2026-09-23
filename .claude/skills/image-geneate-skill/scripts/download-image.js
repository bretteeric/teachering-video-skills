// playwright-cli run-code --filename=... 的腳本：必須是「單一函式運算式」，
// 不可使用 import / export / require。
//
// 【不要直接呼叫本檔】請透過 scripts/save-image.js：
//   node .claude/skills/image-geneate-skill/scripts/save-image.js
// 本檔只負責「把原圖的位元組取出來並回傳 base64」，寫檔由 save-image.js 做。
//
// ---------------------------------------------------------------------------
// 2026-09-09 改版。舊版（hover 圖片 → 找下載鈕 → download.saveAs）三個前提全部失效，
// 實測過程與結論如下，避免後人重走一遍：
//
// 1) 圖片來源不再是 oaiusercontent。
//    現為 `https://chatgpt.com/backend-api/estuary/content?id=file_...`（same-origin）。
//    舊選擇器 `main img[src*="oaiusercontent"]` 抓到 0 張。
//    改用**實際解碼尺寸**（naturalWidth/naturalHeight）判斷，不綁網域——
//    這同時就是「原圖 vs 預覽縮圖」的判準。
//
// 2) `button[aria-label*="下載"]` 會誤中側欄的「**下載應用程式**」。
//    那顆鈕永遠存在，所以舊版的 waitFor 立刻「成功」，再點下去卡滿 30 秒逾時。
//    而這個版本的 ChatGPT 介面裡，圖片訊息**根本沒有下載鈕**：
//    可用的只有 編輯圖片／共享此圖像／按讚此圖像／更多動作（＝查看來源、開啟新分支）。
//
// 3) 用 `<a download>` 觸發下載會**讓整個瀏覽器結束**（Session closed），
//    無論走 blob 還是 same-origin 直連、有沒有先另開分頁墊著都一樣。
//    download 事件雖然有發出來，但 `download.saveAs()` 需要發起下載的頁面還活著，
//    等 saveAs 執行時 Chrome 已經收掉了，必定拿到
//    "Target page, context or browser has been closed"。
//    （把網址直接 goto 也不行：estuary 是 inline 顯示，不會產生 download 事件。）
//
// 因此改走「頁內 fetch → base64 → 交給 Node 寫檔」：
//    run-code 沙箱沒有 require / process / Buffer / fs（已實測），
//    能寫檔的 Playwright API 只有 download.saveAs 與 page.screenshot，
//    前者被 (3) 堵死，後者是截圖（畫質與尺寸都不對，明令禁止）。
//    頁內 fetch 帶 cookie 取同源網址則完全正常，且拿到的就是原始位元組。
// ---------------------------------------------------------------------------
//
// 真正的把關仍是步驟八的尺寸檢查（必須 1024×1536）。
async page => {
  const MIN_EDGE = 1024; // 長寬都要 >= 這個值，否則是預覽縮圖不是原圖

  // 生圖完成才動手：ChatGPT 串流期間就會掛上最終解析度的 img，
  // 只看 naturalWidth 有機會抓到還沒畫完的中間狀態，所以同時排除「正在建立圖像」。
  await page.waitForFunction(
    (min) => {
      const main = document.querySelector('main');
      if (!main) return false;
      if (main.innerText.includes('正在建立圖像')) return false;
      return [...main.querySelectorAll('img')].some(
        (i) => i.naturalWidth >= min && i.naturalHeight >= min
      );
    },
    MIN_EDGE,
    { timeout: 240000 }
  );

  const url = await page.evaluate((min) => {
    const full = [...document.querySelectorAll('main img')].filter(
      (i) => i.naturalWidth >= min && i.naturalHeight >= min
    );
    return full.length ? full[full.length - 1].src : null; // 一則多圖時取最後一張
  }, MIN_EDGE);

  if (!url) throw new Error('找不到原始尺寸的圖片（main 內沒有長寬都 >= 1024 的 img）');

  const result = await page.evaluate(async (u) => {
    const r = await fetch(u, { credentials: 'include' });
    if (!r.ok) throw new Error('fetch 失敗：HTTP ' + r.status);
    const blob = await r.blob();
    const b64 = await new Promise((resolve, reject) => {
      const fr = new FileReader();
      fr.onload = () => resolve(String(fr.result).split(',')[1]); // 去掉 data:image/png;base64,
      fr.onerror = () => reject(new Error('FileReader 讀取失敗'));
      fr.readAsDataURL(blob);
    });
    return { b64, bytes: blob.size, type: blob.type };
  }, url);

  if (result.type && result.type !== 'image/png') {
    throw new Error('取回的不是 PNG：' + result.type);
  }
  return result;
}
