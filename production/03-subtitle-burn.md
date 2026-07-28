# 03 — 上字（硬字幕 / BAR 下標 / SUPER 名條）

> 狀態：**核心已驗證填實**；TVBS 正規樣式待接。

## 三層字幕

| 層（ASS style） | 內容 | 出現時機 |
|---|---|---|
| `Cap` 逐句字幕 | OS/SB 逐句中文 | 全程 |
| `Bar` 下標 | 每段標題（文稿 BAR1-4） | 對應 OS 段全程 |
| `Super` 名條 | 受訪者職稱+姓名（文稿 SUPER） | 對應 SB 段全程 |

## OS 字幕同步（已驗證）

1. 用 ASR **詞級時間戳**（faster-whisper `word_timestamps=True`）
2. 分配到**實際語音區間** `[首詞start, 尾詞end]`（非整段含留白，否則不同步）
3. **零長度防呆**（1:18 亂源，見 `09` C1）：ASR 漏詞導致詞用完時，把剩餘句**均分到 `[最後 cue 尾, 段尾]`**，保證無零長度塌陷
4. **尾字延長**：每句 end +0.15s（上限＝下一句 start）；最後一句 end = 段長
5. SB 字幕：文稿 SB 中文譯文，分配到受訪語音區間
   - ⚠️ **受訪者句中停頓時，等比例分配會整條字幕落在空拍上**（`胰癌新藥1600` 的 Sasse 中間停 2 秒）。有原文詞級時間戳時，**把每行中文錨到它涵蓋的最後一個原文詞**（`就在睡前`→`bedtime`、`我會吃下幾百毫克的`→`of`），沒有時間戳才退回「只在有聲區間內」等比例分配
6. **終檢掃全片**：除了逐句 RMS，另外掃「聽得到卻沒有任何字幕覆蓋」的區段（見 `09` A7）——OS 段多出來的雜訊只有這道會亮

## 燒錄（已驗證）

- 產 ASS → ffmpeg `subtitles` 濾鏡硬燒（`libx264 crf20`，音訊 copy/aac）
- ⚠️ Windows 路徑跳脫雷：**`cd` 到 .ass 所在目錄，用相對檔名 `subtitles=subs.ass`**（見 `09` D1）

## 暫用樣式（實測可讀，待接 TVBS 正規 CG）

```
PlayResX/Y: 1920/1080，字型 Microsoft JhengHei
Cap  : 58px 白字黑邊(Outline3) 底部置中 MarginV220
Bar  : 52px 黃字(&H0000FFFF) 半透明深藍底框(BorderStyle3) MarginV300
Super: 46px 白字 半透明藍底框(BorderStyle3) 左下 MarginV300
MarginL/R 均為 140
```

> **MarginV 由 70／175 改為 220／300（2026-07-28，`胰癌新藥1600`）**：舊值會讓字壓在安全框外。以 [`reference_tvbs_safe_frame_spec`](../README.md) 的 1920×1080 基準（X=140 Y=109 W=1634 H=751 → 內容下緣不得低於 y=860）換算，字幕底線至少要離下緣 220px。Bar 與 Super 不會同時出現（Bar 在 OS 段、Super 在 SB 段），可共用同一層高度。

## 待補（TODO）

- [ ] **TVBS 正規 CG 樣式**：BAR/SUPER 的正式配色、字級、位置、動態
- [x] **安全框**套用（2026-07-28 完成）：見本機記憶 `reference_tvbs_safe_frame_spec`（1920×1080 基準 X=140/Y=109/W=1634/H=751，來源 tools.tvbs.ai/tools/locked-frame/）→ 已落成上方 MarginL/R 140、MarginV 220/300
- [x] 字幕腳本整理進 repo（2026-07-28）：[`scripts/production/make_subs.py`](../scripts/production/make_subs.py)、終檢 [`final_check.py`](../scripts/production/final_check.py)
