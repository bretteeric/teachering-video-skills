# 語音合成與音訊處理

## 一、語音選擇（已定案，不要改）

```python
VOICE  = "zh-TW-YunJheNeural"   # 台灣男聲，edge-tts 中唯一
RATE   = "-10%"                 # 平順緩和
PITCH  = "-4Hz"                 # 沉穩
VOLUME = "+0%"                  # 音量交給 loudnorm，這裡不動
```

實測 `edge-tts --list-voices | grep zh-TW` 只有三個：

| Voice | 性別 | 適用 |
|---|---|---|
| `zh-TW-YunJheNeural` | **Male** | ✅ 本專案使用 |
| `zh-TW-HsiaoChenNeural` | Female | ✗ |
| `zh-TW-HsiaoYuNeural` | Female | ✗ |

**不要退回 `zh-CN-Yunyang` 等大陸語音** —— 腔調、用詞、兒化音都不對。

### 參數調整範圍

| 參數 | 建議 | 說明 |
|---|---|---|
| `rate` | `-8%` ~ `-12%` | 低於 `-15%` 會拖沓，聽起來像放慢的錄音 |
| `pitch` | `-2Hz` ~ `-6Hz` | 低於 `-8Hz` 會出現明顯的電子音失真 |

---

## 二、SSML 不可用（重要）

**edge-tts 7.x 不支援 SSML。** 原始碼中：

```python
self.texts = split_text_by_byte_length(
    escape(remove_incompatible_characters(text)), 4096)
```

輸入經 `escape()` 處理，`<break time="500ms"/>` 會變成 `&lt;break...&gt;` 被**逐字唸出來**。

所以：

| 想要的效果 | 正確作法 |
|---|---|
| 停頓 | 用標點（`，` 短停、`。` 長停）；跨句停頓靠合成時插入靜音 |
| 強調 | 改寫句子把重點放句首或獨立成句 |
| 語速變化 | 分段用不同 `rate` 合成，再串接 |

---

## 三、去爆音處理鏈（實測驗證）

爆音來自三個地方，各有對應處理：

| 成因 | 處理 |
|---|---|
| 段落起訖振幅非零 → 接點喀噠聲 | 每段 `afade` 淡入 40ms／淡出 60ms |
| MP3 解碼的 DC offset 與超低頻 | `highpass=f=60` |
| 取樣率不一致串接 | 全部先解碼成 **48kHz 單聲道 PCM WAV** |

### 尾端靜音必須裁掉

edge-tts 每段結尾固定附帶約 **0.95 秒靜音**——實測與句長無關：

```
[0] 24 字  speech=5.496  最後一詞結束=4.531  差 +0.965
[1] 40 字  speech=7.440  最後一詞結束=6.475  差 +0.965
[2] 35 字  speech=8.784  最後一詞結束=7.856  差 +0.928
```

不裁掉的話，句間會變成 `0.95 + 0.3 = 1.25 秒`的死氣，整支影片拖沓
（實測某三場景影片因此多出約 4 秒空白）。

裁切點取「最後一個 `WordBoundary` 結束 + 0.12 秒自然尾音」，
且**一定要在淡出之前裁**，否則會從波形中間切斷而產生爆音。

### 單段處理

```powershell
ffmpeg -y -i seg.mp3 `
  -af "highpass=f=60,atrim=0:<最後一詞結束+0.12>,asetpts=N/SR/TB,afade=t=in:st=0:d=0.04,areverse,afade=t=in:st=0:d=0.06,areverse,apad=pad_dur=0.3" `
  -ar 48000 -ac 1 -c:a pcm_s16le seg.wav
```

濾鏡順序固定為：**高通 → 裁切 → 淡入淡出 → 補停頓**。

`areverse,afade=t=in,areverse` 是**不需要事先知道長度**就能淡出的技巧——比 `afade=t=out:st=<dur-0.06>` 穩，不必先 ffprobe。段落是單句，記憶體開銷可忽略。

`apad=pad_dur=0.3` 是句間換氣（段落之間用 0.6）。裁掉原生靜音後，這個值才真正等於實際停頓。

### 串接與收尾

```powershell
# 首端 300ms 靜音（避免影片一開始就出聲＝首爆音）
ffmpeg -y -f lavfi -t 0.3 -i anullsrc=r=48000:cl=mono -c:a pcm_s16le lead.wav

# concat（清單第一項為 lead.wav）
ffmpeg -y -f concat -safe 0 -i list.txt `
  -af "apad=pad_dur=0.6,loudnorm=I=-16:TP=-1.5:LRA=11" `
  -ar 48000 -c:a pcm_s16le narration.wav
```

**順序不可調換**：`highpass` 一定在 `loudnorm` **之前**。反過來的話 loudnorm 會把超低頻一起提升，highpass 再切掉，實際響度就不到目標值。

### 實測結果

```
duration 9.20s  sr=48000
first 5 samples: (0,0,0,0,0) | last 5: (0,0,0,0,0)   ← 首尾為零，無爆音
peak 27571 (-1.5 dBFS)                                ← 符合 TP=-1.5
```

---

## 四、時間軸取得

**不要估算長度，一律實測。**

```python
def wav_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())
```

### 句內精細時間（給字幕斷句用）

`edge_tts.Communicate` 的 `boundary` 參數**預設是 `SentenceBoundary`**，所以直接讀 `WordBoundary` 事件會拿到 0 筆。必須明確指定：

```python
c = edge_tts.Communicate(text, VOICE, rate=RATE, pitch=PITCH,
                         boundary="WordBoundary")     # ← 關鍵
async for ch in c.stream():
    if ch["type"] == "WordBoundary":
        # offset / duration 單位是 100 奈秒
        start = ch["offset"] / 1e7
        dur   = ch["duration"] / 1e7
        word  = ch["text"]
```

實測輸出（詞組層級，正是斷句需要的粒度）：

```
0.100 +0.333  我們
0.433 +0.167  先
0.600 +0.125  來
0.892 +0.375  一下
1.517 +0.403  功能的
2.225 +0.819  方式
```

注意：offset 從 **0.100s** 起算（非 0），且是**未經後處理**的原始時間。套用到最終時間軸時要以該段 WAV 的實測長度等比對齊，見 `subtitle-ass.md`。

---

## 五、輸出規格

| 項目 | 值 |
|---|---|
| 中間檔 | 48kHz / 單聲道 / PCM s16le WAV |
| 最終編碼 | AAC-LC 192kbps / 48kHz |
| 整合響度 | -16 LUFS（`I=-16`） |
| 真實峰值 | -1.5 dBTP（`TP=-1.5`） |
| 響度範圍 | `LRA=11` |

-16 LUFS 是線上影片的通用標準，音量適中且保留動態。
