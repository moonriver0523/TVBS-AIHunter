# CNN掐Bite

本規則是 [`掐BITE助手`](../common/07-bite-assistant.md) 的延伸情境：當 CNN Newsource 的 `SUPERS`／`SOT` 結構文稿，或 AP 式 `SHOTLIST`／`SOUNDBITE` 編號清單**完全沒有 TC** 時，用本流程補上句子級 TC。

**開始前必讀**：[`common/07-bite-assistant.md`](../common/07-bite-assistant.md)。找 TC 的來源優先序、先選句再定位、同支片只跑一次 ASR、ASR 只定位不採用字、精度上限、五行 SB 格式與 TC 欄位寫法，**全部以該文件為準，本文件不重述**。輸出格式、中文翻譯、素材查找、不剪片、不上傳、不另存文字檔等規則同樣沿用。

**Rollback：** 省 Token 改寫前舊版見 [`../_archive/cnn/02-clip-bite.pre-token-saving-2026-07-20.md`](../../_archive/cnn/02-clip-bite.pre-token-saving-2026-07-20.md)。

## 觸發條件

使用者提供一個已存在於下列位置的 CNN／AP 素材檔名，同時貼上該素材的官方文稿，並要求掐出一句或多句 Bite：

1. `G:\我的雲端硬碟\Claude共用\`
2. 「掃帶歐印萬」資料夾（不是名稱含 `v2` 的資料夾）

## 本流程專屬：官方文稿 × ASR 的比對定位法

這是本文件唯一不在 `07` 的內容——當官方文稿有逐字但**沒有任何 TC** 時，怎麼把文稿句子對到影片時間軸：

1. 先從官方文稿鎖定要引用的句子（依 `07` 的「先選句再找 TC」）。
2. 對本機素材檔跑 `video_analyze`（`filters: {transcription: true}`），取得逐句 `start`／`end` 時間戳。
3. 取關鍵字在 ASR 結果中找語意相同或相近的句子：
   - **起點**＝第一個對應句的 `start`。
   - **終點**＝最後一個對應句的 `end`。
   - ASR 有錯字但語意及前後文可確認為同一句時，仍可用來定位。
4. 依 [`TC offset檔名慣例`](../common/02-tc-offset-filename.md) 換算成真實時間後輸出。

## 選擇 Bite

- 使用者指定句子時，定位並輸出指定的一句或多句。
- 使用者只貼官方文稿、要求自行挑選時，依「有新聞價值、有衝突性」原則挑選；記者／主播口白同樣可選（見 `07` 的 BITE 講者範圍）。
- 同一素材需要追加更多句時，直接沿用第一次的完整 `video_analyze` 結果，不重新呼叫分析。

## 輸出

五行 SB 格式與 TC 欄位寫法依 [`掐BITE助手`](../common/07-bite-assistant.md)。本情境的素材通常無 `#編號`：CNN 六碼側錄用 `CNN {6碼起}-{6碼訖}`，其他無編號素材用純起訖時間。

交付給使用者的內容是**純文字五行，不要包在 code fence 裡**；英文原句不加任何引號，且必須逐字來自使用者貼上的官方文稿，不得用 ASR 文字替代。
