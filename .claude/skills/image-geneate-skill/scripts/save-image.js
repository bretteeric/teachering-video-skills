#!/usr/bin/env node
/**
 * save-image.js —— 步驟七的進入點。
 *
 *   node .claude/skills/image-geneate-skill/scripts/save-image.js
 *   mv "海報/__latest-poster.png" "海報/NN 標題.png"
 *
 * 為什麼要多這一層：run-code 的沙箱沒有 require / process / Buffer / fs（已實測），
 * 唯一能寫檔的 download.saveAs 又會因為 `<a download>` 讓瀏覽器整個關掉而必定失敗
 * （原因寫在 download-image.js 的檔頭）。所以改成：
 *
 *   download-image.js（在瀏覽器裡）  取原圖位元組 → 回傳 base64
 *   save-image.js    （在 Node 裡）  解碼 base64 → 寫成 海報/__latest-poster.png
 *
 * 路徑一律用相對路徑：Node 的 cwd 就是 workspace，
 * 因此同一份 skill 複製到 金剛經/workspace、心經/workspace 都能用。
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const SESSION = process.env.POSTER_SESSION || 'chatgpt';
if (!/^[A-Za-z0-9_-]+$/.test(SESSION)) fail(`POSTER_SESSION 只能是英數字、_ 或 -：${SESSION}`);
const RUN_SCRIPT = path.join('.claude', 'skills', 'image-geneate-skill', 'scripts', 'download-image.js');
const OUT = path.join('海報', '__latest-poster.png');

function fail(msg) {
  console.error(`[save-image] ${msg}`);
  process.exit(1);
}

if (!fs.existsSync(RUN_SCRIPT)) fail(`找不到 ${RUN_SCRIPT}；請在 workspace 根目錄執行。`);

let stdout;
try {
  // playwright-cli 在 Windows 是 .cmd 外殼，必須走 shell；因此用單一字串命令，
  // 不要用 execFileSync(args, {shell:true})，那會觸發 Node 的 DEP0190 警告。
  stdout = execSync(
    `playwright-cli -s=${SESSION} run-code --filename="${RUN_SCRIPT}"`,
    { encoding: 'utf8', maxBuffer: 128 * 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe'] }
  );
} catch (err) {
  const out = `${err.stdout || ''}${err.stderr || ''}`.trim();
  fail(`playwright-cli 執行失敗：\n${out.slice(0, 800)}`);
}

// playwright-cli 的輸出格式：`### Result` 之後是 JSON，再接 `### Ran Playwright code`。
const MARKER = '### Result';
const start = stdout.indexOf(MARKER);
if (start === -1) fail(`輸出裡沒有 ${MARKER}，瀏覽器可能沒開或腳本拋錯：\n${stdout.slice(0, 800)}`);

let body = stdout.slice(start + MARKER.length);
const end = body.indexOf('### Ran Playwright code');
if (end !== -1) body = body.slice(0, end);

let data;
try {
  data = JSON.parse(body.trim());
} catch (err) {
  fail(`無法解析 run-code 回傳的 JSON（可能被截斷，長度 ${body.trim().length}）：${err.message}`);
}

if (!data || typeof data.b64 !== 'string' || !data.b64) fail(`回傳沒有 b64 欄位：${JSON.stringify(data).slice(0, 300)}`);

const buf = Buffer.from(data.b64, 'base64');

// PNG 檔頭把關，避免把一段錯誤訊息當成圖存下來。
const isPng = buf.length > 8 && buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4e && buf[3] === 0x47;
if (!isPng) fail(`解碼結果不是 PNG（前 8 bytes：${buf.subarray(0, 8).toString('hex')}）`);

if (typeof data.bytes === 'number' && data.bytes !== buf.length) {
  fail(`位元組數對不上：瀏覽器端 ${data.bytes}、解碼後 ${buf.length}，base64 可能被截斷。`);
}

fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, buf);

console.log(`[save-image] 已存 ${OUT}（${buf.length} bytes）`);
