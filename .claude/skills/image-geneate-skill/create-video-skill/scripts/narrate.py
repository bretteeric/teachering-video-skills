#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""旁白合成與時間軸產生 —— 整條管線的事實來源。

由 storyboard.json 的 narration 文字產生：
  narration.wav  48kHz 單聲道，已去爆音、已響度正規化
  timeline.json  每個場景 / 每句的精確起訖時間
  subtitle.ass   180px 紅棕色黑體繁中字幕（燒錄用）
  subtitle.srt   同內容的 SRT（外部使用）

字幕文字一律是旁白原字串的 substring，不經任何轉錄，保證完全正確。

用法:
  python narrate.py --storyboard storyboard.json --outdir audio/
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

import edge_tts

# ---------------------------------------------------------------- 參數

VOICE_DEFAULT = {"name": "zh-TW-YunJheNeural", "rate": "-10%",
                 "pitch": "-4Hz", "volume": "+0%"}

SUB_COLOR_RGB = "B04A32"   # 紅棕色
FONT_NAME     = "Microsoft JhengHei"
FONT_SIZE     = 180
MAX_CHARS     = 18         # 180px 下單行上限（實測 18 字 = 3240px）
MIN_CUE_SEC   = 1.2        # 單一 cue 最短顯示時間
CUE_GAP       = 0.05       # cue 之間的間隙
GAP_SENTENCE  = 0.30       # 句間停頓
GAP_SCENE     = 0.60       # 場景間停頓
LEAD_SILENCE  = 0.30       # 片頭靜音（避免首爆音）
TAIL_SILENCE  = 0.60       # 片尾靜音（避免尾爆音）
TAIL_KEEP     = 0.12       # 每段語音結束後保留的自然尾音

FADE_IN, FADE_OUT = 0.04, 0.06

# ---------------------------------------------------------------- 工具


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"命令失敗: {' '.join(cmd[:3])}...\n{r.stderr[-800:]}")


def probe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def rgb_to_ass(hex_rgb: str, alpha: str = "00") -> str:
    """#B04A32 -> &H00324AB0   ASS 是 AABBGGRR（BGR 反序）"""
    h = hex_rgb.lstrip("#")
    return f"&H{alpha}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def ts_ass(t: float) -> str:
    h, r = divmod(max(t, 0), 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def ts_srt(t: float) -> str:
    h, r = divmod(max(t, 0), 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s % 1) * 1000)):03d}"


