#!/usr/bin/env node
/**
 * md-to-pdf.js —— 教案 Markdown → PDF（A4 直式，繁體中文，含 Mermaid 圖）
 * ---------------------------------------------------------------------------
 *   node .claude/skills/document-creator-skill/scripts/md-to-pdf.js 講義/01_專題導入與環境建置.md
 *   node .claude/skills/document-creator-skill/scripts/md-to-pdf.js 講義/01_*.md --out=講義
 *
 * 為什麼是這條管線（已實測 2026-09-23）：
 *
 *   marked（瀏覽器內）  Markdown → HTML
 *   mermaid（瀏覽器內）  ```mermaid 區塊 → SVG
 *   Chrome page.pdf()   HTML → PDF
 *
 * - **不需要 pandoc / wkhtmltopdf / LaTeX / mmdc**，這台機器上都沒有，也不必裝。
 * - playwright-core 已隨全域的 `@playwright/cli` 裝好，用絕對路徑 require 就能用；
 *   瀏覽器用系統既有的 Chrome（`channel: 'chrome'`），不必另外下載 Playwright 的瀏覽器。
 * - 繁體中文靠系統字型「微軟正黑體」，不必嵌入字型檔。
 * - marked / mermaid 都已 vendor 到 scripts/vendor/，**全程離線**，不打 CDN。
 *
 * 排版約定：
 * - 開頭的 YAML front matter（session/title/subtitle/duration/outcome/example）
 *   會換成 H1 標題與資訊列；原稿本身已有 H1 時不重複產生。
 * - 每個 `##` 章節自動分頁（教案要「切開章節分別說明」），第一個 `##` 除外。
 * - 圖說：Mermaid 圖或擷圖正下方、整段只有 `*圖 NN-k　…*` 的段落，置中灰字。
 * - 表格、程式碼區塊、Mermaid 圖不跨頁切斷。
 * - 頁尾帶頁碼；頁首帶文件標題（取 H1）。
 */

const fs = require('fs');
const path = require('path');

const PW = 'C:/Users/brett/AppData/Roaming/npm/node_modules/@playwright/cli/node_modules/playwright-core';
const VENDOR = path.join(__dirname, 'vendor');

function fail(msg) {
  console.error(`[md-to-pdf] ${msg}`);
  process.exit(1);
}

// --- 參數 ------------------------------------------------------------------

const args = process.argv.slice(2);
const src = args.find((a) => !a.startsWith('--'));
if (!src) fail('用法：node md-to-pdf.js <講義/NN_主題.md> [--out=講義] [--keep-html]');
if (!fs.existsSync(src)) fail(`找不到來源檔：${src}`);

const outDir = (args.find((a) => a.startsWith('--out=')) || '--out=' + path.dirname(src)).slice(6);
const keepHtml = args.includes('--keep-html');

const stem = path.basename(src, path.extname(src));
const outPdf = path.join(outDir, stem + '.pdf');

for (const f of ['marked.min.js', 'mermaid.min.js']) {
  if (!fs.existsSync(path.join(VENDOR, f))) fail(`缺少 ${path.join('vendor', f)}；見 SKILL.md 的「離線資源」一節。`);
}

// --- 組出 HTML -------------------------------------------------------------

const raw = fs.readFileSync(src, 'utf8').replace(/^﻿/, '');

