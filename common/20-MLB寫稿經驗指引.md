# MLB 寫稿經驗指引

**用途**：SOT 寫稿遇到 MLB（或同類美國職業運動賽事）新聞時才讀。日常 SOT 不預讀；[`06-auto-script-sot.md`](06-auto-script-sot.md) 只放一行提醒指到這裡。

**來源案例**：`道奇淘汰1700`（2026-10-16，國聯冠軍賽第 4 戰，釀酒人 6:4 道奇、4:0 橫掃）。完成稿、人工改稿、背景資料與精華 TC 都在 `Claude共用\SOT自動寫稿測試\道奇淘汰1700\`；後台稿號 4036973。

本文件是經驗紀錄，不是硬規則；與 `06`／`07`／`00` 衝突時以那些檔案為準。

---

## 1. 素材與授權（先看，會直接決定能不能用）

- **MLB 比賽畫面時效很短**，起稿前先查每支的限制：
  - **AP 的 SNTV 精華**（編號 `AP5` 開頭）通常寫：24 小時內使用、每場比賽最多 2 分鐘、只限定時新聞、不可上社群、要標 MLB。
  - **Reuters 的 MLB 精華**限制更硬，寫死「比賽結束 24 小時後不可使用」（附 GMT 時間，例：`No use after 0600GMT on October 16, 2026`）。案例中 RT0330（第 3 戰）在寫稿當下已經過期，使用者指示排除，只用 AP。
- **SNTV 賽後受訪**（`Baseball MLB {人名} Reaction`）多半是「可上網、不用下架」，但可能要求標轉播來源，例：大谷受訪要標 Sportsnet LA。
- **賽後受訪會比比賽精華晚幾個小時才上架**。使用者要「某球星受訪」時，用球星英文名或 `Dodgers Reaction`、`Roberts` 這類關鍵字在 AP API 現搜，並看 `arrivaldatetime`。案例：大谷受訪 AP5472892 比比賽精華晚了約 3 小時才出現。
- **清單裡的「賽後記者會」要核對是哪一場**。案例中 AP5472815／AP5472820 是第 3 戰後（0:3 落後時）的受訪，不是淘汰當天的。要明講，不能把前一場的談話寫成賽後感想。
- **使用者的稿單比分描述可能和官方分鏡不同**，要回頭核對。AP 分鏡也可能標錯局數：案例中 AP 把 4:4 扳平寫在 4 局上，實際是 5 局上（以 NBC LA 報導與畫面計分板為準）。

## 2. 比賽精華的 TC：看畫面上的計分板

- 精華片畫面的計分板有比分、局數、投打者名字，可以用來定位每個關鍵球。
- 接觸表做法：`ffmpeg -vf "fps=1/5,scale=320:-1,drawtext=fontfile='C\:/Windows/Fonts/arial.ttf':text='%{pts\:hms}':...,tile=6x6"`。
  - ⚠️ `drawtext` 不指定 `fontfile` 會因 Fontconfig 找不到設定而 segfault，一定要給字型路徑。
- 一張 6x6 接觸表就能看完 2–3 分鐘精華：哪一格比分變了、哪一格出現「SOLO HOME RUN {人名}」字卡，那就是該球的 TC。

## 3. 球評是主要 BITE 來源（ASR 要換參數）

- 使用者明講：**比賽片段的球評解說是 BITE 主要用到的**。
- ⚠️ **預設的歐印萬 ASR（`oyinwan_asr_draft.py`，開 VAD）在比賽轉播上幾乎轉不出球評**。觀眾聲會被 VAD 判成雜音吃掉，案例 #01 整支 2:41 只剩 6 段。
- **改用 whisper-cli 關 VAD、逐句切分**：
  ```bash
  whisper-cli --model ~/.claude-video-vision/models/ggml-large-v3-turbo.bin --file a.wav --language en -ml 90 -sow --output-srt --output-file out
  ```
  案例 #01 從 6 段變 35 句，關鍵球的球評都有出來。
- **需要精準起訖時**，把那一段切出來（`ffmpeg -ss 55 -t 20`），用 `-ml 1 -sow --output-csv` 拿字級時間戳。
- **TC 誤差**：觀眾聲蓋過的地方 ±1–2 秒，掐之前請使用者用耳朵確認。球評在歡呼聲中拉長尾音時，字級時間戳會被拉得很長，例：「the Brewers are going to the World Series」被拉到約 10 秒。
- **ASR 常錯的人名**：Otani＝Ohtani、Bowers＝Bauers、Jerry／Sherry＝Chourio。要搭配畫面上的背號確認。
- **SB 講者行**：使用者人工稿改成 `MLB轉播球評`（只寫職稱，不寫名字）。

## 4. 背景資料：上網查轉折點

- 使用者會要求「查網路新聞的精彩點與轉折點當背景資料，再找素材裡對應的 TC」。產出一份 `{SLUG} 背景資料與精華TC.txt`，依局數列出事件、數據與 TC。
- ⚠️ **搜尋結果會混到去年同系列賽**（2025 年國聯冠軍賽也是道奇對釀酒人第 4 戰）。每篇都要核對年份與比分。
- 可用來源：NBC Los Angeles 的 AP 賽後稿（逐局最完整）、Bleacher Report 文字轉播（數據多，但「史上首見」類說法只有它寫時要再核）、AP STORYLINE（素材文稿內就有）。MLB.com 用 WebFetch 會回 406。
- 球星數據（季後賽打擊率、三振數、開轟荒幾個打席）通常在 AP STORYLINE 裡就有，要寫進 OS。

## 5. 稿子結構（使用者這次指定、並採用的寫法）

- 總長 2 分 10 秒，必寫的點：**球星出場 → 關鍵轉折 1 → 關鍵轉折 2 → 球星被三振 → 比賽結束 → 賽後受訪（球星一定要有 BITE）→ 以勝隊狂歡收尾**。
- **用球評 BITE 當 OPEN**：開頭第一段就是球星全壘打的球評，例：「There's a high drive… A ground shaking jolt on an Ohtani home run」。背景說明（背水一戰、調回第一棒）放在 SB 後的第一段 OS。
- 每個轉折點盡量配一句球評 SB，例：「They just keep on coming… to tie it up in the fifth」「Here it is. Gone. Milwaukee takes the lead」。沒有球評的轉折（例：大谷被三振那段，ASR 抓不到球評）用 OS 帶過。
- 比賽結束用最後一個出局數的球評，例：「for the first time in 44 years, the Brewers are going to the World Series」。
- 使用者人工稿的手法：
  - 球星 SB 前加一句情緒鋪陳：「賽後受訪時，他難掩失落，心有不甘。」
  - 勝隊總教練 SB 後接 `NS #08`（休息室噴香檳）
  - 最後一段 OS 以「比賽結果兩樣情」對比收尾

