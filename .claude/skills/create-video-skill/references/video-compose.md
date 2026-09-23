# 影片合成

把 3840×2160 PNG 素材 + `narration.wav` + `subtitle.ass` 合成為最終 MP4。

---

## 一、時間軸原則

**場景長度由旁白決定，不是反過來。**

```
scene.duration = Σ(該場景各句實測長度) + 句間停頓
```

`timeline.json`（由 `narrate.py` 產出）記錄每個場景的起訖：

```jsonc
{
  "total": 128.45,
  "scenes": [
    { "id": "s01", "start": 0.0,   "end": 12.3 },
    { "id": "s02", "start": 12.3,  "end": 31.8 }
  ]
}
```

合成時直接照這份時間軸配置畫面。轉場時間**算在前一個場景內**，不額外增加總長，否則音畫會漸進飄移。

---

## 二、單一場景片段

```powershell
ffmpeg -y -loop 1 -i scene.png -t 12.3 `
  -vf "scale=3840:2160:force_original_aspect_ratio=decrease,pad=3840:2160:(ow-iw)/2:(oh-ih)/2:color=0x0f172a,fps=30,format=yuv420p" `
  -c:v libx264 -preset medium -crf 16 scene.mp4
```

`force_original_aspect_ratio=decrease` + `pad` 保證**不變形**（mermaid 圖比例常與 16:9 不同）。

### 運鏡（避免長時間靜止畫面）

超過 6 秒的靜態畫面用緩慢推近（Ken Burns）：

```
zoompan=z='min(zoom+0.00015,1.08)':d=<幀數>:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30
```

- 幅度**很小**（最多 1.08 倍）。教學影片的重點是看清楚介面，大幅運鏡會讓人分心。
- 操作步驟畫面（`screen`）**不要運鏡**，觀眾需要看清楚 UI 細節。
- `zoompan` 在 4K 下較耗時，先跑一個場景確認時間再全跑。

---

## 三、串接與轉場

同場景內的步驟影格用短交叉溶接（0.3s），場景之間用稍長（0.5s）。

### 用單一濾鏡鏈，不要逐次兩兩接合

```
[0:v][1:v]xfade=transition=fade:duration=0.5:offset=o1[v1];
[v1][2:v]xfade=transition=fade:duration=0.5:offset=o2[v2];
[v2]ass='subtitle.ass'[vout]
```

`offset` 是**累積長度 − 本次轉場長度**，逐段遞推：

```python
acc = durs[0]
for i in range(1, len(clips)):
    off = acc - trans[i-1]
    acc = acc + durs[i] - trans[i-1]
```

**不要**寫成「接一次輸出一個檔、再拿去接下一個」。那樣第一段會被重複編碼 N 次
（N = 片段數），4K 下畫質累積劣化且時間呈平方成長。整條鏈一次算完，全片只編碼一次。

轉場只用 `fade`（或 `wipeleft`）。**不要**用 `circleopen`、`pixelize` 等花俏轉場——教學影片要穩重。

### 轉場一定要補償長度

每接一次，總長就少掉一個轉場的時間，但**音訊沒有變短**。不補回來的話，
每過一個轉場音畫就飄移一次（實測三個場景就差 1.9 秒，結尾旁白直接被 `-shortest` 截掉）。

每個場景的片段長度預算：

```
budget = 旁白長度
       + (該場景影格數 - 1) × 0.3     # 場景內轉場
       + 0.5                          # 場景間轉場（最後一個場景不加）
       + 片頭靜音（第一個場景）
       + 片尾靜音（最後一個場景）
```

合成後應檢查「畫面總長 ≈ 旁白總長」，差距超過 0.5 秒就是補償算錯了。

---

## 四、最終輸出

```powershell
ffmpeg -y -i video_concat.mp4 -i narration.wav `
  -vf "ass=subtitle.ass" `
  -map 0:v:0 -map 1:a:0 `
  -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p `
  -profile:v high -level 5.1 `
  -x264-params "keyint=60:min-keyint=30" `
  -color_primaries bt709 -color_trc bt709 -colorspace bt709 `
  -c:a aac -b:a 192k -ar 48000 `
  -movflags +faststart `
  -shortest `
  "教學影片/{檔名}.mp4"
```

| 參數 | 理由 |
|---|---|
| `-crf 18` `-preset slow` | 4K 螢幕畫面的文字需要較高位元率才不糊 |
| `-pix_fmt yuv420p` | 相容性；缺了在部分播放器不顯示 |
| `-level 5.1` | 4K30 的必要 level |
| `-movflags +faststart` | moov atom 前置，網頁可邊下載邊播 |
| `-shortest` | 音視訊長度若差幾十毫秒，以短者為準 |
| `bt709` | 標示色彩空間，避免播放器猜錯導致偏色 |

### 硬體加速（選用）

本機 ffmpeg 有 NVENC。趕時間可用：

```
-c:v h264_nvenc -preset p6 -rc vbr -cq 20 -b:v 0
```

但**文字銳利度略遜於 x264 CRF 18**。最終交付建議仍用 x264；NVENC 用於預覽草稿。

---

## 五、字幕燒錄順序（易錯）

```
素材 PNG → 縮放至 3840×2160 → 串接 → 【燒字幕】 → 編碼
```

**字幕必須最後燒。** 若在縮放前燒錄，字級會跟著被縮放，180px 就不再是 180px。

濾鏡用 `ass=` 而非 `subtitles=`（見 `subtitle-ass.md`）。

---

## 六、輸出驗證

```powershell
ffprobe -v error -select_streams v:0 `
  -show_entries stream=width,height,r_frame_rate,codec_name,pix_fmt `
  -of default=nw=1 "教學影片/{檔名}.mp4"

ffprobe -v error -select_streams a:0 `
  -show_entries stream=codec_name,sample_rate,channels `
  -of default=nw=1 "教學影片/{檔名}.mp4"
```

必須是 `width=3840` / `height=2160` / `codec_name=h264` / `pix_fmt=yuv420p`，且音軌存在。

抽一張中段影格目視確認字幕：

```powershell
ffmpeg -y -ss 30 -i "教學影片/{檔名}.mp4" -frames:v 1 check.png
```
