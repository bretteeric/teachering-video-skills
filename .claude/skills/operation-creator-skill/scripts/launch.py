#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""找出、啟動、停止要錄影的專案。

三個子命令：

  list   列出資料夾裡的每一個可執行專案，並決定影片檔名
  start  在「確定沒人用」的連接埠啟動專案，等到能回應、且頁面內容正確才算就緒
  stop   只停掉 start 啟動的那個行程樹，絕不碰別人的行程

用法:
  python launch.py list  --root "範例"
  python launch.py start --project "範例/02_xxx" --state "$WORK/launch.json" \
                         --marker "RagDemo" --absent "期末驗收" --probe /api/public/ping
  python launch.py stop  --state "$WORK/launch.json"

為什麼不沿用專案自己的連接埠：其他單元的範例站可能已經佔住同一個埠。
那時 dotnet run 會以 address already in use 失敗，但輪詢仍拿得到 200 ——
回應來自別的站，截圖就整批擷到錯的 app。所以一律挑空的埠，再斷言頁面內容。
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SKIP_DIRS = {"bin", "obj", "node_modules", ".git", ".vs", ".venv", "venv",
             "__pycache__", "publish", "wwwroot", "dist", "build", ".playwright-mcp"}
PORT_FROM = 5310
READY_TIMEOUT = 180          # dotnet 第一次 run 要還原＋建置，給寬一點


# ---------------------------------------------------------------- 偵測

def _walk(root: Path, depth: int):
    """有限深度走訪，略過建置輸出與套件資料夾。"""
    if depth < 0:
        return
    try:
        entries = list(root.iterdir())
    except OSError:
        return
    yield root, [e for e in entries if e.is_file()]
    for d in entries:
        if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith("."):
            yield from _walk(d, depth - 1)


def _is_web_csproj(p: Path) -> bool:
    if re.search(r"\.Tests?$", p.stem, re.I):
        return False
    try:
        head = p.read_text(encoding="utf-8", errors="ignore")[:600]
    except OSError:
        return False
    return "Microsoft.NET.Sdk.Web" in head or "Microsoft.NET.Sdk.Razor" in head


