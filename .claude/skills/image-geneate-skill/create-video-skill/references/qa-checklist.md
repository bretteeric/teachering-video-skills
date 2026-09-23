# 驗收檢查表

**每一項都要實際跑過**，不能目測帶過。任一項不過就回到對應階段修正。

---

## 1. 影片規格

```powershell
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,codec_name,pix_fmt,r_frame_rate -of default=nw=1 "教學影片/{檔名}.mp4"
```

- [ ] `width=3840` / `height=2160`（4K）
- [ ] `codec_name=h264`、`pix_fmt=yuv420p`
- [ ] 檔名為 `{提示詞輸入的檔案名稱}.mp4`，位於 `教學影片/`

## 2. 音訊

```powershell
ffprobe -v error -select_streams a:0 -show_entries stream=codec_name,sample_rate,channels -of default=nw=1 "教學影片/{檔名}.mp4"
```

- [ ] 音軌存在，`aac` / 48000Hz
- [ ] **首尾無爆音**——檢查首尾各 0.25 秒（片頭靜音設計值為 0.3 秒，
      窗開太大會抓到正常語音而誤判）：

```python
import subprocess, struct, math
raw = subprocess.run(["ffmpeg","-v","error","-i",MP4,"-f","s16le","-ac","1","-ar","48000","-"],
                     capture_output=True).stdout
d = struct.unpack(f"<{len(raw)//2}h", raw[:len(raw)//2*2])
w = 12000                                        # 0.25 秒 @ 48kHz
print("head max:", max(abs(x) for x in d[:w]))   # 應接近 0
print("tail max:", max(abs(x) for x in d[-w:]))  # 應接近 0
print("first/last sample:", d[0], d[-1])         # 應為 0
```

- [ ] 首尾樣本為 0，首尾 0.25 秒近乎靜音
- [ ] 全片峰值 ≤ -1.0 dBFS（無削波）
- [ ] 逐段接點無喀噠聲（實際聽過場景交界處）

## 3. 旁白品質（人工聽過，不可跳過）

- [ ] 台灣腔，男聲，語調沉穩
- [ ] 語速平順緩和，不趕不拖
- [ ] **聽起來像講話，不像念稿**（最重要）
- [ ] 專有名詞唸法正確（英文縮寫、產品名）
- [ ] 沒有把符號唸出來（底線、斜線、括號）

## 4. 字幕

- [ ] **文字與旁白逐字一致** —— 用程式比對，不能目視：

```python
# 把 ASS 所有 cue 串起來，與 narration.txt 去標點後比對
import re, unicodedata
def norm(s): return re.sub(r"[，。、；：？！\s]", "", s)
assert norm(cues_joined) == norm(narration_all), "字幕與旁白不一致"
```

- [ ] 字級 180px、紅棕色 `#B04A32`、微軟正黑體、**繁體**中文
- [ ] 單行不超過 18 個全形字，無自動折行
- [ ] 無簡體字殘留：

```python
import re
assert not re.search(r"[这个说话学习实现验证网络数据设备权限统计]", text), "混入簡體字"
```

- [ ] 字幕與語音同步（抽 5 個時間點目視確認，含開頭、中段、結尾）
- [ ] 同時輸出 `.srt`，UTF-8 無 BOM

## 5. 內容正確性

- [ ] 操作步驟與實際系統一致，沒有虛構的按鈕或流程
- [ ] mermaid 圖與文件描述相符，中文無方框
- [ ] 技術說明正確（有講「為什麼」不只「是什麼」）
- [ ] 畫面中**無真實個資、無正式環境密碼與 Token**

## 6. 觀看體驗

- [ ] 抽查 5 張影格，UI 文字銳利可讀

```powershell
foreach ($t in 5,30,60,90,120) { ffmpeg -y -v error -ss $t -i "教學影片/{檔名}.mp4" -frames:v 1 "chk_$t.png" }
```

- [ ] 字幕未遮住重要操作區
- [ ] 無單一畫面靜止超過 15 秒
- [ ] 轉場自然，無黑幀、無跳接
- [ ] 從頭到尾完整播放一次無異常

---

## 選用：ASR 交叉驗證

可用 ffmpeg 內建的 whisper 濾鏡把成品音訊轉回文字，與腳本比對，抓出破音或唸錯的字。

> **僅供驗證。絕不可用 ASR 結果當字幕** —— 字幕一律來自旁白腳本原文，那才是「完全正確」的保證。

---

## 交付

- [ ] `教學影片/{檔名}.mp4`
- [ ] `教學影片/{檔名}.srt`
- [ ] scratchpad 中間檔已清理，未污染專案目錄
- [ ] 回報影片長度、場景數、檔案大小
