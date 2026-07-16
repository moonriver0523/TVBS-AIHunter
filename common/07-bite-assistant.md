# 掐BITE助手

當使用者以「掐BITE助手」呼叫，或給素材編號/檔名並要求找出一段 Bite 的 TC 與雙語逐字時，依本規則執行。前身是已移除的「指定掐Bite」，現已升級為跨來源獨立流程——不限於 Reuters 素材，也不限於接續寫稿流程，日常任何場合都可直接呼叫。

只在對話中輸出指定格式的文字，不使用 ffmpeg、不剪片、不將檔案上傳雲端，也不另存 `.txt`。

## 輸入方式

### 方式1：指定素材編號掐BITE

適用於已有 `#編號` 的素材（例如批次下載後的編號清單，見 [`common/05-material-numbering.md`](05-material-numbering.md)）。使用者給素材編號，有兩種分支：

- **分支1**：使用者再給一段文字（中文或原文），去該編號對應的影片與文稿裡找出這段話的位置與 TC。
- **分支2**：使用者不給文字，要求自己讀該編號文稿，依新聞價值與重大性判斷，建議兩段 Bite。

### 方式2：CNN 6碼側錄素材掐BITE

適用於「側錄素材」（CNN 側錄音檔的6碼時間戳，例如 `060710`，不是 CNN Newsource 網站的編號素材）：

1. 去雲端「掃帶歐印萬」資料夾（不是名稱含 `v2` 的資料夾）找**相近時間碼**的素材——資料夾內檔名以6碼時間戳開頭，但清單上的時間碼不一定剛好有同名檔案，要自行判斷找最接近的。
2. 讀該素材的雙語對照逐字稿，找出合適 Bite 片段（長度限制：2句話或10-20秒，上限25秒）。
3. **若沒有現成逐字稿**，需要自行轉譯影音檔找 Bite 時，依 [`TC offset檔名慣例`](02-tc-offset-filename.md) 換算：檔名前6碼（例如 `060656`）＝該檔案 `00:00:00` 對應的真實時間 `06:06:56`，轉譯工具回報的內部時間（從0開始）都要加上這個偏移，才是正確的真實 TC。

### 方式3：本機/雲端已存素材，無編號

素材已存在本機或雲端（不上 Reuters Connect 搜尋或下載）。使用者提供檔名時，依序在下列位置尋找：

1. `G:\我的雲端硬碟\Claude共用\`
2. 「掃帶歐印萬」資料夾（不是名稱含 `v2` 的資料夾）

使用者也可能不提供要引用的句子，而是將完整、未經處理的外電原始文稿（例如 Reuters 完整逐字稿或 shotlist 原文）直接貼在文字視窗，要求自行從中挑選一段有新聞價值且有衝突性的 Bite。此時直接以使用者貼上的原文判斷，不另行尋找素材檔案查看內容。

### 補充情境：官方 CNN/AP 文稿沒有 TC 時

若引言來源是官方 CNN/AP 文稿（CNN Newsource 的 `SUPERS`／`SOT` 結構、或 AP 式 `SHOTLIST`／`SOUNDBITE` 編號清單）但文稿本身完全沒有 TC，套用 [`cnn/02-clip-bite.md`](../cnn/02-clip-bite.md) 的技術做法：對本機影片檔跑 `video_analyze`（`filters: {transcription: true}`）取得逐句 ASR 時間戳，把官方文稿句子對照 ASR 結果定位起訖時間，再依 [`TC offset檔名慣例`](02-tc-offset-filename.md) 換算真實時間；**引言文字內容一律以官方文稿為準，不採信 ASR 轉譯的用字**（ASR 只用來定位時間，可能有同音錯字）。

## 找 TC 共用原則

- 對照素材/使用者貼文的逐字稿、transcript 確認起訖 TC；若貼上的原始文稿本身已含時間標記，直接使用該標記。
- 逐字稿標示的時間精確度就是可用上限，不自行推估到更細的時間，也不宣稱比逐字稿更精確。
- 不擴寫或改寫英文引言；最後輸出的英文必須逐字照抄來源原文。

## 4. 套用檔名 TC offset（方式2、方式3與補充情境適用）

檔名前6碼的解析、有效性判斷、8碼檔名處理及相對TC換算，全部以 [`TC offset檔名慣例`](02-tc-offset-filename.md) 為單一規則來源，本文件不另行定義。換算完成後，再依下方輸出格式呈現真實起訖TC。

## 輸出格式（統一版，取代舊的4行單行標籤格式）

```text
SB
{職稱} {姓名}
{中文翻譯口白}（不帶「」引號）
{TC欄位}
{英文/原文原句}
```

格式規則：

- 順序固定為：SB → 職稱姓名 → 中文翻譯 → TC欄位 → 英文原文。
- **有 `#編號` 的素材**（方式1）：TC欄位＝`#{素材編號} {TC起}-{TC訖}`。
- **沒有 `#編號` 的素材**（方式2、方式3、補充情境）：TC欄位＝純**6碼無冒號格式**起訖時間，例如 `060900-060923`，不帶清單上的原始代碼。
- 中文翻譯必須是忠於原意的原創繁體中文翻譯，不帶「」引號。
- 英文逐字照抄來源原文；若來源是官方文稿，一律以官方文稿為準，不採信 ASR 文字。
- 除上述內容外，不附加流程說明、搜尋紀錄或檔案處理說明。

範例（方式1，有編號）：

```text
SB
智利總統 卡斯特
那些透過非法、不正規且秘密手段越境的人，遲早必須離開我們的國家。
#03 0033-0044
Those who came in through the window in an illegal manner, in an irregular and clandestine manner, sooner rather than later, will be outside our country.
```

範例（方式2，CNN6碼）：

```text
SB
白宮記者 Kevin Liptak
他們不必造成巨大破壞或把船擊沉，就能實質關閉水道，因為船長不願冒險通過。除非透過外交手段讓伊朗退讓，否則要重新開放該水道會很難。
060900-060923
They don't have to really cause that much damage or sink them, but they still are able to essentially close the waterway because ship captains are unwilling to take the risk of trying to transit through. And unless you get the Iranians to back off of that diplomatically, it will be very difficult to get that waterway reopened.
```
