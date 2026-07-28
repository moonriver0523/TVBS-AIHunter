# 製片產出（Production）— 自動剪片配音上字

> 狀態：**規則空殼，逐步回填中**（2026-07-25 建立）。工作流程細節待補；已驗證的踩雷見 `09-known-issues.md`。

## 這一段在系統中的位置

端到端外電自動化的**最後一段**：把「完成文稿 + 素材影片」變成可上鏡的成品。

```
自動下載 → 自動寫稿(SOT/CTV) → 【製片產出：配音 + 剪接 + 上字】 → 成品 mp4
                                   ↑ 本模組
```

## 輸入 / 輸出

- **輸入**：
  - 完成文稿（`common/06-auto-script-sot.md` / `cnn/01-auto-script-writing.md` 產出的台灣播出格式稿）
  - 素材影片（外電成品或母帶）
  - 母帶 TC offset（`common/02-tc-offset-filename.md`）
- **輸出**：
  - 配音上字成品 `.mp4`（1920×1080），OS 用本人聲音、保留 SB 受訪原聲、燒中文硬字幕 + BAR 下標 + SUPER 名條
  - 完整版上雲端 `Claude共用`，壓縮預覽版供即時檢視

## 子流程（各自一份規則檔）

| 檔案 | 內容 | 狀態 |
|---|---|---|
| `01-voiceover-os.md` | OS 配音（GPT-SoVITS 本人聲音；跳過 LEAD 稿頭、跳過 SB） | 待回填 |
| `02-video-assembly.md` | 剪接組裝（B-roll 分配、SB 接點 VAD 精裁、時間軸） | 待回填 |
| `03-subtitle-burn.md` | 上字（硬字幕 / BAR 下標 / SUPER 名條 / 安全框） | 待回填 |
| `09-known-issues.md` | 已驗證踩雷與定版流程 | 已有內容 |

## 前置依賴（阻擋正式上鏡）

- **聲音模型**：目前用 `os_voice`(v1)，尾字偶爾偏軟。需先修訓練資料污染、重訓 **os_voice3**（見本機 `project_voice_clone_gptsovits` 記憶 / `D:\voice-training`）才夠正式播出。
- 環境：GPT-SoVITS 於 `E:\GitHub\GPT-SoVITS`、conda 環境 `D:\CondaEnvs\GPTSoVits`（torch 須 2.5.1+cu124）。

## 實測案例

- CTV「魚群暴斃1600」（首例）：外電成品 → TVBS 中文版（配音 + 上字），流程全自動走通，成品在 `Claude共用\CTV自動寫稿測試\魚群暴斃1600\`。
- CTV「胰癌新藥1600」（2026-07-28，PY-11MO）：寫稿→配音→剪接→上字全鏈一次跑完，成品 89.9 秒。本案新增 `09` A7／A8 兩條踩雷（組首雜訊、繁簡多音字誤判）與 `03` 的安全框 MarginV、SB 字幕錨詞做法。
