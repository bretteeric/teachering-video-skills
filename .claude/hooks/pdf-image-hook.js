#!/usr/bin/env node
/**
 * pdf-image-hook
 * ---------------------------------------------------------------------------
 * 監看 workspace 底下的 `講義/`，當有 PDF「新增完成」時，喚醒 Claude 去呼叫
 * skill `image-geneate-skill` 產生單元海報。
 *
 * 由 .claude/settings.json 的兩個 hook 事件驅動：
 *
 *   session-start  (SessionStart)
 *     建立 `講義/`，並把它的絕對路徑用 hookSpecificOutput.watchPaths 回報給
 *     Claude Code 的檔案監看器；順便列出「還沒有海報」的 PDF 當背景資訊。
 *
 *   file-changed   (FileChanged, asyncRewake:true)
 *     stdin 會拿到 { hook_event_name, file_path, event, cwd, ... }。
 *     確認是 `講義/` 直屬的、寫入已完成的新 PDF 之後，把指示寫到 stderr 並以
 *     exit code 2 結束 —— asyncRewake 會把這段文字當成 system-reminder 叫醒模型。
 *     其他情況一律安靜地 exit 0，不打擾使用者。
 *
 * 檔案寫入是否完成：Claude Code 的監看器本身帶 awaitWriteFinish（穩定 500ms 才
 * 送事件），這裡再補一道 `%PDF` 檔頭檢查，避免抓到寫到一半的檔案。
 */

const fs = require('fs');
const path = require('path');

const LECTURE_DIR = '講義';
const POSTER_DIR = '海報';
const SKILL_NAME = 'image-geneate-skill';
const STATE_FILE = path.join('.claude', 'hooks', 'pdf-image-hook.state.json');

const IS_WIN = process.platform === 'win32';

// --- 小工具 ----------------------------------------------------------------

function readStdin() {
  return new Promise((resolve) => {
    if (process.stdin.isTTY) return resolve('');
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => (data += chunk));
    process.stdin.on('end', () => resolve(data));
    process.stdin.on('error', () => resolve(data));
  });
}

function parseInput(raw) {
  try {
    return JSON.parse(raw) || {};
  } catch {
    return {};
  }
}

/** hook 的工作目錄不保證是 workspace，優先用 Claude Code 給的專案根目錄。 */
function projectRoot(input) {
  return path.resolve(process.env.CLAUDE_PROJECT_DIR || input.cwd || process.cwd());
}

function samePath(a, b) {
  const x = path.resolve(a);
  const y = path.resolve(b);
  return IS_WIN ? x.toLowerCase() === y.toLowerCase() : x === y;
}

function readState(root) {
  try {
    return JSON.parse(fs.readFileSync(path.join(root, STATE_FILE), 'utf8')) || {};
  } catch {
    return {};
  }
}

function writeState(root, state) {
  const file = path.join(root, STATE_FILE);
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify(state, null, 2) + '\n', 'utf8');
  } catch {
    /* 記不起來頂多重複提醒一次，不值得讓 hook 失敗 */
  }
}

/** 03_無住.pdf -> 03；沒有數字前綴就回傳去掉副檔名的檔名。 */
function unitKey(pdfName) {
  const stem = path.basename(pdfName, path.extname(pdfName));
  const m = stem.match(/^(\d{1,3})/);
  return m ? m[1] : stem;
}

/** 找同一單元的講義 .md（skill 真正吃的來源）。 */
function findLectureMd(lectureDir, key) {
  let names;
  try {
    names = fs.readdirSync(lectureDir);
  } catch {
    return null;
  }
  const md = names.filter((n) => n.toLowerCase().endsWith('.md'));
  return (
    md.find((n) => n.startsWith(key + '_')) ||
    md.find((n) => n.startsWith(key + ' ')) ||
    md.find((n) => path.basename(n, '.md') === key) ||
    null
  );
}