## 6. 日語 BITE 翻譯要連前文一起看

- 大谷原句「このメンバーでできるのも最後ですし」，前一句在講「每年陣容都不一樣」。
- AI 初譯寫成「能和這群隊友一起打球，就到今年為止了」，**會被讀成大谷要離隊**，使用者指出有問題。
- 改成：「今年這群成員一起打球的旅程也結束了，真的很不甘心，現在的心情大概就只有這樣。」
- 原則：SB 只取後半句時，翻譯仍要依整段語意，不能讓節錄的句子產生原話沒有的意思（離隊、退休、交易等）。

## 7. 譯名（本案採用）

| 英文 | 中文 |
|---|---|
| Garrett Mitchell | 米契爾 |
| Jake Bauers | 鮑爾斯 |
| David Hamilton | 漢米爾頓 |
| Aaron Ashby | 艾許比 |
| Jackson Chourio | 丘里奧 |
| Pat Murphy | 墨菲 |
| Christian Yelich | 葉利奇 |
| Alex Vesia | 維西亞 |
| Tanner Scott | 史考特 |
| Tyler Glasnow | 葛拉斯諾 |
| Dustin May | 梅伊 |
| Milwaukee Brewers | 密爾瓦基釀酒人 |

## 8. 後台上稿

- **議題包**：`MLB季後賽`（id 2033，季後賽期間）。
- **分類**：使用者預設是「國際」，後台另有「體育」（id 6），要換時由使用者決定。
- **延伸閱讀**：用「大谷」「道奇」「釀酒人」搜 `more-news` 就能湊滿 10 篇。
- **AP 照片三張**：球星開轟、球星失落（被三振後走回休息區）、勝隊噴香檳。
  - 打擊照的頭常在畫面最上緣，16:9 裁切時 `y` 從 0 起，不要置中裁，以免切到頭。
- **讀回驗證**：後台圖片網址要帶原本的 query（`?w=…&c=…`）才會回實圖。不帶 query 會回 1067x600 的 TVBS 灰色預設圖，用尺寸檢查會誤判為正常，要實際看圖。