def write_utf8(path: Path, text: str) -> None:
    """一律 UTF-8 無 BOM —— 帶 BOM 會讓 libass 第一句解析異常。"""
    path.write_text(text, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- TTS


async def synth(text: str, voice: dict, out_mp3: Path) -> list[tuple[float, float, str]]:
    """合成單句，回傳 WordBoundary 事件 [(start, dur, word), ...]。

    boundary 預設是 SentenceBoundary，必須明確指定 WordBoundary
    才拿得到詞組層級時間（否則事件數為 0）。
    """
    c = edge_tts.Communicate(
        text, voice["name"], rate=voice["rate"], pitch=voice["pitch"],
        volume=voice.get("volume", "+0%"), boundary="WordBoundary")

    events: list[tuple[float, float, str]] = []
    with open(out_mp3, "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                events.append((ch["offset"] / 1e7, ch["duration"] / 1e7, ch["text"]))
    return events


def clean_segment(mp3: Path, wav: Path, tail_pad: float,
                  speech_end: float | None = None) -> None:
    """去爆音：高通除 DC → 裁掉尾端多餘靜音 → 淡入淡出 → 補上設計的停頓。

    edge-tts 每段結尾固定附帶約 0.95 秒靜音（實測與句長無關）。不裁掉的話，
    句間會變成 0.95 + 0.3 = 1.25 秒的死氣，整支影片拖沓。
    裁切一定要在淡出「之前」，否則會從波形中間切斷而產生爆音。

    areverse,afade=t=in,areverse 是不需預先知道長度的淡出技巧。
    """
    chain = ["highpass=f=60"]
    if speech_end:
        chain.append(f"atrim=0:{speech_end:.3f}")
        chain.append("asetpts=N/SR/TB")
    chain += [f"afade=t=in:st=0:d={FADE_IN}",
              "areverse", f"afade=t=in:st=0:d={FADE_OUT}", "areverse",
              f"apad=pad_dur={tail_pad}"]
    run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-af", ",".join(chain),
         "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)])


# ---------------------------------------------------------------- 字幕切分

_PUNCT_STRONG = "。！？"
_PUNCT_MID    = "；："
_PUNCT_WEAK   = "，、"
_PUNCT_ALL    = _PUNCT_STRONG + _PUNCT_MID + _PUNCT_WEAK
_PUNCT_RE     = re.compile(r"[，。、；：？！,.!?\s]")


def _strip_punct(s: str) -> str:
    """WordBoundary 的 text 不含標點與空白，比對字數時必須用同一把尺。"""
    return _PUNCT_RE.sub("", s)


def _split_keep(text: str, puncts: str) -> list[str]:
    """在指定標點後切開，標點保留在前段。"""
    out, buf = [], ""
    for ch in text:
        buf += ch
        if ch in puncts:
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out


def _atoms(text: str, words: list[str]) -> list[str]:
    """把原文拆成「一個 TTS 詞 + 緊跟其後的標點」的最小單位。

    有了詞的邊界，斷句就不會切在詞中間（例如把「使用者註冊的功能」
    硬切成「…使用者註冊的」與「功能。」這種讀起來很怪的碎片）。
    """
    out, i, wi = [], 0, 0
    while i < len(text):
        if wi < len(words) and words[wi] and text.startswith(words[wi], i):
            a = words[wi]
            i += len(a)
            wi += 1
        else:
            a = text[i]
            i += 1
        while i < len(text) and _PUNCT_RE.match(text[i]):   # 吸收後續標點與空白
            a += text[i]
            i += 1
        out.append(a)
    return out


def split_line(text: str, words: list[str] | None = None) -> list[str]:
    """把一句旁白切成 <=MAX_CHARS 的單行 cue。

    只在詞或標點邊界切、不改寫文字 —— 確保 cue 是原文 substring。
    """
    text = text.strip()
    if len(text) <= MAX_CHARS:
        return [text]

    if words:
        # 以詞為單位裝箱：句末標點一定斷，逗頓號夠長也斷（語意斷點優先於塞滿整行）
        groups: list[list[str]] = []
        cur: list[str] = []
        for a in _atoms(text, words):
            if cur and len("".join(cur)) + len(a) > MAX_CHARS:
                groups.append(cur)
                cur = [a]
            else:
                cur.append(a)
            joined = "".join(cur)
            if joined and (joined[-1] in _PUNCT_STRONG or (
                    joined[-1] in _PUNCT_MID + _PUNCT_WEAK
                    and len(joined) >= MAX_CHARS // 2)):
                groups.append(cur)
                cur = []
        if cur:
            groups.append(cur)

        # 結尾若剩一小截（例如「了。」），從前一組挪詞過來，而不是硬留著
        while (len(groups) >= 2 and len("".join(groups[-1])) < 4
               and len(groups[-2]) > 1
               and len("".join(groups[-2][-1:] + groups[-1])) <= MAX_CHARS):
            groups[-1].insert(0, groups[-2].pop())

        out = [g.strip() for g in ("".join(x) for x in groups) if g.strip()]
    else:
        # 沒有詞資訊時的後備：依標點強弱逐級嘗試
        parts = _split_keep(text, _PUNCT_ALL)
        for puncts in (_PUNCT_STRONG, _PUNCT_STRONG + _PUNCT_MID, _PUNCT_ALL):
            cand = _split_keep(text, puncts)
            if len(cand) > 1 and max(len(p) for p in cand) <= MAX_CHARS:
                parts = cand
                break
        merged: list[str] = []
        for p in parts:
            if merged and len(merged[-1]) + len(p) <= MAX_CHARS:
                merged[-1] += p
            else:
                merged.append(p)
        out = []
        for p in merged:
            while len(p) > MAX_CHARS:
                out.append(p[:MAX_CHARS])
                p = p[MAX_CHARS:]
            if p:
                out.append(p)
        out = [s.strip() for s in out if s.strip()]

    # 收尾碎片併回前一段（若併得下）
    #
    # **不可寫成 `out[-2] += out.pop()`。** 擴增指派會先取出 out[-2] 的值，
    # 接著才算右邊的 out.pop()——而 pop() 已經把串列縮短一格，最後寫回時
    # 的 -2 指到的**已經是另一個元素**。三段以上的句子會因此被寫壞：
    # 實測 ['回 201，嚴重性這次是', 'recovery，', '恢復。'] 會變成
    # ['recovery，恢復。', 'recovery，']——前段整段消失、後段重複一次。
    # 幸好本檔最後的逐字比對會擋下來（結束碼 2），否則字幕會安靜地出錯。
    if len(out) >= 2 and len(out[-1]) < 4 and len(out[-2]) + len(out[-1]) <= MAX_CHARS:
        tail = out.pop()
        out[-1] += tail
    return out


def cue_times(cues: list[str], events, seg_start: float,
              seg_dur: float) -> list[tuple[float, float, str]]:
    """用 WordBoundary 把 cue 對到實際時間；沒有事件時退回等比分配。

    直接使用 WordBoundary 的原始 offset，不做任何縮放 —— 音訊處理
    （highpass / afade / atrim / apad）都不會平移語音的時間位置。
    若拿「音檔長度 / 最後一個詞結束時間」當比例去縮放，會被 edge-tts
    尾端那段固定靜音灌水成 1.12~1.21 倍，讓每句最後一個 cue 晚上將近一秒。
    """
    if not events:
        # 後備：依字數等比分配
        total = sum(len(c) for c in cues) or 1
        result, acc = [], 0.0
        for c in cues:
            d = seg_dur * len(c) / total
            result.append((seg_start + acc, seg_start + acc + d, c))
            acc += d
        return result

    # marks: (累積「非標點」字數, 該詞起, 該詞迄)
    marks, pos = [], 0
    for start, dur, word in events:
        pos += len(word)
        marks.append((pos, start, start + dur))

    def start_at(p: int) -> float:
        """第一個「起點在 p 之後」的詞 —— 用嚴格大於，才不會抓到已消費完的詞。"""
        for mp, s, _ in marks:
            if mp > p:
                return s
        return marks[-1][1]

    def end_at(p: int) -> float:
        for mp, _, e in marks:
            if mp >= p:
                return e
        return marks[-1][2]

    result, cursor = [], 0
    for c in cues:
        s = start_at(cursor)
        cursor += len(_strip_punct(c))   # 與 marks 同樣不計標點，否則逐句累積偏移
        result.append((seg_start + s, seg_start + end_at(cursor), c))
    return result


def enforce_min(cues: list[tuple[float, float, str]], hard_end: float):
    """套用最短顯示時間與 cue 間隙，並確保絕不重疊。

    WordBoundary 對到的 cue 結尾是「該詞的結束」，而下一個 cue 的開始是
    「同一個詞的開始」，兩者天生會重疊一個詞的長度。這裡無條件把結尾夾到
    下一個 cue 的開頭 —— 沒有這一步，畫面上會同時出現兩行字幕。
    """
    out = []
    for i, (s, e, t) in enumerate(cues):
        nxt = cues[i + 1][0] if i + 1 < len(cues) else hard_end
        e = min(e, nxt)                       # 先去重疊
        if e - s < MIN_CUE_SEC:               # 再補最短顯示時間（仍不得越界）
            e = min(s + MIN_CUE_SEC, nxt)
        e -= CUE_GAP
        if e <= s:
            e = s + 0.25
        out.append((s, e, t))
    return out


# ---------------------------------------------------------------- 輸出


def build_ass(cues) -> str:
    color = rgb_to_ass(SUB_COLOR_RGB)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 3840
PlayResY: 2160
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TW,{FONT_NAME},{FONT_SIZE},{color},{color},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,4,2,160,160,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    body = "".join(
        f"Dialogue: 0,{ts_ass(s)},{ts_ass(e)},TW,,0,0,0,,{t}\n" for s, e, t in cues)
    return head + body


def build_srt(cues) -> str:
    return "".join(
        f"{i}\n{ts_srt(s)} --> {ts_srt(e)}\n{t}\n\n"
        for i, (s, e, t) in enumerate(cues, 1))


# ---------------------------------------------------------------- 主流程


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--storyboard", required=True)
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()

    sb = json.loads(Path(a.storyboard).read_text(encoding="utf-8"))
    voice = {**VOICE_DEFAULT, **sb.get("voice", {})}
    outdir = Path(a.outdir)
    segdir = outdir / "segments"
    segdir.mkdir(parents=True, exist_ok=True)

    cursor = LEAD_SILENCE          # 全域時間游標（片頭靜音之後）
    wav_list: list[Path] = []
    all_cues: list[tuple[float, float, str]] = []
    scene_times: list[dict] = []
    narration_lines: list[str] = []

    for si, scene in enumerate(sb["scenes"]):
        lines = [l.strip() for l in scene.get("narration", []) if l.strip()]
        if not lines:
            print(f"  ! 場景 {scene.get('id')} 沒有旁白，略過", file=sys.stderr)
            continue
        scene_start = cursor

        for li, line in enumerate(lines):
            narration_lines.append(line)
            is_last = (li == len(lines) - 1)
            pad = GAP_SCENE if is_last else GAP_SENTENCE

            mp3 = segdir / f"s{si:02d}_{li:02d}.mp3"
            wav = segdir / f"s{si:02d}_{li:02d}.wav"

            events = await synth(line, voice, mp3)
            # 裁到最後一個詞結束後留一點自然尾音，其餘 edge-tts 的固定靜音丟掉
            speech_end = (max(e[0] + e[1] for e in events) + TAIL_KEEP) if events else None
            clean_segment(mp3, wav, pad, speech_end)
            dur = probe_duration(wav)
            speech = max(dur - pad, 0.1)      # 扣掉停頓才是語音長度

            cues = split_line(line, [e[2] for e in events])
            all_cues.extend(cue_times(cues, events, cursor, speech))

            wav_list.append(wav)
            cursor += dur
            print(f"  {scene.get('id')} [{li+1}/{len(lines)}] {dur:5.2f}s  "
                  f"{len(cues)} cue  {line[:24]}")

        scene_times.append({"id": scene.get("id", f"s{si:02d}"),
                            "start": round(scene_start, 3),
                            "end": round(cursor, 3),
                            "duration": round(cursor - scene_start, 3)})

    if not wav_list:
        print("錯誤：storyboard 中沒有任何旁白", file=sys.stderr)
        return 1

    # 片頭靜音
    lead = segdir / "_lead.wav"
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t", str(LEAD_SILENCE),
         "-i", "anullsrc=r=48000:cl=mono", "-c:a", "pcm_s16le", str(lead)])

    # concat 清單（用 POSIX 路徑，ffmpeg concat 對反斜線敏感）
    listfile = outdir / "concat.txt"
    write_utf8(listfile, "".join(
        f"file '{p.resolve().as_posix()}'\n" for p in [lead] + wav_list))

    final = outdir / "narration.wav"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(listfile),
         "-af", f"apad=pad_dur={TAIL_SILENCE},loudnorm=I=-16:TP=-1.5:LRA=11",
         "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(final)])

    total = probe_duration(final)
    all_cues = enforce_min(all_cues, total)

    write_utf8(outdir / "subtitle.ass", build_ass(all_cues))
    write_utf8(outdir / "subtitle.srt", build_srt(all_cues))
    write_utf8(outdir / "narration.txt", "\n".join(narration_lines) + "\n")
    write_utf8(outdir / "timeline.json", json.dumps(
        {"total": round(total, 3), "lead": LEAD_SILENCE,
         "scenes": scene_times}, ensure_ascii=False, indent=2))

    # 自我驗證：字幕文字必須與旁白逐字一致
    norm = lambda s: re.sub(r"[，。、；：？！\s]", "", s)
    if norm("".join(t for _, _, t in all_cues)) != norm("".join(narration_lines)):
        print("錯誤：字幕與旁白不一致，切分邏輯有問題", file=sys.stderr)
        return 2

    print(f"\n完成 總長 {total:.2f}s / {len(all_cues)} 個字幕 cue")
    print(f"  {final}\n  {outdir/'subtitle.ass'}\n  {outdir/'timeline.json'}")
    print("  字幕與旁白逐字一致 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
