#!/usr/bin/env node
/**
 * capture-screens.js —— 在模擬環境擷取教案用的操作畫面
 * ---------------------------------------------------------------------------
 *   node .claude/skills/document-creator-skill/scripts/capture-screens.js \
 *     --base=http://localhost:5199 --out=講義/images/03 \
 *     "/=01-首頁" "/Admin/Upload=02-上傳頁"
 *
 * 每個位置參數的格式是 `<路徑>=<檔名>`，會存成 <out>/<檔名>.png。
 *
 * 選項：
 *   --base=<url>        網站根位址（必填）
 *   --out=<dir>         輸出目錄（預設 講義/images）
 *   --width=<px>        視窗寬，預設 1280
 *   --height=<px>       視窗高，預設 800
 *   --full              整頁擷取（預設只擷可視範圍，教案用圖通常這樣就夠）
 *   --scale=<n>         解析度倍率，預設 2（PDF 縮圖後才不會糊）
 *   --wait=<ms>         每頁額外等待毫秒數，預設 600（等前端 JS 畫完）
 *   --headed            顯示瀏覽器視窗，用來除錯
 *
 * 用系統既有的 Chrome（channel: 'chrome'），不必另外下載 Playwright 瀏覽器。
 * 與 md-to-pdf.js 共用同一份全域 playwright-core。
 */

const fs = require('fs');
const path = require('path');

const PW = 'C:/Users/brett/AppData/Roaming/npm/node_modules/@playwright/cli/node_modules/playwright-core';

function fail(msg) {
  console.error(`[capture-screens] ${msg}`);
  process.exit(1);
}

const argv = process.argv.slice(2);
const opt = (name, dflt) => {
  const hit = argv.find((a) => a.startsWith(`--${name}=`));
  return hit === undefined ? dflt : hit.slice(name.length + 3);
};

const base = opt('base');
if (!base) fail('缺少 --base=<網站根位址>。用法見檔頭註解。');

const outDir = opt('out', path.join('講義', 'images'));
const width = parseInt(opt('width', '1280'), 10);
const height = parseInt(opt('height', '800'), 10);
const scale = parseFloat(opt('scale', '2'));
const waitMs = parseInt(opt('wait', '600'), 10);
const fullPage = argv.includes('--full');
const headed = argv.includes('--headed');

const targets = argv
  .filter((a) => !a.startsWith('--'))
  .map((a) => {
    const i = a.lastIndexOf('=');
    if (i <= 0) fail(`參數格式要是 "<路徑>=<檔名>"，收到：${a}`);
    return { route: a.slice(0, i), name: a.slice(i + 1) };
  });

if (targets.length === 0) fail('至少要給一個 "<路徑>=<檔名>"。');

// Git Bash（MSYS）會把 "/" 開頭的參數當成 Unix 路徑，自動改寫成 "C:/Program Files/Git/..."。
// 已實測會發生，且錯得很安靜——網址變成一串垃圾，只看到 goto 失敗。這裡直接擋下來講清楚。
for (const t of targets) {
  if (/^[A-Za-z]:[\\/]/.test(t.route)) {
    fail(
      `路徑被 Git Bash 改寫成了 Windows 絕對路徑：${t.route}\n` +
        '  在指令前面加上 MSYS_NO_PATHCONV=1 再跑一次，例如：\n' +
        '    MSYS_NO_PATHCONV=1 node .../capture-screens.js --base=... "/=01-首頁"\n' +
        '  改用 PowerShell 執行則沒有這個問題。'
    );
  }
}

(async () => {
  let chromium;
  try {
    ({ chromium } = require(PW));
  } catch {
    fail(`無法載入 playwright-core（${PW}）。請確認全域已裝 @playwright/cli。`);
  }

  fs.mkdirSync(outDir, { recursive: true });

  const browser = await chromium.launch({ channel: 'chrome', headless: !headed });
  const results = [];
  try {
    const page = await browser.newPage({
      viewport: { width, height },
      deviceScaleFactor: scale,
      locale: 'zh-TW',
    });

    for (const { route, name } of targets) {
      const url = base.replace(/\/+$/, '') + (route.startsWith('/') ? route : '/' + route);
      const file = path.join(outDir, name.endsWith('.png') ? name : name + '.png');
      try {
        const resp = await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
        const status = resp ? resp.status() : 0;
        if (status >= 400) {
          // 400/500 的錯誤頁不該被當成教學畫面存下來。
          results.push({ url, file, ok: false, why: `HTTP ${status}` });
          continue;
        }
        await page.waitForTimeout(waitMs);
        await page.screenshot({ path: file, fullPage });
        results.push({ url, file, ok: true, why: `HTTP ${status}` });
      } catch (e) {
        results.push({ url, file, ok: false, why: (e && e.message ? e.message : String(e)).split('\n')[0] });
      }
    }
  } finally {
    await browser.close();
  }

  let failed = 0;
  for (const r of results) {
    if (r.ok) {
      const kb = (fs.statSync(r.file).size / 1024).toFixed(0);
      console.log(`[capture-screens] OK   ${r.file}（${kb} KB）← ${r.url}`);
    } else {
      failed++;
      console.error(`[capture-screens] 失敗 ${r.url} → ${r.why}`);
    }
  }
  console.log(`[capture-screens] 成功 ${results.length - failed} / ${results.length} 張，輸出目錄 ${outDir}`);
  if (failed) {
    console.error('[capture-screens] 有畫面沒擷到：確認網站已啟動、路徑正確，再重跑一次。');
    process.exit(1);
  }
})().catch((e) => fail(`${(e && e.stack) || e}`));