/** 海報/NN ....png 是否已經存在。前綴後面必須接非數字，才不會讓 1 誤中 10。 */
function hasPoster(posterDir, key) {
  const prefix = new RegExp('^' + key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(\\D|$)');
  try {
    return fs
      .readdirSync(posterDir)
      .some((n) => n.toLowerCase().endsWith('.png') && prefix.test(n));
  } catch {
    return false;
  }
}

function looksLikePdf(file) {
  let fd;
  try {
    fd = fs.openSync(file, 'r');
    const buf = Buffer.alloc(5);
    const n = fs.readSync(fd, buf, 0, 5, 0);
    return n === 5 && buf.toString('latin1', 0, 4) === '%PDF';
  } catch {
    return false;
  } finally {
    if (fd !== undefined) {
      try {
        fs.closeSync(fd);
      } catch {
        /* ignore */
      }
    }
  }
}

// --- FileChanged -----------------------------------------------------------

function runFileChanged(input) {
  // 只認「新增」。覆蓋既有檔案（change）與刪除（unlink）都不觸發。
  if (input.event !== 'add') return 0;

  const filePath = input.file_path;
  if (typeof filePath !== 'string' || filePath === '') return 0;
  if (path.extname(filePath).toLowerCase() !== '.pdf') return 0;

  const name = path.basename(filePath);
  if (name.startsWith('~$') || name.startsWith('.')) return 0; // Office / 系統暫存檔

  const root = projectRoot(input);
  const lectureDir = path.join(root, LECTURE_DIR);
  // 只收 講義/ 直屬的 PDF，講義/images/ 之類的子資料夾不算。
  if (!samePath(path.dirname(filePath), lectureDir)) return 0;

  let st;
  try {
    st = fs.statSync(filePath);
  } catch {
    return 0; // 事件送到時檔案已經不在了
  }
  if (!st.isFile() || st.size === 0) return 0;
  if (!looksLikePdf(filePath)) return 0; // 還在寫、或根本不是 PDF

  // 同一份檔案（大小＋mtime 都沒變）不重複叫醒模型。
  const state = readState(root);
  const stamp = `${st.size}:${Math.floor(st.mtimeMs)}`;
  if (state[name] && state[name].stamp === stamp) return 0;
  state[name] = { stamp, notifiedAt: new Date().toISOString() };
  writeState(root, state);

  const key = unitKey(name);
  const md = findLectureMd(lectureDir, key);
  const posterExists = hasPoster(path.join(root, POSTER_DIR), key);

  const lines = [
    `[pdf-image-hook] ${LECTURE_DIR}/ 新增了一份 PDF：${LECTURE_DIR}/${name}`,
    '',
    `請立刻用 Skill 工具呼叫 \`${SKILL_NAME}\`，args 傳入「${key}」，為這一單元產生海報。`,
    '',
    md
      ? `・對應講義：${LECTURE_DIR}/${md}（已存在）。依 skill 原流程，用這份 .md 當講義來源上傳。`
      : `・目前 ${LECTURE_DIR}/ 底下沒有 ${key} 對應的 .md。此時請改用這份 PDF（${LECTURE_DIR}/${name}）當附件上傳給 ChatGPT——` +
        'skill 前置條件裡「沒有 .md 就直接回報」那一條在這個情境不適用，不要因此中止，也不要自己編一份講義。',
    `・海報命名與存放依 skill 步驟二、步驟七：存成 ${POSTER_DIR}/${key} <主標>.png，並做步驟八的 1024×1536 尺寸檢查。`,
  ];
  if (posterExists) {
    lines.push(
      `・注意：${POSTER_DIR}/ 已經有 ${key} 開頭的海報。依 skill 步驟二，先問使用者要重畫（存成 v2）還是跳過，不要直接覆蓋。`
    );
  }
  lines.push('', '（這則訊息由 workspace 的 pdf-image-hook 自動送出。）');

  process.stderr.write(lines.join('\n') + '\n');
  return 2; // asyncRewake：exit 2 才會把上面這段送去叫醒模型
}

// --- SessionStart ----------------------------------------------------------

function runSessionStart(input) {
  const root = projectRoot(input);
  const lectureDir = path.join(root, LECTURE_DIR);
  try {
    fs.mkdirSync(lectureDir, { recursive: true });
  } catch {
    /* 建不起來就讓監看器自己去處理 */
  }

  const out = {
    hookSpecificOutput: {
      hookEventName: 'SessionStart',
      watchPaths: [lectureDir],
    },
    suppressOutput: true,
  };

  let pending = [];
  try {
    const posterDir = path.join(root, POSTER_DIR);
    pending = fs
      .readdirSync(lectureDir)
      .filter((n) => n.toLowerCase().endsWith('.pdf') && !n.startsWith('~$') && !n.startsWith('.'))
      .filter((n) => !hasPoster(posterDir, unitKey(n)));
  } catch {
    pending = [];
  }

  if (pending.length > 0) {
    out.hookSpecificOutput.additionalContext =
      `[pdf-image-hook] ${LECTURE_DIR}/ 底下有 ${pending.length} 份 PDF 還沒有對應的 ${POSTER_DIR}/ 海報：` +
      pending.join('、') +
      `。此為背景資訊，不必主動執行；使用者開口時再用 ${SKILL_NAME} 產生海報。`;
  }

  process.stdout.write(JSON.stringify(out) + '\n');
  return 0;
}

// --- 進入點 ----------------------------------------------------------------

async function main() {
  const mode = process.argv[2] || 'file-changed';
  const input = parseInput(await readStdin());

  if (mode === 'session-start') return runSessionStart(input);
  if (mode === 'file-changed') return runFileChanged(input);
  return 0;
}

main()
  .then((code) => {
    process.exitCode = code;
  })
  .catch((err) => {
    // 用 1 而不是 2：hook 自己壞掉不該被當成「有新 PDF」去叫醒模型。
    process.stderr.write(`[pdf-image-hook] 執行失敗：${(err && err.stack) || err}\n`);
    process.exitCode = 1;
  });
