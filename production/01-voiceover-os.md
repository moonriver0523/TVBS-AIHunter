# 01 — OS 配音（GPT-SoVITS 本人聲音）

> 狀態：**核心已驗證填實**；未知處標 TODO。實測腳本在本機 `D:\voice-training\work\`。

## 目標

把完成文稿裡的**記者 OS（過音）**用本人聲音模型配出來。

## 範圍（哪些要配、哪些不配）

- ✅ 配：記者 OS 過音段（BAR 段的敘述文字）
- ❌ 不配：**稿頭 LEAD**（棚上主播，跳過）
- ❌ 不配：**SB / BITE**（受訪原聲，保留素材原音）

## 模型與環境

- 現用：**`os_voice3` 低 epoch**（去污染乾淨資料 394 段）：SoVITS `SoVITS_weights_v2\os_voice3_e8_s1064.pth`、GPT `GPT_weights_v2\os_voice3-e12.ckpt`
- ⚠️ **選檢查點別挑最高 epoch**：e20/SoVITS12 會「合成感重、很假」（把多支新聞語調平均掉）；降到 GPT e12 + SoVITS e8 音色追平 v1 又保乾淨資料優勢。**乾淨資料 ≠ 好聽，過度訓練反而爛**
- 引擎：GPT-SoVITS v2，conda 環境 `D:\CondaEnvs\GPTSoVits`（torch 2.5.1+cu124）
- 呼叫：`TTS_infer_pack.TTS`，config `tts_infer.yaml` 覆寫 t2s/vits 權重路徑，`device=cuda, is_half=True, version=v2`
- ⚠️ **log 重導向檔案時 stdout 是 cp950**，中文診斷 print 會 `UnicodeEncodeError` 崩 → 啟動前加 `PYTHONIOENCODING=utf-8 PYTHONUTF8=1`

## 參考音（決定輸出乾淨度）

- 從語料自動挑 **SNR 最高**的原始段（腳本 `rank_clean_refs.py`）：SNR = 99pct峰值 / 10pct噪底；篩 `3.2s≤dur≤9.5s`、`speaker_sim≥0.86`
- **不做降噪**（會削高頻變糊）
- prompt_text 取該參考段在 `.list` 的逐字稿

## 合成流程（已驗證）

1. 完成文稿 OS 段 → 切字幕級短句 →（TODO：通用解析器；目前手動分組）
2. **2–3 句一組**合成（甜蜜點；`text_split_method=cut0`，組內用 `，` 串）
   - 逐句更慘、整段跳句，故取中間
   - **尾字修復（已驗證）**：組尾接**犧牲字** `。嗯。`（`gtext = "，".join(lines) + "。嗯。"`）。AR 解碼器收尾常吃掉真正最後一個音節（加 padding 無效，因為根本沒錄到）；犧牲字逼模型把真字念完，再用 ASR 詞級對齊**切在最後一個真字之後 +0.12s**、丟掉犧牲字。**只在 ASR 覆蓋足夠真字數才切，否則保留全長**（不誤切）。實測 weak 8→3、尾字補回
3. **int16 修正 + 峰值正規化**（防爆音，硬約束）：
   ```python
   y = np.asarray(audio, np.float32)
   if np.max(np.abs(y)) > 2.0: y = y/32768.0
   # 全組串接後：
   block = block/(np.max(np.abs(block)) or 1.0)*0.8
   ```
3. **驗收**：每組 ASR（faster-whisper large-v3）
   - 覆蓋率 = 逐句拼音在 ASR 結果的 in-order 命中率；`cn2an` 正規化數字（避免 32≠三十二 誤判）
   - 門檻 `0.80`；未達 → 換 seed 重試
   - seed 池：`[42,1042,2042,7,123,888,3407,9999]`
   - **語言偵測**：ASR 偵測非中文 → 該組廢棄（非中文＝一定不是本人）
4. 全掛句（8 seed 都 <0.80）→ **編輯刪除**（多為修辭句/與 SB 重複句，可割捨；腳本 `trim_os_lines.py` 依 cue 邊界切）
5. 輸出：乾淨 OS wav（每段一檔）+ 逐句時間戳 JSON（給字幕 `03` 用）
6. **終檢**：逐句 cue 區間 RMS ≥0.02（防「有字幕沒配音」）

## 硬約束（不可違反）

- 輸出前驗 `clip% = mean(|y|>0.99) == 0`（見 `09` A1）
- 不逐句合成、不降噪參考音

## 待補（TODO）

- [ ] 完成文稿 → OS 短句 + 分組的通用解析器（目前手動）
- [ ] 合成/驗收腳本（`synth_os_groups_v3.py`）從 `D:\voice-training\work\` 整理進 repo `scripts/`
