# auto-editor／video-use 導入評估 — V2：自動配音剪接（GPT-SoVITS OS）

- 日期：2026-08-18
- 性質：**評估報告，不是規則、不是授權實作**——結論為可行性與整合方向評估，是否真的動工、動多少、先做哪塊，由使用者裁定
- 對應現行規則：`production/09-known-issues.md` A–D 節（GPT-SoVITS 合成 OS＋剪接＋字幕的既有踩雷/定版流程）
- 觸發：使用者新裝 `auto-editor`（本機二進位 `C:\Users\User\bin\auto-editor.exe`）與 `video-use`（skill，clone 在 `E:\GitHub\video-use`，跳過 ElevenLabs API，轉錄仍走既有 faster-whisper），要求評估怎麼接進既有兩條規則
- 兩個工具的定位：`auto-editor` 是純本機、無需 API 的「音量式自動靜音切除＋剪接」CLI；`video-use` 是一套「LLM 讀逐字稿做剪接決策」的完整 skill/方法論，其轉錄用 ElevenLabs Scribe（本次跳過），但**剪接/調色/字幕/動畫的具體 ffmpeg 技法本身不依賴 API key**，可以直接借用寫法

---

## 一、先講結論

**video-use 的「Hard Rules」比它的轉錄後端更有價值**——裡面明確列出的幾條 ffmpeg 剪接鐵律，正好對到我們 A–D 節反覆踩過的坑，是**可以直接吸收、不需要整套工具依賴**的部分。auto-editor 則適合替換 A7（組首雜訊偵測）跟 B 節（剪接對齊）裡手刻的靜音/雜訊判斷邏輯，但**不適合**取代 GPT-SoVITS 合成與覆蓋率驗收本身（那是這條流程的核心，兩個工具都不做語音合成）。

## 二、video-use Hard Rules 對照既有踩雷

| video-use 規則 | 對應現行規則 | 差距 |
|---|---|---|
| **30ms 音訊 fade 在每個片段邊界**（`afade=t=in:st=0:d=0.03,afade=t=out:...`） | 無對應——A/B 節目前只做「頭部裁切」「+0.3秒緩衝」，**完全沒有做淡入淡出** | ⚠️ **這條我們一直沒做**，很可能是 A7「組首雜訊」、B1「-shortest 剪尾字」這類問題的一部分成因——硬切點本身就容易有可聽見的爆音/喀聲，淡入淡出是業界標準解法，成本極低（一行 ffmpeg filter），**建議直接採用，不需要整套工具** |
| **Per-segment extract → `-c copy` concat**，不要單一 filtergraph | 現行 B 節剪接流程已經是這個模式（分段合成→逐段裁切→組裝） | ✅ 已符合，無需改動 |
| **剪接點必須落在字詞邊界，不可切在字中間** | A3/A5 已有「ASR 覆蓋率驗收」「犧牲字補尾音」邏輯，精神一致 | ✅ 概念已具備，但 video-use 把它訂成「絕對規則」而非事後補救，可以把驗收邏輯提前到**選字級時間戳時就對齊**，減少事後補救的犧牲字技巧複雜度 |
| **字幕永遠疊加在最後一層**（overlay 之後才燒字幕） | 現行流程沒有 overlay 疊加需求（新聞 OS 通常不疊動畫），此規則暫不適用 | 空 — 除非未來 AICG/CG 需求要疊圖層才會用到 |
| **自我驗收：render 完再用 timeline_view 抽格＋看波形，逐一過每個剪點 ±1.5秒**，最多 3 輪 | 現行「方法論」有「交付前自動驗證」，但主要是數值檢查（clip%/RMS/覆蓋率），**沒有「抽格看畫面」這層** | ⚠️ 值得補：純數值驗收會漏掉「數值正常但畫面/聽感怪」的情況（跟這次人工配音檔消化整個下午在追的「頭尾殘字/雜音」是同一類問題——數值過關不代表聽感過關）。**建議把「render 後抽剪點前後 1.5 秒波形圖＋看一眼」正式納入終檢步驟** |

## 三、auto-editor 可以吃掉哪些手刻邏輯

| 現行手刻邏輯 | auto-editor 對應能力 | 建議 |
|---|---|---|
| A7 組首雜訊偵測（`words[0].start - 0.12` 裁切、雜訊區段掃描） | `--edit audio:threshold=X` + `--margin` 直接做音量式靜音/雜訊切除，是同一件事的成熟實作 | 可評估替換，但 A7 的「雜訊偵測」是**合成音檔特有**的問題（GPT-SoVITS 偶發吐雜訊），跟 auto-editor 設計拿來處理「人講話中的停頓」場景不完全一樣，需要先拿實際 A7 案例（`胰癌新藥1600`）測試門檻值抓不抓得到 |
| B1（`-shortest` 剪尾字問題）、B2（BITE 接點抓開口點） | `--margin` 控制留白、`--transition dissolve:DURATION` 直接加交叉淡化 | 這條**直接對應**，`--transition dissolve` 等於幫我們把「30ms fade」這條 video-use 鐵律內建成一個 CLI 參數，比手刻 ffmpeg filter 更省事 |
| whisper 逐字時間戳（現行走 faster-whisper） | auto-editor 內建 `whisper` 子命令，本機跑、有 `--split-word` 逐字輸出、`-t threshold` | 功能重疊，**沒有明顯優勢取代現有 faster-whisper 腳本**（模型/精度未知，需要實測比較），優先度低 |

## 四、不建議動的部分

- **GPT-SoVITS 合成、ASR 覆蓋率驗收弱句換 seed（A2/A3）**：這是這條流程的核心邏輯，兩個工具都不做語音合成，不受影響、不需要改
- **video-use 的轉錄/剪接決策方法論（`takes_packed.md`、editor sub-agent）**：那套是給「多顆機位/多次拍攝挑最佳鏡頭」的真人拍攝場景設計的，新聞 OS 只有一顆聲音來源（合成配音），不需要整套「多 take 挑選」機制

## 五、建議的落地順序（未裁決，供參考）

1. **先做最小改動、風險最低的**：在既有剪接組裝步驟加上 30ms 音訊 fade（video-use 規則 3），這是純加分項、不影響現有邏輯
2. **拿 `--transition dissolve` 測試取代手刻 B1/B2 的邊界處理**，用既有案例（`魚群暴斃1600`／`胰癌新藥1600`）比較效果
3. **補「render 後抽剪點畫面/波形看一眼」進終檢流程**（不一定要用 video-use 的 `timeline_view.py`，可以用 ffmpeg 自己截圖+畫波形，或直接借那支腳本，它不依賴 ElevenLabs）
4. auto-editor 的 A7 雜訊替換與 whisper 子命令暫緩，優先度較低，除非現有手刻邏輯遇到新案例明顯不夠用

## 六、與現有規則庫的關係

延伸自 `production/09` A–D 節與 [[reference_auto_video_pipeline_pitfalls]]，本檔評估完成、狀態=待使用者裁定是否動工；動工前不修改 09 正式規則。
