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

## 燒錄（已驗證）

- 產 ASS → ffmpeg `subtitles` 濾鏡硬燒（`libx264 crf20`，音訊 copy/aac）
- ⚠️ Windows 路徑跳脫雷：**`cd` 到 .ass 所在目錄，用相對檔名 `subtitles=subs.ass`**（見 `09` D1）

## 暫用樣式（實測可讀，待接 TVBS 正規 CG）

```
PlayResX/Y: 1920/1080，字型 Microsoft JhengHei
Cap  : 58px 白字黑邊(Outline3) 底部置中 MarginV70
Bar  : 52px 黃字(&H0000FFFF) 半透明深藍底框(BorderStyle3) MarginV175
Super: 46px 白字 半透明藍底框(BorderStyle3) 左下 MarginV175
```

## 待補（TODO）

- [ ] **TVBS 正規 CG 樣式**：BAR/SUPER 的正式配色、字級、位置、動態
- [ ] **安全框**套用：見本機記憶 `reference_tvbs_safe_frame_spec`（1920×1080 基準 X=140/Y=109/W=1634/H=751，來源 tools.tvbs.ai/tools/locked-frame/）
- [ ] 字幕腳本整理進 repo `scripts/`