def detect(project: Path) -> dict | None:
    """回傳 {type, entry, cwd}；找不到可執行的網站就回 None。"""
    for d, files in _walk(project, 3):
        for f in files:
            if f.suffix == ".csproj" and _is_web_csproj(f):
                return {"type": "dotnet", "entry": str(f), "cwd": str(f.parent)}
    for d, files in _walk(project, 2):
        names = {f.name for f in files}
        for cand in ("run.py", "app.py", "wsgi.py", "main.py"):
            if cand in names:
                src = (d / cand).read_text(encoding="utf-8", errors="ignore")
                if re.search(r"\b(Flask|FastAPI|create_app)\b", src):
                    return {"type": "python", "entry": str(d / cand), "cwd": str(d)}
        if "package.json" in names:
            try:
                pkg = json.loads((d / "package.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if any(k in pkg.get("scripts", {}) for k in ("dev", "start")):
                return {"type": "node", "entry": str(d / "package.json"), "cwd": str(d)}
    return None


def cmd_list(a) -> int:
    """資料夾本身是專案 → 一支影片；否則每個子資料夾是一個專案 → 逐一出片。

    影片檔名 = 專案資料夾名稱（不是 csproj 名稱：十五個單元的 csproj 全叫 RagDemo）。
    """
    root = Path(a.root).resolve()
    out = []
    children = [(c, detect(c)) for c in sorted(root.iterdir())
                if c.is_dir() and c.name not in SKIP_DIRS]
    children = [(c, i) for c, i in children if i]
    # 只有一個子資料夾是專案（例如 02_xxx/RagDemo/）→ 整個資料夾就是那一個專案，
    # 影片以外層資料夾命名；兩個以上才是「一個資料夾放很多專案」要逐一出片。
    if len(children) >= 2:
        for c, info in children:
            out.append({"name": c.name, "project": str(c), **info})
    else:
        own = detect(root)
        if own:
            out.append({"name": root.name, "project": str(root), **own})
    if a.videos:
        vd = Path(a.videos)
        for item in out:
            item["video_exists"] = (vd / f"{item['name']}.mp4").exists()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out else 1


# ---------------------------------------------------------------- 連接埠

def port_busy(port: int) -> bool:
    """同時試 IPv4 與 IPv6 —— Kestrel 綁 localhost 時可能只聽其中一個。"""
    for fam, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        s = socket.socket(fam, socket.SOCK_STREAM)
        s.settimeout(0.3)
        try:
            if s.connect_ex((host, port)) == 0:
                return True
        except OSError:
            pass
        finally:
            s.close()
    return False


def free_port(start: int) -> int:
    for p in range(start, start + 200):
        if not port_busy(p):
            return p
    raise RuntimeError(f"{start} 起 200 個連接埠都被佔用")


# ---------------------------------------------------------------- 啟動

def _launch_env(cwd: Path) -> dict:
    """沿用 launchSettings.json 的環境變數（主要是 ASPNETCORE_ENVIRONMENT）。

    我們用 --no-launch-profile 啟動（不然會套用它寫死的埠與 launchBrowser），
    代價是那些環境變數也不會套用，所以這裡自己補回來。
    """
    ls = cwd / "Properties" / "launchSettings.json"
    env = {"ASPNETCORE_ENVIRONMENT": "Development"}
    if ls.exists():
        try:
            prof = json.loads(ls.read_text(encoding="utf-8-sig")).get("profiles", {})
            pick = prof.get("http") or next(
                (v for v in prof.values() if v.get("commandName") == "Project"), {})
            env.update(pick.get("environmentVariables", {}))
        except (json.JSONDecodeError, StopIteration):
            pass
    return env


def build_command(info: dict, port: int, override: str | None) -> tuple[list[str] | str, dict]:
    cwd = Path(info["cwd"])
    env: dict = {}
    if override:
        return override.replace("{port}", str(port)), env

    if info["type"] == "dotnet":
        env.update(_launch_env(cwd))
        env["ASPNETCORE_URLS"] = f"http://localhost:{port}"
        return (["dotnet", "run", "--project", info["entry"], "--no-launch-profile",
                 "--urls", f"http://localhost:{port}"], env)

    if info["type"] == "python":
        py = cwd / ".venv" / "Scripts" / "python.exe"
        if not py.exists():
            py = Path(info["cwd"]).parent / ".venv" / "Scripts" / "python.exe"
        exe = str(py) if py.exists() else sys.executable
        env.update({"PORT": str(port), "FLASK_RUN_PORT": str(port),
                    "FLASK_ENV": "development", "PYTHONUTF8": "1"})
        entry = Path(info["entry"])
        src = entry.read_text(encoding="utf-8", errors="ignore")
        if "FastAPI" in src:
            return ([exe, "-m", "uvicorn", f"{entry.stem}:app", "--port", str(port)], env)
        if entry.name == "run.py":
            return ([exe, entry.name], env)       # run.py 通常自己讀 PORT；讀不到就用 --cmd
        return ([exe, "-m", "flask", "--app", entry.stem, "run", "--port", str(port)], env)

    # node
    pkg = json.loads(Path(info["entry"]).read_text(encoding="utf-8"))
    env["PORT"] = str(port)
    script = "dev" if "dev" in pkg.get("scripts", {}) else "start"
    return (["npm", "run", script, "--", "--port", str(port)], env)


def http_get(url: str, timeout: float = 5) -> tuple[int, str, str]:
    """回傳 (status, final_url, body)。4xx/5xx 也算有回應（代表網站活著）。"""
    req = urllib.request.Request(url, headers={"User-Agent": "operation-creator"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.geturl(), r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, url, e.read().decode("utf-8", "ignore")


def _tail(path: Path, n: int = 25) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="ignore").splitlines()[-n:])
    except OSError:
        return ""


def cmd_start(a) -> int:
    project = Path(a.project).resolve()
    info = detect(project)
    if not info and not a.cmd:
        print(f"錯誤：{project} 找不到可執行的網站專案（用 --cmd 自行指定）", file=sys.stderr)
        return 1
    info = info or {"type": "custom", "entry": "", "cwd": str(project)}

    port = a.port or free_port(PORT_FROM)
    if port_busy(port):
        print(f"錯誤：連接埠 {port} 已被佔用。不要去停別人的行程，換一個埠。", file=sys.stderr)
        return 1

    cmd, extra_env = build_command(info, port, a.cmd)
    for kv in a.env or []:
        k, _, v = kv.partition("=")
        extra_env[k] = v
    env = {**os.environ, **extra_env}

    state = Path(a.state).resolve()
    state.parent.mkdir(parents=True, exist_ok=True)
    log = state.with_suffix(".log")
    logf = open(log, "w", encoding="utf-8", errors="ignore")

    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    proc = subprocess.Popen(cmd, cwd=info["cwd"], env=env, stdout=logf,
                            stderr=subprocess.STDOUT, creationflags=flags,
                            shell=isinstance(cmd, str))

    base = f"http://localhost:{port}"
    probe = base + (a.probe or "/")
    print(f"  啟動 {info['type']}  pid={proc.pid}  {base}")
    print(f"  日誌 {log}")

    ready, status, body, final = False, 0, "", probe
    t0 = time.time()
    while time.time() - t0 < READY_TIMEOUT:
        if proc.poll() is not None:
            print(f"錯誤：行程已結束（代碼 {proc.returncode}）\n{_tail(log)}", file=sys.stderr)
            return 1
        try:
            status, final, body = http_get(probe)
            if status < 500:
                ready = True
                break
        except (urllib.error.URLError, OSError, TimeoutError):
            pass
        time.sleep(1.5)

    if not ready:
        print(f"錯誤：{READY_TIMEOUT} 秒內 {probe} 沒有回應\n{_tail(log)}", file=sys.stderr)
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        return 1

    # ---- 身分斷言：回應一定要來自「這個」專案
    _, home_final, home = http_get(base + (a.page or "/"))
    # Razor 會把 @ 輸出的中文編成 &#x9996;&#x9801;，不還原的話 marker 會誤判失敗
    home = html.unescape(home)
    title = (re.search(r"<title>(.*?)</title>", home, re.S | re.I) or [None, ""])[1].strip()
    problems = []
    for m in a.marker or []:
        if m not in home:
            problems.append(f"找不到應出現的字串「{m}」")
    for m in a.absent or []:
        if m in home:
            problems.append(f"出現了不應出現的字串「{m}」（可能連到別的站）")
    if "address already in use" in _tail(log, 200).lower():
        problems.append("日誌出現 address already in use")

    st = {"project": str(project), "type": info["type"], "url": base, "port": port,
          "pid": proc.pid, "log": str(log), "cmd": cmd if isinstance(cmd, str) else " ".join(cmd),
          "title": title, "home_url": home_final, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    state.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"  就緒 {time.time() - t0:.0f}s  HTTP {status}  <title>{title}</title>")
    if problems:
        print("錯誤：頁面身分斷言失敗\n  " + "\n  ".join(problems), file=sys.stderr)
        print("  已保留行程以便檢查；確認後執行 stop。", file=sys.stderr)
        return 3
    if not a.marker:
        print("  ! 沒有給 --marker：請自行確認上面的 <title> 真的是這個專案", file=sys.stderr)
    print(f"  狀態檔 {state}")
    return 0


def cmd_stop(a) -> int:
    state = Path(a.state)
    if not state.exists():
        print("沒有狀態檔，沒有要停的行程")
        return 0
    st = json.loads(state.read_text(encoding="utf-8"))
    # /T 連同子行程（dotnet run 會再開一個 RagDemo.exe）一起停；只停自己開的 pid
    r = subprocess.run(["taskkill", "/PID", str(st["pid"]), "/T", "/F"],
                       capture_output=True, text=True, encoding="cp950", errors="ignore")
    time.sleep(1)
    still = port_busy(st["port"])
    print(f"  停止 pid={st['pid']}  埠 {st['port']} {'仍在監聽 !' if still else '已釋放'}")
    if still:
        print(f"  ! {r.stdout.strip()} {r.stderr.strip()}", file=sys.stderr)
    return 1 if still else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd_name", required=True)

    p = sub.add_parser("list")
    p.add_argument("--root", required=True)
    p.add_argument("--videos", help="教學影片資料夾，用來標記同名影片是否已存在")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("start")
    p.add_argument("--project", required=True)
    p.add_argument("--state", required=True, help="狀態檔路徑（放 scratchpad）")
    p.add_argument("--port", type=int)
    p.add_argument("--probe", help="就緒探針路徑，預設 /")
    p.add_argument("--page", help="身分斷言要抓的頁面，預設 /")
    p.add_argument("--marker", action="append", help="頁面必須出現的字串，可重複")
    p.add_argument("--absent", action="append", help="頁面不可出現的字串，可重複")
    p.add_argument("--env", action="append", help="額外環境變數 KEY=VALUE，可重複")
    p.add_argument("--cmd", help="自訂啟動命令，{port} 會被替換")
    p.set_defaults(fn=cmd_start)

    p = sub.add_parser("stop")
    p.add_argument("--state", required=True)
    p.set_defaults(fn=cmd_stop)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