// YAML front matter（book-creator-skill 靠它編書）→ 換成 H1 + 資訊列。
// 不剝掉的話，marked 會把結尾的 `---` 當成 setext H2，多出一頁亂碼標題。
const fmMatch = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n/);
const fm = {};
if (fmMatch) {
  for (const line of fmMatch[1].split(/\r?\n/)) {
    const m = line.match(/^([A-Za-z_]+):\s*(.*)$/);
    if (m) fm[m[1]] = m[2].replace(/^["']|["']$/g, '').trim();
  }
}
let md = fmMatch ? raw.slice(fmMatch[0].length) : raw;
// 找 H1 時要跳過 ``` 程式碼區塊：Python／bash 的 `# 註解` 也是 `#` 開頭，會被誤認成 H1。
const withoutFences = (s) => s.replace(/^```[\s\S]*?^```/gm, '');
if (fmMatch && fm.title && !/^#\s+/m.test(withoutFences(md))) {
  const head = [`# Section ${fm.session || ''}｜${fm.title}`.replace('Section ｜', '')];
  if (fm.subtitle) head.push('', `> ${fm.subtitle}`);
  head.push('');
  if (fm.duration) head.push(`- **時數**：${fm.duration}`);
  if (fm.session) head.push(`- **對應大綱**：第 ${fm.session} 單元`);
  if (fm.outcome) head.push(`- **驗收成果**：${fm.outcome}`);
  if (fm.example) head.push(`- **範例專案**：\`${fm.example}\``);
  md = head.join('\n') + '\n\n' + md;
}

const title = (withoutFences(md).match(/^#\s+(.+)$/m) || [, stem])[1].trim();
const fileUrl = (p) => 'file:///' + path.resolve(p).replace(/\\/g, '/');

const html = `<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>${title.replace(/[<&]/g, (c) => ({ '<': '&lt;', '&': '&amp;' }[c]))}</title>
<style>
  :root { --ink:#1a1a1a; --muted:#5b6470; --line:#d7dce3; --accent:#006CB7; --soft:#f4f7fb; }
  * { box-sizing: border-box; }
  body {
    font-family: "Microsoft JhengHei", "微軟正黑體", "Noto Sans TC", sans-serif;
    color: var(--ink); font-size: 11pt; line-height: 1.75; margin: 0;
  }
  code, pre, kbd { font-family: Consolas, "Cascadia Mono", "Courier New", monospace; }

  h1 { font-size: 22pt; color: var(--accent); border-bottom: 3px solid var(--accent);
       padding-bottom: 8px; margin: 0 0 6px; line-height: 1.35; }
  h2 { font-size: 15pt; color: #fff; background: var(--accent); padding: 7px 12px;
       border-radius: 4px; margin: 0 0 12px; line-height: 1.4; }
  h3 { font-size: 12.5pt; color: var(--accent); border-left: 5px solid var(--accent);
       padding-left: 9px; margin: 18px 0 8px; }
  h4 { font-size: 11.5pt; margin: 14px 0 6px; }

  /* 每個 ## 章節起新頁；第一個不分頁。 */
  h2 { break-before: page; }
  h1 + h2, h1 ~ p:first-of-type + h2 { break-before: auto; }
  #content > h2:first-of-type { break-before: auto; }
  h1, h2, h3, h4 { break-after: avoid; }

  p, li { orphans: 3; widows: 3; }
  ul, ol { padding-left: 1.7em; }
  li { margin: 3px 0; }

  table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 10pt;
          break-inside: avoid; }
  th, td { border: 1px solid var(--line); padding: 6px 9px; text-align: left;
           vertical-align: top; }
  th { background: var(--soft); font-weight: 600; }

  pre { background: #1e2430; color: #e8edf5; padding: 11px 14px; border-radius: 5px;
        font-size: 9pt; line-height: 1.55; overflow: visible; white-space: pre-wrap;
        word-break: break-all; break-inside: avoid; }
  pre code { background: none; color: inherit; padding: 0; }
  :not(pre) > code { background: var(--soft); color: #b3005e; padding: 1px 5px;
                     border-radius: 3px; font-size: 9.5pt; }

  blockquote { border-left: 4px solid var(--accent); background: var(--soft);
               margin: 12px 0; padding: 9px 14px; color: var(--muted);
               break-inside: avoid; }

  img { max-width: 100%; height: auto; border: 1px solid var(--line);
        border-radius: 4px; break-inside: avoid; display: block; margin: 10px auto; }

  .mermaid { text-align: center; margin: 14px 0; break-inside: avoid; }
  .mermaid svg { max-width: 100%; height: auto; }

  /* 圖說：緊接在 Mermaid 圖或擷圖後、整段只有一個 *斜體* 的段落。 */
  .mermaid + p:has(> em:only-child), p:has(> img) + p:has(> em:only-child) {
    text-align: center; color: var(--muted); font-size: 9.5pt; margin: -6px 0 14px;
    break-before: avoid; }
  .mermaid + p:has(> em:only-child) em, p:has(> img) + p:has(> em:only-child) em { font-style: normal; }

  hr { border: none; border-top: 1px solid var(--line); margin: 20px 0; }
  a { color: var(--accent); text-decoration: none; }
</style>
</head>
<body>
<div id="content"></div>
<script src="${fileUrl(path.join(VENDOR, 'marked.min.js'))}"></script>
<script src="${fileUrl(path.join(VENDOR, 'mermaid.min.js'))}"></script>
<script id="md-source" type="text/plain">${md.replace(/<\/script>/gi, '<\\/script>')}</script>
<script>
(async () => {
  try {
    const src = document.getElementById('md-source').textContent;
    document.getElementById('content').innerHTML = marked.parse(src);

    // mermaid 圍欄區塊會被 marked 變成 <pre><code class="language-mermaid">，換回 mermaid 要的容器
    document.querySelectorAll('pre > code.language-mermaid').forEach((code) => {
      const div = document.createElement('div');
      div.className = 'mermaid';
      div.textContent = code.textContent;
      code.parentElement.replaceWith(div);
    });

    const blocks = document.querySelectorAll('.mermaid');
    if (blocks.length) {
      mermaid.initialize({
        startOnLoad: false,
        theme: 'base',
        securityLevel: 'loose',
        fontFamily: '"Microsoft JhengHei","微軟正黑體",sans-serif',
        themeVariables: {
          primaryColor: '#e8f1fb', primaryBorderColor: '#006CB7', primaryTextColor: '#1a1a1a',
          lineColor: '#5b6470', fontSize: '15px',
        },
      });
      await mermaid.run({ nodes: blocks });
    }
    window.__mermaidCount = blocks.length;
    window.__renderDone = true;
  } catch (err) {
    window.__renderError = String((err && err.message) || err);
    window.__renderDone = true;
  }
})();
</script>
</body>
</html>`;

// 暫存 HTML 放在 md 同目錄，讓 ![](images/NN/x.png) 這類相對路徑照樣解析得到。
const tmpHtml = path.join(path.dirname(src), `.__${stem}.tmp.html`);
fs.writeFileSync(tmpHtml, html, 'utf8');

// --- 出 PDF ----------------------------------------------------------------

(async () => {
  let chromium;
  try {
    ({ chromium } = require(PW));
  } catch {
    fail(`無法載入 playwright-core（${PW}）。請確認全域已裝 @playwright/cli。`);
  }

  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage();
    const consoleErrors = [];
    page.on('pageerror', (e) => consoleErrors.push(e.message));

    await page.goto(fileUrl(tmpHtml), { waitUntil: 'load' });
    await page.waitForFunction('window.__renderDone === true', null, { timeout: 60000 });

    const err = await page.evaluate('window.__renderError || null');
    if (err) fail(`頁面渲染失敗：${err}`);
    const mermaidCount = await page.evaluate('window.__mermaidCount || 0');

    // 圖片載不到會靜靜變成破圖，先點出來而不是讓它進 PDF。
    const brokenImgs = await page.evaluate(
      `Array.from(document.images).filter(i => !i.complete || i.naturalWidth === 0).map(i => i.getAttribute('src'))`
    );

    fs.mkdirSync(path.dirname(path.resolve(outPdf)), { recursive: true });
    await page.pdf({
      path: outPdf,
      format: 'A4',
      printBackground: true,
      margin: { top: '20mm', bottom: '18mm', left: '16mm', right: '16mm' },
      displayHeaderFooter: true,
      headerTemplate:
        `<div style="font-family:'Microsoft JhengHei',sans-serif;font-size:7.5pt;color:#8a929c;width:100%;padding:0 16mm;">` +
        `<span style="float:left">${title.replace(/[<&"]/g, '')}</span></div>`,
      footerTemplate:
        `<div style="font-family:'Microsoft JhengHei',sans-serif;font-size:7.5pt;color:#8a929c;width:100%;padding:0 16mm;text-align:center;">` +
        `<span class="pageNumber"></span> / <span class="totalPages"></span></div>`,
    });

    const size = fs.statSync(outPdf).size;
    console.log(`[md-to-pdf] 已輸出 ${outPdf}（${(size / 1024).toFixed(0)} KB、Mermaid ${mermaidCount} 張）`);
    if (brokenImgs.length) {
      console.warn(`[md-to-pdf] 警告：${brokenImgs.length} 張圖片載不到，PDF 內會是空白：`);
      brokenImgs.forEach((s) => console.warn(`  - ${s}`));
    }
    if (consoleErrors.length) {
      console.warn(`[md-to-pdf] 頁面 JS 有錯（PDF 仍已產出，但 Mermaid 可能沒畫出來）：`);
      consoleErrors.slice(0, 5).forEach((s) => console.warn(`  - ${s}`));
    }
  } finally {
    await browser.close();
    if (!keepHtml) {
      try { fs.unlinkSync(tmpHtml); } catch { /* 留著也無妨 */ }
    } else {
      console.log(`[md-to-pdf] 保留中繼檔：${tmpHtml}`);
    }
  }
})().catch((e) => fail(`${(e && e.stack) || e}`));
