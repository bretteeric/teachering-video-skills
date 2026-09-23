# ASS 字幕規範

要求：**繁體中文、180 像素、紅棕色、黑體**。

字幕以 **ASS（Advanced SubStation Alpha）** 為主格式並燒錄進畫面（字體大小與顏色才能精確控制），同時附一份 `.srt` 供外部使用。

---

## 一、樣式規格（實測驗證）

```ass
[Script Info]
ScriptType: v4.00+
PlayResX: 3840
PlayResY: 2160
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TW,Microsoft JhengHei,180,&H00324AB0,&H00324AB0,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,4,2,160,160,120,1
```

| 欄位 | 值 | 理由 |
|---|---|---|
| `PlayResX/Y` | **3840 / 2160** | 必須等於輸出解析度，`Fontsize` 才等於實際像素 |
| `Fontname` | `Microsoft JhengHei` | 繁中黑體，Windows 內建（`msjhbd.ttc`） |
| `Fontsize` | **180** | 需求指定 |
| `PrimaryColour` | `&H00324AB0` | **紅棕色 #B04A32**（見下節 BGR 轉換） |
| `Bold` | **-1** | ASS 的 true 是 `-1`，不是 `1` |
| `Outline` | 6 | 黑色描邊，深淺背景都能讀 |
| `Shadow` | 4 | 陰影再加一層分離度 |
| `Alignment` | 2 | 底部置中 |
| `MarginL/R` | 160 | 左右安全邊界 |
| `MarginV` | 120 | 底部距離 |
| `Encoding` | 1 | Default；CJK 靠字型本身，不要設 136 |

### 字型可用性

實測 `Microsoft JhengHei` **不需要 `fontsdir` 參數**即可被 libass 解析（本機 `fc-list` 無輸出，但 libass 走 Windows 原生字型列舉）。備選 `Noto Sans TC`（`NotoSansTC-VF.ttf`，同樣內建）。

若換到沒有微軟正黑體的機器，改用：
```
-vf "ass=subtitle.ass:fontsdir=fonts"
```
並把 `msjhbd.ttc` 放進 `fonts/`。注意在 **PowerShell 中此參數的冒號需跳脫**，直接寫 `C:/Windows/Fonts` 會解析失敗（實測錯誤：`No option name near '/Windows/Fonts'`）；用相對路徑 `fontsdir=fonts` 最省事。

---

## 二、顏色：BGR 反序陷阱

**ASS 顏色格式是 `&HAABBGGRR`** —— Alpha、Blue、Green、Red，**RGB 是反過來的**。

```
#B04A32  →  R=B0 G=4A B=32  →  &H00 32 4A B0  →  &H00324AB0
              ↑                      ↑  ↑  ↑
            RGB 順序              AA  BB GG RR
```

寫成 `&H00B04A32` 會得到**藍綠色**——這是最常見的錯誤。

轉換函式：

```python
def rgb_to_ass(hex_rgb: str, alpha: str = "00") -> str:
    """#B04A32 -> &H00324AB0  (ASS 為 AABBGGRR)"""
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha}{b}{g}{r}".upper()
```

### 紅棕色可選色板（皆已實際算圖比對）

| 色碼 | ASS | 特性 |
|---|---|---|
| **`#B04A32`** | `&H00324AB0` | ✅ **預設**。紅棕明確，深淺背景皆清楚 |
| `#9C4A32` | `&H00324A9C` | 最典型的紅棕色，稍暗 |
| `#8B3A2E` | `&H002E3A8B` | 最深；深色背景上對比偏低，慎用 |
| `#A0522D` | `&H002D52A0` | 偏橘（赭色），紅感較弱 |

要換色只改 `Style:` 那一行的 `PrimaryColour`（與 `SecondaryColour`）即可。

---

## 三、斷句規則

### 每行最多 18 個全形字（實測）

`Microsoft JhengHei` Bold 在 180px 下，全形字進距**正好 180px**：

```
12 字 → 2160px  OK
16 字 → 2880px  OK
18 字 → 3240px  OK   ← 上限（可用寬度 3840 - 160×2 = 3520px）
20 字 → 3600px  OVERFLOW
```

### 一律單行

180px 兩行會佔掉畫面高度約 17%，蓋住操作區。**cue 必須是單行**，長句要切成多個 cue。

### 切分演算法

以 **`WordBoundary` 的詞** 為最小單位，絕不切在詞中間：

