# 製片產出腳本（配音 → 剪接 → 上字 → 終檢）

規則在 [`production/`](../../production/)；這裡是可直接跑的實作。四支照順序跑，
中間的產物都落在**完成文稿所在的資料夾**（`--outdir` 可改）。

```bash
cd 案件資料夾   # 內含 "{SLUG} 完成文稿.txt" 與 "{SLUG}.mp4"
S="{SLUG} 完成文稿.txt"

python locate_sb.py    --script "$S" --source "{SLUG}.mp4"   # ASR + SB 精確起訖
python synth_os.py     --script "$S"                          # OS 配音（可 --dry-run 先看分組）
python build_video.py  --script "$S" --source "{SLUG}.mp4"    # 剪接組裝
python make_subs.py    --script "$S"                          # 三層字幕 + 硬燒
python final_check.py  --script "$S"                          # 終檢，exit 0 才可交
```

| 產物 | 說明 |
|---|---|
| `{SLUG} ASR.txt` | 素材逐字稿（**要跟完成檔一起上傳**，見 `common/08`） |
| `asr_words.json` | 詞級時間戳（SB 切點與字幕錨詞） |
| `sb_spans.json` | 每段 SB 的精確起訖與中文字幕錨點 |
| `os/os{n}.wav`、`os/os_timings.json` | 各段 OS 配音與逐句時間 |
| `assembled.mp4`／`timeline.json` | 未上字的組裝帶 |
| `subs.ass`／`cues.json`／`{SLUG} 完成帶.mp4` | 字幕與成品 |

## 常用旗標

- `synth_os.py --dry-run`：只印分組，不呼叫 TTS。動稿之後先跑這個確認斷句。
- `synth_os.py --only os3`：只重配某幾段（改稿後不要整支重跑）。
- `locate_sb.py --anchors anchors.json`：手動指定 SB 每行中文對到的原文詞，
  例 `{"sb1": ["bedtime", "of", null]}`（`null` = 跟到句尾）。自動分配已足夠時不用給。
- 環境變數 `GPT_SOVITS_DIR`、`FW_MODEL` 可覆蓋預設路徑；聲音模型用 `--gpt/--sovits`。

## 前提

完成文稿必須先過 `python scripts/validate_sot.py "…完成文稿.txt" --mode ctv`（exit 0）——
這裡的解析直接沿用驗證器的 `parse_ctv`，格式不合會直接讀不出來。
