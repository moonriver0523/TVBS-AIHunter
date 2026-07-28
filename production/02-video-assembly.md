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

先看 SB 起訖是**怎麼來的**，決定走哪條路。這是兩條互斥的路線，**不要串起來做**：

### 路線 A：邊界來自文稿 TC／目測（不精準）→ 用 VAD 精裁

`sb_vad_trim.py`：切掉接點前後約 0.5 秒非受訪內容

- 偵測法：能量 RMS 每 100ms，找**開頭 0.8 秒內最後一個靜音凹陷點**（`< max(0.02, 0.3×median)`），開口在其後；沒有凹陷（一開口就講）就不裁
- `HEAD_PAD=0.08、TAIL_PAD=0.20`
- ⚠️ 不要只用 webrtcvad/能量門檻，會被開頭瞬間雜音（前一鏡尾音）騙（見 `09` B2）

### 路線 B：邊界已由 ASR 詞級時間戳定出 → **直接切，禁止再 VAD 二次裁**

1. 對素材跑 faster-whisper `word_timestamps=True`，定位受訪句的**第一個詞 start／最後一個詞 end**
2. 直接以該區間切片，頭 `-0.10`、尾 `+0.30` 當緩衝
3. 切完**再跑一次 ASR 驗內容**，確認頭尾實字都在

⚠️ **絕不要在路線 B 之後補做 VAD 精裁**：ASR 邊界本來就貼著人聲、沒有非語音前導，VAD 會把**句中的自然停頓**誤判成接點而往內砍。浣熊實測 sb1 3.40→2.13s 砍掉「Me and my」，sb2 砍掉「mammals as well」（見 `09` B3）。

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

- [x] 完成文稿 → 時間軸解析（2026-07-28 完成，沿用驗證器的 `parse_ctv`，見 [`scripts/production/ctv_common.py`](../scripts/production/ctv_common.py)；SB 精確起訖由 [`locate_sb.py`](../scripts/production/locate_sb.py) 對 ASR 詞級時間戳求出）
- [ ] B-roll **智慧選片**（語意對齊畫面與旁白內容；目前為順序填）
- [x] 組裝腳本整理進 repo（2026-07-28）：[`scripts/production/build_video.py`](../scripts/production/build_video.py)
- [ ] ⚠️ **剪接接點「夾畫面／裁切不乾淨」**（使用者 2026-07-25 回報）：**部分解，仍有優化空間**
  - ✅ 已解一半：SB 內容被砍掉的部分，根因是**在 ASR 邊界上再做 VAD 二次裁**（見上方路線 B）。浣熊改用 ASR 詞級邊界直接切後，兩段 SB 內容完整
  - ⬜ 未解：**視訊切點本身仍未做幀級對齊**。切點落在鏡頭轉換中間時，接點前後會夾到前/後一鏡的殘幀
  - 待試方向：(1) 切點吸附到最近的鏡頭轉換（`ffmpeg select='gt(scene,0.3)'` 偵測 scene cut，切點對齊過去）；(2) 接點統一內縮 1-2 幀；(3) 2-3 幀 crossfade 遮掉殘幀；(4) 切片改用關鍵幀對齊避免重編碼誤差