```
1. 把原文拆成「一個 TTS 詞 + 緊跟其後的標點」的原子單位
2. 逐個裝箱，超過 18 字就換一個 cue
3. 遇 。！？ 一定斷句
4. 遇 ，、；： 且目前已累積 >= 9 字也斷 —— 語意斷點優先於塞滿整行
5. 結尾若剩 < 4 字的碎片，從前一個 cue 挪一個詞過來（不是硬留著）
```

第 4 步很關鍵。少了它會變成「我會從整個流程的架構開始，帶你一路 / 做到實際的操作。」
這種塞滿但讀起來很怪的斷法；加上以後是「我會從整個流程的架構開始， / 帶你一路做到實際的操作。」

第 1 步也很關鍵。純粹按字數硬切會產生「…是使用者註冊的 / 功能。」這種把詞切開的碎片。

**cue 文字必須是旁白原字串的 substring**，只允許移除切點上的標點，**不得改寫、不得補字**。這是「字幕完全正確」的保證來源。合成後務必用程式比對（見 `qa-checklist.md`）。

### 時間分配

**直接用 `WordBoundary` 的原始 offset，不要做任何縮放。**

```python
cue_start = seg_global_offset + raw_word_start
cue_end   = seg_global_offset + raw_word_end
```

> ⚠️ **不要**用 `scale = 音檔長度 / 最後一個詞結束時間` 去等比映射。
> edge-tts 每段結尾固定附帶約 **0.95 秒靜音**（實測與句長無關），
> 這會把 scale 灌水成 **1.12～1.21**，讓每句最後一個 cue 晚將近一秒出現。
> 音訊處理（highpass / afade / atrim / apad）都不會平移語音位置，原始 offset 就是對的。

### 字數對位陷阱

`WordBoundary` 事件的 `text` **不含標點與空白**（實測 `方式` 而非 `方式，`）。
用 cue 的字數去查表時，必須用同一把尺：

```python
cursor += len(re.sub(r"[，。、；：？！\s]", "", cue))   # 不能用 len(cue)
```

否則每經過一個標點就累積一格偏移，長句的後段 cue 會整個對到下一個詞。

查表的邊界條件也要分開處理：

- **起點**：第一個累積字數 **> cursor** 的詞（嚴格大於，才不會抓到已消費完的詞）
- **終點**：第一個累積字數 **>= cursor** 的詞

### 再套用三條規則

- **最短顯示 1.2 秒**。太短會閃現，讀不完。
- **cue 之間留 0.05 秒**間隙，避免 libass 在交界處同時渲染兩行。
- **結尾一律夾到下一個 cue 的開頭**。WordBoundary 對出來的 cue 結尾是「該詞的結束」，
  而下一個 cue 的開頭是「同一個詞的開始」，天生會重疊一個詞的長度。
  沒有這一步，畫面上會同時出現兩行字幕。

> 正常結果是字幕比語音**早 0.15～0.25 秒**出現（實測 0.17～0.20 秒）。
> 這是正確的，觀眾需要一點提前量才讀得順；不要試圖「校正」掉。

---

## 四、SRT 附檔

同一份 cue 資料另存 `.srt`（**UTF-8 無 BOM**）：

```srt
1
00:00:00,300 --> 00:00:02,150
哈囉，這一支影片我們要來看的

2
00:00:02,200 --> 00:00:04,050
是使用者註冊的功能。
```

SRT 不帶樣式，僅供外部播放器／上傳平台使用。**畫面上的字幕以 ASS 燒錄為準。**

---

## 五、燒錄

```powershell
ffmpeg ... -vf "ass=subtitle.ass" ...
```

- 用 **`ass`** 濾鏡，不要用 `subtitles` 濾鏡：後者會重新套用 `PlayRes` 縮放，180px 會跑掉。
- 燒錄必須在**縮放到 3840×2160 之後**進行。若先燒字幕再縮放，字級會跟著被縮放。

---

## 六、常見錯誤

| 症狀 | 原因 |
|---|---|
| 字幕變藍綠色 | 顏色寫成 RGB，未轉 BGR |
| 字級不是 180 | `PlayResX/Y` 未設或不等於輸出解析度 |
| 字沒有粗體 | `Bold` 寫 `1`，應為 `-1` |
| 第一句沒顯示 | ASS 檔存成 UTF-8 **with BOM** |
| 中文變方框 | 字型名稱拼錯，或該機無微軟正黑體 |
| 字幕自動折行 | 單行超過 18 全形字 |
