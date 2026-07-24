# 02 — 剪接組裝（ffmpeg）

> 狀態：**核心已驗證填實**；未知處標 TODO。實測腳本 `D:\voice-training\work\build_fish_video2.py`、`sb_vad_trim.py`。

## 目標

把 OS 配音、SB 受訪原聲、B-roll 畫面按時間軸組成一支影片。

## 時間軸結構（典型 SOT 包）

```
BAR1段OS(B-roll) → SB1(受訪原聲) → BAR2段OS → SB2 → … → 收尾OS
```
每段 OS 鋪 B-roll、配對應 BAR 下標；SB 用素材原音原畫。

## SB 定位與精裁（已驗證）

1. **定位**：文稿 SB 的 TC（如 `0035-0044`）給大概位置，用素材 ASR 逐字稿核對受訪句實際起訖
2. **VAD 精裁**（`sb_vad_trim.py`）：切掉接點前後約 0.5 秒非受訪內容
   - 偵測法：能量 RMS 每 100ms，找**開頭 0.8 秒內最後一個靜音凹陷點**（`< max(0.02, 0.3×median)`），開口在其後；沒有凹陷（一開口就講）就不裁
   - `HEAD_PAD=0.08、TAIL_PAD=0.20`
   - ⚠️ 不要只用 webrtcvad/能量門檻，會被開頭瞬間雜音（前一鏡尾音）騙（見 `09` B2）

## B-roll 分配（已驗證）

- B-roll 池 = 各 SB 之間的畫面段串接（`concat`），**不重複使用**
- 依序切給每段 OS（切片長 = 該段 OS 音訊長）
- **OS 總長 > 可用畫面** → 縮短 OS：
  - 優先刪冗餘句（`trim_os_lines.py`）
  - 或 `atempo` 微變速（比例 = need/footage，≤1.05 無感），**且同步把字幕 cue 時間 `/sp`**
  - 絕不循環重播畫面

## 組裝（已驗證）

- 每段先正規化：`scale=1920:1080,setsar=1,fps=30000/1001` + `libx264 yuv420p` + `aac 48k stereo`（統一參數 concat 才不壞）
- OS 段：影片切片取 `音訊長+0.3`、`-map 0:v -map 1:a -t 音訊長`，**不用 `-shortest`**（否則剪掉 OS 尾字，見 `09` B1）
- 全段 `concat` demuxer `-c copy` → assembled.mp4
- 燒字幕見 `03`

## 硬約束

- 不用 `-shortest`；不重複 B-roll；段落參數統一

## 待補（TODO）

- [ ] 完成文稿 → 時間軸解析（BAR/SB 交錯結構自動抽取）
- [ ] B-roll **智慧選片**（語意對齊畫面與旁白內容；目前為順序填）
- [ ] 組裝腳本整理進 repo `scripts/`
